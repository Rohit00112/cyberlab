-- Read-only production role attestation. Run against the migrated cyberlab DB.
\set ON_ERROR_STOP on
BEGIN READ ONLY;
DO $$
DECLARE
  reader text := 'cyberlab_security_core';
  writer text := 'cyberlab_security_writer';
BEGIN
  IF current_database() <> 'cyberlab' THEN
    RAISE EXCEPTION 'Role verification must target the cyberlab database';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = reader)
     OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = writer) THEN
    RAISE EXCEPTION 'Both dedicated Rust service roles must exist';
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_roles
    WHERE rolname IN (reader, writer)
      AND (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls)
  ) THEN
    RAISE EXCEPTION 'A Rust service role has forbidden cluster privileges';
  END IF;
  IF NOT has_column_privilege(writer, 'public.provisioning_jobs', 'status', 'UPDATE')
     OR NOT has_column_privilege(writer, 'public.lab_instances', 'provider_ref', 'UPDATE')
     OR NOT has_column_privilege(writer, 'public.lab_instances', 'flag_hash', 'UPDATE')
     OR NOT has_column_privilege(writer, 'public.audit_logs', 'details', 'INSERT')
  THEN
    RAISE EXCEPTION 'Rust writer is missing provisioning/audit grants';
  END IF;
  IF NOT has_column_privilege(reader, 'public.challenges', 'id', 'SELECT')
     OR NOT has_column_privilege(reader, 'public.submissions', 'earned_points', 'SELECT')
  THEN
    RAISE EXCEPTION 'Rust reader is missing catalog/leaderboard grants';
  END IF;
  IF has_column_privilege(reader, 'public.challenges', 'flag_hash', 'SELECT')
     OR has_column_privilege(reader, 'public.lab_instances', 'provider_ref', 'SELECT')
     OR has_column_privilege(reader, 'public.audit_logs', 'details', 'INSERT')
     OR has_column_privilege(writer, 'public.users', 'email', 'SELECT')
     OR has_column_privilege(writer, 'public.vpn_peers', 'public_key', 'UPDATE')
     OR has_table_privilege(writer, 'public.vpn_peers', 'DELETE')
  THEN
    RAISE EXCEPTION 'Rust role has privileges outside its allowlist';
  END IF;
  RAISE NOTICE 'Rust reader/writer column permissions verified';
END $$;
ROLLBACK;
