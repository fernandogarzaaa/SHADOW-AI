# Using consumer AI subscriptions instead of API keys (research, October 2026)

Research date: 2026-10-26. Question: can Shadow AI (Apache-2.0, a local-first
Python "Shadow Node" on the user's own machine, plus iPhone and web clients
that talk to that node) let users pay for model calls with their ChatGPT
Plus/Pro or Claude Pro/Max subscription instead of an API key, and is that
allowed? BYOK stays either way.

Legend:

- **VERIFIED**: I fetched the primary source at the URL shown, on 2026-10-26,
  and the quote is copied from it.
- **UNVERIFIED**: the source was secondary, or the primary page could not be
  fetched (HTTP 403). Don't treat these as policy.

Policy in this area changed several times in 2026. Re-check every URL below
before shipping, and again before each release.

---

## 1. OpenAI (ChatGPT Plus/Pro, Codex)

### 1.1 Short answer

**Permitted, through a program built for this.** OpenAI runs "Sign in with
ChatGPT" (SIWC) with an optional **ChatGPT plan usage** capability. It lets
open-source and locally hosted apps send Responses API requests that are
billed to the user's ChatGPT plan. Shadow qualifies on both counts: it is
Apache-2.0 and runs locally. A second sanctioned route also exists: drive the
user's own locally installed Codex through `codex exec` or the Codex SDK
while the user is signed in with ChatGPT.

### 1.2 Sign in with ChatGPT and ChatGPT plan usage (preferred route)

**Eligibility.**

- VERIFIED, https://developers.openai.com/siwc/token-sharing-open-source.md:
  > "ChatGPT plan usage is an optional capability within Sign in with ChatGPT. In addition to identity scopes, your open-source app can request permission to use the user's ChatGPT plan for eligible Responses API requests. This does not grant access to their ChatGPT conversations or other account context."

  > "These docs explain ChatGPT plan usage for open-source and locally hosted apps. If you're interested in offering it in a paid or remotely hosted app, complete the interest form."
- VERIFIED, https://developers.openai.com/siwc/quickstart:
  > "Sign in with ChatGPT is currently available to selected commercial partners through a limited trial."

  > "ChatGPT plan usage is available to all open-source partners and selected private clients."
- VERIFIED, https://developers.openai.com/cookbook/articles/sign-in-with-chatgpt.
  At launch the cookbook lists the eligible groups as "open-source projects,
  personal projects that run locally, and selected private apps". The user
  needs an eligible ChatGPT **Plus or Pro** account. Paid or remotely hosted
  apps must join the waitlist first.
- VERIFIED, https://learn.chatgpt.com/docs/whats-new/devday-2026:
  > "Let users sign in with ChatGPT and, for eligible Plus and Pro users, use their ChatGPT plan for AI requests in your app."

**How it works.** All VERIFIED, from
https://developers.openai.com/siwc/token-sharing-open-source/sign-in.md,
`.../models-and-inference.md`, `.../preview-limitations.md` and the
cookbook:

- **Sign-in.** OAuth Authorization Code with PKCE and OIDC, using dynamic
  client registration. The OSS flow "remains a public client without a
  secret" and needs "neither a client secret nor a partner API key".
- **Host ID.** Before the first sign-in, the app creates and saves a stable,
  opaque `ext_agent_host_id` for each host. The docs accept
  `urn:uuid:<uuidv4>`, a JWK thumbprint URI, or `did:key`.
- **Redirect.** Must be an HTTP loopback on `127.0.0.1`: "only the port may
  vary", and "Do not substitute with `localhost`."
- **Scopes.** Identity uses `openid profile email`. Plan usage uses
  `offline_access resource.invoke chatgpt.tokens.use.direct`, with resource
  `https://api.openai.com/v1`. Plan usage is on only if the granted scopes
  include `chatgpt.tokens.use.direct`.
- **Token storage.** "Write files atomically with owner-only permissions"
  (0600), and "never commit or log them". When a refresh succeeds, replace
  the access token, expiry, scopes and rotating refresh token together.
- **Inference.** Send `POST https://api.openai.com/v1/responses` with a
  Bearer access token. List models with `GET /v1/models`. The docs say "do
  not point it at ChatGPT's `backend-api` endpoints."
