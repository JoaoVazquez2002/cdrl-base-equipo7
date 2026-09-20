#!/bin/bash
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- 1. Crear los roles
    CREATE ROLE migration_role;
    CREATE ROLE write_role;
    CREATE ROLE read_role;
    CREATE ROLE operation_role;

    -- 2. Asignar permisos estrictos a cada rol
    GRANT ALL PRIVILEGES ON SCHEMA public TO migration_role;
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO write_role;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO read_role;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO operation_role;

    -- 3. Crear los usuarios usando las variables de entorno y asignarles su rol
    CREATE USER "$DB_USER_MIGRATE" WITH PASSWORD '$DB_PASS_MIGRATE';
    GRANT migration_role TO "$DB_USER_MIGRATE";

    CREATE USER "$DB_USER_WRITE" WITH PASSWORD '$DB_PASS_WRITE';
    GRANT write_role TO "$DB_USER_WRITE";

    CREATE USER "$DB_USER_READ" WITH PASSWORD '$DB_PASS_READ';
    GRANT read_role TO "$DB_USER_READ";

    CREATE USER "$DB_USER_OP" WITH PASSWORD '$DB_PASS_OP';
    GRANT operation_role TO "$DB_USER_OP";
EOSQL