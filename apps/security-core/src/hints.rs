//! Progressive hint unlocks with a durable, atomic audit trail.
use deadpool_postgres::Pool;
use serde::{Deserialize, Serialize};

use crate::publishing::{validate_permission, PublishError, PublishRequest};

#[derive(Debug, Deserialize)]
pub struct HintRevealRequest {
    pub challenge_id: String,
    pub actor_id: String,
    pub roles: Vec<String>,
    pub ip_address: Option<String>,
    pub hint_index: i32,
}

#[derive(Debug, Serialize)]
pub struct HintRevealResponse {
    pub outcome: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub revealed_count: Option<i32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub total_hints: Option<i32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub next_index: Option<i32>,
}

fn response(
    outcome: &str,
    revealed_count: Option<i32>,
    total_hints: Option<i32>,
    next_index: Option<i32>,
) -> HintRevealResponse {
    HintRevealResponse {
        outcome: outcome.into(),
        revealed_count,
        total_hints,
        next_index,
    }
}

pub fn validate(request: &HintRevealRequest) -> Result<(), PublishError> {
    validate_permission(
        &PublishRequest {
            challenge_id: request.challenge_id.clone(),
            actor_id: request.actor_id.clone(),
            roles: request.roles.clone(),
            ip_address: request.ip_address.clone(),
        },
        "challenge.attempt",
    )
}

pub async fn reveal(
    pool: &Pool,
    request: &HintRevealRequest,
) -> Result<HintRevealResponse, PublishError> {
    validate(request)?;
    if request.hint_index < 0 {
        return Ok(response("negative_index", None, None, None));
    }

    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let tx = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;

    // Serialize one user's reveals for this challenge across Rust and Python.
    // The advisory transaction lock needs no UPDATE grant on the users table.
    tx.query_one(
        "SELECT pg_advisory_xact_lock(hashtextextended( \
         (($1::text)::uuid)::text || ':' || (($2::text)::uuid)::text, 0))",
        &[&request.actor_id, &request.challenge_id],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    let user = tx
        .query_opt(
            "SELECT is_active FROM users WHERE id = ($1::text)::uuid",
            &[&request.actor_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(user) = user else {
        return Ok(response("not_found", None, None, None));
    };
    if !user.get::<_, bool>(0) {
        return Err(PublishError::Forbidden);
    }

    // Read the authoritative published status and number of available hints.
    // A concurrent challenge edit/publish cannot change this during the reveal.
    let challenge = tx
        .query_opt(
            "SELECT slug, status, CASE WHEN json_typeof(hints::json) = 'array' \
             THEN json_array_length(hints::json) ELSE 0 END AS total \
             FROM challenges WHERE id = ($1::text)::uuid FOR SHARE",
            &[&request.challenge_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(challenge) = challenge else {
        return Ok(response("not_found", None, None, None));
    };
    let status: String = challenge.get(1);
    if status != "published" {
        return Ok(response("not_found", None, None, None));
    }
    let total: i32 = challenge.get(2);
    if request.hint_index >= total {
        return Ok(response("invalid_index", None, Some(total), None));
    }

    let rows = tx
        .query(
            "SELECT hint_index FROM hint_reveals \
             WHERE user_id = ($1::text)::uuid AND challenge_id = ($2::text)::uuid",
            &[&request.actor_id, &request.challenge_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let count = i32::try_from(rows.len()).map_err(|_| PublishError::Database)?;
    if rows
        .iter()
        .any(|row| row.get::<_, i32>(0) == request.hint_index)
    {
        return Ok(response("already_revealed", Some(count), None, None));
    }
    if request.hint_index != count {
        return Ok(response("out_of_order", None, None, Some(count)));
    }

    tx.execute(
        "INSERT INTO hint_reveals (id, user_id, challenge_id, hint_index) \
         VALUES (gen_random_uuid(), ($1::text)::uuid, ($2::text)::uuid, $3)",
        &[
            &request.actor_id,
            &request.challenge_id,
            &request.hint_index,
        ],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    let slug: String = challenge.get(0);
    tx.execute(
        "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address, details) \
         VALUES (gen_random_uuid(), 'hint.reveal', ($1::text)::uuid, $2, $3, \
         json_build_object('hint_index', $4::integer))",
        &[
            &request.actor_id,
            &slug,
            &request.ip_address,
            &request.hint_index,
        ],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.commit().await.map_err(|_| PublishError::Database)?;
    Ok(response("revealed", Some(count + 1), None, None))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn requires_student_permission_and_valid_identity() {
        let mut request = HintRevealRequest {
            challenge_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee".into(),
            actor_id: "bbbbbbbb-cccc-dddd-eeee-ffffffffffff".into(),
            roles: vec!["student".into()],
            ip_address: None,
            hint_index: 0,
        };
        assert!(validate(&request).is_ok());
        request.roles = vec!["faculty".into()];
        assert!(matches!(validate(&request), Err(PublishError::Forbidden)));
        request.actor_id = "invalid".into();
        assert!(matches!(validate(&request), Err(PublishError::Invalid)));
    }
}
