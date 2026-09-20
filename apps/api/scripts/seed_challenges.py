"""Seed the challenge catalogue from YAML definitions (PRD §56 — quality over quantity).

Idempotent: challenges are keyed on slug and skipped when already present.
The plaintext flags in ``challenges/*.yaml`` are development seeds only; only their
SHA-256 hashes are stored.

Location of the YAML directory (defaults to the repo-root ``challenges/``) can be
overridden with the ``CYBERLAB_CHALLENGES_DIR`` environment variable or ``--dir``.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

import yaml
from sqlalchemy import select

from app.core.flags import hash_flag, slugify
from app.db.base import SessionLocal
from app.models.challenges import Challenge
from app.models.users import User

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DIR = REPO_ROOT / "challenges"

REQUIRED_FIELDS = ("title", "description", "category", "difficulty", "points", "flag")


def _load_specs(directory: Path) -> list[tuple[Path, dict]]:
    if not directory.is_dir():
        raise SystemExit(f"challenges directory not found: {directory}")
    specs: list[tuple[Path, dict]] = []
    for path in sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml")):
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        if not isinstance(loaded, list):
            raise SystemExit(f"{path}: expected a YAML list of challenges")
        for item in loaded:
            if not isinstance(item, dict):
                raise SystemExit(f"{path}: every challenge must be a mapping")
            _validate(item, path)
            specs.append((path, item))
    return specs


def _validate(spec: dict, path: Path) -> None:
    missing = [field for field in REQUIRED_FIELDS if not spec.get(field)]
    if missing:
        raise SystemExit(f"{path}: missing fields {missing} for {spec.get('title', '?')}")
    if spec["difficulty"] not in {"beginner", "intermediate", "advanced"}:
        raise SystemExit(f"{path}: bad difficulty {spec['difficulty']!r}")
    if spec.get("environment_type", "none") not in {"none", "docker"}:
        raise SystemExit(f"{path}: bad environment_type {spec['environment_type']!r}")


async def seed(directory: Path | None = None) -> None:
    directory = directory or DEFAULT_DIR
    specs = _load_specs(directory)
    print(f"seed_challenges: {len(specs)} definitions from {directory}")

    async with SessionLocal() as db:
        admin = await db.scalar(select(User).where(User.email == "admin@cyberlab.local"))
        author_id = admin.id if admin else None

        inserted = 0
        updated = 0
        for _path, spec in specs:
            slug = slugify(spec["title"])
            flag = spec.pop("flag")
            env_type = spec.pop("environment_type", "none")
            hint_penalty = spec.pop("hint_penalty", 0)
            flag_hash_val = hash_flag(flag)

            existing = await db.scalar(select(Challenge).where(Challenge.slug == slug))
            if existing:
                existing.flag_hash = flag_hash_val
                existing.environment_type = env_type
                existing.hint_penalty = hint_penalty
                for k, v in spec.items():
                    setattr(existing, k, v)
                updated += 1
                continue

            challenge = Challenge(
                slug=slug,
                author_id=author_id,
                flag_hash=flag_hash_val,
                status="published",
                environment_type=env_type,
                hint_penalty=hint_penalty,
                **spec,
            )
            db.add(challenge)
            inserted += 1

        await db.commit()
        print(f"seed_challenges: {inserted} inserted, {updated} updated")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed challenges from YAML")
    parser.add_argument(
        "--dir",
        default=os.environ.get("CYBERLAB_CHALLENGES_DIR"),
        help="Directory containing challenge YAML files (default: repo-root challenges/)",
    )
    args = parser.parse_args()
    target = Path(args.dir) if args.dir else DEFAULT_DIR
    asyncio.run(seed(target))


if __name__ == "__main__":
    main()