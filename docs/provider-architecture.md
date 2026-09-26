# SHADOW-AI Provider Architecture

This is the product specification for the model provider layer: how
SHADOW-AI connects to AI providers under the user's own keys, and how it
presents models, costs, and capabilities honestly. It follows the PRD's
core principles: the app is the consent command center, keys never leave
the device except to the provider the user chose, autonomy is revocable,
and every consequential behavior is auditable.

## 1. PRD alignment

The PRD defines SHADOW-AI as a local-first personal AI operating layer:
explicit consent, revocable autonomy, encrypted local memory, safe action
boundaries, and an audit trail. The provider layer applies those
principles to model access:

- **Consent command center.** The user chooses every provider and every
  model. Nothing phones home, nothing pre-fetches with a key the user has
  not saved, and no provider is contacted until the user picks it.
- **Keys stay local.** API keys live in `expo-secure-store` on the device.
  The only network destination a key ever reaches is the provider's own
  API (or a user-supplied custom endpoint). There is no proxy, no
  telemetry, no key escrow.
- **Honest validation.** Key checks are explicit (the user taps save or
  refresh), minimal (one cheap call), and honest about what they prove.
  A check that cannot confirm a key says so instead of guessing.
- **Revocable.** Keys can be removed at any time from Settings; removal
  is immediate and local.
- **Auditable.** Provider errors are typed (`invalid_key`, `rate_limited`,
  `tier_access`, `server`, `network`) and surfaced to the user in plain
  language, not swallowed.

## 2. Provider inventory and dialect taxonomy

The registry (`ProviderId`) currently holds 13 entries: anthropic,
openai, openrouter, opencode, xai, gemini, deepseek, mistral, groq,
together, cohere, custom, and node. Keyed providers appear automatically
in onboarding and Settings via `KEY_PROVIDERS`.

Providers fall into three dialect families:

| Family | Members | Transport |
|---|---|---|
| OpenAI-compatible factory | openai, xai, gemini (chat base), deepseek, mistral, groq, together, custom | `openaiCompatible.ts`: bearer auth, `GET /models`, `POST /chat/completions` streaming SSE |
| Native dialects | anthropic, cohere | Provider-native request/response shapes (Anthropic messages API; Cohere `/v2/chat` SSE) |
| Multi-dialect gateway | opencode (Zen) | OpenAI-compatible body on `/chat/completions` for supported models; fails loudly for the rest |

The shared factory is the default for any provider that speaks the
OpenAI wire shape. Native adapters exist only where the wire shape
differs. The generic custom endpoint is the universal compatibility path
for Ollama, LM Studio, vLLM, LiteLLM, and other OpenAI-compatible
gateways.

No Meta Muse inference provider exists. As of September 2026 there is no
public Muse model-inference API to build against; Muse connectors are
integrations that let Muse reach external systems, not an API SHADOW-AI
can call. Adding Muse requires first-party API documentation.

## 3. Model discovery contract

`ModelProvider.listModels(apiKey)` returns the live catalog. The
`modelCatalog` module wraps it:

- **Cache:** 24-hour in-memory cache per provider; the model sheet opens
  instantly on repeat visits.
- **Dedup:** concurrent requests for the same provider share one fetch.
- **Fallback:** any discovery failure falls back to the provider's static
  `models` list, so the UI never breaks offline.
- **Stale eviction:** a failed refresh drops the expired entry so a stale
  list is never served as fresh.
- **Source tagging:** every `ModelInfo` carries `capabilities.source`:
  `"live"` for catalog entries, `"static"` for fallbacks. The UI can say
  the list may be stale.

Some catalogs are public (OpenRouter, Zen) and need no key; the key is
accepted for API-shape symmetry. Others (xAI, DeepSeek, and most
factory providers) require the key for `GET /models`, which makes
catalog access double as a health signal.

## 4. Capability metadata contract

`ModelInfo.capabilities` (see `types.ts`) describes what is known about a
model entry:

- `protocol`: `"chat-completions"`, `"responses"`, `"messages"`, or
  `"native"`. Set only when known.
- `contextWindow`, `maxOutputTokens`: tokens, when the catalog reports
  them.
- `vision`, `tools`: when the catalog reports the modality or tool
  support.
- `streaming`: when the adapter can stream the model.
- `source`: `"live"` or `"static"`.

The central rule: **unknown stays unknown.** An unset field is rendered
as unknown, never guessed. OpenRouter is the richest source today
(`context_length`, `architecture.input_modalities`); the Zen catalog
does not report dialects, so Zen entries leave `protocol` unset and the
adapter fails loudly on non-chat models instead of guessing.

Planned (not built): capability and modality filters in the model sheet,
context-window presentation, authoritative pricing display. Pricing is
never shown from memory or third-party aggregators; it requires an
authoritative provider source.

## 5. Key validation semantics

