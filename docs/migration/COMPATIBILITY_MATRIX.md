# Compatibility Matrix — IIC CyberLab Migration

## API Endpoint Compatibility

| Endpoint | Current Behavior | Post-Migration Behavior | Compatibility |
|---|---|---|---|
| `GET /api/v1/health` | 200 OK | 200 OK (unchanged) | ✅ |
| `POST /api/v1/auth/callback` | OIDC callback | Unchanged | ✅ |
| `GET /api/v1/challenges` | List published | Unchanged | ✅ |
| `GET /api/v1/challenges/{slug}` | Detail view | Unchanged | ✅ |
| `POST /api/v1/challenges` | Create (admin) | Unchanged | ✅ |
| `PUT /api/v1/challenges/{id}` | Update (admin) | Unchanged | ✅ |
| `POST /api/v1/challenges/{id}/lab/launch` | 201 + LabOut (blocking) | 202 + LabOut (async) | ⚠️ See note 1 |
| `GET /api/v1/labs` | User's labs | + new states (QUEUED, etc.) | ✅ Additive |
| `POST /api/v1/labs/{id}/stop` | Stop container | Unchanged | ✅ |
| `POST /api/v1/labs/{id}/reset` | Reset container | Unchanged | ✅ |
| `POST /api/v1/labs/{id}/expire` | Expire lab | Unchanged | ✅ |
| `GET /api/v1/labs/{id}/status` | Provider query | + state machine info | ✅ Additive |
| `GET /api/v1/labs/{id}/logs` | Container logs | Unchanged | ✅ |
| `GET /api/v1/admin/labs` | All labs (admin) | + new states | ✅ Additive |
| `POST /api/v1/admin/labs/{id}/terminate` | Force expire | Unchanged | ✅ |
| `POST /api/v1/submissions/{challenge}/submit` | Flag check | Unchanged | ✅ |
| `GET /api/v1/leaderboard` | Global scores | Unchanged | ✅ |
| `GET /api/v1/competitions` | List | Unchanged | ✅ |
| All competition endpoints | Full lifecycle | Unchanged | ✅ |
| All skill/badge/path endpoints | Full feature set | Unchanged | ✅ |
| All research endpoints | Pseudonymized | Unchanged | ✅ |
| `GET /metrics` | Prometheus text | + new lab state gauges | ✅ Additive |

### Note 1: Lab Launch Status Code Change

**Before**: `POST /challenges/{id}/lab/launch` → `201 Created` (synchronous)
**After**: `POST /challenges/{id}/lab/launch` → `202 Accepted` (asynchronous)

**Mitigation**: Query parameter `?sync=true` restores blocking 201 behavior for existing clients.

## Database Compatibility

| Table | Change Type | Migration Approach |
|---|---|---|
| `users` | No changes | — |
| `challenges` | Add nullable `template_version_id` FK | Additive column |
| `submissions` | No changes | — |
| `lab_instances` | New status values | Existing values remain valid |
| `competitions` | No changes | — |
| `competition_*` | No changes | — |
| `teams` / `team_members` | No changes | — |
| `badges` / `user_badges` | No changes | — |
| `skills` / `challenge_skills` | No changes | — |
| `learning_paths` / `steps` | No changes | — |
| `audit_logs` | No changes | — |
| `notifications` | No changes | — |
| `research_*` | No changes | — |
| `machine_templates` | **New table** | Alembic migration |
| `machine_template_versions` | **New table** | Alembic migration |
| `provisioning_jobs` | **New table** | Alembic migration |
| `compute_nodes` | **New table** | Alembic migration |
| `resource_reservations` | **New table** | Alembic migration |
| `vpn_peers` | **New table** | Alembic migration |
| `score_events` | **New table** | Alembic migration |

## Frontend Compatibility

| Component | Change | Compatibility |
|---|---|---|
| Auth flow | Unchanged | ✅ |
| Challenge browser | Unchanged | ✅ |
| Lab panel | Enhanced (SSE, progress) | ✅ Backward compat |
| Leaderboard | + freeze indicator | ✅ Additive |
| Admin pages | + template builder | ✅ New routes |
| Dashboard | Unchanged | ✅ |

## Configuration Compatibility

| Variable | Status | Notes |
|---|---|---|
| `DATABASE_URL` | Unchanged | ✅ |
| `REDIS_URL` | Unchanged | ✅ Used by Celery too |
| `OIDC_*` | Unchanged | ✅ |
| `LAB_PROVIDER` | Extended | + `libvirt` option |
| `LAB_*` | Unchanged | ✅ |
| `PROXMOX_*` | Unchanged | ✅ |
| `CELERY_BROKER_URL` | **New** | Defaults to `REDIS_URL` |
| `WIREGUARD_*` | **New** | Only needed when VPN enabled |
| `LIBVIRT_URI` | **New** | Only when `LAB_PROVIDER=libvirt` |