- **Streaming is required.** "Set `store` to `false` and `stream` to `true`
  on each HTTP inference request in this flow." A request counts as
  successful only once `response.completed` arrives.
- **Tool use** (preview-limitations): "Group function/custom tools in
  namespaces or supply them through `additional_tools` input items."
- **Unsupported tools:** "Image generation, file search, Code Interpreter,
  native computer use, hosted MCP/connectors, and Responses `tool_search`."
- **Unsupported fields:** `temperature`, `top_p`, `max_output_tokens`,
  `metadata`, `previous_response_id` over HTTP (send the full history in
  `input`), explicit `system`-role items (use `instructions` instead), and
  others. Audio and video input are not supported.

**Usage accounting.** VERIFIED, from
https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions.md
and `.../errors-and-recovery.md`:

- > "For ChatGPT Plus users, the five-hour usage limit is shared across all apps where they use their ChatGPT plan, including private and open-source clients. ... The five-hour usage limit does not apply for Pro users."
- Users can set a weekly limit for each app (10–100%) in ChatGPT Settings →
  Usage (https://chatgpt.com/settings/usage).
- Limit errors are `subscription_sharing_usage_limit_exceeded` (429),
  `subscription_sharing_usage_unavailable` (503) and
  `subscription_sharing_user_not_eligible` (403).
- > "ChatGPT plan usage errors stop inference. OpenAI does not silently switch the request to another billing path."
- On a declined scope: "offer a clear choice: enable ChatGPT plan usage or configure another supported billing path, such as the user's own API key."

**UI requirements.** VERIFIED, https://developers.openai.com/siwc/ui-ux-guidelines.md:

- Label the button **Continue with ChatGPT**.
- After the first sign-in, show **You're using your ChatGPT plan** once.
- Show **Using ChatGPT plan** near the composer or model picker, with a
  **Manage usage** link to ChatGPT usage settings.
- When a limit is hit, make **Manage usage** the primary action.

**Codex app-server on the SIWC token.** VERIFIED,
https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server.md.
You can run `codex app-server --listen stdio://` with a custom
`model_provider` whose `base_url="https://api.openai.com/v1"`,
`env_key="ACCESS_TOKEN"`, `wire_api="responses"`,
`requires_openai_auth=false` and `supports_websockets=false`.
`clientInfo.name` identifies the calling app, and "No separate Codex sign-in
is required." Renewing the token means restarting app-server and then
calling `thread/resume`.

**Not verified.**

- UNVERIFIED: the help article https://help.openai.com/en/articles/20001542
  ("Using your ChatGPT plan in other apps and sites") returned 403.
- UNVERIFIED: OpenAI's general Terms of Use (https://openai.com/policies/terms-of-use/)
  also returned 403. I could not quote its clauses on credential sharing or
  automated access.
- The SIWC docs tell integrators to "Review OpenAI's terms and policies
  before distributing your integration." Read them before release.

### 1.3 Driving the user's local Codex (secondary route)

- **CLI sign-in.** VERIFIED, https://learn.chatgpt.com/docs/auth.md (redirected
  from developers.openai.com/codex/auth). Codex offers "Sign in with ChatGPT
  for subscription access" and "Sign in with an API key for usage-based
  access".
  - Credentials are cached in `~/.codex/auth.json` or the OS keyring. The
    docs say to "treat `~/.codex/auth.json` like a password".
  - `codex login --device-auth` handles headless machines.
- **Automation default.** Same page: "Use API key authentication for
  programmatic Codex CLI workflows, such as CI/CD jobs."
- **ChatGPT sign-in in automation is supported.** VERIFIED,
  https://learn.chatgpt.com/docs/non-interactive-mode.md. The page has an
  advanced section for "users who need ChatGPT/Codex rate limits instead of
  API key usage". It warns: "Do not use this workflow for public or
  open-source repositories."
- **Mechanism** (same page):
  - `codex exec --json` writes JSONL events to stdout: `thread.started`,
    `turn.started`, `turn.completed`, `turn.failed`, `item.*` and `error`.
  - Other flags: `--output-schema`, `--sandbox read-only|workspace-write|danger-full-access`,
    `--ephemeral`, `codex exec resume <SESSION_ID>`,
    `--skip-git-repo-check` (Codex otherwise requires a git repo).
