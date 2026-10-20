# CyberLab Rust migration — October 20, 2026

## Current delivery

The existing IIC CyberLab project remains in `/cyberlab`. A new internal Rust service lives in `apps/security-core`, with a narrowly scoped Axum API:

- `GET /health`
- `POST /v1/verify`: SHA-256 flag verification with constant-time digest comparison, compatible with the existing trimmed-flag digest format
- `POST /v1/score`: deterministic standard, dynamic and first-blood calculations with bounded numeric inputs
- `POST /v1/lab-transition`: validates all lab-state transition arcs against the original state machine

The FastAPI integration is in `apps/api/app/core/rust_engine.py`. Production/dev Compose services use internal Docker DNS and a shared secret. Rust traffic is not exposed by a host port, and malformed or unavailable service responses cause an HTTP 503. When running FastAPI without a Rust URL, its original Python path remains available for standalone development.

This is a **Rust core migration, not a full backend rewrite**. FastAPI continues to run OIDC, RBAC, ORM, transactions, provisioning, competition APIs and research exports. The Next.js UI and PostgreSQL schema remain compatible.

## Verified defects corrected

- API production image virtualenv location now matches its PATH.
- API image health check now uses the actual `/api/v1/health` endpoint.
- The duplicate stale `/health` Caddy route was removed.
- Celery production deployment now overrides the dev image and source bind mount.
- Python fallback flag verification now uses `hmac.compare_digest`.
- The score-event creation now targets the actual SQLAlchemy `ScoreEvent` columns. Its first-solve rank is corrected for the already-committed submission.
- The VPN peer and score-event SQLAlchemy models now match the actual October migration columns.
- Scoring, score-event creation, and submission persistence are now a single transaction. A scoring error rolls back the submission.
- Lab launch, reset, and asynchronous provisioning now follow valid `provisioning → starting → running` transitions.
- Scoring recording failures no longer disappear behind a broad exception handler.

## Verification and setup

Verification on October 20, 2026: `cargo test --locked` (5 passed), `cargo fmt -- --check`, targeted Ruff lint, `uv run pytest -q` (147 passed), and `docker compose config --quiet` passed. A local Rust HTTP smoke test validated authentication, flags, scoring, and all 121 lab-state pairs. The Docker image itself has not been built or runtime-smoke-tested in this pass.

Set `RUST_CORE_SHARED_TOKEN` to a distinct random 32+ character value in the host `.env`; Compose supplies it to the API and Rust core. The Rust service is reached internally at `http://security-core:8081`. Restart both services together after rotating this token.

## Remaining work

The rest of FastAPI is still Python. A complete migration requires Rust implementations for identity validation, challenge CRUD, transactions, lab/VM provisioning, competition state changes, research APIs, and operations; API contract tests and production cutover must precede removal of Python services. Production container integration and browser-based end-to-end tests remain outstanding. The existing October 15 gap documents describe an earlier state and must be refreshed against current endpoints, since some listed missing modules now exist.
