"""
Módulo de Seguridad, Control de Acceso (RBAC), Auditoría con Enmascaramiento y Remediación (M09)
CDRL - Centralized Data Repository

Implementa:
1. Control de Acceso Basado en Roles (RBAC) por colección y operación (`check_permission`).
2. Enmascaramiento recursivo de secretos sin mutar el payload original (`sanitize_payload`).
3. Auditoría estructurada e integrada en MongoDB (`audit_event`).
4. Remediación automática ante patrones de abuso repetidos (`trigger_remediation`).
"""

import os
import sys
import uuid
import copy
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Set

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from pymongo import MongoClient
from pymongo.errors import OperationFailure


# =====================================================================
# CONEXIÓN A MONGODB (Compatible con M06, M07 y M08)
# =====================================================================

def get_mongo_uri() -> str:
    """
    Construye la URI de conexión dinámicamente mediante variables de entorno.
    Garantiza cero credenciales hardcodeadas en el código fuente.
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
    Retorna la instancia de base de datos MongoDB configurada en el entorno.
    """
    nombre_bd = db_name or os.getenv("MONGO_DB", "cdrl_nosql")
    cliente = MongoClient(get_mongo_uri(), serverSelectionTimeoutMS=4000)
    return cliente[nombre_bd]


# =====================================================================
# 1. CONTROL DE ACCESO POR COLECCIÓN Y OPERACIÓN (RBAC)
# =====================================================================

RBAC_POLICY: Dict[str, Dict[str, Set[str]]] = {
    "cdrl_reader": {
        "eventos_operativos": {"find", "read"},
    },
    "cdrl_writer": {
        "eventos_operativos": {"find", "read", "insert", "write"},
    },
    "cdrl_auditor": {
        "audit_logs": {"find", "read", "insert"},
        "audit_log": {"find", "read", "insert"},
    },
    "admin": {
        "*": {"find", "read", "insert", "write", "update", "delete", "createRole", "authenticate"},
    },
}

# Alias de compatibilidad para nombres cortos de rol
ROLE_ALIASES: Dict[str, str] = {
    "reader": "cdrl_reader",
    "read_role": "cdrl_reader",
    "writer": "cdrl_writer",
    "write_role": "cdrl_writer",
    "auditor": "cdrl_auditor",
    "audit_role": "cdrl_auditor",
    "cdrl_admin": "admin",
}


def check_permission(actor_role: str, action: str, resource: str) -> bool:
    """
    Valida si un rol (`actor_role`) tiene permiso para ejecutar una operación (`action`)
    sobre una colección o recurso (`resource`).

    Si el rol no existe o no cuenta con el privilegio requerido, levanta `PermissionError`.
    """
    if not actor_role or not action or not resource:
        raise PermissionError("Parámetros de autorización incompletos (actor_role, action, resource son requeridos).")

    normalized_role = ROLE_ALIASES.get(actor_role.strip().lower(), actor_role.strip().lower())
    normalized_action = action.strip()
    normalized_resource = resource.strip()

    if normalized_role not in RBAC_POLICY:
        raise PermissionError(
            f"Acceso denegado (RBAC): El rol '{actor_role}' no está reconocido en la política de seguridad."
        )

    permisos_rol = RBAC_POLICY[normalized_role]

    # Verificar acceso comodín (admin) o acceso específico al recurso
    acciones_permitidas = permisos_rol.get("*", set()) | permisos_rol.get(normalized_resource, set())

    if normalized_action not in acciones_permitidas and normalized_action.lower() not in acciones_permitidas:
        raise PermissionError(
            f"Acceso denegado (RBAC): El rol '{actor_role}' no tiene permiso para ejecutar "
            f"la acción '{action}' sobre el recurso '{resource}'."
        )

    return True


# =====================================================================
# 2. ENMASCARAMIENTO RECURSIVO DE SECRETOS
# =====================================================================

DEFAULT_SENSITIVE_KEYS: Set[str] = {
    "password",
    "secret",
    "token",
    "api_key",
    "credential",
    "auth",
    "passwd",
    "pwd",
    "authorization",
    "key",
}


def _get_sensitive_keys() -> Set[str]:
    """
    Obtiene el conjunto de llaves sensibles combinando la lista base del ADR-009
    con la variable de entorno opcional `AUDIT_MASKED_FIELDS`.
    """
    keys = set(DEFAULT_SENSITIVE_KEYS)
    env_fields = os.getenv("AUDIT_MASKED_FIELDS", "")
    if env_fields.strip():
        for field in env_fields.split(","):
            clean_field = field.strip().lower()
            if clean_field:
                keys.add(clean_field)
    return keys


def sanitize_payload(payload: Any, mask_value: str = "*** [SANITIZED] ***") -> Any:
    """
    Recorre recursivamente una copia profunda del diccionario o lista proporcionada
    y reemplaza el valor de cualquier llave sensible por `'*** [SANITIZED] ***'`.
    Garantiza que el objeto original en memoria no sea mutado.
    """
    if payload is None:
        return {}

    copia_segura = copy.deepcopy(payload)
    campos_sensibles = _get_sensitive_keys()

    def _recorrer(obj: Any) -> Any:
        if isinstance(obj, dict):
            resultado = {}
            for k, v in obj.items():
                if str(k).strip().lower() in campos_sensibles:
                    resultado[k] = mask_value
                elif isinstance(v, (dict, list)):
                    resultado[k] = _recorrer(v)
                else:
                    resultado[k] = v
            return resultado
        elif isinstance(obj, list):
            return [_recorrer(item) for item in obj]
        return obj

    return _recorrer(copia_segura)


