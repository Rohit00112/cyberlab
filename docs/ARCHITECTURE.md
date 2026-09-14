# Architecture Overview

This document records the high-level architecture decisions for IIC CyberLab (MVP).

## Logical layers

```text
Web Platform (Next.js)  ─┐
Application API (FastAPI) ┼── PostgreSQL + Redis + Keycloak
Cyber Range (Docker)     ─┘        (LabProvider abstraction → Proxmox in Phase 2)
```

## Key decisions

1. **Modular monorepo** (`apps/web`, `apps/api`, `infrastructure`, `challenges`, `docs`).
2. **Identity** — Keycloak realm `cyberlab`. The web app uses the `web` (public, auth code + PKCE)
   client. The API validates JWTs with the `api` (confidential) client via OIDC discovery + JWKS.
   Users are upserted locally (keyed by Keycloak `sub`) so DB foreign keys work.
3. **Lab isolation** — Docker containers attached to a dedicated internal bridge network with
   resource limits. The API is the only holder of the Docker socket; students never reach
   infrastructure directly. `LabProvider` interface keeps business logic decoupled from the
   infrastructure backend (Proxmox later).
4. **Server-side enforcement** — flags are hashed server-side, scoring and expiry are enforced by
   the API, and all authorization is checked per-request from JWT claims — never from the client.
5. **Flags stored as salted SHA-256 hashes** (pragmatic for static flags; see PRD §19). Lab
   challenges augment this with **per-session flags**: each container is launched with a fresh
   `IIC{lab-<hex>}` written to its filesystem (`/flag.txt`), only its hash persists in
   `lab_instances.flag_hash`, and submissions can bind to a `lab_id` to validate against that
   live session (ownership + running + not-expired checks, PRD §19/§80).
6. **Development** — Docker Compose (postgres, redis, keycloak, api hot-reload, web `next dev`).
   Production build uses `standalone` output + `python:3.13-slim` multi-stage images.
7. **Challenge catalogue as data** — seeds live in `challenges/*.yaml` (per category) and are
   loaded idempotently by slug via `apps/api/scripts/seed_challenges.py`. Only flag hashes are
   stored; YAML plaintext is dev-only.
8. **Adaptive surfaces** — recommendations (`/recommendations/challenges`), learning paths
   (sequential unlock), and difficulty analytics feed the student-facing UI (dashboard, `/skills`,
   `/paths`, `/analytics`).

## Deviations from PRD recommendations (all deliberate for MVP)

| Area | PRD | MVP choice | Why |
|---|---|---|---|
| Lab orchestration | dedicated service | module within API (`app/labs`) | single-instance compose; extracted later |
| Task queue | Celery | async tasks + Redis state | dependency reduction until volume demands it |
| Proxmox | primary VM backend | Docker only | no VM infrastructure in dev; adapter-first |