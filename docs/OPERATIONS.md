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

### Proxmox template preparation (operator action, staging only)

The repository script `apps/api/scripts/proxmox_template.sh` must be copied to
and run **on the Proxmox node**, not on the Mac API host. It is a new-template
builder, not an in-place repair tool: choose a fresh numeric `PVMID` and an
approved isolated `PM_BRIDGE`. **Do not run it with an existing VMID** (in the
current lab, previous VMs `9000`, `108` and `111` were removed; staging VM
`9002` may already exist). Confirm the live cluster inventory, capacity,
storage and isolation first.

The host needs `guestfs-tools` (`virt-customize`), `qm`, `pvesm`, `ip`,
`curl` and `sha512sum`. Use an SSH public key as the temporary Cloud-Init login
method, or explicitly supply `PM_CI_PASS` for console login. With neither,
the script refuses to create a VM. Avoid inherited/static template passwords
for production labs; review or replace clone credentials as part of rollout.

```bash
# Run on the Proxmox node, from the folder containing the current script:
sudo PVMID=YOUR_UNUSED_VMID PM_BRIDGE=YOUR_ISOLATED_BRIDGE \
  PM_SSH_KEY=/root/.ssh/id_ed25519.pub \
  ./proxmox_template.sh
```

The script copies the upstream Debian cloud image before modifying it, bakes
in `qemu-guest-agent`, imports and resizes the disk, boots the unique VM, and
requires a successful `qm guest cmd <UNUSED_VMID> ping`. It waits for Cloud-Init,
clears per-instance Cloud-Init state, machine identity and SSH host keys via
the verified guest-agent channel, shuts down, then converts the VM to a
template. If any check fails, **no template is created**, and the newly
allocated VM is left available for manual, ownership-verified inspection; it
will not delete or overwrite another guest. Set `PM_IMAGE_SHA512` to a trusted
pinned image hash to validate the downloaded image; without one the script
warns, and its default image URL uses HTTPS.

Proxmox defaults to `ciupgrade=1`, which triggers `apt-get dist-upgrade` on
first boot. The builder explicitly sets `--ciupgrade 0` so isolated lab
networks without DHCP or package-mirror access do not fail Cloud-Init due to
automatic upgrades. This is **not** a substitute for patching the image in a
controlled build pipeline. For a previously failed staging VM, inspect
`cloud-init status --long` with `qm guest exec`, set `qm set <VMID> --ciupgrade 0`,
regenerate its Cloud-Init drive, and rerun Cloud-Init only on that disposable
VM before considering manual template conversion. Never retry the builder
against an existing VMID.

After a successful build, set `LAB_IMAGE` to the new template VMID in the API
configuration and run the read-only `scripts.proxmox_check` readiness check.
Only after the intended bridge, API token permissions and guest isolation are
verified should an operator opt into `scripts.proxmox_smoke --run`; that test
creates and then attempts to remove one owned disposable clone. Never run the
live smoke test as part of the normal Python unit suite.

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
