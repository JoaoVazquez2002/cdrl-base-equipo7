"""
Módulo de Paginación Estable Basada en Cursores (Keyset Pagination) - M08
CDRL - Centralized Data Repository

Implementa paginación documental determinista sobre MongoDB utilizando punteros
de clave (_id / timestamp) en lugar de desplazamiento por offset (skip).

Principios de Arquitectura:
- Estabilidad ante inserciones: Inmune a desfases o duplicados por escrituras concurrentes.
- Complejidad O(1): Resuelto por escaneo directo de índice sin descartar documentos en memoria.
- Prohibición estricta de skip(): Cumple la regla de oro para evitar degradación p95.
- Gobernanza de entorno: Conexión dinámica vía os.getenv sin credenciales hardcodeadas.
"""

import os
from typing import Any, Dict, List, Optional, Tuple, Union
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING, DESCENDING
from bson import ObjectId
from bson.errors import InvalidId

load_dotenv()


def get_mongo_uri() -> str:
    """
    Construye la URI de conexión de forma dinámica a partir de variables de entorno.
    Garantiza que no existan credenciales hardcodeadas en el código fuente.
    """
    uri = os.getenv("MONGO_URI")
    if uri:
        return uri

    user = os.getenv("MONGO_USER")
    password = os.getenv("MONGO_PASSWORD")
    host = os.getenv("MONGO_HOST", "localhost")
    port = os.getenv("MONGO_PORT", "27017")

    if user and password:
        return f"mongodb://{user}:{password}@{host}:{port}/"
    return f"mongodb://{host}:{port}/"


def get_db(db_name: Optional[str] = None):
    """
    Obtiene la instancia de la base de datos MongoDB utilizando variables de entorno.
    """
    nombre_bd = db_name or os.getenv("MONGO_DB", "cdrl_nosql")
    cliente = MongoClient(get_mongo_uri(), serverSelectionTimeoutMS=4000)
    return cliente[nombre_bd]


def parse_cursor_id(last_id: Union[str, ObjectId]) -> Union[ObjectId, str]:
    """
    Convierte de forma segura un identificador de cursor a ObjectId si tiene
    el formato hexadecimal estándar de 24 caracteres, o conserva el valor original.
    """
    if isinstance(last_id, ObjectId):
        return last_id
    if isinstance(last_id, str):
        if ObjectId.is_valid(last_id):
            return ObjectId(last_id)
        return last_id
    return last_id


def setup_indexes(db, collection_name: str = "eventos_operativos") -> List[str]:
    """
    Crea los índices necesarios para respaldar la paginación por cursores y
    optimizar las consultas de telemetría y benchmark sin escaneos completos (COLLSCAN).

    Índices configurados:
    1. _id (índice único natural de MongoDB, implícito).
    2. eventId (único para idempotencia).
    3. (type, _id) / (type, timestamp, _id): Para consultas filtradas por tipo con ordenamiento estable.
    4. (timestamp, _id): Para navegación temporal indexada.
    """
    coleccion = db[collection_name]
    indices_creados = []

    # Índice de idempotencia para inserciones seguras
    idx_event_id = coleccion.create_index("eventId", unique=True, name="idx_event_id_unique")
    indices_creados.append(idx_event_id)

    # Índice compuesto para consultas filtradas por tipo con ordenamiento ascendente por cursor (_id)
    idx_type_id = coleccion.create_index(
        [("type", ASCENDING), ("_id", ASCENDING)],
        name="idx_type_asc_id_asc"
    )
    indices_creados.append(idx_type_id)

    # Índice compuesto para consultas filtradas por tipo con orden temporal inverso
    idx_type_time_id = coleccion.create_index(
        [("type", ASCENDING), ("timestamp", DESCENDING), ("_id", DESCENDING)],
        name="idx_type_timestamp_id"
    )
    indices_creados.append(idx_type_time_id)

    # Índice para ordenamiento cronológico general con desempate determinista
    idx_time_id = coleccion.create_index(
        [("timestamp", DESCENDING), ("_id", DESCENDING)],
        name="idx_timestamp_id"
    )
    indices_creados.append(idx_time_id)

    print(f"=> [setup_indexes] Índices asegurados en '{collection_name}': {indices_creados}")
    return indices_creados


