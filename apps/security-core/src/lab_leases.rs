//! Atomic per-user lab lease extension with independent authorization and audit.
use deadpool_postgres::Pool;
use serde::{Deserialize, Serialize};

use crate::authorization::{authorize, AuthorizationRequest};
use crate::publishing::{validate_permission, PublishError, PublishRequest};

#[derive(Debug, Deserialize)]
pub struct LabExtendRequest {
    pub lab_id: String,
    pub actor_id: String,
    pub roles: Vec<String>,
    pub ip_address: Option<String>,
    pub additional_minutes: i64,
    pub max_expiry_minutes: i64,
}

#[derive(Debug, Serialize)]
pub struct LabExtendResponse {
    pub outcome: String,
    pub current_status: Option<String>,
}

pub fn validate(request: &LabExtendRequest) -> Result<(), PublishError> {
    validate_permission(
        &PublishRequest {
            challenge_id: request.lab_id.clone(),
            actor_id: request.actor_id.clone(),
            roles: request.roles.clone(),
            ip_address: request.ip_address.clone(),
        },
        "lab.launch",
    )?;
    if !(5..=120).contains(&request.additional_minutes)
        || !(1..=525_600).contains(&request.max_expiry_minutes)
    {
        return Err(PublishError::Invalid);
    }
    Ok(())
}

pub async fn extend(
    pool: &Pool,
    request: &LabExtendRequest,
) -> Result<LabExtendResponse, PublishError> {
    validate(request)?;
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let tx = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    let row = tx
        .query_opt(
            "SELECT user_id::text, status, \
             COALESCE(expires_at < now(), false) \
             FROM lab_instances WHERE id = ($1::text)::uuid FOR UPDATE",
            &[&request.lab_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(row) = row else {
        return Ok(LabExtendResponse {
            outcome: "not_found".into(),
            current_status: None,
        });
    };
    let owner: String = row.get(0);
    let state: String = row.get(1);
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
    if state != "running" {
        return Ok(LabExtendResponse {
            outcome: "not_running".into(),
            current_status: Some(state),
        });
    }
    let expired: bool = row.get(2);
    if expired {
        return Ok(LabExtendResponse {
            outcome: "expired".into(),
            current_status: None,
        });
    }
    tx.execute(
        "UPDATE lab_instances SET \
         expires_at = LEAST( \
           COALESCE(expires_at, now()) + $2::bigint * interval '1 minute', \
           COALESCE(created_at, now()) + $3::bigint * interval '1 minute' \
         ), updated_at = now() WHERE id = ($1::text)::uuid",
        &[
            &request.lab_id,
            &request.additional_minutes,
            &request.max_expiry_minutes,
        ],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.execute(
        "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address) \
         VALUES (gen_random_uuid(), 'lab.extend', ($1::text)::uuid, $2, $3)",
        &[&request.actor_id, &request.lab_id, &request.ip_address],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.commit().await.map_err(|_| PublishError::Database)?;
    Ok(LabExtendResponse {
        outcome: "extended".into(),
        current_status: None,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_bad_identity_roles_and_lease_bounds() {
        let mut request = LabExtendRequest {
            lab_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee".into(),
            actor_id: "bbbbbbbb-cccc-dddd-eeee-ffffffffffff".into(),
            roles: vec!["student".into()],
            ip_address: None,
            additional_minutes: 30,
            max_expiry_minutes: 240,
        };
        assert!(validate(&request).is_ok());
        request.additional_minutes = 121;
        assert!(matches!(validate(&request), Err(PublishError::Invalid)));
        request.additional_minutes = 30;
        request.roles = vec!["guest".into()];
        assert!(matches!(validate(&request), Err(PublishError::Forbidden)));
        request.roles = vec!["student".into()];
        request.lab_id = "invalid".into();
        assert!(matches!(validate(&request), Err(PublishError::Invalid)));
    }
}
