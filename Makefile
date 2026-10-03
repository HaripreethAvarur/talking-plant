PYTHON ?= python3
VENV = .venv/bin
ARGS ?=

.PHONY: install install-vision install-hardware install-fetch local neon stop native mock replay devices freewili calibrate camera image test lint build schemas smoke migrate
install:
	$(PYTHON) -m venv .venv
	$(VENV)/python -m pip install --require-hashes -r requirements-dev.txt
install-vision:
	$(VENV)/python -m pip install -r requirements-vision.txt
install-hardware:
	$(VENV)/python -m pip install --require-hashes -r requirements-hardware.txt
install-fetch:
	$(VENV)/python -m pip install --require-hashes -r requirements-fetch.txt
local:
	docker compose up -d --build --wait
neon:
	docker compose -f compose.neon.yaml up -d --build --wait
stop:
	docker compose down
native:
	$(VENV)/uvicorn backend.api:create_app --factory --host 127.0.0.1 --port $${PORT:-8000} --workers 1
mock:
	$(VENV)/python -m backend.sensors.bridge --mode mock $(ARGS)
replay:
	$(VENV)/python -m backend.sensors.bridge --mode replay $(ARGS)
devices:
	$(VENV)/python -m backend.sensors.diagnostics $(ARGS)
freewili:
	$(VENV)/python -m backend.sensors.bridge --mode freewili $(ARGS)
calibrate:
	$(VENV)/python -m backend.sensors.calibration $(ARGS)
camera image:
	$(VENV)/python -m backend.vision.observe $(ARGS)
test:
	$(VENV)/python -m pytest -q
lint:
	$(VENV)/ruff check backend shared scripts tests
	$(VENV)/ruff format --check backend shared scripts tests
build:
	docker build -f backend/Dockerfile -t talking-plant-backend:local .
schemas:
	$(VENV)/python -m scripts.export_contracts
smoke:
	$(VENV)/python -m scripts.smoke $(ARGS)
migrate:
	$(VENV)/python -m backend.database.migrate
