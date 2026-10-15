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

# Shared base VM template VMID cloned for every lab (numeric PVE template VMID)
LAB_IMAGE=9000
```

### 2.2 Proxmox VE Setup

When using Proxmox:

1. **Create API Token**: In Proxmox VE GUI, navigate to `Datacenter > Permissions > API Tokens`. Add token `cyberlab` for user with `PVEVMAdmin` role. Use the token's **UUID** as `PROXMOX_TOKEN_UUID`.
2. **Create storage** (if none exists): `Datacenter > Storage > Add > Directory` — e.g. storage ID `local-lvm` (LVM-Thin) or a directory storage. The configured `PROXMOX_STORAGE` must exist, otherwise clones fail.
3. **Create a Linux bridge**: `Datacenter > <node> > Network > Create > Linux Bridge`, e.g. `vmbr1` on the interface that reaches the CyberLab network. The configured `PROXMOX_BRIDGE` must exist on the node.
4. **Prepare a base template** (`qemu-guest-agent` installed, cloud-init enabled):
   - Create a VM with the Cloud-Init CPU type / assist, attach an ISO or imported disk, boot it, install the guest OS, install `qemu-guest-agent`, and enable it (`systemctl enable --now qemu-guest-agent`).
   - Add a cloud-init drive (`CloudInit Drive > Enable`), set a default IP config if desired, then **Convert to Template** (`Right-click VM > Convert to Template`).
   - Record the template's VMID.
5. **Point the API at the template**: all `docker`-type challenges fall back to the configured default image, so set
   `LAB_IMAGE=<template-vmid>` in `.env` (a numeric PVE template VMID, **not** a Docker image name like `alpine:3.20`). Per-challenge overrides are still possible via each challenge's `lab_config` JSON, e.g. `{"image": "9000", "expiry_minutes": 60}`.
6. **IP Discovery**: The provider polls the Proxmox QEMU Guest Agent for assigned IPv4 addresses, so the template must have `qemu-guest-agent` running and the VM attached to the configured bridge.

> **Plain-HTTP gotcha**: Proxmox answers on `https://` and returns empty-body `301/308` redirects for `http://` requests. Always set `PROXMOX_ENDPOINT=https://<host>:8006` (with `PROXMOX_VERIFY_SSL=false` for self-signed certs). A missing/mismatched bridge name or storage makes launches surface as `503 No such network/storage` errors.
>
> **Isolation note**: per-user isolated bridge networks are a Docker concept. On Proxmox, VMs attach to the shared configured bridge — use Proxmox SDN VLANs at the network level if per-user isolation is required.

### 2.3 Readiness Check & Automated Template Build

Two helper scripts ship in `apps/api/scripts/`:

- **`proxmox_check.py`** — run from anywhere the API `.env` is available to see exactly which PVE prerequisite is missing (endpoint/auth, node, storage, bridge, template VMID). Exits non-zero until everything passes:
  ```bash
  cd "$REPO_ROOT"           # so it reads the root .env
  apps/api/.venv/bin/python apps/api/scripts/proxmox_check.py
  ```
- **`proxmox_template.sh`** — run **on the PVE host as root** to build a cloud-init base template. It bakes `qemu-guest-agent` into a Debian cloud image **offline** with `virt-customize` (`apt install -y libguestfs-tools` first), imports it, attaches a cloud-init drive, and converts it to a template — no guest boot required:
  ```bash
  apt-get update && apt-get install -y libguestfs-tools
  sudo PVMID=9000 PM_STORAGE=local-lvm PM_BRIDGE=vmbr1 apps/api/scripts/proxmox_template.sh
  ```
  Then set `LAB_IMAGE=9000` in the API `.env` and restart the API. Customize via `PVMID`, `PM_STORAGE`, `PM_BRIDGE`, `PM_MEMORY`, `PM_CORES`, `PM_DISK_GB`, `PM_IMAGE_URL`, `PM_CI_USER`, `PM_CI_PASS`, `PM_SSH_KEY`.

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
