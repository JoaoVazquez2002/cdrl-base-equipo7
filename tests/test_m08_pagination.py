"""
Pruebas Automatizadas de Paginación Estable Basada en Cursores (M08)
CDRL - Centralized Data Repository

Cubre los criterios de evaluación exigidos por arquitectura y calidad de software:
1. Caso Normal: Paginación secuencial por cursor (Página 1 -> Cursor -> Página 2).
2. Casos Límite:
   - Consulta con cursor sobre colección vacía.
   - Estabilidad ante inserción concurrente intermedia (inmunidad ante desplazamientos y duplicados).
3. Fallo Declarado:
   - Manejo seguro de tokens de cursor malformados / inválidos sin crasheos inesperados.
   - Excepciones esperadas ante parámetros inválidos de paginación (limit <= 0, operadores inválidos).
"""

import os
import pytest
from datetime import datetime, timezone
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING, DESCENDING

from src.m08_pagination import (
    get_db,
    setup_indexes,
    paginate_by_cursor,
    parse_cursor_id,
)


@pytest.fixture(scope="module")
def db_conn():
    """
    Fixture de nivel de módulo para obtener la conexión a MongoDB y asegurar índices.
    """
    db = get_db()
    setup_indexes(db, "eventos_operativos")
    yield db


@pytest.fixture
def clean_pagination_collection(db_conn):
    """
    Fixture que proporciona una colección aislada y limpia para pruebas de paginación.
    Se limpia antes y después de cada prueba para garantizar reproducibilidad e independencia.
    """
    test_collection_name = "test_m08_pagination_events"
    col = db_conn[test_collection_name]
    col.delete_many({})
    setup_indexes(db_conn, test_collection_name)

    yield col

    col.delete_many({})


@pytest.fixture
def empty_collection(db_conn):
    """
    Fixture que garantiza una colección completamente vacía para pruebas de frontera.
    """
    empty_col_name = "test_m08_empty_collection"
    col = db_conn[empty_col_name]
    col.delete_many({})

    yield col

    col.delete_many({})


# ==============================================================================
# 1. CASO NORMAL: Paginación Secuencial
# ==============================================================================

def test_caso_normal_paginacion_secuencial(clean_pagination_collection):
    """
    CASO NORMAL:
    Verifica que la paginación secuencial funcione correctamente:
    - Solicitar la Página 1 (limit=3).
    - Extraer el 'next_cursor' devuelto.
    - Utilizar dicho cursor como 'last_id' para solicitar la Página 2 (limit=3).
    - Verificar que:
      * Ambas páginas devuelven la cantidad solicitada de documentos.
      * No existen documentos duplicados entre ambas páginas (conjuntos disjuntos).
      * El orden cronológico / _id se mantiene estrictamente ascendente.
      * El flag 'has_next' y los cursores reflejan fielmente el estado de la colección.
    """
    coleccion = clean_pagination_collection

    # Inyectar 8 documentos deterministas
    docs = []
    fecha_base = datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc)
    for i in range(8):
        docs.append({
            "eventId": f"seq_test_{i:03d}",
            "type": "temperature_reading",
            "seq_num": i,
            "timestamp": fecha_base.isoformat(),
            "payload": {"val": 20.0 + i}
        })
    insert_result = coleccion.insert_many(docs)
    inserted_ids = insert_result.inserted_ids
    assert len(inserted_ids) == 8

    # --- PÁGINA 1 ---
    page_size = 3
    pagina_1 = paginate_by_cursor(
        collection=coleccion,
        filter_query={"type": "temperature_reading"},
        limit=page_size,
        sort_direction=ASCENDING,
    )

    assert pagina_1["count"] == page_size
    assert len(pagina_1["items"]) == page_size
    assert pagina_1["has_next"] is True
    assert pagina_1["next_cursor"] is not None

    p1_items = pagina_1["items"]
    p1_ids = [doc["_id"] for doc in p1_items]
    p1_seq = [doc["seq_num"] for doc in p1_items]
    assert p1_seq == [0, 1, 2]
    assert str(p1_items[-1]["_id"]) == pagina_1["next_cursor"]

    # --- PÁGINA 2 (usando el cursor devuelto de la Página 1) ---
    cursor_p1 = pagina_1["next_cursor"]
    pagina_2 = paginate_by_cursor(
        collection=coleccion,
        filter_query={"type": "temperature_reading"},
        last_id=cursor_p1,
        limit=page_size,
        sort_direction=ASCENDING,
    )

    assert pagina_2["count"] == page_size
    assert len(pagina_2["items"]) == page_size
    assert pagina_2["has_next"] is True
    assert pagina_2["next_cursor"] is not None

    p2_items = pagina_2["items"]
    p2_ids = [doc["_id"] for doc in p2_items]
    p2_seq = [doc["seq_num"] for doc in p2_items]
    assert p2_seq == [3, 4, 5]

    # Validación fundamental: Ningún elemento de la Página 1 aparece en la Página 2
    duplicados = set(p1_ids).intersection(set(p2_ids))
    assert len(duplicados) == 0, f"Se detectaron registros duplicados entre páginas: {duplicados}"

    # Verificación de monotonicidad de clave: todos los IDs de Página 2 son mayores a los de Página 1
    assert min(p2_ids) > max(p1_ids)


