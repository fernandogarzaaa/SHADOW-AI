FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONPATH=/app/apps/shadow-node:/app/packages/agent-core:/app/packages/memory-engine:/app/packages/axiom-adapter:/app/packages/ghost-adapter \
    SHADOW_DATA_DIR=/data \
    SHADOW_WORKSPACE_DIR=/data/workspace
# Run unprivileged; all mutable state (keys, DBs, workspace) lives on /data.
RUN useradd --system --uid 10001 --home-dir /data shadownode \
    && mkdir -p /data && chown shadownode:shadownode /data
USER shadownode
VOLUME ["/data"]
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8787/health',timeout=3).status==200 else 1)"
CMD ["uvicorn","shadow_node.main:app","--app-dir","apps/shadow-node","--host","0.0.0.0","--port","8787"]
