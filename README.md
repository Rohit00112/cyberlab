# IIC CyberLab

**Learn. Practice. Compete. Defend.**

Intelligent Cybersecurity Training, Simulation, Competition & Skill Analytics Platform for Itahari International College.

Source of truth: [`IIC_CyberLab_Proposal_PRD.md`](./IIC_CyberLab_Proposal_PRD.md).

## Stack

| Layer | Technology |
|---|---|
| Web | Next.js (App Router), React, TypeScript, Tailwind, shadcn/ui |
| API | Python, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic |
| Data | PostgreSQL 16, Redis 7 |
| Identity | Keycloak (OIDC, realm `cyberlab`) |
| Labs | Docker (Phase 2+, via `LabProvider` abstraction) |

## Getting started

```bash
# 1. Start Docker Desktop, then:
cp .env.example .env

# 2. Boot the full stack (postgres, redis, keycloak, api, web)
docker compose up --build

# 3. Seed the database schema (first run only)
docker compose exec api uv run alembic upgrade head
```

| Service | URL |
|---|---|
| Web app | http://localhost:3000 |
| API docs | http://localhost:8000/docs |
| Keycloak admin | http://localhost:8080/admin |
| Postgres | localhost:5432 (cyberlab / cyberlab) |

### Seeded accounts (Keycloak realm `cyberlab`)

| Username | Password | Roles |
|---|---|---|
| `admin` | `admin` | sysadmin, faculty |
| `faculty` | `faculty` | faculty |
| `labadmin` | `labadmin` | lab_admin |
| `student` | `student` | student |

> Dev-only credentials. Change before any production use.

### Challenge catalogue

Challenge definitions live as YAML in [`challenges/`](./challenges/) — one file per category,
21 challenges covering all 10 categories. Seed them against the running API (idempotent on slug):

```bash
docker compose exec api uv run python -m scripts.seed_challenges
```

## Repository layout

```text
apps/web/      Next.js frontend
apps/api/      FastAPI backend + Alembic migrations
infrastructure/  docker, keycloak realm, lab images
challenges/      seed challenge definitions
docs/           architecture decisions, security notes
```

## Development workflow

- Compose runs the API with `--reload` and the web app with `next dev`; both hot-reload on save.
- Backend deps are managed with `uv` (see `apps/api/pyproject.toml`).
- Migrations: `docker compose exec api uv run alembic revision --autogenerate -m "..."`.
- Tests: `docker compose exec api uv run pytest`.
- Lint: `uv run ruff check app scripts tests` (API) and `pnpm lint && pnpm exec tsc --noEmit` (web).

## Feature map

User-facing surface (all gated by RBAC):

| Area | Pages |
|---|---|
| Challenges | `/challenges`, `/challenges/[slug]` (hints, scoring, per-session lab flags) |
| Labs | `/labs` + embedded `LabPanel` on challenge detail (launch/stop/reset/expire) |
| Skills & badges | `/skills` (per-skill progress, evidence, badges) |
| Learning paths | `/paths`, `/paths/[id]`, admin at `/admin/paths` |
| Recommendations | "Recommended for you" on `/dashboard` |
| Faculty analytics | `/analytics` (summary, skills, per-challenge difficulty) + `/analytics/students/[id]` drill-down |
| Competitions | `/competitions`, `/admin/competitions` |
| Admin | challenges, labs, users, audit trail |

Lab-flagged challenges: each running lab receives a unique per-session flag written to
its filesystem (default `/flag.txt`). The API stores only the SHA-256 hash; submissions may
optionally carry `lab_id`, forcing validation against that live session's flag and rejecting
stale/foreign/non-running sessions.

## Phases

1. **Platform MVP** (done): auth, RBAC, challenges, submissions, scoring, leaderboard
2. **Cyber Range** (done): Docker labs, provisioning, isolation, expiration, per-session flags
3. **Competition platform** (done): challenges, teams, standings
4. **Skill intelligence** (done): skill profiles, badges, faculty analytics
5. **Adaptive learning** (done): recommendations, learning paths, per-challenge difficulty
6. **Research platform** (not started)