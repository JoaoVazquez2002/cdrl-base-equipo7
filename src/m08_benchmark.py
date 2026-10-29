"""
Script de Benchmark de Consultas y Paginación Documental (M08)
CDRL - Centralized Data Repository

Mide y compara el rendimiento de consultas documentales y estrategias de paginación
(Offset vs. Keyset Cursor) bajo una carga sintética reproducible en MongoDB,
calculando percentiles p50 y p95 y registrando las especificaciones del entorno de ejecución.
"""

import os
import sys
import time
import math
import random
import argparse
import platform
import datetime
from typing import List, Dict, Any, Tuple
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from pymongo import MongoClient, UpdateOne, ASCENDING, DESCENDING
from bson import ObjectId


def get_mongo_uri() -> str:
    """Construye la URI de conexión dinámicamente mediante variables de entorno."""
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


def get_db():
    """Retorna la instancia de base de datos MongoDB configurada."""
    db_name = os.getenv("MONGO_DB", "cdrl_nosql")
    client = MongoClient(get_mongo_uri(), serverSelectionTimeoutMS=4000)
    return client[db_name]


def obtener_info_entorno(db=None) -> Dict[str, Any]:
    """Captura los metadatos del entorno de hardware, software y motor de base de datos."""
    info = {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "os_system": platform.system(),
        "os_release": platform.release(),
        "os_platform": platform.platform(),
        "architecture": platform.machine(),
        "cpu_cores": os.cpu_count() or 1,
        "python_version": platform.python_version(),
        "pymongo_version": None,
        "mongodb_version": "unknown",
    }
    try:
        import pymongo
        info["pymongo_version"] = pymongo.__version__
    except ImportError:
        pass

    if db is not None:
        try:
            build_info = db.command("buildInfo")
            info["mongodb_version"] = build_info.get("version", "unknown")
        except Exception as e:
            info["mongodb_version"] = f"error: {str(e)}"

    return info


def inyectar_carga_sintetica(
    db,
    collection_name: str = "eventos_operativos",
    total_docs: int = 1000,
    seed: int = 42,
) -> int:
    """
    Inyecta una carga de documentos sintéticos deterministas y reproducibles.
    Alineada al esquema compatible de telemetría v2 (M07).
    """
    random.seed(seed)
    coleccion = db[collection_name]

    print(f"=> Inyectando {total_docs} documentos sintéticos en '{collection_name}' (Seed: {seed})...")
    tipos_evento = ["temperature_reading", "pressure_alert", "humidity_level", "system_heartbeat"]
    fuentes = [f"sensor_node_{i:02d}" for i in range(1, 11)]

    # Fecha base determinista: 2026-10-01T00:00:00Z
    fecha_base = datetime.datetime(2026, 10, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)

    operaciones = []
    for i in range(total_docs):
        timestamp = (fecha_base + datetime.timedelta(minutes=i * 5)).isoformat()
        tipo = tipos_evento[i % len(tipos_evento)]
        fuente = fuentes[i % len(fuentes)]

        payload = {
            "metrics": {
                "value": round(20.0 + (i % 45) + random.uniform(0.1, 0.9), 2),
                "unit": "celsius" if "temperature" in tipo else "standard_unit",
            },
            "status_flag": "NORMAL" if i % 10 != 0 else "WARNING",
        }

        doc = {
            "eventId": f"bench-m08-{seed:04d}-{i:05d}",
            "type": tipo,
            "source": fuente,
            "timestamp": timestamp,
            "schemaVersion": 2,
            "firmwareVersion": "v2.1.0-lts",
            "status": "OPERATIONAL",
            "payload": payload,
        }

        operaciones.append(
            UpdateOne({"eventId": doc["eventId"]}, {"$set": doc}, upsert=True)
        )

    # Inserción en bloques de 500 para optimizar rendimiento de red
    tamano_lote = 500
    for chunk_start in range(0, len(operaciones), tamano_lote):
        lote = operaciones[chunk_start : chunk_start + tamano_lote]
        coleccion.bulk_write(lote, ordered=False)

    total_actual = coleccion.count_documents({})
    print(f"=> Carga completada. Documentos actuales en '{collection_name}': {total_actual}")
    return total_docs


