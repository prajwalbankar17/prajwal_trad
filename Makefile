.PHONY: help setup backend frontend migrate revision seed test lint infra-up infra-down

PY := backend/.venv/bin/python
PIP := backend/.venv/bin/pip

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup:        ## Create venv, install backend + frontend deps
	python3.12 -m venv backend/.venv
	$(PIP) install --upgrade pip
	$(PIP) install -r backend/requirements.txt
	cd frontend && npm install

infra-up:     ## Start Postgres + Redis in Docker
	docker compose up -d

infra-down:   ## Stop Docker infrastructure
	docker compose down

migrate:      ## Apply database migrations
	cd backend && .venv/bin/alembic upgrade head

revision:     ## Autogenerate a migration: make revision m="message"
	cd backend && .venv/bin/alembic revision --autogenerate -m "$(m)"

seed:         ## Seed roles, permissions, admin user, demo strategies
	cd backend && .venv/bin/python -m scripts.seed

backend:      ## Run the API (http://localhost:8000/docs)
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend:     ## Run the UI (http://localhost:5173)
	cd frontend && npm run dev

test:         ## Run backend tests
	cd backend && .venv/bin/pytest

lint:         ## Lint backend
	cd backend && .venv/bin/ruff check app tests scripts