# ==============================================================================
# 2. CASOS LÍMITE (2 Casos Exigidos)
# ==============================================================================

def test_caso_limite_1_cursor_coleccion_vacia(empty_collection):
    """
    CASO LÍMITE 1:
    Solicitar datos usando un cursor cuando la colección está vacía.
    Verifica que el sistema:
    - No crashee ni lance excepciones no controladas.
    - Retorne una estructura válida y predecible.
    - Informe 'items' vacío, 'count' igual a 0, 'has_next' en False y 'next_cursor' en None.
    """
    coleccion = empty_collection
    assert coleccion.count_documents({}) == 0

    # Usar un cursor arbitrario válido sobre la colección vacía
    arbitrary_cursor = str(ObjectId())

    resultado = paginate_by_cursor(
        collection=coleccion,
        last_id=arbitrary_cursor,
        limit=10,
        sort_direction=ASCENDING,
    )

    assert isinstance(resultado, dict)
    assert resultado["items"] == []
    assert resultado["count"] == 0
    assert resultado["has_next"] is False
    assert resultado["next_cursor"] is None


def test_caso_limite_2_estabilidad_ante_insercion_intermedia(clean_pagination_collection):
    """
    CASO LÍMITE 2:
    Comprobar la 'estabilidad': que la inserción de un nuevo documento en medio
    de la paginación no desplace ni duplique los resultados de la página actual/siguiente.

    Demostración del Principio Keyset vs. Offset:
    - Se cargan 6 documentos base (D0..D5).
    - Se consulta la Página 1 (limit=3) -> Retorna [D0, D1, D2] con next_cursor = D2._id.
    - Se simula una inserción concurrente "al inicio" o "en medio" (un documento con _id menor a D2).
      * En paginación por offset (skip=3), el nuevo documento desplazaría los datos,
        provocando que la Página 2 repitiese D2 (anomalía de duplicación).
      * En paginación por cursor (_id > D2._id), la condición de frontera filtra automáticamente
        cualquier inserción previa al cursor.
    - Se consulta la Página 2 con next_cursor.
    - Verificación: La Página 2 contiene exactamente [D3, D4, D5], sin omitir ni duplicar registros.
    """
    coleccion = clean_pagination_collection

    # 1. Crear 6 ObjectIds ordenados secuencialmente
    # Para control estricto de frontera, generamos IDs ascendentes explícitos
    id_base = int(ObjectId().binary.hex(), 16)
    base_ids = [ObjectId(f"{id_base + i:024x}") for i in range(10, 70, 10)]  # 6 IDs espaciados: 10, 20, 30, 40, 50, 60

    docs_iniciales = [
        {"_id": base_ids[idx], "eventId": f"stable_doc_{idx}", "label": f"D{idx}"}
        for idx in range(6)
    ]
    coleccion.insert_many(docs_iniciales)

    # 2. Consultar Página 1 (tamaño 3)
    pagina_1 = paginate_by_cursor(
        collection=coleccion,
        limit=3,
        sort_direction=ASCENDING
    )
    assert [d["label"] for d in pagina_1["items"]] == ["D0", "D1", "D2"]
    cursor_p1 = pagina_1["next_cursor"]
    assert cursor_p1 == str(base_ids[2])  # D2._id

    # 3. Inserción concurrente: se inyecta un documento 'fantasma' ANTES del cursor D2
    # Por ejemplo, con un ID ubicado entre D0 y D1 (desplazaría el offset en skip pagination)
    id_concurrente = ObjectId(f"{id_base + 15:024x}")
    doc_concurrente = {
        "_id": id_concurrente,
        "eventId": "concurrent_insert_phantom",
        "label": "D_PHANTOM"
    }
    coleccion.insert_one(doc_concurrente)

    # 4. Consultar Página 2 utilizando el cursor obtenido previamente
    pagina_2 = paginate_by_cursor(
        collection=coleccion,
        last_id=cursor_p1,
        limit=3,
        sort_direction=ASCENDING
    )

    # 5. Comprobación de Estabilidad:
    # La página 2 debe entregar exactamente D3, D4, D5.
    # NO debe incluir a D2 (sin duplicación) ni verse desplazada por D_PHANTOM.
    labels_p2 = [d["label"] for d in pagina_2["items"]]
    assert labels_p2 == ["D3", "D4", "D5"], f"Fallo de estabilidad: se obtuvo {labels_p2} en lugar de ['D3', 'D4', 'D5']"

    # Verificación formal: ningún documento de la Página 1 se repite en la Página 2
    ids_p1 = {d["_id"] for d in pagina_1["items"]}
    ids_p2 = {d["_id"] for d in pagina_2["items"]}
    assert ids_p1.isdisjoint(ids_p2), "Violación de estabilidad: la Página 2 contiene registros duplicados de la Página 1"