def calcular_percentil(datos: List[float], percentil: float) -> float:
    """Calcula el percentil (ej. 50 para p50, 95 para p95) sobre una lista de tiempos."""
    if not datos:
        return 0.0
    ordenados = sorted(datos)
    k = (len(ordenados) - 1) * (percentil / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return ordenados[int(k)]
    d0 = ordenados[int(f)] * (c - k)
    d1 = ordenados[int(c)] * (k - f)
    return d0 + d1


def asegurar_indices_optimizados(db, collection_name: str = "eventos_operativos"):
    """Garantiza la existencia de índices para cursor keyset y consultas combinadas."""
    coleccion = db[collection_name]
    coleccion.create_index("eventId", unique=True)
    # Índice compuesto para ordenamiento estable de paginación
    coleccion.create_index([("type", ASCENDING), ("timestamp", DESCENDING), ("_id", ASCENDING)])
    coleccion.create_index([("timestamp", DESCENDING), ("_id", DESCENDING)])


def benchmark_offset_pagination(
    coleccion,
    filtro: Dict[str, Any],
    offset: int,
    page_size: int,
    iteraciones: int,
) -> List[float]:
    """
    Línea Base: Mide el tiempo de paginación tradicional usando skip() y limit().
    Complejidad O(N) respecto al offset (MongoDB debe recorrer y descartar N documentos).
    """
    tiempos_ms = []
    for _ in range(iteraciones):
        t0 = time.perf_counter()
        cursor = coleccion.find(filtro).sort([("timestamp", DESCENDING), ("_id", DESCENDING)]).skip(offset).limit(page_size)
        _ = list(cursor)  # Consumir resultados
        t1 = time.perf_counter()
        tiempos_ms.append((t1 - t0) * 1000.0)
    return tiempos_ms


def benchmark_cursor_pagination(
    coleccion,
    filtro_base: Dict[str, Any],
    page_size: int,
    iteraciones: int,
) -> List[float]:
    """
    Propuesta Optimizada: Paginación estable basada en cursor (Keyset Pagination).
    Utiliza el último `_id` visto para anclar la siguiente página con $lt / $gt.
    Complejidad O(1) indexada e inmune a desplazamientos por inserciones concurrentes.
    """
    tiempos_ms = []

    # Obtener un cursor pivote representativo para medir una página profunda de forma constante
    doc_pivote = coleccion.find(filtro_base).sort([("timestamp", DESCENDING), ("_id", DESCENDING)]).skip(200).limit(1)
    lista_pivote = list(doc_pivote)
    
    ultimo_id = lista_pivote[0]["_id"] if lista_pivote else None

    for _ in range(iteraciones):
        filtro = dict(filtro_base)
        if ultimo_id:
            filtro["_id"] = {"$lt": ultimo_id}

        t0 = time.perf_counter()
        cursor = coleccion.find(filtro).sort([("_id", DESCENDING)]).limit(page_size)
        _ = list(cursor)
        t1 = time.perf_counter()
        tiempos_ms.append((t1 - t0) * 1000.0)

    return tiempos_ms


def ejecutar_benchmark_completo(
    db,
    collection_name: str = "eventos_operativos",
    iteraciones: int = 100,
    page_size: int = 20,
    deep_offset: int = 500,
) -> Dict[str, Any]:
    """
    Ejecuta el protocolo comparativo reproducible calculando p50 y p95.
    """
    coleccion = db[collection_name]
    asegurar_indices_optimizados(db, collection_name)

    filtro = {"type": "temperature_reading"}

    print("\n" + "=" * 70)
    print(f" EJECUCIÓN DE BENCHMARK REPRODUCIBLE (M08) - Colección: {collection_name}")
    print(f" Iteraciones: {iteraciones} | Tamaño de página: {page_size} | Offset profundo: {deep_offset}")
    print("=" * 70)

    # 1. Medición Línea Base (Skip/Limit)
    print("=> Midiendo Línea Base: Paginación Offset (skip/limit)...")
    tiempos_offset = benchmark_offset_pagination(coleccion, filtro, deep_offset, page_size, iteraciones)
    p50_offset = calcular_percentil(tiempos_offset, 50)
    p95_offset = calcular_percentil(tiempos_offset, 95)
    avg_offset = sum(tiempos_offset) / len(tiempos_offset)

    # 2. Medición Optimizada (Keyset Cursor)
    print("=> Midiendo Solución Optimizada: Keyset Cursor Pagination...")
    tiempos_cursor = benchmark_cursor_pagination(coleccion, filtro, page_size, iteraciones)
    p50_cursor = calcular_percentil(tiempos_cursor, 50)
    p95_cursor = calcular_percentil(tiempos_cursor, 95)
    avg_cursor = sum(tiempos_cursor) / len(tiempos_cursor)

    speedup_p50 = (p50_offset / p50_cursor) if p50_cursor > 0 else 1.0
    speedup_p95 = (p95_offset / p95_cursor) if p95_cursor > 0 else 1.0

    entorno = obtener_info_entorno(db)

    resultados = {
        "entorno": entorno,
        "configuracion": {
            "coleccion": collection_name,
            "iteraciones": iteraciones,
            "tamano_pagina": page_size,
            "offset_profundo": deep_offset,
            "muestra_documentos": coleccion.count_documents({}),
        },
        "linea_base_offset": {
            "p50_ms": round(p50_offset, 4),
            "p95_ms": round(p95_offset, 4),
            "avg_ms": round(avg_offset, 4),
            "min_ms": round(min(tiempos_offset), 4),
            "max_ms": round(max(tiempos_offset), 4),
        },
        "optimizada_cursor": {
            "p50_ms": round(p50_cursor, 4),
            "p95_ms": round(p95_cursor, 4),
            "avg_ms": round(avg_cursor, 4),
            "min_ms": round(min(tiempos_cursor), 4),
            "max_ms": round(max(tiempos_cursor), 4),
        },
        "mejora": {
            "speedup_p50": round(speedup_p50, 2),
            "speedup_p95": round(speedup_p95, 2),
        },
    }

    # Impresión tabular de resultados
    print("\n--- RESUMEN DE RESULTADOS DEL BENCHMARK ---")
    print(f"{'Métrica':<25} | {'Línea Base (Offset)':<20} | {'Optimizada (Cursor)':<20} | {'Factor de Mejora':<15}")
    print("-" * 88)
    print(f"{'Latencia p50 (Mediana)':<25} | {p50_offset:>14.4f} ms | {p50_cursor:>14.4f} ms | {speedup_p50:>13.2f}x")
    print(f"{'Latencia p95 (Percentil)':<25} | {p95_offset:>14.4f} ms | {p95_cursor:>14.4f} ms | {speedup_p95:>13.2f}x")
    print(f"{'Latencia Promedio':<25} | {avg_offset:>14.4f} ms | {avg_cursor:>14.4f} ms | {(avg_offset/avg_cursor):>13.2f}x")
    print("-" * 88)
    print("\n--- ESPECIFICACIONES DEL ENTORNO REGISTRADO ---")
    print(f" Sistema Operativo: {entorno['os_platform']}")
    print(f" Arquitectura CPU:  {entorno['architecture']} ({entorno['cpu_cores']} núcleos)")
    print(f" Versión Python:    {entorno['python_version']}")
    print(f" Driver PyMongo:    {entorno['pymongo_version']}")
    print(f" Versión MongoDB:   {entorno['mongodb_version']}")
    print(f" Timestamp (UTC):   {entorno['timestamp_utc']}")
    print("=" * 70 + "\n")

    return resultados


def main():
    parser = argparse.ArgumentParser(description="CDRL M08 Benchmark de Consultas y Paginación Documental")
    parser.add_argument("--seed", action="store_true", help="Inyecta 1000 documentos sintéticos reproducibles")
    parser.add_argument("--run", action="store_true", help="Ejecuta la medición comparativa (p50 / p95)")
    parser.add_argument("--docs", type=int, default=int(os.getenv("BENCHMARK_DOCS_COUNT", "1000")), help="Cantidad de documentos a inyectar")
    parser.add_argument("--iterations", type=int, default=int(os.getenv("BENCHMARK_ITERATIONS", "100")), help="Número de iteraciones del benchmark")
    parser.add_argument("--page-size", type=int, default=int(os.getenv("BENCHMARK_PAGE_SIZE", "20")), help="Tamaño de página para paginación")
    parser.add_argument("--collection", type=str, default=os.getenv("BENCHMARK_COLLECTION", "eventos_operativos"), help="Nombre de la colección")

    args = parser.parse_args()

    db = get_db()

    # Si no se pasan banderas explícitas, ejecutar flujo integral por defecto
    ejecutar_todo = not (args.seed or args.run)

    if args.seed or ejecutar_todo:
        inyectar_carga_sintetica(db, collection_name=args.collection, total_docs=args.docs)

    if args.run or ejecutar_todo:
        ejecutar_benchmark_completo(
            db,
            collection_name=args.collection,
            iteraciones=args.iterations,
            page_size=args.page_size,
        )


if __name__ == "__main__":
    main()
