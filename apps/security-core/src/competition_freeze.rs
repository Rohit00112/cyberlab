//! Atomic competition leaderboard freeze/unfreeze with mandatory audit.
use deadpool_postgres::Pool;
use serde::{Deserialize, Serialize};

use crate::publishing::{validate_permission, PublishError, PublishRequest};

#[derive(Debug, Deserialize)]
pub struct CompetitionFreezeRequest {
    pub competition_id: String,
    pub actor_id: String,
    pub roles: Vec<String>,
    pub ip_address: Option<String>,
    pub frozen: bool,
}

#[derive(Debug, Serialize)]
pub struct CompetitionFreezeResponse {
    pub outcome: String,
}

pub fn validate(request: &CompetitionFreezeRequest) -> Result<(), PublishError> {
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

pub async fn set_frozen(
    pool: &Pool,
    request: &CompetitionFreezeRequest,
) -> Result<CompetitionFreezeResponse, PublishError> {
    validate(request)?;
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let tx = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    let competition = tx
        .query_opt(
            "SELECT slug FROM competitions WHERE id = ($1::text)::uuid FOR UPDATE",
            &[&request.competition_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(competition) = competition else {
        return Ok(CompetitionFreezeResponse {
            outcome: "not_found".into(),
        });
    };
    let slug: String = competition.get(0);
    // The public contract allows freeze or unfreeze in any lifecycle state,
    // including repeated requests. Each call is audited independently.
    tx.execute(
        "UPDATE competitions SET freeze_leaderboard = $2, \
         frozen_at = CASE WHEN $2 THEN now() ELSE NULL END, updated_at = now() \
         WHERE id = ($1::text)::uuid",
        &[&request.competition_id, &request.frozen],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    let event = if request.frozen {
        "competition.freeze"
    } else {
        "competition.unfreeze"
    };
    tx.execute(
        "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address) \
         VALUES (gen_random_uuid(), $1, ($2::text)::uuid, $3, $4)",
        &[&event, &request.actor_id, &slug, &request.ip_address],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.commit().await.map_err(|_| PublishError::Database)?;
    Ok(CompetitionFreezeResponse {
        outcome: "updated".into(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn permits_organizers_and_denies_invalid_identity() {
        let mut request = CompetitionFreezeRequest {
            competition_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee".into(),
            actor_id: "bbbbbbbb-cccc-dddd-eeee-ffffffffffff".into(),
            roles: vec!["faculty".into()],
            ip_address: None,
            frozen: true,
        };
        assert!(validate(&request).is_ok());
        request.roles = vec!["student".into()];
        assert!(matches!(validate(&request), Err(PublishError::Forbidden)));
        request.roles = vec!["faculty".into()];
        request.competition_id = "bad".into();
        assert!(matches!(validate(&request), Err(PublishError::Invalid)));
    }
}
