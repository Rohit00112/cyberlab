# Phase 5 — Adaptive Learning Design Spec

Date: 2026-09-13
Project: IIC CyberLab
PRD Reference: Phase 5, §28–§30

---

## Goal

Implement the Adaptive Learning backend (Phase 5 of the CyberLab PRD), enabling:
- Challenge recommendations personalized to each user's skill competency level
- Curated learning paths with per-user progress tracking
- Difficulty scoring that updates automatically based on submission patterns
- Explicit user skill profiles

---

## Context

### Existing Infrastructure

| Layer       | Technology           |
|-------------|----------------------|
| Backend     | FastAPI + SQLAlchemy |
| Database    | PostgreSQL           |
| Auth        | Keycloak + JWT       |
| Models      | `skills`, `challenges`, `challenge_skills`, `submissions`, `users` |

Phase 4 delivered:
- `skills` taxonomy
- `challenge_skills` linking challenges to skills
- `badges` system with competency scoring (initial)

Phase 5 builds on top of these by adding:
- Explicit user skill profiles
- Learning path data structures
- Dynamic recommendation logic
- Difficulty scoring refinement

---

## Design

### 1. Database Schema (New Tables)

#### `user_skill_profiles`
Tracks the competency level for each user per skill. Updated when a user submits a correct solution to a challenge that maps to that skill.

| Column             | Type      | Notes                             |
|--------------------|-----------|-----------------------------------|
| `id`               | UUID PK   |                                   |
| `user_id`          | UUID FK   | → users.id ON DELETE CASCADE      |
| `skill_id`         | UUID FK   | → skills.id ON DELETE CASCADE     |
| `competency_level` | Float     | 0.0 – 100.0 scale                 |
| `last_updated`     | Timestamp |                                   |

Unique constraint on `(user_id, skill_id)`.

#### `learning_paths`
Curated static learning sequences authored by faculty/admins.

| Column        | Type      | Notes |
|---------------|-----------|-------|
| `id`          | UUID PK   |       |
| `slug`        | String    | URL-safe, unique |
| `title`       | String    |       |
| `description` | Text      |       |
| `is_published`| Boolean   | Default false |
| `created_at`  | Timestamp |       |

#### `learning_path_steps`
Ordered list of challenges within a path.

| Column            | Type    | Notes |
|-------------------|---------|-------|
| `id`              | UUID PK |       |
| `learning_path_id`| UUID FK | → learning_paths.id ON DELETE CASCADE |
| `challenge_id`    | UUID FK | → challenges.id ON DELETE CASCADE |
| `step_order`      | Integer | ASC sort |

Unique constraint on `(learning_path_id, challenge_id)`.

---

### 2. Challenge Difficulty Scoring

The `challenges.points` (static) remains unchanged. A separate `difficulty_score` float column is added (or can reuse the existing `difficulty` enum as a seed and calculate separately — we add a column for computed score):

| Column                        | Type  | Notes |
|-------------------------------|-------|-------|
| `difficulty_score`            | Float | 0.0–1.0; higher = harder. Computed from submissions. |
| `difficulty_scored_at_count`  | Int   | Total submission count when `difficulty_score` was last computed. Default 0. |

**Algorithm (lightweight ELO-adjacent):**
```
difficulty_score = failures / (successes + failures)
```
- Recomputed when `current_submission_count - difficulty_scored_at_count >= 10`.
- Bootstrapped from: beginner = 0.2, intermediate = 0.5, advanced = 0.8 on first run.

This score influences the recommendation ranking (see §4) and can be surfaced in faculty analytics.

---

### 3. Competency Update Logic

When a submission is marked `correct`:
1. Fetch all `ChallengeSkill` records for the solved challenge.
2. For each skill:
   - Find or create `UserSkillProfile(user_id, skill_id)`.
   - Increment `competency_level` using the challenge's `difficulty_score`:
     ```
     gain = max(0.5, challenge.difficulty_score) * 10
     new_level = min(100.0, current + gain)
     ```
3. Update `last_updated`.

This is called directly from the submission service after a correct answer is verified (not a background job, to keep it simple).

---

### 4. Recommendation Logic

`RecommendationService.get_recommendations(user_id, limit=10)`:

1. Fetch solved `challenge_id` set for `user_id`.
2. Fetch `UserSkillProfile` for `user_id` (skill_id → competency_level map).
3. Query unsolved challenges (published, status = "published").
4. Score each unsolved challenge:
   ```
   skill_match_score = avg(user_competency[skill] for skill in challenge_skills)
   difficulty_gap = abs(user_avg_competency - challenge.difficulty_score * 100)
   score = skill_match_score - difficulty_gap * 0.3
   ```
5. Order by descending `score`. Return top N.

If user has no `UserSkillProfile` yet (new user), fall back to returning top-N beginner challenges ordered by points desc.

---

### 5. Learning Path Progress

`LearningPathService.get_path_with_progress(path_id, user_id)`:

- Load `LearningPath` + ordered `LearningPathStep`s.
- For each step, check if `challenge_id` is in the user's solved set.
- Return each step with `status`: `completed`, `unlocked`, or `locked`.
  - `completed` = solved
  - `unlocked` = first unsolved step (one at a time)
  - `locked` = all subsequent

---

### 6. API Endpoints

| Method | Route                          | Auth    | Purpose |
|--------|--------------------------------|---------|---------|
| GET    | `/api/v1/paths`                | Any     | List published learning paths |
| GET    | `/api/v1/paths/{id}`           | Auth    | Path detail + user progress |
| POST   | `/api/v1/paths` (admin)        | Admin   | Create learning path |
| POST   | `/api/v1/paths/{id}/steps`     | Admin   | Add step to path |
| GET    | `/api/v1/recommendations/challenges` | Auth | Personalized challenge recommendations |
| GET    | `/api/v1/users/{id}/skills`    | Auth    | User skill profile (competency per skill) |

---

### 7. Migration

A single Alembic migration adds:
- `user_skill_profiles` table
- `learning_paths` table
- `learning_path_steps` table
- `challenges.difficulty_score` column
- `challenges.difficulty_scored_at_count` column

---

### 8. File Structure (New Files)

```
apps/api/
  app/
    models/
      learning_paths.py       (LearningPath, LearningPathStep)
      skill_profiles.py       (UserSkillProfile)
    schemas/
      learning_path.py
      skill_profile.py
      recommendation.py
    services/
      recommendations.py      (RecommendationService)
      learning_paths.py       (LearningPathService)
      skill_profiles.py       (competency update logic)
    api/
      recommendations.py
      paths.py
  alembic/versions/
    YYYY_MM_DD_phase5_adaptive_learning.py
```

---

### 9. Out of Scope (Phase 5)

- ML models / embeddings for recommendations
- Anonymized data export (Phase 6)
- Real-time difficulty score updates via WebSocket
- Faculty analytics dashboard UI

---

## Testing

- Unit tests: scoring algorithm, competency update math
- Integration tests: recommendation endpoint returns expected challenges for a seeded user profile
- No mocked database (use test DB as per project convention)

---

## Success Criteria

1. A user who solves beginner challenges sees their skill `competency_level` increase.
2. `/api/v1/recommendations/challenges` returns unsolved challenges personalized to skill gaps.
3. A learning path has correct step statuses (completed / unlocked / locked) per user.
4. `difficulty_score` on challenges updates correctly based on success/failure ratios.
