.PHONY: setup test run
setup:
	python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
test:
	pytest
run:
	uvicorn shadow_node.main:app --app-dir apps/shadow-node --reload --port 8787
