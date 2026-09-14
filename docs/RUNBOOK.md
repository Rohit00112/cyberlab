# CyberLab Operations Runbook

Comprehensive operational guide for running, maintaining, and troubleshooting CyberLab services.

---

## 1. Quick Architecture Reference

- **Backend API**: FastAPI (`apps/api`) running with Python 3.13 / Uvicorn
- **Frontend**: Next.js 14 (`apps/web`)
- **Database**: PostgreSQL 16 with async SQLAlchemy + Alembic migrations
- **Identity & Access**: Keycloak (`/realms/cyberlab`) with JWT verification
- **Lab Infrastructure**: Pluggable provider system (`docker`, `proxmox`, `fake`)
- **Recommendation Engine**: Multi-backend dispatcher (`rule`, `graph`, `gnn`)
- **Real-time Comms**: Server-Sent Events (SSE) for notifications & announcements

---

## 2. Lab Provider Operations

CyberLab uses a provider abstraction layer (`app.infrastructure.base.LabProvider`) allowing seamless switching between containerized labs and full virtual machines.

### 2.1 Configuration

Set the active provider in `.env`:

```bash
# Provider selection: "docker" (default), "proxmox", or "fake" (testing)
LAB_PROVIDER=docker

# Proxmox VE configuration (when LAB_PROVIDER=proxmox)
PROXMOX_ENDPOINT=https://pve.internal:8006
PROXMOX_USER=root@pam!cyberlab
PROXMOX_TOKEN_UUID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
PROXMOX_NODE=pve-node1
PROXMOX_STORAGE=local-lvm
PROXMOX_BRIDGE=vmbr1
PROXMOX_VERIFY_SSL=true
```

### 2.2 Proxmox VE Setup

When using Proxmox:
1. **Create API Token**: In Proxmox VE GUI, navigate to `Datacenter > Permissions > API Tokens`. Add token `cyberlab` for user with `PVEVMAdmin` role.
2. **Prepare Templates**: Create base VM templates with `qemu-guest-agent` installed and cloud-init enabled.
3. **Template VMIDs**: Specify template VMID in each challenge's `lab_config` JSON (e.g. `{"image": "9000", "expiry_minutes": 60}`).
4. **IP Discovery**: The provider polls the Proxmox QEMU Guest Agent for assigned IPv4 addresses on the internal bridge.

### 2.3 Inspecting and Debugging Labs

- **Real-Time Status**:
  ```bash
  curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/labs/{lab_id}/status
  ```
  Returns live provider state (`running`, `stopped`, CPU/memory info).

- **Log Streaming / Tailing**:
  ```bash
  curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/api/v1/labs/{lab_id}/logs?tail=50"
  ```
  Fetches recent stdout/stderr output from the Docker container or Proxmox console.

- **Manual Lab Expiry / Termination**:
  ```bash
  # Terminate and destroy specific lab (admin)
  curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/api/v1/labs/{lab_id}/terminate
  ```

---

## 3. Recommendation Engine Management

CyberLab supports three recommendation strategies selectable at runtime without code changes.

### 3.1 Backend Selection

Configure via `RECOMMENDATION_BACKEND` in `.env`:

```bash
# Options: "rule" (default baseline), "graph" (knowledge graph), "gnn" (trained neural model)
RECOMMENDATION_BACKEND=rule

# Model path for GNN inference:
GNN_MODEL_PATH=data/research/model/gnn.onnx
```

- **`rule`**: Heuristic scoring based on user competency gap and skill tag match.
- **`graph`**: Co-solve graph traversal and learning path sequence ordering.
- **`gnn`**: ONNX Runtime embeddings inference over challenge similarity graph.
- **Automatic Fallback**: If `graph` or `gnn` encounters an unhandled runtime error, the dispatcher automatically falls back to `rule` and tags the recommendation with `source="rule"`.

### 3.2 Checking Engine Health

Query the status endpoint:
```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/recommendations/status
```

Response format:
```json
{
  "active_backend": "gnn",
  "healthy": true,
  "model_path": "data/research/model/gnn.onnx",
  "detail": "Loaded ONNX model successfully"
}
```

### 3.3 Exporting Trained PyTorch GNN to ONNX

After retraining the research model:
```bash
uv run python research/export_model.py \
  --checkpoint checkpoints/gnn_best.pt \
  --output data/research/model/gnn.onnx \
  --embed-dim 32
```

Verify the exported model:
```bash
python -c "import onnx; model = onnx.load('data/research/model/gnn.onnx'); onnx.checker.check_model(model); print('Valid ONNX model!')"
```

### 3.4 Recommendation Analytics & Evaluation

Retrieve per-backend evaluation metrics (CTR, conversion rate, precision@k):
```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/api/v1/research/recommendations/insights
```

---

## 4. Competition Scheduler & Maintenance

The background maintenance loop (`app.services.maintenance.maintenance_loop`) runs periodically (default: every 60 seconds).

### 4.1 Automatic State Transitions

- **Scheduled → Live**: When `now >= competition.start_at`
- **Live → Finished**: When `now >= competition.end_at`

Manual state overrides can still be performed by faculty/admin via:
```bash
curl -X POST -H "Authorization: Bearer $FACULTY_TOKEN" http://localhost:8000/api/v1/competitions/{id}/status \
  -H "Content-Type: application/json" -d '{"status": "live"}'
```

### 4.2 Per-Event Analytics

Query competition performance and solve metrics:
```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/competitions/{id}/analytics
```
Returns:
- Total participants and active solvers
- Per-challenge solve rates and time-to-first-solve
- Score distribution histogram data

---

## 5. Notification & Announcement Operations

### 5.1 Real-Time Server-Sent Events (SSE)

Clients connect to the SSE stream to receive instant updates:
```bash
curl -N -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/notifications/stream
```

Events delivered:
- `event: connected` — initial handshake
- `event: notification` — JSON payload with new user or broadcast notifications
- `: keepalive` — heartbeat sent every 30s to keep HTTP connections alive

### 5.2 Publishing Announcements

Faculty or administrators can broadcast announcements:
```bash
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/api/v1/announcements \
  -H "Content-Type: application/json" \
  -d '{
    "title": "CTF Flag format update",
    "body": "Flags are formatted as cyberlab{...}. Please review your submissions.",
    "target": "all"
  }'
```

---

## 6. Incident Response & Troubleshooting

### Problem: Labs stuck in "provisioning" status
- **Cause**: Network creation failure, slow image pull, or container runtime timeout.
- **Remedy**:
  1. The maintenance sweep marks labs in provisioning for >10m as `error`.
  2. Verify Docker daemon / Proxmox VE network health.
  3. Pre-pull common challenge base images: `docker pull cyberlab/base-linux:latest`.

### Problem: GNN backend failing to score candidates
- **Cause**: Missing or incompatible ONNX model file at `GNN_MODEL_PATH`.
- **Remedy**:
  1. Check `GET /api/v1/recommendations/status` for error details.
  2. The system automatically falls back to `rule` based scoring so users will not experience disruption.
  3. Re-export model using `python research/export_model.py` or switch `RECOMMENDATION_BACKEND=rule`.

### Problem: SSE stream disconnects behind reverse proxy
- **Cause**: Proxy buffering SSE responses or timing out idle connections.
- **Remedy**:
  Ensure Caddy / Nginx has buffering disabled:
  - Header: `X-Accel-Buffering: no`
  - Flush interval: immediate
  - CyberLab's internal 30-second keepalive ping prevents idle timeouts.
