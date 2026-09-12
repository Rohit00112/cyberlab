# IIC CyberLab — Project Proposal + Product Requirements Document (PRD)

**Document type:** Institutional Project Proposal + Software Product Requirements Document  
**Project:** IIC CyberLab  
**Subtitle:** Intelligent Cybersecurity Training, Simulation, Competition & Skill Analytics Platform  
**Institution:** Itahari International College (IIC), Nepal  
**Version:** 1.0  
**Status:** Proposed  
**Primary audience:** IIC management, faculty, project supervisors, developers, DevOps/infrastructure team, research team, and AI coding agents/LLMs

---

# 1. Executive Summary

IIC CyberLab is a secure, isolated and extensible cybersecurity training platform designed for Itahari International College.

The platform will combine four capabilities:

1. **Cybersecurity learning** — structured lessons, guided labs, hints and learning paths.
2. **Cyber range** — isolated vulnerable machines, applications, networks and defensive environments where students can safely practice.
3. **CTF/competition platform** — challenges, flags, scoring, teams, leaderboards and competition events.
4. **Cybersecurity intelligence** — student skill profiles, performance analytics, competency mapping and personalized challenge recommendations.

The central principle is:

> Students should be able to practice realistic cybersecurity skills without being able to damage IIC's production infrastructure.

The system must therefore treat the cyber-range environment as an untrusted, disposable environment and enforce strong network and resource isolation.

The first release should focus on a reliable MVP:

**Authentication → Challenge catalogue → Challenge instructions → Isolated lab → Flag submission → Validation → Score → Leaderboard → Faculty analytics.**

Advanced features such as automated VM provisioning, adaptive learning, ML recommendations, knowledge graphs and research analytics should be introduced incrementally.

---

# 2. Institutional Context

IIC is a private undergraduate institution associated with Innovate Nepal Group and delivers UK university programmes, including BSc (Hons) Computing and BA (Hons) Business Administration. Its computing environment, practical orientation, student projects, workshops, innovation activities and cybersecurity-related activities make a practical cybersecurity platform a strong institutional fit.

The platform is intended to support:

- BSc Computing teaching
- cybersecurity workshops
- practical laboratory sessions
- project-based learning
- internal CTF competitions
- inter-class competitions
- student portfolios
- cybersecurity research
- faculty assessment
- industry-oriented skill development
- future inter-college cybersecurity events

The product should be designed as an institutional platform rather than as a one-off student project.

---

# 3. Problem Statement

Traditional cybersecurity education has several limitations:

- Students often learn security concepts theoretically.
- Practical environments are difficult to provision and reset.
- Instructors have limited visibility into practical skill development.
- CTF platforms often focus on competition rather than structured learning.
- Vulnerable systems can create security risks if placed on production networks.
- Students have difficulty understanding which cybersecurity skills they actually possess.
- Faculty may know a student's final score but not the specific competency gaps behind that score.
- Creating and maintaining practical labs manually is time-consuming.

IIC CyberLab addresses these problems through a controlled, measurable and reusable cybersecurity training environment.

---

# 4. Product Vision

## Vision

> Build a safe, intelligent and reusable cybersecurity learning environment for IIC where students learn by doing, faculty can measure practical competency, and advanced students can progress from learners to challenge creators and cybersecurity researchers.

## Long-term vision

IIC CyberLab should eventually function as:

- IIC's cybersecurity practical laboratory
- IIC's internal CTF platform
- a cybersecurity competency tracking system
- a research platform
- a student cybersecurity portfolio
- a platform for workshops and competitions
- a foundation for future inter-college cybersecurity events

---

# 5. Product Goals

## Primary goals

1. Provide safe hands-on cybersecurity training.
2. Isolate vulnerable systems from IIC's production network.
3. Allow faculty to create and manage challenges.
4. Allow students to launch and solve practical labs.
5. Automatically validate challenge completion.
6. Track student performance.
7. Map challenges to cybersecurity skills.
8. Provide faculty analytics.
9. Support individual and team competitions.
10. Create a foundation for adaptive cybersecurity education.
11. Make the platform extensible enough for future research.
12. Make infrastructure reproducible and resettable.

## Secondary goals

- Provide student cybersecurity portfolios.
- Support badges/certificates.
- Support multiple difficulty levels.
- Support red-team and blue-team activities.
- Support Linux, Windows, web, network, cloud and forensic labs.
- Allow advanced students to contribute challenge content subject to faculty approval.

---

# 6. Non-Goals

The initial system must NOT attempt to:

- replace a full enterprise SIEM.
- replace IIC's production identity infrastructure.
- provide unrestricted access to the Internet from vulnerable machines.
- host uncontrolled malware.
- expose intentionally vulnerable machines directly to the public Internet.
- automatically punish or academically fail students based solely on ML predictions.
- become a generic college ERP.
- become a general-purpose cloud provider.
- provide unrestricted offensive-security infrastructure.

All offensive-security functionality must remain inside authorized, isolated environments.

---

# 7. Target Users

## 7.1 Student

Students use the platform to:

- learn concepts
- read lab instructions
- launch environments
- solve challenges
- submit flags
- request hints
- track progress
- view scores
- see skill development
- participate in competitions
- build a cybersecurity portfolio

## 7.2 Faculty / Instructor

Faculty use the platform to:

- create challenges
- publish labs
- assign challenges
- monitor student progress
- review submissions
- inspect analytics
- create competitions
- assess practical skills
- manage hints
- review student-generated challenges

## 7.3 Lab Administrator

Administrators manage:

- infrastructure
- VM templates
- networks
- resource quotas
- challenge environments
- system health
- backups
- audit logs
- platform configuration

## 7.4 Competition Organizer

Competition organizers manage:

- CTF events
- teams
- challenge availability
- scoring rules
- start/end times
- leaderboards
- event announcements

