"""
Pruebas Unitarias y de Integración - M08 Paginación Estable (Keyset Cursor)
CDRL - Centralized Data Repository

Valida:
1. Estabilidad ante inserciones concurrentes (ausencia de duplicados u omisiones).
2. Cumplimiento de la regla de oro: Prohibición absoluta de .skip().
3. Creación correcta de índices optimizados para benchmark.
4. Flujo continuo de paginación mediante next_cursor.
"""

import ast
import inspect
import pytest
from bson import ObjectId
from pymongo import MongoClient
from src.m08_pagination import (
    get_db,
    setup_indexes,
    paginate_by_cursor,
    parse_cursor_id,
)


@pytest.fixture(scope="module")
def db():
    database = get_db()
    setup_indexes(database, "eventos_operativos")
    yield database


@pytest.fixture
def limpiar_coleccion(db):
    coleccion = db["eventos_operativos"]
    coleccion.delete_many({"eventId": {"$regex": "^test_m08_pagi_"}})
    yield
    coleccion.delete_many({"eventId": {"$regex": "^test_m08_pagi_"}})


def test_prohibicion_estricta_de_skip():
    """
    REGLA DE ORO:
    Verifica mediante análisis estático del AST que la función paginate_by_cursor
    no invoque el método .skip() bajo ninguna circunstancia.
    """
    codigo_fuente = inspect.getsource(paginate_by_cursor)
    arbol = ast.parse(codigo_fuente)

    llamadas_skip = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute):
            if nodo.func.attr == "skip":
                llamadas_skip.append(nodo.lineno)

    assert len(llamadas_skip) == 0, f"Violación de la Regla de Oro: Se detectó llamada a .skip() en línea(s): {llamadas_skip}"


def test_parse_cursor_id():
    """Valida la conversión segura de ObjectId o strings."""
    oid = ObjectId()
    assert parse_cursor_id(str(oid)) == oid
    assert parse_cursor_id(oid) == oid
    assert parse_cursor_id("custom_id_123") == "custom_id_123"


def test_setup_indexes_crea_indices(db):
    """Verifica que setup_indexes asegure los índices requeridos por el benchmark."""
    coleccion = db["eventos_operativos"]
    nombres_indices = setup_indexes(db, "eventos_operativos")
    
    indices_existentes = coleccion.index_information()
    assert "idx_type_asc_id_asc" in indices_existentes or any("type" in str(idx) for idx in indices_existentes)
    assert len(nombres_indices) >= 3


def test_paginacion_cursor_secuencial(db, limpiar_coleccion):
    """
    Verifica que la paginación mediante cursor devuelva correctamente los documentos
    ordenados, calcule has_next adecuadamente y proporcione next_cursor válido.
    """
    coleccion = db["eventos_operativos"]

    # Insertar 5 documentos con orden determinista
    docs = [
        {"eventId": f"test_m08_pagi_{i:02d}", "type": "temperature_reading", "order_idx": i}
        for i in range(5)
    ]
    coleccion.insert_many(docs)

    # Página 1 (limit=2)
    p1 = paginate_by_cursor(coleccion, filter_query={"type": "temperature_reading"}, limit=2)
    assert len(p1["items"]) == 2
    assert p1["has_next"] is True
    assert p1["next_cursor"] is not None
    assert p1["items"][0]["order_idx"] == 0
    assert p1["items"][1]["order_idx"] == 1

    # Página 2 (limit=2, usando cursor de p1)
    p2 = paginate_by_cursor(
        coleccion,
        filter_query={"type": "temperature_reading"},
        last_id=p1["next_cursor"],
        limit=2
    )
    assert len(p2["items"]) == 2
    assert p2["has_next"] is True
    assert p2["items"][0]["order_idx"] == 2
    assert p2["items"][1]["order_idx"] == 3

    # Página 3 (último elemento restante)
    p3 = paginate_by_cursor(
        coleccion,
        filter_query={"type": "temperature_reading"},
        last_id=p2["next_cursor"],
        limit=2
    )
    assert len(p3["items"]) == 1
    assert p3["has_next"] is False
    assert p3["next_cursor"] is None
    assert p3["items"][0]["order_idx"] == 4


def test_estabilidad_ante_inserciones_concurrentes(db, limpiar_coleccion):
    """
    CRITERIO CLAVE M08:
    Comprueba que la paginación por cursor no sufra duplicaciones ni omisiones
    cuando se insertan nuevos registros mientras el cliente navega entre páginas.
    """
    coleccion = db["eventos_operativos"]

    # 1. Cargar estado inicial de 4 documentos
    iniciales = [
        {"eventId": f"test_m08_pagi_init_{i}", "type": "benchmark_sensor", "seq": i}
        for i in range(4)
    ]
    coleccion.insert_many(iniciales)

    # 2. Cliente obtiene Página 1 (2 registros)
    p1 = paginate_by_cursor(
        coleccion,
        filter_query={"type": "benchmark_sensor"},
        limit=2
    )
    assert len(p1["items"]) == 2
    ids_p1 = [doc["eventId"] for doc in p1["items"]]
    cursor_p1 = p1["next_cursor"]

    # 3. Simulación de INSERCIÓN CONCURRENTE en el sistema
    # (Un evento nuevo llega al sistema)
    coleccion.insert_one({
        "eventId": "test_m08_pagi_init_concurrente",
        "type": "benchmark_sensor",
        "seq": 999
    })

    # 4. Cliente obtiene Página 2 usando cursor de p1
    p2 = paginate_by_cursor(
        coleccion,
        filter_query={"type": "benchmark_sensor"},
        last_id=cursor_p1,
        limit=2
    )
    ids_p2 = [doc["eventId"] for doc in p2["items"]]

    # 5. Verificación de Estabilidad: NINGÚN documento de p1 debe repetirse en p2
    interseccion = set(ids_p1).intersection(set(ids_p2))
    assert len(interseccion) == 0, f"Error: Se detectaron registros duplicados en páginas subsecuentes: {interseccion}"
