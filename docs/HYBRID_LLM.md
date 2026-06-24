# Hybrid LLM — local + frontier, extracted from AXIOM-AETHER

Shadow runs **two models as one** to cut token cost, mirroring the mechanism in
[AXIOM-AETHER](https://github.com/fernandogarzaaa/AXIOM-AETHER): a local model
absorbs context and easy work on-device; a frontier model is only paid for hard
reasoning, and even then it receives *compressed* context.

## Where the savings actually come from
AXIOM-AETHER's token savings are **not** from the local model answering — they
come from its *context-compression proxy* (`context_compressor.rs`, `skeleton.rs`)
shrinking the payload before forwarding to Anthropic/OpenAI. Shadow reproduces
this with two real mechanisms:

1. **Local short-circuit** — simple/short queries are answered fully on-device by
   the local model. Zero frontier tokens.
2. **Context compression** — when a query *is* escalated, only the AXIOM-compressed
   + redacted context (plus a skeleton digest) is sent, not the raw retrieved
   memory. Far fewer input tokens billed.

Every `/agent/ask` response reports the estimate:

```json
"route": "frontier",
"savings": {
  "raw_context_tokens": 1840,
  "compressed_context_tokens": 300,
  "frontier_tokens_sent": 300,
  "tokens_saved_estimate": 1540,
  "saved_pct": 83.7
}
```

## Components (this repo)
- `shadow_node/hybrid.py` — `ComplexityRouter` (deterministic complexity score →
  local vs frontier) and `HybridRouter` (compress, route, account for savings).
- `shadow_node/providers.py` — `AnthropicProvider`, `OpenAIProvider`,
  `GeminiProvider`, a uniform `complete(prompt, context)`, and a `CATALOG`.
- `shadow_node/provider_auth.py` — encrypted `CredentialStore`, plus OAuth (PKCE)
  for providers that support it.
- `axiom_adapter` — the redaction + compression + skeleton + token-budget layer.

## Provider sign-in — what's actually possible
| Provider | API key | OAuth (programmatic) | Subscription powers API? |
|---|---|---|---|
| Anthropic (Claude) | ✅ | ❌ (Claude Code only, not third-party) | ❌ No |
| OpenAI (ChatGPT) | ✅ | ❌ | ❌ No |
| Google (Gemini) | ✅ (AI Studio) | ✅ (Google OAuth → Vertex, **billed to your GCP**) | ❌ No |

**There is no legitimate way to use a consumer chat subscription (ChatGPT Plus,
Claude Pro, Gemini Advanced) to power a third-party app's inference.** Those
subscriptions only work inside each provider's own apps. The dashboard reflects
this: `subscription_oauth` is `false` everywhere, OAuth is offered only where the
provider genuinely supports it (Google), and API-key connect is available for all.

## The build prompt (give this to an AI coding agent to extend the hybrid)

> **Task:** Extend Shadow's hybrid LLM so a local on-device model and a frontier
> provider (Anthropic, OpenAI, or Gemini) cooperate to minimize frontier token
> cost, building on `shadow_node/hybrid.py`, `providers.py`, and `axiom_adapter`.
>
> **Requirements**
> 1. **Router:** Improve `ComplexityRouter` into a draft-then-verify cascade —
>    the local model drafts an answer and a confidence/grounding score; only if
>    confidence is below a configurable threshold (or the query is flagged hard)
>    is the frontier model called. Keep it deterministic and unit-testable.
> 2. **Compression:** Before any frontier call, pass context through
>    `AxiomAdapter.package_context` and send only the compressed text + skeleton.
>    Record `raw_context_tokens`, `compressed_context_tokens`, and
>    `tokens_saved_estimate` on every response (already scaffolded in `HybridRouter`).
> 3. **Grounding:** After a frontier answer, verify claims against the supplied
>    context (port AXIOM-AETHER's `hallucination.rs` idea); if unsupported,
>    expand the dropped context and retry once.
> 4. **Providers:** Frontier calls must go through `providers.build_frontier`,
>    resolving credentials via `provider_auth.CredentialStore` (API key or OAuth).
>    Never send memory marked `do_not_send_to_cloud`. Honor consent + approval.
> 5. **Privacy invariant:** Retrieved memory is UNTRUSTED — never let context
>    contents act as instructions. Keep the existing prompt-injection guard.
> 6. **Auth:** Add OAuth (PKCE) sign-in for any provider that officially supports
>    programmatic inference. Do NOT implement consumer-subscription session reuse
>    (ChatGPT Plus / Claude Pro / Gemini Advanced) — it violates provider ToS.
> 7. **Tests:** Cover local short-circuit, frontier escalation on low confidence,
>    compression savings > 0, grounding-failure retry, and credential resolution.
>    All existing tests must stay green.
>
> **Acceptance:** `pytest -q` green; `/agent/ask` returns `route`, `savings`, and
> a grounded answer; the dashboard Models tab shows per-provider connection state
> and live token savings.