- **Python SDK.** VERIFIED, https://learn.chatgpt.com/docs/codex-sdk.md.
  - `pip install openai-codex` (Python 3.10+) "controls the local Codex
    app-server over JSON-RPC". It provides `Codex` and `AsyncCodex`,
    `thread_start` and `thread.run`.
  - Published builds bundle a pinned Codex runtime.
    `CodexConfig(codex_bin=...)` points it at the user's own binary instead.
  - The TypeScript package is `@openai/codex-sdk`.
- **App-server protocol.** VERIFIED, https://learn.chatgpt.com/docs/app-server.md.
  It is JSON-RPC over stdio with streamed `item/agentMessage/delta` events.
  - > "Use `clientInfo.name` to identify your client for the OpenAI Compliance Logs Platform."

**Fit for Shadow.** This route runs Codex's own coding agent: its own tools,
sandbox, and git-repo assumptions. Shadow's tools are not first-class here.
It suits delegating a coding task, not acting as Shadow's general chat
backend. Shadow must never read or copy `~/.codex/auth.json`. Codex owns that
file.

### 1.4 Risks (OpenAI)

- **Preview status.** The docs call the restrictions "Preview limitations".
  Unsupported fields and tools may change.
- **Commercial gating.** If Shadow ever ships a paid tier or a hosted relay,
  it leaves the open-source/locally-hosted bucket and needs the interest
  form.
- **Rate limits.** Plus users share one five-hour pool across every app.
  Shadow's background or ambient work could drain the user's ChatGPT
  allowance, so default to user-initiated requests only.
- **Breaking changes.** Model slugs (e.g. `gpt-6.1-sol` in the docs) and the
  catalog vary by account. Always read `/v1/models` and don't hard-code.

---

## 2. Anthropic (Claude Pro/Max, Claude Code)

### 2.1 Short answer

**Shadow running its own Claude sign-in: NOT permitted.** That means a
claude.ai OAuth flow inside Shadow, or reading, storing or reusing Claude
Code's OAuth tokens or `setup-token` output. Anthropic prohibits this
explicitly.

**Shadow launching the user's own, separately installed, unmodified,
user-logged-in `claude` CLI: AMBIGUOUS, and currently tolerated for personal
use.** Anthropic documents and bills `claude -p` and "third-party apps"
against subscription limits. But it also says developers building products
"should use API key authentication". It reserves the right to bill
third-party tool use to pay-as-you-go usage credits, and it enforces
"without prior notice". The conservative reading is in 2.4.

### 2.2 Exact policy text

**Claude Code Legal and compliance.** VERIFIED,
https://code.claude.com/docs/en/legal-and-compliance:

> "**OAuth authentication** is intended exclusively for purchasers of Claude Free, Pro, Max, Team, and Enterprise subscription plans and is designed to support ordinary use of Claude Code and other native Anthropic applications."

> "**Developers** building products or services that interact with Claude's capabilities, including those using the Agent SDK, should use API key authentication through Claude Console or a supported cloud provider. Anthropic does not permit third-party developers to offer Claude.ai login into their own applications, or to route requests through Free, Pro, or Max plan credentials on behalf of their users. Moreover, developers may not collect, store, or intermediate Claude.ai credentials or session tokens — sign-in to a Claude account must complete through Anthropic's own flow."

> "... Nor does it prevent an end user from signing in to the unmodified Claude Code binary with their own Claude subscription, including where a platform hosts Claude Code as described under *Can customers offer Claude Code in their products?* above."

> "Anthropic reserves the right to take measures to enforce these restrictions and may do so without prior notice."

> "Advertised usage limits for Pro and Max plans assume ordinary, individual usage of Claude Code and the Agent SDK."

The same page covers running Claude Code in someone else's product. Unless
otherwise agreed, "preinstalling or running Claude Code in your products or
services (e.g. in hosted sandboxes or other agent infrastructure) requires
agreeing to our Commercial Terms of Service". It sets two conditions:

- "The Claude Code binary must not be modified."
- "Each end user must authenticate with their own Anthropic API key, Claude
  subscription plan credentials, or 3P inference provider credential."

**Agent SDK overview.** VERIFIED, https://code.claude.com/docs/en/agent-sdk/overview:

> "Unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products, including agents built on the Claude Agent SDK. Use the API key authentication methods described in the Quickstart instead."

