.PHONY: setup verify run clean

setup:
	@echo "=> Preparando entorno para CI..."
	cp -n .env.example .env || true
	@echo "=> Levantando infraestructura de bases de datos..."
	docker compose up -d
	@echo "=> Esperando a que los motores esten listos..."
	sleep 5
	@echo "=> Provisionando roles y permisos en PostgreSQL..."
	docker compose exec -T postgres bash /docker-entrypoint-initdb.d/00-roles.sh
	@echo "=> Ejecutando migraciones y carga inicial de datos en PostgreSQL..."
	docker compose exec -T postgres psql -U cdrl_dev -d cdrl -f /docker-entrypoint-initdb.d/01-init.sql
	docker compose exec -T postgres psql -U cdrl_dev -d cdrl -f /docker-entrypoint-initdb.d/02-relational-model.sql
	docker compose exec -T postgres psql -U cdrl_dev -d cdrl -f /docker-entrypoint-initdb.d/03-seed.sql
	@echo "=> Creando entorno virtual e instalando dependencias..."
	python3 -m venv venv
	./venv/bin/pip install --upgrade pip
	./venv/bin/pip install -r requirements.txt
	@echo "=> Inicializando datos y esquemas de forma idempotente..."
	PYTHONPATH=. ./venv/bin/python src/init_mongo.py
	PYTHONPATH=. ./venv/bin/python src/m06_recovery.py setup
	@echo "=> Setup completado."

verify:
	@echo "=> Ejecutando pruebas automatizadas y generando XML en artifacts/..."
	mkdir -p artifacts
	PYTHONPATH=. ./venv/bin/pytest tests/ -v --junitxml=artifacts/test_results.xml

run:
	@echo "=> Ejecutando ruta crítica y simulador del sistema CDRL..."
	PYTHONPATH=. ./venv/bin/python src/main.py

clean:
	@echo "=> Limpiando entorno..."
	docker compose down -v
	rm -rf venv .pytest_cache __pycache__ artifacts .env