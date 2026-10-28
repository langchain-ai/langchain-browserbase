ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

.PHONY: install format lint typecheck test check build

install:
	uv sync --project $(ROOT) --locked

format:
	uv run --project $(ROOT) ruff format $(ROOT)src $(ROOT)tests

lint:
	uv run --project $(ROOT) ruff format --check $(ROOT)src $(ROOT)tests
	uv run --project $(ROOT) ruff check $(ROOT)src $(ROOT)tests

typecheck:
	uvx --from mypy==1.19.1 mypy --config-file $(ROOT)pyproject.toml --python-executable $(ROOT).venv/bin/python $(ROOT)src $(ROOT)tests/typecheck.py

test:
	NO_COLOR=1 uv run --project $(ROOT) pytest $(ROOT)tests/test_middleware.py --color=no

check: lint typecheck test

build:
	uv build --project $(ROOT)
