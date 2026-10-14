#!/bin/bash
set -e

# Valores por defecto para variables de entorno en caso de omisión
DB_USER_MIGRATE="${DB_USER_MIGRATE:-usuario_migracion}"
DB_PASS_MIGRATE="${DB_PASS_MIGRATE:-pass_migracion_local}"
DB_USER_WRITE="${DB_USER_WRITE:-usuario_escritura}"
DB_PASS_WRITE="${DB_PASS_WRITE:-pass_escritura_local}"
DB_USER_READ="${DB_USER_READ:-usuario_lectura}"
DB_PASS_READ="${DB_PASS_READ:-pass_lectura_local}"
DB_USER_OP="${DB_USER_OP:-usuario_operacion}"
DB_PASS_OP="${DB_PASS_OP:-pass_op_local}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- 1. Crear los roles de forma idempotente
    DO \$do\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'migration_role') THEN
            CREATE ROLE migration_role;
        END IF;
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'write_role') THEN
            CREATE ROLE write_role;
        END IF;
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'read_role') THEN
            CREATE ROLE read_role;
        END IF;
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'operation_role') THEN
            CREATE ROLE operation_role;
        END IF;
    END
    \$do\$;

    -- 2. Asignar permisos a esquemas y tablas existentes
    GRANT ALL PRIVILEGES ON SCHEMA public TO migration_role;

    -- Rol de escritura: SELECT, INSERT, UPDATE (SIN DELETE para proteger datos historicos)
    GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO write_role;
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO write_role;
    REVOKE DELETE ON ALL TABLES IN SCHEMA public FROM write_role;

    -- Rol de lectura: solo SELECT
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO read_role;

    -- Rol de operacion: NO tiene acceso a tablas de telemetria directas
    REVOKE ALL ON ALL TABLES IN SCHEMA public FROM operation_role;

    -- 3. Asignar permisos por defecto para tablas futuras
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO write_role;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO write_role;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO read_role;

    -- 4. Sincronizar permisos especificos sobre telemetria y vista segura si existen
    DO \$do\$
    BEGIN
        IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'telemetry') THEN
            REVOKE ALL ON telemetry FROM operation_role;
            REVOKE DELETE ON telemetry FROM write_role;
        END IF;
        IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'telemetry_events') THEN
            REVOKE ALL ON telemetry_events FROM operation_role;
            REVOKE DELETE ON telemetry_events FROM write_role;
        END IF;
        IF EXISTS (SELECT FROM information_schema.views WHERE table_schema = 'public' AND table_name = 'telemetry_operator_view') THEN
            GRANT SELECT ON telemetry_operator_view TO operation_role;
        END IF;
    END
    \$do\$;

    -- 5. Crear o actualizar los usuarios usando las variables de entorno de forma idempotente
    DO \$do\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '$DB_USER_MIGRATE') THEN
            CREATE USER "$DB_USER_MIGRATE" WITH PASSWORD '$DB_PASS_MIGRATE';
        ELSE
            ALTER USER "$DB_USER_MIGRATE" WITH PASSWORD '$DB_PASS_MIGRATE';
        END IF;
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '$DB_USER_WRITE') THEN
            CREATE USER "$DB_USER_WRITE" WITH PASSWORD '$DB_PASS_WRITE';
        ELSE
            ALTER USER "$DB_USER_WRITE" WITH PASSWORD '$DB_PASS_WRITE';
        END IF;
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '$DB_USER_READ') THEN
            CREATE USER "$DB_USER_READ" WITH PASSWORD '$DB_PASS_READ';
        ELSE
            ALTER USER "$DB_USER_READ" WITH PASSWORD '$DB_PASS_READ';
        END IF;
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '$DB_USER_OP') THEN
            CREATE USER "$DB_USER_OP" WITH PASSWORD '$DB_PASS_OP';
        ELSE
            ALTER USER "$DB_USER_OP" WITH PASSWORD '$DB_PASS_OP';
        END IF;
    END
    \$do\$;

    -- 6. Asignar roles a usuarios
    GRANT migration_role TO "$DB_USER_MIGRATE";
    GRANT write_role TO "$DB_USER_WRITE";
    GRANT read_role TO "$DB_USER_READ";
    GRANT operation_role TO "$DB_USER_OP";
EOSQL