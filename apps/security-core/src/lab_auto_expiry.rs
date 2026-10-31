//! Finalize a provider-confirmed automatic lab expiry with an atomic audit.
//!
//! Only the internal maintenance caller can reach this route. The Rust writer
//! checks database time and the exact resource handle under a row lock so a
//! stale sweep cannot overwrite a renewed or reprovisioned environment.
use deadpool_postgres::Pool;
use serde::{Deserialize, Serialize};

use crate::publishing::{valid_uuid, PublishError};

#[derive(Debug, Deserialize)]
pub struct AutoLabExpiryRequest {
    pub lab_id: String,
    pub expected_provider_ref: String,
}

#[derive(Debug, Serialize)]
pub struct AutoLabExpiryResponse {
    pub outcome: String,
}

pub fn validate(request: &AutoLabExpiryRequest) -> Result<(), PublishError> {
    if !valid_uuid(&request.lab_id)
        || request.expected_provider_ref.is_empty()
        || request.expected_provider_ref.len() > 255
    {
        return Err(PublishError::Invalid);
    }
    Ok(())
}

pub async fn finalize(
    pool: &Pool,
    request: &AutoLabExpiryRequest,
) -> Result<AutoLabExpiryResponse, PublishError> {
    validate(request)?;
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let tx = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    let row = tx
        .query_opt(
            "SELECT user_id::text, status, COALESCE(provider_ref, container_id), COALESCE(expires_at < now(), false) FROM lab_instances WHERE id = ($1::text)::uuid FOR UPDATE",
            &[&request.lab_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(row) = row else {
        return Ok(AutoLabExpiryResponse {
            outcome: "not_found".into(),
        });
    };
    let owner: String = row.get(0);
    let state: String = row.get(1);
    let reference: Option<String> = row.get(2);
    let overdue: bool = row.get(3);
    if state != "running" {
        return Ok(AutoLabExpiryResponse {
            outcome: "not_running".into(),
        });
    }
    if reference.as_deref() != Some(request.expected_provider_ref.as_str()) {
        return Ok(AutoLabExpiryResponse {
            outcome: "stale_provider".into(),
        });
    }
    if !overdue {
        return Ok(AutoLabExpiryResponse {
            outcome: "not_due".into(),
        });
    }
    tx.execute(
        "UPDATE lab_instances SET status = 'expired', updated_at = now() WHERE id = ($1::text)::uuid",
        &[&request.lab_id],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.execute(
        "INSERT INTO audit_logs (id, event, user_id, target_id) VALUES (gen_random_uuid(), 'lab.expire_auto', ($1::text)::uuid, $2)",
        &[&owner, &request.lab_id],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.commit().await.map_err(|_| PublishError::Database)?;
    Ok(AutoLabExpiryResponse {
        outcome: "expired".into(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn validates_automatic_expiry_targets() {
        let mut request = AutoLabExpiryRequest {
            lab_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee".into(),
            expected_provider_ref: "guest-1".into(),
        };
        assert!(validate(&request).is_ok());
        request.expected_provider_ref = String::new();
        assert!(matches!(validate(&request), Err(PublishError::Invalid)));
        request.expected_provider_ref = "x".repeat(256);
        assert!(matches!(validate(&request), Err(PublishError::Invalid)));
        request.expected_provider_ref = "guest-1".into();
        request.lab_id = "../wrong".into();
        assert!(matches!(validate(&request), Err(PublishError::Invalid)));
    }
}
