import os
import pytest
import psycopg2
from psycopg2 import errors
from dotenv import load_dotenv

# Cargar variables del .env local
load_dotenv()

def get_connection(user_var, pass_var):
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB", "cdrl"),
        user=os.getenv(user_var),
        password=os.getenv(pass_var),
        host="localhost",
        port="5432"
    )

@pytest.fixture
def db_write_conn():
    # Usamos el rol de escritura que definimos en la configuración
    conn = get_connection("DB_USER_WRITE", "DB_PASS_WRITE")
    conn.autocommit = True
    yield conn
    conn.close()

def test_caso_normal_con_fixture(db_write_conn):
    with db_write_conn.cursor() as cur:
        # Fixture sintético: Insertamos un dato inventado
        cur.execute("INSERT INTO devices (name, firmware_version) VALUES ('sensor-sintetico-01', '1.0.0') ON CONFLICT DO NOTHING;")
        cur.execute("SELECT name FROM devices WHERE name = 'sensor-sintetico-01';")
        assert cur.fetchone()[0] == 'sensor-sintetico-01'

def test_caso_limite_valor_maximo(db_write_conn):
    with db_write_conn.cursor() as cur:
        cur.execute("INSERT INTO telemetry_events (device_id, event_type, value) VALUES ((SELECT id FROM devices LIMIT 1), 'TEMP', 9999);")
        cur.execute("SELECT value FROM telemetry_events WHERE value = 9999;")
        assert float(cur.fetchone()[0]) == 9999.0

def test_fallo_declarado_invariante(db_write_conn):
    with db_write_conn.cursor() as cur:
        # Falla intencionalmente porque -300 es menor al límite físico de -273.15
        with pytest.raises(errors.CheckViolation):
            cur.execute("INSERT INTO telemetry_events (device_id, event_type, value) VALUES ((SELECT id FROM devices LIMIT 1), 'TEMP', -300);")