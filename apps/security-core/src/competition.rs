//! Authoritative competition transition policy.
//!
//! All input timestamps are UTC Unix milliseconds. The API owns the trusted clock,
//! database transactions and authorization; this module owns state decisions.
use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize)]
pub struct CompetitionTransitionRequest {
    pub current: String,
    /// For organizer actions: start_registration, schedule, start, finish, archive.
    /// For the timer: auto.
    pub action: String,
    pub start_at: Option<i64>,
    pub end_at: Option<i64>,
    pub now: i64,
}

#[derive(Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct CompetitionTransitionResponse {
    pub next_status: Option<String>,
    pub error_code: Option<String>,
}

fn decision(next: Option<&str>, error: Option<&str>) -> CompetitionTransitionResponse {
    CompetitionTransitionResponse {
        next_status: next.map(str::to_owned),
        error_code: error.map(str::to_owned),
    }
}

pub fn transition_competition(
    request: &CompetitionTransitionRequest,
) -> Result<CompetitionTransitionResponse, &'static str> {
    if !matches!(
        request.current.as_str(),
        "draft" | "registration" | "scheduled" | "live" | "finished" | "archived"
    ) {
        return Err("unknown competition status");
    }
    if request.action == "auto" {
        return Ok(match request.current.as_str() {
            "scheduled" if request.start_at.is_some_and(|start| start <= request.now) => {
                decision(Some("live"), None)
            }
            "live" if request.end_at.is_some_and(|end| end <= request.now) => {
                decision(Some("finished"), None)
            }
            _ => decision(None, None),
        });
    }
    let (expected, next) = match request.action.as_str() {
        "start_registration" => ("draft", "registration"),
        "schedule" => ("registration", "scheduled"),
        "start" => ("scheduled", "live"),
        "finish" => ("live", "finished"),
        "archive" => ("finished", "archived"),
        _ => return Ok(decision(None, Some("unknown_action"))),
    };
    if request.current != expected {
        return Ok(decision(None, Some("invalid_transition")));
    }
    if request.action == "schedule" && (request.start_at.is_none() || request.end_at.is_none()) {
        return Ok(decision(None, Some("missing_schedule")));
    }
    // Organizer may start up to five minutes early (existing API contract).
    if request.action == "start"
        && request
            .start_at
            .is_some_and(|start| i128::from(start) > i128::from(request.now) + 300_000)
    {
        return Ok(decision(None, Some("too_early")));
    }
    Ok(decision(Some(next), None))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn req(current: &str, action: &str) -> CompetitionTransitionRequest {
        CompetitionTransitionRequest {
            current: current.into(),
            action: action.into(),
            start_at: Some(1_000),
            end_at: Some(3_000),
            now: 1_500,
        }
    }

    #[test]
    fn organizer_transitions() {
        for (current, action, next) in [
            ("draft", "start_registration", "registration"),
            ("registration", "schedule", "scheduled"),
            ("scheduled", "start", "live"),
            ("live", "finish", "finished"),
            ("finished", "archive", "archived"),
        ] {
            let result = transition_competition(&req(current, action)).unwrap();
            assert_eq!(result.next_status.as_deref(), Some(next));
            assert_eq!(result.error_code, None);
        }
    }

    #[test]
    fn denies_unexpected_actions_and_bad_state() {
        assert_eq!(
            transition_competition(&req("draft", "start"))
                .unwrap()
                .error_code
                .as_deref(),
            Some("invalid_transition")
        );
        assert_eq!(
            transition_competition(&req("draft", "arbitrary"))
                .unwrap()
                .error_code
                .as_deref(),
            Some("unknown_action")
        );
        assert!(transition_competition(&req("unrecognized", "start")).is_err());
    }

    #[test]
    fn scheduling_constraints() {
        let mut request = req("registration", "schedule");
        request.end_at = None;
        assert_eq!(
            transition_competition(&request)
                .unwrap()
                .error_code
                .as_deref(),
            Some("missing_schedule")
        );
        let mut request = req("scheduled", "start");
        request.start_at = Some(301_501);
        assert_eq!(
            transition_competition(&request)
                .unwrap()
                .error_code
                .as_deref(),
            Some("too_early")
        );
        request.start_at = Some(301_500);
        assert_eq!(
            transition_competition(&request)
                .unwrap()
                .next_status
                .as_deref(),
            Some("live")
        );
    }

    #[test]
    fn scheduled_competitions_transition_at_boundaries() {
        let mut request = req("scheduled", "auto");
        request.now = 999;
        assert_eq!(transition_competition(&request).unwrap().next_status, None);
        request.now = 1_000;
        assert_eq!(
            transition_competition(&request)
                .unwrap()
                .next_status
                .as_deref(),
            Some("live")
        );
        request.current = "live".into();
        request.now = 2_999;
        assert_eq!(transition_competition(&request).unwrap().next_status, None);
        request.now = 3_000;
        assert_eq!(
            transition_competition(&request)
                .unwrap()
                .next_status
                .as_deref(),
            Some("finished")
        );
        request.current = "finished".into();
        assert_eq!(transition_competition(&request).unwrap().next_status, None);
    }
}
