//! Atomic competition team creation and joining, with audit on the same commit.
use deadpool_postgres::Pool;
use serde::{Deserialize, Serialize};

use crate::publishing::{valid_uuid, validate_permission, PublishError, PublishRequest};

#[derive(Debug, Deserialize)]
pub struct TeamRequest {
    pub competition_id: String,
    pub actor_id: String,
    pub roles: Vec<String>,
    pub ip_address: Option<String>,
    pub name: Option<String>,
    pub team_id: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct TeamResponse {
    pub outcome: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub current_status: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub max_team_size: Option<i32>,
}

fn response(outcome: &str) -> TeamResponse {
    TeamResponse {
        outcome: outcome.into(),
        current_status: None,
        max_team_size: None,
    }
}

pub fn validate(request: &TeamRequest) -> Result<(), PublishError> {
    validate_permission(
        &PublishRequest {
            challenge_id: request.competition_id.clone(),
            actor_id: request.actor_id.clone(),
            roles: request.roles.clone(),
            ip_address: request.ip_address.clone(),
        },
        "challenge.attempt",
    )?;
    if request.team_id.as_ref().is_some_and(|id| !valid_uuid(id))
        || request.name.as_ref().is_some_and(|name| {
            let length = name.trim().chars().count();
            !(2..=120).contains(&length)
        })
    {
        return Err(PublishError::Invalid);
    }
    Ok(())
}

pub async fn create(pool: &Pool, request: &TeamRequest) -> Result<TeamResponse, PublishError> {
    validate(request)?;
    if request.team_id.is_some() || request.name.is_none() {
        return Err(PublishError::Invalid);
    }
    let name = request.name.as_ref().ok_or(PublishError::Invalid)?.trim();
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let tx = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    // All team mutations in a competition serialize on its parent row.
    let competition = tx
        .query_opt(
            "SELECT slug, status, allow_teams FROM competitions \
             WHERE id = ($1::text)::uuid FOR UPDATE",
            &[&request.competition_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(competition) = competition else {
        return Ok(response("not_found"));
    };
    let slug: String = competition.get(0);
    let status: String = competition.get(1);
    let allow_teams: bool = competition.get(2);
    if !matches!(status.as_str(), "registration" | "scheduled") {
        return Ok(TeamResponse {
            current_status: Some(status),
            ..response("closed")
        });
    }
    if !allow_teams {
        return Ok(response("disabled"));
    }
    let participant = tx
        .query_opt(
            "SELECT team_id::text FROM competition_participants \
             WHERE competition_id = ($1::text)::uuid AND user_id = ($2::text)::uuid \
             FOR UPDATE",
            &[&request.competition_id, &request.actor_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(participant) = participant else {
        return Ok(response("not_registered"));
    };
    if participant.get::<_, Option<String>>(0).is_some() {
        return Ok(response("already_on_team"));
    }
    let team_id: String = tx
        .query_one(
            "INSERT INTO teams (id, competition_id, name, created_by) \
             VALUES (gen_random_uuid(), ($1::text)::uuid, $2, ($3::text)::uuid) \
             RETURNING id::text",
            &[&request.competition_id, &name, &request.actor_id],
        )
        .await
        .map_err(|_| PublishError::Database)?
        .get(0);
    tx.execute(
        "INSERT INTO team_members (id, team_id, user_id, role) \
         VALUES (gen_random_uuid(), ($1::text)::uuid, ($2::text)::uuid, 'captain')",
        &[&team_id, &request.actor_id],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.execute(
        "UPDATE competition_participants SET team_id = ($1::text)::uuid \
         WHERE competition_id = ($2::text)::uuid AND user_id = ($3::text)::uuid",
        &[&team_id, &request.competition_id, &request.actor_id],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    let details = serde_json::json!({"competition": slug}).to_string();
    tx.execute(
        "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address, details) \
         VALUES (gen_random_uuid(), 'team.create', ($1::text)::uuid, \
         $2, $3, ($4::text)::jsonb)",
        &[&request.actor_id, &name, &request.ip_address, &details],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.commit().await.map_err(|_| PublishError::Database)?;
    Ok(response("created"))
}

pub async fn join(pool: &Pool, request: &TeamRequest) -> Result<TeamResponse, PublishError> {
    validate(request)?;
    if request.team_id.is_none() || request.name.is_some() {
        return Err(PublishError::Invalid);
    }
    let team_id = request.team_id.as_ref().ok_or(PublishError::Invalid)?;
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let tx = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    let competition = tx
        .query_opt(
            "SELECT slug, status, allow_teams, max_team_size FROM competitions \
             WHERE id = ($1::text)::uuid FOR UPDATE",
            &[&request.competition_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(competition) = competition else {
        return Ok(response("not_found"));
    };
    let slug: String = competition.get(0);
    let status: String = competition.get(1);
    let allow_teams: bool = competition.get(2);
    let max_team_size: i32 = competition.get(3);
    if !matches!(status.as_str(), "registration" | "scheduled") {
        return Ok(TeamResponse {
            current_status: Some(status),
            ..response("closed")
        });
    }
    if !allow_teams {
        return Ok(response("disabled"));
    }
    let team = tx
        .query_opt(
            "SELECT name FROM teams WHERE id = ($1::text)::uuid \
             AND competition_id = ($2::text)::uuid",
            &[&team_id, &request.competition_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(team) = team else {
        return Ok(response("team_not_found"));
    };
    let name: String = team.get(0);
    let participant = tx
        .query_opt(
            "SELECT team_id::text FROM competition_participants \
             WHERE competition_id = ($1::text)::uuid AND user_id = ($2::text)::uuid \
             FOR UPDATE",
            &[&request.competition_id, &request.actor_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    let Some(participant) = participant else {
        return Ok(response("not_registered"));
    };
    if participant.get::<_, Option<String>>(0).is_some() {
        return Ok(response("already_on_team"));
    }
    let member_count: i64 = tx
        .query_one(
            "SELECT COUNT(*) FROM team_members WHERE team_id = ($1::text)::uuid",
            &[&team_id],
        )
        .await
        .map_err(|_| PublishError::Database)?
        .get(0);
    if member_count >= i64::from(max_team_size) {
        return Ok(TeamResponse {
            max_team_size: Some(max_team_size),
            ..response("full")
        });
    }
    tx.execute(
        "UPDATE competition_participants SET team_id = ($1::text)::uuid \
         WHERE competition_id = ($2::text)::uuid AND user_id = ($3::text)::uuid",
        &[&team_id, &request.competition_id, &request.actor_id],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.execute(
        "INSERT INTO team_members (id, team_id, user_id, role) \
         VALUES (gen_random_uuid(), ($1::text)::uuid, ($2::text)::uuid, 'member')",
        &[&team_id, &request.actor_id],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    let details = serde_json::json!({"competition": slug}).to_string();
    tx.execute(
        "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address, details) \
         VALUES (gen_random_uuid(), 'team.join', ($1::text)::uuid, \
         $2, $3, ($4::text)::jsonb)",
        &[&request.actor_id, &name, &request.ip_address, &details],
    )
    .await
    .map_err(|_| PublishError::Database)?;
    tx.commit().await.map_err(|_| PublishError::Database)?;
    Ok(response("joined"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn validates_student_roles_and_input() {
        let mut request = TeamRequest {
            competition_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee".into(),
            actor_id: "bbbbbbbb-cccc-dddd-eeee-ffffffffffff".into(),
            roles: vec!["student".into()],
            ip_address: None,
            name: Some("Blue Team".into()),
            team_id: None,
        };
        assert!(validate(&request).is_ok());
        request.roles = vec!["competition_organizer".into()];
        assert!(matches!(validate(&request), Err(PublishError::Forbidden)));
        request.roles = vec!["student".into()];
        request.name = Some("  ".into());
        assert!(matches!(validate(&request), Err(PublishError::Invalid)));
        request.name = None;
        request.team_id = Some("invalid".into());
        assert!(matches!(validate(&request), Err(PublishError::Invalid)));
    }
}
