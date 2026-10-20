# CyberLab Rust migration — October 20, 2026

## Current delivery

The existing IIC CyberLab project remains in `/cyberlab`. A new internal Rust service lives in `apps/security-core`, with a narrowly scoped Axum API:

- `GET /health`
- `POST /v1/verify`: SHA-256 flag verification with constant-time digest comparison, compatible with the existing trimmed-flag digest format
- `POST /v1/score`: deterministic standard, dynamic and first-blood calculations with bounded numeric inputs
- `POST /v1/lab-transition`: validates all lab-state transition arcs against the original state machine
- `POST /v1/authorization`: expands Keycloak realm roles into permissions and checks access using Rust RBAC rules
- `POST /v1/competition-transition`: validates organizer actions and time-based competition lifecycle changes in Rust
- `POST /v1/catalog/query`: pooled PostgreSQL query returning filtered, paginated challenge IDs and counts; students are restricted to published challenges
- `POST /v1/leaderboard`: pooled PostgreSQL global leaderboard aggregation, ordered by points and earliest correct solve

The FastAPI integration is in `apps/api/app/core/rust_engine.py`. Production/dev Compose services use internal Docker DNS and a shared secret. Rust traffic is not exposed by a host port, and malformed or unavailable service responses cause an HTTP 503. When running FastAPI without a Rust URL, its original Python path remains available for standalone development.

This is a **Rust core migration, not a full backend rewrite**. FastAPI continues to validate Keycloak OIDC tokens and run ORM, transactions, provisioning, competition APIs and research exports; Rust evaluates role-based permissions when configured. The Next.js UI and PostgreSQL schema remain compatible.

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
- Role-based permission expansion and checks in API dependencies, challenge visibility, lab administration and research ownership use Rust when the internal core is configured. The Python permission policy remains available for standalone development. Rust outages fail closed with HTTP 503.

## Verification and setup

Verification on October 20, 2026: `cargo test --locked` (5 passed), `cargo fmt -- --check`, targeted Ruff lint, `uv run pytest -q` (147 passed), and `docker compose config --quiet` passed. A local Rust HTTP smoke test validated authentication, flags, scoring, and all 121 lab-state pairs. The Docker image itself has not been built or runtime-smoke-tested in this pass.

Next Rust RBAC slice verification: `cargo test --locked` (8 passed), `cargo clippy --all-targets -- -D warnings`, targeted Ruff lint, authorization regression tests, and 286 Rust/Python RBAC permission-decision parity checks. The parity check is automated in GitHub Actions with `apps/security-core/tools/check_policy_parity.py`.

Competition lifecycle slice: organizer transitions and scheduled start/finish decisions now use Rust when configured, while FastAPI retains database transactions, audit events and badge awards. Checks included 12 Rust tests, 12 new database/policy Python tests, 164 backend tests overall, and 378 live Rust/Python competition decisions across action and time boundaries. The parity check runs in CI through `apps/security-core/tools/check_competition_parity.py`. Repository-wide Ruff lint was also corrected and passed.

Set `RUST_CORE_SHARED_TOKEN` to a distinct random 32+ character value in the host `.env`; Compose supplies it to the API and Rust core. The Rust service is reached internally at `http://security-core:8081`. Restart both services together after rotating this token.

PostgreSQL catalog slice: Rust now queries challenge IDs and totals through a read-only repeatable-read transaction; FastAPI retains response formatting and checks visibility again after hydration. The database URL is supplied internally in development/production Compose as `SECURITY_CORE_DATABASE_URL`. Validation included 14 Rust tests, focused Python integration tests and a live PostgreSQL-backed Rust HTTP smoke query. Full role-based Rust-mode browser integration and production image checks remain outstanding.

Global leaderboard slice: Rust now aggregates correct submissions and rank ordering with a bounded query; FastAPI retains the public leaderboard route and its permission dependency. Challenge catalog pagination also gained a deterministic ID tie-break, and challenge creation/updates reject direct publication to enforce the dedicated publish workflow. The full Rust-mode HTTP+PostgreSQL leaderboard parity and production image checks remain to be completed.

October 20 integration verification: `apps/api/tests/test_rust_live_database.py` adds an opt-in end-to-end Rust/PostgreSQL parity check that creates a unique temporary database, seeds users, correct and incorrect submissions plus draft/published challenges, runs the real Rust binary over loopback HTTP, and checks Python/Rust leaderboard results, challenge page IDs/counts, publication visibility and API responses. It also verifies that unauthenticated calls and invalid limits are rejected. The temporary database is dropped at the end, without changing `cyberlab` or `cyberlab_test`. To run locally:

```bash
cd apps/security-core
CARGO_TARGET_DIR=/tmp/cyberlab-rust-parity-target cargo build --locked
cd ../api
RUN_RUST_DB_INTEGRATION=1 RUST_CORE_TEST_BINARY=/tmp/cyberlab-rust-parity-target/debug/cyberlab-security-core uv run pytest -q tests/test_rust_live_database.py
```

This test is opt-in to avoid assuming every CI job has a compiled Rust binary and database creation privileges. Python leaderboard ranking now uses a deterministic user-ID tie-break matching the Rust query. Full production image and browser validation remain outstanding.

## Remaining work

October 20 follow-up hardening (changes pending end-to-end production verification): the Rust core now provides `GET /ready` which checks a PostgreSQL connection with a two-second timeout, while `GET /health` remains a lightweight liveness probe. Docker and Compose health checks now target readiness so API dependencies do not start against a Rust process unable to query its database. The CI API job builds the Rust binary and runs the isolated Rust/PostgreSQL parity test; the web job's pnpm version is aligned with `apps/web/package.json`. The production Compose override now runs the standalone Next.js server and removes inherited development bind mounts/anonymous dependency volumes from API and web, preserving only necessary API data/socket mounts. The production Keycloak command imports the bundled realm on a fresh database; Caddy no longer configures `example.org` as an unintended admin API bind address. These changes require actual production-image and container-network verification before being considered deployed. The API/Celery Docker socket remains a privileged integration that needs isolation before public production deployment. Rust's production PostgreSQL credentials also need a dedicated restricted read-only role.

Follow-up verification: a native Rust production Docker image was built successfully (`cyberlab-security-core:verification`) using the Rust 1.90 builder and Debian slim runtime, with a non-root `cyberlab` runtime user. Starting the image under Compose has **not** been validated: Docker Desktop subsequently stopped accepting daemon connections (`Cannot connect to the Docker daemon`). Rust-mode database/API parity passed using the native binary but is not proof of container-to-container connectivity. The FastAPI Rust adapter additionally rejects unexpected ports for the `security-core` hostname, with regression tests preventing attempts to send the shared token to untrusted destinations. Complete production Compose startup, frontend/browser flows, WireGuard provisioning, container isolation and a restricted DB role remain pending.

The rest of FastAPI is still Python. A complete migration requires Rust implementations for identity validation, challenge CRUD, database transactions, lab/VM provisioning, competition persistence and leaderboards, research APIs, and operations; API contract tests and production cutover must precede removal of Python services. Production container integration and browser-based end-to-end tests remain outstanding. The existing October 15 gap documents describe an earlier state and must be refreshed against current endpoints, since some listed missing modules now exist.
