# Target Architecture — IIC CyberLab

## Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                          Clients                                  │
│  Browser (Next.js SPA)  │  WireGuard VPN  │  Admin CLI            │
└──────────┬──────────────┴───────┬─────────┴───────────────────────┘
           │ HTTPS                │ UDP 51820
┌──────────▼──────────────────────▼─────────────────────────────────┐
│                    Caddy Reverse Proxy                             │
│          TLS termination, routing, rate limiting                   │
└──────────┬──────────────────────┬─────────────────────────────────┘
           │                      │
┌──────────▼──────────┐ ┌────────▼──────────┐
│   Next.js Frontend  │ │   WireGuard       │
│   (App Router SSR)  │ │   Gateway         │
└──────────┬──────────┘ └────────┬──────────┘
           │ HTTP (internal)     │ tunnel
┌──────────▼──────────────────────▼─────────────────────────────────┐
│                    FastAPI Application                             │
│                                                                    │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐            │
│  │ Auth    │ │Challenges│ │ Labs     │ │ Competitions│            │
│  │ (OIDC)  │ │ Service  │ │ Service  │ │  Service    │            │
│  └─────────┘ └──────────┘ └────┬─────┘ └────────────┘            │
│  ┌─────────┐ ┌──────────┐     │       ┌────────────┐             │
│  │ Scoring │ │ Skills   │     │       │ Machine    │             │
│  │ Service │ │ & Badges │     │       │ Builder    │             │
│  └─────────┘ └──────────┘     │       └────────────┘             │
│  ┌──────────┐ ┌──────────┐    │       ┌────────────┐             │
│  │ Research │ │Recommend │    │       │ Audit &    │             │
│  │ Platform │ │ Engine   │    │       │ Metrics    │             │
│  └──────────┘ └──────────┘    │       └────────────┘             │
└───────────────────────────────┼───────────────────────────────────┘
                                │ (Celery tasks)
┌───────────────────────────────▼───────────────────────────────────┐
│                    Celery Worker(s)                                │
│                                                                    │
│  ┌───────────────────┐  ┌─────────────────┐  ┌────────────────┐  │
│  │ Provisioning      │  │ Maintenance     │  │ Image Build    │  │
│  │ Worker            │  │ Worker          │  │ Worker         │  │
│  │                   │  │                 │  │                │  │
│  │ • Create VM/Ctr   │  │ • Expire labs   │  │ • Build images │  │
│  │ • Inject flags    │  │ • Cleanup       │  │ • Validate     │  │
│  │ • Health checks   │  │ • Comp. auto    │  │ • Publish      │  │
│  │ • State updates   │  │ • WG key rotate │  │ • Hash/sign    │  │
│  └────────┬──────────┘  └─────────────────┘  └────────────────┘  │
└───────────┼──────────────────────────────────────────────────────┘
            │
┌───────────▼──────────────────────────────────────────────────────┐
│                Provider Abstraction Layer                         │
│                                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐         │
│  │  Docker  │  │  QEMU /  │  │ Proxmox  │  │  Fake    │         │
│  │ Provider │  │  KVM via │  │ Provider │  │ Provider │         │
│  │          │  │  Libvirt │  │          │  │ (test)   │         │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘         │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                    Data Layer                                     │
│                                                                   │
│  ┌────────────┐  ┌──────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ PostgreSQL │  │Redis │  │ Keycloak │  │ File Storage     │   │
│  │ 16         │  │ 7    │  │ 26       │  │ (images/exports) │   │
│  └────────────┘  └──────┘  └──────────┘  └──────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

## Design Decisions

### 1. Preserve existing architecture

The current monorepo structure (`apps/api`, `apps/web`, `infrastructure`) is well-organized.
All new work extends this structure rather than replacing it.

### 2. Add Celery for background tasks

The existing `asyncio.Event` maintenance loop is replaced with Celery workers backed by Redis.
This enables:
- Non-blocking lab provisioning (202 Accepted → poll or SSE)
- Reliable retry with exponential backoff
- Multi-worker deployment
- Job inspection and cancellation

### 3. Provider-based provisioning

Extend the existing `LabProvider` ABC with:
- `reset_lab()` (destroy + recreate as atomic operation)
- `readiness_check()` (verify services are up)
- Validated state machine for instance lifecycle

Add QEMU/KVM via Libvirt as a new provider alongside existing Docker and Proxmox.

### 4. Machine template system

Introduce `MachineTemplate` and `MachineTemplateVersion` models alongside the existing
`Challenge` model. Templates are the infrastructure definition; challenges are the
player-facing wrapper that references a template version.

### 5. WireGuard access layer

A separate WireGuard gateway service manages per-user/team VPN peers.
Lab instances are reachable only through the VPN tunnel, never directly exposed.

### 6. SSE for real-time updates

Server-Sent Events (SSE) for:
- Lab provisioning progress
- Lab status changes
- Competition live scoring

SSE chosen over WebSockets for simplicity and HTTP/2 compatibility.

### 7. Incremental database migration

All schema changes use Alembic migrations. Existing data is preserved.
New tables are added; existing tables gain columns with defaults.

## New Entities

| Entity | Purpose |
|---|---|
| MachineTemplate | Reusable machine definition (OS, services, vulnerabilities) |
| MachineTemplateVersion | Immutable, versioned snapshot of a template |
| ProvisioningJob | Durable record of async provisioning work |
| ComputeNode | Registered compute host with capacity |
| ResourceReservation | Pre-allocated resources for a provisioning job |
| InstanceLease | Time-bounded access grant to an instance |
| VPNPeer | WireGuard peer configuration per user/team |
| ScoreEvent | Granular scoring record for dynamic scoring |

## Technology Additions

| Component | Technology | Rationale |
|---|---|---|
| Task queue | Celery + Redis broker | Non-blocking provisioning, reliable retry |
| VM provider | libvirt (Python bindings) | Direct QEMU/KVM control |
| VPN | WireGuard | Lightweight, per-peer isolation |
| Real-time | SSE | Simple push for status updates |
| Dynamic scoring | Custom | Decay-based, solve-count-aware |

## What is NOT Changing

- FastAPI remains the API framework
- PostgreSQL remains the database
- Redis remains for caching and as Celery broker
- Keycloak remains for identity
- Next.js + React + Tailwind + shadcn/ui remain the frontend
- Docker Compose remains for deployment
- Alembic remains for migrations
- The existing test suite continues to run
