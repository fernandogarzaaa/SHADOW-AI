# Personal Agent Landscape Research, September 2026

Purpose: find concrete features and integrations SHADOW-AI (local-first BYOK
personal AI, Expo/React Native iOS/Android, 13 providers, SecureStore keys,
Sentinel-lite policy engine, credential vault, audit log, GHOST ambient agent,
SearXNG web search, optional SHADOW node) could add next.

Method: five parallel research tracks (Meta Muse docs, xAI Grok docs, agent
app landscape, mobile platform capabilities, GitHub open source), each using
web search plus page fetches, primary sources preferred. Rule used throughout:
**VERIFIED** means confirmed against a primary source in this pass;
**UNVERIFIED** means secondary, conflicting, or unconfirmed. Guessed URLs,
prices, and endpoints are never presented as fact.

## Track 1: Meta Muse AI developer surface

**VERIFIED: Meta Model API exists and is OpenAI-compatible.**
Meta operates a developer inference API documented at
https://dev.meta.ai/docs/getting-started/overview (fetched Sep 27, 2026).
Base URL `https://api.meta.ai/v1`, auth `Bearer` with a `MODEL_API_KEY` from
the dev.meta.ai dashboard. Documented model `muse-spark-1.1`, 1,048,576 token
context. Three request formats: Responses API (`POST /v1/responses`), Chat
Completions, and Anthropic-compatible Messages. Documented features: tool
calling, parallel tool calls, streamed tool-call arguments, reasoning effort
controls, structured output, prompt caching, Files API, search grounding,
image/video/audio understanding. Meta AI Research
(https://research.meta.ai/blog/introducing-muse-spark-1-3) confirms Muse Spark
1.3 is available in Muse Code and the Meta Model API. Muse is the consumer
personal agent (iOS, Android, muse.ai, WhatsApp); Muse Spark is the
developer-facing model family. They are distinct products.

**VERIFIED: no API to drive the Muse assistant itself.** The official surface
offers the raw model (Meta Model API), not remote control of a user's Muse
agent. The connector program only lets developers expose services INTO Muse
(via a muse.ai/platform submission form accepting hosted MCP endpoints or raw
APIs). No published protocol spec or SDK for connectors was found.

**WhatsApp Cloud API (VERIFIED via consistent recent guides, secondary):**
REST `https://graph.facebook.com/v{version}/{phone_number_id}/messages`,
webhook on the `messages` field, free test number with up to 5 verified
recipients. Constraints: business verification for public messaging,
template-approved proactive messages outside the 24h window, bot number cannot
also run the consumer app, roughly 20 msg/sec ceiling. Viable as a bot
channel only, not a personal-channel integration.

**Llama Stack (VERIFIED via secondary sources):** open-source agent framework,
FastAPI server with standardized REST APIs for inference, agents, RAG,
safety, eval; pluggable providers including Ollama, vLLM, OpenAI, Anthropic,
Together, Groq. Self-hosted plumbing, not a Meta-hosted service.

**UNVERIFIED:** reported Muse Spark pricing ($1.25/$4.25 per 1M in/out, $20
free credit, US-only at launch) comes from press, not Meta's pricing page.
The Llama API (llama.developer.meta.com, preview) vs Meta Model API
relationship is not established in any source found. Third-party Llama API
price lists are UNVERIFIED.

## Track 2: xAI Grok API

**VERIFIED from docs.x.ai (models page updated Sep 21, 2026; release notes;
pricing page; REST reference):**
- Flagship `grok-4.7`: 500k context, text+image input, text-only output,
  $2.00 input / $6.00 output per 1M tokens ($4/$12 long-context band at or
  above 200k prompt tokens), cached input $0.50, reasoning effort
  low/medium/high (default)/xhigh, knowledge cutoff May 2026.
- Also current: `grok-4.6` (500k, same pricing), `grok-4.5` (500k),
  `grok-4.3` (1M context, $1.25/$2.50, the cheap tier), `grok-build-0.1`
  (256k coding model, $1/$2), voice and Imagine (image/video) APIs.
- Server-side tools on chat completions: Web Search, X Search, Code
  Interpreter, Image Generation, Collections Search; plus client-side function
  calling. Tool invocations billed separately from tokens.
- Responses API: `max_turns`, `previous_response_id`, 30-day stored responses,
  WebSocket transport, Context Compaction API, remote MCP tools, structured
  outputs, `service_tier: "priority"` (2x), exact per-request
  `usage.cost_in_usd_ticks`.
- May 15, 2026 retirement: `grok-3`, `grok-4-0709`, `grok-4-fast-*`,
  `grok-4-1-fast-*`, `grok-code-fast-1`, `grok-imagine-image-pro` retired;
  old slugs silently redirect to `grok-4.3` and bill at grok-4.3 rates.
- Base URL `https://api.x.ai`, `Authorization: Bearer <xAI key>`,
  `POST /v1/chat/completions`, `GET /v1/models`; "compatible with the OpenAI
  REST API" per official reference. Management endpoints live at
  `https://management-api.x.ai` with a separate key.
- `logprobs`/`top_logprobs` silently ignored on grok-4.20 and newer.

**UNVERIFIED / partially:** legacy `search_parameters` (Live Search) on chat
completions is reported deprecated/410 by multiple integrations but not
confirmed on docs.x.ai. Live-search per-source billing ($0.025) is
third-party only. `grok-4.7-fast` is Cursor/Grok Build only, not public API.
No first-party Telegram/Discord bot; `@grok` on X has no developer API.
Grok Bot (Aug 2026, durable cloud teammates) is a closed hosted product with
no public management API documented.

**BYOK checklist for the existing Grok provider:** add `grok-4.7` as default,
keep 4.6/4.5/4.3/build-0.1, warn on retired slugs (silent redirect billing
surprise), expose `reasoning_effort`, confirm vision input, strip logprobs,
read `cost_in_usd_ticks`, migrate search to server-side tools, show the
200k-token two-tier pricing, do not offer `grok-4.7-fast`.

## Track 3: Personal AI agent app landscape

Covered 20 products (all 12 requested plus OpenClaw, Screenpipe, MailOver,
SaneBox, Cora, Plaud discovered). Killer features per product:

- **Lindy:** Slack-native teammate (DM, iMessage, Chrome ext, joins
  Meet/Zoom/Teams), 40+ skills, artifact production (decks, sheets, reports),
  editable plain-text memory files, approval-gated consequential steps.
- **Granola:** bot-free meeting capture via system audio, Enhance Notes merges
  jottings with transcript, Recipes (shareable prompt templates), Pre-meeting
  Briefs from calendar, Apple Watch haptics.
- **Motion:** auto-scheduling engine with deadline risk alerts (cautionary:
  reshuffles without asking, the anti-pattern to avoid).
- **Reclaim.ai:** time-defense auto-blocking, smart meeting links, buffer and
  travel time, Slack status sync. Free tier, paid from $8/mo (vendor blog).
- **Shortwave:** AI-organized inbox (todos, bundles), voice-matched drafting
  from sent mail, natural-language mail search.
- **Superhuman:** Ask AI across inbox/calendar/web, auto thread summaries,
  auto drafts in personal voice, auto follow-up reminders.
- **OMI / Bee / Friend:** ambient wearables. Bee ($49.99, week-long battery,
  AI daily journal, calendar/email actions) is the mainstream reference; OMI
  is the open-source pendant; Friend is the cautionary tale (unsolicited
  commentary without utility).
- **Screenpipe (OSS):** local-first screen/audio capture into searchable
  SQLite + REST/MCP, PII redaction, "Pipes" as markdown-scheduled ambient
  agents. Closest thing to GHOST ambient plus scheduler.
- **OpenClaw (OSS, MIT):** messaging-native assistant (WhatsApp, Telegram,
  Signal, iMessage) with real execution, BYO key, markdown memory files,
  heartbeat daemon for proactive briefings.
- **MailOver / Cora / Fyxer / SaneBox:** email secretary patterns. MailOver's
  daily briefing with 3-bucket categorization and teach-lessons loop; Cora's
  twice-daily Brief; SaneBox's metadata-only triage and SaneNoReplies.
- **ChatGPT (2026):** Scheduled Tasks hub with visible ledger (view/pause/
  edit/delete), web-monitoring tasks that notify only on meaningful change,
  ChatGPT Work autonomous execution, Cloud Browser with credential isolation
  and Always Ask / Auto Approve / Always Allow permission levels, unattended
  tasks auto-pause, human-in-the-loop for financial/legal actions. The
  strongest documented approval model in the survey.
- **Claude (2026):** Skills (reusable instruction/script bundles), 200+
  connectors, persistent editable memory, Agent memory "Dreaming"
  consolidation, scheduled tasks with admin audit view.
- **Copilot (Sep 2026):** Autopilot persistent cloud agent with own identity
  and email, usage-based billing, consumer features retired (enterprise
  pivot).

**Limitless/Pendant is defunct** (Meta acquired 2025, hardware halted):
lesson is that cloud recording raised GDPR issues; local-first is the
opposite bet.

## Track 4: Mobile platform capabilities (iOS 26 / Android 16 era)

**VERIFIED:**
- **App Intents is the only Siri path.** Apple deprecated SiriKit at WWDC
  2026 (2-3 year support window); the rebuilt Siri surfaces third-party apps
  only through App Intents, with personal context understanding and
  onscreen awareness. Reported powered by Gemini with confidential-computing
  cloud escalation (secondary).
- **iOS 26 WidgetPushHandler:** real-time widget refresh via push, replacing
  the old timeline cadence. Live Activities: ~12h total, 4KB push payload,
  can only start from in-app user action.
- **Background budgets:** iOS `BGAppRefreshTask` ~30s, `BGProcessingTask`
  minutes (usually needs charging/idle), silent push ~30s, one-shot requests,
  overruns get shadow-banned. iOS 26 adds `BGContinuedProcessingTask`.
  Android: WorkManager 15-min minimum, foreground service types mandatory
  since API 34, Android 16 tightens standby buckets.
- **Apple Foundation Models framework:** free on-device ~3B model, Swift API
  with tool calling and guided generation, no key, no network. Gate: A17
  Pro+ / M1+, Apple Intelligence enabled, 4,096 token context, one in-flight
  request, short bounded tasks only.
- **Gemini Nano via AICore:** third-party access on Pixel 9/10, Galaxy S25,
  and recent flagships from Honor, Xiaomi, OPPO, vivo, Motorola, OnePlus,
  iQOO, POCO, realme. ML Kit GenAI APIs (summarize, rewrite, describe, beta
  prompt API). Inference only while app is foreground; background inference
  not architecturally supported.
- **Expo reality:** `expo-background-task` (15-min, BGTaskScheduler/
  WorkManager), push-triggered data-only wake (~30s), Expo Go cannot do
  background execution, widgets, share extensions, or custom native modules
  (needs prebuild/dev client). **Packaged on-device LLM for Expo exists:**
  `expo-local-llm` (Foundation Models + Gemini Nano, tool calling,
  constrained JSON, near-zero bundle size) and React Native AI wrappers;
  `llama.rn` (GGUF) and `whisper.rn` proven in shipped Expo apps.
- **Voice:** iOS 26 on-device SpeechAnalyzer/Transcriber stack; Android
  offline SpeechRecognizer; `expo-speech` wraps system TTS.
- **Rich notifications:** up to 4 action buttons on iOS; Android 16 "Live
  Updates" mirrors Live Activities; Glance widgets support callbacks without
  launching the app.

**Architectural truth across sources:** neither OS allows a true always-on
background agent. Design around foreground sessions, push-triggered 30s
windows, and 15-minute opportunistic sync; heavy work belongs on a server
or the paired node.

**UNVERIFIED:** WWDC26 Foundation Models updates (Claude/Gemini session
routing, image input, Private Cloud Compute access) could not be confirmed
against developer.apple.com. "Gemini Intelligence" device tier is
single-source. No mature Expo package for App Intents/WidgetKit found;
expect custom native modules.

## Track 5: GitHub open source

Star counts below are as shown on the fetched GitHub pages; treat as
approximate. Licenses marked where the page showed them.

- **mybigday/llama.rn** (1,041 stars, MIT): React Native llama.cpp binding,
  Expo config, Metal acceleration, tool calling, embeddings, TTS. Strongest
  direct on-device runtime candidate.
- **a-ghorbani/pocketpal-ai** (8,420 stars, MIT): React Native GGUF app,
  model downloads, hardware fallback, local tool loop, personas,
  WatermelonDB, Keychain storage. Reference architecture for a mobile agent
  loop.
- **hurrtz/mrbroccoli** (1 star, license UNVERIFIED): Expo SDK 57 voice-first
  BYOK app, eight providers, SecureStore keys, rolling compaction, on-device
  retrieval, route receipts. Architecturally closest to SHADOW-AI.
- **modelcontextprotocol/typescript-sdk** (13,464 stars, Apache-2.0/MIT):
  official SDK, Streamable HTTP + stdio, OAuth helpers. React Native bundler
  compatibility UNVERIFIED, must be tested.
- **mcp-use/mcp-use** (10,681 stars, MIT): TS MCP framework with React
  bindings. RN compatibility UNVERIFIED.
- **ggui-ai/ggui** (42 stars, Apache-2.0): MCP-UI protocol with a React
  Native host package. Only RN MCP-UI host found.
- **mem0ai/mem0** (66,023 stars, Apache-2.0): persistent memory layer,
  hybrid retrieval, temporal reasoning. Node-side or API use, not RN-embed.
- **getzep/graphiti** (31,176 stars, Apache-2.0): temporal context graph
  with provenance and contradiction handling. Backend service fit.
- **NevaMind-AI/memU** (14,429 stars, Apache-2.0 per README): portable
  user-owned memory as readable Markdown/wiki, cross-agent adapters,
  automatic skill extraction. Closest to Genesis/PCR values.
- **letta-ai/letta** (24,896 stars, Apache-2.0): self-editing memory blocks,
  TypeScript agent SDK.
- **openclaw/openclaw** (page-shown 390,570 stars; README says MIT, metadata
  NOASSERTION): local gateway, native mobile apps, channel integrations,
  device pairing. Architecture reference.
- **NousResearch/hermes-agent** (page-shown 249,188 stars, MIT): BYOK
  provider router (20+ providers), native MCP client, three-layer memory,
  cron scheduler. Pattern borrowing, Python-first.
- **binaydhakal/react-native-local-llm** (1 star, MIT, 3 commits): unified RN
  interface over Foundation Models / ExecuTorch / llama.cpp. Evaluate code
  quality before adoption.
- **Awesome lists:** punkpeye/awesome-mcp-servers (95,547 stars, MIT),
  mnemoverse/awesome-agent-memory (CC0-1.0, includes benchmarks),
  ARUNAGIRINATHAN-K/awesome-ai-agents-2026 (CC0-1.0).

## Consolidated UNVERIFIED register

Do not treat these as facts: Muse Spark pricing ($1.25/$4.25, $20 credit);
Llama API vs Meta Model API relationship and any Llama API pricing; Grok
legacy `search_parameters` deprecation and per-source search billing;
Grok Bot plan expansion and X integration depth; Lindy/Shortwave/Superhuman/
Granola/Bee/Friend exact pricing; ChatGPT agent quota numbers; Copilot
pricing; WWDC26 Foundation Models updates; "Gemini Intelligence" tier;
Android App Actions 2026 expansion; star counts as precise figures; license
metadata marked NOASSERTION; React Native compatibility of MCP TS SDKs;
Screenpipe license dispute.

## What SHADOW-AI could add

Prioritized by leverage. PRD fit notes how each maps to consent,
local-first, or auditability. Effort: S/M/L. Items marked [DECISION] need
Inan's product call before implementation.

1. **Meta Model API provider (Muse Spark).** Add `meta` to the provider
   registry via the existing OpenAI-compatible factory pointed at
   `https://api.meta.ai/v1` with a Bearer key from dev.meta.ai. Track 1.
   PRD fit: user-chosen provider, key in SecureStore, traffic direct to
   Meta. Effort: S. Confirm pricing on Meta's pricing page before any cost
   display.
2. **Grok provider refresh.** Set `grok-4.7` default, add 4.6/4.5/4.3/
   build-0.1 to the static registry, warn on retired slugs that silently
   redirect (billing surprise), expose `reasoning_effort`, strip logprobs,
   surface `cost_in_usd_ticks`, migrate search to server-side tools, show
   the 200k-token two-tier pricing. Track 2. PRD fit: honest cost and
   capability presentation. Effort: S/M. No product decision needed.
3. **Rich push notifications with approval actions.** Approve/deny buttons
   on approval-queue pushes with deep links, via `expo-notifications`
   (up to 4 actions on iOS, Android actions likewise). Track 4. PRD fit:
   consent command center, approvals inbox stays first in tab order even
   when the app is closed. Effort: S/M. No product decision needed.
4. **Editable plain-text memory files.** Export and inspect the memory
   store as human-readable Markdown (Lindy/OpenClaw/memU pattern),
   editable and re-importable. Track 3/5. PRD fit: transparent memory
   review, auditability. Effort: S. No product decision needed.
5. **On-device LLM triage via expo-local-llm.** Use Apple Foundation
   Models / Gemini Nano for zero-cost offline tasks: inbox triage drafts,
   memory consolidation, quick summaries, with availability gating and
   cloud fallback to the user's chosen provider. Track 4. PRD fit:
   local-first, keys never leave for small tasks. Effort: M. [DECISION]:
   offline tier positioning and which tasks qualify.
6. **Opt-in twice-daily briefing.** Digest of calendar, new email, and
   memory highlights with action items, generated on-device or via the
   node, delivered by push. Track 3 (MailOver/Cora/Bee pattern). PRD fit:
   proactive value with explicit opt-in; scheduler stays OFF by default.
   Effort: M. [DECISION]: proactive output policy and quiet hours.
7. **Per-tool approval tiers in Sentinel-lite.** Always Ask / Auto Approve
   / Always Allow per tool class, mirroring ChatGPT's Cloud Browser model,
   so routine reads run silent and writes pause. Track 3. PRD fit:
   granular consent, revocable autonomy. Effort: M. [DECISION]: safety
   model change, default tier for each class.
8. **Voice loop.** On-device speech-to-text (iOS 26 SpeechAnalyzer or
   WhisperKit/whisper.rn; Android offline recognizer) plus `expo-speech`
   TTS for replies, as a hands-free chat mode. Track 4. PRD fit:
   local-first input/output. Effort: M. No product decision needed.
9. **Share target / share extension.** Android ACTION_SEND target and iOS
   share extension ("send to agent") to capture text/links into the inbox
   from any app. Track 4. PRD fit: user-initiated capture, explicit
   consent per item. Effort: S/M. Needs prebuild; no product decision.
10. **Siri and Shortcuts via App Intents.** Expose agent actions (new
    chat, run briefing, capture note) as App Intents through a small
    native module, since SiriKit is deprecated and this is the only Siri
    path. Track 4. PRD fit: user-invoked, consent-preserving. Effort: M.
    No product decision needed.
11. **Web-change watchers.** "Notify me only when X changes" scheduled
    watchers on pages or topics with a meaningful-change threshold to
    avoid spam, building on the existing SearXNG search and GHOST
    scheduler. Track 3 (ChatGPT scheduled tasks pattern). PRD fit:
    opt-in ambient work, auditable runs. Effort: M. [DECISION]: scheduler
    policy and cadence limits.
12. **GGUF on-device inference via llama.rn.** Full local model downloads
    (pocketpal-ai pattern: capability checks, hardware fallback, download
    management) for a true offline mode. Track 5. PRD fit: strongest
    local-first story. Effort: L. [DECISION]: app size, storage UX, which
    models to bless.
13. **MCP client support.** Adopt the official TypeScript SDK behind the
    SHADOW node or a gateway first (React Native bundler compat must be
    tested), with a skill-vetting policy before installing community
    servers. Track 5. PRD fit: extends agent capability under the audit
    log. Effort: M/L. [DECISION]: MCP scope and trust policy for
    third-party servers.
14. **Portable user-owned memory (memU pattern).** Memory as readable,
    portable Markdown plus automatic skill extraction, aligned with the
    Genesis/PCR values already in the ecosystem. Track 5. PRD fit:
    ownership, portability, provenance. Effort: M. [DECISION]: memory
    architecture direction.
15. **Cross-corpus Ask AI.** One natural-language query across chat
    history, calendar, email, notes, and web with source citations
    (Superhuman/Shortwave pattern). Track 3. PRD fit: answers attributed
    to sources, drafts only, never auto-send. Effort: L. [DECISION]:
    connector scope (which inboxes and calendars).