## 7.5 Researcher

Researchers use anonymized or authorized datasets to study:

- cybersecurity learning
- challenge difficulty
- skill progression
- adaptive learning
- student engagement
- recommendation algorithms
- practical competency

## 7.6 System Administrator

The system administrator manages:

- authentication
- roles
- platform configuration
- infrastructure integrations
- security controls
- monitoring
- backups
- incident response

---

# 8. User Roles and RBAC

The system must implement Role-Based Access Control.

Recommended roles:

| Role | Core permissions |
|---|---|
| Student | Solve assigned/public challenges, launch labs, submit flags |
| Faculty | Create/manage challenges, assignments, view student analytics |
| Competition Organizer | Manage competitions, teams, scoring |
| Lab Admin | Manage environments, templates, resources |
| Researcher | Access approved/anonymized research analytics |
| System Admin | Full platform administration |

Permissions should be granular rather than relying only on role names.

Example permissions:

- `challenge.view`
- `challenge.create`
- `challenge.edit`
- `challenge.publish`
- `challenge.delete`
- `lab.launch`
- `lab.reset`
- `lab.admin`
- `submission.create`
- `submission.review`
- `competition.create`
- `competition.manage`
- `analytics.view`
- `analytics.research`
- `user.manage`
- `audit.view`

---

# 9. Product Architecture

The system should be divided into logical layers.

```text
                         IIC CYBERLAB
                              |
          +-------------------+-------------------+
          |                   |                   |
      Web Platform       Application API     Cyber Range
          |                   |                   |
      Next.js UI          FastAPI API        Proxmox/Docker
          |                   |                   |
          +-------------------+-------------------+
                              |
                         PostgreSQL
                              |
              +---------------+----------------+
              |               |                |
          Redis/Queue      Object Storage    Search/Logs
              |               |                |
              +---------------+----------------+
                              |
                      Monitoring Layer
                              |
                    Prometheus + Grafana
                              |
                        Security Logs
                              |
                           Wazuh
```

---

# 10. Recommended Technology Stack

The implementation should use technologies that are maintainable, well documented and practical for an educational institution.

## Frontend

Recommended:

- Next.js
- React
- TypeScript
- Tailwind CSS
- component library such as shadcn/ui
- TanStack Query where appropriate
- Zod for validation

## Backend

Recommended:

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic

## Database

- PostgreSQL

## Caching / background jobs

- Redis
- Celery or equivalent task queue

## Authentication

Preferred:

- Keycloak for self-hosted identity and RBAC

Possible future integration:

- institutional Microsoft/Google identity provider if available and approved

## Cyber-range infrastructure

Primary recommendation:

- Proxmox VE for VM-based labs
- Docker for lightweight application challenges
- Ansible for reproducible configuration
- cloud-init where appropriate

## Monitoring

- Prometheus
- Grafana

## Security monitoring

- Wazuh
- Zeek where appropriate

## Reverse proxy

- Nginx or Caddy

Cloudflare Tunnel may be used for selected administrative/public application endpoints, but the vulnerable cyber-range networks must not be exposed through the same path.

## AI/ML

Initial:

- Python
- scikit-learn

Advanced:

- PyTorch
- graph libraries such as PyTorch Geometric

---

# 11. High-Level Network Architecture

Security isolation is a mandatory architectural requirement.

```text
                              INTERNET
                                  |
                            [Edge Firewall]
                                  |
                     +------------+------------+
                     |                         |
                Public Zone              Admin/Application
                     |                         |
              Web/API Gateway             IIC CyberLab
                                               |
                                        [Range Controller]
                                               |
                                      +--------+--------+
                                      |                 |
                                 Lab Network       Monitoring
                                      |                 |
                         +------------+-----------+     Wazuh
                         |            |           |     Zeek
                       Linux       Windows      Web    Grafana
                        VM           VM         VM
```

The production IIC network must not be routable from intentionally vulnerable student machines.

The preferred security model is:

> Assume every student-controlled lab environment can become compromised.

---

# 12. Cyber Range Isolation Requirements

The cyber range must support:

- isolated VLANs or equivalent network segmentation
- dedicated virtual bridges
- firewall rules
- per-lab network policies
- no unrestricted inbound Internet access
- controlled outbound traffic
- resource quotas
- CPU limits
- memory limits
- disk limits
- maximum concurrent environments
- automatic expiration
- snapshot/reset
- environment destruction
- audit logging

Each lab should have a lifecycle:

```text
AVAILABLE
   ↓
PROVISIONING
   ↓
RUNNING
   ↓
EXPIRED
   ↓
RESETTING
   ↓
AVAILABLE
```

If provisioning fails:

```text
PROVISIONING
      ↓
    ERROR
      ↓
CLEANUP
      ↓
RETRY / ADMIN REVIEW
```

---

# 13. MVP Scope

The first production-capable MVP should contain:

## Authentication

- Login
- Logout
- Role-based access
- Password reset if local accounts are supported
- Session management

## Student Dashboard

Display:

- current challenges
- assigned labs
- progress
- recent submissions
- score
- badges
- skill summary
- active lab sessions

## Challenge Catalogue

Each challenge should have:

- title
- description
- category
- difficulty
- estimated time
- skills
- prerequisites
- points
- hints
- flag format
- environment type
- author
- status

## Challenge categories

Initial categories:

- Linux
- Networking
- Web Security
- Cryptography
- Digital Forensics
- OSINT
- System Security
- Blue Team
- Secure Coding
- Cloud Security

---

# 14. Challenge Lifecycle

A challenge should move through states:

```text
DRAFT
  ↓
REVIEW
  ↓
APPROVED
  ↓
PUBLISHED
  ↓
ARCHIVED
```

Only approved/published challenges should become available to students.

