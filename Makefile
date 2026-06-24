.PHONY: setup test run demo compile
setup:
	python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
test:
	pytest -q
compile:
	python -m compileall apps/shadow-node packages
demo:
	PYTHONPATH=apps/shadow-node:packages/agent-core:packages/memory-engine:packages/axiom-adapter:packages/ghost-adapter python scripts/demo.py
run:
	uvicorn shadow_node.main:app --app-dir apps/shadow-node --reload --port 8787
