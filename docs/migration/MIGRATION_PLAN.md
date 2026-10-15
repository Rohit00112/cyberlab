# Migration Plan — IIC CyberLab

## Guiding Principles

1. **Incremental**: Each step produces a working system
2. **Non-destructive**: Existing data preserved via Alembic migrations  
3. **Backward-compatible**: Existing API endpoints remain functional
4. **Testable**: Each step has acceptance criteria and automated tests

---

## Phase 1: Core Infrastructure (Week 1–2)

### 1.1 Add Celery + Background Worker
- Add `celery` to `pyproject.toml` dependencies
- Create `app/worker.py` with Celery app configuration
- Create `app/tasks/` package for task definitions
- Move `lab_maintenance_loop` to a Celery periodic task
- Add `celery-worker` service to `docker-compose.yml`
- **Keep existing asyncio loop as fallback** until Celery is verified

### 1.2 Lab Instance State Machine
- Create `app/core/states.py` with validated state transitions
- States: QUEUED → PROVISIONING → STARTING → RUNNING → STOPPING → STOPPED → RESETTING → TERMINATING → TERMINATED → FAILED → EXPIRED
- Add transition validation to lab service
- **Migration**: Existing `status` values map directly (provisioning→PROVISIONING, running→RUNNING, stopped→STOPPED, error→FAILED, expired→EXPIRED)

### 1.3 Background Lab Provisioning
- Create `app/tasks/provisioning.py` with `provision_lab_task`
- Modify `launch_lab()` to return 202 with job ID instead of blocking
- Add polling endpoint `GET /labs/{id}` (already exists, enhanced)
- Add SSE endpoint `GET /labs/{id}/events` for push updates
- **Backward compat**: Add query param `?sync=true` for blocking behavior during migration

### 1.4 Idempotent Launch Guard
- Add unique constraint on (user_id, challenge_id, status IN active_statuses)
- Check for existing active instance before creating new one
- Return existing instance if already provisioning/running

---

## Phase 2: QEMU/KVM Provider (Week 2–3)

### 2.1 Libvirt Provider Implementation
- Create `app/infrastructure/libvirt_provider.py`
- Implement all `LabProvider` ABC methods using `libvirt-python`
- Support: VM creation from qcow2 images, network attachment, resource allocation
- Register in factory with `LAB_PROVIDER=libvirt`

### 2.2 Enhanced Provider Interface
- Add `reset_lab()` to ABC (currently done at service level)
- Add `readiness_check()` for service health verification
- Add `get_resource_usage()` for capacity tracking
- **Backward compat**: Default implementations in ABC for existing providers

---

## Phase 3: Machine Template System (Week 3–4)

### 3.1 Database Models
- Create `MachineTemplate` model (slug, title, OS, arch, base_image, services, resources)
- Create `MachineTemplateVersion` model (immutable snapshot, build artifacts, hash)
- Alembic migration (additive, no changes to existing tables)
- Add `template_version_id` FK to `challenges` (nullable, backward compat)

### 3.2 Template API
- CRUD endpoints under `/api/v1/admin/templates`
- Version creation endpoint
- Approval workflow (draft → review → approved → published)
- Template validation endpoint

### 3.3 Challenge-Template Link
- Challenges can optionally reference a template version
- Lab launch resolves image from template version when linked
- Existing challenges with `lab_config.image` continue to work unchanged

---

## Phase 4: Dynamic Scoring (Week 4)

### 4.1 Scoring Engine
- Create `app/services/scoring.py` with pluggable scoring backends
- Implement: static, dynamic (decay-based), first-blood bonus
- Add `scoring_mode` to Competition (already exists in model)
- Create `ScoreEvent` model for granular score history

### 4.2 Scoreboard Freeze
- Enforce `frozen_at` in leaderboard queries
- Add admin endpoint to freeze/unfreeze
- Show frozen indicator in frontend

---

## Phase 5: WireGuard VPN (Week 5)

### 5.1 VPN Peer Management
- Create `VPNPeer` model (user_id, public_key, allowed_ips, expires_at)
- Create `app/services/vpn.py` for peer lifecycle
- API endpoints for config generation and download

### 5.2 WireGuard Gateway
- Container/service running WireGuard
- Dynamic peer configuration via API calls
- Routing to lab networks only

---

## Phase 6: Frontend Enhancements (Week 5–6)

### 6.1 Real-time Lab Status
- SSE client hook for lab provisioning progress
- Live status updates on machine detail page
- Provisioning progress indicator

### 6.2 Machine Template Builder (Admin)
- Template CRUD pages under `/admin/templates`
- Version management UI
- Approval workflow UI

### 6.3 Enhanced Machine Detail Page
- Structured connection info (IP, ports, credentials)
- Remaining time with live countdown
- Extend lease button
- VPN config download

---

## Database Migration Strategy

All migrations are:
- **Additive**: New tables and nullable columns only
- **Reversible**: Alembic downgrade supported
- **Data-preserving**: No existing records modified

### Migration Order
1. Add `machine_templates` + `machine_template_versions` tables
2. Add `template_version_id` to `challenges` (nullable FK)
3. Add `provisioning_jobs` table
4. Add `compute_nodes` + `resource_reservations` tables
5. Add `vpn_peers` table
6. Add `score_events` table
7. Extend `lab_instances` with new state values + indexes

---

## Compatibility Matrix

| API Endpoint | Before | After | Breaking? |
|---|---|---|---|
| POST `/challenges/{id}/lab/launch` | Returns 201 + LabOut | Returns 202 + LabOut (status=QUEUED) | ⚠️ Status code change; add `?sync=true` |
| GET `/labs` | Returns running/stopped/etc | Returns all states incl. QUEUED | No (additive) |
| GET `/labs/{id}/status` | Provider query | Provider query + state machine | No |
| POST `/labs/{id}/stop` | Unchanged | Unchanged | No |
| POST `/labs/{id}/reset` | Unchanged | Unchanged | No |
| All other endpoints | Unchanged | Unchanged | No |

### New Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/labs/{id}/events` | SSE stream for lab status |
| PUT | `/labs/{id}/extend` | Extend lease duration |
| GET/POST | `/admin/templates` | Template CRUD |
| GET/POST | `/admin/templates/{id}/versions` | Version management |
| POST | `/admin/templates/{id}/approve` | Approval workflow |
| GET | `/vpn/config` | Download WireGuard config |
| GET | `/competitions/{id}/scoreboard` | Enhanced with freeze support |