Faculty-created challenges should support versioning.

---

# 15. Challenge Model

Each challenge should conceptually contain:

```yaml
challenge:
  id:
  title:
  slug:
  description:
  category:
  difficulty:
  points:
  estimated_minutes:
  skills:
  prerequisites:
  instructions:
  hints:
  environment:
  validation:
  author:
  status:
  version:
```

The exact implementation should use normalized database entities where appropriate rather than storing the entire challenge only as JSON.

---

# 16. Challenge Types

The platform should support several challenge types.

## 16.1 Flag challenge

Student receives a static problem and submits a flag.

## 16.2 Docker lab

Student receives a temporary vulnerable application.

## 16.3 VM lab

Student receives a temporary VM.

## 16.4 Multi-VM lab

Student receives a small network containing several machines.

## 16.5 Blue-team investigation

Student analyzes logs/traffic and answers questions.

## 16.6 Secure-coding challenge

Student fixes vulnerable code or identifies the vulnerability.

## 16.7 CTF challenge

Time-limited competitive challenge.

---

# 17. Lab Session System

A student should be able to click:

> Launch Lab

The backend should:

1. Verify authorization.
2. Check resource quota.
3. Create a lab session.
4. Provision the environment.
5. Configure networking.
6. Start required machines/containers.
7. Generate temporary credentials if needed.
8. Return connection information.
9. Start session timer.
10. Record audit information.

Example state:

```text
Student
  |
  | Launch
  v
API
  |
  v
Lab Orchestrator
  |
  +--> Check quota
  |
  +--> Create VM/container
  |
  +--> Attach isolated network
  |
  +--> Start services
  |
  +--> Register session
  |
  v
Student receives lab access
```

---

# 18. Lab Expiration

Every environment must have an expiration time.

Example:

- default: 60 minutes
- configurable by faculty
- maximum duration enforced by server

At expiration:

```text
RUNNING
   ↓
EXPIRED
   ↓
REVOKE ACCESS
   ↓
DESTROY/RESET
   ↓
RELEASE RESOURCES
```

The student must never be able to bypass server-side expiration by manipulating the frontend.

---

# 19. Flag Validation

Flags must be validated server-side.

A basic model:

```text
Student
   ↓
Submit Flag
   ↓
API
   ↓
Normalize Input
   ↓
Find Challenge
   ↓
Validate
   ↓
Correct?
  /   \
YES    NO
 |      |
Score   Attempt Log
```

The actual flag should never be sent to the frontend as plain text.

For static flags, store a secure representation such as a cryptographic hash where practical.

For dynamic flags, validation should occur inside the lab environment or through a controlled validator.

---

# 20. Anti-Cheating and Integrity

The system should support:

- attempt logging
- rate limiting
- submission timestamps
- challenge access logs
- suspicious activity detection
- optional browser/session telemetry
- competition-specific anti-cheating controls

Do not implement invasive surveillance by default.

The system should prioritize educational integrity while respecting privacy.

---

# 21. Scoring System

Each challenge can have:

- base points
- difficulty multiplier
- optional time bonus
- hint penalties
- competition-specific scoring

For MVP:

```text
Final Points = Base Challenge Points - Hint Penalties
```

Avoid unnecessarily complicated scoring in the first release.

---

# 22. Hint System

Hints should be progressive.

Example:

```text
Hint 1
Small conceptual clue

Hint 2
More specific direction

Hint 3
Strong clue / methodology
```

Each hint can optionally reduce the student's score.

Faculty should be able to configure:

- free hints
- percentage penalty
- fixed penalty

---

# 23. Leaderboards

Support:

- global leaderboard
- class leaderboard
- course leaderboard
- competition leaderboard
- team leaderboard

Leaderboard data should support:

- points
- solved challenges
- rank
- completion time
- optional badges

Privacy settings should allow administrators to determine whether real names, display names or anonymous identifiers are shown.

---

# 24. Competition System

Competition entities:

```text
Competition
  |
  +-- Challenges
  |
  +-- Participants
  |
  +-- Teams
  |
  +-- Rules
  |
  +-- Start/End Time
  |
  +-- Leaderboard
```

Competition lifecycle:

```text
DRAFT
  ↓
REGISTRATION
  ↓
SCHEDULED
  ↓
LIVE
  ↓
FINISHED
  ↓
ARCHIVED
```

Competition organizer capabilities:

- create event
- select challenges
- configure scoring
- allow teams
- set time
- publish rules
- monitor event
- freeze leaderboard
- export results

---

# 25. Student Skill System

Every challenge should be associated with one or more skills.

Example:

```text
Challenge:
"Investigating a Suspicious PCAP"

Skills:
- Network Analysis
- TCP/IP
- Wireshark
- Traffic Investigation
- Incident Response
```

Student skill score should not be a simplistic average of challenge points.

The first implementation can use a weighted competency score.

Example:

```text
Skill Score =
  weighted performance
  + challenge difficulty
  + repeated evidence
  + recent performance
```

Later versions may replace this with a research-grade competency model.

---

# 26. Cybersecurity Skill Taxonomy

Create a versioned taxonomy.

Initial top-level categories:

```text
1. Networking
2. Linux
3. Windows
4. Web Security
5. Secure Coding
6. Cryptography
7. Digital Forensics
8. Incident Response
9. Malware Analysis
10. Cloud Security
11. Security Operations
12. OSINT
13. Penetration Testing
14. Vulnerability Analysis
15. Governance / Risk / Compliance
```

The taxonomy should be extensible.

Each skill should have:

- id
- name
- description
- parent skill
- difficulty
- related skills
- version

---

# 27. Faculty Analytics

Faculty dashboard should provide:

## Class overview

- active students
- completed challenges
- average score
- average completion time
- challenge completion rate

## Challenge analytics

