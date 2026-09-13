-- SQLBook: Code
-- ==============================================================================
-- MIGRACIÓN M02: MODELO RELACIONAL E INVARIANTES
-- ==============================================================================

-- 1. TABLA CATÁLOGO: devices
-- Almacena los sensores de forma única
CREATE TABLE IF NOT EXISTS devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(50) NOT NULL UNIQUE,
    firmware_version VARCHAR(20) NOT NULL DEFAULT '1.0.0'
);

-- 2. TABLA CATÁLOGO: ingestion_runs
-- Registra los intentos de ingesta de datos y asegura que solo haya 3 estados
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) NOT NULL 
        CHECK (status IN ('PENDING', 'SUCCESS', 'FAILED'))
);

-- 3. TABLA TRANSACCIONAL: telemetry_events
-- Conecta los datos con los sensores e impone límites físicos reales
CREATE TABLE IF NOT EXISTS telemetry_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Llaves foráneas (Relaciones)
    device_id UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    ingestion_run_id UUID REFERENCES ingestion_runs(id) ON DELETE SET NULL,
    
    -- Invariantes (Reglas estrictas)
    event_type VARCHAR(30) NOT NULL 
        CHECK (event_type IN ('TEMP', 'HUMIDITY', 'STATUS')), 
        
    value NUMERIC NOT NULL 
        CHECK (value >= -273.15 AND value <= 9999), 
        
    captured_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);