import os
import json
import hashlib
import time
from datetime import datetime, timezone

from pymongo import MongoClient, UpdateOne
from pymongo.errors import OperationFailure


MONGO_USER = os.getenv("MONGO_USER", "admin")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD", "admin123")
MONGO_DB = os.getenv("MONGO_DB", "cdrl_nosql")
MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
MONGO_PORT = os.getenv("MONGO_PORT", "27017")

URI = (
    f"mongodb://{MONGO_USER}:{MONGO_PASSWORD}"
    f"@{MONGO_HOST}:{MONGO_PORT}/"
)

SECRET_KEYS = {"password", "token", "secret"}


def get_db():
    cliente = MongoClient(URI)
    return cliente[MONGO_DB]


def evolucionar_esquema(db):
    if "eventos_operativos" not in db.list_collection_names():
        db.create_collection("eventos_operativos")

    validador_v2 = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["eventId", "type", "timestamp"],
            "properties": {
                "eventId": {"bsonType": "string"},
                "type": {"bsonType": "string"},
                "timestamp": {"bsonType": "string"},
                "schemaVersion": {"bsonType": ["int", "double"]},
                "firmwareVersion": {"bsonType": "string"}
            }
        }
    }

    try:
        db.command(
            "collMod",
            "eventos_operativos",
            validator=validador_v2,
            validationLevel="strict",
            validationAction="error"
        )
    except OperationFailure as error:
        raise RuntimeError(
            "No fue posible actualizar el validador de eventos."
        ) from error


def sanitizar_detalles(valor):
    """Oculta secretos también dentro de diccionarios y listas."""
    if isinstance(valor, dict):
        resultado = {}
        for clave, contenido in valor.items():
            if str(clave).lower() in SECRET_KEYS:
                resultado[clave] = "***** [SANITIZED] *****"
            else:
                resultado[clave] = sanitizar_detalles(contenido)
        return resultado

    if isinstance(valor, list):
        return [sanitizar_detalles(elemento) for elemento in valor]

    if isinstance(valor, tuple):
        return [sanitizar_detalles(elemento) for elemento in valor]

    return valor


def auditar_operacion(db, actor, action, entity, result, detalles=None):
    detalles_seguros = sanitizar_detalles(detalles or {})

    db["audit_logs"].insert_one({
        "actorId": actor,
        "action": action,
        "entity": entity,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result": result,
        "details": detalles_seguros
    })


def recuperar_desde_fixture(db, filepath="fixtures/telemetry_backup.json"):
    inicio = time.perf_counter()

    if not os.path.exists(filepath):
        auditar_operacion(
            db, "system", "RESTORE", "eventos", "FAILED",
            {"error": "Backup no existe"}
        )
        raise FileNotFoundError("Backup no existe.")

    with open(filepath, "rb") as archivo:
        contenido = archivo.read()

    sha256_respaldo = hashlib.sha256(contenido).hexdigest()

    try:
        datos = json.loads(contenido.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        auditar_operacion(
            db, "system", "RESTORE", "eventos", "FAILED",
            {"error": "Backup JSON inválido", "sha256": sha256_respaldo}
        )
        raise ValueError("El respaldo no contiene JSON válido.") from error

    if not isinstance(datos, list):
        auditar_operacion(
            db, "system", "RESTORE", "eventos", "FAILED",
            {"error": "El respaldo debe ser una lista"}
        )
        raise ValueError("El respaldo debe contener una lista de eventos.")

    ids = []
    for documento in datos:
        if not isinstance(documento, dict) or not documento.get("eventId"):
            auditar_operacion(
                db, "system", "RESTORE", "eventos", "FAILED",
                {"error": "Documento inválido en el respaldo"}
            )
            raise ValueError("Cada evento debe ser un objeto con eventId.")

        ids.append(documento["eventId"])

    if len(ids) != len(set(ids)):
        auditar_operacion(
            db, "system", "RESTORE", "eventos", "FAILED",
            {"error": "eventId duplicado dentro del respaldo"}
        )
        raise ValueError("El respaldo contiene eventId duplicados.")

    coleccion = db["eventos_operativos"]
    existentes_antes = coleccion.count_documents({})

    operaciones = [
        UpdateOne(
            {"eventId": documento["eventId"]},
            {"$set": documento},
            upsert=True
        )
        for documento in datos
    ]

    resultado = None
    if operaciones:
        resultado = coleccion.bulk_write(operaciones, ordered=True)

    existentes_despues = coleccion.count_documents({})
    duracion_ms = round((time.perf_counter() - inicio) * 1000, 3)

    detalles = {
        "records_in_backup": len(datos),
        "records_before": existentes_antes,
        "records_after": existentes_despues,
        "upserted_count": resultado.upserted_count if resultado else 0,
        "modified_count": resultado.modified_count if resultado else 0,
        "duration_ms": duracion_ms,
        "backup_sha256": sha256_respaldo
    }

    auditar_operacion(
        db, "admin", "RESTORE", "eventos", "SUCCESS", detalles
    )

    print(
        f"=> Restore completado: {len(datos)} eventos en el respaldo; "
        f"{detalles['upserted_count']} nuevos; duración {duracion_ms} ms."
    )

    return detalles


def crear_fixture_ejemplo():
    os.makedirs("fixtures", exist_ok=True)
    datos = [
        {
            "eventId": "evt_v1_001",
            "type": "temp",
            "timestamp": "2026-10-01T10:00:00Z"
        },
        {
            "eventId": "evt_v2_002",
            "type": "temp",
            "timestamp": "2026-10-01T10:05:00Z",
            "schemaVersion": 2,
            "firmwareVersion": "1.0.4"
        }
    ]

    with open("fixtures/telemetry_backup.json", "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, indent=2)


if __name__ == "__main__":
    import sys

    cliente = MongoClient(URI)
    try:
        db = cliente[MONGO_DB]

        if len(sys.argv) > 1 and sys.argv[1] == "setup":
            crear_fixture_ejemplo()
            evolucionar_esquema(db)
            recuperar_desde_fixture(db)
        elif len(sys.argv) > 1 and sys.argv[1] == "demo":
            recuperar_desde_fixture(db)
        else:
            print("Uso: python src/m06_recovery.py [setup|demo]")
    finally:
        cliente.close()
