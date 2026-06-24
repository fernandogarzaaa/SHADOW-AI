PYTHONPATH=apps/shadow-node:packages/agent-core:packages/memory-engine:packages/axiom-adapter:packages/ghost-adapter
.PHONY: setup test run demo
setup:
	python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
test:
	PYTHONPATH=$(PYTHONPATH) pytest -q
run:
	PYTHONPATH=$(PYTHONPATH) uvicorn shadow_node.main:app --app-dir apps/shadow-node --reload --port 8787
demo:
	PYTHONPATH=$(PYTHONPATH) python scripts/demo_e2e.py