- attempts
- successful attempts
- failure rate
- average time
- hint usage
- difficulty indicators

## Skill analytics

Example:

```text
Networking             78%
Linux                  84%
Web Security           71%
Cryptography           56%
Forensics              49%
Incident Response      61%
```

## Student-level analytics

Faculty should be able to inspect:

- challenge history
- skill evidence
- attempts
- completion time
- hints used
- badges
- assigned challenges

---

# 28. Challenge Difficulty Analytics

The system should eventually estimate whether a challenge is:

- too easy
- appropriate
- too difficult

Useful metrics:

```text
Success Rate
Median Completion Time
Attempts per Student
Hint Usage
Drop-off Rate
```

Example:

```text
Challenge: Network Forensics 03

Success rate:        31%
Median time:         74 min
Hint usage:          81%

Recommendation:
Difficulty may be too high for target level.
```

The recommendation must be advisory, not automatically authoritative.

---

# 29. Adaptive Learning — Phase 2/3

Once enough data exists, implement challenge recommendations.

Input:

- student skills
- solved challenges
- failed challenges
- challenge difficulty
- recent performance
- prerequisites
- learning objectives

Output:

```text
Recommended next challenges
```

The recommendation engine should initially use transparent rules.

Example:

```text
IF skill < target
AND prerequisite satisfied
AND difficulty appropriate
THEN recommend challenge
```

ML should only be introduced after collecting sufficient quality data.

---

# 30. AI/ML Research Layer

Future research components may include:

- challenge recommendation
- difficulty prediction
- skill estimation
- learning outcome prediction
- student clustering
- anomaly detection
- knowledge graphs
- graph neural networks

Potential research question:

> Can adaptive cybersecurity challenge recommendations improve practical learning outcomes compared with a fixed challenge sequence?

Another:

> Can practical challenge performance provide a more accurate representation of cybersecurity competency than theoretical assessment alone?

---

# 31. Knowledge Graph — Future Feature

Represent relationships such as:

```text
Student
  ├── solved → Challenge
  ├── demonstrates → Skill
  ├── enrolled_in → Course
  ├── completed → Module
  └── participated_in → Competition

Challenge
  ├── teaches → Skill
  ├── requires → Skill
  └── belongs_to → Category

Skill
  ├── prerequisite_of → Skill
  └── related_to → Skill
```

This graph can later support:

- skill recommendations
- prerequisite reasoning
- challenge recommendations
- student similarity
- research

---

# 32. Blue Team / SOC Simulation

A later version should include defensive exercises.

Possible lab:

```text
Web Server
    |
    +--> Application Logs
    |
    +--> System Logs
    |
    +--> Network Traffic
              |
              v
             SIEM
              |
              v
           Student
              |
              v
       Investigate Incident
```

Students could:

- investigate suspicious login activity
- identify malicious traffic
- analyze logs
- create detection rules
- respond to simulated incidents
- produce incident reports

---

# 33. Student Portfolio

Each student should eventually have a cybersecurity profile.

Example:

```text
IIC CyberLab Profile

Overall Competency: 78/100

Skills:
Web Security       88
Linux              83
Networking         76
Forensics          61
Cryptography       57

Challenges Solved: 64
CTF Competitions: 5
Badges: 8

Selected Achievements:
- Web Security Intermediate
- Linux Security Practitioner
- CTF Finalist
```

The student should be able to export a shareable portfolio or certificate where institutionally appropriate.

---

# 34. Badges

Badge system should support:

- badge name
- description
- criteria
- icon
- skill association
- issuer
- issue date

Examples:

- Linux Fundamentals
- Web Security Beginner
- Network Analysis
- CTF Participant
- CTF Winner
- Blue Team Fundamentals

Badges should be evidence-based rather than merely decorative.

---

# 35. Faculty Challenge Authoring

Faculty should have a challenge builder.

Fields:

- title
- description
- learning objective
- category
- difficulty
- estimated time
- skills
- prerequisites
- points
- hints
- instructions
- environment
- validation method

The challenge should support a preview before publishing.

---

# 36. Student Challenge Authoring

Future feature.

Advanced students may submit challenges.

Workflow:

```text
Student creates challenge
        ↓
SUBMITTED
        ↓
Faculty review
        ↓
Security review
        ↓
Approved?
      /    \
    NO      YES
    |        |
Feedback   Publish
```

Never allow student-created infrastructure to automatically become trusted infrastructure.

---

# 37. Database Design

Recommended core entities:

```text
users
roles
permissions
user_roles

courses
modules
enrollments

skills
skill_relationships

challenges
challenge_versions
challenge_skills
challenge_prerequisites
challenge_hints

lab_templates
lab_instances
lab_sessions

submissions
submission_attempts

competitions
competition_challenges
competition_participants
teams
team_members

scores
leaderboards

badges
student_badges

notifications

audit_logs

system_settings
```

Use foreign keys, indexes and constraints properly.

Do not create a single giant `users` or `challenges` JSON table.

---

# 38. API Requirements

The backend should expose REST APIs initially.

Example groups:

```text
/api/v1/auth
/api/v1/users
/api/v1/challenges
/api/v1/labs
/api/v1/submissions
/api/v1/competitions
/api/v1/leaderboards
/api/v1/skills
/api/v1/analytics
/api/v1/badges
/api/v1/admin
```

All APIs must enforce authorization server-side.

Frontend visibility is not security.

---

# 39. Example API Endpoints

