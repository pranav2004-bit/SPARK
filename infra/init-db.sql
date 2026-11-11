-- SPARK dev database initialisation
-- Runs once when the postgres container is first created.
-- Phase 5: creates 6 isolated databases with dedicated least-privilege users.

-- ── Databases ──────────────────────────────────────────────────────────────────

CREATE DATABASE auth_db;
CREATE DATABASE user_db;
CREATE DATABASE resource_db;
CREATE DATABASE practice_db;
CREATE DATABASE notification_db;
CREATE DATABASE analytics_db;
CREATE DATABASE assessment_db;

-- ── Per-service users ──────────────────────────────────────────────────────────

CREATE USER auth_db_user         WITH PASSWORD 'auth_dev_password_2024';
CREATE USER user_db_user         WITH PASSWORD 'user_dev_password_2024';
CREATE USER resource_db_user     WITH PASSWORD 'resource_dev_password_2024';
CREATE USER practice_db_user     WITH PASSWORD 'practice_dev_password_2024';
CREATE USER notification_db_user WITH PASSWORD 'notification_dev_password_2024';
CREATE USER analytics_db_user    WITH PASSWORD 'analytics_dev_password_2024';
CREATE USER assessment_db_user   WITH PASSWORD 'assessment_dev_password_2024';

-- ── Lock down PUBLIC connect so cross-service access is impossible ─────────────
-- PostgreSQL 15+ revokes CREATE on public schema from PUBLIC by default,
-- but CONNECT on databases is still granted to PUBLIC unless revoked.

REVOKE CONNECT ON DATABASE auth_db         FROM PUBLIC;
REVOKE CONNECT ON DATABASE user_db         FROM PUBLIC;
REVOKE CONNECT ON DATABASE resource_db     FROM PUBLIC;
REVOKE CONNECT ON DATABASE practice_db     FROM PUBLIC;
REVOKE CONNECT ON DATABASE notification_db FROM PUBLIC;
REVOKE CONNECT ON DATABASE analytics_db    FROM PUBLIC;
REVOKE CONNECT ON DATABASE assessment_db   FROM PUBLIC;

-- Grant each user connect to ONLY its own database.

GRANT CONNECT ON DATABASE auth_db         TO auth_db_user;
GRANT CONNECT ON DATABASE user_db         TO user_db_user;
GRANT CONNECT ON DATABASE resource_db     TO resource_db_user;
GRANT CONNECT ON DATABASE practice_db     TO practice_db_user;
GRANT CONNECT ON DATABASE notification_db TO notification_db_user;
GRANT CONNECT ON DATABASE analytics_db    TO analytics_db_user;
GRANT CONNECT ON DATABASE assessment_db   TO assessment_db_user;

-- ── auth_db — schema grants ────────────────────────────────────────────────────

\connect auth_db

-- Schema ownership: needed so Django migrate can CREATE/ALTER tables.
GRANT USAGE, CREATE ON SCHEMA public TO auth_db_user;
-- DML on existing tables (covers tables already present if init runs twice).
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO auth_db_user;
-- Sequences: needed for auto-increment PKs.
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO auth_db_user;
-- Default privileges: new tables/sequences created by migrations get these grants automatically.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO auth_db_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO auth_db_user;

-- ── user_db ────────────────────────────────────────────────────────────────────

\connect user_db

GRANT USAGE, CREATE ON SCHEMA public TO user_db_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO user_db_user;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO user_db_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO user_db_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO user_db_user;

-- ── resource_db ────────────────────────────────────────────────────────────────

\connect resource_db

GRANT USAGE, CREATE ON SCHEMA public TO resource_db_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO resource_db_user;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO resource_db_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO resource_db_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO resource_db_user;

-- ── practice_db ────────────────────────────────────────────────────────────────

\connect practice_db

GRANT USAGE, CREATE ON SCHEMA public TO practice_db_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO practice_db_user;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO practice_db_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO practice_db_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO practice_db_user;

-- ── notification_db ────────────────────────────────────────────────────────────

\connect notification_db

GRANT USAGE, CREATE ON SCHEMA public TO notification_db_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO notification_db_user;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO notification_db_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO notification_db_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO notification_db_user;

-- ── analytics_db ───────────────────────────────────────────────────────────────

\connect analytics_db

GRANT USAGE, CREATE ON SCHEMA public TO analytics_db_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO analytics_db_user;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO analytics_db_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO analytics_db_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO analytics_db_user;

-- ── assessment_db ──────────────────────────────────────────────────────────────

\connect assessment_db

GRANT USAGE, CREATE ON SCHEMA public TO assessment_db_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO assessment_db_user;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO assessment_db_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO assessment_db_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO assessment_db_user;
