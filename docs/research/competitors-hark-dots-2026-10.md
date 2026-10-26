# Competitor brief: Hark Pro and OpenAI dots (2026-10-26)

Scope: Hark / Hark Pro, and OpenAI's "dots" personal agents, as of
October 2026. Complements Track 3 of
`docs/research/personal-agent-landscape-2026-09.md`, which covered neither.

## Evidence labels

- **VERIFIED**: stated on a primary source fetched this session (URL given).
- **UNVERIFIED**: from secondary coverage or search snippets only. For dots,
  every openai.com and help.openai.com page returned HTTP 403 to the fetch
  tool, so **no OpenAI primary source could be read this session**. All
  dots claims below are therefore UNVERIFIED. Where several independent
  outlets agree, that is noted.

Primary sources fetched (Hark):

- https://hark.com/ (home)
- https://hark.com/pricing
- https://hark.com/using-hark
- https://hark.com/security
- https://hark.com/privacy-policy (last updated 2026-10-01)
- https://hark.com/manifesto
- https://trust.hark.com/ (page loaded but showed only a title, no content)

Other sources:

- TechCrunch, Hark launch, 2026-10-06:
  https://techcrunch.com/2026/10/06/hark-releases-an-ai-personal-assistant-with-a-focus-on-privacy/
- TechCrunch, dots launch, 2026-09-29:
  https://techcrunch.com/2026/09/29/openai-launches-dots-its-bubbly-agentic-avatar/
- Engadget, dots:
  https://www.engadget.com/2272230/dots-are-openais-new-personal-agents-and-soon-youll-be-able-to-control-several-of-them/
- 9to5Google, dots: https://9to5google.com/2026/09/29/openai-dots-agent/
- OpenTools, dots control boundary:
  https://opentools.ai/news/openai-dots-always-on-agents-launch-availability-limits
- OpenAI Help Center "Getting started with your dot" (403 on fetch; seen
  only as a search snippet): https://help.openai.com/en/articles/20001530
- OpenAI announcement (403 on fetch; URL cited by TechCrunch and OpenTools):
  https://openai.com/index/introducing-dots/
- CopilotKit/OpenDots README (fetched): https://github.com/CopilotKit/OpenDots

## Name disambiguation

- **Hark Pro** is the consumer app from Hark (Hark Labs), Brett Adcock's
  startup. Launched broadly on 2026-10-06 (TechCrunch, secondary). Paid
  tiers are called **Pro²** and **Pro³** (VERIFIED, hark.com/pricing).
- **OpenAI "dots"** (OpenAI writes it lowercase, e.g. "your dot") is a
  feature inside ChatGPT, not a separate app. It is an always-on agent with
  its own cloud computer. Announced at DevDay on 2026-09-29, powered by
  "GPT-6 Astra", and rolling out to Pro and Business Premium (UNVERIFIED;
  consistent across TechCrunch, Engadget, 9to5Google, OpenTools, and the
  help-center snippet).
- **OpenDots** (which the Shadow code cites) is **not an OpenAI product**.
  It is CopilotKit's MIT-licensed, self-hosted alpha template for
  "persistent AI agents, each with its own computer". Its README does not
  mention OpenAI (VERIFIED, github.com/CopilotKit/OpenDots).

---

## 1. Hark Pro

### Core experience and UX

- Three views: **Home** (Action Cards plus Panels), **Chat** (one
  persistent thread where Handoffs happen), and **Projects** (topic
  threads that keep related files together). VERIFIED, /using-hark.
- "A single, persistent chat thread" handles everything, with no "agents"
  or "tokens" to manage. VERIFIED, /using-hark.
- **Action Buttons/Cards** are suggested, prioritized tasks generated from
  email and conversations. Each offers one tap ("Pay", "Cancel") and Hark
  then completes the task end to end. The cards replace problem-style
  notifications. VERIFIED, / and /using-hark.
- **Panels** are custom mini-apps built from a description (trackers, media
  players). You can redesign or query one via "Reply", and they connect
  to services such as Strava, Spotify, and Venmo. VERIFIED, / and /using-hark.
- The background is a live sky simulation driven by location, wind, cloud
  cover, particulates, and time of day. VERIFIED, /using-hark.
