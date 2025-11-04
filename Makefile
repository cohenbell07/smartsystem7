.PHONY: help install dev backend frontend worker db seed test test-backend test-frontend fmt lint clean

help:
	@echo "Agent Factory - Makefile Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install      Install all dependencies"
	@echo "  make db           Run database migrations"
	@echo "  make seed         Seed database with demo data"
	@echo ""
	@echo "Development:"
	@echo "  make dev          Run backend + frontend + worker (3 processes)"
	@echo "  make backend      Run backend API only"
	@echo "  make frontend     Run frontend only"
	@echo "  make worker       Run background worker only"
	@echo ""
	@echo "Testing:"
	@echo "  make test         Run all tests"
	@echo "  make test-backend Run backend tests"
	@echo "  make test-frontend Run frontend tests"
	@echo ""
	@echo "Code Quality:"
	@echo "  make fmt          Format code (black, ruff, prettier)"
	@echo "  make lint         Lint code"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean        Remove generated files"

install:
	@echo "📦 Installing backend dependencies..."
	cd backend && python -m venv venv && \
		. venv/bin/activate && \
		pip install --upgrade pip && \
		pip install -r requirements.txt
	@echo "📦 Installing frontend dependencies..."
	cd frontend && npm install
	@echo "🎭 Installing Playwright browsers..."
	cd backend && . venv/bin/activate && playwright install chromium
	@echo "✅ Installation complete!"

dev:
	@echo "🚀 Starting Agent Factory in development mode..."
	@echo "   Backend:  http://localhost:8000"
	@echo "   Frontend: http://localhost:3000"
	@echo "   Docs:     http://localhost:8000/docs"
	@trap 'kill 0' EXIT; \
	(cd backend && . venv/bin/activate && uvicorn app.main:app --reload --port 8000) & \
	(cd backend && . venv/bin/activate && python -m workers.runner) & \
	(cd frontend && npm run dev) & \
	wait

backend:
	@echo "🐍 Starting backend API..."
	cd backend && . venv/bin/activate && uvicorn app.main:app --reload --port 8000

frontend:
	@echo "⚛️  Starting frontend..."
	cd frontend && npm run dev

worker:
	@echo "👷 Starting background worker..."
	cd backend && . venv/bin/activate && python -m workers.runner

db:
	@echo "🗄️  Running database migrations..."
	cd backend && . venv/bin/activate && alembic upgrade head
	@echo "✅ Database migrations complete!"

seed:
	@echo "🌱 Seeding database with demo data..."
	cd backend && . venv/bin/activate && python -m app.seed
	@echo "✅ Seeding complete!"

test:
	@echo "🧪 Running all tests..."
	@make test-backend
	@make test-frontend

test-backend:
	@echo "🐍 Running backend tests..."
	cd backend && . venv/bin/activate && pytest tests/ -v --cov=app --cov-report=term-missing

test-frontend:
	@echo "⚛️  Running frontend tests..."
	cd frontend && npm test

fmt:
	@echo "🎨 Formatting code..."
	cd backend && . venv/bin/activate && black app/ workers/ tests/ && ruff check app/ workers/ tests/ --fix
	cd frontend && npm run format
	@echo "✅ Code formatted!"

lint:
	@echo "🔍 Linting code..."
	cd backend && . venv/bin/activate && black app/ workers/ tests/ --check && ruff check app/ workers/ tests/
	cd frontend && npm run lint
	@echo "✅ Lint checks passed!"

clean:
	@echo "🧹 Cleaning generated files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	rm -rf backend/htmlcov
	rm -rf frontend/.next
	rm -rf frontend/out
	@echo "✅ Cleanup complete!"

.DEFAULT_GOAL := help