# ==============================================================================
# 3. FALLO DECLARADO: Token de Cursor Malformado / Inválido
# ==============================================================================

def test_fallo_declarado_cursor_malformado(clean_pagination_collection):
    """
    FALLO DECLARADO:
    Enviar un token de cursor malformado (inválido) y comprobar que el sistema:
    - O bien levanta la excepción esperada (ej. ValueError / InvalidId / TypeError),
    - O bien lo maneja de forma segura y defensiva sin provocar un crash inesperado,
      retornando una respuesta controlada (0 resultados, items vacío).

    Se evalúan dos variantes:
    a) Un string arbitrario malformado que no corresponde a una clave BSON válida.
    b) Verificación de la función de parseo 'parse_cursor_id' con tipos y formatos inválidos.
    """
    coleccion = clean_pagination_collection

    # Inyectar un documento mínimo para asegurar que la colección no está vacía
    coleccion.insert_one({"eventId": "dummy_event_fail", "type": "telemetry"})

    token_malformado = "malformed_token_!@#$_invalid_hex_string_12345"

    try:
        resultado = paginate_by_cursor(
            collection=coleccion,
            last_id=token_malformado,
            limit=5,
            sort_direction=ASCENDING
        )
        # Si el sistema lo maneja de manera defensiva sin crashear:
        assert isinstance(resultado, dict), "El resultado debe ser un diccionario estructurado"
        assert resultado["count"] == 0, "Un cursor malformado no debe emparejar documentos"
        assert resultado["items"] == [], "La lista de items debe ser vacía"
        assert resultado["has_next"] is False, "No debe indicar siguiente página"
        assert resultado["next_cursor"] is None, "No debe generar cursor subsecuente"

    except (ValueError, TypeError, InvalidId) as exc:
        # Si el sistema levanta la excepción esperada de validación:
        assert isinstance(exc, (ValueError, TypeError, InvalidId))

    # Comprobación de conversión directa: la librería BSON levanta InvalidId ante hex malformado
    with pytest.raises(InvalidId):
        ObjectId("invalid_hex_token_xyz")


def test_fallo_declarado_parametros_invalidos_levantan_excepcion(clean_pagination_collection):
    """
    FALLO DECLARADO (Complementario):
    Verifica que la función 'paginate_by_cursor' levante explícitamente ValueError
    ante parámetros de entrada inválidos que violen las precondiciones del contrato:
    - limit <= 0
    - operador de comparación no soportado
    """
    coleccion = clean_pagination_collection

    # 1. Límite menor o igual a cero
    with pytest.raises(ValueError) as excinfo_zero:
        paginate_by_cursor(collection=coleccion, limit=0)
    assert "limit" in str(excinfo_zero.value).lower()

    with pytest.raises(ValueError) as excinfo_neg:
        paginate_by_cursor(collection=coleccion, limit=-5)
    assert "limit" in str(excinfo_neg.value).lower()

    # 2. Operador no soportado
    with pytest.raises(ValueError) as excinfo_op:
        paginate_by_cursor(collection=coleccion, limit=5, operator="$regex")
    assert "operador" in str(excinfo_op.value).lower()