```text
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
GET    /api/v1/me

GET    /api/v1/challenges
GET    /api/v1/challenges/{id}
POST   /api/v1/challenges
PATCH  /api/v1/challenges/{id}
POST   /api/v1/challenges/{id}/publish

POST   /api/v1/labs/{challenge_id}/launch
GET    /api/v1/labs/sessions
POST   /api/v1/labs/{session_id}/reset
POST   /api/v1/labs/{session_id}/terminate

POST   /api/v1/challenges/{id}/submit

GET    /api/v1/leaderboards
GET    /api/v1/skills/me
GET    /api/v1/analytics/class/{id}

POST   /api/v1/competitions
GET    /api/v1/competitions/{id}
```

Exact endpoint naming can be adjusted during implementation, but consistency is mandatory.

---

# 40. API Security

Implement:

- authentication
- authorization
- input validation
- rate limiting
- CSRF protection where applicable
- secure cookies/token handling
- request logging
- audit logging
- server-side authorization
- parameterized queries
- output encoding
- security headers
- secret management

Never trust:

- challenge IDs from frontend
- user roles sent by frontend
- score values sent by frontend
- lab status sent by frontend
- competition status sent by frontend

---

# 41. Frontend Requirements

The interface should be responsive.

Supported:

- desktop
- laptop
- tablet
- mobile

Primary pages:

```text
/login

/dashboard

/challenges
/challenges/[id]

/labs
/labs/[session]

/competitions
/competitions/[id]
/leaderboard

/skills

/profile

/faculty
/faculty/challenges
/faculty/students
/faculty/analytics

/admin
/admin/users
/admin/labs
/admin/infrastructure
```

The UI should clearly distinguish:

- learning content
- active lab environments
- competitions
- administrative actions

---

# 42. Student Dashboard UX

The student dashboard should show:

```text
Welcome

Current Progress
[Progress bar]

Active Lab
[Launch/Continue]

Recommended Challenges
[Cards]

Recent Activity
[Timeline]

Skills
[Chart]

Achievements
[Badges]

Competition Rank
[Rank]
```

Avoid information overload.

---

# 43. Faculty Dashboard UX

Faculty dashboard should prioritize:

```text
Students requiring attention
Challenge performance
Class competency
Recent submissions
Active labs
Upcoming competitions
```

Charts should be useful and interpretable.

---

# 44. Infrastructure Management

Lab administrators need:

- VM template management
- container template management
- resource limits
- lab network management
- active session monitoring
- forced termination
- reset
- health checks
- capacity monitoring

The platform should never expose raw Proxmox credentials to students.

The backend/orchestrator should mediate infrastructure operations.

---

# 45. Lab Orchestrator

Create a dedicated service/module for infrastructure operations.

Conceptually:

```text
API
 |
 v
Lab Orchestrator
 |
 +--> Proxmox Adapter
 |
 +--> Docker Adapter
 |
 +--> Network Adapter
 |
 +--> Credential Adapter
```

This abstraction allows infrastructure to change without rewriting the entire application.

---

# 46. Infrastructure Adapter Interface

Conceptually:

```python
class LabProvider:
    def provision(self, template, config):
        ...

    def start(self, instance):
        ...

    def stop(self, instance):
        ...

    def reset(self, instance):
        ...

    def destroy(self, instance):
        ...

    def get_status(self, instance):
        ...
```

Concrete implementations:

```text
ProxmoxLabProvider
DockerLabProvider
```

Do not tightly couple business logic to Proxmox API calls.

---

# 47. Observability

The platform must provide:

## Application logs

- request ID
- timestamp
- user ID where appropriate
- endpoint
- status
- error information

## Infrastructure metrics

- CPU
- RAM
- disk
- VM count
- active sessions
- provisioning failures

## Security events

- login failures
- privilege changes
- challenge publishing
- lab launches
- lab resets
- suspicious submissions
- administrative actions

---

# 48. Audit Logging

Audit logs should be append-oriented and difficult for ordinary users to modify.

Important events:

- login
- logout
- role change
- challenge creation
- challenge modification
- challenge publication
- lab creation
- lab destruction
- flag submission
- competition modification
- administrator actions

Example:

```json
{
  "event": "lab.launch",
  "user_id": "user-id",
  "lab_id": "lab-id",
  "timestamp": "...",
  "source": "...",
  "result": "success"
}
```

Do not store secrets in logs.

---

# 49. Data Privacy

The system will handle student information and therefore must implement privacy-by-design.

Requirements:

- collect only necessary data
- pseudonymize data for research
- restrict access based on role
- encrypt data in transit
- encrypt sensitive data at rest where appropriate
- maintain audit trails
- define retention periods
- provide controlled research exports
- avoid exposing private student data on public leaderboards

Research datasets should preferably use anonymized identifiers.

---

# 50. Security Principles

The project must follow:

## Principle 1 — Least privilege

Users receive only necessary permissions.

## Principle 2 — Defense in depth

Do not rely on one firewall or one authorization check.

## Principle 3 — Zero trust between lab environments

Treat every lab as potentially compromised.

## Principle 4 — Disposable infrastructure

Students should not be able to permanently alter shared lab templates.

## Principle 5 — Server-side enforcement

Never trust client-side state.

## Principle 6 — Secure defaults

A new lab should start isolated.

## Principle 7 — Auditability

Important administrative/security actions must be traceable.

---

# 51. Backup Strategy

Back up:

- PostgreSQL database
- challenge definitions
- configuration
- important lab templates
- platform secrets/configuration through secure secret-management practices

Do not blindly back up every temporary student VM.

Use:

```text
Database backup
+
Configuration backup
+
Golden VM/template backup
```

Temporary lab instances should be disposable.

---

# 52. Disaster Recovery

Define:

- Recovery Point Objective (RPO)
- Recovery Time Objective (RTO)
- backup schedule
- restore procedure
- emergency admin access
- infrastructure rebuild procedure

The platform should be reproducible enough that a failed application server can be rebuilt from documented infrastructure configuration.

---

# 53. Testing Strategy

Testing must exist at multiple levels.

## Unit tests

Backend:

