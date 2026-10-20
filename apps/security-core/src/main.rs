use axum::{
    extract::{DefaultBodyLimit, State},
    http::{HeaderMap, StatusCode},
    routing::{get, post},
    Json, Router,
};
use cyberlab_security_core::authorization::{
    authorize, AuthorizationRequest, AuthorizationResponse,
};
use cyberlab_security_core::{
    score, validate_lab_transition, verify_flag, LabTransitionRequest, LabTransitionResponse,
    ScoreRequest, ScoreResponse, VerifyFlagRequest, VerifyFlagResponse,
};
use std::{env, net::SocketAddr, sync::Arc};
use subtle::ConstantTimeEq;

#[derive(Clone)]
struct AppState {
    token: Arc<String>,
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

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let token =
        env::var("RUST_CORE_SHARED_TOKEN").expect("RUST_CORE_SHARED_TOKEN must be configured");
    assert!(
        token.len() >= 32 && !token.contains('\n'),
        "Rust core token must be at least 32 bytes"
    );
    let port: u16 = env::var("PORT").unwrap_or_else(|_| "8081".into()).parse()?;
    let app = Router::new()
        .route("/health", get(health))
        .route("/v1/verify", post(verify))
        .route("/v1/score", post(calculate))
        .route("/v1/lab-transition", post(lab_transition))
        .route("/v1/authorization", post(authorization))
        .layer(DefaultBodyLimit::max(4096))
        .with_state(AppState {
            token: Arc::new(token),
        });
    let listener = tokio::net::TcpListener::bind(SocketAddr::from(([0, 0, 0, 0], port))).await?;
    axum::serve(listener, app).await?;
    Ok(())
}