- Onboarding: sign in with Google, Apple, or email (VERIFIED, /). Hark asks
  for an email connection so it gets "a snapshot of your life" (VERIFIED,
  /using-hark). No detailed onboarding flow is documented.
- Memory: persistent and learned from conversations. You can ask Hark to
  forget a specific memory (VERIFIED, /using-hark), and you can review,
  edit, or delete memory by asking the agent (VERIFIED, /privacy-policy).
- **Specialties** are memorized multi-step workflows for repeated tasks,
  created by Hark automatically or on request. VERIFIED, /using-hark.
- Voice: the manifesto says the stack uses end-to-end speech models
  (VERIFIED, /manifesto), and the privacy policy lists voice among Inputs
  (VERIFIED). No voice-mode UX is documented on /using-hark.
- Human in the loop: tasks start by "defaulting to consent", you can watch
  the agent act, and there is "a button to cancel your order" (VERIFIED,
  /security). Hark "checks in with you before actions that require
  approval" (VERIFIED, /). TechCrunch adds that the agent's web navigation
  shows in a small window to build trust (secondary). The approval
  taxonomy itself is not documented.

### Agentic capabilities

- **Handoff** is Hark's computer-use agent: its own secure cloud computer
  with a full browser. It signs into websites, buys items, fills forms,
  builds websites, does research, places orders, and makes slides. It
  starts automatically when a request needs a browser. VERIFIED, / and
  /using-hark.
- Up to six browsers at once and "millions of websites": UNVERIFIED
  (search snippet only).
- Direct API connections include Google Workspace and Microsoft 365, plus
  "more". Google Docs is used for tracking complex projects, and Handoff
  "can use thousands of websites". VERIFIED, /using-hark.
- **Scheduled Tasks** (recurring actions, created by asking) and
  **Background Tasks** (for example, tracking a food delivery, with a lag
  of a few minutes) are both VERIFIED, /using-hark. Slack tracking and doc
  creation are listed features (VERIFIED, /pricing).
- The model is trained specifically for computer use (TechCrunch,
  secondary). Demo examples: a DMV registration renewal and expense
  approvals (secondary).

### Surfaces

- Browser, iOS, and Android. VERIFIED, / and /using-hark.
- Hardware: "bespoke native hardware devices" and "agentic computers" are
  planned, with no dates (VERIFIED, /manifesto). A 2027 device was
  reported by TechCrunch (secondary).
- No messaging-app or wearable surface is documented.

### Pricing (VERIFIED, hark.com/pricing and /using-hark)

| Tier | Price | Unlocks |
|---|---|---|
| Free | $0 | All features |
| Pro² | $20/mo | 2x usage |
| Pro³ | $100/mo | 10x usage |

- No absolute limits are published, only illustrative examples. Upgrading
  "does not unlock additional features".
- **Auto top-up** refills credits from a connected card, up to a ceiling
  you set. VERIFIED, /using-hark.

### Privacy and data model

- Cloud-hosted. Data may be transferred to US servers. VERIFIED,
  /privacy-policy.
- No training on Inputs, Outputs, Memory, or connected-account data, with
  "no opt-out needed". VERIFIED, /privacy-policy.
- Third-party AI providers are bound by written no-training agreements
  (VERIFIED, /privacy-policy). /security calls them "0 data retention"
  vetted models (VERIFIED, /security).
- **Secured by Hark**: an encrypted vault. Passwords and card numbers are
  tokenized and "detokenized only on the target page". Hark claims "We
  never see your most sensitive data" and that it never sells data or uses
  it for ads. VERIFIED, /, /security, /using-hark. No cryptographic detail
  is published, and the trust center showed no content when fetched.
- Data is retained for the lifetime of the account. Backups are deleted
  within 90 days. Sandbox data (files, shell commands, logs) is collected.
  VERIFIED, /privacy-policy.

### Recent launches (Sept-Oct 2026)

- 2026-10-06: Hark Pro broad launch (TechCrunch, secondary).
- 2026-10-01: privacy policy updated (VERIFIED).
- No later changelog was found.

---

## 2. OpenAI dots (all UNVERIFIED: OpenAI pages returned 403)

