//! Rust-owned challenge editing; one transaction covers data, skills and audit.
use std::collections::{HashMap, HashSet};

use deadpool_postgres::Pool;
use serde::Deserialize;
use serde_json::{Map, Value};
use tokio_postgres::Transaction;

use crate::publishing::{validate_permission, PublishError, PublishRequest, PublishResponse};

#[derive(Debug, Deserialize)]
pub struct EditRequest {
    pub challenge_id: String,
    pub actor_id: String,
    pub roles: Vec<String>,
    pub ip_address: Option<String>,
    pub changes: Map<String, Value>,
}

fn nonempty_string(value: &Value, max_len: Option<usize>) -> bool {
    value
        .as_str()
        .is_some_and(|s| !s.is_empty() && max_len.is_none_or(|max| s.chars().count() <= max))
}

fn string_or_null(value: &Value, max_len: Option<usize>) -> bool {
    value.is_null()
        || value
            .as_str()
            .is_some_and(|s| max_len.is_none_or(|m| s.len() <= m))
}

fn valid_string_list(value: &Value) -> bool {
    value.is_null()
        || value.as_array().is_some_and(|list| {
            list.len() <= 500
                && list
                    .iter()
                    .all(|entry| entry.as_str().is_some_and(|s| s.len() <= 256))
        })
}

pub fn validate_changes(changes: &Map<String, Value>) -> Result<(), PublishError> {
    for (key, value) in changes {
        let valid = match key.as_str() {
            "title" => nonempty_string(value, Some(200)),
            "description" => nonempty_string(value, None),
            "instructions" => string_or_null(value, None),
            "category" => value.as_str().is_some_and(|category| {
                matches!(
                    category,
                    "Linux"
                        | "Networking"
                        | "Web Security"
                        | "Cryptography"
                        | "Digital Forensics"
                        | "OSINT"
                        | "System Security"
                        | "Blue Team"
                        | "Secure Coding"
                        | "Cloud Security"
                )
            }),
            "difficulty" => value
                .as_str()
                .is_some_and(|d| matches!(d, "beginner" | "intermediate" | "advanced")),
            "points" | "hint_penalty" => value
                .as_i64()
                .is_some_and(|n| (0..=i32::MAX as i64).contains(&n)),
            "estimated_minutes" => {
                value.is_null()
                    || value
                        .as_i64()
                        .is_some_and(|n| (1..=i32::MAX as i64).contains(&n))
            }
            "skills" | "prerequisites" | "hints" => valid_string_list(value),
            "flag_hash" => {
                value.is_null()
                    || value.as_str().is_some_and(|hash| {
                        hash.len() == 64 && hash.bytes().all(|byte| byte.is_ascii_hexdigit())
                    })
            }
            "flag_format" => string_or_null(value, Some(120)),
            "environment_type" => nonempty_string(value, Some(32)),
            "lab_config" => value.is_null() || value.is_object(),
            // Status is deliberately NEVER editable through PATCH.
            _ => false,
        };
        if !valid {
            return Err(PublishError::Invalid);
        }
    }
    Ok(())
}

