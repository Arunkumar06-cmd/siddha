.PHONY: build lint test audit clean
PY := python3

build: lint typecheck test
	@echo "build OK"

lint:
	ruff check .

typecheck:
	$(PY) -m py_compile server.py src/*.py src/*.py tests/*.py

test:
	$(PY) -m pytest tests/ -q

coverage:
	$(PY) -m pytest tests/ --cov=src --cov=server --cov-report=term-missing -q

clean:
	find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete
	rm -rf .pytest_cache
