use axum::{
    extract::{DefaultBodyLimit, State},
    http::{HeaderMap, StatusCode},
    routing::{get, post},
    Json, Router,
};
use cyberlab_security_core::attempts::{
    record as record_incorrect_attempt, IncorrectAttemptRequest, IncorrectAttemptResponse,
};
use cyberlab_security_core::authorization::{
    authorize, AuthorizationRequest, AuthorizationResponse,
};
use cyberlab_security_core::catalog::{query_catalog, CatalogError, CatalogPage, CatalogQuery};
use cyberlab_security_core::competition::{
    transition_competition, CompetitionTransitionRequest, CompetitionTransitionResponse,
};
use cyberlab_security_core::competition_freeze::{
    set_frozen, CompetitionFreezeRequest, CompetitionFreezeResponse,
};
use cyberlab_security_core::competition_links::{
    add as add_competition_challenge, remove as remove_competition_challenge,
    CompetitionLinkRequest, CompetitionLinkResponse,
};
use cyberlab_security_core::competition_participants::{
    register as register_participant, unregister as unregister_participant, ParticipantRequest,
    ParticipantResponse,
};
use cyberlab_security_core::competition_teams::{
    create as create_team, join as join_team, TeamRequest, TeamResponse,
};
use cyberlab_security_core::competition_transition_writes::{
    persist as persist_competition_transition, ManualTransitionRequest, ManualTransitionResponse,
};
use cyberlab_security_core::competition_writes::{
    create as create_competition_record, edit as edit_competition_record, CompetitionCreateRequest,
    CompetitionCreateResponse, CompetitionEditRequest, CompetitionEditResponse,
};
use cyberlab_security_core::creation::{create, CreateRequest, CreateResponse};
use cyberlab_security_core::editing::{edit, EditRequest};
use cyberlab_security_core::leaderboard::{
    global_leaderboard, LeaderboardError, LeaderboardQuery, LeaderboardRow,
};
use cyberlab_security_core::publishing::{
    delete, publish, PublishError, PublishRequest, PublishResponse,
};
use cyberlab_security_core::solves::{
    record as record_correct_solve, CorrectSolveRequest, CorrectSolveResponse,
};
use cyberlab_security_core::{
    score, validate_lab_transition, verify_flag, LabTransitionRequest, LabTransitionResponse,
    ScoreRequest, ScoreResponse, VerifyFlagRequest, VerifyFlagResponse,
};
use std::{env, net::SocketAddr, sync::Arc, time::Duration};
use subtle::ConstantTimeEq;

#[derive(Clone)]
struct AppState {
    token: Arc<String>,
    database: Option<deadpool_postgres::Pool>,
    write_database: Option<deadpool_postgres::Pool>,
}

fn authorized(headers: &HeaderMap, state: &AppState) -> bool {
    let Some(value) = headers.get("x-internal-token") else {
        return false;
    };
    let token = state.token.as_bytes();
    let received = value.as_bytes();
    received.len() == token.len() && bool::from(received.ct_eq(token))
}

async fn health() -> Json<serde_json::Value> {
    Json(serde_json::json!({"status":"ok","service":"cyberlab-security-core"}))
}

// Liveness is independent of PostgreSQL, but callers must not be routed to
// catalog/leaderboard handlers until their backing database is reachable.
async fn ready(State(state): State<AppState>) -> Result<Json<serde_json::Value>, StatusCode> {
    let pool = state
        .database
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;
    let check = async {
        let client = pool
            .get()
            .await
            .map_err(|_| StatusCode::SERVICE_UNAVAILABLE)?;
        client
            .simple_query("SELECT 1")
            .await
            .map_err(|_| StatusCode::SERVICE_UNAVAILABLE)?;
        Ok::<(), StatusCode>(())
    };
    tokio::time::timeout(Duration::from_secs(2), check)
        .await
        .map_err(|_| StatusCode::SERVICE_UNAVAILABLE)??;
    Ok(Json(serde_json::json!({"status":"ready"})))
}

async fn verify(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<VerifyFlagRequest>,
) -> Result<Json<VerifyFlagResponse>, StatusCode> {
    if !authorized(&headers, &state) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    verify_flag(&payload)
        .map(Json)
        .map_err(|_| StatusCode::BAD_REQUEST)
}

async fn calculate(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<ScoreRequest>,
) -> Result<Json<ScoreResponse>, StatusCode> {
    if !authorized(&headers, &state) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    score(&payload)
        .map(Json)
        .map_err(|_| StatusCode::BAD_REQUEST)
}

async fn lab_transition(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<LabTransitionRequest>,
) -> Result<Json<LabTransitionResponse>, StatusCode> {
    if !authorized(&headers, &state) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    validate_lab_transition(&payload)
        .map(Json)
        .map_err(|_| StatusCode::BAD_REQUEST)
}

