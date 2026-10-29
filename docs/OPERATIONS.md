# Operations & Deployment Runbook

Production-oriented notes for IIC CyberLab (Phase 7, PRD §47–§53).

## Deployment

Run the production stack using `docker-compose.prod.yml`, which overrides the dev
compose and publishes **only** Caddy ports 80/443. On a fresh installation,
apply schema migrations and initialize the restricted Rust database roles
before starting the API and Rust service:

```bash
# 1. Prepare a production .env from the template (fill REAL secrets)
cp .env.production.example .env

# 2. Replace cyberlab.example.org/auth.example.org in the production Compose
#    file and Caddyfile, and in .env values such as CORS_ORIGINS.

# 3. Build the application images, then start the infrastructure services.
docker compose -f docker-compose.yml -f docker-compose.prod.yml build api security-core web celery-worker
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d postgres redis keycloak

# 4. Run Alembic migrations without triggering the API's Rust health dependency.
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm --no-deps api alembic upgrade head

# 5. Create or refresh the limited Rust read/write roles and grants.
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile maintenance run --rm security-core-role-init

# 6. Start the rest of the stack.
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Re-run step 5 after schema migrations that add or change fields accessed by
Rust, before restarting the Rust service. The production PostgreSQL bootstrap
creates the Keycloak database using `POSTGRES_USER` as its owner and skips the
developer-only `cyberlab_test` database. Changing `POSTGRES_USER` does not
rename roles inside an already initialized persistent PostgreSQL volume.
Existing volumes also retain any `cyberlab_test` database created before this
change; inspect those separately before deciding whether to remove them.

The frontend embeds `NEXT_PUBLIC_*` settings when `pnpm build` runs. Update
`web.build.args` and the matching `web.environment` values in the production
Compose file to the real public origins before building. Rebuild the web image
after any change to those public URLs; restarting a previously built image
cannot change the browser bundle.

What production mode enforces automatically:

- `ENVIRONMENT=production` → FastAPI hides `/docs` & `/openapi.json` and the
  container refuses to boot on placeholder secrets (`python -m scripts.verify_config`).
- Non-root app users in both images (`appuser` / `node`).
- API served by uvicorn workers behind a Caddy reverse proxy that terminates TLS;
  the API, database, Redis and Keycloak never publish host ports.
- Lab instances run with per-instance CPU / memory / pid caps
  (`LAB_CPU_LIMIT`, `LAB_MEMORY_LIMIT_MB`, `LAB_PIDS_LIMIT`).

### Keycloak in production

Keycloak runs in `start` mode with forwarded proxy headers and a strict public
hostname behind Caddy. Replace every example hostname in
`docker-compose.prod.yml`, `infrastructure/caddy/Caddyfile`, and the relevant
production `.env` values before deployment. Configure the public API, frontend
and Keycloak URLs consistently; changing `.env` alone does not change the
hardcoded production Compose or Caddy hostnames.

## Observability (PRD §47)

- Every request logs one JSON line (request id, method, path, status, duration).
- `GET /metrics` (root, Prometheus text) exposes HTTP counters/histograms and
  per-status lab instance gauges. Enable the bundled stack with:

  ```bash
  docker compose -f docker-compose.yml -f docker-compose.prod.yml \
                 -f infrastructure/monitoring/docker-compose.monitoring.yml \
                 up -d prometheus grafana
  ```

- Audit events (PRD §48) are recorded in the `audit_logs` table and viewable in
  the admin UI.

## Backups & disaster recovery (PRD §51–52)

What to back up: PostgreSQL (`cyberlab` + `keycloak`), configuration, challenge
definitions, and research artifacts. Lab instances are disposable — never back up
containers/VMs.

RPO/RTO (default, single-host): backups run on the host schedule; with an
off-host archives copy the expected RPO is one backup interval and RTO is the
time to `restore.sh` + `up -d --build` (~minutes).

```bash
./infrastructure/backup/backup.sh                 # writes archives/<timestamp>/
./infrastructure/backup/restore.sh archives/<ts>/ # restores cyberlab DB + config
```

Scheduled off-host copies (e.g. `rsync`/`restic` to a remote encrypted target)
are the operator's responsibility; rotate archives off-box.

## Range hardening checklist (PRD §75–78 / §50)

- ⬜ Per-user isolated bridge network per lab (enforced; no host ports published).
- ⬜ Lab CPU/mem/pids limits enforced by the Docker provider.
- ⬜ Expiration enforced both lazily (read-path) and by the background sweep task.
- ⬜ Per-session flags only ever stored hashed; submissions validate against the
      live session (ownership, running, not-expired).
- ⬜ API is the only holder of the Docker socket; production exposes no lab ports.
