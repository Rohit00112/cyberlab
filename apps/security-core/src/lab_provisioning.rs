//! Atomic claim of an asynchronous lab job before Python performs provider I/O.
//! Provider calls cannot share this PostgreSQL transaction; only the durable
//! queued -> provisioning transition and required audit belong to Rust here.
use deadpool_postgres::Pool;
use serde::{Deserialize, Serialize};

use crate::publishing::{valid_uuid, PublishError};

#[derive(Debug, Deserialize)]
pub struct ProvisioningClaimRequest {
    pub job_id: String,
}

#[derive(Debug, Serialize)]
pub struct ProvisioningClaimResponse {
    pub outcome: String,
}

#[derive(Debug, Deserialize)]
pub struct ProvisioningCompleteRequest {
    pub job_id: String,
    pub provider_ref: String,
    pub container_name: String,
    pub flag_hash: String,
    pub flag_path: String,
    pub connection_hint: String,
    pub expiry_minutes: i32,
}

#[derive(Debug, Deserialize)]
pub struct ProvisioningFailRequest {
    pub job_id: String,
    pub error_message: String,
    pub cleanup_failed: bool,
    pub provider_ref: Option<String>,
}

fn valid_ref(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
}

pub fn validate_complete(request: &ProvisioningCompleteRequest) -> Result<(), PublishError> {
    if !valid_uuid(&request.job_id)
        || !valid_ref(&request.provider_ref)
        || !valid_ref(&request.container_name)
        || request.flag_hash.len() != 64
        || !request
            .flag_hash
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
        || !request.flag_path.starts_with('/')
        || request.flag_path.len() > 255
        || request.flag_path.contains('\0')
        || request.connection_hint.len() > 2048
        || !(1..=240).contains(&request.expiry_minutes)
    {
        return Err(PublishError::Invalid);
    }
    Ok(())
}

pub fn validate_failure(request: &ProvisioningFailRequest) -> Result<(), PublishError> {
    if !valid_uuid(&request.job_id)
        || request.error_message.is_empty()
        || request.error_message.len() > 4096
        || request.cleanup_failed && !request.provider_ref.as_deref().is_some_and(valid_ref)
        || request
            .provider_ref
            .as_deref()
            .is_some_and(|value| !valid_ref(value))
    {
        return Err(PublishError::Invalid);
    }
    Ok(())
}

pub fn validate(request: &ProvisioningClaimRequest) -> Result<(), PublishError> {
    if !valid_uuid(&request.job_id) {
        return Err(PublishError::Invalid);
    }
    Ok(())
}