- services
- validators
- scoring
- authorization

Frontend:

- utility functions
- critical components

## Integration tests

- API + database
- authentication
- submissions
- scoring
- lab orchestration mocks

## End-to-end tests

Example:

```text
Login
 ↓
Open challenge
 ↓
Launch lab
 ↓
Submit flag
 ↓
Receive score
 ↓
Leaderboard updates
```

## Security testing

Test:

- IDOR
- privilege escalation
- injection
- authentication bypass
- rate-limit bypass
- insecure direct access to lab resources
- unauthorized challenge access
- unauthorized score manipulation

---

# 54. Definition of Done — MVP

The MVP is complete when all of the following work:

### Student

- [ ] Login
- [ ] View challenges
- [ ] Filter challenges
- [ ] Open challenge
- [ ] Launch lab
- [ ] Connect to lab
- [ ] Submit flag
- [ ] Receive result
- [ ] Earn points
- [ ] View leaderboard
- [ ] View progress

### Faculty

- [ ] Create challenge
- [ ] Edit challenge
- [ ] Add skills
- [ ] Add hints
- [ ] Publish challenge
- [ ] View student submissions
- [ ] View analytics

### Infrastructure

- [ ] Provision isolated lab
- [ ] Start lab
- [ ] Stop lab
- [ ] Reset lab
- [ ] Expire lab
- [ ] Enforce resource limits
- [ ] Record lab events

### Security

- [ ] RBAC
- [ ] Server-side authorization
- [ ] Audit logs
- [ ] Rate limiting
- [ ] Network isolation
- [ ] Secrets not exposed to frontend
- [ ] No direct student access to infrastructure APIs

---

# 55. Phase Roadmap

## Phase 0 — Architecture and Threat Model

Deliver:

- architecture
- threat model
- network design
- data model
- authentication design
- deployment design

## Phase 1 — Platform MVP

Deliver:

- authentication
- users/roles
- challenge catalogue
- challenge management
- submissions
- scoring
- leaderboard
- basic analytics

## Phase 2 — Cyber Range

Deliver:

- Docker labs
- VM labs
- provisioning
- reset
- expiration
- resource quotas
- isolated networks

## Phase 3 — Competition Platform

Deliver:

- competitions
- teams
- event scheduling
- competition leaderboard
- event analytics

## Phase 4 — Skill Intelligence

Deliver:

- skill taxonomy
- skill profiles
- competency scoring
- faculty analytics
- badges

## Phase 5 — Adaptive Learning

Deliver:

- challenge recommendation
- difficulty analytics
- learning paths
- personalized recommendations

## Phase 6 — Research Platform

Deliver:

- anonymized data export
- knowledge graph
- ML experiments
- GNN research
- research dashboards

---

# 56. Suggested Initial Challenge Set

The MVP should start with a small, high-quality challenge library.

Suggested initial distribution:

| Category | Beginner | Intermediate | Advanced |
|---|---:|---:|---:|
| Linux | 2 | 2 | 1 |
| Networking | 2 | 2 | 1 |
| Web Security | 3 | 3 | 1 |
| Cryptography | 2 | 2 | 1 |
| Forensics | 2 | 2 | 1 |
| OSINT | 2 | 1 | 1 |
| Secure Coding | 2 | 2 | 1 |
| Blue Team | 2 | 2 | 1 |

Start with approximately 35–40 challenges.

Quality is more important than quantity.

---

# 57. Example Beginner Challenge

```text
Title:
Basic Linux Investigation

Category:
Linux

Difficulty:
Beginner

Objective:
Practice Linux filesystem navigation and basic investigation.

Skills:
- Linux CLI
- Filesystem
- Basic command usage

Environment:
Docker

Expected duration:
20 minutes

Points:
100

Validation:
Flag submission
```

---

# 58. Example Intermediate Challenge

```text
Title:
Suspicious Web Request Investigation

Category:
Web Security / Blue Team

Difficulty:
Intermediate

Objective:
Identify a suspicious request in application logs and determine
the attack technique.

Environment:
Docker + log dataset

Skills:
- HTTP
- Log analysis
- Web security
- Incident investigation

Expected duration:
45 minutes
```

---

# 59. Example Advanced Challenge

```text
Title:
Compromised Multi-Service Network

Category:
Network Security / Blue Team

Difficulty:
Advanced

Environment:
Multiple isolated VMs

Topology:

Client
  |
Web Server
  |
Database

Additional:
DNS
Log server
Monitoring

Objective:
Investigate a simulated compromise and produce an incident report.
```

---

# 60. LLM/AI Development Instructions

This document is intended to be usable as a source of truth for an AI coding agent.

The AI agent must NOT attempt to generate the entire platform in one step.

It should work incrementally.

Recommended sequence:

```text
1. Understand requirements
2. Identify ambiguities
3. Create architecture
4. Create repository structure
5. Create database schema
6. Implement authentication
7. Implement challenge management
8. Implement submission/scoring
9. Implement frontend
10. Implement lab orchestration
11. Implement competitions
12. Implement analytics
13. Add security hardening
14. Add tests
15. Deploy
```

Each stage must produce a runnable system before moving to the next major stage.

---

# 61. AI Coding Agent Rules

The coding agent must:

1. Prefer simple maintainable architecture.
2. Avoid premature microservices.
3. Keep infrastructure adapters separate from business logic.
4. Use typed models.
5. Validate all external input.
6. Enforce authorization server-side.
7. Write migrations rather than manually modifying production databases.
8. Add tests for important functionality.
9. Document configuration.
10. Never hard-code secrets.
11. Use environment variables or secure secret management.
12. Never expose Proxmox credentials to the frontend.
13. Never allow users to directly execute arbitrary host commands.
14. Treat lab infrastructure as untrusted.
15. Log security-relevant actions.
16. Keep frontend and backend responsibilities clear.
17. Use API versioning.
18. Avoid unnecessary dependencies.
19. Keep deployment reproducible.
20. Explain important architectural decisions in documentation.

