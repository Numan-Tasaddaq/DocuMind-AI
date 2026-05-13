DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'documind_app') THEN
    CREATE ROLE documind_app LOGIN PASSWORD 'change_this_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
  ELSE
    ALTER ROLE documind_app WITH LOGIN PASSWORD 'change_this_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
  END IF;
END
$$;

REVOKE ALL ON DATABASE documind_ai FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE documind_ai TO documind_app;
GRANT USAGE ON SCHEMA public TO documind_app;
GRANT SELECT, INSERT, UPDATE ON TABLE app_users TO documind_app;
GRANT SELECT, INSERT ON TABLE user_login_history TO documind_app;
GRANT USAGE, SELECT ON SEQUENCE user_login_history_id_seq TO documind_app;

