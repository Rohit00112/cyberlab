//! Atomic, role-gated competition self-registration and unregistration.
use deadpool_postgres::Pool;
use serde::{Deserialize, Serialize};

use crate::publishing::{validate_permission, PublishError, PublishRequest};

#[derive(Debug, Deserialize)]
pub struct ParticipantRequest {
    pub competition_id: String,
    pub actor_id: String,
    pub roles: Vec<String>,
    pub ip_address: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct ParticipantResponse {
    pub outcome: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub current_status: Option<String>,
}

fn response(outcome: &str, current_status: Option<String>) -> ParticipantResponse {
    ParticipantResponse {
        outcome: outcome.into(),
        current_status,
    }
}

pub fn validate(request: &ParticipantRequest) -> Result<(), PublishError> {
    validate_permission(
        &PublishRequest {
            challenge_id: request.competition_id.clone(),
            actor_id: request.actor_id.clone(),
            roles: request.roles.clone(),
            ip_address: request.ip_address.clone(),
        },
        "challenge.attempt",
    )
}

pub async fn register(
    pool: &Pool,
    request: &ParticipantRequest,
) -> Result<ParticipantResponse, PublishError> {
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
        return Ok(response("not_found", None));
    };
    let slug: String = row.get(0);
    let status: String = row.get(1);
    if !matches!(status.as_str(), "registration" | "scheduled") {
        return Ok(response("closed", Some(status)));
    }
    let inserted = tx
        .query_opt(
            "INSERT INTO competition_participants (id, competition_id, user_id) \
             VALUES (gen_random_uuid(), ($1::text)::uuid, ($2::text)::uuid) \
             ON CONFLICT (competition_id, user_id) DO NOTHING RETURNING id::text",
            &[&request.competition_id, &request.actor_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    if inserted.is_none() {
        return Ok(response("already_registered", None));
    }
    tx.execute(
        "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address) \
         VALUES (gen_random_uuid(), 'competition.register', ($1::text)::uuid, $2, $3)",
        &[&request.actor_id, &slug, &request.ip_address],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.commit().await.map_err(|_| PublishError::Database)?;
    Ok(response("registered", None))
}

pub async fn unregister(
    pool: &Pool,
    request: &ParticipantRequest,
) -> Result<ParticipantResponse, PublishError> {
    validate(request)?;
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let tx = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    let row = tx
        .query_opt(
            "SELECT slug FROM competitions WHERE id = ($1::text)::uuid FOR UPDATE",
            &[&request.competition_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(row) = row else {
        return Ok(response("not_found", None));
    };
    let slug: String = row.get(0);
    let participant = tx
        .query_opt(
            "SELECT team_id::text FROM competition_participants \
             WHERE competition_id = ($1::text)::uuid AND user_id = ($2::text)::uuid",
            &[&request.competition_id, &request.actor_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(participant) = participant else {
        return Ok(response("not_registered", None));
    };
    let team_id: Option<String> = participant.get(0);
    tx.execute(
        "DELETE FROM competition_participants \
         WHERE competition_id = ($1::text)::uuid AND user_id = ($2::text)::uuid",
        &[&request.competition_id, &request.actor_id],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    if let Some(team_id) = team_id {
        tx.execute(
            "DELETE FROM team_members \
             WHERE team_id = ($1::text)::uuid AND user_id = ($2::text)::uuid",
            &[&team_id, &request.actor_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    }
    tx.execute(
        "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address) \
         VALUES (gen_random_uuid(), 'competition.unregister', ($1::text)::uuid, $2, $3)",
        &[&request.actor_id, &slug, &request.ip_address],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.commit().await.map_err(|_| PublishError::Database)?;
    Ok(response("unregistered", None))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_unauthorized_participant_actions() {
        let mut request = ParticipantRequest {
            competition_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee".into(),
            actor_id: "bbbbbbbb-cccc-dddd-eeee-ffffffffffff".into(),
            roles: vec!["student".into()],
            ip_address: None,
        };
        assert!(validate(&request).is_ok());
        request.roles = vec!["competition_organizer".into()];
        assert!(matches!(validate(&request), Err(PublishError::Forbidden)));
        request.roles = vec!["student".into()];
        request.actor_id = "bad-id".into();
        assert!(matches!(validate(&request), Err(PublishError::Invalid)));
    }
}
