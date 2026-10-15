# Existing System Audit — IIC CyberLab

> Generated from repository inspection on 2026-10-15.

## 1. Technology Stack

| Layer | Technology | Version / Notes |
|---|---|---|
| **Backend Framework** | FastAPI | ≥0.115, Python 3.13 |
| **ORM / DB** | SQLAlchemy 2 (async) + Alembic | asyncpg, PostgreSQL 16 |
| **Cache / State** | Redis 7 | append-only persistence |
| **Identity** | Keycloak 26.1 | OIDC realm `cyberlab`, `web` (PKCE) + `api` (confidential) clients |
| **Frontend** | Next.js 16.3, React 19, TypeScript, Tailwind CSS 4, shadcn/ui | pnpm 11 |
| **Containerisation** | Docker Compose (dev + prod profiles) | Caddy reverse proxy in prod |
| **CI** | GitHub Actions (`ci.yml`) | ruff lint, pytest (≥50% coverage), eslint, tsc, next build |
| **Package Management** | uv (API), pnpm (Web) | Lock files present |

## 2. Project Structure

```
apps/api/          FastAPI backend (app/, tests/, scripts/, alembic/, research/)
apps/web/          Next.js frontend (app/, components/, lib/)
infrastructure/    docker init, keycloak realm/themes, caddy, monitoring, backup
challenges/        10 YAML category files (21 challenges)
data/research/     pseudonymized exports (volume-mounted)
docs/              ARCHITECTURE.md, OPERATIONS.md, RUNBOOK.md
```

## 3. Backend Module Inventory

### 3.1 API Routes (21 routers)
| Router | Prefix | Status |
|---|---|---|
| health | `/api/v1` | ✅ Complete |
| auth | `/api/v1` | ✅ Complete |
| users | `/api/v1` | ✅ Complete |
| challenges | `/api/v1` | ✅ Complete |
| submissions | `/api/v1` | ✅ Complete |
| hints | `/api/v1` | ✅ Complete |
| labs | `/api/v1` | ✅ Complete |
| leaderboard | `/api/v1` | ✅ Complete |
| badges | `/api/v1` | ✅ Complete |
| skills | `/api/v1` | ✅ Complete |
| paths | `/api/v1` | ✅ Complete |
| recommendations | `/api/v1` | ✅ Complete |
| competitions | `/api/v1` | ✅ Complete |
| notifications | `/api/v1` | ✅ Complete |
| audit | `/api/v1` | ✅ Complete |
| research | `/api/v1` | ✅ Complete |
| metrics | `/metrics` | ✅ Complete |

### 3.2 Database Models (14 migration files, 14+ models)

| Model | Table | Status |
|---|---|---|
| User | `users` | ✅ Keycloak-sub keyed, roles JSON |
| Challenge | `challenges` | ✅ Full schema incl. lab_config, difficulty_score |
| Submission | `submissions` | ✅ Partial unique index on correct solves |
| LabInstance | `lab_instances` | ✅ Provider-aware (docker/proxmox/fake) |
| Competition | `competitions` | ✅ Full lifecycle state machine |
| CompetitionChallenge | `competition_challenges` | ✅ Junction table |
| CompetitionParticipant | `competition_participants` | ✅ With optional team_id |
| Team | `teams` | ✅ Competition-scoped |
| TeamMember | `team_members` | ✅ Role-aware |
| Badge / UserBadge | `badges`, `user_badges` | ✅ Complete |
| Skill / ChallengeSkill | `skills`, `challenge_skills` | ✅ Complete |
| UserSkillProfile | `user_skill_profiles` | ✅ Per-skill tracking |
| LearningPath / Step | `learning_paths`, `learning_path_steps` | ✅ Sequential unlock |
| HintReveal | `hint_reveals` | ✅ Penalty tracking |
| AuditLog | `audit_logs` | ✅ Event logging |
| Notification / Announcement | `notifications`, `announcements` | ✅ Complete |
| ResearchDataset / Experiment / RecommendationLog | `research_*` | ✅ Complete |

### 3.3 Services (18 service modules)

| Service | Lines | Status | Notes |
|---|---|---|---|
| labs.py | 524 | ✅ Functional | Provider abstraction, per-session flags, expiry |
| submissions.py | 392 | ✅ Complete | Flag verification, scoring, leaderboard, analytics |
| competitions.py | 957 | ✅ Complete | Full lifecycle, team scoring, auto-transition |
| skills.py | ~700 | ✅ Complete | Skill profiles, evidence, analytics |
| badges.py | ~400 | ✅ Complete | Auto-granting after solve |
| challenges.py | ~250 | ✅ Complete | CRUD + publish workflow |
| users.py | ~400 | ✅ Complete | Sync from Keycloak, RBAC, audit |
| recommendations.py | ~200 | ✅ Complete | Multi-backend (rule/graph/GNN) |
| research.py | ~1000 | ✅ Complete | Pseudonymized exports, knowledge graph |
| notifications.py | ~180 | ✅ Complete | In-app notifications |
| maintenance.py | 47 | ✅ Complete | Background sweep loop |
| learning_paths.py | ~160 | ✅ Complete | Sequential paths |

### 3.4 Infrastructure Providers

