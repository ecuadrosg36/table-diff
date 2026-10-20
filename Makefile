.PHONY: demo test

demo:
	uv run python scripts/demo.py

test:
	uv run ruff check .
	uv run pytest -q
