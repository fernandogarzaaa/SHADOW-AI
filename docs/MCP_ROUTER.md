# Shadow Router — MCP server for route-prompting

Exposes Shadow's hybrid local+frontier routing as **Model Context Protocol**
tools, so any MCP client (Claude Desktop, Claude Code, other agents) can route
prompts through Shadow to cut frontier token cost — without re-implementing the
router. This mirrors AXIOM-AETHER's own MCP server (`mcp_stdio.rs`).

## Tools
| Tool | What it does | Inference? |
|---|---|---|
| `route_estimate` | Decide local vs frontier for a prompt + estimate token savings | no |
| `compress_context` | AXIOM-compress text + skeleton digest + raw/compressed token counts | no |
| `route_complete` | Full hybrid completion: local short-circuit, or frontier with **compressed** context. Returns answer, route, savings | yes |
| `list_providers` | Connection status of each frontier provider | no |

Why it saves tokens (same as the in-node router): simple prompts are answered
fully on-device (zero frontier tokens); escalated prompts send only AXIOM-
compressed context (measured ~80% smaller on repetitive context) instead of the
raw retrieved memory.

## Run

```bash
make mcp          # python -m shadow_node.mcp_server  (stdio)
```

The `mcp` dependency is only imported by the server entrypoint — the FastAPI
node never loads it.

## Connect from Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "shadow-router": {
      "command": "python",
      "args": ["-m", "shadow_node.mcp_server"],
      "env": {
        "PYTHONPATH": "/abs/path/SHADOW-AI/apps/shadow-node:/abs/path/SHADOW-AI/packages/agent-core:/abs/path/SHADOW-AI/packages/memory-engine:/abs/path/SHADOW-AI/packages/axiom-adapter:/abs/path/SHADOW-AI/packages/ghost-adapter",
        "SHADOW_MODEL_PROVIDER": "anthropic",
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

Then a client can call, e.g.:

```jsonc
// route_complete — let Shadow decide and answer
{"name": "route_complete", "arguments": {"prompt": "summarize these notes", "context": "<text>", "allow_cloud": true}}
// or just get a routing decision + savings without paying for inference
{"name": "route_estimate", "arguments": {"prompt": "what's the capital of France?"}}
```

`route_complete` resolves provider credentials from the encrypted
`CredentialStore` (or env). Frontier escalation requires `allow_cloud: true` and
a connected provider; otherwise everything stays local.

## Privacy
Context passed to these tools is treated as **untrusted** (never executed as
instructions). Provider credentials are read from the encrypted store; nothing is
logged. Consumer chat subscriptions still cannot be used — see `HYBRID_LLM.md`.