| Provider | Status | Notes |
|---|---|---|
| Docker (`DockerLabProvider`) | ✅ **Production-ready** | Raw unix socket HTTP, resource limits, per-user network |
| Proxmox (`ProxmoxLabProvider`) | ⚠️ **Functional, needs testing** | Clone + cloud-init, guest agent IP polling |
| Fake (`FakeLabProvider`) | ✅ **Complete** | In-memory for tests/CI |
| Factory + base ABC | ✅ **Well-designed** | Clean provider interface |

### 3.5 Authentication & Authorization

| Component | Status | Notes |
|---|---|---|
| OIDC JWT verification | ✅ Complete | Keycloak JWKS with rotation handling |
| RBAC | ✅ Complete | 6 roles, granular permissions, wildcard for sysadmin |
| Dependency injection | ✅ Complete | `get_current_user`, `require_permission`, `current_user_or_none` |
| User sync | ✅ Complete | Keycloak → local DB on each request |

### 3.6 Tests (26 test files)

| Area | Count | Status |
|---|---|---|
| Challenge CRUD | 1 | ✅ |
| Submissions/Scoring | 1 | ✅ |
| Labs lifecycle | 2 | ✅ |
| Lab providers | 1 | ✅ |
| Badges | 1 | ✅ |
| Competition scheduler | 1 | ✅ |
| Analytics | 1 | ✅ |
| Recommendations | 2 | ✅ |
| Research | 1 | ✅ |
| Users / Permissions | 2 | ✅ |
| Health / Metrics / Logging | 3 | ✅ |
| Rate limiting | 1 | ✅ |
| Hints | 1 | ✅ |
| Notifications | 1 | ✅ |
| Maintenance | 1 | ✅ |
| Adaptive/Learning paths | 2 | ✅ |

Coverage target: ≥50% (CI-enforced).

### 3.7 Frontend Pages

| Section | Routes | Status |
|---|---|---|
| Landing | `/` | ✅ |
| Dashboard | `/dashboard` | ✅ |
| Challenges | `/challenges`, `/challenges/[slug]` | ✅ |
| Labs | `/labs`, embedded `LabPanel` | ✅ |
| Competitions | `/competitions` | ✅ |
| Leaderboard | `/leaderboard` | ✅ |
| Skills | `/skills` | ✅ |
| Badges | `/badges` | ✅ |
| Paths | `/paths`, `/paths/[id]` | ✅ |
| Research | `/research` | ✅ |
| Profile | `/profile` | ✅ |
| Portfolio | `/portfolio` | ✅ |
| Analytics (admin) | `/analytics` | ✅ |
| Admin (8 sub-pages) | `/admin/*` | ✅ |

## 4. Strengths

1. **Clean architecture**: Well-separated layers (routes → services → models → infrastructure)
2. **Provider abstraction**: `LabProvider` ABC with factory pattern — already supports Docker, Proxmox, Fake
3. **Per-session flags**: Dynamic `IIC{lab-<hex>}` per container, only hash stored — good security
4. **Comprehensive RBAC**: 6 roles, permission-based authorization, wildcard for sysadmin
5. **Good test coverage**: 26 test files covering all major subsystems
6. **Alembic migrations**: 14 incremental, reversible migrations
7. **Production compose**: Caddy TLS, non-root containers, secret validation
8. **Observability**: JSON logs, Prometheus `/metrics`, audit trail
9. **Modern stack**: Python 3.13, Next.js 16, React 19, Tailwind 4, shadcn/ui
10. **Research platform**: Pseudonymized data governance, offline ML pipeline

## 5. Weaknesses & Gaps

### Critical
1. **No QEMU/KVM/Libvirt provider** — only Docker (containers) and Proxmox (external API)
2. **No machine template builder** — challenges defined as YAML seeds, no admin UI builder
3. **No machine image build pipeline** — images referenced by name, no build/validation workflow
4. **Synchronous provisioning** — lab launch blocks the API request (no background job queue)
5. **No WireGuard/VPN access** — labs reachable only through API, no direct network access for students
6. **No compute node scheduling** — single Docker host, no multi-node awareness
7. **No resource reservation system** — concurrent launches may overcommit

### Important
8. **No Celery/Dramatiq** — background work is an `asyncio.Event` loop in the API process
9. **No idempotency controls** — duplicate launch requests not guarded
10. **Limited state machine** — lab states are string literals, no validated transitions
11. **No lease extension** — labs can only be expired/reset, not extended
12. **No dynamic scoring** — fixed points minus hint penalty only
13. **No challenge versioning** — single `version` int, no immutable template versions
14. **No scoreboard freeze/unfreeze** at competition-level (field exists, not enforced in queries)
15. **No MFA** — Keycloak supports it, but not configured/documented

### Minor
16. **Flag storage**: SHA-256 without salt (acceptable for CTF flags, noted)
17. **Rate limiting**: Redis-based sliding window exists but not applied to all endpoints
18. **Metrics cardinality**: Raw URL paths in Prometheus labels (noted in code comments)
19. **No E2E tests**: Only unit/integration tests, no Playwright/Cypress
20. **Docker socket exposure**: API container gets Docker socket (documented risk)
