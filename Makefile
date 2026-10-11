.PHONY: setup verify run clean

setup:
	@echo "=> Preparando entorno para CI..."
	cp -n .env.example .env || true
	@echo "=> Levantando infraestructura de bases de datos..."
	docker compose up -d
	@echo "=> Esperando a que los motores esten listos..."
	sleep 5
	@echo "=> Creando entorno virtual e instalando dependencias..."
	python3 -m venv venv
	./venv/bin/pip install --upgrade pip
	./venv/bin/pip install -r requirements.txt
	@echo "=> Inicializando datos y esquemas de forma idempotente..."
	PYTHONPATH=. ./venv/bin/python src/m06_recovery.py setup
	@echo "=> Setup completado."

verify:
	@echo "=> Ejecutando pruebas automatizadas y generando XML en artifacts/..."
	mkdir -p artifacts
	PYTHONPATH=. ./venv/bin/pytest tests/ -v --junitxml=artifacts/test_results.xml

run:
	@echo "=> Ejecutando simulacro de fallo y recuperacion..."
	PYTHONPATH=. ./venv/bin/python src/m06_recovery.py demo

clean:
	@echo "=> Limpiando entorno..."
	docker compose down -v
	rm -rf venv .pytest_cache __pycache__ artifacts .env