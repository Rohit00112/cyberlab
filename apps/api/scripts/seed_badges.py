"""Seed canonical badges (PRD §34, Phase 4).

Idempotent: badges are keyed on code and skipped when already present.
Run via: apps/api/.venv/bin/python -m scripts.seed_badges
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db.base import SessionLocal
from app.models.badges import Badge
from app.models.skills import Skill

CANONICAL_BADGES: list[dict] = [
    {
        "code": "first_solve",
        "name": "First Flag",
        "description": "Solved your very first cybersecurity challenge on CyberLab.",
        "icon": "🚩",
        "criteria": {"code": "first_solve", "value": 1},
    },
    {
        "code": "solver_5",
        "name": "Apprentice Solver",
        "description": "Successfully solved 5 cybersecurity challenges.",
        "icon": "🥉",
        "criteria": {"code": "solver_n", "value": 5},
    },
    {
        "code": "solver_10",
        "name": "Journeyman Solver",
        "description": "Successfully solved 10 cybersecurity challenges.",
        "icon": "🥈",
        "criteria": {"code": "solver_n", "value": 10},
    },
    {
        "code": "solver_25",
        "name": "Master Solver",
        "description": "Successfully solved 25 cybersecurity challenges.",
        "icon": "🥇",
        "criteria": {"code": "solver_n", "value": 25},
    },
    {
        "code": "web_champ",
        "name": "Web Exploiter",
        "description": "Solved 3 or more Web Security challenges.",
        "icon": "🌐",
        "criteria": {"code": "category_champion", "category": "Web Security", "value": 3},
        "skill_slug": "web-security",
    },
    {
        "code": "crypto_champ",
        "name": "Cryptanalyst",
        "description": "Solved 3 or more Cryptography challenges.",
        "icon": "🔐",
        "criteria": {"code": "category_champion", "category": "Cryptography", "value": 3},
        "skill_slug": "cryptography",
    },
    {
        "code": "forensics_champ",
        "name": "Digital Investigator",
        "description": "Solved 3 or more Digital Forensics challenges.",
        "icon": "🔍",
        "criteria": {"code": "category_champion", "category": "Digital Forensics", "value": 3},
        "skill_slug": "digital-forensics",
    },
    {
        "code": "linux_champ",
        "name": "Linux Maestro",
        "description": "Solved 3 or more Linux system challenges.",
        "icon": "🐧",
        "criteria": {"code": "category_champion", "category": "Linux", "value": 3},
        "skill_slug": "linux",
    },
    {
        "code": "network_champ",
        "name": "Packet Whisperer",
        "description": "Solved 3 or more Networking challenges.",
        "icon": "📡",
        "criteria": {"code": "category_champion", "category": "Networking", "value": 3},
        "skill_slug": "networking",
    },
    {
        "code": "blue_team_champ",
        "name": "Security Defender",
        "description": "Solved 3 or more Blue Team / SOC challenges.",
        "icon": "🛡️",
        "criteria": {"code": "category_champion", "category": "Blue Team", "value": 3},
        "skill_slug": "security-operations",
    },
    {
        "code": "lab_pioneer",
        "name": "Lab Pioneer",
        "description": "Launched and experimented with an isolated cyber range container lab.",
        "icon": "🧪",
        "criteria": {"code": "lab_session", "value": 1},
    },
    {
        "code": "ctf_veteran",
        "name": "CTF Veteran",
        "description": "Competed in an official timed CyberLab CTF competition.",
        "icon": "⚔️",
        "criteria": {"code": "ctf_participant", "value": 1},
    },
    {
        "code": "ctf_winner",
        "name": "Podium Finisher",
        "description": "Achieved a top 3 finish in an official CyberLab competition.",
        "icon": "🏆",
        "criteria": {"code": "ctf_winner", "value": 3},
    },
]


async def seed() -> None:
    async with SessionLocal() as db:
        skills = {s.slug: s.id for s in (await db.scalars(select(Skill))).all()}
        inserted = 0
        for item in CANONICAL_BADGES:
            code = item["code"]
            existing = await db.scalar(select(Badge).where(Badge.code == code))
            if existing is None:
                skill_id = skills.get(item.get("skill_slug")) if item.get("skill_slug") else None
                db.add(
                    Badge(
                        code=code,
                        name=item["name"],
                        description=item["description"],
                        icon=item["icon"],
                        criteria=item["criteria"],
                        skill_id=skill_id,
                        is_active=True,
                    )
                )
                inserted += 1
        await db.commit()
        print(f"seed_badges: inserted {inserted}, total {len(CANONICAL_BADGES)} canonical badges")


if __name__ == "__main__":
    asyncio.run(seed())
