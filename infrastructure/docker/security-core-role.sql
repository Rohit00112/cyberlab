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
GRANT SELECT (id) ON public.challenges TO cyberlab_security_writer;
