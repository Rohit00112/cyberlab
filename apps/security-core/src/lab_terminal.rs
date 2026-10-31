//! Atomic manual expiry and administrative termination after provider I/O.
//!
//! The API is responsible for stopping/removing the guest. Rust locks the lab,
//! rechecks permissions and the provider handle, then writes status and audit.
use deadpool_postgres::Pool;
use serde::{Deserialize, Serialize};

use crate::authorization::{authorize, AuthorizationRequest};
use crate::publishing::{validate_permission, PublishError, PublishRequest};

#[derive(Debug, Clone, Copy, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum LabTerminalAction {
    Expire,
    Terminate,
}

#[derive(Debug, Deserialize)]
pub struct LabTerminalRequest {
    pub action: LabTerminalAction,
    pub lab_id: String,
    pub actor_id: String,
    pub roles: Vec<String>,
    pub ip_address: Option<String>,
    pub expected_provider_ref: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct LabTerminalResponse {
    pub outcome: String,
    pub current_status: Option<String>,
}

pub fn validate(request: &LabTerminalRequest) -> Result<(), PublishError> {
    let permission = match request.action {
        LabTerminalAction::Expire => "lab.launch",
        LabTerminalAction::Terminate => "lab.admin",
    };
    validate_permission(
        &PublishRequest {
            challenge_id: request.lab_id.clone(),
            actor_id: request.actor_id.clone(),
            roles: request.roles.clone(),
            ip_address: request.ip_address.clone(),
        },
        permission,
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
    request: &LabTerminalRequest,
) -> Result<LabTerminalResponse, PublishError> {
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
        return Ok(LabTerminalResponse {
            outcome: "not_found".into(),
            current_status: None,
        });
    };
    let owner: String = row.get(0);
    let state: String = row.get(1);
    let provider_ref: Option<String> = row.get(2);
    if matches!(request.action, LabTerminalAction::Expire) && owner != request.actor_id {
        let allowed = authorize(&AuthorizationRequest {
            roles: request.roles.clone(),
            permission: Some("lab.admin".into()),
        })
        .map_err(|_| PublishError::Invalid)?;
        if allowed.allowed != Some(true) {
            return Err(PublishError::Forbidden);
        }
    }
    if provider_ref != request.expected_provider_ref {
        return Ok(LabTerminalResponse {
            outcome: "stale_provider".into(),
            current_status: None,
        });
    }
    if state == "expired" {
        // Expiry only stops a guest; admin termination may subsequently remove
        // the same expired guest. Preserve an audit of that cleanup action.
        if matches!(request.action, LabTerminalAction::Terminate) {
            tx.execute(
                "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address) VALUES (gen_random_uuid(), 'lab.terminate', ($1::text)::uuid, $2, $3)",
                &[&request.actor_id, &request.lab_id, &request.ip_address],
            )
            .await
            .map_err(|_| PublishError::Database)?;
            tx.commit().await.map_err(|_| PublishError::Database)?;
        }
        return Ok(LabTerminalResponse {
            outcome: "already_expired".into(),
            current_status: None,
        });
    }
    if state == "running" && provider_ref.is_none() {
        return Ok(LabTerminalResponse {
            outcome: "provider_missing".into(),
            current_status: None,
        });
    }
    // A worker can still be creating or replacing a guest in these states.
    // Expiring the row would misrepresent the provider's actual lifecycle.
    if matches!(
        state.as_str(),
        "provisioning" | "starting" | "resetting" | "stopping" | "terminating"
    ) {
        return Ok(LabTerminalResponse {
            outcome: "state_changed".into(),
            current_status: Some(state),
        });
    }
    let audit_event = match request.action {
        LabTerminalAction::Expire => "lab.expire",
        LabTerminalAction::Terminate => "lab.terminate",
    };
    tx.execute(
        "UPDATE lab_instances SET status = 'expired', updated_at = now() WHERE id = ($1::text)::uuid",
        &[&request.lab_id],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.execute(
        "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address) VALUES (gen_random_uuid(), $1, ($2::text)::uuid, $3, $4)",
        &[&audit_event, &request.actor_id, &request.lab_id, &request.ip_address],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.commit().await.map_err(|_| PublishError::Database)?;
    Ok(LabTerminalResponse {
        outcome: "expired".into(),
        current_status: None,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request(action: LabTerminalAction, roles: Vec<String>) -> LabTerminalRequest {
        LabTerminalRequest {
            action,
            lab_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee".into(),
            actor_id: "bbbbbbbb-cccc-dddd-eeee-ffffffffffff".into(),
            roles,
            ip_address: None,
            expected_provider_ref: Some("guest".into()),
        }
    }

    #[test]
    fn validates_manual_and_admin_permissions() {
        assert!(validate(&request(LabTerminalAction::Expire, vec!["student".into()])).is_ok());
        assert!(matches!(
            validate(&request(
                LabTerminalAction::Terminate,
                vec!["student".into()]
            )),
            Err(PublishError::Forbidden)
        ));
        assert!(validate(&request(
            LabTerminalAction::Terminate,
            vec!["sysadmin".into()]
        ))
        .is_ok());
        let mut invalid = request(LabTerminalAction::Expire, vec!["student".into()]);
        invalid.expected_provider_ref = Some("x".repeat(256));
        assert!(matches!(validate(&invalid), Err(PublishError::Invalid)));
    }
}
