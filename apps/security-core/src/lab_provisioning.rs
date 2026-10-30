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
}
