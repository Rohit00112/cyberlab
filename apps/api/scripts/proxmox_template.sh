#!/usr/bin/env bash
# Build a reusable CyberLab base VM template on a Proxmox VE node.
#
# Designed to run ON the PVE host as root (no SSH is required from the API host).
# It:
#   1. verifies the configured storage + Linux bridge exist (bails with a clear
#      message otherwise),
#   2. downloads a cloud image (Debian by default),
#   3. creates a VM with a cloud-init drive + qemu-guest-agent,
#   4. boots it once so cloud-init initializes (installs qemu-guest-agent if the
#      image does not ship it), then shuts it down,
#   5. converts the VM to a template at the requested VMID.
#
# After the build, set LAB_IMAGE=<vmid> in the API's .env (already "9000").
#
# Usage:
#   sudo ./scripts/proxmox_template.sh            # all defaults
#   sudo PVMID=9002 PM_BRIDGE=vmbr2 ./scripts/proxmox_template.sh
#
# Variables (all optional):
#   PVMID        template VMID                     (default: 9000)
#   PM_NAME      template name                     (default: cyberlab-base)
#   PM_STORAGE   storage for the clone            (default: local-lvm)
#   PM_BRIDGE    Linux bridge for net0            (default: vmbr1)
#   PM_MEMORY    RAM MiB                          (default: 2048)
#   PM_CORES     vCPUs                            (default: 2)
#   PM_DISK_GB   disk size in GiB                 (default: 8)
#   PM_IMAGE_URL cloud image to download           (default: Debian 13 genericcloud amd64)
#   PM_CI_USER   cloud-init login user            (default: admin)
#   PM_CI_PASS   cloud-init password (optional)
#   PM_SSH_KEY   path to a public key to install  (optional)
#   PM_AGENT     "1" install qemu-guest-agent on first boot (default: 1)
set -euo pipefail

PVMID="${PVMID:-9000}"
PM_NAME="${PM_NAME:-cyberlab-base}"
PM_STORAGE="${PM_STORAGE:-local-lvm}"
PM_BRIDGE="${PM_BRIDGE:-vmbr1}"
PM_MEMORY="${PM_MEMORY:-2048}"
PM_CORES="${PM_CORES:-2}"
PM_DISK_GB="${PM_DISK_GB:-8}"
PM_IMAGE_URL="${PM_IMAGE_URL:-https://cloud.debian.org/images/cloud/trixie/latest/debian-13-genericcloud-amd64.qcow2}"
PM_CI_USER="${PM_CI_USER:-admin}"
PM_CI_PASS="${PM_CI_PASS:-}"
PM_SSH_KEY="${PM_SSH_KEY:-}"
PM_AGENT="${PM_AGENT:-1}"

IMG_NAME="${PM_IMAGE_URL##*/}"
IMG_PATH="/var/lib/vz/template/iso/${IMG_NAME}"

log() { printf '[proxmox-template] %s\n' "$*"; }
die() { printf '[proxmox-template] ERROR: %s\n' "$*" >&2; exit 1; }

for tool in qm pvesm ip curl; do
    command -v "$tool" >/dev/null 2>&1 || die "missing required tool: '$tool' (run this script on the Proxmox node as root)"
done
[[ "$(id -u)" -eq 0 ]] || die "must run as root on the Proxmox node"

# --- 1. Storage ---
if ! pvesm status -content images 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx "$PM_STORAGE"; then
    die "storage '$PM_STORAGE' not found (content=images). Create it in Datacenter > Storage, or set PM_STORAGE."
fi
log "storage '$PM_STORAGE' ok"

# --- 2. Bridge ---
if ! ip link show "$PM_BRIDGE" >/dev/null 2>&1; then
    die "bridge '$PM_BRIDGE' not found. Create it in the node's Network tab, or set PM_BRIDGE."
fi
log "bridge '$PM_BRIDGE' ok"

# --- 3. Cloud image ---
mkdir -p "$(dirname "$IMG_PATH")"
if [[ -f "$IMG_PATH" ]]; then
    log "using existing image $IMG_PATH"
