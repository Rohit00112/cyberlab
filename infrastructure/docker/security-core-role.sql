-- Apply against the cyberlab database as its owner after schema migrations.
-- This dedicated Rust service identity needs only a few SELECT columns.
\set ON_ERROR_STOP on
\getenv core_password SECURITY_CORE_DB_PASSWORD
\if :{?core_password}
\else
  \echo 'SECURITY_CORE_DB_PASSWORD is required'
  \quit 1
\endif

SELECT 'CREATE ROLE cyberlab_security_core LOGIN NOINHERIT'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cyberlab_security_core')
\gexec

ALTER ROLE cyberlab_security_core
  WITH LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  PASSWORD :'core_password';

GRANT CONNECT ON DATABASE cyberlab TO cyberlab_security_core;
GRANT USAGE ON SCHEMA public TO cyberlab_security_core;

-- Reapply grants safely if the script runs after a schema migration.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM cyberlab_security_core;
-- Table-level REVOKE does not remove prior column-level grants. Reset these
-- before granting the current allowlist, including on subsequent deployments.
DO $$
DECLARE column_grant record;
BEGIN
  FOR column_grant IN
    SELECT n.nspname, c.relname, a.attname, acl.privilege_type
    FROM pg_class AS c
    JOIN pg_namespace AS n ON n.oid = c.relnamespace
    JOIN pg_attribute AS a ON a.attrelid = c.oid
    CROSS JOIN LATERAL aclexplode(a.attacl) AS acl
    WHERE n.nspname = 'public' AND a.attnum > 0 AND NOT a.attisdropped
      AND acl.grantee = 'cyberlab_security_core'::regrole
  LOOP
    EXECUTE format('REVOKE %s (%I) ON TABLE %I.%I FROM cyberlab_security_core',
      column_grant.privilege_type, column_grant.attname,
      column_grant.nspname, column_grant.relname);
  END LOOP;
END $$;
GRANT SELECT (id, status, category, difficulty, points, created_at)
  ON public.challenges TO cyberlab_security_core;
GRANT SELECT (id, display_name)
  ON public.users TO cyberlab_security_core;
GRANT SELECT (user_id, is_correct, earned_points, created_at)
  ON public.submissions TO cyberlab_security_core;

ALTER ROLE cyberlab_security_core IN DATABASE cyberlab
  SET default_transaction_read_only = on;

-- Independent writer, limited to challenge publication and its audit event.
SELECT 'CREATE ROLE cyberlab_security_writer LOGIN NOINHERIT'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cyberlab_security_writer')
\gexec
\getenv writer_password SECURITY_CORE_WRITE_DB_PASSWORD
\if :{?writer_password}
\else
  \echo 'SECURITY_CORE_WRITE_DB_PASSWORD is required'
  \quit 1
\endif
ALTER ROLE cyberlab_security_writer
  WITH LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  PASSWORD :'writer_password';
GRANT CONNECT ON DATABASE cyberlab TO cyberlab_security_writer;
GRANT USAGE ON SCHEMA public TO cyberlab_security_writer;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM cyberlab_security_writer;
DO $$
DECLARE column_grant record;
BEGIN
  FOR column_grant IN
    SELECT n.nspname, c.relname, a.attname, acl.privilege_type
    FROM pg_class AS c
    JOIN pg_namespace AS n ON n.oid = c.relnamespace
    JOIN pg_attribute AS a ON a.attrelid = c.oid
    CROSS JOIN LATERAL aclexplode(a.attacl) AS acl
    WHERE n.nspname = 'public' AND a.attnum > 0 AND NOT a.attisdropped
      AND acl.grantee = 'cyberlab_security_writer'::regrole
  LOOP
    EXECUTE format('REVOKE %s (%I) ON TABLE %I.%I FROM cyberlab_security_writer',
      column_grant.privilege_type, column_grant.attname,
      column_grant.nspname, column_grant.relname);
  END LOOP;
