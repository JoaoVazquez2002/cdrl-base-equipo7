# ADR-002: Modelo Relacional y Decisiones de Arquitectura - Semana 02

## Estado
Aceptado

## Contexto
En la Semana 02, el equipo requirió evolucionar la base de datos inicial hacia un modelo relacional robusto que permita gestionar de manera segura y eficiente la información del sistema, garantizando la integridad referencial y la consistencia de los datos mediante consultas parametrizadas.

## Decisión
Se implementó un diseño relacional estructurado mediante migraciones SQL idempotentes y consultas seguras en la capa de datos utilizando parámetros protegidos contra inyecciones SQL.

### 1. ¿Por qué esta estructura de tablas?
* **Normalización:** Se estructuraron las tablas separando entidades clave para evitar redundancia de datos y anomalías en las operaciones de inserción, actualización o eliminación.
* **Relaciones Claras:** Se definieron llaves primarias en cada tabla para garantizar la unicidad de los registros y llaves foráneas para mantener la coherencia lógica entre las entidades asociadas.

### 2. Alternativas Consideradas
* **Estructura No Normalizada / Documental:** Se evaluó el uso de esquemas más flexibles (tipo NoSQL o JSON dentro de la misma base), pero se descartó porque la naturaleza del sistema académico u operativo requiere transacciones estrictas y reportes relacionales complejos.
* **Creación de tablas sin restricciones explícitas:** Se consideró omitir validaciones a nivel de base de datos para delegarlas completamente al código de la aplicación; sin embargo, se descartó para priorizar la seguridad en la capa de datos (la base de datos misma).

### 3. ¿Cómo se aseguran los invariantes?
Los invariantes y reglas de negocio del sistema se garantizan mediante:
* **Restricciones NOT NULL:** Obligan a que los campos indispensables cuenten con información obligatoria en cada transacción.
* **Restricciones CHECK:** Se implementaron reglas lógicas directamente en el motor de la base de datos para restringir dominios de valores inválidos (por ejemplo, rangos numéricos o estados específicos).
* **Integridad Referencial:** Las llaves foráneas con reglas de control evitan registros huérfanos.
* **Consultas Parametrizadas:** A nivel de software, el uso estricto de parámetros en las consultas evita la alteración maliciosa o accidental de los datos.

## Consecuencias
* Mayor seguridad e integridad en los datos almacenados.
* Facilidad para la ejecución de pruebas automáticas que validan el comportamiento ante casos límite y fallos intencionales.