async fn authorization(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<AuthorizationRequest>,
) -> Result<Json<AuthorizationResponse>, StatusCode> {
    if !authorized(&headers, &state) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    authorize(&payload)
        .map(Json)
        .map_err(|_| StatusCode::BAD_REQUEST)
}

async fn competition_transition(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<CompetitionTransitionRequest>,
) -> Result<Json<CompetitionTransitionResponse>, StatusCode> {
    if !authorized(&headers, &state) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    transition_competition(&payload)
        .map(Json)
        .map_err(|_| StatusCode::BAD_REQUEST)
}

async fn challenge_catalog(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<CatalogQuery>,
) -> Result<Json<CatalogPage>, StatusCode> {
    if !authorized(&headers, &state) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    let pool = state
        .database
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;
    match query_catalog(pool, &payload).await {
        Ok(page) => Ok(Json(page)),
        Err(CatalogError::Invalid) => Err(StatusCode::BAD_REQUEST),
        Err(CatalogError::Database) => Err(StatusCode::SERVICE_UNAVAILABLE),
    }
}

async fn leaderboard(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<LeaderboardQuery>,
) -> Result<Json<Vec<LeaderboardRow>>, StatusCode> {
    if !authorized(&headers, &state) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    let pool = state
        .database
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;
    match global_leaderboard(pool, &payload).await {
        Ok(rows) => Ok(Json(rows)),
        Err(LeaderboardError::Invalid) => Err(StatusCode::BAD_REQUEST),
        Err(LeaderboardError::Database) => Err(StatusCode::SERVICE_UNAVAILABLE),
    }
}

async fn publish_challenge(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<PublishRequest>,
) -> Result<Json<PublishResponse>, StatusCode> {
    if !authorized(&headers, &state) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    let pool = state
        .write_database
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;
    match publish(pool, &payload).await {
        Ok(result) => Ok(Json(result)),
        Err(PublishError::Invalid) => Err(StatusCode::BAD_REQUEST),
        Err(PublishError::Forbidden) => Err(StatusCode::FORBIDDEN),
        Err(PublishError::Database) => Err(StatusCode::SERVICE_UNAVAILABLE),
    }
}

async fn delete_challenge(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<PublishRequest>,
) -> Result<Json<PublishResponse>, StatusCode> {
    if !authorized(&headers, &state) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    let pool = state
        .write_database
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;
    match delete(pool, &payload).await {
        Ok(result) => Ok(Json(result)),
        Err(PublishError::Invalid) => Err(StatusCode::BAD_REQUEST),
        Err(PublishError::Forbidden) => Err(StatusCode::FORBIDDEN),
        Err(PublishError::Database) => Err(StatusCode::SERVICE_UNAVAILABLE),
    }
}

async fn edit_challenge(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<EditRequest>,
) -> Result<Json<PublishResponse>, StatusCode> {
    if !authorized(&headers, &state) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    let pool = state
        .write_database
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;
    match edit(pool, &payload).await {
        Ok(value) => Ok(Json(value)),
        Err(PublishError::Invalid) => Err(StatusCode::BAD_REQUEST),
        Err(PublishError::Forbidden) => Err(StatusCode::FORBIDDEN),
        Err(PublishError::Database) => Err(StatusCode::SERVICE_UNAVAILABLE),
    }
}

async fn create_challenge(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<CreateRequest>,
) -> Result<Json<CreateResponse>, StatusCode> {
    if !authorized(&headers, &state) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    let pool = state
        .write_database
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;
    match create(pool, &payload).await {
        Ok(value) => Ok(Json(value)),
        Err(PublishError::Invalid) => Err(StatusCode::BAD_REQUEST),
        Err(PublishError::Forbidden) => Err(StatusCode::FORBIDDEN),
        Err(PublishError::Database) => Err(StatusCode::SERVICE_UNAVAILABLE),
    }
}

async fn incorrect_submission(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<IncorrectAttemptRequest>,
) -> Result<Json<IncorrectAttemptResponse>, StatusCode> {
    if !authorized(&headers, &state) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    let pool = state
        .write_database
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;
    match record_incorrect_attempt(pool, &payload).await {
        Ok(result) => Ok(Json(result)),
        Err(PublishError::Invalid) => Err(StatusCode::BAD_REQUEST),
        Err(PublishError::Forbidden) => Err(StatusCode::FORBIDDEN),
        Err(PublishError::Database) => Err(StatusCode::SERVICE_UNAVAILABLE),
    }
}

async fn correct_submission(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<CorrectSolveRequest>,
) -> Result<Json<CorrectSolveResponse>, StatusCode> {
    if !authorized(&headers, &state) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    let pool = state
        .write_database
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;
    match record_correct_solve(pool, &payload).await {
        Ok(result) => Ok(Json(result)),
        Err(PublishError::Invalid) => Err(StatusCode::BAD_REQUEST),
        Err(PublishError::Forbidden) => Err(StatusCode::FORBIDDEN),
        Err(PublishError::Database) => Err(StatusCode::SERVICE_UNAVAILABLE),
    }
}