fn normalize(value: &str) -> String {
    value
        .trim()
        .to_lowercase()
        .replace('/', " ")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn skill_alias(value: &str) -> &str {
    match value {
        "packet basics" | "tcp ip" | "email headers" | "spf dkim awareness" => "networking",
        "linux cli"
        | "filesystem"
        | "basic command usage"
        | "bash scripting"
        | "linux permissions"
        | "suid"
        | "enumeration" => "linux",
        "web enumeration" | "sql" | "auth bypass" => "web-security",
        "xor" | "pattern recognition" => "cryptography",
        "exif" | "metadata analysis" | "forensics tooling" => "digital-forensics",
        "phishing analysis" => "security-operations",
        "c" | "buffer handling" | "code review" => "secure-coding",
        _ => "",
    }
}

/// Reconcile taxonomy links inside the same transaction as a challenge write.
/// Shared by editing and creation, so neither flow can commit without links.
pub(crate) async fn sync_skills(
    transaction: &Transaction<'_>,
    challenge_id: &str,
    skills_value: &Value,
) -> Result<(), PublishError> {
    transaction
        .execute(
            "DELETE FROM challenge_skills WHERE challenge_id = ($1::text)::uuid",
            &[&challenge_id],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    if let Some(names) = skills_value.as_array() {
        let rows = transaction
            .query("SELECT id::text, slug, name FROM skills", &[])
            .await
            .map_err(|_| PublishError::Database)?;
        let mut by_key: HashMap<String, String> = HashMap::new();
        for row in rows {
            let id: String = row.get(0);
            let slug: String = row.get(1);
            let name: String = row.get(2);
            by_key.insert(slug, id.clone());
            by_key.insert(normalize(&name), id);
        }
        let mut linked: HashSet<String> = HashSet::new();
        for value in names {
            if let Some(raw) = value.as_str() {
                let key = normalize(raw);
                if let Some(id) = by_key.get(&key).or_else(|| by_key.get(skill_alias(&key))) {
                    linked.insert(id.clone());
                }
            }
        }
        for skill_id in linked {
            transaction
                .execute(
                    "INSERT INTO challenge_skills (id, challenge_id, skill_id)
                     VALUES (gen_random_uuid(), ($1::text)::uuid, ($2::text)::uuid)",
                    &[&challenge_id, &skill_id],
                )
                .await
                .map_err(|_| PublishError::Database)?;
        }
    }
    Ok(())
}

pub async fn edit(pool: &Pool, request: &EditRequest) -> Result<PublishResponse, PublishError> {
    validate_permission(
        &PublishRequest {
            challenge_id: request.challenge_id.clone(),
            actor_id: request.actor_id.clone(),
            roles: request.roles.clone(),
            ip_address: request.ip_address.clone(),
        },
        "challenge.edit",
    )?;
    validate_changes(&request.changes)?;
    let mut client = pool.get().await.map_err(|_| PublishError::Database)?;
    let transaction = client
        .transaction()
        .await
        .map_err(|_| PublishError::Database)?;
    let row = transaction
        .query_opt(
            "SELECT slug, status FROM challenges WHERE id = ($1::text)::uuid FOR UPDATE",
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
    let status: String = row.get(1);
    if status == "published" && request.changes.get("flag_hash").is_some_and(Value::is_null) {
        return Ok(PublishResponse {
            outcome: "missing_flag".into(),
            version: None,
        });
    }

    // Convert to JSON text rather than interpolating any user-supplied SQL identifiers.
    // All modifiable columns are explicitly allowlisted above and below.
    let changes = Value::Object(request.changes.clone()).to_string();
    let row = transaction.query_one(
        "UPDATE challenges SET
            title = CASE WHEN ($2::text)::jsonb ? 'title' THEN ($2::text)::jsonb->>'title' ELSE title END,
            description = CASE WHEN ($2::text)::jsonb ? 'description' THEN ($2::text)::jsonb->>'description' ELSE description END,
            instructions = CASE WHEN ($2::text)::jsonb ? 'instructions' THEN ($2::text)::jsonb->>'instructions' ELSE instructions END,
            category = CASE WHEN ($2::text)::jsonb ? 'category' THEN ($2::text)::jsonb->>'category' ELSE category END,
            difficulty = CASE WHEN ($2::text)::jsonb ? 'difficulty' THEN ($2::text)::jsonb->>'difficulty' ELSE difficulty END,
            points = CASE WHEN ($2::text)::jsonb ? 'points' THEN (($2::text)::jsonb->>'points')::integer ELSE points END,
            estimated_minutes = CASE WHEN ($2::text)::jsonb ? 'estimated_minutes' THEN (($2::text)::jsonb->>'estimated_minutes')::integer ELSE estimated_minutes END,
            skills = CASE WHEN ($2::text)::jsonb ? 'skills' THEN (($2::text)::jsonb->'skills')::json ELSE skills END,
            prerequisites = CASE WHEN ($2::text)::jsonb ? 'prerequisites' THEN (($2::text)::jsonb->'prerequisites')::json ELSE prerequisites END,
            hints = CASE WHEN ($2::text)::jsonb ? 'hints' THEN (($2::text)::jsonb->'hints')::json ELSE hints END,
            hint_penalty = CASE WHEN ($2::text)::jsonb ? 'hint_penalty' THEN (($2::text)::jsonb->>'hint_penalty')::integer ELSE hint_penalty END,
            flag_hash = CASE WHEN ($2::text)::jsonb ? 'flag_hash' THEN ($2::text)::jsonb->>'flag_hash' ELSE flag_hash END,
            flag_format = CASE WHEN ($2::text)::jsonb ? 'flag_format' THEN ($2::text)::jsonb->>'flag_format' ELSE flag_format END,
            environment_type = CASE WHEN ($2::text)::jsonb ? 'environment_type' THEN ($2::text)::jsonb->>'environment_type' ELSE environment_type END,
            lab_config = CASE WHEN ($2::text)::jsonb ? 'lab_config' THEN (($2::text)::jsonb->'lab_config')::json ELSE lab_config END,
            version = version + 1, updated_at = now()
         WHERE id = ($1::text)::uuid RETURNING version",
        &[&request.challenge_id, &changes],
    ).await.map_err(|_| PublishError::Database)?;
    let version: i32 = row.get(0);

    if let Some(skills_value) = request.changes.get("skills") {
        sync_skills(&transaction, &request.challenge_id, skills_value).await?;
    }
    transaction
        .execute(
            "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address)
         VALUES (gen_random_uuid(), 'challenge.update', ($1::text)::uuid, $2, $3)",
            &[&request.actor_id, &slug, &request.ip_address],
        )
        .await
        .map_err(|_| PublishError::Database)?;
    transaction
        .commit()
        .await
        .map_err(|_| PublishError::Database)?;
    Ok(PublishResponse {
        outcome: "updated".into(),
        version: Some(version),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_publication_and_invalid_field_values() {
        let mut updates = Map::new();
        updates.insert("status".into(), Value::String("published".into()));
        assert!(matches!(
            validate_changes(&updates),
            Err(PublishError::Invalid)
        ));
        updates.clear();
        updates.insert("points".into(), Value::Number((-1).into()));
        assert!(matches!(
            validate_changes(&updates),
            Err(PublishError::Invalid)
        ));
        updates.clear();
        updates.insert("skills".into(), serde_json::json!(["Linux CLI", "SQL"]));
        assert!(validate_changes(&updates).is_ok());
        assert_eq!(skill_alias(&normalize("Linux CLI")), "linux");
    }
}
