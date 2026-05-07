-- ABC Phones — PostgreSQL initialization script
-- Runs once on first database creation (docker-entrypoint-initdb.d)

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS intermediate;
CREATE SCHEMA IF NOT EXISTS analytics;

GRANT ALL ON SCHEMA raw, staging, intermediate, analytics TO abcphones;