### Core experience and UX

- You start with one **primary dot** that you name and customize. Teams of
  dots and specialist dots are planned. (TechCrunch, Engadget, 9to5Google.)
- A dot pursues user-defined goals in the background and makes progress
  between conversations. Talking to it is "as simple as having a
  conversation" (OpenAI quote via Engadget). The help-center snippet says
  "always-on agent ... can take on ongoing responsibility and keep making
  progress between conversations."
- **Check-ins**: the dot messages you with progress, questions, or
  decisions that need your input (Engadget).
- **Activity view**: you can watch the dot's cloud computer at any time
  and redirect it (Engadget, 9to5Google, OpenTools).
- Memory: it learns from your feedback over time (9to5Google). Idle
  research is saved as the dot's private notes. OpenAI reportedly does not
  train directly on those notes or on proactive research (OpenTools).
- Approvals: dots ship with built-in rules for when to act alone and when
  to ask (OpenAI quote via Engadget). Users add **Custom Rules** that
  allow, require approval for, or block an action. Permissions reuse
  ChatGPT's app controls. **Auto-review** checks actions that could affect
  accounts or share information. Some actions, such as password changes,
  always stay with the human. (Engadget, OpenTools.)
- **Proactive research while idle uses read-only tools only**: no sending
  messages, editing app content, or controlling a browser or computer
  (Engadget, OpenTools, 9to5Google).
- Example from OpenAI: the dot noticed an unbilled article, drafted an
  invoice, and sent it after the user approved (Engadget, 9to5Google).

### Agentic capabilities

- Each dot has its own cloud computer and browser, and keeps running after
  you log off.
- It reaches 4,000+ apps via ChatGPT plugins (Engadget, 9to5Google).
- Optional control of your own computer, off by default and connected
  through the desktop app (help-center snippet, Engadget).
- Saved passwords can be used on supported sites without exposing them to
  the model (Engadget, OpenTools).
- It can start or manage work in Codex and ChatGPT Work (OpenTools).
- Monitoring can pause or stop a dot when it detects a safety concern
  (OpenTools).

### Surfaces

- Created only on ChatGPT desktop or desktop web, not on mobile at launch.
  After setup you can message it from the mobile app (help-center snippet,
  9to5Google).
- Voice calls with the dot in ChatGPT (Engadget, 9to5Google).
- Slack and Microsoft Teams, with text messaging "coming soon"
  (TechCrunch).
- Launchable from Codex or ChatGPT (TechCrunch).
- Enterprise specialist dots under Microsoft Agent 365 governance are
  reported as pilot or roadmap (TechCrunch; timing varies by outlet).

### Pricing and availability

- One dot included with ChatGPT **Pro** and **Business Premium**. Pro is
  excluded in the EEA, Switzerland, and the UK. Enterprise, Edu, and
  Healthcare get an admin-enabled beta, off by default.
- Chatting with the dot does not count toward ChatGPT limits. Work it does
  in Codex or Work does count. Extended allowance in the first month, with
  usage terms to follow.
- Extra dots and extra capacity are future options.
- 9to5Google mentions a new $500/mo ChatGPT Pro tier but does not tie it
  to dots. **The exact current Pro price was not confirmed.**

### Privacy and data model

- Cloud-hosted on OpenAI infrastructure. Business, Enterprise, and Edu
  content is not used for training by default. Personal-plan users control
  the improvement setting. (OpenTools.)
- OpenAI acknowledges its prompt-injection defenses are not perfect
  (secondary).

### Recent launches

- 2026-09-29: dots announced at DevDay and rolled out to Pro and Business
  Premium (all outlets).

---

## 3. Already in Shadow

Code citations are from `apps/shadow-node/shadow_node/` and `packages/`.

