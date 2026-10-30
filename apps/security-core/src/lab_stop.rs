//! Transactional manual lab stop finalization after the provider confirms shutdown.
//!
//! Provider I/O stays in FastAPI. This writer independently verifies the actor,
//! lab state and exact provider handle before recording the stop and its audit.
use deadpool_postgres::Pool;
use serde::{Deserialize, Serialize};

use crate::authorization::{authorize, AuthorizationRequest};
use crate::publishing::{validate_permission, PublishError, PublishRequest};

#[derive(Debug, Deserialize)]
pub struct LabStopRequest {
    pub lab_id: String,
    pub actor_id: String,
    pub roles: Vec<String>,
    pub ip_address: Option<String>,
    pub expected_provider_ref: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct LabStopResponse {
    pub outcome: String,
    pub current_status: Option<String>,
}

pub fn validate(request: &LabStopRequest) -> Result<(), PublishError> {
    validate_permission(
        &PublishRequest {
            challenge_id: request.lab_id.clone(),
            actor_id: request.actor_id.clone(),
            roles: request.roles.clone(),
            ip_address: request.ip_address.clone(),
        },
        "lab.launch",
    )?;
    if request
        .expected_provider_ref
        .as_ref()
        .is_some_and(|reference| reference.is_empty() || reference.len() > 255)
    {
        return Err(PublishError::Invalid);
    }
    Ok(())
}

pub async fn finalize(
    pool: &Pool,
    request: &LabStopRequest,
) -> Result<LabStopResponse, PublishError> {
    validate(request)?;
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let tx = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    let row = tx
        .query_opt(
            "SELECT user_id::text, status, COALESCE(provider_ref, container_id) FROM lab_instances WHERE id = ($1::text)::uuid FOR UPDATE",
            &[&request.lab_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(row) = row else {
        return Ok(LabStopResponse {
            outcome: "not_found".into(),
            current_status: None,
        });
    };
    let owner: String = row.get(0);
    let state: String = row.get(1);
    let provider_ref: Option<String> = row.get(2);
    if owner != request.actor_id {
        let allowed = authorize(&AuthorizationRequest {
            roles: request.roles.clone(),
            permission: Some("lab.admin".into()),
        })
        .map_err(|_| PublishError::Invalid)?;
        if allowed.allowed != Some(true) {
            return Err(PublishError::Forbidden);
        }
    }
    if state == "stopped" {
        return Ok(LabStopResponse {
            outcome: "already_stopped".into(),
            current_status: None,
        });
    }
    if state != "running" {
        return Ok(LabStopResponse {
            outcome: "not_running".into(),
            current_status: Some(state),
        });
    }
    if provider_ref.is_none() {
        return Ok(LabStopResponse {
            outcome: "provider_missing".into(),
            current_status: None,
        });
    }
    if provider_ref != request.expected_provider_ref {
        return Ok(LabStopResponse {
            outcome: "stale_provider".into(),
            current_status: None,
        });
    }
    tx.execute(
        "UPDATE lab_instances SET status = 'stopped', updated_at = now() WHERE id = ($1::text)::uuid",
        &[&request.lab_id],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.execute(
        "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address) VALUES (gen_random_uuid(), 'lab.stop', ($1::text)::uuid, $2, $3)",
        &[&request.actor_id, &request.lab_id, &request.ip_address],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.commit().await.map_err(|_| PublishError::Database)?;
    Ok(LabStopResponse {
        outcome: "stopped".into(),
        current_status: None,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn validates_identity_permission_and_provider_reference() {
        let mut request = LabStopRequest {
            lab_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee".into(),
            actor_id: "bbbbbbbb-cccc-dddd-eeee-ffffffffffff".into(),
            roles: vec!["student".into()],
            ip_address: None,
            expected_provider_ref: Some("owned-container".into()),
        };
        assert!(validate(&request).is_ok());
        request.roles = vec!["guest".into()];
        assert!(matches!(validate(&request), Err(PublishError::Forbidden)));
        request.roles = vec!["student".into()];
        request.expected_provider_ref = Some("x".repeat(256));
        assert!(matches!(validate(&request), Err(PublishError::Invalid)));
        request.expected_provider_ref = None;
        request.lab_id = "../invalid".into();
        assert!(matches!(validate(&request), Err(PublishError::Invalid)));
    }
}
