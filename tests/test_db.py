import os
import pytest
import psycopg2
from psycopg2 import errors
from dotenv import load_dotenv

# Cargar variables del .env local
load_dotenv()

def get_connection(user_var="DB_USER_WRITE", pass_var="DB_PASS_WRITE"):
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB", "cdrl"),
        user=os.getenv(user_var, os.getenv("POSTGRES_USER", "cdrl_dev")),
        password=os.getenv(pass_var, os.getenv("POSTGRES_PASSWORD", "cdrl_dev_only")),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432")
    )

@pytest.fixture
def db_write_conn():
    # Usamos el rol de escritura que definimos en la configuración
    conn = get_connection("DB_USER_WRITE", "DB_PASS_WRITE")
    conn.autocommit = True
    yield conn
    conn.close()

# ==============================================================================
# PRUEBAS SEMANA 1 (M01): TABLA TELEMETRY, SEED E IDEMPOTENCIA
# ==============================================================================

def test_caso_normal_lectura_seed(db_write_conn):
    """Verifica que el seed inicial cargue los dispositivos requeridos."""
    with db_write_conn.cursor() as cur:
        cur.execute("SELECT device_id FROM telemetry;")
        records = cur.fetchall()
        devices = [record[0] for record in records]
        assert "sensor-01" in devices, "Falta sensor-01 en la tabla telemetry"
        assert "sensor-02" in devices, "Falta sensor-02 en la tabla telemetry"

def test_idempotencia_carga_seed(db_write_conn):
    """Verifica que reejecutar la inserción de seed con ON CONFLICT no duplique registros."""
    with db_write_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM telemetry WHERE device_id IN ('sensor-01', 'sensor-02');")
        count_inicial = cur.fetchone()[0]

        # Reintentar la misma inserción del seed
        cur.execute("""
            INSERT INTO telemetry (device_id, timestamp, temperature)
            VALUES
                ('sensor-01', '2026-01-01 00:00:00+00', 22.50),
                ('sensor-02', '2026-01-01 00:00:00+00', 24.10)
            ON CONFLICT (device_id, timestamp) DO NOTHING;
        """)

        cur.execute("SELECT COUNT(*) FROM telemetry WHERE device_id IN ('sensor-01', 'sensor-02');")
        count_final = cur.fetchone()[0]
        assert count_inicial == count_final, "La carga repetida duplicó registros en telemetry"

def test_caso_limite_1_temperatura_maxima(db_write_conn):
    """Verifica el límite superior de temperatura en telemetry (999.99)."""
    with db_write_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO telemetry (device_id, timestamp, temperature) VALUES (%s, NOW(), %s) ON CONFLICT (device_id, timestamp) DO NOTHING;",
            ("sensor-max", 999.99)
        )
        cur.execute("SELECT temperature FROM telemetry WHERE device_id = 'sensor-max' ORDER BY id DESC LIMIT 1;")
        assert float(cur.fetchone()[0]) == 999.99

def test_caso_limite_2_temperatura_minima(db_write_conn):
    """Verifica el límite inferior de temperatura en telemetry (-999.99)."""
    with db_write_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO telemetry (device_id, timestamp, temperature) VALUES (%s, NOW(), %s) ON CONFLICT (device_id, timestamp) DO NOTHING;",
            ("sensor-min", -999.99)
        )
        cur.execute("SELECT temperature FROM telemetry WHERE device_id = 'sensor-min' ORDER BY id DESC LIMIT 1;")
        assert float(cur.fetchone()[0]) == -999.99

def test_fallo_declarado_valor_nulo(db_write_conn):
    """Falla intencionalmente violando la restricción NOT NULL de device_id."""
    with db_write_conn.cursor() as cur:
        with pytest.raises(errors.NotNullViolation):
            cur.execute(
                "INSERT INTO telemetry (device_id, timestamp, temperature) VALUES (%s, NOW(), %s);",
                (None, 25.00)
            )

# ==============================================================================
# PRUEBAS MODELO RELACIONAL E INVARIANTES
# ==============================================================================

def test_caso_normal_con_fixture(db_write_conn):
    with db_write_conn.cursor() as cur:
        # Fixture sintético: Insertamos un dato inventado
        cur.execute("INSERT INTO devices (name, firmware_version) VALUES ('sensor-sintetico-01', '1.0.0') ON CONFLICT DO NOTHING;")
        cur.execute("SELECT name FROM devices WHERE name = 'sensor-sintetico-01';")
        assert cur.fetchone()[0] == 'sensor-sintetico-01'

def test_caso_limite_valor_maximo(db_write_conn):
    with db_write_conn.cursor() as cur:
        cur.execute("INSERT INTO devices (name, firmware_version) VALUES ('sensor-sintetico-01', '1.0.0') ON CONFLICT DO NOTHING;")
        cur.execute("INSERT INTO telemetry_events (device_id, event_type, value) VALUES ((SELECT id FROM devices WHERE name = 'sensor-sintetico-01'), 'TEMP', 9999);")
        cur.execute("SELECT value FROM telemetry_events WHERE value = 9999;")
        assert float(cur.fetchone()[0]) == 9999.0

def test_fallo_declarado_invariante(db_write_conn):
    with db_write_conn.cursor() as cur:
        cur.execute("INSERT INTO devices (name, firmware_version) VALUES ('sensor-sintetico-01', '1.0.0') ON CONFLICT DO NOTHING;")
        # Falla intencionalmente porque -300 es menor al límite físico de -273.15
        with pytest.raises(errors.CheckViolation):
            cur.execute("INSERT INTO telemetry_events (device_id, event_type, value) VALUES ((SELECT id FROM devices WHERE name = 'sensor-sintetico-01'), 'TEMP', -300);")