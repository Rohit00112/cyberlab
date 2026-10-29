//! Persist incorrect flag attempts with an audit event in one transaction.
//! The gateway verifies flag correctness and authenticates Keycloak users.
//! Correct solves use the existing scoring transaction until migrated as a whole.
use deadpool_postgres::Pool;
use serde::{Deserialize, Serialize};

use crate::publishing::{validate_permission, PublishError, PublishRequest};

#[derive(Debug, Deserialize)]
pub struct IncorrectAttemptRequest {
    pub challenge_id: String,
    pub user_id: String,
    pub roles: Vec<String>,
    pub ip_address: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct IncorrectAttemptResponse {
    pub outcome: String,
}

pub async fn record(
    pool: &Pool,
    request: &IncorrectAttemptRequest,
) -> Result<IncorrectAttemptResponse, PublishError> {
    validate_permission(
        &PublishRequest {
            challenge_id: request.challenge_id.clone(),
            actor_id: request.user_id.clone(),
            roles: request.roles.clone(),
            ip_address: request.ip_address.clone(),
        },
        "submission.create",
    )?;
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let transaction = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    // Recheck challenge visibility in the writer database rather than trusting
    // the caller's stale ORM object. No flag or expected hash is exposed here.
    let row = transaction
        .query_opt(
            "SELECT slug FROM challenges WHERE id = ($1::text)::uuid AND status = 'published'",
            &[&request.challenge_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(row) = row else {
        return Ok(IncorrectAttemptResponse {
            outcome: "not_found".into(),
        });
    };
    let slug: String = row.get(0);
    transaction
        .execute(
            "INSERT INTO submissions (id, challenge_id, user_id, is_correct, earned_points)
             VALUES (gen_random_uuid(), ($1::text)::uuid, ($2::text)::uuid, false, 0)",
            &[&request.challenge_id, &request.user_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    transaction
        .execute(
            "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address, details)
             VALUES (gen_random_uuid(), 'submission.attempt', ($1::text)::uuid, $2, $3,
                     '{\"correct\":false,\"points\":0}'::json)",
            &[&request.user_id, &slug, &request.ip_address],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    transaction
        .commit()
        .await
        .map_err(|_| PublishError::Database)?;
    Ok(IncorrectAttemptResponse {
        outcome: "recorded".into(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn write_requires_submission_role_and_uuid() {
        let mut request = IncorrectAttemptRequest {
            challenge_id: "11111111-2222-3333-4444-555555555555".into(),
            user_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee".into(),
            roles: vec!["student".into()],
            ip_address: None,
        };
        assert!(validate_permission(
            &PublishRequest {
                challenge_id: request.challenge_id.clone(),
                actor_id: request.user_id.clone(),
                roles: request.roles.clone(),
                ip_address: None,
            },
            "submission.create"
        )
        .is_ok());
        request.roles = vec![];
        assert!(matches!(
            validate_permission(
                &PublishRequest {
                    challenge_id: request.challenge_id.clone(),
                    actor_id: request.user_id.clone(),
                    roles: request.roles,
                    ip_address: None,
                },
                "submission.create"
            ),
            Err(PublishError::Forbidden)
        ));
    }
}