END $$;
GRANT SELECT (id, slug, flag_hash) ON public.challenges TO cyberlab_security_writer;
GRANT UPDATE (status, version, updated_at) ON public.challenges TO cyberlab_security_writer;
GRANT SELECT (version) ON public.challenges TO cyberlab_security_writer;
GRANT INSERT (id, event, user_id, target_id, ip_address) ON public.audit_logs TO cyberlab_security_writer;
GRANT DELETE ON public.challenges TO cyberlab_security_writer;
GRANT SELECT (status) ON public.challenges TO cyberlab_security_writer;
GRANT UPDATE (title, description, instructions, category, difficulty, points,
  estimated_minutes, skills, prerequisites, hints, hint_penalty, flag_hash,
  flag_format, environment_type, lab_config) ON public.challenges TO cyberlab_security_writer;
-- Rust challenge creation supplies only these explicit fields. Keep INSERT
-- column-scoped so new schema fields are not writable without review.
GRANT INSERT (id, slug, title, description, instructions, category,
  difficulty, points, estimated_minutes, skills, prerequisites, hints,
  hint_penalty, flag_hash, flag_format, environment_type, lab_config,
  author_id, status, version) ON public.challenges TO cyberlab_security_writer;
GRANT SELECT (id, slug, name) ON public.skills TO cyberlab_security_writer;
GRANT DELETE, INSERT ON public.challenge_skills TO cyberlab_security_writer;
-- The Rust skill sync deletes links using this WHERE column.
GRANT SELECT (challenge_id) ON public.challenge_skills TO cyberlab_security_writer;
GRANT SELECT (id) ON public.challenges TO cyberlab_security_writer;
GRANT SELECT (status) ON public.challenges TO cyberlab_security_writer;
GRANT INSERT (id, challenge_id, user_id, is_correct, earned_points)
  ON public.submissions TO cyberlab_security_writer;
GRANT INSERT (details) ON public.audit_logs TO cyberlab_security_writer;
-- Correct solve: revalidate flag and lab state, then atomically update the
-- submission ledger, score ledger, competency profiles and audit record.
GRANT SELECT (id, is_active) ON public.users TO cyberlab_security_writer;
GRANT SELECT (points, hint_penalty, difficulty_score, flag_hash)
  ON public.challenges TO cyberlab_security_writer;
GRANT SELECT (id, user_id, challenge_id, status, flag_hash, expires_at)
  ON public.lab_instances TO cyberlab_security_writer;
GRANT SELECT (user_id, challenge_id) ON public.hint_reveals TO cyberlab_security_writer;
GRANT SELECT (id, challenge_id, user_id, is_correct)
  ON public.submissions TO cyberlab_security_writer;
GRANT UPDATE (earned_points) ON public.submissions TO cyberlab_security_writer;
GRANT INSERT (id, user_id, challenge_id, event_type, points, current_total, is_first_blood, is_frozen)
  ON public.score_events TO cyberlab_security_writer;
GRANT SELECT (user_id, competition_id, points) ON public.score_events TO cyberlab_security_writer;
GRANT SELECT (challenge_id, skill_id) ON public.challenge_skills TO cyberlab_security_writer;
GRANT INSERT (id, user_id, skill_id, competency_level)
  ON public.user_skill_profiles TO cyberlab_security_writer;
GRANT UPDATE (competency_level, last_updated)
  ON public.user_skill_profiles TO cyberlab_security_writer;
GRANT SELECT (user_id, skill_id, competency_level)
  ON public.user_skill_profiles TO cyberlab_security_writer;
GRANT INSERT (id, slug, title, description, rules, start_at, end_at,
  registration_ends_at, allow_teams, max_team_size, scoring_mode, status,
  created_by, freeze_leaderboard)
  ON public.competitions TO cyberlab_security_writer;
