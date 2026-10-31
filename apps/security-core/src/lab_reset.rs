//! Guarded lab reset claims and terminal writes; provider I/O stays in FastAPI.
//!
//! Claiming the row before destroying the old resource prevents competing
//! reset/expiry operations. Completion and failure each include their audit.
use deadpool_postgres::Pool;
use serde::{Deserialize, Serialize};
use tokio_postgres::Transaction;

use crate::authorization::{authorize, AuthorizationRequest};
use crate::publishing::{validate_permission, PublishError, PublishRequest};

#[derive(Debug, Deserialize)]
pub struct ResetIdentity {
    pub lab_id: String,
    pub actor_id: String,
    pub roles: Vec<String>,
    pub ip_address: Option<String>,
    pub expected_old_ref: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct ResetBeginRequest {
    #[serde(flatten)]
    pub actor: ResetIdentity,
}

#[derive(Debug, Deserialize)]
pub struct ResetCompleteRequest {
    #[serde(flatten)]
    pub actor: ResetIdentity,
    pub provider: String,
    pub provider_ref: String,
    pub container_name: String,
    pub flag_hash: String,
    pub flag_path: String,
    pub connection_hint: String,
    pub expiry_minutes: i32,
}

#[derive(Debug, Deserialize)]
pub struct ResetFailRequest {
    #[serde(flatten)]
    pub actor: ResetIdentity,
    pub error_message: String,
    pub remaining_provider_ref: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct ResetResponse {
    pub outcome: String,
}

fn valid_ref(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
}

pub fn validate_actor(request: &ResetIdentity) -> Result<(), PublishError> {
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
        .expected_old_ref
        .as_deref()
        .is_some_and(|reference| !valid_ref(reference))
    {
        return Err(PublishError::Invalid);
    }
    Ok(())
}

pub fn validate_complete(request: &ResetCompleteRequest) -> Result<(), PublishError> {
    validate_actor(&request.actor)?;
    if !matches!(request.provider.as_str(), "docker" | "proxmox" | "libvirt")
        || !valid_ref(&request.provider_ref)
        || !valid_ref(&request.container_name)
        || request.flag_hash.len() != 64
        || !request
            .flag_hash
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
        || !request.flag_path.starts_with('/')
        || request.flag_path.len() > 255
        || request.flag_path.contains('\0')
        || request.connection_hint.len() > 2048
        || !(1..=525_600).contains(&request.expiry_minutes)
    {
        return Err(PublishError::Invalid);
    }
    Ok(())
}

pub fn validate_fail(request: &ResetFailRequest) -> Result<(), PublishError> {
    validate_actor(&request.actor)?;
    if request.error_message.is_empty()
        || request.error_message.len() > 4096
        || request
            .remaining_provider_ref
            .as_deref()
            .is_some_and(|reference| !valid_ref(reference))
    {
        return Err(PublishError::Invalid);
    }
    Ok(())
}

fn authorize_owner(request: &ResetIdentity, owner: &str) -> Result<(), PublishError> {
    if owner != request.actor_id {
        let result = authorize(&AuthorizationRequest {
            roles: request.roles.clone(),
            permission: Some("lab.admin".into()),
        })
        .map_err(|_| PublishError::Invalid)?;
        if result.allowed != Some(true) {
            return Err(PublishError::Forbidden);
        }
    }
    Ok(())
}

async fn lock_lab(
    tx: &Transaction<'_>,
    request: &ResetIdentity,
) -> Result<Option<(String, String, Option<String>)>, PublishError> {
    let row = tx
        .query_opt(
            "SELECT user_id::text, status, COALESCE(provider_ref, container_id) FROM lab_instances WHERE id = ($1::text)::uuid FOR UPDATE",
            &[&request.lab_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(row) = row else {
        return Ok(None);
    };
    let owner: String = row.get(0);
    authorize_owner(request, &owner)?;
    Ok(Some((owner, row.get(1), row.get(2))))
}

pub async fn begin(
    pool: &Pool,
    request: &ResetBeginRequest,
) -> Result<ResetResponse, PublishError> {
    validate_actor(&request.actor)?;
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let tx = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    let Some((_, state, reference)) = lock_lab(&tx, &request.actor).await? else {
        return Ok(ResetResponse {
            outcome: "not_found".into(),
        });
    };
    if reference != request.actor.expected_old_ref {
        return Ok(ResetResponse {
            outcome: "stale_provider".into(),
        });
    }
    if state == "running" && reference.is_none() {
        return Ok(ResetResponse {
            outcome: "provider_missing".into(),
        });
    }
    if !matches!(state.as_str(), "running" | "stopped" | "expired") {
        return Ok(ResetResponse {
            outcome: "unavailable".into(),
        });
    }
    tx.execute(
        "UPDATE lab_instances SET status = 'resetting', updated_at = now() WHERE id = ($1::text)::uuid",
        &[&request.actor.lab_id],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.execute(
        "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address) VALUES (gen_random_uuid(), 'lab.reset.begin', ($1::text)::uuid, $2, $3)",
        &[&request.actor.actor_id, &request.actor.lab_id, &request.actor.ip_address],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.commit().await.map_err(|_| PublishError::Database)?;
    Ok(ResetResponse {
        outcome: "claimed".into(),
    })
}

pub async fn complete(
    pool: &Pool,
    request: &ResetCompleteRequest,
) -> Result<ResetResponse, PublishError> {
    validate_complete(request)?;
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let tx = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    let Some((_, state, reference)) = lock_lab(&tx, &request.actor).await? else {
        return Ok(ResetResponse {
            outcome: "not_found".into(),
        });
    };
    if state == "running" && reference.as_deref() == Some(request.provider_ref.as_str()) {
        return Ok(ResetResponse {
            outcome: "already_completed".into(),
        });
    }
    if state != "resetting" || reference != request.actor.expected_old_ref {
        return Ok(ResetResponse {
            outcome: "unavailable".into(),
        });
    }
    tx.execute(
        "UPDATE lab_instances SET status = 'running', provider = $2, provider_ref = $3, container_id = $3, container_name = $4, flag_hash = $5, flag_path = $6, connection_hint = $7, expires_at = now() + ($8::int * interval '1 minute'), error_message = NULL, updated_at = now() WHERE id = ($1::text)::uuid",
        &[&request.actor.lab_id, &request.provider, &request.provider_ref, &request.container_name, &request.flag_hash, &request.flag_path, &request.connection_hint, &request.expiry_minutes],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.execute(
        "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address) VALUES (gen_random_uuid(), 'lab.reset', ($1::text)::uuid, $2, $3)",
        &[&request.actor.actor_id, &request.actor.lab_id, &request.actor.ip_address],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.commit().await.map_err(|_| PublishError::Database)?;
    Ok(ResetResponse {
        outcome: "completed".into(),
    })
}

pub async fn fail(pool: &Pool, request: &ResetFailRequest) -> Result<ResetResponse, PublishError> {
    validate_fail(request)?;
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let tx = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    let Some((_, state, reference)) = lock_lab(&tx, &request.actor).await? else {
        return Ok(ResetResponse {
            outcome: "not_found".into(),
        });
    };
    if state != "resetting" || reference != request.actor.expected_old_ref {
        return Ok(ResetResponse {
            outcome: "unavailable".into(),
        });
    }
    tx.execute(
        "UPDATE lab_instances SET status = 'failed', error_message = $2, provider_ref = $3, container_id = $3, updated_at = now() WHERE id = ($1::text)::uuid",
        &[&request.actor.lab_id, &request.error_message, &request.remaining_provider_ref],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.execute(
        "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address) VALUES (gen_random_uuid(), 'lab.reset.failure', ($1::text)::uuid, $2, $3)",
        &[&request.actor.actor_id, &request.actor.lab_id, &request.actor.ip_address],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.commit().await.map_err(|_| PublishError::Database)?;
    Ok(ResetResponse {
        outcome: "failed".into(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn identity() -> ResetIdentity {
        ResetIdentity {
            lab_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee".into(),
            actor_id: "bbbbbbbb-cccc-dddd-eeee-ffffffffffff".into(),
            roles: vec!["student".into()],
            ip_address: None,
            expected_old_ref: Some("old-guest".into()),
        }
    }

    #[test]
    fn rejects_bad_identity_new_resource_or_completion_fields() {
        assert!(validate_actor(&identity()).is_ok());
        let mut wrong = identity();
        wrong.expected_old_ref = Some("/unsafe".into());
        assert!(matches!(validate_actor(&wrong), Err(PublishError::Invalid)));
        let mut complete = ResetCompleteRequest {
            actor: identity(),
            provider: "docker".into(),
            provider_ref: "new-guest".into(),
            container_name: "guest-123".into(),
            flag_hash: "a".repeat(64),
            flag_path: "/flag.txt".into(),
            connection_hint: "ready".into(),
            expiry_minutes: 30,
        };
        assert!(validate_complete(&complete).is_ok());
        complete.provider = "unknown".into();
        assert!(matches!(
            validate_complete(&complete),
            Err(PublishError::Invalid)
        ));
        complete.provider = "docker".into();
        complete.flag_hash = "z".repeat(64);
        assert!(matches!(
            validate_complete(&complete),
            Err(PublishError::Invalid)
        ));
        let failure = ResetFailRequest {
            actor: identity(),
            error_message: "provider down".into(),
            remaining_provider_ref: Some("new-guest".into()),
        };
        assert!(validate_fail(&failure).is_ok());
    }
}