async fn create_competition_record_route(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<CompetitionCreateRequest>,
) -> Result<Json<CompetitionCreateResponse>, StatusCode> {
    if !authorized(&headers, &state) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    let pool = state
        .write_database
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;
    match create_competition_record(pool, &payload).await {
        Ok(result) => Ok(Json(result)),
        Err(PublishError::Invalid) => Err(StatusCode::BAD_REQUEST),
        Err(PublishError::Forbidden) => Err(StatusCode::FORBIDDEN),
        Err(PublishError::Database) => Err(StatusCode::SERVICE_UNAVAILABLE),
    }
}

async fn edit_competition_record_route(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<CompetitionEditRequest>,
) -> Result<Json<CompetitionEditResponse>, StatusCode> {
    if !authorized(&headers, &state) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    let pool = state
        .write_database
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;
    match edit_competition_record(pool, &payload).await {
        Ok(result) => Ok(Json(result)),
        Err(PublishError::Invalid) => Err(StatusCode::BAD_REQUEST),
        Err(PublishError::Forbidden) => Err(StatusCode::FORBIDDEN),
        Err(PublishError::Database) => Err(StatusCode::SERVICE_UNAVAILABLE),
    }
}

async fn add_competition_challenge_route(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<CompetitionLinkRequest>,
) -> Result<Json<CompetitionLinkResponse>, StatusCode> {
    if !authorized(&headers, &state) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    let pool = state
        .write_database
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;
    match add_competition_challenge(pool, &payload).await {
        Ok(result) => Ok(Json(result)),
        Err(PublishError::Invalid) => Err(StatusCode::BAD_REQUEST),
        Err(PublishError::Forbidden) => Err(StatusCode::FORBIDDEN),
        Err(PublishError::Database) => Err(StatusCode::SERVICE_UNAVAILABLE),
    }
}

async fn remove_competition_challenge_route(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<CompetitionLinkRequest>,
) -> Result<Json<CompetitionLinkResponse>, StatusCode> {
    if !authorized(&headers, &state) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    let pool = state
        .write_database
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;
    match remove_competition_challenge(pool, &payload).await {
        Ok(result) => Ok(Json(result)),
        Err(PublishError::Invalid) => Err(StatusCode::BAD_REQUEST),
        Err(PublishError::Forbidden) => Err(StatusCode::FORBIDDEN),
        Err(PublishError::Database) => Err(StatusCode::SERVICE_UNAVAILABLE),
    }
}

async fn register_competition_participant_route(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<ParticipantRequest>,
) -> Result<Json<ParticipantResponse>, StatusCode> {
    if !authorized(&headers, &state) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    let pool = state
        .write_database
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;
    match register_participant(pool, &payload).await {
        Ok(result) => Ok(Json(result)),
        Err(PublishError::Invalid) => Err(StatusCode::BAD_REQUEST),
        Err(PublishError::Forbidden) => Err(StatusCode::FORBIDDEN),
        Err(PublishError::Database) => Err(StatusCode::SERVICE_UNAVAILABLE),
    }
}

async fn unregister_competition_participant_route(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<ParticipantRequest>,
) -> Result<Json<ParticipantResponse>, StatusCode> {
    if !authorized(&headers, &state) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    let pool = state
        .write_database
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;
    match unregister_participant(pool, &payload).await {
        Ok(result) => Ok(Json(result)),
        Err(PublishError::Invalid) => Err(StatusCode::BAD_REQUEST),
        Err(PublishError::Forbidden) => Err(StatusCode::FORBIDDEN),
        Err(PublishError::Database) => Err(StatusCode::SERVICE_UNAVAILABLE),
    }
}

async fn create_competition_team_route(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<TeamRequest>,
) -> Result<Json<TeamResponse>, StatusCode> {
    if !authorized(&headers, &state) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    let pool = state
        .write_database
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;
    match create_team(pool, &payload).await {
        Ok(result) => Ok(Json(result)),
        Err(PublishError::Invalid) => Err(StatusCode::BAD_REQUEST),
        Err(PublishError::Forbidden) => Err(StatusCode::FORBIDDEN),
        Err(PublishError::Database) => Err(StatusCode::SERVICE_UNAVAILABLE),
    }
}

async fn join_competition_team_route(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<TeamRequest>,
) -> Result<Json<TeamResponse>, StatusCode> {
    if !authorized(&headers, &state) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    let pool = state
        .write_database
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;
    match join_team(pool, &payload).await {
        Ok(result) => Ok(Json(result)),
        Err(PublishError::Invalid) => Err(StatusCode::BAD_REQUEST),
        Err(PublishError::Forbidden) => Err(StatusCode::FORBIDDEN),
        Err(PublishError::Database) => Err(StatusCode::SERVICE_UNAVAILABLE),
    }
}

