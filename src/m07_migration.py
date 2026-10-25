import os
import sys
import json
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from pymongo.errors import OperationFailure, PyMongoError

load_dotenv()


def get_mongo_uri():
    """Construye la URI de conexión dinámicamente sin credenciales hardcodeadas."""
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
    """Obtiene la instancia de la base de datos MongoDB vía variables de entorno."""
    db_name = os.getenv("MONGO_DB", "cdrl_nosql")
    uri = get_mongo_uri()
    cliente = MongoClient(uri, serverSelectionTimeoutMS=3000)
    return cliente[db_name]


def evolucionar_esquema_v2(db):
    """
    Aplica el patrón Expand actualizando la validación en caliente mediante collMod.
    Define los campos nuevos (schemaVersion, firmwareVersion, status, payload.metrics)
    como opcionales para permitir la convivencia pacífica de documentos v1 y v2.
    """
    validador_v2 = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["eventId", "type", "source", "timestamp", "payload"],
            "properties": {
                "eventId": {"bsonType": "string"},
                "type": {"bsonType": "string"},
                "source": {"bsonType": "string"},
                "timestamp": {"bsonType": "string"},
                "schemaVersion": {"bsonType": ["int", "long", "double"]},
                "firmwareVersion": {"bsonType": "string"},
                "status": {"bsonType": "string"},
                "payload": {
                    "bsonType": "object",
                    "properties": {
                        "metrics": {"bsonType": "object"}
                    }
                }
            }
        }
    }

    if "eventos_operativos" not in db.list_collection_names():
        db.create_collection("eventos_operativos", validator=validador_v2)
    else:
        try:
            db.command("collMod", "eventos_operativos", validator=validador_v2)
        except OperationFailure as e:
            print(f"=> [collMod] Aviso al actualizar validador: {e}")


def migrar_documentos_v2(db):
    """
    Migración idempotente aplicando Expand & Contract con lectura compatible (Dual-Read).
    - Preserva los campos raíz en payload (ej. payload.temperature) para consumidores v1.
    - Agrega schemaVersion=2, firmwareVersion, status y payload.metrics para v2.
    - Idempotente: procesa únicamente documentos con schemaVersion ausente o menor a 2.
    """
    coleccion = db["eventos_operativos"]
    filtro_pendientes = {
        "$or": [
            {"schemaVersion": {"$exists": False}},
            {"schemaVersion": {"$lt": 2}}
        ]
    }

    docs_a_migrar = list(coleccion.find(filtro_pendientes))
    if not docs_a_migrar:
        print("=> [M07-MIGRATION] Ningún documento requiere migración. Idempotencia confirmada.")
        return {"matched": 0, "modified": 0}

    operaciones = []
    for doc in docs_a_migrar:
        payload_actual = doc.get("payload", {})
        if not isinstance(payload_actual, dict):
            payload_actual = {}

        # Construir estructura de métricas v2 sin duplicar anidamiento
        metricas = dict(payload_actual)
        metricas.pop("metrics", None)

        if "temperature" in metricas and "unit" not in metricas:
            metricas["unit"] = "celsius"
        elif "humidity" in metricas and "unit" not in metricas:
            metricas["unit"] = "percent"

        # Lectura dual: el payload conserva las propiedades raíz y expone 'metrics'
        nuevo_payload = dict(payload_actual)
        nuevo_payload["metrics"] = metricas

        firmware = doc.get("firmwareVersion") or os.getenv("DEFAULT_FIRMWARE_VERSION", "v2.1.0-lts")
        status = doc.get("status") or "OPERATIONAL"

        operaciones.append(
            UpdateOne(
                {"_id": doc["_id"]},
                {
                    "$set": {
                        "schemaVersion": 2,
                        "firmwareVersion": firmware,
                        "status": status,
                        "payload": nuevo_payload
                    }
                }
            )
        )

    resultado = coleccion.bulk_write(operaciones)
    print(f"=> [M07-MIGRATION] Migración exitosa. Documentos procesados: {resultado.modified_count}/{len(docs_a_migrar)}.")
    return {"matched": len(docs_a_migrar), "modified": resultado.modified_count}


def revertir_migracion_v1(db):
    """
    Rollback determinista: revierte los documentos v2 al formato v1 funcional.
    - Remueve schemaVersion, firmwareVersion, status y payload.metrics mediante $unset.
    - Conserva intactos los campos de telemetría raíz en payload sin borrar registros.
    """
    coleccion = db["eventos_operativos"]
    filtro_v2 = {"schemaVersion": {"$gte": 2}}

    docs_v2 = list(coleccion.find(filtro_v2))
    if not docs_v2:
        print("=> [M07-ROLLBACK] Ningún documento v2 para revertir. Idempotencia confirmada.")
        return {"matched": 0, "modified": 0}

    operaciones = []
    for doc in docs_v2:
        operaciones.append(
            UpdateOne(
                {"_id": doc["_id"]},
                {
                    "$unset": {
                        "schemaVersion": "",
                        "firmwareVersion": "",
                        "status": "",
                        "payload.metrics": ""
                    }
                }
            )
        )

    resultado = coleccion.bulk_write(operaciones)
    print(f"=> [M07-ROLLBACK] Rollback completado exitosamente. Revertidos: {resultado.modified_count}/{len(docs_v2)}.")
    return {"matched": len(docs_v2), "modified": resultado.modified_count}


def cargar_fixture_evolucion(db, ruta_fixture=None):
    """Carga los datos iniciales de evolución para validar la migración."""
    ruta = ruta_fixture or os.getenv("FIXTURE_EVOLUTION_PATH", "fixtures/telemetry_evolution.json")
    if not os.path.exists(ruta):
        raise FileNotFoundError(f"Fixture no encontrado en la ruta: {ruta}")

    with open(ruta, "r", encoding="utf-8") as f:
        datos = json.load(f)

    operaciones = [UpdateOne({"eventId": doc["eventId"]}, {"$set": doc}, upsert=True) for doc in datos]
    if operaciones:
        db["eventos_operativos"].bulk_write(operaciones)
    return len(datos)


def main():
    comando = sys.argv[1].lower() if len(sys.argv) > 1 else "migrate"
    db = get_db()

    if comando == "migrate":
        evolucionar_esquema_v2(db)
        migrar_documentos_v2(db)
    elif comando == "rollback":
        revertir_migracion_v1(db)
    elif comando == "seed":
        cargar_fixture_evolucion(db)
    else:
        print(f"Uso: python {sys.argv[0]} [migrate|rollback|seed]")
        sys.exit(1)


if __name__ == "__main__":
    main()
