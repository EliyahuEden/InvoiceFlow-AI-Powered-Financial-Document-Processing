-- Executed once by the postgres image on first start (as the bootstrap superuser).
-- Creates the least-privilege application role. Migrations run as the owner role
-- (POSTGRES_USER); the API and worker connect as `invoiceflow_app`, which is NOT a
-- superuser and NOT the table owner, so PostgreSQL row-level security applies to it.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'invoiceflow_app') THEN
    CREATE ROLE invoiceflow_app LOGIN PASSWORD 'invoiceflow_app_dev';
  END IF;
END $$;

GRANT CONNECT ON DATABASE invoiceflow TO invoiceflow_app;
GRANT USAGE ON SCHEMA public TO invoiceflow_app;

-- Test database used by the pytest integration suite.
CREATE DATABASE invoiceflow_test;
\connect invoiceflow_test
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
GRANT CONNECT ON DATABASE invoiceflow_test TO invoiceflow_app;
GRANT USAGE ON SCHEMA public TO invoiceflow_app;
