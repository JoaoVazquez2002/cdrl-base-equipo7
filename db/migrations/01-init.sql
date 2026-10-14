CREATE TABLE IF NOT EXISTS telemetry (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(50) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    temperature NUMERIC(5, 2) NOT NULL,
    CONSTRAINT unique_telemetry UNIQUE (device_id, timestamp)
);

-- Vista segura para el operador: omite métricas sensibles (temperature)
CREATE OR REPLACE VIEW telemetry_operator_view AS
    SELECT device_id, timestamp
    FROM telemetry;

-- Aplicar principio de menor privilegio sobre telemetry y la vista de operador
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'operation_role') THEN
        REVOKE ALL ON telemetry FROM operation_role;
        GRANT SELECT ON telemetry_operator_view TO operation_role;
    END IF;
    IF EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'write_role') THEN
        REVOKE DELETE ON telemetry FROM write_role;
        GRANT SELECT, INSERT, UPDATE ON telemetry TO write_role;
    END IF;
END
$$;