| Competitor idea | Shadow equivalent |
|---|---|
| Hark Panels (glanceable mini-dashboards) | `panels.py` (Hark item 2) |
| Hark "build a panel from a description" | `custom_panels.py` (Hark item 3) |
| Hark Scheduled Tasks | `scheduled_tasks.py`, `reminders.py` (Hark item 4) |
| Hark accounts / connections screen | `accounts.py` (Hark item 5) |
| One assistant across devices | `continuity.py` (Hark item 11) |
| Approval before consequential acts, cancel/consent | Sentinel-lite `policy.yaml`: sensitive_tools, `irreversible_tools` with double confirmation (Hark item 12) |
| dots Custom Rules (allow/ask/block) | `policy.yaml` `tool_tiers` (always_ask/auto_approve/always_allow) plus blocked_tools. Operator-file only; no in-app editor |
| dots read-only idle research | `ambient_tasks.py` contract: tasks are read-only observers; acting goes through the approval path |
| dots proactive check-ins | `shadow_acts.py` plus `paced_plans.py` (policy-gated proactive acts, quiet hours, staged delivery) |
| Name your primary dot | `persona.py` (name, avatar, vibe) |
| Hark "forget a memory" | Memory cards with per-card forget (`DELETE /memory/{id}`) |
| dots goals | `goals.py` (tracking, progress, briefing). Not autonomous goal pursuit |
| Daily feed / ideas | `feed.py`, `ideas.py` |
| Docs/slides output | `artifacts.py` (with OpenDots-style revision 409) |
| Voice | `voice.py` (TTS and voice notes; needs a provider) |
| OpenDots HITL receipts, scope guard, request hygiene, per-device credentials | `main.py` approvals receipt, `runtime_scope.py`, `request_hygiene.py`, `device_credentials.py` |
| Privacy posture | Stronger than both: local-first, encrypted at rest, BYOK, tamper-evident audit chain |

## 4. Features Shadow lacks, ranked by user value

1. **Browser/computer-use agent with live activity view** (Hark Handoff
   VERIFIED; dots cloud computer and activity view UNVERIFIED). Shadow has
   web fetch and search only. Local version: a sandboxed headless browser
   on the node, with a screenshot stream to the phone and every
   submit/purchase step passing the existing irreversible gate. This is
   the main capability gap with both products.
2. **One-tap Action Cards from email and calendar** (Hark, VERIFIED).
   Turn feed/ideas into prefilled, approval-ready actions ("Pay", "Reply",
   "Cancel"). This depends on the ROADMAP item for real email/calendar
   connectors.
3. **Credential vault with detokenize-at-use** (Hark Secured by Hark
   VERIFIED; dots "passwords never exposed to the model" UNVERIFIED). Keep
   site credentials and cards in the node's encrypted store and inject
   them only into the browser step, never into model context.
4. **In-app rules editor for autonomy** (dots Custom Rules, UNVERIFIED).
   Shadow's `tool_tiers` exist but need operator file edits and a restart.
   Expose allow/ask/block per tool or connector in the app and dashboard,
   with signed changes and audit. Keep the hard gates non-waivable.
5. **Autonomous goal pursuit with check-ins** (dots, UNVERIFIED). Link
   `goals.py` to Shadow Acts so a goal can own a standing read-only
   research loop that writes private notes and asks for decisions through
   approvals and push.
6. **Specialties: learned reusable workflows** (Hark, VERIFIED). Detect
   repeated multi-step runs and offer to save them as named, re-runnable,
   approval-gated workflows. These could build on the ghost-adapter skill
   registry.
7. **Messaging surfaces** (dots Slack/Teams with SMS coming, UNVERIFIED).
   Let the node answer through a user-owned channel (Telegram, Signal,
   iMessage via Mac, Slack), with approvals deep-linking back to the app.
8. **Projects: topic threads with attached files** (Hark, VERIFIED).
   Group chats, artifacts, and memory under a project, such as a trip or a
   job search.
9. **Voice calls with the agent** (dots, UNVERIFIED; Hark voice models
   VERIFIED via the manifesto). This means a realtime duplex call mode
   beyond Shadow's TTS and voice notes.
10. **Background tracking of external tasks** (Hark Background Tasks,
    VERIFIED), for example a delivery or order status poller that feeds
    the feed.
11. **Multiple specialist agents** with their own identity, tools, and
    rules (dots roadmap and OpenDots, UNVERIFIED for OpenAI). Lower
    priority for a single-user personal agent.

Not worth copying: Hark's usage-credit tiers and auto top-up (they don't
fit BYOK), and the sky background (cosmetic, though it does make Home
feel alive).
