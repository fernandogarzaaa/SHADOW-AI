FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONPATH=/app/apps/shadow-node:/app/packages/agent-core:/app/packages/memory-engine:/app/packages/axiom-adapter:/app/packages/ghost-adapter
CMD ["uvicorn","shadow_node.main:app","--app-dir","apps/shadow-node","--host","0.0.0.0","--port","8787"]
