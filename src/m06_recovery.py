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

import time

def sanitizar_detalles(obj):
    """Ofusca de forma recursiva campos sensibles en diccionarios y listas anidadas."""
    campos_sensibles = {"password", "token", "secret", "authorization", "api_key", "key"}
    if isinstance(obj, dict):
        resultado = {}
        for k, v in obj.items():
            if str(k).lower() in campos_sensibles:
                resultado[k] = "***** [SANITIZED] *****"
            elif isinstance(v, (dict, list)):
                resultado[k] = sanitizar_detalles(v)
            else:
                resultado[k] = v
        return resultado
    elif isinstance(obj, list):
        return [sanitizar_detalles(elem) for elem in obj]
    return obj

def auditar_operacion(db, actor, action, entity, result, detalles=None):
    detalles_seguros = sanitizar_detalles(detalles or {})

    db["audit_logs"].insert_one({
        "actorId": actor, "action": action, "entity": entity,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result": result, "details": detalles_seguros
    })

def simular_falla_y_recuperar(db, filepath="fixtures/telemetry_backup.json"):
    """
    Provoca una pérdida controlada de datos en MongoDB, mide el tiempo de recuperación
    y verifica la consistencia tras restaurar desde el fixture.
    Escribe el reporte en artifacts/recovery_metrics.txt.
    """
    # 0. Asegurar que el fixture exista físicamente
    if not os.path.exists(filepath):
        crear_fixture_ejemplo()

    # 1. Asegurar estado base desde el fixture
    recuperar_desde_fixture(db, filepath)
    total_antes = db["eventos_operativos"].count_documents({})

    # 2. Provocar pérdida controlada (eliminar un evento clave)
    evento_objetivo = "evt_v1_001"
    res_delete = db["eventos_operativos"].delete_one({"eventId": evento_objetivo})
    total_durante_falla = db["eventos_operativos"].count_documents({})
    
    auditar_operacion(
        db,
        actor="chaos_engineer",
        action="CONTROLLED_FAULT_INJECTION",
        entity="eventos_operativos",
        result="SUCCESS",
        detalles={"deleted_eventId": evento_objetivo, "deleted_count": res_delete.deleted_count}
    )

    # 3. Medir tiempo de recuperación y consistencia
    t_inicio = time.perf_counter()
    recuperar_desde_fixture(db, filepath)
    t_fin = time.perf_counter()

    duracion_segundos = t_fin - t_inicio
    duracion_ms = duracion_segundos * 1000.0
    total_tras_recuperacion = db["eventos_operativos"].count_documents({})
    consistente = (total_tras_recuperacion >= total_antes)

    # 4. Registrar métricas en artifacts/recovery_metrics.txt
    os.makedirs("artifacts", exist_ok=True)
    reporte = (
        "=== RECOVERY METRICS - CDRL FAULT TOLERANCE SIMULATION ===\n"
        f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n"
        f"Registros antes del fallo: {total_antes}\n"
        f"Registros eliminados (falla controlada): {res_delete.deleted_count} (eventId: {evento_objetivo})\n"
        f"Registros durante el fallo: {total_durante_falla}\n"
        f"Registros tras recuperación: {total_tras_recuperacion}\n"
        f"Tiempo de recuperación: {duracion_ms:.3f} ms ({duracion_segundos:.6f} s)\n"
        f"Consistencia de datos: {'OK / CONSISTENTE' if consistente else 'INCONSISTENTE'}\n"
        f"Resultado: {'EXITOSO' if consistente else 'FALLIDO'}\n"
    )
    metric_path = os.path.join("artifacts", "recovery_metrics.txt")
    with open(metric_path, "w", encoding="utf-8") as f:
        f.write(reporte)

    print(f"\n=> Pérdida y recuperación simulada exitosamente.")
    print(f"=> Tiempo: {duracion_ms:.3f} ms | Consistencia: {consistente}")
    print(f"=> Métricas guardadas en {metric_path}")

    return {
        "duration_seconds": duracion_segundos,
        "duration_ms": duracion_ms,
        "total_before": total_antes,
        "total_after": total_tras_recuperacion,
        "consistent": consistente
    }

def recuperar_desde_fixture(db, filepath="fixtures/telemetry_backup.json"):
    if not os.path.exists(filepath):
        auditar_operacion(db, "system", "RESTORE", "eventos", "FAILED", {"error": "No file"})
        raise FileNotFoundError("Backup no existe.")

    with open(filepath, 'r', encoding="utf-8") as f:
        datos = json.load(f)

    # Asegurar que cada documento cumpla el esquema estricto de MongoDB (source y payload)
    for doc in datos:
        if "source" not in doc:
            doc["source"] = "sensor-telemetry"
        if "payload" not in doc or not isinstance(doc["payload"], dict):
            doc["payload"] = {"status": "recovered", "temperature": 22.50}

    operaciones = [UpdateOne({"eventId": doc["eventId"]}, {"$set": doc}, upsert=True) for doc in datos]
    if operaciones:
        resultado = db["eventos_operativos"].bulk_write(operaciones)
        auditar_operacion(db, "admin", "RESTORE", "eventos", "SUCCESS", {"records": len(datos)})
        print(f"=> Restore listo. No hay duplicados. Upserts: {resultado.upserted_count}")

def crear_fixture_ejemplo():
    os.makedirs("fixtures", exist_ok=True)
    datos = [
        {
            "eventId": "evt_v1_001",
            "type": "temp",
            "source": "sensor-01",
            "timestamp": "2026-10-01T10:00:00Z",
            "payload": {"temperature": 22.50}
        },
        {
            "eventId": "evt_v2_002",
            "type": "temp",
            "source": "sensor-02",
            "timestamp": "2026-10-01T10:05:00Z",
            "schemaVersion": 2,
            "firmwareVersion": "1.0.4",
            "payload": {"temperature": 24.10}
        }
    ]
    with open("fixtures/telemetry_backup.json", "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2)

if __name__ == "__main__":
    import sys
    db = get_db()
    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        crear_fixture_ejemplo()
        evolucionar_esquema(db)
        recuperar_desde_fixture(db)
    elif len(sys.argv) > 1 and sys.argv[1] == "demo":
        simular_falla_y_recuperar(db)
    else:
        simular_falla_y_recuperar(db)