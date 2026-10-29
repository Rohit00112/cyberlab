//! Transactional challenge creation, taxonomy links, and audit recording.
use deadpool_postgres::Pool;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

use crate::editing::{sync_skills, validate_changes};
use crate::publishing::{validate_permission, PublishError, PublishRequest};

#[derive(Debug, Deserialize)]
pub struct CreateRequest {
    pub actor_id: String,
    pub roles: Vec<String>,
    pub ip_address: Option<String>,
    pub slug: String,
    pub fields: Map<String, Value>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct CreateResponse {
    pub outcome: String,
    pub challenge_id: String,
}

pub fn validate(request: &CreateRequest) -> Result<(), PublishError> {
    // There is no challenge ID yet; reuse the actor UUID and RBAC validation.
    validate_permission(
        &PublishRequest {
            challenge_id: request.actor_id.clone(),
            actor_id: request.actor_id.clone(),
            roles: request.roles.clone(),
            ip_address: request.ip_address.clone(),
        },
        "challenge.create",
    )?;
    if request.slug.is_empty()
        || request.slug.len() > 200
        || request.slug.starts_with('-')
        || request.slug.ends_with('-')
        || !request
            .slug
            .bytes()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'-')
    {
        return Err(PublishError::Invalid);
    }
    validate_changes(&request.fields)?;
    if !["title", "description", "category", "difficulty"]
        .iter()
        .all(|key| request.fields.contains_key(*key))
    {
        return Err(PublishError::Invalid);
    }
    Ok(())
}

pub async fn create(pool: &Pool, request: &CreateRequest) -> Result<CreateResponse, PublishError> {
    validate(request)?;
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let transaction = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    let fields = Value::Object(request.fields.clone()).to_string();
    let base = request.slug.chars().take(113).collect::<String>();
    let initial_slug = request.slug.chars().take(120).collect::<String>();

    // A unique constraint protects concurrent creators with the same title.
    // ON CONFLICT allows a retry without aborting the transaction.
    let mut inserted = None;
    for attempt in 0..8 {
        let slug = if attempt == 0 {
            initial_slug.clone()
        } else {
            let suffix: String = transaction
                .query_one(
                    "SELECT substr(replace(gen_random_uuid()::text, '-', ''), 1, 6)",
                    &[],
                )
                .await
                .map_err(|_| PublishError::Database)?
                .get(0);
            format!("{}-{suffix}", base.trim_end_matches('-'))
        };
        let row = transaction
            .query_opt(
                "INSERT INTO challenges (
                    id, slug, title, description, instructions, category, difficulty,
                    points, estimated_minutes, skills, prerequisites, hints, hint_penalty,
                    flag_hash, flag_format, environment_type, lab_config, author_id,
                    status, version
                 )
                 SELECT gen_random_uuid(), $1, data->>'title', data->>'description',
                    data->>'instructions', data->>'category', data->>'difficulty',
                    COALESCE((data->>'points')::integer, 0),
                    (data->>'estimated_minutes')::integer,
                    (data->'skills')::json, (data->'prerequisites')::json,
                    (data->'hints')::json,
                    COALESCE((data->>'hint_penalty')::integer, 0),
                    data->>'flag_hash', data->>'flag_format',
                    COALESCE(data->>'environment_type', 'none'),
                    (data->'lab_config')::json, ($3::text)::uuid, 'draft', 1
                 FROM (SELECT ($2::text)::jsonb AS data) AS payload
                 ON CONFLICT (slug) DO NOTHING
                 RETURNING id::text",
                &[&slug, &fields, &request.actor_id],
            )
            .await
            .map_err(|_| PublishError::Database)?;
        if let Some(row) = row {
            let id: String = row.get(0);
            inserted = Some((id, slug));
            break;
        }
    }
    let Some((challenge_id, slug)) = inserted else {
        return Err(PublishError::Database);
    };

    if let Some(skills) = request.fields.get("skills") {
        sync_skills(&transaction, &challenge_id, skills).await?;
    }
    transaction
        .execute(
            "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address)
             VALUES (gen_random_uuid(), 'challenge.create', ($1::text)::uuid, $2, $3)",
            &[&request.actor_id, &slug, &request.ip_address],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    transaction
        .commit()
        .await
        .map_err(|_| PublishError::Database)?;
    Ok(CreateResponse {
        outcome: "created".into(),
        challenge_id,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request() -> CreateRequest {
        CreateRequest {
            actor_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee".into(),
            roles: vec!["faculty".into()],
            ip_address: Some("127.0.0.1".into()),
            slug: "new-challenge".into(),
            fields: serde_json::from_value(serde_json::json!({
                "title":"New challenge", "description":"Find the flag",
                "category":"Linux", "difficulty":"beginner",
                "points":100, "skills":["Linux CLI"]
            }))
            .unwrap(),
        }
    }

    #[test]
    fn creation_requires_role_slug_and_all_required_fields() {
        assert!(validate(&request()).is_ok());
        let mut invalid = request();
        invalid.roles = vec!["student".into()];
        assert!(matches!(validate(&invalid), Err(PublishError::Forbidden)));
        invalid = request();
        invalid.slug = "../unauthorized".into();
        assert!(matches!(validate(&invalid), Err(PublishError::Invalid)));
        invalid = request();
        invalid.fields.remove("title");
        assert!(matches!(validate(&invalid), Err(PublishError::Invalid)));
        invalid = request();
        invalid
            .fields
            .insert("status".into(), Value::String("published".into()));
        assert!(matches!(validate(&invalid), Err(PublishError::Invalid)));
    }
}
