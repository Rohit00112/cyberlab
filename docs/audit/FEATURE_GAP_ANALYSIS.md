# Feature Gap Analysis — IIC CyberLab

> Maps the target vision to existing implementation status.

## Classification Key

| Status | Meaning |
|---|---|
| ✅ Complete | Fully implemented and reusable |
| 🔧 Needs improvement | Functional but requires enhancement |
| 🚧 Incomplete | Partially implemented |
| ❌ Missing | Not implemented |
| 🗑️ Redundant | Dead code or superseded |

---

## A. CTF Hosting Platform

| Feature | Status | Notes |
|---|---|---|
| User registration via Keycloak | ✅ Complete | OIDC/PKCE flow, local DB sync |
| Authentication (JWT) | ✅ Complete | JWKS rotation, issuer verification |
| Authorization (RBAC) | ✅ Complete | 6 roles, granular permissions |
| Challenge browsing/filtering | ✅ Complete | Category, difficulty, search |
| Challenge detail page | ✅ Complete | Instructions, hints, lab panel |
| CTF competitions/events | ✅ Complete | Full lifecycle state machine |
| Team management | ✅ Complete | Create, join, per-competition |
| Flag submission (static) | ✅ Complete | SHA-256 hash verification |
| Flag submission (dynamic/lab) | ✅ Complete | Per-session lab flags |
| Static scoring | ✅ Complete | Base points − hint penalty |
| Dynamic scoring | ❌ Missing | No decay/solve-count-based scoring |
| Leaderboard | ✅ Complete | Global + competition-scoped |
| User progress/dashboard | ✅ Complete | Solves, points, skill profiles |
| Achievements/badges | ✅ Complete | Auto-grant on criteria |
| Admin challenge management | ✅ Complete | CRUD + publish workflow |
| Real-time machine status | 🔧 Needs improvement | Polling-based, no SSE/WebSocket |
| Competition status (real-time) | 🔧 Needs improvement | No live updates |
| Scoreboard freeze enforcement | 🚧 Incomplete | Field exists, query not filtered |
| MFA | 🚧 Incomplete | Keycloak supports it, not configured |
| Password reset | ✅ Complete | Via Keycloak |

## B. CTF Machine Builder and Generator

| Feature | Status | Notes |
|---|---|---|
| Machine template definitions | 🚧 Incomplete | YAML seeds with `lab_config` JSON, no structured builder |
| Reusable vulnerability templates | ❌ Missing | |
| Template versioning | 🚧 Incomplete | Single `version` int on Challenge |
| Image build pipeline | ❌ Missing | Images referenced by name only |
| Build validation | ❌ Missing | |
| Automated testing of builds | ❌ Missing | |
| Template approval workflow | ❌ Missing | Only draft→published status |
| Artifact management | ❌ Missing | |
| Challenge generation from templates | ❌ Missing | |
| Manifest format | ❌ Missing | YAML seeds exist but not structured manifests |

## C. On-Demand Machine Provisioning

| Feature | Status | Notes |
|---|---|---|
| Launch machine (Docker) | ✅ Complete | Per-user isolated network |
| Launch machine (Proxmox VMs) | 🔧 Needs improvement | Provider exists, needs testing |
| Launch machine (QEMU/KVM/Libvirt) | ❌ Missing | No libvirt provider |
| Stop machine | ✅ Complete | |
| Reset machine | ✅ Complete | Destroys + re-creates |
| Terminate machine | ✅ Complete | Admin only |
| Extend lease | ❌ Missing | |
| Connection details | 🔧 Needs improvement | Text hint only, no structured format |
| Machine status | ✅ Complete | Real-time provider query |
| Lab logs | ✅ Complete | Docker + Proxmox guest agent |
| Expiry enforcement | ✅ Complete | Background sweep + lazy check |
| Resource limits | ✅ Complete | CPU/memory/pids per container |
| Instance quota | ✅ Complete | Per-user max_instances |
| Background provisioning | ❌ Missing | Blocks API request |
| Idempotent launch | ❌ Missing | No dedup key |
| Compute node scheduling | ❌ Missing | Single host |
| Resource reservation | ❌ Missing | |
| Failure recovery | 🔧 Needs improvement | Error status set, no retry |
| Instance state machine | 🔧 Needs improvement | String statuses, no validated transitions |
| WireGuard VPN access | ❌ Missing | |
| Network isolation testing | ❌ Missing | |

## D. Infrastructure & Operations

| Feature | Status | Notes |
|---|---|---|
| Docker Compose (dev) | ✅ Complete | |
| Docker Compose (prod) | ✅ Complete | Caddy TLS, non-root |
| CI pipeline | ✅ Complete | lint + test + build |
| Structured logging | ✅ Complete | JSON + request IDs |
| Prometheus metrics | ✅ Complete | HTTP + lab gauges |
| Audit trail | ✅ Complete | Database table |
| Backup/restore | ✅ Complete | Scripts + docs |
| Alembic migrations | ✅ Complete | 14 incremental |
| Health endpoints | ✅ Complete | `/api/v1/health` |
| Background task queue (Celery) | ❌ Missing | asyncio loop only |
| Multi-worker deployment | 🔧 Needs improvement | 2 uvicorn workers, no task queue |
| Monitoring stack (Grafana) | 🚧 Incomplete | Compose file exists, not integrated |

---

## Priority Backlog

### P0 — Critical Vertical Slice (Login → Launch → Submit → Score)

| # | Task | Dependencies | Acceptance Criteria |
|---|---|---|---|
| 1 | Add QEMU/KVM Libvirt provider | Provider ABC | Can create/start/stop/destroy VMs via libvirt |
| 2 | Background provisioning with Celery | Redis | Lab launch returns 202, async worker provisions |
| 3 | Machine state machine | — | Validated transitions, no invalid state changes |
| 4 | Idempotent launch guard | Redis or DB lock | Duplicate launch returns existing instance |
| 5 | Lease extension API | — | PUT `/labs/{id}/extend` adds time |
| 6 | Dynamic scoring | — | Configurable decay-based scoring per challenge |
| 7 | Scoreboard freeze enforcement | — | Queries respect `frozen_at` timestamp |

### P1 — Machine Builder

| # | Task | Dependencies | Acceptance Criteria |
|---|---|---|---|
| 8 | MachineTemplate + Version models | Alembic | Templates versioned independently of Challenges |
| 9 | Machine template builder API | P8 | Admin CRUD for templates |
| 10 | Image build pipeline | P8 | Build image from template manifest |
| 11 | Template validation | P10 | Reject invalid configurations |
| 12 | Approval workflow | P8 | draft → review → approved → published |
| 13 | Challenge generation from template | P8 | Create challenges from approved templates |

### P2 — Network Security

| # | Task | Dependencies | Acceptance Criteria |
|---|---|---|---|
| 14 | WireGuard VPN service | — | Per-user/team peers, config download |
| 15 | Network isolation validation | P14 | Automated test: cross-tenant access denied |
| 16 | Management network protection | P14 | Labs cannot reach API/DB/Keycloak |

### P3 — Operational Excellence

| # | Task | Dependencies | Acceptance Criteria |
|---|---|---|---|
| 17 | Real-time updates (SSE) | — | Lab status pushes to frontend |
| 18 | Compute node inventory | — | Register/deregister hosts, capacity tracking |
| 19 | Resource reservation system | P18 | Reserve before provision, release on cleanup |
| 20 | E2E test suite | — | Playwright tests for critical workflows |
