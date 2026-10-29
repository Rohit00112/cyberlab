//! Competition challenge-link writes: lock state, mutate links and audit atomically.
use deadpool_postgres::Pool;
use serde::{Deserialize, Serialize};

use crate::publishing::{valid_uuid, validate_permission, PublishError, PublishRequest};

#[derive(Debug, Deserialize)]
pub struct CompetitionLinkRequest {
    pub competition_id: String,
    pub challenge_id: String,
    pub actor_id: String,
    pub roles: Vec<String>,
    pub ip_address: Option<String>,
    pub points: Option<i64>,
}

#[derive(Debug, Serialize)]
pub struct CompetitionLinkResponse {
    pub outcome: String,
}

fn response(outcome: &str) -> CompetitionLinkResponse {
    CompetitionLinkResponse {
        outcome: outcome.into(),
    }
}

pub fn validate(request: &CompetitionLinkRequest) -> Result<(), PublishError> {
    validate_permission(
        &PublishRequest {
            challenge_id: request.competition_id.clone(),
            actor_id: request.actor_id.clone(),
            roles: request.roles.clone(),
            ip_address: request.ip_address.clone(),
        },
        "competition.manage",
    )?;
    if !valid_uuid(&request.challenge_id)
        || request
            .points
            .is_some_and(|points| !(0..=i32::MAX as i64).contains(&points))
    {
        return Err(PublishError::Invalid);
    }
    Ok(())
}

pub async fn add(
    pool: &Pool,
    request: &CompetitionLinkRequest,
) -> Result<CompetitionLinkResponse, PublishError> {
    validate(request)?;
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let tx = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    let row = tx
        .query_opt(
            "SELECT slug, status, scoring_mode FROM competitions \
             WHERE id = ($1::text)::uuid FOR UPDATE",
            &[&request.competition_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(row) = row else {
        return Ok(response("not_found"));
    };
    let slug: String = row.get(0);
    let status: String = row.get(1);
    let scoring_mode: String = row.get(2);
    if !matches!(status.as_str(), "draft" | "registration") {
        return Ok(response("locked"));
    }
    let challenge = tx
        .query_opt(
            "SELECT status FROM challenges WHERE id = ($1::text)::uuid",
            &[&request.challenge_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    if !challenge.is_some_and(|row| row.get::<_, String>(0) == "published") {
        return Ok(response("challenge_not_found"));
    }
    let position: i32 = tx
        .query_one(
            "SELECT COALESCE(MAX(position), -1) FROM competition_challenges \
             WHERE competition_id = ($1::text)::uuid",
            &[&request.competition_id],
        )
        .await
        .map_err(|_| PublishError::Database)?
        .get(0);
    let next_position = position.checked_add(1).ok_or(PublishError::Database)?;
    let points = if scoring_mode == "override" {
        request.points.map(|value| value as i32)
    } else {
        None
    };
    let inserted = tx
        .query_opt(
            "INSERT INTO competition_challenges \
             (id, competition_id, challenge_id, points, position) \
             VALUES (gen_random_uuid(), ($1::text)::uuid, ($2::text)::uuid, $3, $4) \
             ON CONFLICT (competition_id, challenge_id) DO NOTHING RETURNING id::text",
            &[
                &request.competition_id,
                &request.challenge_id,
                &points,
                &next_position,
            ],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    if inserted.is_none() {
        return Ok(response("duplicate"));
    }
    let details = serde_json::json!({"competition": slug}).to_string();
    tx.execute(
        "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address, details) \
         VALUES (gen_random_uuid(), 'competition.challenge_add', \
         ($1::text)::uuid, $2, $3, ($4::text)::jsonb)",
        &[
            &request.actor_id,
            &request.challenge_id,
            &request.ip_address,
            &details,
        ],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.commit().await.map_err(|_| PublishError::Database)?;
    Ok(response("added"))
}

pub async fn remove(
    pool: &Pool,
    request: &CompetitionLinkRequest,
) -> Result<CompetitionLinkResponse, PublishError> {
    validate(request)?;
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let tx = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    let row = tx
        .query_opt(
            "SELECT slug, status FROM competitions \
             WHERE id = ($1::text)::uuid FOR UPDATE",
            &[&request.competition_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(row) = row else {
        return Ok(response("not_found"));
    };
    let slug: String = row.get(0);
    let status: String = row.get(1);
    if !matches!(status.as_str(), "draft" | "registration") {
        return Ok(response("locked"));
    }
    // The legacy DELETE is idempotent: even a missing link receives an audit.
    tx.execute(
        "DELETE FROM competition_challenges WHERE competition_id = ($1::text)::uuid \
         AND challenge_id = ($2::text)::uuid",
        &[&request.competition_id, &request.challenge_id],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    let details = serde_json::json!({"competition": slug}).to_string();
    tx.execute(
        "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address, details) \
         VALUES (gen_random_uuid(), 'competition.challenge_remove', \
         ($1::text)::uuid, $2, $3, ($4::text)::jsonb)",
        &[
            &request.actor_id,
            &request.challenge_id,
            &request.ip_address,
            &details,
        ],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.commit().await.map_err(|_| PublishError::Database)?;
    Ok(response("removed"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn validates_organizer_permissions_ids_and_points() {
        let mut request = CompetitionLinkRequest {
            competition_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee".into(),
            challenge_id: "bbbbbbbb-cccc-dddd-eeee-ffffffffffff".into(),
            actor_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee".into(),
            roles: vec!["faculty".into()],
            ip_address: None,
            points: Some(0),
        };
        assert!(validate(&request).is_ok());
        request.roles = vec!["student".into()];
        assert!(matches!(validate(&request), Err(PublishError::Forbidden)));
        request.roles = vec!["faculty".into()];
        request.points = Some(-1);
        assert!(matches!(validate(&request), Err(PublishError::Invalid)));
        request.points = None;
        request.challenge_id = "invalid".into();
        assert!(matches!(validate(&request), Err(PublishError::Invalid)));
    }
}
