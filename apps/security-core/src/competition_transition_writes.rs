//! Persistent organizer transitions: re-evaluate the Rust policy under a
//! PostgreSQL row lock and audit the state change in the same transaction.
use deadpool_postgres::Pool;
use serde::{Deserialize, Serialize};

use crate::competition::{transition_competition, CompetitionTransitionRequest};
use crate::publishing::{validate_permission, PublishError, PublishRequest};

#[derive(Debug, Deserialize)]
pub struct ManualTransitionRequest {
    pub competition_id: String,
    pub action: String,
    pub actor_id: String,
    pub roles: Vec<String>,
    pub ip_address: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct ManualTransitionResponse {
    pub outcome: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub current_status: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub next_status: Option<String>,
}

fn response(
    outcome: &str,
    current_status: Option<String>,
    next_status: Option<String>,
) -> ManualTransitionResponse {
    ManualTransitionResponse {
        outcome: outcome.into(),
        current_status,
        next_status,
    }
}

pub fn validate(request: &ManualTransitionRequest) -> Result<(), PublishError> {
    validate_permission(
        &PublishRequest {
            challenge_id: request.competition_id.clone(),
            actor_id: request.actor_id.clone(),
            roles: request.roles.clone(),
            ip_address: request.ip_address.clone(),
        },
        "competition.manage",
    )
}

pub async fn persist(
    pool: &Pool,
    request: &ManualTransitionRequest,
) -> Result<ManualTransitionResponse, PublishError> {
    validate(request)?;
    // "auto" is scheduler-only. An internal caller cannot invoke automatic
    // transitions through an organizer endpoint by bypassing FastAPI's schema.
    if !matches!(
        request.action.as_str(),
        "start_registration" | "schedule" | "start" | "finish" | "archive"
    ) {
        return Ok(response("unknown_action", None, None));
    }
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let tx = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    let row = tx
        .query_opt(
            "SELECT slug, status, \
             floor(extract(epoch FROM start_at) * 1000)::bigint, \
             floor(extract(epoch FROM end_at) * 1000)::bigint, \
             floor(extract(epoch FROM now()) * 1000)::bigint \
             FROM competitions WHERE id = ($1::text)::uuid FOR UPDATE",
            &[&request.competition_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(row) = row else {
        return Ok(response("not_found", None, None));
    };
    let slug: String = row.get(0);
    let current: String = row.get(1);
    let decision = transition_competition(&CompetitionTransitionRequest {
        current: current.clone(),
        action: request.action.clone(),
        start_at: row.get(2),
        end_at: row.get(3),
        now: row.get(4),
    })
    .map_err(|_| PublishError::Database)?;
    if let Some(error) = decision.error_code {
        return Ok(response(&error, Some(current), None));
    }
    let next = decision.next_status.ok_or(PublishError::Database)?;
    tx.execute(
        "UPDATE competitions SET status = $2, updated_at = now() \
         WHERE id = ($1::text)::uuid",
        &[&request.competition_id, &next],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    let details = serde_json::json!({
        "action": request.action,
        "from": current,
        "to": next,
    })
    .to_string();
    tx.execute(
        "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address, details) \
         VALUES (gen_random_uuid(), 'competition.transition', \
         ($1::text)::uuid, $2, $3, ($4::text)::jsonb)",
        &[&request.actor_id, &slug, &request.ip_address, &details],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.commit().await.map_err(|_| PublishError::Database)?;
    Ok(response("updated", Some(current), Some(next)))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn requires_organizer_permission_and_valid_ids() {
        let mut request = ManualTransitionRequest {
            competition_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee".into(),
            action: "start_registration".into(),
            actor_id: "bbbbbbbb-cccc-dddd-eeee-ffffffffffff".into(),
            roles: vec!["faculty".into()],
            ip_address: None,
        };
        assert!(validate(&request).is_ok());
        request.roles = vec!["student".into()];
        assert!(matches!(validate(&request), Err(PublishError::Forbidden)));
        request.roles = vec!["faculty".into()];
        request.actor_id = "invalid".into();
        assert!(matches!(validate(&request), Err(PublishError::Invalid)));
    }
}