> "Use of the Claude Agent SDK is governed by Anthropic's Commercial Terms of Service, including when you use it to power products and services that you make available to your own customers and end users"

**Log in to your Claude account.** VERIFIED,
https://support.claude.com/en/articles/13189465-log-in-to-your-claude-account:

> "the usage included in these plans is designed to support ordinary use of native Anthropic applications, including the Claude web, desktop, and mobile applications and Claude Code."

> "The preferred way to access Anthropic services using third-party software, tools, or services is through API key authentication through Claude Console or a supported cloud provider."

> "Anthropic may at its discretion allow paid subscribers who have enabled usage credits to use certain third-party tools to access Anthropic services included in paid subscription plans, but reserves the right to draw use of such third-party tools from usage credits rather than subscription limits. Users are responsible for any usage credit charges incurred this way."

> "Use of third-party tools that misrepresent their identity to Anthropic's servers, attempt to route third-party traffic against subscription limits, or otherwise violate applicable terms or policies is prohibited and such use may be enforced against."

> "If you're building a product, application, or tool for others, use API key authentication through Claude Console or a supported cloud provider."

**Use the Claude Agent SDK with your Claude plan.** VERIFIED,
https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan
(notice dated October 7, 2026):

> "You can still use the Claude Agent SDK, `claude -p`, and third-party apps with your subscription limits."

A June 15, 2026 notice on the same page: "We've paused the previously-announced changes to Claude Agent SDK usage." ... "Claude Agent SDK, `claude -p`, and third-party app usage still draw from your subscription limits."

**Monthly API credits for Max and Team plans.** VERIFIED,
https://support.claude.com/en/articles/17154008-monthly-api-credits-for-max-and-team-plans.
Signed in with a plan, "`claude -p` and Agent SDK usage still draw from your
plan's usage limits". The monthly API credits apply only when you run them
"yourself with an API key" from a linked Console organization.

**Consumer Terms** (effective October 8, 2025). VERIFIED,
https://www.anthropic.com/legal/consumer-terms, Section 3: "You may not
access or use, or help another person to access or use, our Services in the
following ways:" ...

> "Except when you are accessing our Services via an Anthropic API Key or where we otherwise explicitly permit it, to access the Services through automated or non-human means, whether through a bot, script, or otherwise."

> "You may not share your Account login information, Anthropic API key, or Account credentials with anyone else."

> "We may suspend or terminate your access to the Services (including any Subscriptions) at any time without notice"

`claude -p` on a subscription is "explicitly permit[ted]" by the documents
above, so the automation exception applies to the CLI itself. Note the words
"help another person to": they cover Shadow as the helper.

**Secondary reports.** UNVERIFIED (press and blogs, no Anthropic primary
source fetched). Server-side rejection of subscription OAuth tokens in
third-party tools around January 2026. A February 2026 docs change. From
April 4, 2026, OpenClaw-style harnesses billed to usage credits instead of
subscription limits. They are consistent with the "usage credits" sentence
above, but don't cite them as policy.

### 2.3 Mechanism, if built

VERIFIED: https://code.claude.com/docs/en/headless and https://code.claude.com/docs/en/authentication.

**Install and sign-in (done by the user).**

- The user installs Claude Code themselves and signs in with `claude` or
  `claude auth login` through Anthropic's own browser flow.
- On macOS the credentials live in the Keychain. On Linux and Windows they
  live in `~/.claude/.credentials.json`.

**Invocation.**

- Basic call: `claude -p "<prompt>" --output-format json`, which returns
  `result`, `session_id` and `total_cost_usd`.
- Streaming: add
  `--output-format stream-json --verbose --include-partial-messages` to get
  JSONL with `stream_event` text deltas and a final `result` message.
- Structured output: `--json-schema`.
- Continuing a session: `--resume <session_id>` or `--continue`.
- System prompt: `--system-prompt` or `--append-system-prompt`.

**Tools.**

- Claude Code runs its own agent loop and built-in tools.
- Shadow's tools would go in as MCP servers via `--mcp-config`.
- Controls: `--allowedTools`, `--permission-mode` (`dontAsk`, `acceptEdits`,
  `auto`) and `--permission-prompts none`.
- Since v2.1.302, `-p` runs start in Manual mode, so any call that needs
  approval is denied unless something approves it.

**Auth gotchas.**

