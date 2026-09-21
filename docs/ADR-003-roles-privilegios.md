# ADR 003: Implementación de Roles y Privilegios Estrictos

## Contexto
El entorno requería separar accesos operativos para evitar modificaciones no autorizadas, cumpliendo con el principio de menor privilegio.

## Decisión
Se crearon roles específicos en `00-roles.sh` y se implementó `ALTER DEFAULT PRIVILEGES` para garantizar que las tablas hereden las restricciones automáticamente.

## Consecuencias
Seguridad mejorada y prevención de inyecciones destructivas, a cambio de una mayor complejidad en las pruebas de conexión.

## Rotación de Secretos
Los secretos y credenciales no están versionados en el repositorio, se inyectan mediante el archivo `.env` y variables del entorno en el pipeline. Para rotar las credenciales:
1. Generar nuevas contraseñas seguras.
2. Actualizar el archivo `.env` en los entornos de despliegue.
3. Reiniciar los contenedores (`docker compose down -v` y `make run`) para que PostgreSQL asigne las nuevas contraseñas a los usuarios existentes mediante el script de inicialización.