
cat > db/migrations/00-roles.sh <<'EOF'
#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    -v DB_USER_MIGRATE="$DB_USER_MIGRATE" \
    -v DB_PASS_MIGRATE="$DB_PASS_MIGRATE" \
    -v DB_USER_WRITE="$DB_USER_WRITE" \
    -v DB_PASS_WRITE="$DB_PASS_WRITE" \
    -v DB_USER_READ="$DB_USER_READ" \
    -v DB_PASS_READ="$DB_PASS_READ" \
    -v DB_USER_OP="$DB_USER_OP" \
    -v DB_PASS_OP="$DB_PASS_OP" <<'EOSQL'

-- 1. Crear roles si no existen
SELECT 'CREATE ROLE migration_role'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'migration_role'
)
\gexec

SELECT 'CREATE ROLE write_role'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'write_role'
)
\gexec

SELECT 'CREATE ROLE read_role'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'read_role'
)
\gexec

SELECT 'CREATE ROLE operation_role'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'operation_role'
)
\gexec

-- 2. Permisos sobre el esquema
GRANT ALL PRIVILEGES ON SCHEMA public TO migration_role;
GRANT USAGE ON SCHEMA public TO write_role, read_role, operation_role;

-- 3. Permisos de las tablas existentes
-- Escritura: consultar, insertar y actualizar; no eliminar
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM write_role;
GRANT SELECT, INSERT, UPDATE
    ON ALL TABLES IN SCHEMA public TO write_role;

-- Permitir el uso de secuencias existentes al insertar registros
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO write_role;

-- Lectura: solo consultar
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM read_role;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO read_role;

-- Operación: consultar únicamente las tablas autorizadas
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM operation_role;
GRANT SELECT ON devices, ingestion_runs TO operation_role;

-- 4. Permisos predeterminados para tablas futuras
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL ON TABLES FROM write_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE ON TABLES TO write_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE ON SEQUENCES TO write_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL ON TABLES FROM read_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO read_role;

-- No conceder acceso automático a tablas futuras al rol de operación
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL ON TABLES FROM operation_role;

-- 5. Crear usuarios si no existen y asignar sus roles
SELECT format('CREATE USER %I WITH PASSWORD %L',
              :'DB_USER_MIGRATE', :'DB_PASS_MIGRATE')
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = :'DB_USER_MIGRATE'
)
\gexec
GRANT migration_role TO :"DB_USER_MIGRATE";

SELECT format('CREATE USER %I WITH PASSWORD %L',
              :'DB_USER_WRITE', :'DB_PASS_WRITE')
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = :'DB_USER_WRITE'
)
\gexec
GRANT write_role TO :"DB_USER_WRITE";

SELECT format('CREATE USER %I WITH PASSWORD %L',
              :'DB_USER_READ', :'DB_PASS_READ')
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = :'DB_USER_READ'
)
\gexec
GRANT read_role TO :"DB_USER_READ";

SELECT format('CREATE USER %I WITH PASSWORD %L',
              :'DB_USER_OP', :'DB_PASS_OP')
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = :'DB_USER_OP'
)
\gexec
GRANT operation_role TO :"DB_USER_OP";

EOSQL
EOF
