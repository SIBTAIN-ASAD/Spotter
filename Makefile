.PHONY: setup dev test lint format migrate load-fuel docker-up docker-down

PYTHON ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python

setup: $(VENV)/bin/activate migrate load-fuel

$(VENV)/bin/activate: requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@test -f .env || cp .env.example .env

migrate:
	$(PY) manage.py migrate

load-fuel:
	$(PY) manage.py load_fuel_stations

dev:
	$(PY) manage.py runserver

test:
	$(PY) -m pytest

lint:
	$(VENV)/bin/ruff check .

format:
	$(VENV)/bin/ruff check --fix .
	$(VENV)/bin/ruff format .

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down
