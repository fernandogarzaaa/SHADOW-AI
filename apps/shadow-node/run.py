import uvicorn
uvicorn.run("shadow_node.main:app", host="0.0.0.0", port=8787, reload=True)