-- RETURNING reads id, and ON CONFLICT (slug) checks the arbiter column.
-- Keep these column-scoped; the writer cannot read competition details.
GRANT SELECT (id, slug) ON public.competitions TO cyberlab_security_writer;
-- Edit locks and rechecks the state before the update; no broad table access.
GRANT SELECT (status) ON public.competitions TO cyberlab_security_writer;
GRANT UPDATE (title, description, rules, start_at, end_at,
  registration_ends_at, allow_teams, max_team_size, scoring_mode, updated_at)
  ON public.competitions TO cyberlab_security_writer;
-- Competition link ownership: lock status, resolve published challenges,
-- compute the next position, and insert/delete links with a required audit.
GRANT SELECT (scoring_mode) ON public.competitions TO cyberlab_security_writer;
GRANT SELECT (id, competition_id, challenge_id, position)
  ON public.competition_challenges TO cyberlab_security_writer;
GRANT INSERT (id, competition_id, challenge_id, points, position)
  ON public.competition_challenges TO cyberlab_security_writer;
GRANT DELETE ON public.competition_challenges TO cyberlab_security_writer;
-- Register/unregister participants atomically with mandatory audit records.
GRANT SELECT (id, competition_id, user_id, team_id)
  ON public.competition_participants TO cyberlab_security_writer;
GRANT INSERT (id, competition_id, user_id)
  ON public.competition_participants TO cyberlab_security_writer;
GRANT DELETE ON public.competition_participants TO cyberlab_security_writer;
-- Unregister must also revoke the participant's existing team membership.
GRANT SELECT (team_id, user_id) ON public.team_members TO cyberlab_security_writer;
GRANT DELETE ON public.team_members TO cyberlab_security_writer;
-- Team creation and joining: serialize on the competition, recheck eligibility,
-- assign membership, and commit the corresponding audit in one transaction.
GRANT SELECT (allow_teams, max_team_size) ON public.competitions TO cyberlab_security_writer;
GRANT SELECT (id, competition_id, name) ON public.teams TO cyberlab_security_writer;
GRANT INSERT (id, competition_id, name, created_by)
  ON public.teams TO cyberlab_security_writer;
GRANT INSERT (id, team_id, user_id, role)
  ON public.team_members TO cyberlab_security_writer;
GRANT UPDATE (team_id) ON public.competition_participants TO cyberlab_security_writer;
-- Competition leaderboard freeze and its audit must share one transaction.
GRANT UPDATE (freeze_leaderboard, frozen_at, updated_at)
  ON public.competitions TO cyberlab_security_writer;
-- Organizer status changes use the stored schedule in the Rust policy and
-- require the status mutation and transition audit in one transaction.
GRANT SELECT (start_at, end_at) ON public.competitions TO cyberlab_security_writer;
GRANT UPDATE (status) ON public.competitions TO cyberlab_security_writer;
-- Automatic scheduler writes use these same restricted columns and the audit
-- insert allowlist; no extra table-wide privileges are required.
-- Lab lease extension: recheck the owner and current expiration under a row
-- lock, update only the lease/timestamp, and insert the required audit atomically.
GRANT SELECT (created_at) ON public.lab_instances TO cyberlab_security_writer;
GRANT UPDATE (expires_at, updated_at) ON public.lab_instances TO cyberlab_security_writer;
-- Worker-only claim: lock the pending job and queued lab, commit both state
-- changes with an audit record before Python calls an external lab provider.
-- Do not grant config or provider connection details to the Rust writer.
GRANT SELECT (id, lab_instance_id, user_id, challenge_id, status)
  ON public.provisioning_jobs TO cyberlab_security_writer;
GRANT UPDATE (status, started_at, completed_at, error_message, updated_at)
  ON public.provisioning_jobs TO cyberlab_security_writer;
GRANT SELECT (challenge_id) ON public.lab_instances TO cyberlab_security_writer;
GRANT UPDATE (status, updated_at) ON public.lab_instances TO cyberlab_security_writer;
-- Terminal provisioning transactions commit provider metadata, expiry and
-- mandatory audit together, without exposing network configuration or flags.
GRANT UPDATE (provider_ref, container_id, container_name, flag_hash, flag_path,
  connection_hint, error_message) ON public.lab_instances TO cyberlab_security_writer;
