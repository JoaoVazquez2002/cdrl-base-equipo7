.PHONY: setup verify run clean

setup:
	@echo "=> Levantando infraestructura de bases de datos..."
	docker compose up -d
	@echo "=> Creando entorno virtual e instalando dependencias..."
	python3 -m venv venv
	./venv/bin/pip install --upgrade pip
	./venv/bin/pip install -r requirements.txt
	@echo "=> Setup completado."

verify:
	@echo "=> Ejecutando pruebas automatizadas..."
	PYTHONPATH=. ./venv/bin/pytest tests/ -v

run:
	@echo "=> Ejecutando ruta crítica..."
	PYTHONPATH=. ./venv/bin/python src/main.py

clean:
	@echo "=> Limpiando entorno..."
	docker compose down -v
	rm -rf venv
	rm -rf .pytest_cache
	rm -rf __pycache__