async fn freeze_competition_route(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<CompetitionFreezeRequest>,
) -> Result<Json<CompetitionFreezeResponse>, StatusCode> {
    if !authorized(&headers, &state) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    let pool = state
        .write_database
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;
    match set_frozen(pool, &payload).await {
        Ok(result) => Ok(Json(result)),
        Err(PublishError::Invalid) => Err(StatusCode::BAD_REQUEST),
        Err(PublishError::Forbidden) => Err(StatusCode::FORBIDDEN),
        Err(PublishError::Database) => Err(StatusCode::SERVICE_UNAVAILABLE),
    }
}

async fn persist_competition_transition_route(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<ManualTransitionRequest>,
) -> Result<Json<ManualTransitionResponse>, StatusCode> {
    if !authorized(&headers, &state) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    let pool = state
        .write_database
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;
    match persist_competition_transition(pool, &payload).await {
        Ok(result) => Ok(Json(result)),
        Err(PublishError::Invalid) => Err(StatusCode::BAD_REQUEST),
        Err(PublishError::Forbidden) => Err(StatusCode::FORBIDDEN),
        Err(PublishError::Database) => Err(StatusCode::SERVICE_UNAVAILABLE),
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let token =
        env::var("RUST_CORE_SHARED_TOKEN").expect("RUST_CORE_SHARED_TOKEN must be configured");
    assert!(
        token.len() >= 32 && !token.contains('\n'),
        "Rust core token must be at least 32 bytes"
    );
    let port: u16 = env::var("PORT").unwrap_or_else(|_| "8081".into()).parse()?;
    let database = match env::var("SECURITY_CORE_DATABASE_URL") {
        Ok(url) if !url.is_empty() => {
            let mut config = deadpool_postgres::Config::new();
            config.url = Some(url);
            config.pool = Some(deadpool_postgres::PoolConfig::new(8));
            Some(config.create_pool(
                Some(deadpool_postgres::Runtime::Tokio1),
                tokio_postgres::NoTls,
            )?)
        }
        _ => None,
    };
    let write_database = match env::var("SECURITY_CORE_WRITE_DATABASE_URL") {
        Ok(url) if !url.is_empty() => {
            let mut config = deadpool_postgres::Config::new();
            config.url = Some(url);
            config.pool = Some(deadpool_postgres::PoolConfig::new(4));
            Some(config.create_pool(
                Some(deadpool_postgres::Runtime::Tokio1),
                tokio_postgres::NoTls,
            )?)
        }
        _ => None,
    };
    let app = Router::new()
        .route("/health", get(health))
        .route("/ready", get(ready))
        .route("/v1/verify", post(verify))
        .route("/v1/score", post(calculate))
        .route("/v1/lab-transition", post(lab_transition))
        .route("/v1/authorization", post(authorization))
        .route("/v1/competition-transition", post(competition_transition))
        .route(
            "/v1/competitions/create",
            post(create_competition_record_route),
        )
        .route("/v1/competitions/edit", post(edit_competition_record_route))
        .route(
            "/v1/competitions/challenges/add",
            post(add_competition_challenge_route),
        )
        .route(
            "/v1/competitions/challenges/remove",
            post(remove_competition_challenge_route),
        )
        .route(
            "/v1/competitions/register",
            post(register_competition_participant_route),
        )
        .route(
            "/v1/competitions/unregister",
            post(unregister_competition_participant_route),
        )
        .route(
            "/v1/competitions/teams/create",
            post(create_competition_team_route),
        )
        .route(
            "/v1/competitions/teams/join",
            post(join_competition_team_route),
        )
        .route("/v1/competitions/freeze", post(freeze_competition_route))
        .route(
            "/v1/competitions/transition/persist",
            post(persist_competition_transition_route),
        )
        .route("/v1/catalog/query", post(challenge_catalog))
        .route("/v1/leaderboard", post(leaderboard))
        .route("/v1/challenges/publish", post(publish_challenge))
        .route("/v1/challenges/delete", post(delete_challenge))
        .route("/v1/challenges/edit", post(edit_challenge))
        .route("/v1/challenges/create", post(create_challenge))
        .route("/v1/submissions/incorrect", post(incorrect_submission))
        .route("/v1/submissions/correct", post(correct_submission))
        .layer(DefaultBodyLimit::max(64 * 1024))
        .with_state(AppState {
            token: Arc::new(token),
            database,
            write_database,
        });
    let listener = tokio::net::TcpListener::bind(SocketAddr::from(([0, 0, 0, 0], port))).await?;
    axum::serve(listener, app).await?;
    Ok(())
}
