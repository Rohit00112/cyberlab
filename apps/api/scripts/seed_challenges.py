"""Seed the initial challenge catalogue (see PRD §56 — quality over quantity).

Idempotent: challenges are keyed on slug and skipped when already present.
The plaintext flags below are development seeds only.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.flags import hash_flag, slugify
from app.db.base import SessionLocal
from app.models.challenges import Challenge
from app.models.users import User

STARTER_CHALLENGES: list[dict] = [
    {
        "title": "Basic Linux Investigation",
        "description": (
            "Find a suspicious file hidden in the filesystem and recover the flag from it."
        ),
        "instructions": (
            "Connect to the provided lab container. A file named `flag.txt` is not where it "
            "should be. Search for it, inspect ownership, timestamps and file contents, then "
            "submit the flag you uncover."
        ),
        "category": "Linux",
        "difficulty": "beginner",
        "points": 100,
        "estimated_minutes": 20,
        "skills": ["Linux CLI", "Filesystem", "Basic command usage"],
        "prerequisites": ["Comfortable with a terminal"],
        "hints": ["`find / -name flag.txt 2>/dev/null` is a good starting point."],
        "flag": "IIC{linux-investigation-101}",
        "flag_format": "IIC{...}",
        "environment_type": "docker",
    },
    {
        "title": "Networking Trivia: TCP Handshake",
        "description": "Identify the intended final sequence of a TCP three-way handshake.",
        "instructions": (
            "The traditional TCP three-way handshake goes SYN, then SYN-ACK. Submit the flag "
            "that names the third packet of a successful handshake."
        ),
        "category": "Networking",
        "difficulty": "beginner",
        "points": 75,
        "estimated_minutes": 10,
        "skills": ["TCP/IP", "Packet basics"],
        "prerequisites": [],
        "hints": ["The last packet confirms the connection is established."],
        "flag": "IIC{ack}",
        "flag_format": "IIC{...}",
        "environment_type": "none",
    },
    {
        "title": "XOR is Not Encryption",
        "description": "A single-byte XOR cipher hides the flag. Decode it without a key.",
        "instructions": (
            "Decrypt the following hex blob that was XOR-encrypted with a single byte: "
            "`5e151b5231435f183b551d5f1f515b3e153f1d0b513737`."
        ),
        "category": "Cryptography",
        "difficulty": "beginner",
        "points": 150,
        "estimated_minutes": 25,
        "skills": ["XOR", "Bash scripting", "Pattern recognition"],
        "prerequisites": ["Bitwise operations"],
        "hints": [
            "Try every byte from 0x00 to 0xFF.",
            "The plaintext is human-readable and starts with the flag prefix.",
        ],
        "flag": "IIC{xor-single-byte}",
        "flag_format": "IIC{...}",
        "environment_type": "none",
    },
    {
        "title": "Hidden Metadata",
        "description": "Examine a photo file and extract the flag from its EXIF metadata.",
        "instructions": (
            "A JPEG attached to a phishing email was found on the file server. In its EXIF "
            "metadata a comment field contains the flag. Open the file and inspect its metadata."
        ),
        "category": "Digital Forensics",
        "difficulty": "beginner",
        "points": 125,
        "estimated_minutes": 15,
        "skills": ["EXIF", "Metadata analysis", "Forensics tooling"],
        "prerequisites": ["Basic image awareness"],
        "hints": ["On Linux: `exiftool photo.jpg` or `identify -verbose`."],
        "flag": "IIC{exif-metadata-leak}",
        "flag_format": "IIC{...}",
        "environment_type": "none",
    },
    {
        "title": "SQL Injection in the Wild",
        "description": "Bypass the login form of a deliberately vulnerable web app.",
        "instructions": (
            "Launch the provided lab. The login form at `/login` naively concatenates user "
            "input into a SQL query. Log in as the administrator without knowing the password "
            "(the flag is printed after a successful admin login)."
        ),
        "category": "Web Security",
        "difficulty": "intermediate",
        "points": 250,
        "estimated_minutes": 30,
        "skills": ["SQL", "Web enumeration", "Auth bypass"],
        "prerequisites": ["Understanding of SQL basics", "How HTTP forms work"],
        "hints": [
            "Try submitting `' OR '1'='1` as the username and any password.",
            "The vulnerable query wraps the payload in single quotes.",
        ],
        "flag": "IIC{sqli-auth-bypass}",
        "flag_format": "IIC{...}",
        "environment_type": "docker",
    },
    {
        "title": "Privilege Escalation Primer",
        "description": "Exploit a common misconfiguration to read a protected file.",
        "instructions": (
            "You have a low-privileged shell in the lab container. A root-owned executable "
            "with the SUID bit can be abused to read `/root/flag.txt`. Identify it and recover "
            "the flag."
        ),
        "category": "System Security",
        "difficulty": "intermediate",
        "points": 275,
        "estimated_minutes": 35,
        "skills": ["SUID", "Linux permissions", "Enumeration"],
        "prerequisites": ["Linux permissions model", "Basic shell"],
        "hints": [
            "Look for SUID binaries with `find / -perm -4000 2>/dev/null`.",
            "GNU `find` itself can execute commands with its own privileges.",
        ],
        "flag": "IIC{suid-privesc}",
        "flag_format": "IIC{...}",
        "environment_type": "docker",
    },
    {
        "title": "Blue Team: Spot the Phish",
        "description": "Analyse an email header and decide whether the message is malicious.",
        "instructions": (
            "Review the supplied email `.eml` file. Submit the flag once you identify the "
            "spoofed sender domain used in the phishing attempt."
        ),
        "category": "Blue Team",
        "difficulty": "beginner",
        "points": 100,
        "estimated_minutes": 20,
        "skills": ["Email headers", "Phishing analysis", "SPF/DKIM awareness"],
        "prerequisites": [],
        "hints": [
            "`Received:` headers reveal the real sending path.",
            "Compare `From` with `Return-Path`.",
        ],
        "flag": "IIC{spoofed-domain}",
        "flag_format": "IIC{...}",
        "environment_type": "none",
    },
    {
        "title": "Secure Coding: Memory Safety",
        "description": "Find the bug class that makes this C snippet exploitable.",
        "instructions": (
            "The snippet calls `strcpy(buffer, user_input)` with a fixed-size stack buffer. "
            "Submit the flag naming the vulnerability class."
        ),
        "category": "Secure Coding",
        "difficulty": "beginner",
        "points": 100,
        "estimated_minutes": 15,
        "skills": ["C", "Buffer handling", "Code review"],
        "prerequisites": ["C basics"],
        "hints": ["What happens when input is larger than the buffer?"],
        "flag": "IIC{buffer-overflow}",
        "flag_format": "IIC{...}",
        "environment_type": "none",
    },
]


async def seed() -> None:
    async with SessionLocal() as db:
        admin = await db.scalar(
            select(User).where(User.email == "admin@cyberlab.local")
        )
        author_id = admin.id if admin else None

        inserted = 0
        skipped = 0
        for spec in STARTER_CHALLENGES:
            slug = slugify(spec["title"])
            existing = await db.scalar(select(Challenge).where(Challenge.slug == slug))
            if existing:
                skipped += 1
                continue
            flag = spec.pop("flag")
            challenge = Challenge(
                slug=slug,
                author_id=author_id,
                flag_hash=hash_flag(flag),
                status="published",
                **spec,
            )
            db.add(challenge)
            inserted += 1

        await db.commit()
        print(f"seed_challenges: {inserted} inserted, {skipped} skipped")


if __name__ == "__main__":
    asyncio.run(seed())