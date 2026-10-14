# ADR 003: Implementación de Roles y Privilegios Estrictos

## Contexto
El entorno requería separar accesos operativos para evitar modificaciones no autorizadas, cumpliendo con el principio de menor privilegio.

## Decisión
Se crearon roles específicos en `00-roles.sh` y se implementó `ALTER DEFAULT PRIVILEGES` para garantizar que las tablas hereden las restricciones automáticamente.
Adicionalmente, se aplican dos políticas estrictas de menor privilegio:
1. **Escritor (`write_role`)**: Se le retiran los privilegios de `DELETE` sobre las tablas de telemetría para proteger la persistencia histórica de datos y evitar manipulaciones destructivas.
2. **Operador (`operation_role`)**: Se revoca el acceso directo a la tabla `telemetry` y se expone exclusivamente a través de la vista segura `telemetry_operator_view`, la cual oculta mediciones sensibles de temperatura.

## Consecuencias
Seguridad mejorada y prevención de inyecciones destructivas, garantizando la confidencialidad de métricas sensibles y la inmutabilidad de los registros históricos de telemetría.

## Rotación de Secretos
Los secretos y credenciales no están versionados en el repositorio, se inyectan mediante el archivo `.env` y variables del entorno en el pipeline. Para rotar las credenciales:
1. Generar nuevas contraseñas seguras.
2. Actualizar el archivo `.env` en los entornos de despliegue.
3. Reiniciar los contenedores (`docker compose down -v` y `make run`) para que PostgreSQL asigne las nuevas contraseñas a los usuarios existentes mediante el script de inicialización.