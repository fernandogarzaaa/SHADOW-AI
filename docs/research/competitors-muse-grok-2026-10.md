# Competitor Research: Meta Muse and xAI Grok (consumer products), October 2026

Date: 2026-10-26. Scope: the user-facing products only. Developer APIs
(Meta Model API, Muse Spark models, xAI REST API, model slugs and token
prices) are covered in `personal-agent-landscape-2026-09.md` and are not
repeated here.

Labels:
- **VERIFIED**: confirmed on a primary source (official site, help center,
  official docs, official blog, or the official App Store listing) fetched
  in this session. The URL is given.
- **UNVERIFIED**: press, third-party blogs, or claims that conflict with
  or were missing from the primary sources.

Sources that blocked fetching in this session (403/429): x.ai/news index,
x.ai/changelog/bot, x.ai/legal/faq, help.x.com, grok.com/plans (empty
shell), ai.meta.com/muse (empty shell), muse.ai (auth redirect), CNBC.
Claims that depend only on those pages are marked UNVERIFIED.

Naming note: xAI's own pages use "SpaceXAI" and "SpaceXSI" in places, and
the Grok Bot docs say Bot computers "run in Cursor's cloud" and use Cursor
sign-in. Third-party sources say SpaceX acquired xAI in early 2026
(UNVERIFIED). Grok Bot is effectively a joint xAI/Cursor product.

---

## 1. Meta Muse (consumer personal agent)

### 1.1 Core experience and UX

- **VERIFIED** Launched Sep 8, 2026 (post updated Sep 30), rolling out in
  the US on iOS, Android, and muse.ai, "coming soon to AI glasses."
  Reachable in the Muse app or directly in WhatsApp "like messaging another
  person." https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/
- **VERIFIED** Goal-first UX: you share a goal, Muse builds a personalized
  plan, coordinates time and resources, and "turns long-term goals into
  action plans." It keeps working after the app is closed and comes back
  when something changes or approval is needed. (same URL)
- **VERIFIED** Proactivity: it "can make suggestions unprompted" and acts
  on details you mentioned only once (example: saved Instagram recipe reel
  becomes a grocery list; remembering friends' dietary restrictions when
  sending dinner invites). (same URL)
- **VERIFIED** Memory with a user "forget" command. (same URL)
- **VERIFIED** Customization: users name the agent and shape its tone.
  App Store listing: https://apps.apple.com/us/app/muse-from-meta/id6760173601
- **VERIFIED** Voice: long-form voice mode where "Muse gets work done in
  the background while you're still talking"; voice is designed by
  description ("faster, slower, or even a specific accent"). Muse Realtime
  Avatar turns the voice into an expressive interactive avatar (research
  release, no date). https://www.meta.com/blog/meta-connect-2026-everything-we-announced/