def paginate_by_cursor(
    collection,
    filter_query: Optional[Dict[str, Any]] = None,
    last_id: Optional[Union[str, ObjectId]] = None,
    limit: int = 20,
    sort_direction: int = ASCENDING,
    operator: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Consulta documentos aplicando Paginación Estable basada en Cursores (Seek / Keyset Pagination).

    REGLA DE ORO:
    - ESTRICTAMENTE PROHIBIDO el uso de `.skip()`.
    - La posición de la página se ancla mediante la condición {'_id': {'$gt': last_id}}
      (o '$lt' según la dirección del ordenamiento), permitiendo al motor de base de datos
      acceder en O(1) vía índice al siguiente registro sin importar el volumen previo.

    Args:
        collection: Instancia de pymongo.collection.Collection a consultar.
        filter_query: Filtro de consulta opcional (ej. {'type': 'temperature_reading'}).
        last_id: Puntero del último documento de la página anterior (_id o string hexadecimal).
        limit: Cantidad de documentos deseados por página (debe ser > 0).
        sort_direction: Dirección del ordenamiento (pymongo.ASCENDING o pymongo.DESCENDING).
        operator: Operador de comparación para el cursor ('$gt' o '$lt').
                  Si no se especifica, se determina automáticamente:
                  - ASCENDING -> '$gt'
                  - DESCENDING -> '$lt'

    Returns:
        Diccionario con la estructura:
        {
            "items": List[Dict[str, Any]],       # Documentos de la página actual
            "next_cursor": Optional[str],        # Puntero para solicitar la página siguiente (o None)
            "has_next": bool,                    # Indica si existen páginas posteriores
            "count": int                         # Cantidad de elementos retornados en la página
        }
    """
    if limit <= 0:
        raise ValueError("El parámetro 'limit' debe ser un entero positivo mayor a 0.")

    # Copia defensiva del filtro base para evitar mutar diccionarios externos
    query: Dict[str, Any] = dict(filter_query) if filter_query else {}

    # Determinar el operador de cursor ($gt por defecto para orden ascendente)
    if operator is None:
        op = "$gt" if sort_direction == ASCENDING else "$lt"
    else:
        if operator not in ("$gt", "$gte", "$lt", "$lte"):
            raise ValueError(f"Operador de cursor no soportado: {operator}")
        op = operator

    # Aplicar el ancla de cursor sin utilizar skip()
    if last_id is not None:
        parsed_id = parse_cursor_id(last_id)
        if "_id" in query and isinstance(query["_id"], dict):
            query["_id"][op] = parsed_id
        else:
            query["_id"] = {op: parsed_id}

    # Se solicita limit + 1 documentos para evaluar si existe una página siguiente
    # sin necesidad de disparar una consulta count_documents() adicional.
    cursor = (
        collection.find(query)
        .sort([("_id", sort_direction)])
        .limit(limit + 1)
    )

    documentos = list(cursor)

    has_next = len(documentos) > limit
    items = documentos[:limit]

    next_cursor = str(items[-1]["_id"]) if (has_next and items) else None

    return {
        "items": items,
        "next_cursor": next_cursor,
        "has_next": has_next,
        "count": len(items),
    }


def main():
    """
    Ejecución demostrativa de verificación rápida de la paginación por cursores.
    """
    db = get_db()
    coleccion = db["eventos_operativos"]

    print("--- Verificación de Paginación por Cursor (M08) ---")
    setup_indexes(db, "eventos_operativos")

    total_existente = coleccion.count_documents({})
    print(f"Total de documentos en 'eventos_operativos': {total_existente}")

    if total_existente == 0:
        print("=> Advertencia: La colección está vacía. Ejecuta primero `python src/m08_benchmark.py --seed`.")
        return

    # Página 1 (sin last_id)
    print("\n=> Solicitando Página 1 (limit=3)...")
    pagina_1 = paginate_by_cursor(
        collection=coleccion,
        limit=3,
        sort_direction=ASCENDING
    )
    for doc in pagina_1["items"]:
        print(f"   [_id: {doc['_id']}] eventId: {doc.get('eventId')} | type: {doc.get('type')}")
    print(f"   -> has_next: {pagina_1['has_next']} | next_cursor: {pagina_1['next_cursor']}")

    # Página 2 (usando next_cursor como last_id)
    if pagina_1["has_next"]:
        cursor_p1 = pagina_1["next_cursor"]
        print(f"\n=> Solicitando Página 2 (last_id={cursor_p1}, limit=3)...")
        pagina_2 = paginate_by_cursor(
            collection=coleccion,
            last_id=cursor_p1,
            limit=3,
            sort_direction=ASCENDING
        )
        for doc in pagina_2["items"]:
            print(f"   [_id: {doc['_id']}] eventId: {doc.get('eventId')} | type: {doc.get('type')}")
        print(f"   -> has_next: {pagina_2['has_next']} | next_cursor: {pagina_2['next_cursor']}")


if __name__ == "__main__":
    main()
