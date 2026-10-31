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

### Proxmox endpoint accessible only over IPv6

If a Proxmox hostname works with `curl -6` but hangs with `curl -4`, the API
container may be selecting an unusable IPv4 route. CyberLab normally uses the
default dual-stack-capable HTTPX behavior and an IPv4 Compose bridge. The
optional `docker-compose.proxmox-ipv6.yml` overlay adds a separate IPv6 bridge
to only the API and worker, preserving the default IPv4 inter-service network
and DNS aliases. It also sets `PROXMOX_FORCE_IPV6=true` on those two services.
Both are required: enabling an IPv6 network alone does not force HTTPX
away from a broken IPv4 address. TLS verification remains controlled by
`PROXMOX_VERIFY_SSL`, and must remain enabled in production.

Validate the configuration without modifying running services:

```bash
docker compose -f docker-compose.yml -f docker-compose.proxmox-ipv6.yml config --quiet
```

Applying the overlay with `docker compose -f docker-compose.yml -f
docker-compose.proxmox-ipv6.yml up -d` **recreates the API and worker** but
should leave the default Compose network and other services unchanged. Confirm
the proposed changes and arrange a short API maintenance window. Removing the
overlay and running the base Compose file again returns those two services to
their usual network configuration. When using a
different network or an IPv6-only internal endpoint, ensure Docker hosts and
upstream firewalls have outbound IPv6 routing before enabling this option.

On a cold clone, Cloud-Init and the guest operating system can take time to
start the QEMU guest agent, especially on an isolated bridge without DHCP.
`PROXMOX_AGENT_WAIT_SECONDS` defaults to 300 seconds (30–900 supported),
matching the template builder's default. A timeout still fails provisioning;
it does not mean a nonresponsive guest flag was successfully installed.

Proxmox flag provisioning waits for a QEMU guest-agent ping, then writes the
per-lab flag using the guest-agent `file-write` API and verifies the exact
contents using `file-read`. This avoids relying on short-lived guest-exec
process IDs. The target directory must already exist in the template and be
writable by the guest agent. Missing permissions, a failed write, mismatched
read-back, or a guest-agent timeout abort provisioning; the lab must never be
reported ready without a verified flag. The Proxmox API token must have the
guest-agent file operation permissions (`VM.GuestAgent.Unrestricted` on PVE 9).

Staging network verification (October 31): template VMID `9002` uses
`ipconfig0=ip=dhcp`. An earlier disposable guest on the isolated `vmbr1` had
no assigned IP (`pending`), but its guest-agent flag verification passed and
its VMID was removed. After activating the SDN VNet below, a new disposable
guest on `clabnet1` received `10.210.0.100`, passed guest-agent flag
`file-write`/`file-read` verification, and was removed with VMID `103`
confirmed absent. This proves guest address allocation on the staging VNet,
**not** VPN reachability or per-student security isolation. Do not attach the
isolated bridge to a public interface to provide connectivity.

### Proxmox SDN isolated staging VNet (activated, staging only)

The operator created and applied zone `clabzone` and VNet `clabnet1` on node
`com`. The node reports `clabnet1` with gateway `10.210.0.1/24`; systemd
reports `dnsmasq@clabzone` active. The live authenticated readiness check
passed for the zone, applied bridge, template, storage and SDN token ACLs.
The application supports an optional existing VNet via `PROXMOX_SDN_VNET`
(default empty, preserving the working `PROXMOX_BRIDGE`). It verifies the
cluster VNet, the zone's `available` status on the node and the applied bridge
at `/nodes/{node}/sdn/zones/{zone}/bridges` before allocating a guest, then
uses the VNet for `net0`. Readiness also requires `SDN.Use` permission for the
VNet and the template's original bridge. The application does **not** create
or apply SDN resources automatically.

Applied staging configuration (verify no overlap with management LANs, VPN
ranges, other networks or existing routes before widening access):