---

# 62. AI Agent Development Workflow

For each implementation task:

### Step 1 — Inspect

Inspect:

- existing repository
- package configuration
- environment
- architecture
- existing code

### Step 2 — Plan

Describe:

- files to create/change
- database changes
- APIs
- UI changes
- tests

### Step 3 — Implement

Make the smallest coherent implementation.

### Step 4 — Test

Run:

- unit tests
- integration tests where applicable
- lint
- type checking
- build

### Step 5 — Review

Check:

- authorization
- security
- edge cases
- error handling
- database constraints

### Step 6 — Document

Update relevant documentation.

Do not silently skip failed tests.

---

# 63. Recommended Repository Structure

A modular monorepo is recommended initially.

```text
iic-cyberlab/
│
├── apps/
│   ├── web/
│   │   ├── app/
│   │   ├── components/
│   │   ├── lib/
│   │   └── tests/
│   │
│   └── api/
│       ├── app/
│       │   ├── api/
│       │   ├── core/
│       │   ├── models/
│       │   ├── schemas/
│       │   ├── services/
│       │   ├── repositories/
│       │   └── workers/
│       └── tests/
│
├── infrastructure/
│   ├── docker/
│   ├── proxmox/
│   ├── ansible/
│   ├── networking/
│   └── monitoring/
│
├── challenges/
│   ├── linux/
│   ├── web/
│   ├── networking/
│   ├── crypto/
│   ├── forensics/
│   └── blue-team/
│
├── docs/
│   ├── architecture/
│   ├── security/
│   ├── deployment/
│   └── research/
│
├── scripts/
├── .env.example
├── docker-compose.yml
└── README.md
```

This is a recommendation, not a rigid requirement. The implementation agent may improve the structure while preserving separation of concerns.

---

# 64. Environment Configuration

Never commit secrets.

Provide:

```text
.env.example
```

Possible variables:

```env
DATABASE_URL=
REDIS_URL=

AUTH_ISSUER_URL=
AUTH_CLIENT_ID=
AUTH_CLIENT_SECRET=

PROXMOX_API_URL=
PROXMOX_API_TOKEN_ID=
PROXMOX_API_TOKEN_SECRET=

OBJECT_STORAGE_ENDPOINT=
OBJECT_STORAGE_ACCESS_KEY=
OBJECT_STORAGE_SECRET_KEY=

APP_SECRET=
```

Production secrets must be managed securely.

---

# 65. Deployment Model

For the first deployment:

```text
                    IIC SERVER
                       |
             +---------+---------+
             |                   |
          Web/API            PostgreSQL
             |
           Redis
             |
       Lab Orchestrator
             |
          Proxmox
             |
     +-------+-------+
     |       |       |
    VM      VM      VM
```

The application can initially be deployed using Docker Compose.

As scale increases, orchestration can be reconsidered.

Do not introduce Kubernetes unless there is an actual operational requirement.

---

# 66. Performance Requirements

MVP target:

- support at least 100 concurrent authenticated users
- support at least 50 concurrent lab sessions depending on available infrastructure
- normal dashboard/API responses should generally be under 500 ms excluding long-running infrastructure operations
- lab provisioning should be asynchronous
- frontend must never block while waiting for a VM to provision

The infrastructure capacity should be benchmarked before claiming a larger concurrency target.

---

# 67. Reliability Requirements

The platform should:

- gracefully handle lab provisioning failures
- prevent duplicate lab sessions where policy disallows them
- clean up abandoned sessions
- retry transient infrastructure failures
- avoid orphaned VMs
- maintain database consistency
- maintain score consistency
- survive application restart without losing active session state

---

# 68. Accessibility and Usability

The web application should:

- use semantic HTML
- provide keyboard navigation
- maintain readable contrast
- provide meaningful error messages
- avoid relying only on color
- work on common laptop and mobile screen sizes
- provide loading and empty states
- provide confirmation for destructive actions

---

# 69. Notifications

Future notifications:

- challenge assignment
- lab expiration
- competition starting
- competition ending
- badge earned
- challenge published
- faculty announcements

Channels can later include:

- in-app
- email
- institutional messaging

Do not tightly couple notifications to one provider.

---

# 70. Research Data Pipeline

For research:

```text
Operational Database
        |
        v
Approved Data Extraction
        |
        v
Pseudonymization
        |
        v
Research Dataset
        |
        +--> ML
        +--> Statistics
        +--> Graph Analysis
        +--> Visualization
```

Research data must not be copied casually from production into notebooks.

---

# 71. Research Metrics

Potential metrics:

### Learning

- challenge completion rate
- skill improvement
- pre/post assessment
- retention
- time-to-competency

### Engagement

- active sessions
- challenges attempted
- hints used
- return frequency

### Challenge quality

- success rate
- median solve time
- failure rate
- abandonment rate

### Recommendation quality

- recommendation acceptance
- recommendation completion
- performance improvement

---

# 72. Possible Research Hypotheses

## H1

Adaptive challenge recommendations improve cybersecurity practical performance compared with fixed challenge sequences.

## H2

Practical cyber-range performance is correlated with competency demonstrated in cybersecurity assessments.

## H3

Gamification increases voluntary engagement with cybersecurity practical exercises.

## H4

Skill-graph-based recommendations improve learning-path relevance.

These hypotheses can be tested only after appropriate data collection and research approval.

---

# 73. Future Industry Integration

A future version may support:

```text
Student Skill Profile
        ↓
Employer Skill Requirements
        ↓
Skill Matching
        ↓
Internship Recommendation
```

This should remain a future phase and must not be required for the initial MVP.

