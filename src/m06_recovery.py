import os
import json
from pymongo import MongoClient, UpdateOne
from pymongo.errors import OperationFailure
from datetime import datetime, timezone

MONGO_USER = os.getenv("MONGO_USER", "admin")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD", "admin123")
MONGO_DB = os.getenv("MONGO_DB", "cdrl_nosql")
MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
MONGO_PORT = os.getenv("MONGO_PORT", "27017")
URI = f"mongodb://{MONGO_USER}:{MONGO_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}/"

def get_db():
    return MongoClient(URI)[MONGO_DB]

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
        db.command("collMod", "eventos_operativos", validator=validador_v2)
    except OperationFailure as e:
        print(f"Error validador: {e}")

def auditar_operacion(db, actor, action, entity, result, detalles=None):
    detalles_seguros = (detalles or {}).copy()
    for campo in ["password", "token", "secret"]:
        if campo in detalles_seguros:
            detalles_seguros[campo] = "***** [SANITIZED] *****"

    db["audit_logs"].insert_one({
        "actorId": actor, "action": action, "entity": entity,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result": result, "details": detalles_seguros
    })

def recuperar_desde_fixture(db, filepath="fixtures/telemetry_backup.json"):
    if not os.path.exists(filepath):
        auditar_operacion(db, "system", "RESTORE", "eventos", "FAILED", {"error": "No file"})
        raise FileNotFoundError("Backup no existe.")

    with open(filepath, 'r') as f:
        datos = json.load(f)

    operaciones = [UpdateOne({"eventId": doc["eventId"]}, {"$set": doc}, upsert=True) for doc in datos]
    if operaciones:
        resultado = db["eventos_operativos"].bulk_write(operaciones)
        auditar_operacion(db, "admin", "RESTORE", "eventos", "SUCCESS", {"records": len(datos)})
        print(f"=> Restore listo. No hay duplicados. Upserts: {resultado.upserted_count}")

def crear_fixture_ejemplo():
    os.makedirs("fixtures", exist_ok=True)
    datos = [
        {"eventId": "evt_v1_001", "type": "temp", "timestamp": "2026-10-01T10:00:00Z"},
        {"eventId": "evt_v2_002", "type": "temp", "timestamp": "2026-10-01T10:05:00Z", "schemaVersion": 2, "firmwareVersion": "1.0.4"}
    ]
    with open("fixtures/telemetry_backup.json", "w") as f:
        json.dump(datos, f)

if __name__ == "__main__":
    import sys
    db = get_db()
    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        crear_fixture_ejemplo()
        evolucionar_esquema(db)
        recuperar_desde_fixture(db)
    elif len(sys.argv) > 1 and sys.argv[1] == "demo":
        recuperar_desde_fixture(db)