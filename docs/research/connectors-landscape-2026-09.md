# SHADOW-AI Connector Landscape

Date: 2026-09-27. Goal: a connector architecture so the SHADOW-AI agent
can read and act (with approval) across the user's apps: email, social,
GitHub, messaging, and productivity tools.

Method: five parallel research tracks (email, social, GitHub,
messaging/productivity, MCP fast-path), each run against primary
developer docs where reachable. Claims marked VERIFIED were confirmed in
an official doc or page the researcher opened (URL cited). Claims marked
SECONDARY are corroborated by multiple independent sources but not
confirmed against a primary doc. Claims marked UNVERIFIED could not be
confirmed and must not drive product or engineering commitments.

Nothing in this report invents an endpoint, scope string, price, or
quota. Quoted values come from the cited source.

## 1. Email connectors

### Gmail API

Auth: OAuth 2.0 authorization code with PKCE for installed/mobile apps.
VERIFIED (developers.google.com/identity/protocols/oauth2/native-app):
Google supports PKCE S256; installed apps use a custom URI scheme
redirect; loopback IP redirect is deprecated for mobile; the installed-app
client secret is "obviously not treated as a secret". Refresh tokens
require `access_type=offline`. Incremental authorization is Google's
stated best practice: request scopes at the time access is required, not
up front.

