PYTHON ?= python3
ARGS ?=
ifeq ($(OS),Windows_NT)
PY = .venv/Scripts/python
else
PY = .venv/bin/python
endif

.PHONY: install install-vision install-fetch install-arduino native local neon stop mock replay arduino arduino-mock arduino-devices touch calibrate camera test lint build schemas smoke migrate lock

# Setup
install:
	$(PYTHON) -m venv .venv
	$(PY) -m pip install --require-hashes -r requirements-dev.txt
install-vision:
	$(PY) -m pip install -r requirements-vision.txt
install-fetch:
	$(PY) -m pip install --require-hashes -r requirements-fetch.txt
install-arduino:
	$(PY) -m pip install -r requirements-arduino.txt

# Backend (one process serves the API, the UI WebSocket and audio)
native:
	$(PY) -m backend.server
local:
	docker compose up -d --build --wait
neon:
	docker compose -f compose.neon.yaml up -d --build --wait
stop:
	docker compose down

# Sensor bridges (run next to the backend)
mock:
	$(PY) -m backend.sensors.bridge --mode mock $(ARGS)
replay:
	$(PY) -m backend.sensors.bridge --mode replay $(ARGS)
arduino:
	$(PY) -m backend.sensors.bridge --mode arduino $(ARGS)
arduino-mock:
	$(PY) -m backend.sensors.bridge --mode arduino-mock --count 24 $(ARGS)
arduino-devices:
	$(PY) -m backend.sensors.arduino $(ARGS)
touch:
	$(PY) -m scripts.touch
calibrate:
	$(PY) -m backend.sensors.calibration $(ARGS)
camera:
	$(PY) -m backend.vision.observe $(ARGS)

# Checks and maintenance
test:
	$(PY) -m pytest -q
lint:
	$(PY) -m ruff check backend shared scripts tests
	$(PY) -m ruff format --check backend shared scripts tests
build:
	docker build -f backend/Dockerfile -t talking-plant-backend:local .
schemas:
	$(PY) -m scripts.export_contracts
smoke:
	$(PY) -m scripts.smoke $(ARGS)
migrate:
	$(PY) -m backend.database.migrate
lock:
	uv pip compile --universal --generate-hashes -q requirements.in -o requirements.txt
	uv pip compile --universal --generate-hashes -q requirements-dev.in -o requirements-dev.txt
	uv pip compile --universal --generate-hashes -q requirements-fetch.in -o requirements-fetch.txt