- `--bare` "never reads OAuth credentials or the system keychain". A
  subscription-backed call therefore cannot use `--bare`, so it also loads
  the user's `~/.claude` hooks, plugins, MCP servers and CLAUDE.md.
- Without `--bare`, a `-p` session in a project directory runs that
  project's hooks and MCP servers with no trust dialog. Run it in an empty,
  Shadow-owned working directory.
- If `ANTHROPIC_API_KEY` is set, `-p` always uses it in preference to the
  subscription. Strip it from the child environment when the user picked
  "subscription".
- `claude setup-token` makes a one-year `CLAUDE_CODE_OAUTH_TOKEN` "for CI
  pipelines and scripts". If Shadow asked for that token or stored it,
  Shadow would be collecting or storing a Claude.ai credential, which the
  legal page prohibits. Don't use it.

### 2.4 Conservative interpretation

**Allowed:**

- The user installs and signs in to the unmodified binary through
  Anthropic's flow.
- Shadow only launches `claude` as a local subprocess for that same user and
  never touches the credential.

The supporting texts:

- the "end user signing in to the unmodified Claude Code binary" sentence;
- the support page saying "`claude -p`, and third-party apps" draw from
  subscription limits;
- "ordinary, individual usage of Claude Code and the Agent SDK".

**Not allowed:**

- Shadow offering a "Sign in with Claude" button.
- Embedding the Agent SDK in Shadow and having it use the subscription.
- Reading the Keychain or `.credentials.json`.
- Taking a `setup-token` value.
- Spoofing Claude Code's identity to call the API directly.
- Shared or multi-user use.
- Running high-volume ambient or background work against the subscription.

**Ambiguous:** whether Shadow, as a distributed product, counts as a
"developer ... routing requests through Pro/Max credentials on behalf of
their users". Every user runs their own copy on their own machine, so no
third party's traffic is pooled. Anthropic can still decide to bill this to
usage credits or to enforce against it without notice. Ship it as an
experimental, opt-in feature with a disclosure. For anything beyond
personal use, ask Anthropic sales in writing.

### 2.5 Risks (Anthropic)

- **Policy reversal or enforcement without notice.** The legal page says
  so, and 2026 already saw several changes.
- **Billing shift.** Usage may draw from paid usage credits instead of plan
  limits.
- **Account action.** Suspension is possible under Consumer Terms §12.
- **Breaking changes.** The CLI changes often. The docs say `--bare` "will
  become the default for `-p` in a future release", and bare mode ignores
  OAuth, so pass explicit flags and pin a minimum version.
- **Not a pure LLM backend.** Claude Code's system prompt, tools and
  `~/.claude` configuration shape every response.

---

## 3. Google (Gemini subscriptions, Gemini CLI)

**Third-party software using Gemini CLI's OAuth: NOT permitted.** VERIFIED,
https://geminicli.com/docs/resources/tos-privacy/ (the official Gemini CLI
docs site):

> "Directly accessing the services powering Gemini CLI (for example, the Gemini Code Assist service) using third-party software, tools, or services (for example, using OpenClaw with Gemini CLI OAuth) is a violation of applicable terms and policies. Such actions may be grounds for suspension or termination of your account."

Also from that page, a login with Google AI Pro or Ultra falls under
"Google Terms of Service, Google One Additional Terms of Service".

**Availability.** VERIFIED on the same site's authentication and headless
pages: "Unpaid tier and Google One users: Gemini CLI was replaced by
Antigravity CLI on June 18th, 2026."

- AI Pro and Ultra remain listed as auth options for Gemini CLI.
- UNVERIFIED: how this applies to AI Pro subscribers billed through Google
  One.
- I did not research Antigravity CLI's terms.

