import os

import uvicorn

# Loopback by default: set SHADOW_HOST=0.0.0.0 to expose the node on the LAN
# (pair the first owner with the bootstrap code printed at startup).
uvicorn.run(
    "shadow_node.main:app",
    host=os.getenv("SHADOW_HOST", "127.0.0.1"),
    port=int(os.getenv("SHADOW_PORT", "8787")),
    reload=os.getenv("SHADOW_RELOAD", "false").lower() == "true",
)
