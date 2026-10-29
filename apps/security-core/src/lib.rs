//! Pure, auditable security calculations. DB access and access control stay in the API.
pub mod attempts;
pub mod authorization;
pub mod catalog;
pub mod competition;
pub mod creation;
pub mod editing;
pub mod leaderboard;
pub mod publishing;
pub mod solves;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use subtle::ConstantTimeEq;

#[derive(Debug, Deserialize)]
pub struct VerifyFlagRequest {
    pub candidate: String,
    pub expected_sha256: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct VerifyFlagResponse {
    pub correct: bool,
}

pub fn verify_flag(request: &VerifyFlagRequest) -> Result<VerifyFlagResponse, &'static str> {
    if request.candidate.is_empty() || request.candidate.len() > 2048 {
        return Err("invalid candidate length");
    }
    let decoded = hex::decode(&request.expected_sha256).map_err(|_| "invalid digest")?;
    let expected: [u8; 32] = decoded.try_into().map_err(|_| "invalid digest length")?;
    let actual = Sha256::digest(request.candidate.trim().as_bytes());
    Ok(VerifyFlagResponse {
        correct: bool::from(actual.as_slice().ct_eq(&expected)),
    })
}

#[derive(Debug, Deserialize)]
pub struct ScoreRequest {
    pub base_points: i64,
    pub solve_rank: u64,
    pub mode: String,
    pub penalty: i64,
    #[serde(default = "default_min_points")]
    pub min_points: i64,
    #[serde(default = "default_decay_scale")]
    pub decay_scale: u64,
}