Each provider defines what "valid key" means in `validateKey`, and the
rules are strict:

- Validation runs only on explicit user action (save key, refresh).
- It makes the cheapest possible call and discloses the cost (Zen's
  probe costs ~1 token; OpenRouter's `GET /key` costs nothing).
- Only statuses that positively prove acceptance count as valid:
  - 2xx: the call worked.
  - 429: rate-limited still proves the key was accepted.
  - Zen 403 `FreeTierError`: tier-gated, but the key itself is valid.
- 401 means a bad key. 403 otherwise means rejected.
- Anything else (400, 404, 5xx) means the provider **could not verify**
  the key. The UI reports that instead of misreading it as valid.

Zen-specific policy: the probe targets a chat-completions-safe model
(`CHAT_SAFE_MODELS`), preferring a safe id that also appears on the live
roster. It never probes with the first catalog entry, which may require
a non-chat dialect and would make a good key look broken.

## 6. Security model

- Keys are stored in `expo-secure-store`, never in app state, logs, or
  memory files.
- The provider layer never logs keys, prompts, or responses. `FetchLike`
  bodies are not persisted.
- A key is sent only to its provider's configured base URL. Custom
  endpoints send the key only to the user-supplied base URL after
  normalization; the UI shows the URL being used.
- No analytics, no telemetry, no request proxying. Model traffic is
  direct between the device and the provider.
- Key removal from Settings is immediate and local; cached catalogs are
  unaffected (they contain no keys).

## 7. Zen multi-dialect limitation

OpenCode Zen serves some models on `/responses` or `/messages` rather
than `/chat/completions`. The adapter speaks `/chat/completions` only.
Selecting a non-chat model fails loudly with a clear message naming the
limitation. Work to attach per-model protocol metadata from Zen (or a
curated override list) is open; until then, the limitation is surfaced,
not hidden.

## 8. UX contract: model selection

Current (built): dynamic catalog loading in `ModelSheet`, manual model-id
input for custom endpoints, provider help entries and base-URL input in
`KeySheet`.

Planned (not built): search, virtualized rendering for large catalogs
(OpenRouter lists hundreds of models), manual refresh, persistent mobile
catalog cache, loading/cached/stale/fallback indicators, capability and
modality filters, context-window and output-limit presentation,
authoritative pricing, protocol display.

The sheet must never present a static fallback as a live catalog, and
must never present guessed capabilities as facts.

## 9. Competitive landscape

BYOK chat clients SHADOW-AI is measured against:

- **TypingMind:** polished BYOK chat with model breadth; no local-first
  memory or agent runtime.
- **LibreChat / Open WebUI:** self-hosted, provider-agnostic; server
  software, not a mobile personal agent.
- **Chatbox, Jan, Msty:** desktop-first BYOK clients; limited mobile
  story, no consent/agent architecture.
- **Poe:** model aggregator without BYOK; the user rents access, and
  data flows through Poe.
- **ChatGPT / Claude mobile apps:** first-party, no provider choice,
  account-bound.

SHADOW-AI's differentiation, per the PRD, is not model breadth (that is
table stakes) but the personal-agent layer: local-first encrypted
memory, the consent command center, GHOST ambient execution, AXIOM
context compression, the Sentinel-lite policy engine, and the optional
SHADOW node. Provider breadth exists so the agent layer is never locked
to one vendor.

## 10. Non-goals

- No provider is added or advertised without verification against
  official documentation. `docs/provider-research.md` marks unverified
  claims explicitly; they stay out of user-facing copy.
- No pricing, context limits, or capability claims are presented unless
  they come from an authoritative source or the live catalog.
- No automatic provider failover or smart routing until the product
  decision is made with Inan (failover has billing and privacy
  implications: traffic would move between vendors without per-call
  consent).
- No key escrow, no server-side proxy, no "we hold keys for you" tier.
- No spyware-class behavior: the provider layer never reads, uploads, or
  monitors anything the user did not explicitly send.

## 11. Verification requirements

Before release, every provider entry needs: official-docs confirmation
of base URLs, auth scheme, model-discovery shape, and key-health
semantics; a live smoke test of streaming against the real endpoint
(where a key is available); and a review of the help URLs in `KeySheet`.
The 12 claims flagged UNVERIFIED in `docs/provider-research.md` are the
starting checklist. Subagent research reports are leads, not evidence.

## 12. Provider-layer roadmap

1. Per-model protocol metadata for Zen (curated override or discovery).
2. Model-sheet UX: search, refresh, indicators, filters, virtualization.
3. Authoritative pricing and context presentation from live catalogs.
4. Persistent catalog cache on device (survives app restart).
5. Routing/failover policy decision with Inan (per-call consent model).
6. Tool calling and structured output (revisit Vercel AI SDK or hand-rolled).
7. Node-routed inference as an opt-in provider (`node` entry) with the
  existing HMAC pairing intact.
