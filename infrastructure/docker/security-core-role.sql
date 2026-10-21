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
