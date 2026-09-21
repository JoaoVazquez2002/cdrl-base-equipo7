# ADR 003: Implementación de Roles y Privilegios Estrictos

## Contexto
El entorno requería separar accesos operativos para evitar modificaciones no autorizadas, cumpliendo con el principio de menor privilegio.

## Decisión
Se crearon roles específicos en `00-roles.sh` y se implementó `ALTER DEFAULT PRIVILEGES` para garantizar que las tablas hereden las restricciones automáticamente.

## Consecuencias
Seguridad mejorada y prevención de inyecciones destructivas, a cambio de una mayor complejidad en las pruebas de conexión.
