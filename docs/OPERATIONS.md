# Operations & Deployment Runbook

Production-oriented notes for IIC CyberLab (Phase 7, PRD §47–§53).

## Deployment

Run the production stack (uses `docker-compose.prod.yml`, which overrides the dev
compose and publishes **only** Caddy ports 80/443):

```bash
# 1. Prepare a production .env from the template (fill REAL secrets)
cp .env.production.example .env

# 2. Boot the production stack
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

What production mode enforces automatically:

- `ENVIRONMENT=production` → FastAPI hides `/docs` & `/openapi.json` and the
  container refuses to boot on placeholder secrets (`python -m scripts.verify_config`).
- Non-root app users in both images (`appuser` / `node`).
- API served by uvicorn workers behind a Caddy reverse proxy that terminates TLS;
  the API, database, Redis and Keycloak never publish host ports.
- Lab instances run with per-instance CPU / memory / pid caps
  (`LAB_CPU_LIMIT`, `LAB_MEMORY_LIMIT_MB`, `LAB_PIDS_LIMIT`).

### Keycloak in production

Keycloak runs in `start` mode (not `start-dev`) with `KC_PROXY_HEADERS=xforwarded`
behind Caddy at `auth.example.org`. Update hostnames in `Caddyfile` and the
`/realms/cyberlab` URLs in `.env` to your real domain.

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