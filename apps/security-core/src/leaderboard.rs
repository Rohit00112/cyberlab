//! PostgreSQL-backed global CTF leaderboard, matching FastAPI's public schema.
use deadpool_postgres::Pool;
use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize)]
pub struct LeaderboardQuery {
    pub limit: i64,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct LeaderboardRow {
    pub rank: i64,
    pub user_id: String,
    pub display_name: Option<String>,
    pub points: i64,
    pub solved_count: i64,
}

#[derive(Debug)]
pub enum LeaderboardError {
    Invalid,
    Database,
}

pub async fn global_leaderboard(
    pool: &Pool,
    request: &LeaderboardQuery,
) -> Result<Vec<LeaderboardRow>, LeaderboardError> {
    if !(1..=200).contains(&request.limit) {
        return Err(LeaderboardError::Invalid);
    }
    let client = pool.get().await.map_err(|_| LeaderboardError::Database)?;
    // A single prepared statement returns a consistent snapshot, without
    // granting the client control of table names, conditions or SQL text.
    let rows = client
        .query(
            "SELECT u.id::text, u.display_name,
                    COALESCE(SUM(s.earned_points), 0)::bigint AS points,
                    COUNT(*)::bigint AS solved_count
             FROM users u
             JOIN submissions s ON s.user_id = u.id
             WHERE s.is_correct = true
             GROUP BY u.id, u.display_name
             ORDER BY points DESC, MIN(s.created_at) ASC, u.id ASC
             LIMIT $1",
            &[&request.limit],
        )
        .await
        .map_err(|_| LeaderboardError::Database)?;
    Ok(rows
        .into_iter()
        .enumerate()
        .map(|(i, row)| LeaderboardRow {
            rank: (i as i64) + 1,
            user_id: row.get(0),
            display_name: row.get(1),
            points: row.get(2),
            solved_count: row.get(3),
        })
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn leaderboard_row_has_existing_api_shape() {
        let row = LeaderboardRow {
            rank: 1,
            user_id: "11111111-1111-1111-1111-111111111111".into(),
            display_name: Some("Student".into()),
            points: 250,
            solved_count: 2,
        };
        let value = serde_json::to_value(&row).unwrap();
        assert_eq!(value.as_object().unwrap().len(), 5);
        assert_eq!(value["points"], 250);
        assert_eq!(value["rank"], 1);
    }
}
