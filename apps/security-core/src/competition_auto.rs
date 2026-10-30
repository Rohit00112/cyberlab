//! Database-owned automatic competition transitions. Concurrent sweep workers
//! skip rows held by another transaction, and changes and audits commit together.
use deadpool_postgres::Pool;
use serde::Serialize;

use crate::competition::{transition_competition, CompetitionTransitionRequest};
use crate::publishing::PublishError;

const PHASE_BATCH_LIMIT: i64 = 250;
const _: () = assert!(PHASE_BATCH_LIMIT > 0 && PHASE_BATCH_LIMIT <= 500);

#[derive(Debug, Serialize)]
pub struct AutoTransitionResponse {
    pub changed: usize,
}

pub async fn persist_due(pool: &Pool) -> Result<AutoTransitionResponse, PublishError> {
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let tx = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    let mut changed = 0;
    // Run the two phases in order. A scheduled event whose start *and* end
    // have passed may start and finish in the same sweep, as in the old API.
    for (current, next, query) in [
        (
            "scheduled",
            "live",
            "SELECT id::text, slug, status, \
             floor(extract(epoch FROM start_at) * 1000)::bigint, \
             floor(extract(epoch FROM end_at) * 1000)::bigint, \
             floor(extract(epoch FROM now()) * 1000)::bigint \
             FROM competitions WHERE status = 'scheduled' AND start_at <= now() \
             ORDER BY id LIMIT $1 FOR UPDATE SKIP LOCKED",
        ),
        (
            "live",
            "finished",
            "SELECT id::text, slug, status, \
             floor(extract(epoch FROM start_at) * 1000)::bigint, \
             floor(extract(epoch FROM end_at) * 1000)::bigint, \
             floor(extract(epoch FROM now()) * 1000)::bigint \
             FROM competitions WHERE status = 'live' AND end_at <= now() \
             ORDER BY id LIMIT $1 FOR UPDATE SKIP LOCKED",
        ),
    ] {
        let rows = tx
            .query(query, &[&PHASE_BATCH_LIMIT])
            .await
            .map_err(|_| PublishError::Database)?;
        for row in rows {
            let id: String = row.get(0);
            let slug: String = row.get(1);
            let status: String = row.get(2);
            if status != current {
                return Err(PublishError::Database);
            }
            let decision = transition_competition(&CompetitionTransitionRequest {
                current: status.clone(),
                action: "auto".into(),
                start_at: row.get(3),
                end_at: row.get(4),
                now: row.get(5),
            })
            .map_err(|_| PublishError::Database)?;
            if decision.error_code.is_some() || decision.next_status.as_deref() != Some(next) {
                return Err(PublishError::Database);
            }
            tx.execute(
                "UPDATE competitions SET status = $2, updated_at = now() \
                 WHERE id = ($1::text)::uuid",
                &[&id, &next],
            )
            .await
            .map_err(|_| PublishError::Database)?;
            let details = serde_json::json!({
                "competition_id": id,
                "action": "auto",
                "from": current,
                "to": next,
            })
            .to_string();
            tx.execute(
                "INSERT INTO audit_logs (id, event, target_id, details) \
                 VALUES (gen_random_uuid(), 'competition.auto_transition', \
                 $1, ($2::text)::jsonb)",
                &[&slug, &details],
            )
            .await
            .map_err(|_| PublishError::Database)?;
            changed += 1;
        }
    }
    tx.commit().await.map_err(|_| PublishError::Database)?;
    Ok(AutoTransitionResponse { changed })
}
