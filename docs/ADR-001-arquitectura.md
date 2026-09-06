# ADR-001 — Selección de Stack Tecnológico y Entorno Reproducible

## Estado

Aceptado

## Contexto

El hito M01 requiere levantar una base relacional compatible con la nube, implementar migraciones 100% reproducibles y definir un contrato de datos ejecutable. Se necesita establecer un estándar de desarrollo para todo el equipo.

## Decisión

* Entorno Reproducible (Docker): Se adoptó Docker Compose para la inicialización nativa de PostgreSQL. Esto aísla la base de datos del sistema operativo anfitrión, elimina la configuración manual y cumple estrictamente con el requisito de tener un "respaldo reproducible" para el equipo.


* Lenguaje (Python): Se seleccionó Python como lenguaje principal para el backend y QA. Lo elegimos por su facilidad de lectura, su rapidez para escribir scripts de prueba y porque cuenta con un ecosistema muy maduro (como `pytest` y `psycopg2`) que nos permite hacer validaciones ágiles, conectar directo con PostgreSQL y cumplir sin problemas con los casos límite y contratos de datos exigidos en la rúbrica.

## Consecuencias

* La integración de nuevos desarrolladores se reduce a ejecutar un solo comando (make run) sin requerir instalaciones complejas locales.
