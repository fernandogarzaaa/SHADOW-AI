.PHONY: setup test run demo compile mcp
setup:
	python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt && pip install -e .
test:
	pytest -q
compile:
	python -m compileall apps/shadow-node packages
demo:
	PYTHONPATH=apps/shadow-node:packages/agent-core:packages/memory-engine:packages/axiom-adapter:packages/ghost-adapter python scripts/demo.py
run:
	PYTHONPATH=apps/shadow-node:packages/agent-core:packages/memory-engine:packages/axiom-adapter:packages/ghost-adapter SHADOW_RUNTIME_DB=$${SHADOW_RUNTIME_DB:-data/runtime.db} SHADOW_MEMORY_DB=$${SHADOW_MEMORY_DB:-data/memory.db} uvicorn shadow_node.main:app --app-dir apps/shadow-node --reload --host 127.0.0.1 --port 8787
mcp:
	PYTHONPATH=apps/shadow-node:packages/agent-core:packages/memory-engine:packages/axiom-adapter:packages/ghost-adapter python -m shadow_node.mcp_server
