def obtener_dispositivos(cursor):
    """Obtiene todos los dispositivos registrados."""
    cursor.execute("""
        SELECT id, name, firmware_version
        FROM devices
        ORDER BY name;
    """)
    return cursor.fetchall()


def obtener_dispositivo_por_nombre(cursor, nombre):
    """Busca un dispositivo usando un parámetro seguro."""
    cursor.execute("""
        SELECT id, name, firmware_version
        FROM devices
        WHERE name = %s;
    """, (nombre,))
    return cursor.fetchone()


def obtener_eventos_por_dispositivo(cursor, device_id):
    """Obtiene los eventos de un dispositivo específico."""
    cursor.execute("""
        SELECT id, event_type, value, captured_at
        FROM telemetry_events
        WHERE device_id = %s
        ORDER BY captured_at DESC;
    """, (device_id,))
    return cursor.fetchall()


def obtener_eventos_por_tipo(cursor, event_type):
    """Obtiene eventos filtrados por tipo."""
    cursor.execute("""
        SELECT id, device_id, value, captured_at
        FROM telemetry_events
        WHERE event_type = %s;
    """, (event_type,))
    return cursor.fetchall()