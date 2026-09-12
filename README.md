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

## Phases

1. **Platform MVP** (current): auth, RBAC, challenges, submissions, scoring, leaderboard
2. **Cyber Range**: Docker/VM labs, provisioning, isolation, expiration
3. **Competition platform**
4. **Skill intelligence**
5. **Adaptive learning**
6. **Research platform**