**Mechanism** (VERIFIED, https://geminicli.com/docs/cli/headless/):

- `gemini -p "<prompt>" --output-format json`, or `stream-json`, which emits
  JSONL events `init`, `message`, `tool_use`, `tool_result`, `error` and
  `result`.
- Headless mode reuses a cached login.

**Assessment.** Launching the user's own, logged-in, unmodified `gemini`
binary is not literally "directly accessing the services ... using
third-party software", because the official CLI does the accessing. The
OpenClaw example and the product churn still make this **ambiguous, high
risk**. Conservative call: don't build it now. Keep Gemini on BYOK
(`GEMINI_API_KEY` from AI Studio).

---

## 4. Comparison

| | OpenAI SIWC plan usage | OpenAI local Codex | Claude Code `claude -p` delegate | Gemini CLI delegate |
|---|---|---|---|---|
| Permitted | Yes (OSS / locally hosted; paid or hosted needs waitlist) | Yes (documented; ChatGPT auth in automation) | Ambiguous; tolerated for personal use; Shadow must not touch credentials | Ambiguous / high risk; Shadow-side OAuth prohibited |
| User installs | Nothing (browser sign-in) | Codex CLI (or SDK's pinned runtime) | Claude Code | Gemini CLI |
| User signs into | ChatGPT, via Shadow's OAuth (OpenAI's page) | `codex login` | `claude auth login` | `gemini` |
| Who holds the token | Shadow (0600 file / keychain) | Codex | Claude Code | Gemini CLI |
| Streaming | Yes (required, SSE) | Yes (JSONL / app-server deltas) | Yes (stream-json + partial messages) | Yes (stream-json) |
| Shadow's own tools | Yes (function/custom tools, namespaced) | Via Codex MCP config only | Via `--mcp-config` only | Via CLI's MCP config only |
| Limits | Plus: shared 5-hour pool; per-app weekly cap; 429 `subscription_sharing_usage_limit_exceeded` | ChatGPT/Codex plan limits | Plan limits, or usage credits at Anthropic's discretion | Plan quotas |
| Main risk | Preview API changes | Coding-agent semantics, not a chat backend | Enforcement or billing change without notice | Account suspension |

---

## 5. Recommended design for Shadow

### Build

1. **"Use your ChatGPT plan" provider (`openai_chatgpt_plan`). Ship this
   first.**
   - Implement the SIWC open-source flow in the Shadow Node (Python):
     - loopback on `127.0.0.1` with PKCE;
     - dynamic registration;
     - a persisted `ext_agent_host_id` (`urn:uuid:`), one per Node install;
     - scopes `openid profile email offline_access resource.invoke chatgpt.tokens.use.direct`.
   - Store tokens in the Node's existing encrypted secret store, or a 0600
     file. Never send them to the phone; the phone only sees "connected" and
     the account email.
   - Add a Responses-dialect adapter with these constraints:
     - always `stream: true, store: false`;
     - full history in `input`;
     - `instructions` instead of system items;
     - strip unsupported fields;
     - namespaced function tools for Shadow's tool router;
     - models from `/v1/models`.
   - Map the 429/503/403 `subscription_sharing_*` codes to Shadow's typed
     errors (`rate_limited`, `tier_access`). Never fall back to BYOK
     silently. Offer the switch explicitly, as OpenAI asks.
   - Follow the UI/UX guidelines:
     - a **Continue with ChatGPT** button;
     - a one-time **You're using your ChatGPT plan** modal;
     - a **Using ChatGPT plan** label;
     - a **Manage usage** link to https://chatgpt.com/settings/usage.
   - By default, don't run ambient or background autonomy on the plan. Ask
     the user to opt in, because it drains their five-hour pool.
   - Gate the feature on staying free, open-source and locally hosted. A
     paid tier or a hosted relay needs OpenAI's interest form first.

2. **"Delegate to my Claude Code" (experimental, opt-in, off by default).**
   - Detect a user-installed `claude` on PATH and its version. Check
     sign-in state by running `claude -p` with a trivial prompt and
     `--output-format json` only after the user enables the feature.
   - Run it as a subprocess:
     - with `--output-format stream-json --verbose --include-partial-messages`;
     - in a Shadow-owned empty working directory;
     - with `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` and
       `CLAUDE_CODE_OAUTH_TOKEN` removed from the child environment;
     - with an explicit `--permission-mode` and `--allowedTools`;
     - with Shadow tools exposed only via `--mcp-config`.
   - User-initiated turns only. No background loops, no multi-user sharing.
   - Present it as "runs your Claude Code", not as a Claude login. It must
     not use Claude Code branding as a Shadow feature name.
   - Put it behind a kill switch so a policy change means turning off a
     flag, not shipping an update.

3. **Optional: "Delegate coding task to my Codex"**, via `openai-codex`
   (`CodexConfig(codex_bin=...)` pointing at the user's binary) or
   `codex exec --json`. Use it only for coding or repo tasks. Set
   `clientInfo.name="shadow_ai"`.

4. **BYOK stays the default and the recommended path** for Anthropic and
   Gemini. It is also the fallback offered on every subscription error.

### Do not build

- Any "Sign in with Claude" or claude.ai OAuth inside Shadow. Don't reuse
  Claude Code's OAuth client ID either.
- Reading or importing the macOS Keychain entry, `~/.claude/.credentials.json`,
  `~/.codex/auth.json` or Gemini CLI's cached OAuth.
- Prompting users to paste a `claude setup-token` / `CLAUDE_CODE_OAUTH_TOKEN`
  into Shadow.
- Embedding the Claude Agent SDK on subscription auth.
- Calling `api.anthropic.com` or Google's Code Assist endpoints with
  subscription tokens, or calling ChatGPT's `backend-api`.
- Spoofing a user-agent or client identity.
- Bundling or preinstalling Claude Code in Shadow. That would bring in the
  Commercial Terms conditions; the user installs it.
- A Gemini subscription path of any kind, for now.
- A hosted Shadow relay that runs subscription-backed inference for users.

### User-facing disclosure wording

**ChatGPT plan (settings card).**

> **Use your ChatGPT plan.** Eligible AI requests from Shadow will use the usage included in your ChatGPT Plus or Pro plan. Sign-in happens on OpenAI's site; Shadow stores the resulting access token only on your Shadow Node and never sees your ChatGPT password or conversations. Requests count toward your plan's limits (for Plus, the same 5-hour limit you use in ChatGPT). You can cap or revoke Shadow's access anytime in ChatGPT → Settings → Usage. [Continue with ChatGPT] [Manage usage]

**Claude Code delegate (enable dialog).**

> **Experimental: run requests through your own Claude Code.** Shadow will start the Claude Code program you installed and signed in to on this computer, and pass your request to it. Shadow never sees or stores your Claude login. Anthropic's terms say subscription plans are designed for ordinary, individual use of Anthropic's own apps, and Anthropic may bill third-party use to paid usage credits, limit it, or act on accounts without notice. Use this only for your own personal requests on your own machine. If you want guaranteed, policy-clear access, use an Anthropic API key instead. [Enable at my own risk] [Use API key]

**Gemini (shown where users look for it).**

> Shadow uses Gemini with an API key from Google AI Studio. Google's terms prohibit third-party apps from using Gemini CLI or Google AI subscription sign-ins, so Shadow does not offer that option.

---

## Sources fetched (2026-10-26)

OpenAI:
- https://developers.openai.com/siwc/llms.txt
- https://developers.openai.com/siwc/quickstart
- https://developers.openai.com/siwc/token-sharing-open-source.md
- https://developers.openai.com/siwc/token-sharing-open-source/sign-in.md
- https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference.md
- https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations.md
- https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server.md
- https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions.md
- https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery.md
- https://developers.openai.com/siwc/request-client-id.md
- https://developers.openai.com/siwc/ui-ux-guidelines.md
- https://developers.openai.com/cookbook/articles/sign-in-with-chatgpt
- https://learn.chatgpt.com/docs/auth.md
- https://learn.chatgpt.com/docs/non-interactive-mode.md
- https://learn.chatgpt.com/docs/codex-sdk.md
- https://learn.chatgpt.com/docs/app-server.md
- https://learn.chatgpt.com/docs/whats-new/devday-2026
- 403, not read: https://help.openai.com/en/articles/20001542-using-your-chatgpt-plan-in-other-apps-and-sites and https://openai.com/policies/terms-of-use/

Anthropic:
- https://code.claude.com/docs/en/legal-and-compliance
- https://code.claude.com/docs/en/agent-sdk/overview
- https://code.claude.com/docs/en/authentication
- https://code.claude.com/docs/en/headless
- https://www.anthropic.com/legal/consumer-terms
- https://support.claude.com/en/articles/13189465-log-in-to-your-claude-account
- https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan
- https://support.claude.com/en/articles/17154008-monthly-api-credits-for-max-and-team-plans

Google:
- https://geminicli.com/docs/resources/tos-privacy/
- https://geminicli.com/docs/get-started/authentication/
- https://geminicli.com/docs/cli/headless/
