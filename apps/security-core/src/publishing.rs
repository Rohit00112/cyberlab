//! A single transactional challenge-publishing operation.
//! The public Keycloak-protected API remains in FastAPI during migration.
use deadpool_postgres::Pool;
use serde::{Deserialize, Serialize};

use crate::authorization::{authorize, AuthorizationRequest};

#[derive(Debug, Deserialize)]
pub struct PublishRequest {
    pub challenge_id: String,
    pub actor_id: String,
    pub roles: Vec<String>,
    pub ip_address: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct PublishResponse {
    pub outcome: String,
    pub version: Option<i32>,
}

#[derive(Debug)]
pub enum PublishError {
    Invalid,
    Forbidden,
    Database,
}

pub(crate) fn valid_uuid(value: &str) -> bool {
    value.len() == 36
        && value.bytes().enumerate().all(|(index, byte)| {
            if matches!(index, 8 | 13 | 18 | 23) {
                byte == b'-'
            } else {
                byte.is_ascii_hexdigit()
            }
        })
}

pub fn validate(request: &PublishRequest) -> Result<(), PublishError> {
    validate_permission(request, "challenge.publish")
}

pub(crate) fn validate_permission(
    request: &PublishRequest,
    permission: &str,
) -> Result<(), PublishError> {
    if !valid_uuid(&request.challenge_id)
        || !valid_uuid(&request.actor_id)
        || request
            .ip_address
            .as_ref()
            .is_some_and(|ip| ip.len() > 45 || ip.contains(['\r', '\n']))
    {
        return Err(PublishError::Invalid);
    }
    let auth = authorize(&AuthorizationRequest {
        roles: request.roles.clone(),
        permission: Some(permission.into()),
    })
    .map_err(|_| PublishError::Invalid)?;
    if auth.allowed != Some(true) {
        return Err(PublishError::Forbidden);
    }
    Ok(())
}

pub async fn delete(
    pool: &Pool,
    request: &PublishRequest,
) -> Result<PublishResponse, PublishError> {
    validate_permission(request, "challenge.edit")?;
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let transaction = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    let row = transaction
        .query_opt(
            "SELECT slug FROM challenges WHERE id = ($1::text)::uuid FOR UPDATE",
            &[&request.challenge_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(row) = row else {
        return Ok(PublishResponse {
            outcome: "not_found".into(),
            version: None,
        });
    };
    let slug: String = row.get(0);
    transaction
        .execute(
            "DELETE FROM challenges WHERE id = ($1::text)::uuid",
            &[&request.challenge_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    transaction
        .execute(
            "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address)
             VALUES (gen_random_uuid(), 'challenge.delete', ($1::text)::uuid, $2, $3)",
            &[&request.actor_id, &slug, &request.ip_address],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    transaction
        .commit()
        .await
        .map_err(|_| PublishError::Database)?;
    Ok(PublishResponse {
        outcome: "deleted".into(),
        version: None,
    })
}

pub async fn publish(
    pool: &Pool,
    request: &PublishRequest,
) -> Result<PublishResponse, PublishError> {
    validate(request)?;
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let transaction = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    let row = transaction
        .query_opt(
            "SELECT slug, flag_hash IS NOT NULL FROM challenges
             WHERE id = ($1::text)::uuid FOR UPDATE",
            &[&request.challenge_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(row) = row else {
        return Ok(PublishResponse {
            outcome: "not_found".into(),
            version: None,
        });
    };
    let slug: String = row.get(0);
    let has_flag: bool = row.get(1);
    if !has_flag {
        return Ok(PublishResponse {
            outcome: "missing_flag".into(),
            version: None,
        });
    }
    let row = transaction
        .query_one(
            "UPDATE challenges
             SET status = 'published', version = version + 1, updated_at = now()
             WHERE id = ($1::text)::uuid RETURNING version",
            &[&request.challenge_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let version: i32 = row.get(0);
    // Failure to insert the audit row aborts publication as well.
    // PostgreSQL 16 supplies gen_random_uuid() for this UUID primary key.
    transaction
        .execute(
            "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address)
             VALUES (gen_random_uuid(), 'challenge.publish', ($1::text)::uuid, $2, $3)",
            &[&request.actor_id, &slug, &request.ip_address],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    transaction
        .commit()
        .await
        .map_err(|_| PublishError::Database)?;
    Ok(PublishResponse {
        outcome: "published".into(),
        version: Some(version),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request(roles: Vec<String>) -> PublishRequest {
        PublishRequest {
            challenge_id: "11111111-2222-3333-4444-555555555555".into(),
            actor_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee".into(),
            roles,
            ip_address: Some("127.0.0.1".into()),
        }
    }

    #[test]
    fn rejects_student_and_malformed_ids() {
        assert!(matches!(
            validate(&request(vec!["student".into()])),
            Err(PublishError::Forbidden)
        ));
        let mut bad = request(vec!["faculty".into()]);
        bad.challenge_id = "not-a-uuid".into();
        assert!(matches!(validate(&bad), Err(PublishError::Invalid)));
        assert!(validate(&request(vec!["faculty".into()])).is_ok());
        assert!(validate_permission(&request(vec!["faculty".into()]), "challenge.edit").is_ok());
        assert!(matches!(
            validate_permission(&request(vec!["student".into()]), "challenge.edit"),
            Err(PublishError::Forbidden)
        ));
    }
}
