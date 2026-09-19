# Makefile for CycloneShield
# Usage: make <target>

.PHONY: setup data api web test clean lint help

PYTHON := python
PIP := pip
VENV := .venv
VENV_ACTIVATE := $(VENV)/Scripts/activate

help: ## Show this help
	@echo "CycloneShield — Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: ## Install all Python deps, check Node, copy .env.example
	@echo "=== CycloneShield Setup ==="
	$(PYTHON) -m venv $(VENV) || echo "venv already exists"
	. $(VENV_ACTIVATE) && $(PIP) install --upgrade pip
	. $(VENV_ACTIVATE) && $(PIP) install -r requirements.txt
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env from .env.example — fill in your keys!"; fi
	@echo ""
	@echo "=== Checking GEE authentication ==="
	. $(VENV_ACTIVATE) && $(PYTHON) pipeline/gee_auth.py || true
	@echo ""
	@echo "=== Installing frontend dependencies ==="
	cd frontend && npm install
	@echo ""
	@echo "=== Setup complete. Next steps: ==="
	@echo "  1. Edit .env with your GEMINI_API_KEY"
	@echo "  2. Run: earthengine authenticate"
	@echo "  3. Run: make data"

data: ## Run full pipeline (offline data prep)
	@echo "=== Running CycloneShield Pipeline ==="
	. $(VENV_ACTIVATE) && $(PYTHON) pipeline/build_all.py

data-track: ## Run only track fetch (Phase 1 step 1)
	. $(VENV_ACTIVATE) && $(PYTHON) pipeline/step_01_fetch_track.py

data-wind: ## Run only wind field (Phase 1 step 2)
	. $(VENV_ACTIVATE) && $(PYTHON) pipeline/step_02_wind_field.py

data-surge: ## Run only surge model (Phase 2 step 1)
	. $(VENV_ACTIVATE) && $(PYTHON) pipeline/step_03_surge_model.py

data-rainfall: ## Run only rainfall model (Phase 2 step 2)
	. $(VENV_ACTIVATE) && $(PYTHON) pipeline/step_04_rainfall_model.py

data-sar: ## Run only SAR validation (Phase 2 step 3)
	. $(VENV_ACTIVATE) && $(PYTHON) pipeline/step_05_sar_validation.py

data-infra: ## Run only OSM infrastructure extract (Phase 1 step 3)
	. $(VENV_ACTIVATE) && $(PYTHON) pipeline/step_06_osm_infra.py

data-exposure: ## Run only exposure analysis (Phase 3)
	. $(VENV_ACTIVATE) && $(PYTHON) pipeline/step_07_exposure.py

data-cascade: ## Run only cascade simulation (Phase 3)
	. $(VENV_ACTIVATE) && $(PYTHON) pipeline/step_08_cascade.py

data-insurance: ## Run only insurance triggers (Phase 3)
	. $(VENV_ACTIVATE) && $(PYTHON) pipeline/step_09_insurance.py

data-advisories: ## Generate Gemini advisories (Phase 4)
	. $(VENV_ACTIVATE) && $(PYTHON) pipeline/step_10_advisories.py

sync-data: ## Sync processed data to frontend/public/data and check <50MB size
	$(PYTHON) -c "import shutil, os, sys; os.makedirs('frontend/public/data', exist_ok=True); [shutil.copy2(os.path.join('data/processed', f), os.path.join('frontend/public/data', f)) for f in os.listdir('data/processed') if not f.startswith('.') and not os.path.isdir(os.path.join('data/processed', f))]; total_mb = sum(os.path.getsize(os.path.join('frontend/public/data', f)) for f in os.listdir('frontend/public/data') if os.path.isfile(os.path.join('frontend/public/data', f))) / (1024 * 1024); print(f'Synced data size: {total_mb:.2f} MB'); sys.exit(1 if total_mb > 50 else 0)"

api: ## Start FastAPI backend (default port 8000)
	. $(VENV_ACTIVATE) && uvicorn backend.main:app --reload --port 8000

web: ## Start frontend dev server
	cd frontend && npm run dev

web-build: ## Build frontend for production
	cd frontend && npm run build

test: ## Run all tests
	. $(VENV_ACTIVATE) && pytest tests/ -v --tb=short

test-fast: ## Run tests excluding slow GEE-dependent ones
	. $(VENV_ACTIVATE) && pytest tests/ -v --tb=short -m "not gee"

lint: ## Run linting (ruff + mypy)
	. $(VENV_ACTIVATE) && ruff check pipeline/ backend/ tests/
	. $(VENV_ACTIVATE) && mypy pipeline/ backend/ --ignore-missing-imports

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache
	rm -rf frontend/dist

clean-data: ## Remove processed data (DANGEROUS: re-run make data after)
	@echo "This will delete all processed data. Press Ctrl+C to cancel."
	@sleep 3
	rm -rf data/processed/*
	touch data/processed/.gitkeep

deploy-web: ## Deploy frontend to Vercel
	cd frontend && npx vercel --prod

# Windows-friendly versions of setup targets
setup-win: ## Windows: Install Python deps
	$(PYTHON) -m venv $(VENV)
	$(VENV)\Scripts\pip install --upgrade pip
	$(VENV)\Scripts\pip install -r requirements.txt
	@if not exist .env copy .env.example .env
	$(VENV)\Scripts\python pipeline/gee_auth.py
	cd frontend && npm install