pub async fn claim(
    pool: &Pool,
    request: &ProvisioningClaimRequest,
) -> Result<ProvisioningClaimResponse, PublishError> {
    validate(request)?;
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let tx = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    // Two different brokers may deliver the same job. SKIP LOCKED makes a
    // competing worker decline it without waiting for the first transaction.
    let row = tx
        .query_opt(
            "SELECT lab_instance_id::text, user_id::text, challenge_id::text \
             FROM provisioning_jobs WHERE id = ($1::text)::uuid \
             AND status = 'pending' FOR UPDATE SKIP LOCKED",
            &[&request.job_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(row) = row else {
        return Ok(ProvisioningClaimResponse {
            outcome: "unavailable".into(),
        });
    };
    let lab_id: String = row.get(0);
    let owner_id: String = row.get(1);
    let challenge_id: String = row.get(2);
    let lab_row = tx
        .query_opt(
            "SELECT user_id::text, challenge_id::text, status \
             FROM lab_instances WHERE id = ($1::text)::uuid FOR UPDATE SKIP LOCKED",
            &[&lab_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(lab_row) = lab_row else {
        // An in-flight lab update should not be overwritten by the worker.
        // The pending job can be redispatched once its lock is released.
        return Ok(ProvisioningClaimResponse {
            outcome: "unavailable".into(),
        });
    };
    let lab_owner: String = lab_row.get(0);
    let lab_challenge: String = lab_row.get(1);
    let lab_status: String = lab_row.get(2);
    if lab_status != "queued" || lab_owner != owner_id || lab_challenge != challenge_id {
        // A permanently invalid pending job must not be redispatched forever.
        // Record the rejection (including its audit) without touching the lab.
        let reason = if lab_status != "queued" {
            "Lab is no longer queued for provisioning"
        } else {
            "Provisioning job owner or challenge does not match its lab"
        };
        tx.execute(
            "UPDATE provisioning_jobs SET status = 'failed', completed_at = now(), \
             error_message = $2, updated_at = now() WHERE id = ($1::text)::uuid",
            &[&request.job_id, &reason],
        )
        .await
        .map_err(|_| PublishError::Database)?;
        tx.execute(
            "INSERT INTO audit_logs (id, event, user_id, target_id) \
             VALUES (gen_random_uuid(), 'lab.provisioning.reject', ($1::text)::uuid, $2)",
            &[&owner_id, &lab_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
        tx.commit().await.map_err(|_| PublishError::Database)?;
        return Ok(ProvisioningClaimResponse {
            outcome: "unavailable".into(),
        });
    }
    tx.execute(
        "UPDATE provisioning_jobs SET status = 'running', started_at = now(), \
         updated_at = now() WHERE id = ($1::text)::uuid",
        &[&request.job_id],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.execute(
        "UPDATE lab_instances SET status = 'provisioning', updated_at = now() \
         WHERE id = ($1::text)::uuid",
        &[&lab_id],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.execute(
        "INSERT INTO audit_logs (id, event, user_id, target_id) \
         VALUES (gen_random_uuid(), 'lab.provisioning.claim', ($1::text)::uuid, $2)",
        &[&owner_id, &lab_id],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.commit().await.map_err(|_| PublishError::Database)?;
    Ok(ProvisioningClaimResponse {
        outcome: "claimed".into(),
    })
}

/// Advance an already-claimed lab immediately before creating its provider.
pub async fn start(
    pool: &Pool,
    request: &ProvisioningClaimRequest,
) -> Result<ProvisioningClaimResponse, PublishError> {
    validate(request)?;
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let tx = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    let row = tx
        .query_opt(
            "SELECT lab_instance_id::text, user_id::text, challenge_id::text \
             FROM provisioning_jobs WHERE id = ($1::text)::uuid \
             AND status = 'running' FOR UPDATE SKIP LOCKED",
            &[&request.job_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(row) = row else {
        return Ok(ProvisioningClaimResponse {
            outcome: "unavailable".into(),
        });
    };
    let lab_id: String = row.get(0);
    let owner: String = row.get(1);
    let challenge: String = row.get(2);
    let lab = tx
        .query_opt(
            "SELECT user_id::text, challenge_id::text, status \
             FROM lab_instances WHERE id = ($1::text)::uuid FOR UPDATE SKIP LOCKED",
            &[&lab_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(lab) = lab else {
        return Ok(ProvisioningClaimResponse {
            outcome: "unavailable".into(),
        });
    };
    let lab_owner: String = lab.get(0);
    let lab_challenge: String = lab.get(1);
    let status: String = lab.get(2);
    if status != "provisioning" || owner != lab_owner || challenge != lab_challenge {
        return Ok(ProvisioningClaimResponse {
            outcome: "unavailable".into(),
        });
    }
    tx.execute(
        "UPDATE lab_instances SET status = 'starting', updated_at = now() \
         WHERE id = ($1::text)::uuid",
        &[&lab_id],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.execute(
        "INSERT INTO audit_logs (id, event, user_id, target_id) \
         VALUES (gen_random_uuid(), 'lab.provisioning.start', ($1::text)::uuid, $2)",
        &[&owner, &lab_id],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.commit().await.map_err(|_| PublishError::Database)?;
    Ok(ProvisioningClaimResponse {
        outcome: "started".into(),
    })
}

/// Finalize a provider that actually returned a resource handle. No external
/// provider I/O occurs inside this transaction.
pub async fn complete(
    pool: &Pool,
    request: &ProvisioningCompleteRequest,
) -> Result<ProvisioningClaimResponse, PublishError> {
    validate_complete(request)?;
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let tx = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    let job = tx
        .query_opt(
            "SELECT lab_instance_id::text, user_id::text, challenge_id::text \
             FROM provisioning_jobs WHERE id = ($1::text)::uuid \
             AND status = 'running' FOR UPDATE SKIP LOCKED",
            &[&request.job_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(job) = job else {
        return Ok(ProvisioningClaimResponse {
            outcome: "unavailable".into(),
        });
    };
    let lab_id: String = job.get(0);
    let owner: String = job.get(1);
    let challenge: String = job.get(2);
    let lab = tx
        .query_opt(
            "SELECT user_id::text, challenge_id::text, status \
             FROM lab_instances WHERE id = ($1::text)::uuid FOR UPDATE SKIP LOCKED",
            &[&lab_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(lab) = lab else {
        return Ok(ProvisioningClaimResponse {
            outcome: "unavailable".into(),
        });
    };
    let lab_owner: String = lab.get(0);
    let lab_challenge: String = lab.get(1);
    let lab_state: String = lab.get(2);
    if owner != lab_owner || challenge != lab_challenge || lab_state != "starting" {
        return Ok(ProvisioningClaimResponse {
            outcome: "unavailable".into(),
        });
    }
    tx.execute(
        "UPDATE lab_instances SET provider_ref = $2, container_id = $2, \
         container_name = $3, flag_hash = $4, flag_path = $5, \
         connection_hint = $6, status = 'running', \
         expires_at = now() + ($7::int * interval '1 minute'), \
         updated_at = now() WHERE id = ($1::text)::uuid",
        &[
            &lab_id,
            &request.provider_ref,
            &request.container_name,
            &request.flag_hash,
            &request.flag_path,
            &request.connection_hint,
            &request.expiry_minutes,
        ],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.execute(
        "UPDATE provisioning_jobs SET status = 'completed', completed_at = now(), \
         updated_at = now() WHERE id = ($1::text)::uuid",
        &[&request.job_id],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.execute(
        "INSERT INTO audit_logs (id, event, user_id, target_id) \
         VALUES (gen_random_uuid(), 'lab.provisioning.complete', ($1::text)::uuid, $2)",
        &[&owner, &lab_id],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.commit().await.map_err(|_| PublishError::Database)?;
    Ok(ProvisioningClaimResponse {
        outcome: "completed".into(),
    })
}

/// Record a failed job and its required audit atomically after the Python
/// worker has attempted provider cleanup. The handle is retained only when
/// cleanup failed, so an administrator can reconcile an orphaned resource.
pub async fn fail(
    pool: &Pool,
    request: &ProvisioningFailRequest,
) -> Result<ProvisioningClaimResponse, PublishError> {
    validate_failure(request)?;
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let tx = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    let job = tx
        .query_opt(
            "SELECT lab_instance_id::text, user_id::text, challenge_id::text \
             FROM provisioning_jobs WHERE id = ($1::text)::uuid \
             AND status = 'running' FOR UPDATE SKIP LOCKED",
            &[&request.job_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(job) = job else {
        return Ok(ProvisioningClaimResponse {
            outcome: "unavailable".into(),
        });
    };
    let lab_id: String = job.get(0);
    let owner: String = job.get(1);
    let challenge: String = job.get(2);
    let lab = tx
        .query_opt(
            "SELECT user_id::text, challenge_id::text, status \
             FROM lab_instances WHERE id = ($1::text)::uuid FOR UPDATE SKIP LOCKED",
            &[&lab_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(lab) = lab else {
        return Ok(ProvisioningClaimResponse {
            outcome: "unavailable".into(),
        });
    };
    let lab_owner: String = lab.get(0);
    let lab_challenge: String = lab.get(1);
    let lab_state: String = lab.get(2);
    if owner != lab_owner
        || challenge != lab_challenge
        || !matches!(lab_state.as_str(), "provisioning" | "starting")
    {
        return Ok(ProvisioningClaimResponse {
            outcome: "unavailable".into(),
        });
    }
    let preserved_ref = if request.cleanup_failed {
        request.provider_ref.as_deref()
    } else {
        None
    };
    tx.execute(
        "UPDATE lab_instances SET status = 'failed', error_message = $2, \
         provider_ref = $3, container_id = $3, updated_at = now() \
         WHERE id = ($1::text)::uuid",
        &[&lab_id, &request.error_message, &preserved_ref],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.execute(
        "UPDATE provisioning_jobs SET status = 'failed', error_message = $2, \
         completed_at = now(), updated_at = now() WHERE id = ($1::text)::uuid",
        &[&request.job_id, &request.error_message],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    let details = serde_json::json!({"cleanup_failed": request.cleanup_failed}).to_string();
    tx.execute(
        "INSERT INTO audit_logs (id, event, user_id, target_id, details) \
         VALUES (gen_random_uuid(), 'lab.provisioning.failure', ($1::text)::uuid, $2, ($3::text)::jsonb)",
        &[&owner, &lab_id, &details],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.commit().await.map_err(|_| PublishError::Database)?;
    Ok(ProvisioningClaimResponse {
        outcome: "failed".into(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn claim_rejects_malformed_job_ids() {
        let mut request = ProvisioningClaimRequest {
            job_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee".into(),
        };
        assert!(validate(&request).is_ok());
        request.job_id = "not-a-uuid".into();
        assert!(matches!(validate(&request), Err(PublishError::Invalid)));
    }

    #[test]
    fn terminal_requests_reject_untrusted_fields() {
        let mut request = ProvisioningCompleteRequest {
            job_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee".into(),
            provider_ref: "a".repeat(64),
            container_name: "lab-abcd1234-efab5678".into(),
            flag_hash: "b".repeat(64),
            flag_path: "/flag.txt".into(),
            connection_hint: "isolated lab".into(),
            expiry_minutes: 60,
        };
        assert!(validate_complete(&request).is_ok());
        request.provider_ref = "../other".into();
        assert!(validate_complete(&request).is_err());
        request.provider_ref = "a".repeat(64);
        request.flag_hash = "not-a-hash".into();
        assert!(validate_complete(&request).is_err());

        let mut failure = ProvisioningFailRequest {
            job_id: request.job_id,
            error_message: "provider failed".into(),
            cleanup_failed: true,
            provider_ref: None,
        };
        assert!(validate_failure(&failure).is_err());
        failure.provider_ref = Some("a".repeat(64));
        assert!(validate_failure(&failure).is_ok());
    }
}