else
    log "downloading $PM_IMAGE_URL"
    curl -fL --retry 3 -o "$IMG_PATH.tmp" "$PM_IMAGE_URL"
    mv "$IMG_PATH.tmp" "$IMG_PATH"
fi

# --- 3b. Bake qemu-guest-agent into the image (offline, reliable) ---
AGENT_BAKED=0
if command -v virt-customize >/dev/null 2>&1; then
    log "baking qemu-guest-agent into ${IMG_NAME} (virt-customize)"
    virt-customize -a "$IMG_PATH" \
        --install qemu-guest-agent \
        --truncate /etc/machine-id \
        || die "virt-customize failed (node likely needs internet for apt)"
    AGENT_BAKED=1
else
    log "WARNING: libguestfs-tools (virt-customize) not installed."
    log "         Falling back to a boot-once pass to enable qemu-guest-agent."
fi

# --- 4. Create the VM ---
if qm status "$PVMID" >/dev/null 2>&1; then
    die "VMID $PVMID already exists — refuse to overwrite. Pick a free VMID via PVMID=..."
fi
log "creating VM $PVMID ($PM_NAME)"
qm create "$PVMID" \
    --name "$PM_NAME" \
    --memory "$PM_MEMORY" \
    --cores "$PM_CORES" \
    --scsihw virtio-scsi-pci \
    --net0 "virtio,bridge=${PM_BRIDGE}" \
    --agent enabled=1,fstrim_cloned_disks=1

log "importing cloud image disk"
qm importdisk "$PVMID" "$IMG_PATH" "$PM_STORAGE"

log "attaching disk + cloud-init drive"
qm set "$PVMID" \
    --scsi0 "${PM_STORAGE}:vm-${PVMID}-disk-0" \
    --ide2 "${PM_STORAGE}:cloudinit" \
    --boot order=scsi0 \
    --serial0 socket \
    --vga serial0 \
    --ostype l26 \
    --ipconfig0 ip=dhcp \
    --ciuser "$PM_CI_USER"
if [[ -n "$PM_CI_PASS" ]]; then
    qm set "$PVMID" --cipassword "$PM_CI_PASS"
fi
if [[ -n "$PM_SSH_KEY" && -f "$PM_SSH_KEY" ]]; then
    qm set "$PVMID" --sshkeys "$PM_SSH_KEY"
fi

# --- 5. Boot-once fallback (only when the agent was NOT baked in) ---
if [[ "$AGENT_BAKED" -eq 0 && "$PM_AGENT" == "1" ]]; then
    log "starting VM $PVMID for a one-time cloud-init pass"
    qm start "$PVMID"
    printf '[proxmox-template] waiting for qemu-guest-agent'
    agent_ok=0
    for _ in $(seq 1 60); do
        if qm guest cmd "$PVMID" ping >/dev/null 2>&1; then agent_ok=1; break; fi
        printf '.'
        sleep 5
    done
    printf '\n'
    if [[ "$agent_ok" -eq 1 ]]; then
        log "qemu-guest-agent is responding"
    else
        log "stopping VM — refusing to create a template without an agent"
        qm stop "$PVMID" >/dev/null 2>&1 || true
        die "qemu-guest-agent never came up. Install libguestfs-tools and re-run, or bake the agent yourself: virt-customize -a $IMG_PATH --install qemu-guest-agent"
    fi
    log "shutting VM $PVMID down"
    qm shutdown "$PVMID" --timeout 120 >/dev/null 2>&1 || qm stop "$PVMID" >/dev/null 2>&1
    while qm status "$PVMID" | grep -q running; do sleep 2; done
fi

# --- 6. Convert to template ---
if [[ "$AGENT_BAKED" -eq 1 ]]; then agent_tag="qemu-guest-agent baked-in"; else agent_tag="qemu-guest-agent via boot"; fi
qm template "$PVMID"
log "DONE: template VMID=$PVMID '$PM_NAME' ($agent_tag)"
log "now set LAB_IMAGE=${PVMID} in the API .env and restart the API"