- **UNVERIFIED** Real-time video chat with a user-created avatar, timing
  unspecified (TechCrunch, https://techcrunch.com/2026/09/23/everything-new-coming-to-metas-ai-agent-muse/).
  Reviewers report weak audio input quality and inconsistent voice latency
  (DataCamp, https://www.datacamp.com/blog/muse-agent).
- **VERIFIED** A Feed exists: App Store v13.x (about Oct 24-25, 2026) adds
  a "Feed widget." **UNVERIFIED** detail: the feed aggregates updates from
  connected Facebook/Instagram accounts and web articles, and the WhatsApp
  version lacks the feed and an "ideas" tool (search-result summaries of
  third-party guides; not on Meta pages fetched).
- **UNVERIFIED** Onboarding requires adding a payment card even on the free
  tier, then connecting apps one at a time with per-app access levels
  (DataCamp). A usage meter warns before free usage runs out (DataCamp).

### 1.2 Agentic capabilities

- **VERIFIED** Runs on "Muse Secure VM", a dedicated per-user virtual
  machine holding the agent and the user's data, with its own browser. It
  can open a browser, fill forms, and "negotiate on a person's behalf."
  https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/
- **VERIFIED** App Store use cases: scheduling conflicts, reservations,
  reminders, follow-ups, price comparison and price-drop tracking,
  purchases after approval, expense tracking, subscription audits,
  unfamiliar-charge flags, savings goals, workout/meal plans from health
  data, sleep monitoring, trip planning, small-business insights from
  Instagram Business, Facebook Pages and Meta ad accounts.
  https://apps.apple.com/us/app/muse-from-meta/id6760173601
- **VERIFIED** Connectors named on primary pages: email (read-only or read
  and send is user-selectable), calendar, Instagram, Facebook,
  health/fitness, finances; Asana, Canva, Dropbox, Figma, QuickBooks,
  GitHub, Klaviyo, Zoom, Meta ad accounts, Granola, Notion (App Store
  v10.0, Oct 7); Walmart, Best Buy, Shopify catalogue, Shop Pay, PayPal,
  Instacart, Box, Expedia "coming soon" (Connect post). 1Password planned.
- **UNVERIFIED** "40+ native integrations including every Google Workspace
  app" plus Zapier for 9,000+ apps (search summary of third-party guides).
  Developer connector platform received 1,500+ applications in under a week
  (TechCrunch).
- **VERIFIED** Payments: checkout through Link by Stripe with one-time-use
  cards so real card details stay hidden; Link purchase protections apply.
  (Meta launch post)
- **VERIFIED** Mac computer use: "With your permission, Muse can now drive
  any app on your Mac," and continues "on all the tasks you've lined up"
  after you walk away. Muse will get its own email address (forward or CC
  it into threads). https://www.meta.com/blog/meta-connect-2026-everything-we-announced/
- **VERIFIED** Approvals: asks before sensitive actions (sending email,
  purchases, canceling, spending). Activity log; connectors revocable.
  (launch post, App Store)
- **UNVERIFIED** Recurring/scheduled tasks inside Muse. Meta's older Meta
  AI app got recurring tasks and daily briefings on Jul 24, 2026 (Reuters
  via https://qz.com/meta-ai-daily-briefings-recurring-tasks-automation-072426);
  a third-party Oct 12 tutorial shows scheduling recurring tasks in Muse.
  No Meta primary page for Muse scheduling was found.
- **UNVERIFIED** "Muse network": your Muse working with friends' and
  family's Muses and with businesses' agents (Zuckerberg on the Q3 call,
  https://techcrunch.com/2026/10/21/meta-says-muse-has-over-10m-users-with-shopping-a-top-activity/).

### 1.3 Devices and surfaces

- **VERIFIED** iPhone (iOS 18+), iPad (added v10.0, Oct 7), Android, web
  (muse.ai), WhatsApp, Mac desktop app. App Store v13.1 adds "iPhone Duo"
  support. No Apple Watch support listed. (App Store, Connect post)
- **VERIFIED** AI glasses "in the coming months," activated by saying your
  agent's name, and able to act on what you are looking at. Muse Charm, a
  pocket voice device, "more to share later this year" (no price or date).
  (Connect post)
- **UNVERIFIED** Ray-Ban Meta Audio glasses shipping Oct 13 at $349; Muse
  Charm ships in December (search summaries of Connect coverage).

### 1.4 Pricing

- **VERIFIED** Free "with a usage limit"; Power $20/month with 500M Muse
  tokens per week; Maximum $100/month with 3B Muse tokens per week; monthly
  auto-renew; limited testing, not available in all locations; 18+; Meta
  account required. https://www.meta.com/help/subscriptions/1021145227643680/
- **VERIFIED** App Store v12.0 (Oct 17) lets users buy additional tokens
  when they run out. Tiers differ by allowance, not features.
- **UNVERIFIED** Free tier about 100M tokens/week (traced to a Zuckerberg
  post, not the help page). Meta plans a cut of commerce transactions
  (TechCrunch, Oct 21). Muse Wonder model "will roll out first to
  subscribers" (VERIFIED, https://about.fb.com/news/2026/10/introducing-muse-wonder-models/).

### 1.5 Privacy model

- **VERIFIED** Fully cloud. A separate "Sentinel" agent, isolated at system
  level on the same VM, gates egress: "Nothing Muse does reaches the
  internet unless the Sentinel approves it." Credentials go into secure
  storage that Muse uses without seeing; Muse cannot see passwords typed
  into the browser. "Complete audit trail of past and planned actions."
  Training opt-out available. Conversations and VM data not shared with
  Meta's ad systems. Muse Confidential VM (encrypted with a key only the
  user holds) promised "later this year." (Meta launch post)
- **VERIFIED** App Store privacy label lists Health & Fitness, Sensitive
  Info, Financial Info, Location (precise, may be used while closed),
  Contacts, emails/texts, browsing history as linked to identity, with
  several categories listed for third-party advertising. 18+ rating.
- **UNVERIFIED** Training on Muse data is on by default; deleting a chat
  does not erase what Muse learned ("Muse may still remember information
  it learned from what you deleted"); a macOS zero-day exposed Muse and
  its connectors weeks after launch (PCWorld, via search summary). Users
  complained of unauthorized access to personal messages, disputed by
  Meta (search summary of Oct coverage).

### 1.6 Notable Sept-Oct 2026 launches

- Sep 8: Muse launch (VERIFIED). Sep 20-23: web navigation, form filling,
  goal tracking (App Store v8.x, VERIFIED). Sep 23: Connect (voice design,
  Realtime Avatar, Mac computer use, own email, glasses, Charm, commerce
  connectors; VERIFIED). Oct 7: business connectors and iPad (VERIFIED).
  Oct 12: Muse Wonder models, "Active Memory" and "Active Focus"
  capabilities, coming to Muse subscribers first (VERIFIED). Oct 17: token
  purchases (VERIFIED). Oct 20-21: 10M+ users, ~25% of set-up users daily,
  shopping the top activity (UNVERIFIED, TechCrunch). Oct ~24: Feed widget,
  easier in-chat shopping (VERIFIED, App Store).

---

## 2. xAI Grok (consumer assistant, Grok Bot, companions)

xAI now ships two consumer agent products: the **Grok app** (chat, voice,
Imagine, connectors, Automations, companions) and **Grok Bot** (always-on
"AI teammates" on a persistent cloud computer).

### 2.1 Grok app: core experience

- **VERIFIED** Surfaces: iOS, Android, grok.com, synced. Features: chat,
  voice ("Talk to Grok"), Imagine image/video, file uploads (PDF, images,
  spreadsheets, code, audio), connectors.
  https://docs.x.ai/grok/overview
- **VERIFIED** App Store listing: deep web research, real-time X and web
  access including advanced X search, voice mode with adjustable
  conversation styles, Imagine (text-to-image, short videos with sound,
  photo-to-video, voice-driven generation, editing), and "context
  transfer" to import conversations and context from other AI tools.
  iOS 17+, iPadOS 17+, visionOS 1.0+; no Watch or Mac listed; 16+ rating.
  Every Sep-Oct release note reads "Improvements to Chat, Voice and
  Imagine." https://apps.apple.com/us/app/grok/id6670324846
- **VERIFIED** Companions "are available on the iOS app only," with no
  plans for web or Android. https://docs.x.ai/grok/faq
- **UNVERIFIED / CONFLICTING** Third-party sites say xAI removed the
  animated Companions tab from the Grok app on Sep 1, 2026 and moved
  animated companions (Ani, Mika, Valentine, Rudi) to a separate app called
  "Animates," with personalities kept in text chat
  (https://aiinsightsnews.net/grok-ani-gone-what-happened/). This
  conflicts with the current xAI FAQ above; not resolved.
- **UNVERIFIED** Memory on by default with view/edit/delete, plus reusable
  "Skills"; not available in parts of the EU/UK (Chorus and vendor blogs;
  xAI's 2025 memory announcement is older than this scope).

### 2.2 Grok app: agentic capabilities

- **VERIFIED** Automations (Jul 16, 2026): scheduled jobs (once, daily,
  weekdays, weekly, monthly, yearly, in user timezone) for everyone; email
  triggers (fire when an incoming email matches sender/recipient/subject
  filters, with that email as context) on SuperGrok; @-mention a connector
  to use it every run; "Run now"; templates; create from chat. Each run is
  a full conversation saved to run history you can reopen and continue.
  Delivery by email, app notification, both, or neither. Pause, resume,
  edit, delete. https://x.ai/news/grok-automations
- **VERIFIED** Connectors, available to all users: Gmail & Google
  Calendar, Google Drive, OneDrive, Outlook Mail & Calendar, Microsoft
  Teams, SharePoint, Salesforce (create/update); a broader OAuth catalog at
  grok.com/connectors; custom remote MCP servers (must be publicly
  reachable; local servers need a tunnel). No per-action approval prompts
  are described. https://docs.x.ai/grok/connectors

### 2.3 Grok Bot (consumer and team "AI teammates")

- **VERIFIED** Launched in beta Aug 11, 2026: always-on Bots that finish
  tasks end to end and return only for approval; a "chief of staff" Bot
  coordinates specialist Bots; Bots join group chats with people and each
  other; teach-by-demonstration; memory of preferences and corrections;
  nudges on stalled threads. https://x.ai/news/introducing-grok-bot
- **VERIFIED** Aug 26: included with SuperGrok, SuperGrok Plus, SuperGrok
  Heavy, Cursor Pro/Pro+/Ultra, Cursor Teams; own usage pool separate from
  Grok/Cursor usage. https://x.ai/news/grok-bot-more-plans
- **VERIFIED** Surfaces: desktop app (macOS, Windows, Linux), iPhone,
  iPad, Android; input by typing, dictation, or live voice chat; on X, tag
  `@bot` in a post to start a task (public reply only confirms receipt;
  results stay in the app; not available for accounts in the EU, UK,
  Australia, Iceland, Liechtenstein, Norway).
  https://docs.x.ai/grok-bot/overview, https://docs.x.ai/grok-bot/tag-on-x
- **VERIFIED** Persistent cloud computer per user (browser, terminal,
  files) shared by all of the user's Bots; live preview of clicks and
  typing; user takes over for passwords, 2FA, CAPTCHAs, payments, then
  says "I'm done"; masked secure-secret requests hidden from the model;
  OAuth tokens held on the connector backend, never on the computer;
  optional local computer access with Ask every time (default) / Always
  allow / Never allow. https://docs.x.ai/grok-bot/computer-and-apps
- **VERIFIED** Approvals: Allow once / Always allow (saves a rule) / Deny;
  "Auto Review", an independent review model, checks risky actions (shell,
  app calls, computer use, automation writes, delegation) and can allow,
  escalate, or deny; personal "Ask first" rules beat "Allow automatically."
  Auto Review does not cover memory writes or most settings changes.
  https://docs.x.ai/grok-bot/security
- **VERIFIED** Skills and routines: save a workflow as a skill, or record
  up to 10 minutes of screen to "Teach a task"; routines on time triggers
  or event triggers (Slack message, GitHub notification); up to 50
  routines per Bot, 20 run records kept, at least 5 minutes apart; routines
  pause after long inactivity; guidance to require approval before
  sending, purchasing, deleting, publishing.
  https://docs.x.ai/grok-bot/skills-routines-and-automations
- **VERIFIED** Mobile: notifications for results, questions, approval
  requests; edit then send or discard Bot-prepared email/Slack drafts;
  iOS share sheet (photos, files, links, text; Android text only); routine
  schedule, next run and run history viewable on phone, edits on desktop.
  No calendar/contacts/native-app integration documented.
  https://docs.x.ai/grok-bot/mobile
- **VERIFIED** Grok Voice 3.0 (Oct 14) powers Grok Bot's voice mode; in
  Tesla vehicles drivers can ask about calendar, email, or have Grok Bot
  order coffee or book dinner. https://x.ai/news/grok-voice-3
- **UNVERIFIED** Oct 22, 2026: Grok Bot gained direct integration with
  native iOS/Android phone apps such as calendar and contacts, rolling out
  gradually (basenor.com and fourweekmba.com; both blocked fetch; not in
  the xAI docs fetched).
- **UNVERIFIED** Oct 20: IncidentWatch and IncidentSweep support-team
  features (releasebot summary of x.ai/news/incident-sweep; enterprise
  focused).

### 2.4 Pricing

- **VERIFIED** The X Subscription (Oct 12, 2026): Free $0 (daily Grok,
  Cursor starter allowance), Plus $8 (more Grok/Cursor usage, checkmark,
  fewer ads), Premium $30 (SuperGrok + Cursor Pro + X Premium+, "previously
  $90/month combined", 4x Plus usage), Super $100 (15x Plus), Ultra $200
  (50x Plus). Shared Grok-model usage pool across Grok and Cursor; overage
  via top-ups at API list prices; team seats at the same prices.
  https://x.ai/news/x-subscription
- **VERIFIED** Grok app in-app purchases: SuperGrok Lite $10, SuperGrok
  $30, SuperGrok Plus $100, SuperGrok Heavy $300, a $300 SuperGrok item
  (likely annual), Extra Usage Credits $5/$20/$50/$100.
  https://apps.apple.com/us/app/grok/id6670324846
- **VERIFIED** One shared weekly usage pool across Grok products; credits
  used after the pool is exhausted, expire after a year, $5 minimum, web
  only; free Chat and Voice limits separate; Imagine output watermarked;
  720p video falls back to 480p after the tier cap. https://docs.x.ai/grok/faq
- **UNVERIFIED** How the X Subscription tiers map onto the older
  SuperGrok tiers (both are live in parallel); free-tier caps; Heavy promo
  pricing.

### 2.5 Privacy model

- **VERIFIED** Fully cloud. Deleted chats and files are removed "within
  standard retention windows" unless held for legal, compliance, or safety
  reasons; account deletion restorable within 30 days; data controls under
  Settings > Data Controls. https://docs.x.ai/grok/faq
- **VERIFIED** App Store privacy label for Grok lists only contact info,
  identifiers, and diagnostics (analytics and app functionality).
- **VERIFIED** Grok Bot: per-user hardware-isolated computers in the US;
  connector tokens on Cursor's backend; no training on data with Privacy
  Mode; DPA deletion within 30 days of written direction; Enterprise-only
  audit logs and opt-in Action Recording with 90-day retention; no
  per-org retention policy; encryption at rest not described.
  https://docs.x.ai/grok-bot/security
- **UNVERIFIED** Private Chat not used for training and deleted within 30
  days; training opt-out toggle "Improve the model"; feedback ratings may
  still be used for training; Grok on X has a separate X privacy setting
  (x.ai/legal/faq and help.x.com blocked; search snippets only, and the
  FAQ snippet is dated about 2025).

### 2.6 Notable Sept-Oct 2026 launches

- Sep 1: companions removal from Grok app (UNVERIFIED, conflicts with
  FAQ). Oct 12: The X Subscription bundle (VERIFIED). Oct 14: Grok Voice
  3.0 powering Grok Bot voice and Tesla requests (VERIFIED). Oct 20: Grok
  Bot IncidentWatch/IncidentSweep (UNVERIFIED). Oct 22: Grok Bot native
  phone-app integration (UNVERIFIED). Grok Build CLI v1.0.54-1.0.67, Oct
  12-21 (developer tool, out of scope).

---

## 3. Head-to-head summary

| Dimension | Meta Muse | xAI Grok app + Grok Bot | Shadow today |
|---|---|---|---|
| Where the agent runs | Per-user cloud VM | Per-user cloud computer (Cursor cloud) | User's own computer (Shadow Node) |
| Egress control | Sentinel agent approves all egress | Auto Review model + rules; Enterprise network allowlists | Approval gate, SSRF guard, audit log |
| Approvals UX | Ask before sensitive actions | Allow once / Always allow (rule) / Deny; Auto Review | Per-request approval |
| Scheduling | Background goals; scheduling UNVERIFIED | Automations (time + email triggers), Bot routines (time + Slack/GitHub events) | Time-based scheduled tasks, reminders |
| Delivery | Push, WhatsApp, Feed widget | Email, push, both, neither; run history as conversations | Feed, dashboard |
| Messaging surfaces | WhatsApp, own email address (coming) | `@bot` on X, group chats with Bots | App and web dashboard |
| Desktop control | Mac computer use | Optional local computer, per-command policy | Not offered |
| Voice | Background voice, voice design, avatar | Voice mode, Voice 3.0 in Bot and Tesla | Not offered |
| Payments | Link one-time cards, Shop Pay, PayPal | Not described | Not offered |
| Price | Free / $20 / $100 + token top-ups | Free / $8 / $30 / $100 / $200 (X bundle) | BYOK |
| Privacy | Cloud; training opt-out; Confidential VM promised | Cloud; standard retention windows | Local-first, encrypted memory |

The structural gap for both competitors: **all data and credentials live in
the vendor's cloud**. Meta's own answer (Confidential VM, user-held key) is
announced but unshipped. Shadow already has the property Meta is promising.

---

## 4. Features Shadow lacks, ranked by user value

Ranked by everyday value to a single user, weighted toward what fits a
local-first, approval-gated design. Effort is a rough S/M/L.

1. **Event-triggered automations, especially email triggers.** Grok runs
   an automation when an incoming email matches sender/recipient/subject
   filters, with that email as context; Grok Bot adds Slack/GitHub event
   triggers. Shadow's scheduled tasks are time-only. Add an "on new email
   matching X" trigger (and later webhook triggers) to scheduled tasks, with
   output gated by the existing approvals. VERIFIED (x.ai/news/grok-automations,
   docs.x.ai/grok-bot/skills-routines-and-automations). Effort M.
2. **Run history as reopenable conversations plus per-task delivery
   choice.** Each Grok automation run is a saved conversation you can
   continue, and the user picks email / push / both / neither. Shadow
   should store each scheduled run as a thread and let the user choose
   push, feed-only, or silent. VERIFIED (x.ai/news/grok-automations). Effort S/M.
3. **Three-way approvals with saved rules (Allow once / Always allow /
   Deny) and "Ask first" overrides.** Grok Bot turns "Always allow" into a
   reusable rule and lets "Ask first" rules always win. Removes approval
   fatigue while keeping consent explicit and auditable. Pair with push
   notifications carrying approve/deny actions (Grok Bot and Muse both
   notify on approval requests). VERIFIED (docs.x.ai/grok-bot/security,
   docs.x.ai/grok-bot/mobile). Effort M.
4. **Goal-to-plan agent that keeps working and checks back.** Muse's
   headline UX: share a goal, get a plan, it advances in the background and
   returns on change or approval. Shadow has Goals and scheduled tasks but
   not an agent that decomposes a goal into tasks and schedules its own
   follow-ups. VERIFIED (about.fb.com Muse launch post). Effort L.
5. **Voice mode that keeps working while you talk.** Both products ship
   voice; Muse explicitly runs tasks in the background during a voice
   conversation, and Grok Bot accepts dictation and live voice from the
   phone. On-device STT/TTS would keep Shadow's privacy story. VERIFIED
   (meta.com Connect post, docs.x.ai/grok-bot/mobile). Effort M.
6. **A messaging channel and an agent email address.** Muse works inside
   WhatsApp and will get its own email address you can CC or forward to;
   Grok Bot accepts `@bot` tasks from X. For Shadow, the realistic version
   is a forward-to address or a Telegram/iMessage-style bridge into the
   node's inbox (WhatsApp Cloud API constraints are in the September doc).
   VERIFIED (meta.com Connect post, docs.x.ai/grok-bot/tag-on-x). Effort M.
7. **Share-sheet capture into the agent.** Grok Bot's iOS share sheet
   sends photos, files, links, and text into a chat; Muse turns a saved
   Instagram reel into a grocery list. A Shadow share extension that drops
   items into memory or the inbox is cheap and high-frequency. VERIFIED
   (docs.x.ai/grok-bot/mobile; Muse example from the launch post). Effort S/M.
8. **Teach a task by demonstration / saved skills.** Grok Bot records up
   to 10 minutes of screen to draft a reusable skill, and saves completed
   processes as named skills invoked with `/`. Shadow could start with
   "save this conversation's steps as a skill" (no screen recording).
   VERIFIED (docs.x.ai/grok-bot/skills-routines-and-automations). Effort M.
9. **Remote MCP connectors.** Grok lets any user add a custom MCP server;
   Muse accepts hosted MCP endpoints for its connector platform. Shadow
   runs on the user's machine, so local MCP servers need no tunnel, which
   is a real advantage over Grok's public-internet requirement. VERIFIED
   (docs.x.ai/grok/connectors). Effort M/L.
10. **Watch the agent work, take over for sensitive steps.** Both run a
    browser in a VM the user can watch; Grok Bot hands control to the user
    for passwords/2FA/payments and resumes on "I'm done," and masks secrets
    from the model. Relevant if Shadow adds a local browser tool.
    VERIFIED (docs.x.ai/grok-bot/computer-and-apps; Muse launch post).
    Effort L.
11. **Context import from other assistants.** Grok's App Store listing
    advertises importing conversations and context from other AI tools.
    A ChatGPT/Claude export importer into Shadow memory is a strong
    switching aid. VERIFIED (apps.apple.com/us/app/grok/id6670324846).
    Effort S/M.
12. **Customizable persona (name, tone, designed voice).** Muse lets users
    name the agent and shape its tone, and design its voice by
    description; Grok has companions (iOS). VERIFIED (Muse App Store
    listing, Connect post, docs.x.ai/grok/faq). Effort S.
13. **Home-screen widget for the feed.** Muse v13.1 added a Feed widget.
    Shadow already has a daily feed; a widget surfaces it without opening
    the app. VERIFIED (Muse App Store version history). Effort S/M.
14. **Agent payments with one-time cards.** Muse's highest-engagement use
    is shopping via Link one-time cards. High value for Meta, but it adds
    regulatory and trust risk that conflicts with Shadow's drafts-first
    posture. VERIFIED (Muse launch post); usage data UNVERIFIED. Effort L.
    Treat as a later decision, not a near-term build.

Not recommended to copy: Muse's default training on agent data
(UNVERIFIED) and broad ad-linked data collection (VERIFIED App Store
label), and Grok Bot's single shared computer where every Bot sees every
credential (VERIFIED). Both are positioning openings for Shadow.

## 5. Open questions

- Muse scheduled/recurring tasks: no Meta primary source found.
- Muse Confidential VM ship date; Muse on glasses date; Muse Charm price.
- Grok companions: in the Grok iOS app (xAI FAQ) or moved to "Animates"
  (third parties)?
- Grok Bot native phone-app integration (Oct 22): not in xAI docs.
- Current Grok consumer privacy text (x.ai/legal/faq blocked this session).
