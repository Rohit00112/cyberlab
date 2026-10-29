//! Atomic competition draft creation; authentication stays at FastAPI.
use deadpool_postgres::Pool;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

use crate::publishing::{validate_permission, PublishError, PublishRequest};

#[derive(Debug, Deserialize)]
pub struct CompetitionCreateRequest {
    pub actor_id: String,
    pub roles: Vec<String>,
    pub ip_address: Option<String>,
    pub slug: String,
    pub fields: Map<String, Value>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct CompetitionCreateResponse {
    pub outcome: String,
    pub competition_id: String,
}

#[derive(Debug, Deserialize)]
pub struct CompetitionEditRequest {
    pub competition_id: String,
    pub actor_id: String,
    pub roles: Vec<String>,
    pub ip_address: Option<String>,
    pub changes: Map<String, Value>,
}

#[derive(Debug, Serialize)]
pub struct CompetitionEditResponse {
    pub outcome: String,
}

pub fn validate_edit(request: &CompetitionEditRequest) -> Result<(), PublishError> {
    validate_permission(
        &PublishRequest {
            actor_id: request.actor_id.clone(),
            challenge_id: request.competition_id.clone(),
            roles: request.roles.clone(),
            ip_address: request.ip_address.clone(),
        },
        "competition.manage",
    )?;
    for (key, value) in &request.changes {
        let valid = match key.as_str() {
            "title" => value
                .as_str()
                .is_some_and(|s| !s.is_empty() && s.chars().count() <= 200),
            "description" | "rules" | "start_at" | "end_at" | "registration_ends_at" => {
                value.is_null() || value.is_string()
            }
            "allow_teams" => value.is_boolean(),
            "max_team_size" => value.as_i64().is_some_and(|size| (1..=10).contains(&size)),
            "scoring_mode" => matches!(value.as_str(), Some("standard" | "override")),
            // Never accept direct status, freeze, audit or ownership edits.
            _ => false,
        };
        if !valid {
            return Err(PublishError::Invalid);
        }
    }
    Ok(())
}

pub async fn edit(
    pool: &Pool,
    request: &CompetitionEditRequest,
) -> Result<CompetitionEditResponse, PublishError> {
    validate_edit(request)?;
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let tx = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    let row = tx
        .query_opt(
            "SELECT slug, status FROM competitions WHERE id = ($1::text)::uuid FOR UPDATE",
            &[&request.competition_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(row) = row else {
        return Ok(CompetitionEditResponse {
            outcome: "not_found".into(),
        });
    };
    let slug: String = row.get(0);
    let current_status: String = row.get(1);
    if !matches!(
        current_status.as_str(),
        "draft" | "registration" | "scheduled"
    ) {
        return Ok(CompetitionEditResponse {
            outcome: "locked".into(),
        });
    }

    let json = Value::Object(request.changes.clone()).to_string();
    for key in ["start_at", "end_at", "registration_ends_at"] {
        if let Some(stamp) = request.changes.get(key).and_then(Value::as_str) {
            tx.query_one("SELECT ($1::text)::timestamptz", &[&stamp])
                .await
                .map_err(|_| PublishError::Invalid)?;
        }
    }
    // Match the existing public PATCH rule: compare the two proposed dates
    // only when both are supplied, not against unchanged stored dates.
    if request
        .changes
        .get("start_at")
        .and_then(Value::as_str)
        .is_some()
        && request
            .changes
            .get("end_at")
            .and_then(Value::as_str)
            .is_some()
    {
        let invalid: bool = tx
            .query_one(
                "SELECT ($1::text::jsonb->>'start_at')::timestamptz >= \
                        ($1::text::jsonb->>'end_at')::timestamptz",
                &[&json],
            )
            .await
            .map_err(|_| PublishError::Invalid)?
            .get(0);
        if invalid {
            return Err(PublishError::Invalid);
        }
    }

    let mut assignments = Vec::new();
    for key in request.changes.keys() {
        // These fragments are constants selected by a validated allowlist;
        // no caller-controlled SQL identifiers or values are interpolated.
        let expression = match key.as_str() {
            "title" => "title = $2::text::jsonb->>'title'",
            "description" => "description = $2::text::jsonb->>'description'",
            "rules" => "rules = $2::text::jsonb->>'rules'",
            "start_at" => "start_at = ($2::text::jsonb->>'start_at')::timestamptz",
            "end_at" => "end_at = ($2::text::jsonb->>'end_at')::timestamptz",
            "registration_ends_at" => {
                "registration_ends_at = ($2::text::jsonb->>'registration_ends_at')::timestamptz"
            }
            "allow_teams" => "allow_teams = ($2::text::jsonb->>'allow_teams')::boolean",
            "max_team_size" => "max_team_size = ($2::text::jsonb->>'max_team_size')::integer",
            "scoring_mode" => "scoring_mode = $2::text::jsonb->>'scoring_mode'",
            _ => return Err(PublishError::Invalid),
        };
        assignments.push(expression);
    }
    if !assignments.is_empty() {
        assignments.push("updated_at = now()");
        let query = format!(
            "UPDATE competitions SET {} WHERE id = ($1::text)::uuid",
            assignments.join(", ")
        );
        tx.execute(&query, &[&request.competition_id, &json])
            .await
            .map_err(|_| PublishError::Database)?;
    }
    tx.execute(
        "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address)
         VALUES (gen_random_uuid(), 'competition.update', ($1::text)::uuid, $2, $3)",
        &[&request.actor_id, &slug, &request.ip_address],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.commit().await.map_err(|_| PublishError::Database)?;
    Ok(CompetitionEditResponse {
        outcome: "updated".into(),
    })
}

pub fn validate(request: &CompetitionCreateRequest) -> Result<(), PublishError> {
    validate_permission(
        &PublishRequest {
            actor_id: request.actor_id.clone(),
            challenge_id: request.actor_id.clone(),
            roles: request.roles.clone(),
            ip_address: request.ip_address.clone(),
        },
        "competition.create",
    )?;
    if request.slug.is_empty()
        || request.slug.len() > 120
        || request.slug.starts_with('-')
        || request.slug.ends_with('-')
        || !request
            .slug
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
    {
        return Err(PublishError::Invalid);
    }
    let Some(title) = request.fields.get("title").and_then(Value::as_str) else {
        return Err(PublishError::Invalid);
    };
    if title.is_empty() || title.chars().count() > 200 {
        return Err(PublishError::Invalid);
    }
    if request.fields.keys().any(|key| {
        !matches!(
            key.as_str(),
            "title"
                | "description"
                | "rules"
                | "start_at"
                | "end_at"
                | "registration_ends_at"
                | "allow_teams"
                | "max_team_size"
                | "scoring_mode"
        )
    }) {
        return Err(PublishError::Invalid);
    }
    if [
        "description",
        "rules",
        "start_at",
        "end_at",
        "registration_ends_at",
    ]
    .iter()
    .any(|key| {
        request
            .fields
            .get(*key)
            .is_some_and(|v| !v.is_null() && !v.is_string())
    }) || request
        .fields
        .get("allow_teams")
        .is_some_and(|v| !v.is_boolean())
        || request
            .fields
            .get("max_team_size")
            .is_some_and(|v| !v.as_i64().is_some_and(|n| (1..=10).contains(&n)))
        || request
            .fields
            .get("scoring_mode")
            .is_some_and(|v| !matches!(v.as_str(), Some("standard" | "override")))
    {
        return Err(PublishError::Invalid);
    }
    Ok(())
}

pub async fn create(
    pool: &Pool,
    request: &CompetitionCreateRequest,
) -> Result<CompetitionCreateResponse, PublishError> {
    validate(request)?;
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let tx = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    let json = Value::Object(request.fields.clone()).to_string();
    let mut created = None;
    for attempt in 0..8 {
        let slug = if attempt == 0 {
            request.slug.clone()
        } else {
            let suffix: String = tx
                .query_one(
                    "SELECT left(replace(gen_random_uuid()::text, '-', ''), 6)",
                    &[],
                )
                .await
                .map_err(|_| PublishError::Database)?
                .get(0);
            format!(
                "{}-{suffix}",
                request
                    .slug
                    .chars()
                    .take(113)
                    .collect::<String>()
                    .trim_end_matches('-')
            )
        };
        let row = tx
            .query_opt(
                "INSERT INTO competitions
             (id, slug, title, description, rules, start_at, end_at,
              registration_ends_at, allow_teams, max_team_size, scoring_mode,
              status, created_by, freeze_leaderboard)
             SELECT gen_random_uuid(), $1, data->>'title', data->>'description',
                data->>'rules', (data->>'start_at')::timestamptz,
                (data->>'end_at')::timestamptz,
                (data->>'registration_ends_at')::timestamptz,
                COALESCE((data->>'allow_teams')::boolean, false),
                COALESCE((data->>'max_team_size')::integer, 4),
                COALESCE(data->>'scoring_mode', 'standard'), 'draft', ($3::text)::uuid, false
             FROM (SELECT ($2::text)::jsonb AS data) p
             ON CONFLICT (slug) DO NOTHING RETURNING id::text",
                &[&slug, &json, &request.actor_id],
            )
            .await
            .map_err(|_| PublishError::Database)?;
        if let Some(row) = row {
            created = Some((row.get::<_, String>(0), slug));
            break;
        }
    }
    let Some((competition_id, slug)) = created else {
        return Err(PublishError::Database);
    };
    // If the audit cannot be saved, PostgreSQL rolls back the competition too.
    tx.execute(
        "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address)
         VALUES (gen_random_uuid(), 'competition.create', ($1::text)::uuid, $2, $3)",
        &[&request.actor_id, &slug, &request.ip_address],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.commit().await.map_err(|_| PublishError::Database)?;
    Ok(CompetitionCreateResponse {
        outcome: "created".into(),
        competition_id,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn request() -> CompetitionCreateRequest {
        CompetitionCreateRequest {
            actor_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee".into(),
            roles: vec!["faculty".into()],
            ip_address: None,
            slug: "campus-ctf".into(),
            fields: serde_json::from_value(serde_json::json!({
                "title": "Campus CTF", "scoring_mode": "standard", "max_team_size": 4
            }))
            .unwrap(),
        }
    }
    #[test]
    fn enforces_role_and_input_contract() {
        let mut req = request();
        assert!(validate(&req).is_ok());
        req.roles = vec!["student".into()];
        assert!(matches!(validate(&req), Err(PublishError::Forbidden)));
        req.roles = vec!["faculty".into()];
        req.fields
            .insert("status".into(), Value::String("live".into()));
        assert!(matches!(validate(&req), Err(PublishError::Invalid)));
        req.fields.remove("status");
        req.fields
            .insert("max_team_size".into(), Value::Number(50.into()));
        assert!(matches!(validate(&req), Err(PublishError::Invalid)));
    }

    #[test]
    fn editing_rechecks_manage_permission_and_field_allowlist() {
        let mut req = CompetitionEditRequest {
            competition_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee".into(),
            actor_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee".into(),
            roles: vec!["faculty".into()],
            ip_address: None,
            changes: serde_json::from_value(serde_json::json!({
                "description": null, "title": "Updated", "allow_teams": false
            }))
            .unwrap(),
        };
        assert!(validate_edit(&req).is_ok());
        req.roles = vec!["student".into()];
        assert!(matches!(validate_edit(&req), Err(PublishError::Forbidden)));
        req.roles = vec!["faculty".into()];
        req.changes
            .insert("status".into(), Value::String("live".into()));
        assert!(matches!(validate_edit(&req), Err(PublishError::Invalid)));
        req.changes.remove("status");
        req.changes.insert("title".into(), Value::Null);
        assert!(matches!(validate_edit(&req), Err(PublishError::Invalid)));
    }
}
