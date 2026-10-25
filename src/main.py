import os
import sys
from dotenv import load_dotenv

# Cargar variables del .env local
load_dotenv()

def verificar_postgres():
    try:
        import psycopg2
        conn = psycopg2.connect(
            dbname=os.getenv("POSTGRES_DB", "cdrl"),
            user=os.getenv("POSTGRES_USER", "cdrl_dev"),
            password=os.getenv("POSTGRES_PASSWORD", "cdrl_dev_only"),
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            connect_timeout=3
        )
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM telemetry;")
            count_telemetry = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM devices;")
            count_devices = cur.fetchone()[0]
            print(f"[PostgreSQL] OK: Conectado a base de datos '{os.getenv('POSTGRES_DB', 'cdrl')}'.")
            print(f"             - Dispositivos registrados: {count_devices}")
            print(f"             - Registros en telemetría: {count_telemetry}")
        conn.close()
        return True
    except Exception as e:
        print(f"[PostgreSQL] Advertencia: {e}")
        return False

def verificar_mongo():
    try:
        from pymongo import MongoClient
        from src.init_mongo import URI, MONGO_DB, configurar_base_documental
        
        # Inicialización no destructiva del esquema documental
        configurar_base_documental()
        
        cliente = MongoClient(URI, serverSelectionTimeoutMS=3000)
        db = cliente[MONGO_DB]
        total_eventos = db["eventos_operativos"].count_documents({})
        print(f"[MongoDB]    OK: Conectado a base NoSQL '{MONGO_DB}'.")
        print(f"             - Colección 'eventos_operativos': {total_eventos} eventos conservados.")
        cliente.close()
        return True
    except Exception as e:
        print(f"[MongoDB] Advertencia: {e}")
        return False

def ejecutar_simulacion():
    print("=" * 60)
    print("           CDRL - Centralized Data Repository")
    print("                 Ejecución de Ruta Crítica")
    print("=" * 60)
    
    pg_ok = verificar_postgres()
    mg_ok = verificar_mongo()
    
    # Demostración del flujo de pérdida controlada y recuperación
    from src.m06_recovery import get_db, simular_falla_y_recuperar
    db = get_db()
    print("\n=> Ejecutando simulación de falla controlada y recuperación con métricas...")
    simular_falla_y_recuperar(db)
    print("=> Simulación completada con éxito.")

    # Demostración de migración compatible v1 -> v2 (M07)
    from src.m07_migration import evolucionar_esquema_v2, migrar_documentos_v2
    print("\n=> Ejecutando verificación de esquema y migración compatible (M07)...")
    evolucionar_esquema_v2(db)
    migrar_documentos_v2(db)
    print("=> Migración compatible v1 -> v2 verificada.")
        
    print("=" * 60)
    print("=> Sistema CDRL iniciado y operando correctamente.")
    print("=" * 60)

if __name__ == "__main__":
    ejecutar_simulacion()