1. In **Datacenter → SDN → Zones**, create a **Simple** zone `clabzone` scoped
   to node `com`; use built-in PVE IPAM, and enable the `dnsmasq` DHCP backend
   only after installing and preparing `dnsmasq` on the node according to the
   Proxmox SDN guide.
2. Under **VNets**, create `clabnet1` in zone `clabzone` (Proxmox VNet
   identifiers are limited to eight characters).
3. Define a non-overlapping subnet; candidate **10.210.0.0/24** with gateway
   `10.210.0.1` and DHCP pool `10.210.0.100`–`10.210.0.199`. Keep it
   isolated, with SNAT/public routing disabled for the initial test.
4. The operator applied the cluster-wide SDN configuration. A read-only
   readiness check and one isolated `scripts.proxmox_smoke --run` were
   successful using temporary `PROXMOX_SDN_VNET=clabnet1` overrides. To opt
   in persistently, set `PROXMOX_SDN_VNET=clabnet1` in the API and worker
   environment after reviewing the rollout and restart plan.

Proxmox's built-in SDN DHCP/IPAM integration is still designated **tech
preview**. Confirm the installed version's backend and implement monitoring
and a recovery plan before relying on DHCP for production labs. Crucially,
one staging VNet **is a shared L2 segment**; it is **not** production-grade
per-student isolation. Multiple untrusted students must use separately
isolated lab networks or a fully validated firewall policy, with VPN routing
restricted to each assigned lab and no access to Proxmox management.
The current Proxmox provider now deliberately rejects production-mode lab
provisioning until this isolation and routing enforcement is implemented; its
staging connection hint explicitly identifies the VNet as shared. Do not
interpret successful SDN DHCP or guest flag installation as authorization to
enable student-facing VMs.

#### Opt-in pool of operator-created staging VNets

The application also supports `PROXMOX_SDN_VNET_POOL=clab001,clab002` as an
**alternative** to the shared `PROXMOX_SDN_VNET` setting (never set both).
These example VNet IDs do not exist until an operator creates, configures and
applies them. Each requires its own non-overlapping subnet, IPAM/DHCP range,
appropriate SDN.Use token ACL, and an independently checked host firewall and
VPN routing policy. In particular, separate L2 VNets do **not** by themselves
prevent routing between their IP subnets on the Proxmox host.

When a pool is configured, a PostgreSQL transaction-scoped advisory lock
serializes reservations by user across API workers. The network name stored
with the lab is the chosen VNet, which the Proxmox provider verifies against
the allowed pool and live applied SDN bridges before cloning. Both queued and
synchronous launches reserve a network before committing their lab record;
subsequent labs for the same user reuse the reserved VNet. The allocator
persists reservations in `proxmox_sdn_leases`, a separate table with **no user
foreign-key cascade**. First use also backfills matching historical lab
assignments before reserving a new VNet. This ledger survives removal of lab
history and user accounts. Apply Alembic migrations before enabling the pool.
The allocator **never automatically reuses a leased VNet**, including after
failed, expired or terminated labs, because stopped or orphaned VMs may still
exist. Exhaustion fails closed instead of reassigning another student's
network. Operators must verify that all previous guests, IPAM leases,
forwarding rules and credentials are gone before any audited manual reclaim.
Automated cleanup verification is still required for production-grade reuse.

The pool feature and `clabnet1` remain **staging-only**: the production-mode
Proxmox block stays in effect until end-to-end enforcement and negative
cross-student connectivity tests pass. Do not modify `vmbr0` or enable SNAT to
get connectivity without a reviewed access policy.

The read-only `scripts.proxmox_check` validates every configured pool VNet,
including its distinct RFC1918 IPv4 subnet, DHCP range, disabled SNAT and
`SDN.Use` ACL. For a one-VM disposable test on an approved pool VNet, run
`python -m scripts.proxmox_smoke --run --vnet clab001` after verifying the
operator-created VNet and explicit VM cleanup authority. In pool mode the
smoke test refuses to clone without `--vnet` and never falls back to `vmbr0`
or the shared staging bridge. This remains a provisioning test only; it does
not establish student-to-student or WireGuard access isolation.

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
