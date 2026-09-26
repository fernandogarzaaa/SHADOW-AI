# SHADOW-AI Provider Research

> Product spec: `docs/provider-architecture.md` (PRD-grounded provider
> architecture, capability contract, validation semantics, security model).

Date: 2026-09-27. Goal: wire every AI model provider into SHADOW-AI.
Sources: official provider documentation and official docs repositories where
available; third-party consumer implementations elsewhere. Claims that could not
be verified against a first-party source are marked UNVERIFIED.

## Architecture recommendation (from this research)

Most providers below speak the same wire protocol: OpenAI Chat Completions
(`POST {base}/chat/completions`, `Authorization: Bearer <key>`, SSE stream with
`choices[0].delta.content` chunks, `[DONE]` terminator). SHADOW-AI already has
an OpenAI-compatible streaming transport. The cheapest path to "all providers":

1. Keep one generic OpenAI-compatible adapter driven by per-provider config
   (base URL, auth header, model-list path). This covers OpenRouter, OpenCode
   Zen (chat-completions models), xAI, DeepSeek, Mistral, Groq, Together AI,
   Gemini (via Google's OpenAI-compat shim), and any user-supplied custom
   endpoint.
2. Keep native adapters only for Anthropic (already exists), Cohere v2 Chat,
   and optionally Gemini native (for Live/tools).
3. Replace the hardcoded model catalog with dynamic discovery: on key save,
   call the provider's models endpoint, cache the id list per key in SecureStore
   with a TTL (24h suggested), refresh on demand and on 404 model errors.
4. Use models.dev as metadata enrichment (context limits, pricing, capability
   flags) for display, not as the source of which models a key can call.
5. Make OpenRouter the default recommended aggregator: one key unlocks hundreds
   of models through a single adapter, and its models endpoint is public (no key
   needed to browse).

## 1. OpenRouter

Aggregator over hundreds of models. Official docs repository: openrouterteam/docs.

- Base URL: `https://openrouter.ai/api/v1`
- Auth: `Authorization: Bearer <OPENROUTER_API_KEY>`. Inference keys are
  standard keys; management keys administer other keys and cannot call
  completion endpoints.
- Chat: `POST /chat/completions`, OpenAI Chat Completions compatible. Model ids
  are namespaced, e.g. `openai/gpt-5.2`, `anthropic/claude-sonnet-4.5`,
  `google/gemini-2.5-flash`. Newer models may require a specific API version
  header; the models endpoint response documents what each entry needs.
- Streaming: SSE, OpenAI-style chunks (`choices[0].delta.content`), `[DONE]`
  terminator. The final usage chunk carries actual cost/tokens.
- Models: `GET /models`. No authentication required; it is the authoritative
  public catalog. Response shape:
  `{ "data": [ { "id", "name", "context_length", "pricing": {...} } ] }`
  (each variant is its own entry keyed by exact `id`). Companion endpoint
  `GET /models/{id}/endpoints` gives per-provider routing, latency, and uptime.
- Model discovery auth: not required.
- Key validation: `GET https://openrouter.ai/api/v1/key` with the Bearer key
  (documented in the official limits reference). Returns
  `data: { label, limit, limit_remaining, usage, usage_daily/weekly/monthly,
  is_free_tier, ... }`. Cheap, non-billable, and the recommended health check.
- Key issuance: openrouter.ai/keys; paid models need credits.

## 2. OpenCode Zen

Pay-as-you-go model gateway by the OpenCode team. Base and auth confirmed by
multiple consumer implementations; official page at opencode.ai/docs/zen/.

- Base URL: `https://opencode.ai/zen/v1`. Go subscription variant:
  `https://opencode.ai/zen/go/v1` (open-weight models, fixed-price
  subscription; same account key).
- Auth: `Authorization: Bearer <zen-key>`. Key issued at opencode.ai/auth;
  canonical env var `OPENCODE_API_KEY`.
- Chat: NOT a single OpenAI-compatible surface. Zen serves upstream-native
  dialects per model: `/chat/completions` for some models, `/responses` for
  others (e.g. the `muse-spark-*-free` models), `/messages` reported for some
  Anthropic-family models. A SHADOW adapter must route per model id based on
  the models-list metadata.
- Streaming: SSE on the chat-completions path; the responses path streams its
  own SSE event types.
- Models: `GET /zen/v1/models`. Appears to be public (consumer docs fetch it
  without a key); catalog spans GPT, Claude, Gemini, and open-weight families,
  including rotating zero-cost models.
- Model discovery auth: none required (UNVERIFIED against official docs).
- Key validation: no dedicated key-check endpoint is documented. Validate with
  the public models list plus a minimal chat call, or a cheap call on a
  zero-cost model. UNVERIFIED for an official key endpoint.
- Free tier caution: zero-cost models exist, but on 2026-09-25 a valid Zen key
  with a listed model returned `403 FreeTierError`, an intentional
  client-identity gate. Do not promise free Zen models work from SHADOW-AI until
  official client-access rules are confirmed.

## 3. models.dev and OpenCode models data

- `https://models.dev/api.json` is a public, no-auth JSON catalog of model
  metadata, generated from per-provider TOML files. Top level is keyed by
  provider id; each provider entry carries `id`, `name`, `api`, `doc`, `env`,
  `npm`, and a `models` map keyed by model id with capability flags, modality,
  context/output limits, and cost data. SHADOW-AI already fetches this for
  context limits.
- Update cadence is UNVERIFIED; one consumer caches it for five minutes, another
  republishes daily. Neither establishes the publication schedule.
- Canonical repository/maintainer identity is UNVERIFIED (candidate repos
  appeared under differing org names or mirrors).
- Role in SHADOW-AI: enrichment only (context windows, pricing display,
  capability badges). It must not decide which models a user's key can call;
  the provider's own models endpoint does that.

## 4. xAI Grok

Official documentation: docs.x.ai REST API reference documents OpenAI REST
compatibility.

- Base URL: `https://api.x.ai`
- Auth: `Authorization: Bearer <xAI API key>`
- Chat: `POST /v1/chat/completions`, OpenAI-compatible request/response.
- Streaming: SSE, OpenAI-style (exact chunk/usage field details UNVERIFIED
  against official docs).
- Models: `GET /v1/models` (documented in the official REST reference).
- Model discovery auth: required (key needed).
- Key validation: `GET /v1/api-key` returns key information (documented in the
  official REST reference); use it as the health check.
- Model ids rotate frequently. Third-party mirrors of the official models page
  (docs.x.ai) list current families such as `grok-4.6`/`grok-4.7` flagship
  (~500k context), `grok-4.5`, `grok-4.3` (1M), `grok-4.20-0309-reasoning`,
  `grok-4.20-0309-non-reasoning`, `grok-4.20-multi-agent-0309`,
  `grok-build-0.1` (coding), `grok-composer-2.5-fast`. A 2026-05 retirement wave
  removed `grok-2*`, `grok-3*`, and fast variants. Exact current lineup is
  UNVERIFIED and changes monthly: always discover from `GET /v1/models`.

## 5. Google Gemini

Google ships an official OpenAI-compatibility layer on the Gemini API,
confirmed by multiple independent consumer implementations. This is the
recommended integration path for SHADOW-AI because it reuses the existing
OpenAI-compatible transport with zero new parsing code.

- OpenAI-compat base: `https://generativelanguage.googleapis.com/v1beta/openai`
- Chat: `POST /v1beta/openai/chat/completions` with
  `Authorization: Bearer <API key>`. OpenAI-style request, response, and SSE
  streaming. It is a text compatibility layer; it is not the Gemini Live
  WebSocket API.
- Native API (optional, for tools/Live later):
  `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`
  and `:streamGenerateContent`, auth via `x-goog-api-key` header or `?key=`
  query param. Native request shape uses `contents[].parts[]`; responses use
  `candidates[].content.parts[]`; streaming appends `?alt=sse`.
- Models: `GET https://generativelanguage.googleapis.com/v1beta/models`
  (paginated; filter entries by supported generation methods, keep only models
  supporting `generateContent`).
- Model discovery auth: key required.
- Key validation: call the models list; an invalid key returns an auth error.
  No dedicated key endpoint. Keys are issued at Google AI Studio
  (aistudio.google.com/apikey).
- The OpenAI-compat details above are secondary-sourced (multiple consistent
  consumer implementations); official Google documentation extraction is still
  pending, so treat exact parameter parity as UNVERIFIED.

## 6. DeepSeek

- Base URL: `https://api.deepseek.com/v1`
- Auth: `Authorization: Bearer <key>`
- Chat: `POST /chat/completions`, OpenAI-compatible.
- Streaming: SSE, OpenAI-style chunks.
- Models: `GET /models` (key required). Known families: `deepseek-chat`,
  `deepseek-reasoner`.
- Key validation: models list call.
- Status: documented as OpenAI-compatible by third-party consumers; verify
  against official api-docs.deepseek.com before hardcoding any model ids.

## 7. Mistral (La Plateforme)

- Base URL: `https://api.mistral.ai/v1`
- Auth: `Authorization: Bearer <key>`
- Chat: `POST /chat/completions`, OpenAI-compatible.
- Streaming: SSE, OpenAI-style chunks.
- Models: `GET /v1/models` (key required). Entries carry
  `capabilities.completion_chat`; filter to chat-capable models and exclude
  embed/moderation models.
- Key validation: models list call.

## 8. Groq

- Base URL: `https://api.groq.com/openai/v1`
- Auth: `Authorization: Bearer <key>`
- Chat: `POST /chat/completions`, OpenAI-compatible.
- Streaming: SSE, OpenAI-style chunks.
- Models: `GET /openai/v1/models` (key required); exclude audio/guard models.
- Key validation: models list call.

## 9. Together AI

- Base URL: `https://api.together.xyz/v1` (canonical per current docs; the
  older `api.together.ai` hostname also appears in legacy references).
- Auth: `Authorization: Bearer <key>`
- Chat: `POST /chat/completions`, OpenAI-compatible.
- Streaming: SSE, OpenAI-style chunks.
- Models: `GET /models` (key required).
- Key validation: models list call. One consumer reported the `.xyz` API being
  intermittently unreachable; handle discovery failures gracefully.

## 10. Cohere

Cohere is NOT OpenAI wire-compatible and needs a native adapter.

- Base URL: `https://api.cohere.com`
- Auth: `Authorization: Bearer <key>`
- Chat: `POST /v2/chat`. Request: `{ model, messages: [{ role, content }] }`.
  Response uses typed content blocks, e.g. `message.content[]` with
  `{ type: "text", text: "..." }`, not `choices[]`.
- Streaming: SSE with typed events (`content-delta` with text deltas,
  `message-end` markers). Exact event-type names should be verified against
  current official Cohere docs before implementing.
- Models: `GET /v1/models` per multi-provider gateway documentation. One
  consumer claims `/v2/models`; that path is UNVERIFIED. Prefer `/v1/models`.
- Key validation: models list call.

## 11. Meta Muse API

Status: UNVERIFIED whether any public Muse model-inference API exists.

- September 2026 reports claim Meta opened Muse Connectors to third-party
  developers, and that Muse supports custom API or MCP connectors. A connector
  ecosystem is not the same as a public model-inference API: connectors let
  Muse reach external data, they do not let external apps call Muse Spark.
- No official Meta or Muse developer documentation for a public inference
  endpoint was found in this research.
- Do not build a Muse provider, and do not claim Muse is unavailable or
  publicly available, until first-party documentation is located.

## 12. BYOK personal-AI mobile app landscape

Observed patterns from shipping apps (all secondary-sourced):

- Keys live in OS secure storage (iOS Keychain / Android Keystore; in Expo this
  is SecureStore, which SHADOW-AI already uses). Keys are never logged, never
  leave the device except to the chosen provider.
- The universal escape hatch is a generic "OpenAI-Compatible" custom provider:
  user enters base URL + key + model id, and the app routes through its
  OpenAI-compatible transport. This single pattern covers OpenRouter, Zen,
  xAI, DeepSeek, Mistral, Groq, Together, Gemini-compat, vLLM, LM Studio, and
  Ollama without per-provider code.
- Model pickers are populated by dynamic discovery (`GET {base}/models` with
  the user's key), cached locally with a TTL and a manual refresh, with curated
  presets per provider for first-run. Hardcoded-only catalogs rot within weeks.
- Some apps pair cloud BYOK with on-device inference (llama.cpp) for offline
  use; keys still stored per-provider in secure storage.

Recommendation for SHADOW-AI: ship the generic custom-endpoint provider first
(it immediately covers every OpenAI-compatible service above), then promote the
most-used providers to curated presets with dynamic model discovery.

## 13. Multi-provider TypeScript libraries

- Vercel AI SDK (`vercel/ai`): ~25K GitHub stars (26.7K per one 2026 directory,
  24.6K+ per another). The de facto TypeScript standard: unified provider
  interface across 20+ providers, first-class streaming, React hooks, and
  `@ai-sdk/openai-compatible` for arbitrary base URLs. 500K+ weekly downloads.
  Caveat: React hooks target web; the provider/streaming core is fetch-based
  and portable, but React Native integration needs evaluation.
- `igorls/universal-llm-client`: TypeScript multi-provider client with
  failover support. Star count UNVERIFIED (could not confirm against GitHub).
- `sschepis/llm-wrapper`: TypeScript wrapper across 9 providers. Star count
  UNVERIFIED (could not confirm against GitHub).
- `multi-llm-ts`: TypeScript, ~500 stars (2025), simple unified interface;
  small and readable reference implementation.
- LiteLLM (`BerriAI/litellm`, Python, 22.7K stars): not an Expo dependency,
  but the reference for adapter semantics — 100+ providers normalized to
  OpenAI-compatible I/O plus a proxy server. Useful as a design reference and,
  optionally, as a self-hosted proxy SHADOW-AI could point its generic adapter
  at.

Recommendation: do not add a heavy SDK dependency to the Expo app yet. The
generic OpenAI-compatible adapter plus two native dialects (Anthropic,
Cohere) covers the researched providers with less bundle weight and fewer
native-module risks. Revisit Vercel AI SDK if SHADOW-AI needs structured
output, tool calling, or agent loop primitives later.
