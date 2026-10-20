//! CyberLab RBAC policy, derived from the Keycloak realm role names.
//! Keep this role matrix in parity with app/core/permissions.py during migration.

use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

#[derive(Debug, Deserialize)]
pub struct AuthorizationRequest {
    pub roles: Vec<String>,
    pub permission: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct AuthorizationResponse {
    pub permissions: Vec<String>,
    pub allowed: Option<bool>,
}

fn role_permissions(role: &str) -> &'static [&'static str] {
    match role {
        "sysadmin" => &["*", "user.view", "user.manage", "learning_path.manage"],
        "faculty" => &[
            "challenge.view",
            "challenge.create",
            "challenge.edit",
            "challenge.publish",
            "submission.review",
            "analytics.view",
            "audit.view",
            "lab.launch",
            "lab.reset",
            "lab.admin",
            "competition.create",
            "competition.manage",
            "skill.view",
            "skill.manage",
            "badge.view",
            "badge.manage",
            "learning_path.manage",
            "learning_path.view",
        ],
        "competition_organizer" => &[
            "competition.create",
            "competition.manage",
            "challenge.view",
            "analytics.view",
            "skill.view",
            "badge.view",
            "learning_path.manage",
            "learning_path.view",
        ],
        "lab_admin" => &[
            "lab.admin",
            "lab.launch",
            "lab.reset",
            "challenge.view",
            "analytics.view",
            "audit.view",
            "skill.view",
            "badge.view",
        ],
        "researcher" => &[
            "analytics.view",
            "analytics.research",
            "challenge.view",
            "skill.view",
            "badge.view",
        ],
        "student" => &[
            "challenge.view",
            "challenge.attempt",
            "lab.launch",
            "lab.reset",
            "submission.create",
            "skill.view",
            "badge.view",
            "learning_path.view",
        ],
        _ => &[],
    }
}

pub fn authorize(request: &AuthorizationRequest) -> Result<AuthorizationResponse, &'static str> {
    // Reject malformed/oversized requests rather than accepting partially evaluated roles.
    if request.roles.len() > 32 || request.roles.iter().any(|r| r.len() > 128) {
        return Err("invalid roles");
    }
    if request
        .permission
        .as_ref()
        .is_some_and(|p| p.is_empty() || p.len() > 128)
    {
        return Err("invalid permission");
    }
    // Preserve FastAPI's established expansion order: sorted roles, then
    // sorted permissions within each role, omitting duplicates on first use.
    let mut roles: Vec<&str> = request.roles.iter().map(String::as_str).collect();
    roles.sort_unstable();
    let mut seen = BTreeSet::new();
    let mut permissions = Vec::new();
    for role in roles {
        let mut role_perms = role_permissions(role).to_vec();
        role_perms.sort_unstable();
        for permission in role_perms {
            if seen.insert(permission) {
                permissions.push(permission.to_owned());
            }
        }
    }
    let allowed = request
        .permission
        .as_deref()
        .map(|permission| seen.contains("*") || seen.contains(permission));
    Ok(AuthorizationResponse {
        permissions,
        allowed,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn recognized_and_unknown_roles() {
        let request = AuthorizationRequest {
            roles: vec!["student".into(), "unknown".into(), "student".into()],
            permission: Some("submission.create".into()),
        };
        let result = authorize(&request).unwrap();
        assert_eq!(result.allowed, Some(true));
        assert_eq!(
            result
                .permissions
                .iter()
                .filter(|p| *p == "submission.create")
                .count(),
            1
        );
        assert!(!result.permissions.contains(&"challenge.edit".into()));
        assert_eq!(
            authorize(&AuthorizationRequest {
                roles: vec!["unknown".into()],
                permission: Some("challenge.view".into()),
            })
            .unwrap()
            .allowed,
            Some(false)
        );
    }

    #[test]
    fn wildcard_is_exclusive_to_sysadmin() {
        assert_eq!(
            authorize(&AuthorizationRequest {
                roles: vec!["sysadmin".into()],
                permission: Some("anything.at.all".into()),
            })
            .unwrap()
            .allowed,
            Some(true)
        );
        assert_eq!(
            authorize(&AuthorizationRequest {
                roles: vec!["faculty".into()],
                permission: Some("submission.create".into()),
            })
            .unwrap()
            .allowed,
            Some(false)
        );
    }

    #[test]
    fn permission_expansion_and_validation() {
        let result = authorize(&AuthorizationRequest {
            roles: vec!["faculty".into(), "researcher".into()],
            permission: None,
        })
        .unwrap();
        assert_eq!(result.allowed, None);
        assert!(result.permissions.contains(&"analytics.research".into()));
        assert!(result.permissions.contains(&"challenge.edit".into()));
        assert_eq!(
            result
                .permissions
                .iter()
                .filter(|p| *p == "analytics.view")
                .count(),
            1
        );
        assert!(authorize(&AuthorizationRequest {
            roles: vec!["x".repeat(129)],
            permission: None,
        })
        .is_err());
    }
}
