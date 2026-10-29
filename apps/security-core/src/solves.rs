//! Atomic correct-solve ledger: submission, score event, skills and audit.
//! The FastAPI gateway still owns external OIDC authentication and badge
//! evaluation. This handler verifies the flag again against locked DB state.
use deadpool_postgres::Pool;
use serde::{Deserialize, Serialize};

use crate::{
    publishing::{validate_permission, PublishError, PublishRequest},
    score, verify_flag, ScoreRequest, VerifyFlagRequest,
};

#[derive(Debug, Deserialize)]
pub struct CorrectSolveRequest {
    pub challenge_id: String,
    pub user_id: String,
    pub roles: Vec<String>,
    pub ip_address: Option<String>,
    pub candidate: String,
    pub lab_id: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct CorrectSolveResponse {
    pub outcome: String,
    pub points: i32,
}

pub async fn record(
    pool: &Pool,
    request: &CorrectSolveRequest,
) -> Result<CorrectSolveResponse, PublishError> {
    validate_permission(
        &PublishRequest {
            challenge_id: request.challenge_id.clone(),
            actor_id: request.user_id.clone(),
            roles: request.roles.clone(),
            ip_address: request.ip_address.clone(),
        },
        "submission.create",
    )?;
    if request.candidate.is_empty()
        || request.candidate.len() > 2048
        || request
            .lab_id
            .as_ref()
            .is_some_and(|id| !crate::publishing::valid_uuid(id))
    {
        return Err(PublishError::Invalid);
    }
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let transaction = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;

    // Lock user before challenge for a consistent order across concurrent
    // solves: per-user cumulative score ledger and per-challenge first blood
    // rank remain deterministic without duplicate correct submissions.
    let user = transaction
        .query_opt(
            "SELECT id FROM users WHERE id = ($1::text)::uuid AND is_active = true FOR UPDATE",
            &[&request.user_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    if user.is_none() {
        return Ok(CorrectSolveResponse {
            outcome: "not_found".into(),
            points: 0,
        });
    }
    let challenge = transaction
        .query_opt(
            "SELECT slug, points, hint_penalty, difficulty_score, flag_hash
         FROM challenges WHERE id = ($1::text)::uuid AND status = 'published' FOR UPDATE",
            &[&request.challenge_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(challenge) = challenge else {
        return Ok(CorrectSolveResponse {
            outcome: "not_found".into(),
            points: 0,
        });
    };
    let slug: String = challenge.get(0);
    let base_points: i32 = challenge.get(1);
    let hint_penalty: i32 = challenge.get(2);
    let difficulty: f64 = challenge.get(3);
    let static_hash: Option<String> = challenge.get(4);

    let expected_hash = if let Some(lab_id) = &request.lab_id {
        let lab = transaction
            .query_opt(
                "SELECT flag_hash FROM lab_instances
             WHERE id = ($1::text)::uuid AND user_id = ($2::text)::uuid
               AND challenge_id = ($3::text)::uuid AND status = 'running'
               AND flag_hash IS NOT NULL
               AND (expires_at IS NULL OR expires_at > now())
             FOR SHARE",
                &[lab_id, &request.user_id, &request.challenge_id],
            )
            .await
            .map_err(|_| PublishError::Database)?;
        let Some(lab) = lab else {
            return Ok(CorrectSolveResponse {
                outcome: "lab_unavailable".into(),
                points: 0,
            });
        };
        lab.get::<_, String>(0)
    } else {
        let Some(hash) = static_hash else {
            return Ok(CorrectSolveResponse {
                outcome: "not_found".into(),
                points: 0,
            });
        };
        hash
    };
    let verified = verify_flag(&VerifyFlagRequest {
        candidate: request.candidate.clone(),
        expected_sha256: expected_hash,
    })
    .map_err(|_| PublishError::Invalid)?;
    if !verified.correct {
        // Python's earlier verification may have raced with a flag rotation.
        // Never award points based on an untrusted 'correct' boolean.
        return Ok(CorrectSolveResponse {
            outcome: "stale_flag".into(),
            points: 0,
        });
    }
    let prior = transaction
        .query_opt(
            "SELECT id FROM submissions WHERE challenge_id = ($1::text)::uuid
         AND user_id = ($2::text)::uuid AND is_correct = true",
            &[&request.challenge_id, &request.user_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    if prior.is_some() {
        transaction
            .execute(
                "INSERT INTO audit_logs(id, event, user_id, target_id, ip_address, details)
             VALUES (gen_random_uuid(), 'submission.attempt', ($1::text)::uuid, $2, $3,
                     '{\"correct\":true,\"already_solved\":true}'::json)",
                &[&request.user_id, &slug, &request.ip_address],
            )
            .await
            .map_err(|_| PublishError::Database)?;
        transaction
            .commit()
            .await
            .map_err(|_| PublishError::Database)?;
        return Ok(CorrectSolveResponse {
            outcome: "already_solved".into(),
            points: 0,
        });
    }
    let revealed: i64 = transaction
        .query_one(
            "SELECT count(*) FROM hint_reveals WHERE user_id = ($1::text)::uuid
         AND challenge_id = ($2::text)::uuid",
            &[&request.user_id, &request.challenge_id],
        )
        .await
        .map_err(|_| PublishError::Database)?
        .get(0);
    transaction
        .execute(
            "INSERT INTO submissions (id, challenge_id, user_id, is_correct, earned_points)
         VALUES (gen_random_uuid(), ($1::text)::uuid, ($2::text)::uuid, true, 0)",
            &[&request.challenge_id, &request.user_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let rank: i64 = transaction.query_one(
        "SELECT count(*) FROM submissions WHERE challenge_id = ($1::text)::uuid AND is_correct = true",
        &[&request.challenge_id],
    ).await.map_err(|_| PublishError::Database)?.get(0);
    let penalty = i64::from(hint_penalty)
        .checked_mul(revealed)
        .ok_or(PublishError::Invalid)?;
    let computed = score(&ScoreRequest {
        base_points: i64::from(base_points),
        solve_rank: u64::try_from(rank).map_err(|_| PublishError::Database)?,
        mode: "standard".into(),
        penalty,
        min_points: 100,
        decay_scale: 15,
    })
    .map_err(|_| PublishError::Invalid)?;
    let points = i32::try_from(computed.points).map_err(|_| PublishError::Invalid)?;
    transaction
        .execute(
            "UPDATE submissions SET earned_points = $3 WHERE challenge_id = ($1::text)::uuid
         AND user_id = ($2::text)::uuid AND is_correct = true",
            &[&request.challenge_id, &request.user_id, &points],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let prev_total: i64 = transaction
        .query_one(
            "SELECT COALESCE(sum(points),0)::bigint FROM score_events
         WHERE user_id = ($1::text)::uuid AND competition_id IS NULL",
            &[&request.user_id],
        )
        .await
        .map_err(|_| PublishError::Database)?
        .get(0);
    let new_total = prev_total
        .checked_add(i64::from(points))
        .ok_or(PublishError::Database)?;
    let current_total = i32::try_from(new_total).map_err(|_| PublishError::Database)?;
    transaction.execute(
        "INSERT INTO score_events
         (id,user_id,challenge_id,event_type,points,current_total,is_first_blood,is_frozen)
         VALUES (gen_random_uuid(), ($1::text)::uuid, ($2::text)::uuid, 'solve', $3, $4, $5, false)",
        &[&request.user_id, &request.challenge_id, &points, &current_total, &(rank == 1)],
    ).await.map_err(|_| PublishError::Database)?;

    let competency_gain = difficulty.max(0.5) * 10.0;
    transaction.execute(
        "INSERT INTO user_skill_profiles (id,user_id,skill_id,competency_level)
         SELECT gen_random_uuid(), ($1::text)::uuid, skill_id, $2
         FROM challenge_skills WHERE challenge_id = ($3::text)::uuid
         ON CONFLICT (user_id,skill_id) DO UPDATE SET
           competency_level = LEAST(100.0, user_skill_profiles.competency_level + EXCLUDED.competency_level),
           last_updated = now()",
        &[&request.user_id, &competency_gain, &request.challenge_id],
    ).await.map_err(|_| PublishError::Database)?;
    transaction
        .execute(
            "INSERT INTO audit_logs (id,event,user_id,target_id,ip_address,details)
         VALUES (gen_random_uuid(),'submission.solve',($1::text)::uuid,$2,$3,
                 json_build_object('correct',true,'points',$4::integer))",
            &[&request.user_id, &slug, &request.ip_address, &points],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    transaction
        .commit()
        .await
        .map_err(|_| PublishError::Database)?;
    Ok(CorrectSolveResponse {
        outcome: "solved".into(),
        points,
    })
}