Scopes (VERIFIED, quoted from the official Gmail scopes page):
- Sensitive, verification review only, no security assessment:
  `https://www.googleapis.com/auth/gmail.send` ("Send email on your
  behalf.")
- Restricted, verification PLUS annual security assessment:
  `https://mail.google.com/`,
  `https://www.googleapis.com/auth/gmail.readonly` ("View your email
  messages and settings."),
  `https://www.googleapis.com/auth/gmail.compose`,
  `https://www.googleapis.com/auth/gmail.modify` ("Read, compose, and
  send emails from your Gmail account."), plus insert, metadata, and
  settings scopes.

Key quote: "If you store restricted scope data on servers (or transmit),
then you must go through a security assessment."

Verification and CASA cost: VERIFIED
(support.google.com/cloud/answer/9110914): restricted scopes require
annual re-verification; Google charges no fee for the assessment itself.
Assessor cost is SECONDARY and lab dependent (reports range from roughly
$675 for basic to $4,500+ for full assessments). The highest-value open
question: whether a purely local-first app (tokens and mail on device
only, no server transit) triggers CASA at all. Google's pages are
ambiguous on this. Settle in writing with Google before committing to
the restricted tier. UNVERIFIED.

Quotas (VERIFIED, official quota page): 1,200,000 units/min/project,
6,000/min/user/project, 80,000,000/day billing threshold. Per-method
costs: messages.list 5, messages.get 20, threads.get 40, history.list 2,
messages.send 100, drafts.create 10, drafts.send 100. "All standard use
of the Gmail API is available at no additional cost." Over-threshold
billing is planned later in 2026 with at least 90 days notice. A
single-user personal agent sits orders of magnitude below thresholds.

Key agent operations: `users.messages.list` (search with `q`),
`users.messages.get`, `users.threads.get`, `users.drafts.create`,
`users.messages.send`, `users.drafts.send`, `users.messages.modify`
(mark read/unread, restricted). Ambient change detection without a
server: `users.history.list` polling (2 units per call). `users.watch`
push requires a Cloud Pub/Sub topic, i.e. a server component, so it is
not viable for a purely local-first design.

IMAP/SMTP fallback: dead. Google disabled basic auth for consumer
accounts in 2024-2025 (SECONDARY: March 2025 consumer, May 2025
Workspace). App passwords remain but are fragile and on a deprecation
trajectory. XOAUTH2 IMAP needs the full `https://mail.google.com/`
restricted scope. OAuth via the Gmail API is the only durable path.

Mobile/Expo viability: VERIFIED (docs.expo.dev auth-session):
`expo-auth-session` works in Expo Go, system-browser OAuth with
deep-link return via the app scheme, PKCE supported, never embed secrets
in app code.

PRD fit: strong, with one cost decision. Split read and send: the
sensitive `gmail.send` scope covers send-only without CASA; read scopes
trigger the assessment question. Drafts need no approval to create;
every send goes through the approvals inbox (PRD: no auto-send). Reads
happen only on explicit user request or a user-enabled ambient schedule
(PRD: no silent reading; scheduler defaults OFF).

### Microsoft Graph (Outlook mail)

Auth: Entra ID OAuth 2.0 authorization code + PKCE for public/native
clients; device code flow also available. Register an app in Entra, add
delegated Graph permissions. `offline_access` scope needed for refresh
tokens. SECONDARY (Microsoft's permissions reference page returned 403
to the fetcher; scope names corroborated across 5+ independent
sources): `Mail.Read`, `Mail.ReadBasic`, `Mail.ReadWrite`, `Mail.Send`,
`User.Read`.

Verification: no Google-style restricted tier and no security assessment
for mail delegated permissions (SECONDARY). Publisher verification is
required only for a shared multi-tenant client ID offered broadly; the
BYO-OAuth pattern (each user registers their own free Entra app, works
with a personal Microsoft account) sidesteps verification entirely.

IMAP/SMTP: basic auth for IMAP/POP removed in 2022-2023 (SECONDARY).
SMTP AUTH basic auth is disabled by default on existing tenants at end
of Dec 2026, with final removal to be announced in H2 2027 (SECONDARY,
citing Microsoft's Jan 2026 timeline). OAuth is the only durable path.

Rate limits (SECONDARY, corroborated): 10,000 requests per 10 minutes
per app+mailbox, 4 concurrent requests, 429 with `Retry-After` on
throttle. Exchange send cap around 30 messages per minute (SECONDARY).
Graph API is free; the account needs a Microsoft 365 subscription or a
free Outlook.com account.

Key agent operations (SECONDARY): `GET /me/messages` with
`$filter`/`$search`, `GET /me/messages/{id}`, `POST /me/messages`
(draft), `PATCH /me/messages/{id}` (mark read/unread, needs
Mail.ReadWrite), `POST /me/sendMail`, delta queries for ambient
detection.

Mobile/Expo viability: `expo-auth-session` against Entra v2.0 endpoints
with PKCE and the app's custom scheme works in Expo Go (SECONDARY).
`react-native-msal` with the broker needs a dev client (native module)
and cannot run in Expo Go.

PRD fit: excellent. Granular delegated permissions, per-permission
consent screens, user-revocable tokens, no assessment tax. BYO-OAuth
keeps the consent relationship 1:1 between the user and their own app
registration.

## 2. Social connectors

### X (Twitter) API

Pricing (SECONDARY, corroborated by three independent sources crawled
within 24h of research; docs.x.com blocked the fetcher): since February
2026, pay-per-use for self-serve developers, no subscriptions, no free
tier for new developers. Reported prices: $0.005 per post read, $0.010
per user profile, $0.015 per post created ($0.20 with a URL), $0.001 for
reads of your own account's data. Cap of 3M post reads per monthly
cycle; above that, Enterprise at $42,000+/month. Confirm prices on
docs.x.com before budgeting. UNVERIFIED against official docs.

Auth: OAuth 2.0 authorization code with PKCE (S256 required) for user
context; app-only bearer is read-only. Scopes (SECONDARY, consistent
across recent sources): `tweet.read`, `tweet.write`, `users.read`,
`offline.access`, `like.read`, `like.write`, `follows.read`,
`follows.write`, `bookmark.read`, `bookmark.write`, `dm.read`,
`dm.write`, `media.write`, among others. No app-review gate for
ordinary posting apps: developer account, developer agreement, registered
callback, funded credits.

Key agent operations: recent search covers the last 7 days for every
developer; full-archive search needs an access upgrade or Enterprise.
Mentions and home timeline read via user-context endpoints. DM scopes
exist; whether they need an elevated gate is UNVERIFIED.

Mobile/Expo viability: PKCE flow via system browser and custom-scheme
redirect works from Expo (`expo-auth-session`), no backend needed.

PRD fit: viable but metered. Every read costs money, so ambient polling
of mentions needs a per-connector budget guard in Sentinel-lite. Drafts
and summaries are free to prepare; posting goes through the approvals
inbox. Revocation via standard OAuth revoke.

### LinkedIn

Access model (SECONDARY, consistent across 2026 sources): two free
self-serve products, no approval wait: "Sign In with LinkedIn using
OpenID Connect" (`openid profile email`) and "Share on LinkedIn"
(`w_member_social`). Everything else (feed, analytics, connections,
search, DMs) is partner-gated with custom terms. Dollar figures
circulating online are third-party estimates, not LinkedIn's rates.

Critical gap, VERIFIED by multiple consistent 2026 sources: there is NO
self-serve read API for a member's feed, own posts, notifications, or
search. LinkedIn is a write-only connector on the self-serve path. The
agent can draft and post to the member's profile but cannot read back
mentions or summarize a feed.

Auth: three-legged OAuth 2.0 (authorize and token endpoints VERIFIED
across recent sources). Access tokens valid 60 days; standard apps have
no refresh token (partner-only); renewal repeats the OAuth flow. The
token exchange requires the client secret, which is risky in a mobile
binary (acceptable in the credential vault for a personal app; a
backend exchange is cleaner).

Rate limits (SECONDARY, from LinkedIn docs): 150 requests per member
per day, 100,000 per application per day.

PRD fit: excellent consent story, poor readback. No cost.
Approval-before-post maps directly to the approvals inbox.

### Meta: Facebook, Instagram, Threads

Note: developers.facebook.com returned HTTP 403 to the fetcher, so Meta
claims below are SECONDARY from recent integrator docs.

Facebook: personal profiles are effectively dead for APIs
(`publish_actions` killed 2018; `user_posts` needs Advanced Access plus
App Review plus Business Verification, practically unavailable). Pages
are alive: `pages_manage_posts`, `pages_read_engagement`,
`pages_manage_engagement`, and related scopes allow full Page
management. Messenger API is Page-to-user only; personal Messenger has
no API. Facebook Login requires HTTPS redirect URIs, so a mobile app
needs a backend callback or the native Facebook SDK via dev client.
Development mode allows up to 25 test users with all permissions working
immediately, which is the legitimate single-user path for a personal
agent (the owner is the developer).

Instagram: only via Instagram Graph API with a Business or Creator
account linked to a Facebook Page. Two-step container publish flow; 50
posts per 24h (feed, Reels, Stories combined). Media must be hosted at a
public URL. Reads: media, comments, insights. DMs: only the 20 most
recent messages per conversation retrievable (SECONDARY). App review
required beyond test users.

Threads: standalone OAuth against threads.net. Scopes include
`threads_basic`, `threads_content_publish`, `threads_read_replies`,
`threads_manage_replies`, `threads_keyword_search`. Publishing is a
two-step container flow (text-only posts support one-step
`auto_publish_text`). Limits: 250 posts and 1,000 replies per rolling
24h; keyword search capped at 500 queries per rolling 7 days (a hard
ceiling for listening). No DM API. Standard access suffices for posting
to your own account. Free. Token lifecycle UNVERIFIED (60 days reported;
renewal behavior unclear).

PRD fit: excellent per-connector consent and revocation. Hard
constraints: personal Facebook timelines and personal Messenger cannot
be read at all; do not fake them with browser automation. Every publish
call goes through the approvals inbox.

### Reddit

Free tier (SECONDARY; reddit.com blocked automated fetching): 100
queries per minute with OAuth, non-commercial use only. Commercial tier
(SECONDARY): roughly $0.24 per 1,000 calls with a minimum around
$12,000/month; no smaller commercial plan; enterprise contracts run
$50,000+/year.

2026 access change (SECONDARY, multiple independent 2026 sources):
self-service OAuth app registration closed in late 2025 under the
Responsible Builder Policy; new Data API access needs a manual access
request and approval (typically 2-4 weeks).

Auth: OAuth 2.0 with PKCE for installed apps, viable via
`expo-auth-session`. Scopes include `identity`, `read`, `submit`,
`edit`, `vote`, `save`, `history`, `privatemessages`, `mysubreddits`.
Token lifetime 1 hour; web apps get refresh tokens with
`duration=permanent`.

Key agent operations: subreddit search, comments, submit posts/comments
(`submit` scope), read/save/vote, inbox and personal messages
(`privatemessages`, the only true personal DM API in this survey).

PRD fit: best free read connector in the set. Per-scope consent,
revocation via standard flow, strong auditability. Policy: drafts go
through the approvals inbox; the agent posts only to the user's own
profile or explicitly chosen subreddits (posting into arbitrary
subreddits risks an account ban).

### TikTok

Auth (VERIFIED from official docs the researcher opened): registered app
on developers.tiktok.com, Login Kit, per-product scopes. Content Posting
API Direct Post on `https://open.tiktokapis.com/v2/`: creator info
query (required pre-post step), video init (`FILE_UPLOAD` or
`PULL_FROM_URL`), status fetch. Critical: "All content posted by
unaudited clients will be restricted to private viewing mode." Public
posting requires passing a compliance audit.

Scopes (SECONDARY, consistent): `user.info.basic`, `video.list` (own
videos), `video.upload` (drafts for the user to finish), `video.publish`
(direct post). Reads return only the user's own profile and video
metadata; no feed reading, no search, no listening, no DM API.

Limits: app-level tiers (Basic 10 QPS / 600 QPM / 864,000 QPD,
upgradeable); per-user info/video-list caps reported at 100/day
(SECONDARY). Throttling returns HTTP 200 with `"code": 40100` in the
body, not HTTP 429.

Mobile/Expo viability: PKCE mandatory for Login Kit on mobile. The
token exchange must happen on a backend (client secret cannot ship in
the app). Practical paths: Share Kit handoff to the TikTok app for
user-confirmed posting (zero backend), or web OAuth plus backend token
exchange for API posting.

PRD fit: strong alignment. Explicit per-scope OAuth; the audit gate
enforces no-silent-publishing (unaudited posts are private-only, a
natural safety default); the Share Kit path routes publishing through
the TikTok app's own confirmation UI. Value here is posting assistance,
not feed summarization. Free; the gate is review, not money.

## 3. GitHub connector

Auth recommendation (VERIFIED, docs.github.com): a **GitHub App with
user-to-server tokens via the device flow**. Fine-grained permissions
(no scopes); the user access token gets the intersection of what the
app requested and what the user can access. Token prefix `ghu_`;
refresh `ghr_`. Access tokens expire after 8h by default, refresh after
6 months; expiration is opt-outable. Device flow needs no client secret:
`POST https://github.com/login/device/code` with only `client_id`, poll
the access token endpoint, user enters the 8-char code at
`https://github.com/login/device`. Device flow must be explicitly
enabled in the app settings. The web application flow supports PKCE but
the documented token exchange still lists `client_secret` as required,
and GitHub states never to ship the secret in client-side code, so the
device flow is the correct mobile path. GitHub explicitly prefers Apps
over OAuth apps: granular permissions, user control over repo access,
short-lived tokens.

Auditability (VERIFIED): actions via a GitHub App user-to-server token
are shown as the user with the app's identicon badge overlay, and audit
logs record `programmatic_access_type` = "GitHub App user-to-server
token". Exactly what the PRD's audit trail needs.

API choice: REST as the default (`https://api.github.com`), GraphQL v4
for nested dashboard reads (one round trip for PR + reviews + checks +
comments). No 2026 deprecation of either found. GraphQL notification
types were deprecated effective Jan 1, 2026, so REST is the reliable
path for notifications (SECONDARY, from a community research doc
observing GitHub's own iOS app).

Notifications strategy (VERIFIED): the notifications API is "optimized
for polling with the `Last-Modified` header": send `If-Modified-Since`
and a 304 response "leaves your current rate limit untouched". Obey the
`X-Poll-Interval` header (typically 60s). Webhooks need a public
callback URL, which a pure-local mobile app cannot provide, so register
the GitHub App with webhooks off and poll.

Rate limits (VERIFIED): REST 5,000 requests/hour per user (user-to-server
tokens share the user's combined budget); installation tokens start at
5,000/hr and scale to 12,500/hr. GraphQL 5,000 points/hour per user.
Secondary limits: 100 concurrent requests, ~80 content creations/min.
Search: 30 requests/min authenticated (SECONDARY). Exhaustion returns
403/429 with `x-ratelimit-remaining: 0`; `GET /rate_limit` is exempt
from accounting.

Key agent operations: triage inbox (`GET /notifications`), list
issues/PRs, summarize PR diffs, comment on issues/PRs, open issues/PRs,
merge PRs (approval-gated), CI failure digests (`actions/runs`,
check-runs), code search.

PRD fit: excellent. Device flow UX is inherently consent-first (the user
approves in their own browser). Start with read-only permissions
(Contents/Issues/Pull requests/Actions/Checks read); request write
permissions only when the user enables agent actions (GitHub prompts
re-approval on permission changes). Revocation in GitHub settings;
subsequent calls return 401, which the connector surfaces as a re-auth
prompt. Keep the ambient scheduler OFF by default.

## 4. Messaging and productivity connectors

### Telegram Bot API

Auth: two models. (a) Bot API: bot created via @BotFather, HTTP token,
calls to `https://api.telegram.org/bot<token>/method` (VERIFIED,
official FAQ). (b) User account via MTProto: technically possible with
the user's own session, but acting as a user account with automation is
the "userbot" gray zone with ban risk; ToS status UNVERIFIED.

Bot capabilities (VERIFIED, official FAQ): all messages from private
chats with users, service messages, all messages from channels where it
is a member. In groups, privacy mode (default on) limits it to commands
addressed to it. Updates via long polling (one concurrent poller) or
webhooks (HTTPS only).

Limits (VERIFIED, official FAQ, quoted): single chat "avoid sending
more than one message per second"; group "not more than 20 messages per
minute"; bulk "not more than about 30 messages per second" unless paid
broadcasts (1000/sec at 0.1 Stars per message above the free tier).
Files up to 50 MB send, 20 MB via `getFile`. Free.

Mobile/Expo viability: plain HTTPS + JSON, trivially callable from
Expo. Inbound needs a relay: webhooks need a public endpoint, long
polling needs an always-on process. Do not embed the bot token in the
client without protection.

PRD fit: good. The bot model is inherently scoped (only chats the user
started or groups it was invited to) and cannot impersonate the user,
which is the PRD-safe default. Revocation via BotFather or blocking the
bot. Explicit consent: the user must initiate the bot chat.

### Discord

Auth: bot token (`Authorization: Bot <token>`) for server actions,
OAuth2 bearer for delegated user actions, user tokens are self-botting
and violate ToS. Reading or posting in servers requires a bot installed
via an OAuth2 invite with the `bot` scope plus explicit permissions
(View Channels, Send Messages, Read Message History). An OAuth user
token alone (identify, guilds scopes) cannot read server channel
messages (SECONDARY).

Privileged intents (VERIFIED, official docs): `GUILD_PRESENCES`,
`GUILD_MEMBERS`, `MESSAGE_CONTENT`. Reading message text needs
MESSAGE_CONTENT; without it, content arrives empty. Unverified apps can
use privileged intents without approval but must enable them in app
settings; bots in 100+ servers need verification.

Rate limits (VERIFIED, official docs mirror): 50 requests/second global
for bots, per-route buckets via `X-RateLimit-Bucket`, 429 bodies carry
`retry_after`. Free.

Mobile/Expo viability: REST polling is the practical mobile path; the
Gateway WebSocket is not phone-friendly for always-on use.

PRD fit: decent. Strong scoping (bot only sees servers it was invited
to, per-permission grants at invite time); revocation by removing the
bot or resetting the token. A bot cannot act AS the user, which fits the
no-impersonation principle. MESSAGE_CONTENT is a toggle, not
per-conversation consent, so SHADOW-AI re-gates sends through the
approvals inbox anyway.

### Slack

Auth (VERIFIED in current setup guides): bot tokens (`xoxb-`) represent
the app; user tokens (`xoxp-`) represent a workspace member and are "the
only Slack-native way to act/read as a user". App-level tokens
(`xapp-`, `connections:write`) are for Socket Mode only.

Scopes (VERIFIED in current guides): read `channels:history`,
`groups:history`, `im:history`, `mpim:history`, `channels:read`,
`users:read`; write `chat:write`, `im:write`, `reactions:write`,
`files:read`/`files:write`. Notable: `search.messages` is user-token
only, not available to bot tokens.

Real-time: Socket Mode routes events over one WebSocket with the
`xapp-` token, so no public endpoint is needed; bot tokens work over
Socket Mode, user tokens cannot open Socket Mode connections (VERIFIED
in a 2026 research doc). A persistent socket on a phone is fragile, so a
small backend relay holding the Socket Mode connection and pushing to
the app is the sane architecture. Useful pattern: events in on the bot
token, content actions via the xoxp user token as an explicit "act as
user" opt-in.

Costs: API free; workspace must have the app installed (admin approval
may be required on managed workspaces). Free-plan history caps:
UNVERIFIED; treat history availability as best-effort.

PRD fit: best fit of the chat connectors. Granular scopes per
conversation type, token revocation in Slack settings, bot identity
separate from user identity with an explicit opt-in to act as the user.
Every `chat:write` on a user token sends AS the user, so Sentinel-lite
gates every xoxp call behind approval; default to the bot token.

### WhatsApp Business API (Cloud API)

State and pricing (VERIFIED, Meta docs updated Aug 25, 2026):
categories are marketing, utility, authentication (templates, always
charged), service (free-form replies, charged from Oct 1, 2026), Meta
Business Agent (AI replies, token-based from Aug 1, 2026, $2.00 per 1M
tokens). Service messages can only be sent "in an open 24-hour customer
service window, which opens and resets with each user message"; they
"can only be used to respond, not reach out". Service messages were free
since Nov 2024; charging starts Oct 1, 2026 (payment method required by
Sep 30, 2026 or delivery stops).

Acting as the user's own number: largely no. The Cloud API is
business-only; a number registered to the Cloud API leaves the phone
app. Reusing a personal number requires deleting its WhatsApp account;
"coexistence" (app + API on one number) is only available through Meta
partners, not direct developers (SECONDARY). Unofficial personal-number
automation (Baileys-style) violates WhatsApp ToS and risks number bans.

PRD fit: poor for a personal agent acting as the user, by design. The
API is business-to-customer; the 24h window means the agent cannot
proactively message anyone; per-message metering conflicts with a free
personal app. Recommendation: notify-only via a business number with
explicit per-recipient consent, or deprioritize. Do not build on
unofficial personal-number automation.

### Notion API

Auth (VERIFIED, developers.notion.com): REST at
`https://api.notion.com`, bearer token plus required `Notion-Version`
header. Internal integration token (single workspace, simplest) or
public OAuth integration (code exchange, plus `/v1/oauth/introspect`
and `/v1/oauth/revoke`). Scope inventory is SECONDARY (from a community
scope matrix): read/insert/update content, read/insert comments,
read/insert/update databases, read users.

Key operations: search, retrieve page, query data sources, create/update
pages, append blocks (100 per request, 2 nesting levels), comments,
users, file uploads. Page version history is not exposed (SECONDARY).
Webhooks are limited (OAuth integrations only, subset of events);
practical inbound is polling (SECONDARY).

Limits (VERIFIED via a transcription of the official request-limits
page): "The rate limit for incoming requests per integration is an
average of three requests per second." Payload caps: 1000 blocks / 500KB
per request; pagination max page_size 100.

Critical scoping behavior (SECONDARY, consistent): the user must
explicitly share each page/database with the integration in the Notion
UI; the integration cannot see the whole workspace. A 404 on an existing
page almost always means it was not shared. Free API.

PRD fit: excellent. The share-per-page model is the closest thing to
explicit, granular, revocable consent in this survey: the user picks
exactly what the agent can touch; revocation is unsharing in Notion.
Every write is a discrete REST call, easy to log. Batch carefully
against the 3 req/s limit.

### Google Drive and Google Calendar APIs

Auth: standard OAuth 2.0 via Google Cloud Console, incremental scopes,
refresh tokens with offline access.

Scope tiers (VERIFIED tier assignment, developers.google.com restricted
scope verification doc): Drive `drive.readonly` is RESTRICTED (same
verification + CASA story as Gmail read scopes). Calendar scopes
(`calendar.readonly`, `calendar.events.readonly`, `calendar`) are
sensitive only: review, no CASA. The `drive.file` scope (per-file access
to files created or opened by the app) is reported as non-sensitive but
this is UNVERIFIED against Google's own page.

Quotas (VERIFIED via Google docs transcriptions): Drive 1,000,000
units/min/project, 325,000/min/user/project, 1 TB egress/day; per-call
costs (files.get 5, files.list 100, downloads 200). Calendar: 10,000
requests/min/project, 600/min/user/project. Far above personal-agent
needs.

Agent operations: Drive `files.list` with `q` search, `files.get`,
`files.export` (Docs/Sheets to text), changes feed, comments. Calendar
`events.list` (time-bounded), `events.insert`, `events.patch`/`delete`,
freebusy. All plain HTTPS REST, fine from Expo.

PRD fit: mixed. Granular scopes, incremental consent, user-revocable,
easy auditability. But `drive.readonly` being RESTRICTED makes Drive the
most expensive connector to ship legitimately: consider `drive.file` or
file-picker-mediated per-file grants as lower-friction alternatives, and
decide whether the assessment is worth it. Calendar (sensitive only) is
the easier win: `calendar.events.readonly` plus `calendar.events` with
standard verification.

## 5. MCP servers as connector fast-path

### Server landscape

Official reference repo (VERIFIED, README opened): only 7 reference
servers remain maintained (`everything`, `fetch`, `filesystem`, `git`,
`memory`, `sequentialthinking`, `time`). None are personal-app
connectors. 14 servers were archived to `servers-archived` (github,
slack, gdrive among them) with no security guarantees; the README warns
they are reference implementations, "not production-ready solutions".
Discovery now points at registry.modelcontextprotocol.io.

Vendor first-party remote servers (SECONDARY unless noted): Google, 8
official remote MCP servers in Developer Preview (Gmail at
`gmailmcp.googleapis.com/mcp/v1`, Drive, Docs, Sheets, Slides, Calendar,
Chat, People). Critical detail: Gmail scopes are `gmail.readonly` +
`gmail.compose` only, so it can search, read, label, and create drafts,
but has NO send tool (deliberate). Setup cost is high: own GCP project,
API enablements, own OAuth consent screen, Developer Preview enrollment.
No pricing or GA date published. Notion: official hosted
`https://mcp.notion.com/mcp`, OAuth-only (static tokens rejected),
Streamable HTTP. Slack: official `https://mcp.slack.com/mcp`, GA since
2026-02-17 (SECONDARY). GitHub: `github/github-mcp-server` (SECONDARY).
Todoist, Atlassian, Asana, Sentry also host official servers
(SECONDARY). Community servers exist for Gmail, Calendar, full
Workspace, Outlook, X, but trust signals are thin: no independent
security audit found for any; stars and registry namespace ownership are
the main signals. A large share of community servers are stdio-only.

### Transport and auth state (2026)

Spec revision 2026-07-28 (VERIFIED via spec mirrors and the TypeScript
SDK changelog): HTTP+SSE (old two-endpoint transport) is deprecated with
a minimum 12-month window (removal earliest mid 2027); SSE survives only
as a response encoding inside Streamable HTTP. New work targets
Streamable HTTP only; stdio is unchanged as the local-process transport.
Headline 2026-07-28 changes: stateless core (no session id, no
initialize handshake), mandatory `server/discover` RPC, every result
carries `resultType`, Roots/Sampling/Logging deprecated.
Interop reality (SECONDARY, consistent across three sources): the
deployed ecosystem floor is still the older protocol; a single-era
client cannot talk to the other era. Design for the version matrix, not
the latest spec.

Auth (VERIFIED via spec mirrors and SDK changelog): MCP servers are
OAuth 2.1 Resource Servers; servers MUST publish RFC 9728 Protected
Resource Metadata; clients MUST use it for AS discovery and send RFC
8707 `resource` indicators (tokens audience-bound to that server).
Dynamic Client Registration is deprecated in favor of Client ID Metadata
Documents (CIMD); no per-provider client secret to store, which is good
news for mobile.

### Mobile viability (Expo / React Native)

stdio is a non-starter on mobile: iOS/Android apps cannot spawn
subprocesses, so every stdio-only community server is unreachable
directly from the app. Only remote Streamable HTTP servers are viable
on-device.

The stock `@modelcontextprotocol/sdk` can work on RN but is not plug
and play. Two concrete data points (SECONDARY): **cairn**
(ddutchie/cairn, Jul 2026) confirmed end-to-end on-device against an
OAuth MCP server using the stock SDK Client + StreamableHTTPClient
transport with `expo/fetch` injected, deep-link OAuth via
`expo-web-browser`, CIMD registration, PKCE via an `expo-crypto` shim,
and a SecureStore-backed OAuth provider. **Cherry Studio** publishes
`@cherrystudio/react-native-streamable-http`, a drop-in RN transport,
because the stock transport "relies on browser-specific APIs that don't
work properly in React Native environments". `react-native-url-polyfill`
is needed because RN's built-in URL mangles OAuth discovery paths.

OAuth on mobile is workable but per-vendor: deep-link redirect flow,
CIMD avoids secrets, tokens in SecureStore. Providers requiring
pre-registered redirect URIs may not connect from mobile; Google preview
tokens reportedly need re-auth roughly weekly (SECONDARY).

Background execution is the hard limit: iOS/Android kill long-lived
network streams when the app backgrounds, so streaming subscriptions
are effectively foreground-only; ambient polling must go through OS
background tasks. The stateless 2026-07-28 core helps: no session to
lose, reconnects are cheap.

Verdict: proven possible (one on-device confirmation plus one published
polyfill), requires polyfill surgery and per-vendor OAuth work,
foreground-only for streaming. Not speculative, not zero-config.

### Trust and vetting

OX Security "The Mother of All AI Supply Chains" (disclosed 2026-04-15,
SECONDARY): four attack families across the MCP SDK ecosystem,
including zero-click prompt injection (attacker content silently issuing
tool calls, confirmed in Windsurf/Cursor) and marketplace poisoning (9
of 11 audited registries serving unverified servers). 10+ CVEs.

Official registry moderation policy (VERIFIED, opened the doc): "quite
permissive"; removes only illegal content, malware, spam, and broken
servers; explicitly does NOT remove low-quality servers or servers with
security vulnerabilities. "Consumers should assume minimal-to-no
moderation." Trust is pushed to subregistries. Registry listing proves
namespace ownership, not security.

Recommended vetting policy for SHADOW-AI: allowlist-only server set;
prefer first-party remote servers over community; pin server versions
and digests and re-check on connect; human review of the tool list at
connect time and on any tool-list change; treat tool descriptions as
untrusted input (fence before model context); Sentinel approval gates
on all write tools; never stdio on-device; record server identity,
version, and digest in the hash-chained audit log with tokens redacted;
"add server" itself is a privileged action.

### Architecture options: direct vs via node

Option A, direct mobile-to-MCP-server: no relay, tokens stay on device
in SecureStore, matches the BYOK story, works today with official remote
OAuth servers, stateless spec makes reconnects cheap. Cons: one OAuth
flow per vendor; SDK polyfill surgery; the whole stdio-only community
ecosystem unreachable; background work crippled by OS limits;
per-vendor token lifecycle on the phone.

Option B, MCP servers on the SHADOW node over the existing pairing: the
node runs the full ecosystem (stdio servers, OAuth bridges, community
servers); one consolidated SHADOW-controlled tool surface to the phone;
the node holds refresh tokens and does background polling with always-on
power; phone-side code stays thin. Cons: the node becomes a privileged
proxy and high-value target; tokens live on the user's machine rather
than only on the phone (still local-first, weaker); node reachability
off-LAN needs a relay story; node-side tool calls must be audited as
first-class entries.

Recommendation: hybrid. Phase 1: direct from mobile for first-party
OAuth remote servers (Google, Notion, Slack, Todoist, GitHub) using the
cairn recipe. Phase 2: a node-hosted MCP gateway for stdio-only
community servers and all ambient/background polling, presented as a
single "node connector" over the existing pairing with its own Sentinel
policy.

## 6. Cross-cutting architecture decisions

1. **Identity separation is the PRD-safe default.** Telegram bot,
   Discord bot, Slack bot token all act as a distinct app identity, not
   the user. Only Slack xoxp and Telegram MTProto user sessions act AS
   the user; gate those behind explicit per-action approval, default
   off.
2. **Inbound needs a relay.** Telegram webhooks, Discord Gateway, Slack
   Socket Mode, WhatsApp webhooks, GitHub webhooks all assume an
   always-on endpoint. A phone cannot hold these reliably. Design: the
   SHADOW node (or a minimal per-user relay) holds the sockets/webhooks
   and forwards to the app via push; tokens stay in the app's
   SecureStore; the relay holds only short-lived session credentials.
3. **Polling over webhooks for ambient work.** X mentions, Reddit inbox,
   IG conversations, Threads replies, GitHub notifications (304
   conditional polling), Gmail `history.list`: scheduled, user-enabled,
   budget-capped polling. Ambient defaults OFF per the PRD.
4. **Drafts-first execution.** Drafts need no approval to create (Gmail
   drafts.create, Notion page create, GitHub issue draft); sends, posts,
   merges, and messages go through the approvals inbox. Where a platform
   has no draft state (LinkedIn, Threads, X publish on call), the
   approvals inbox gates the API call itself.
5. **Per-connector OAuth grants in the vault.** Each connector owns its
   own grant, stored per-connector in expo-secure-store, with
   per-connector revoke that deletes the local token AND calls the
   provider revoke endpoint where one exists (Notion
   `/v1/oauth/revoke`, Google revocation, Slack `auth.revoke`).
   Settings show granted scopes, last-used, and a working Revoke.
6. **Shared rate-limit discipline.** One backoff/queue layer honoring
   `Retry-After`/`retry_after` everywhere (Telegram 429, Discord 429,
   Notion 429/529, Drive 403/429 with exponential backoff, X
   pay-per-use caps).
7. **ToS red lines encoded as policy.** No scraping where an API exists
   (LinkedIn, Reddit, Meta prohibit it); no automated posting to
   arbitrary Reddit subreddits; no mass follow/DM on X; TikTok public
   posting blocked until the app audit passes; personal Facebook timeline
   and personal Messenger are unavailable and must not be faked with
   browser automation; no unofficial WhatsApp personal-number
   automation.
8. **Google verification strategy.** The single biggest cost question:
   whether Gmail/Drive restricted scopes trigger CASA for a local-only
   app. Until settled in writing: ship Gmail send-only (`gmail.send`,
   sensitive tier) and Calendar (sensitive tier); defer Gmail/Drive read
   scopes or offer them as BYO-OAuth advanced options.

## 7. Consolidated UNVERIFIED register

These items must be confirmed before they drive product or engineering
commitments:

- Whether a purely local-first app with no server transit of restricted
  Google data is exempt from CASA.
- Exact CASA assessor pricing (Google publishes none).
- X pay-per-use prices and DM scope gating (docs.x.com unreachable).
- Microsoft's exact permission descriptions (permissions reference page
  returned 403); Graph throttling figures (corroborated secondary).
- LinkedIn token lifetime and refresh behavior (60 days, no refresh:
  secondary).
- Meta Valid OAuth Redirect URI rules for Threads custom schemes;
  Instagram DM 20-message limit; TikTok unaudited-app user cap.
- Reddit manual-approval timelines and commercial pricing (secondary).
- Telegram Business-connection bot flow; Slack Socket Mode plan
  restrictions; WhatsApp coexistence availability for direct developers.
- Notion OAuth scope strings against Notion's own docs; Google
  `drive.file` scope tier against Google's own page.
- MCP vendor server endpoints and GA dates (GitHub, Slack, GitLab,
  Asana, Todoist: secondary); Google Workspace MCP servers still in
  Developer Preview (sources Jul-Aug 2026, may have moved).
- The "MCP servers MUST NOT transit tokens" one-hop quote (secondary
  research doc, not the spec text).
- Agentic AI Foundation formation details (secondary only).

## 8. Connector opportunities

Prioritized by leverage for SHADOW-AI. PRD fit notes how each maps to
explicit consent, local-first, revocable autonomy, and auditability.
Effort: S (days), M (1-3 weeks), L (month+). [DECISION] marks items
needing Inan's product call before implementation.

1. **GitHub connector: device flow, read-only by default.** GitHub App
   with the RFC 8628 device flow, REST-first with GraphQL dashboard
   batches, conditional notification polling, write permissions only on
   user opt-in. Track 3. PRD fit: consent-first auth UX, app-badge
   attribution in audit logs, granular permissions. Effort: M.
2. **Gmail send-only connector.** `gmail.send` (sensitive tier, no
   CASA): drafts via the API, every send through the approvals inbox.
   Track 1. PRD fit: no auto-send, minimal scope, incremental consent.
   Effort: S. [DECISION]: whether to pursue Gmail read scopes now or
   defer until the CASA question is settled in writing.
3. **Google Calendar connector.** `calendar.events.readonly` plus
   `calendar.events` (sensitive tier, standard verification): agenda
   reads, event creation behind approval. Track 1/4. PRD fit:
   granular scopes, easy auditability. Effort: S.
4. **Notion connector.** OAuth integration with share-per-page grants:
   search, read, create and update pages behind approval. Track 4. PRD
   fit: the consent gold standard in this survey; revocation is
   unsharing. Effort: S/M.
5. **Slack connector (bot token default).** Read channels and DMs the
   bot is invited to; post and react behind approval; xoxp "act as
   user" as an explicit opt-in. Track 4. PRD fit: identity separation,
   per-conversation-type scopes. Effort: M. [DECISION]: personal vs
   work workspace targeting and the xoxp opt-in policy.
6. **Telegram bot connector.** Notify the user and accept commands via a
   bot the user starts; no impersonation possible. Track 4. PRD fit:
   inherently scoped, free, auditable. Effort: S. Needs a small relay
   for inbound webhooks or poll from the node.
7. **Outlook connector via Microsoft Graph (BYO-OAuth).** Each user
   registers their own free Entra app; `Mail.Read` + `Mail.Send` to
   start, `Mail.ReadWrite` later. Track 1. PRD fit: no assessment tax,
   per-permission consent. Effort: M. [DECISION]: BYO-OAuth onboarding
   friction vs a shared SHADOW-AI client ID with publisher
   verification.
8. **Threads connector.** Post to the user's own profile and keyword
   search (500/week cap) for listening, all behind approval. Track 2.
   PRD fit: explicit per-account OAuth, free. Effort: S/M.
9. **Reddit connector.** Read subreddits and inbox, post to own profile
   or chosen subreddits behind approval. Track 2. PRD fit: best free
   read connector; per-scope consent. Effort: S/M. [DECISION]: whether
   the manual access approval wait (2-4 weeks) is acceptable now.
10. **X connector (budget-guarded).** Mentions and timeline reads with a
    Sentinel-lite spend cap; drafts free to prepare; posts behind
    approval. Track 2. PRD fit: per-account consent; cost meter needs
    the budget guard. Effort: M. [DECISION]: monthly spend budget and
    whether pay-per-use is acceptable at all.
11. **MCP client for first-party remote servers.** Streamable HTTP MCP
    client on the cairn recipe (expo/fetch injection, deep-link OAuth,
    CIMD, SecureStore tokens), allowlist-only servers (Google, Notion,
    Slack, GitHub, Todoist), pinned versions, tool descriptions fenced
    as untrusted. Track 5. PRD fit: extends capability under the audit
    log with explicit per-server consent. Effort: M/L. [DECISION]: MCP
    scope and the trust/vetting policy for third-party servers.
12. **Node-hosted MCP gateway.** The SHADOW node runs the full MCP
    ecosystem (stdio community servers, OAuth bridges) and all
    ambient/background polling, exposed to the app as one "node
    connector" over the existing pairing with its own Sentinel policy.
    Track 5. PRD fit: ambient work supervised where the node can see
    it; phone trust surface stays minimal. Effort: M/L. [DECISION]:
    node roadmap priority and the off-LAN relay story.

Cross-cutting [DECISION] items for Inan: connector order for v1
(recommended: GitHub, Gmail send-only, Calendar, Notion); OAuth
strategy (per-connector grants in the vault is the default; BYO-OAuth
for Google/Microsoft as an advanced path); token handling stays
on-device (SecureStore) with no server transit, which is also what keeps
the Google CASA question open in our favor; inbound relay ownership
(node vs minimal hosted relay).
