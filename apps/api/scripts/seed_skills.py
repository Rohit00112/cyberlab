"""Seed the skill taxonomy (PRD §26) and reconcile challenge links.

Idempotent: skills are keyed on a stable slug and skipped when present.
Run via the API venv: apps/api/.venv/bin/python -m scripts.seed_skills
"""
from sqlalchemy import select

from app.db.base import SessionLocal
from app.models.challenges import Challenge
from app.models.skills import Skill
from app.services.skills import sync_challenge_skills

TOP_LEVEL: list[tuple[str, str, str]] = [
    ("networking", "Networking", "TCP/IP, DNS, HTTP, firewall rules and network protocols."),
    ("linux", "Linux", "CLI, filesystems, permissions, service management and scripting."),
    (
        "windows-ad",
        "Windows & Active Directory",
        "Windows internals, AD domain operations, Kerberos and group policy.",
    ),
    ("web-security", "Web Security", "OWASP Top 10, authn/authz, injection, XSS and CSRF."),
    (
        "secure-coding",
        "Secure Coding",
        "Memory safety, input handling, code review and OWASP ASVS.",
    ),
    ("cryptography", "Cryptography", "Ciphers, hashing, PKI, signatures and cryptographic flaws."),
    (
        "digital-forensics",
        "Digital Forensics",
        "Evidence acquisition, disk/memory analysis and artifacts.",
    ),
    (
        "incident-response",
        "Incident Response",
        "Detection, containment, eradication and recovery playbooks.",
    ),
    (
        "malware-analysis",
        "Malware Analysis",
        "Static and dynamic analysis, packing and obfuscation.",
    ),
    ("cloud-security", "Cloud Security", "IAM, container and serverless hardening across CSPs."),
    (
        "security-operations",
        "Security Operations",
        "SOC monitoring, log analysis and phishing detection.",
    ),
    ("osint", "OSINT", "Open-source intelligence gathering and metadata analysis."),
    (
        "penetration-testing",
        "Penetration Testing",
        "Recon, exploitation, privilege escalation and reporting.",
    ),
    (
        "vulnerability-analysis",
        "Vulnerability Analysis",
        "CVE triage, fuzzing and root-cause identification.",
    ),
    (
        "governance-risk-compliance",
        "Governance / Risk / Compliance",
        "Policies, standards, risk and audit.",
    ),
]


async def seed() -> None:
    async with SessionLocal() as db:
        for slug, name, description in TOP_LEVEL:
            existing = await db.scalar(select(Skill).where(Skill.slug == slug))
            if existing is None:
                db.add(Skill(slug=slug, name=name, description=description))
        await db.commit()
        print(f"seed_skills: ensured {len(TOP_LEVEL)} top-level skills")

        challenges = (await db.scalars(select(Challenge))).all()
        for challenge in challenges:
            await sync_challenge_skills(db, challenge.id, challenge.skills)
        print(f"seed_skills: reconciled {len(challenges)} challenges")


if __name__ == "__main__":
    import asyncio

    asyncio.run(seed())