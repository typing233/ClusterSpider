.PHONY: dev api worker install lint test docker-up docker-down

install:
	pip install -e ".[dev]"
	cd frontend && npm install

dev:
	docker-compose up neo4j redis -d
	uvicorn clusterspider.api.app:app --reload --port 8000 &
	celery -A clusterspider.workers.celery_app worker -Q scans,reports --loglevel=info -c 2 &
	cd frontend && npm run dev

api:
	uvicorn clusterspider.api.app:app --host 0.0.0.0 --port 8000 --reload

worker:
	celery -A clusterspider.workers.celery_app worker -Q scans,reports --loglevel=info -c 4

frontend:
	cd frontend && npm run dev

lint:
	ruff check clusterspider/
	mypy clusterspider/ --ignore-missing-imports

test:
	pytest tests/ -v --cov=clusterspider

docker-up:
	docker-compose up --build -d

docker-down:
	docker-compose down

seed:
	python scripts/seed_neo4j.py
