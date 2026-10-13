
import pytest
import psycopg2
from tests.test_db import get_connection


def test_usuario_lectura_no_puede_insertar():
    """El usuario de lectura no debe poder insertar registros."""
    conn = get_connection("DB_USER_READ", "DB_PASS_READ")
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("INSERT INTO devices DEFAULT VALUES;")
    finally:
        conn.rollback()
        conn.close()


def test_usuario_lectura_no_puede_crear_tablas():
    """El usuario de lectura no debe poder crear tablas."""
    conn = get_connection("DB_USER_READ", "DB_PASS_READ")
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("CREATE TABLE tabla_ilegal (id INT);")
    finally:
        conn.rollback()
        conn.close()


def test_usuario_escritura_no_puede_eliminar_esquemas():
    """El usuario de escritura no debe poder eliminar esquemas."""
    conn = get_connection("DB_USER_WRITE", "DB_PASS_WRITE")
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("DROP SCHEMA public CASCADE;")
    finally:
        conn.rollback()
        conn.close()


def test_usuario_escritura_no_puede_eliminar_registros():
    """El usuario de escritura no debe tener permiso DELETE."""
    conn = get_connection("DB_USER_WRITE", "DB_PASS_WRITE")
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("DELETE FROM devices;")
    finally:
        conn.rollback()
        conn.close()


def test_usuario_operacion_no_puede_consultar_telemetria():
    """El usuario de operación no debe leer tablas de telemetría."""
    conn = get_connection("DB_USER_OP", "DB_PASS_OP")
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("SELECT * FROM telemetry LIMIT 1;")
    finally:
        conn.rollback()
        conn.close()


def test_usuario_operacion_no_puede_crear_roles():
    """El usuario de operación no debe poder crear roles."""
    conn = get_connection("DB_USER_OP", "DB_PASS_OP")
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("CREATE ROLE usuario_malicioso;")
    finally:
        conn.rollback()
        conn.close()