# =====================================================================
# 3. AUDITORÍA INTEGRADA EN MONGODB
# =====================================================================

def audit_event(
    db,
    actor: str,
    action: str,
    resource: str,
    result: str,
    payload: Optional[Dict[str, Any]] = None,
    detail: Optional[str] = None,
    client_ip: str = "internal",
) -> Dict[str, Any]:
    """
    Registra un evento de auditoría en la colección `audit_logs` de MongoDB,
    garantizando que cualquier `payload` pase primero por `sanitize_payload`
    para evitar la persistencia de secretos en texto plano.
    """
    payload_sanitizado = sanitize_payload(payload) if payload is not None else {}

    detalle_seguro = detail or (
        f"Operación '{action}' ejecutada por '{actor}' sobre '{resource}' con resultado '{result}'."
    )

    documento_auditoria: Dict[str, Any] = {
        "audit_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "action": action,
        "resource": resource,
        "result": result,
        "outcome": result,
        "detail": detalle_seguro,
        "payload": payload_sanitizado,
        "client_ip": client_ip,
        "schema_version": 1,
    }

    # Guardar en la colección solicitada `audit_logs`
    db["audit_logs"].insert_one(copy.deepcopy(documento_auditoria))

    # Espejo en `audit_log` para mantener compatibilidad con consultas directas del ADR-009
    try:
        db["audit_log"].insert_one(copy.deepcopy(documento_auditoria))
    except Exception:
        pass

    return documento_auditoria


# =====================================================================
# 4. REMEDIACIÓN ANTE ABUSOS REPETIDOS
# =====================================================================

def trigger_remediation(db, actor: str, reason: str) -> Dict[str, Any]:
    """
    Actúa ante la detección de abuso por parte de un `actor`:
    1. Marca al actor con `is_blocked=True` en la colección `user_profiles`.
    2. Registra una alerta crítica inmutable (`ABUSE_DETECTED` / `ALERT`) en `audit_logs`.
    3. Intenta revocar sesiones activas del actor en MongoDB (`killAllSessions`) si aplica.
    4. Emite una alerta estructurada a `stderr` para monitoreo externo.
    """
    ahora_iso = datetime.now(timezone.utc).isoformat()
    threshold = int(os.getenv("ABUSE_THRESHOLD", "3"))
    window_seconds = int(os.getenv("ABUSE_WINDOW_SECONDS", "60"))

    # 1. Bloquear al actor en la colección de perfiles de usuario
    estado_bloqueo = {
        "actor": actor,
        "is_blocked": True,
        "blocked_at": ahora_iso,
        "reason": reason,
        "abuse_threshold": threshold,
        "abuse_window_seconds": window_seconds,
    }
    db["user_profiles"].update_one(
        {"actor": actor},
        {"$set": estado_bloqueo, "$inc": {"remediation_count": 1}},
        upsert=True,
    )

    # 2. Intentar revocar sesiones activas en el motor (best-effort según privilegios)
    sesion_revocada = False
    try:
        db.command("killAllSessions", [{"user": actor, "db": db.name}])
        sesion_revocada = True
    except OperationFailure:
        sesion_revocada = False
    except Exception:
        sesion_revocada = False

    # 3. Registrar evento crítico en el log de auditoría (sanitizado)
    alerta_doc = audit_event(
        db=db,
        actor=actor,
        action="ABUSE_DETECTED",
        resource="user_profiles",
        result="ALERT",
        payload={
            "reason": reason,
            "is_blocked": True,
            "session_revoked": sesion_revocada,
            "threshold": threshold,
            "window_seconds": window_seconds,
        },
        detail=f"Remediación activada para '{actor}': {reason}",
    )

    # 4. Emitir notificación a stderr para pipelines y agregadores de logs
    print(
        f"[SECURITY ALERT] Remediación activada | actor={actor} | is_blocked=True | "
        f"reason={reason} | timestamp={ahora_iso}",
        file=sys.stderr,
    )

    return {
        "actor": actor,
        "is_blocked": True,
        "reason": reason,
        "session_revoked": sesion_revocada,
        "audit_id": alerta_doc["audit_id"],
        "timestamp": ahora_iso,
    }


def evaluate_and_remediate_if_needed(
    db,
    actor: str,
    window_seconds: Optional[int] = None,
    threshold: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Función auxiliar que verifica si un `actor` ha acumulado >= `threshold` eventos
    con resultado 'DENIED' dentro de la ventana de tiempo y dispara `trigger_remediation`.
    """
    umbral = threshold if threshold is not None else int(os.getenv("ABUSE_THRESHOLD", "3"))
    ventana = window_seconds if window_seconds is not None else int(os.getenv("ABUSE_WINDOW_SECONDS", "60"))

    limite_inferior = (datetime.now(timezone.utc) - timedelta(seconds=ventana)).isoformat()

    intentos_denegados = db["audit_logs"].count_documents({
        "actor": actor,
        "result": "DENIED",
        "timestamp": {"$gte": limite_inferior},
    })

    if intentos_denegados >= umbral:
        motivo = (
            f"Umbral de abuso superado: {intentos_denegados} intentos DENIED "
            f"en los últimos {ventana} segundos (umbral={umbral})."
        )
        return trigger_remediation(db, actor=actor, reason=motivo)

    return None

