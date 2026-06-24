import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
for rel in ["apps/shadow-node", "packages/agent-core", "packages/memory-engine", "packages/axiom-adapter", "packages/ghost-adapter"]:
    sys.path.insert(0, str(ROOT / rel))
import uvicorn
uvicorn.run("shadow_node.main:app", host="0.0.0.0", port=8787, reload=True)