const fn default_min_points() -> i64 {
    100
}
const fn default_decay_scale() -> u64 {
    15
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ScoreResponse {
    pub points: i64,
    pub bonus: i64,
    pub is_first_blood: bool,
}

#[derive(Debug, Deserialize)]
pub struct LabTransitionRequest {
    pub current: String,
    pub target: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct LabTransitionResponse {
    pub allowed: bool,
}

/// All accepted arcs mirror CyberLab's existing lab state machine.
/// A transition that is not in this list is refused, including unknown states.
pub fn validate_lab_transition(
    request: &LabTransitionRequest,
) -> Result<LabTransitionResponse, &'static str> {
    let allowed = match request.current.as_str() {
        "queued" => matches!(
            request.target.as_str(),
            "provisioning" | "failed" | "terminated"
        ),
        "provisioning" => matches!(
            request.target.as_str(),
            "starting" | "failed" | "terminated"
        ),
        "starting" => matches!(request.target.as_str(), "running" | "failed" | "terminated"),
        "running" => matches!(
            request.target.as_str(),
            "stopping" | "resetting" | "terminating" | "expired" | "failed"
        ),
        "stopping" => matches!(request.target.as_str(), "stopped" | "failed"),
        "stopped" => matches!(
            request.target.as_str(),
            "starting" | "resetting" | "terminating" | "terminated"
        ),
        "resetting" => matches!(
            request.target.as_str(),
            "provisioning" | "failed" | "terminated"
        ),
        "terminating" => matches!(request.target.as_str(), "terminated" | "failed"),
        "terminated" => false,
        "failed" => matches!(
            request.target.as_str(),
            "queued" | "terminating" | "terminated"
        ),
        "expired" => matches!(
            request.target.as_str(),
            "terminating" | "terminated" | "resetting"
        ),
        _ => return Err("invalid current lab state"),
    };
    if !matches!(
        request.target.as_str(),
        "queued"
            | "provisioning"
            | "starting"
            | "running"
            | "stopping"
            | "stopped"
            | "resetting"
            | "terminating"
            | "terminated"
            | "failed"
            | "expired"
    ) {
        return Err("invalid target lab state");
    }
    Ok(LabTransitionResponse { allowed })
}

// Integer rounding to nearest even, matching Python's round() for positive inputs.
fn div_round_even(n: u128, d: u128) -> u128 {
    let q = n / d;
    let remainder = n % d;
    if remainder > d - remainder || (remainder == d - remainder && q % 2 == 1) {
        q + 1
    } else {
        q
    }
}

pub fn score(request: &ScoreRequest) -> Result<ScoreResponse, &'static str> {
    if request.base_points < 0
        || request.base_points > 1_000_000
        || request.penalty < 0
        || request.penalty > 1_000_000_000
        || request.min_points < 0
        || request.solve_rank == 0
        || request.decay_scale == 0
        || request.decay_scale > 1_000_000
    {
        return Err("invalid scoring parameters");
    }
    let base = request.base_points as u128;
    let rank = request.solve_rank;
    let bonus = if request.mode == "first_blood" {
        let percentage = match rank {
            1 => 20,
            2 => 10,
            3 => 5,
            _ => 0,
        };
        div_round_even(base * percentage, 100)
    } else {
        0
    };
    let earned = match request.mode.as_str() {
        "standard" | "first_blood" | "override" => base + bonus,
        "dynamic" if rank <= 1 => base,
        "dynamic" => {
            let floor = request.min_points.min(request.base_points) as u128;
            let scale = u128::from(request.decay_scale);
            let denominator = scale + u128::from(rank - 1);
            floor + div_round_even((base - floor) * scale, denominator)
        }
        _ => return Err("unsupported scoring mode"),
    };
    let points = earned.saturating_sub(request.penalty as u128);
    Ok(ScoreResponse {
        points: i64::try_from(points).map_err(|_| "score overflow")?,
        bonus: i64::try_from(bonus).map_err(|_| "bonus overflow")?,
        is_first_blood: rank == 1,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn flag_verification_matches_existing_hashes_and_trims() {
        let digest = hex::encode(Sha256::digest(b"IIC{test-flag}"));
        let request = VerifyFlagRequest {
            candidate: " IIC{test-flag}  ".into(),
            expected_sha256: digest.clone(),
        };
        assert!(verify_flag(&request).unwrap().correct);
        assert!(
            !verify_flag(&VerifyFlagRequest {
                candidate: "IIC{wrong}".into(),
                expected_sha256: digest,
            })
            .unwrap()
            .correct
        );
    }

    #[test]
    fn malformed_digest_is_rejected() {
        assert!(verify_flag(&VerifyFlagRequest {
            candidate: "x".into(),
            expected_sha256: "invalid".into()
        })
        .is_err());
    }

    #[test]
    fn scoring_matches_python_modes() {
        let mut request = ScoreRequest {
            base_points: 500,
            solve_rank: 1,
            mode: "dynamic".into(),
            penalty: 0,
            min_points: 100,
            decay_scale: 10,
        };
        assert_eq!(score(&request).unwrap().points, 500);
        request.solve_rank = 2;
        assert_eq!(score(&request).unwrap().points, 464);
        request.solve_rank = 100;
        assert!(score(&request).unwrap().points >= 100);
        request.mode = "first_blood".into();
        request.solve_rank = 1;
        assert_eq!(score(&request).unwrap().points, 600);
        request.solve_rank = 2;
        request.penalty = 40;
        assert_eq!(score(&request).unwrap().points, 510);
    }

    #[test]
    fn tie_rounding_matches_python() {
        let request = ScoreRequest {
            base_points: 25,
            solve_rank: 3,
            mode: "first_blood".into(),
            penalty: 0,
            min_points: 100,
            decay_scale: 15,
        };
        assert_eq!(score(&request).unwrap().bonus, 1);
        assert!(score(&ScoreRequest {
            solve_rank: 0,
            ..request
        })
        .is_err());
    }

    #[test]
    fn lab_transitions_enforce_valid_arcs_and_terminal_state() {
        for (from, to) in [
            ("queued", "provisioning"),
            ("provisioning", "starting"),
            ("starting", "running"),
            ("running", "stopping"),
            ("stopping", "stopped"),
            ("stopped", "resetting"),
            ("resetting", "provisioning"),
            ("running", "expired"),
        ] {
            assert!(
                validate_lab_transition(&LabTransitionRequest {
                    current: from.into(),
                    target: to.into()
                })
                .unwrap()
                .allowed
            );
        }
        assert!(
            !validate_lab_transition(&LabTransitionRequest {
                current: "terminated".into(),
                target: "running".into()
            })
            .unwrap()
            .allowed
        );
        assert!(
            !validate_lab_transition(&LabTransitionRequest {
                current: "queued".into(),
                target: "running".into()
            })
            .unwrap()
            .allowed
        );
        assert!(validate_lab_transition(&LabTransitionRequest {
            current: "undefined".into(),
            target: "running".into()
        })
        .is_err());
    }
}
