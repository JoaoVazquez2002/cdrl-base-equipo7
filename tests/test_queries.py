import pytest
import psycopg2
from psycopg2 import errors

from src.queries.queries import (
    obtener_dispositivos,
    obtener_dispositivo_por_nombre,
    obtener_eventos_por_dispositivo,
    obtener_eventos_por_tipo,
)

DB_CONFIG = {
    "dbname": "cdrl",
    "user": "cdrl_dev",
    "password": "cdrl_dev_only",
    "host": "localhost",
    "port": "5432",
}


@pytest.fixture
def db_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO devices (name, firmware_version)
            VALUES ('sensor-01', '1.0.0'),
                   ('sensor-02', '1.0.0')
            ON CONFLICT (name) DO NOTHING;
        """)

    yield conn
    conn.close()


def test_obtener_dispositivos(db_connection):
    with db_connection.cursor() as cur:
        dispositivos = obtener_dispositivos(cur)

        nombres = [dispositivo[1] for dispositivo in dispositivos]

        assert "sensor-01" in nombres
        assert "sensor-02" in nombres


def test_buscar_dispositivo_por_nombre(db_connection):
    with db_connection.cursor() as cur:
        dispositivo = obtener_dispositivo_por_nombre(cur, "sensor-01")

        assert dispositivo is not None
        assert dispositivo[1] == "sensor-01"


def test_busqueda_de_dispositivo_inexistente(db_connection):
    with db_connection.cursor() as cur:
        dispositivo = obtener_dispositivo_por_nombre(
            cur,
            "sensor-inexistente"
        )

        assert dispositivo is None


def test_consulta_parametrizada_por_tipo(db_connection):
    with db_connection.cursor() as cur:
        eventos = obtener_eventos_por_tipo(cur, "TEMP")

        assert isinstance(eventos, list)


def test_fallo_declarado_valor_nulo(db_connection):
    with db_connection.cursor() as cur:
        with pytest.raises(errors.NotNullViolation):
            cur.execute("""
                INSERT INTO devices (name, firmware_version)
                VALUES (%s, %s);
            """, (None, "1.0.0"))