---

# 74. Future Inter-College Platform

If IIC later wants to host inter-college competitions:

```text
IIC CyberLab
      |
      +---- IIC Students
      |
      +---- College A
      |
      +---- College B
      |
      +---- College C
```

Use tenant/event isolation so external participants cannot access internal IIC resources.

External competition infrastructure should be separated from internal institutional resources.

---

# 75. Threat Model

Major threats:

## Student escapes lab

Mitigation:

- virtualization isolation
- VLAN/firewall isolation
- no privileged host access
- restricted network paths
- disposable environments

## Student manipulates score

Mitigation:

- server-side scoring
- signed/validated operations
- no client-controlled score

## Student accesses another student's lab

Mitigation:

- per-session authorization
- isolated network
- random/temporary credentials
- resource ownership checks

## Student attacks infrastructure

Mitigation:

- dedicated range network
- firewall
- restricted management plane
- separate management interfaces
- monitoring

## Administrator account compromise

Mitigation:

- strong authentication
- least privilege
- audit logging
- secure secret storage
- optional MFA

## Database compromise

Mitigation:

- network isolation
- least privilege
- encrypted backups
- secure credentials
- parameterized queries

---

# 76. Critical Security Rule

The following must never happen:

```text
Student Browser
      |
      +------> Proxmox API
```

Correct:

```text
Student Browser
      |
      v
IIC CyberLab API
      |
      v
Lab Orchestrator
      |
      v
Proxmox API
```

Students must never receive infrastructure-management credentials.

---

# 77. Success Criteria

The project is successful when IIC can:

1. Give a class of students practical cybersecurity labs.
2. Provision labs without manually configuring each student environment.
3. Reset compromised environments automatically.
4. Conduct an internal CTF.
5. See student practical performance.
6. Identify cybersecurity skill gaps.
7. Create and reuse challenges.
8. Keep the vulnerable environment isolated from production.
9. Generate useful research data under appropriate governance.
10. Extend the platform without rewriting its foundation.

---

# 78. Minimum Viable Product Definition

The absolute minimum useful product is:

```text
Authentication
      ↓
Challenge Catalogue
      ↓
Challenge Detail
      ↓
Launch Docker Lab
      ↓
Student Solves Lab
      ↓
Submit Flag
      ↓
Server Validates
      ↓
Score
      ↓
Leaderboard
      ↓
Faculty Dashboard
```

Do not delay the MVP by implementing AI, GNNs, complex competitions or advanced analytics first.

---

# 79. Recommended First Technical Milestone

Build one complete vertical slice:

## "Linux Fundamentals Lab"

Flow:

```text
Student logs in
      ↓
Opens Linux Fundamentals
      ↓
Clicks Launch
      ↓
Docker container starts
      ↓
Student receives terminal/access method
      ↓
Student investigates filesystem
      ↓
Finds flag
      ↓
Submits flag
      ↓
API validates
      ↓
100 points awarded
      ↓
Leaderboard updated
```

Once this works end-to-end, generalize the architecture.

This is preferable to building dozens of incomplete screens.

---

# 80. Acceptance Test for First Vertical Slice

The following scenario must pass:

```text
GIVEN a valid student account

WHEN the student opens an approved Linux challenge

AND launches the lab

THEN an isolated environment is created

AND the student receives temporary access

WHEN the student submits an incorrect flag

THEN the system records an unsuccessful attempt

AND does not award points

WHEN the student submits the correct flag

THEN the system records a successful submission

AND awards the configured points

AND updates the student's progress

AND updates the leaderboard

WHEN the lab expires

THEN access is revoked

AND the environment is cleaned up
```

---

# 81. Development Priorities

Use this order:

### P0 — Mandatory

- authentication
- RBAC
- database
- challenge catalogue
- challenge authoring
- submissions
- scoring
- basic lab execution
- isolation
- audit logs
- basic leaderboard

### P1 — Important

- competitions
- faculty analytics
- skill taxonomy
- badges
- Docker lab templates
- VM support
- automatic cleanup

### P2 — Advanced

- adaptive recommendations
- Blue Team/SOC labs
- student challenge authoring
- knowledge graph
- ML analytics

### P3 — Research/Expansion

- GNN
- competency prediction
- adaptive learning research
- inter-college federation
- industry skill matching

---

# 82. Final Product Concept

The final platform should feel like a combination of:

```text
Cyber Range
      +
CTF Platform
      +
Learning Management System
      +
Skill Assessment Platform
      +
Security Analytics
```

But it should remain focused specifically on **cybersecurity education**.

The product identity should be:

# IIC CyberLab

**Learn. Practice. Compete. Defend.**

---

# 83. Final Instruction to the Implementing LLM

You are implementing IIC CyberLab from this specification.

Do not attempt to implement every future feature immediately.

Start with the MVP and create a working vertical slice.

Before writing large amounts of code:

1. inspect the repository;
2. propose the implementation architecture;
3. identify assumptions;
4. create the database schema;
5. create the application skeleton;
6. implement authentication and RBAC;
7. implement challenges;
8. implement submissions and scoring;
9. implement one Docker-based lab;
10. connect the complete student flow;
11. add tests;
12. verify security;
13. only then expand to VM provisioning and advanced features.

Whenever a feature involves cybersecurity infrastructure, prefer the safest implementation that satisfies the educational objective.

Never provide students with access to host-level infrastructure controls.

Never expose Proxmox, Docker host, database, Redis, monitoring or administrative credentials to students.

Never allow arbitrary commands to execute on the host based directly on untrusted user input.

Treat every cyber-range environment as potentially compromised.

Keep the application modular so that future research features can be added without redesigning the core platform.

The implementation should prioritize:

**Security → Correctness → Maintainability → Usability → Scalability → Advanced intelligence.**

