# Competitor research: Claude Duet and the Claude consumer baseline

Date: 2026-10-26
Scope: Anthropic's "Claude Duet" personal agent, plus what the current Claude consumer apps already offer as a personal assistant.

Legend:
- **VERIFIED**: stated on a primary Anthropic source (anthropic.com, claude.com, support.claude.com) fetched on 2026-10-26. URL given.
- **UNVERIFIED**: press, reviews or third-party reporting only. Not confirmed on an Anthropic page.

## Primary sources fetched

| # | Source | URL |
|---|--------|-----|
| P1 | "Introducing Claude Duet" (claude.com, 2026-10-21) | https://claude.com/resources/articles/claude-duet |
| P2 | "Claude Duet Safety, Privacy, and Security" (claude.com, 2026-10-23) | https://claude.com/resources/articles/claude-duet-safety-privacy-and-security |
| P3 | Claude Duet product / waitlist page | https://claude.com/product/claude-duet |
| P4 | Claude release notes | https://support.claude.com/en/articles/12138966-release-notes |
| P5 | Scheduled tasks support article | https://support.claude.com/en/articles/13854387 |
| P6 | Chat search and memory | https://support.claude.com/en/articles/11817273-use-claude-s-chat-search-and-memory-to-build-on-previous-context |
| P7 | "Claude Cowork and chat are one Claude" | https://support.claude.com/en/articles/16761823-claude-cowork-and-chat-are-one-claude |
| P8 | Use voice mode | https://support.claude.com/en/articles/11101966-use-voice-mode |
| P9 | Assign tasks from anywhere (Dispatch) | https://support.claude.com/en/articles/13947068-assign-tasks-from-anywhere-in-claude-cowork |
| P10 | Anthropic newsroom index (no Duet post there; announcement lives on claude.com) | https://www.anthropic.com/news |

Secondary sources (UNVERIFIED): MacRumors https://www.macrumors.com/2026/10/21/anthropic-claude-duet/ ; Every "Vibe Check" https://every.to/vibe-check/vibe-check-duet-anthropic-s-always-on-agent ; TechCrunch https://techcrunch.com/2026/10/22/claude-duet-app-is-anthropics-bet-on-agents/ ; CNBC https://www.cnbc.com/2026/10/21/anthropic-preview-of-claude-duet-personal-ai-agent-take-on-muse-dots.html ; 9to5Mac https://9to5mac.com/2026/10/21/anthropic-takes-on-chatgpt-dots-and-meta-muse-with-claude-duet/ . Only MacRumors and Every were fetched in full. The rest are cited from search-result snippets.

---

## 1. Claude Duet: what is actually known

### Status and name
- **Officially announced.** The official name is **Claude Duet**. It was announced on 2026-10-21 as a **research preview** of "a new app where Claude works as a proactive agent." VERIFIED (P1, P4)
- The announcement was posted on claude.com/resources, not on anthropic.com/news. The newsroom has no Duet post. VERIFIED (P10)
- Target users are "professionals and small business owners" with more on their plates than they can track. VERIFIED (P1)
- Press frames it as Anthropic's answer to Meta's Muse and OpenAI's Dots. UNVERIFIED (MacRumors, CNBC, 9to5Mac)

### Availability, surfaces and pricing
- Access is by **waitlist**, starting with **US Pro and Max subscribers**. Team and Enterprise are not included yet. VERIFIED (P1, P3)
- Surfaces are **standalone iOS and Android apps, plus claude.ai on the web**. It is a separate app from the main Claude app. VERIFIED (P1, P3)
  - Discrepancy: MacRumors says "web or a standalone Duet iOS app" and does not mention Android. The official pages list Android too. No desktop-native Duet app is mentioned.
- Duet has **no separate price**. It is included in Pro and Max and shares the plan's usage limits. Background checks and large tasks count against those limits. VERIFIED (P1, P3)
- Model: built around **Claude Opus 5.5**. VERIFIED (P1, P3)

### Capabilities
- **Proactive briefings.** Duet sends a short **morning brief** on important items across connected apps. It monitors those apps through the day and messages "only when attention is needed," checking **every few hours** to save plan limits. Users choose what they hear about and how often. VERIFIED (P1, P3)
- **One ongoing thread.** Users talk to Duet in a single thread, by text or voice. VERIFIED (P1, P3)
  - Every's reviewer says there is "no true voice mode, only transcription." UNVERIFIED
- **Task list.** Each task has its own page, and the user can steer it mid-task. VERIFIED (P2, P3)
  - Every reports recurring topics organized into "channels" and a live tally of open requests. UNVERIFIED
- **Memory, skills and connectors** carry over from the user's Claude account, so there is little setup. The "Search and reference chats" toggle also controls Duet's access to past chats. VERIFIED (P1, P6)
- **Actions and work products.** Duet schedules meetings and builds dashboards, forecasts, prototypes, decks, documents and web apps. VERIFIED (P1, P3)
- **Connectors.** It can use "over 6,000 connectors and plugins" from the Claude Marketplace. Named examples include Gmail, Google Calendar, Slack, QuickBooks, Stripe, Gusto, LinkedIn, Docusign, HubSpot, Canva, Shopify and Notion. VERIFIED (P1, P3)
  - Every reports that scheduled runs cannot reach custom connectors. UNVERIFIED
- **Computer and browser use.** Duet runs on its **own cloud VM with its own browser**, so the user's laptop or phone does not need to stay on. It notifies the user when a task is done or needs review. It **cannot yet show its browser** to the user. VERIFIED (P1, P2)
- **Purchases.** Duet can pay with **Link (Stripe)** using a one-time virtual card locked to one merchant and amount, and can check out with **Shop Pay**. Signing in with **1Password** is "coming soon." VERIFIED (P1, P2)
- **Known limitations.** Anthropic says Duet may misread a thread, misjudge urgency, or miss items that arrive between check-ins. It is weaker at personal errands such as booking tickets. VERIFIED (P1, P3)

### Relationship to other Claude products
- Duet carries over memory, skills and connected apps from Claude.ai and the Claude mobile app. VERIFIED (P1)
- It uses the same trustworthy-agent framework as **Claude Code** and **Claude in Chrome**. Its action checker is built on the **Claude Code auto-mode classifier**, and its credential handling follows the **Claude Managed Agents** design. VERIFIED (P1, P2)
- The official pages describe no direct relationship to **Cowork**.
  - Every reports that Duet can view Claude sessions on the user's computers but cannot direct them. UNVERIFIED

### Safety and privacy model
- **Approval gate.** Before sending messages, paying, signing documents or deleting anything, Duet shows the exact action, destination and content (including every recipient) and waits. VERIFIED (P1, P2)
- **No "don't ask again" for high-risk actions.** Paying or sending money, deleting an order and creating an account always need a fresh approval. VERIFIED (P2)
- **Blocked even with approval:** trading securities, moving money between accounts, and accessing someone else's account. VERIFIED (P1, P2)
- **Independent intent check.** An auto-mode classifier runs **outside the working model**, so injected page text cannot sway it. VERIFIED (P2)
- **Outbound data-loss classifier.** Every outgoing message and browser upload is checked.
  - Credentials, full card and bank numbers, and government IDs are never shared.
  - Health and finance details need explicit consent.
  - A blocked message may be rewritten without the sensitive content and resubmitted for approval.

  VERIFIED (P1, P2)
- **Credential isolation.** The model never sees passwords, cookies or tokens.
  - Passwords are typed into an in-app form and encrypted with a single-use key that exists only on the browser VM.
  - Tokens are placeholders. An outside proxy injects the real values.

  VERIFIED (P2)
- **Identifies itself to websites.** Duet sends a distinct User-Agent and publishes its IP addresses. Some large sites block it. VERIFIED (P2)
- **Retention.** History and memory are kept "until you delete your history or reset it." Disconnecting an app stops new access but keeps what Duet already learned. Deleting the account wipes everything. VERIFIED (P2)
- **Not stated** on the Duet pages: training use, fixed retention periods, encryption at rest, data residency. These defer to Anthropic's general privacy policy. VERIFIED that they are absent (P2)
- **Architecture: fully cloud-hosted.** Duet's memory, VM, browser and approvals all live on Anthropic's infrastructure. Nothing runs on the user's own machine. VERIFIED (P1, P3)
  - This is the sharpest contrast with Shadow's local-first, user-owned node.

---

## 2. Claude consumer baseline (as of October 2026)

The realistic competitor is not only Duet. The main Claude app now includes much of the same agent capability.

| Area | What Claude offers | Status |
|------|--------------------|--------|
| Unified chat + agent | Cowork merged into every conversation (2026-09-16). There is no mode switch. Claude picks its tools. Rolling out on web, desktop and mobile for Pro and Max. | VERIFIED (P4, P7) |
| Cloud execution | Long tasks keep running in the cloud after the laptop closes. Tasks started on desktop appear on mobile, where you can answer questions and redirect. Tasks can also start from the phone. Local files, the built-in browser and computer use still need Claude Desktop open. | VERIFIED (P7) |
| Scheduled tasks | Run hourly, daily, weekly, on weekdays or manually. Create them by describing them in chat or set them up manually with an approval mode, model and folder. A "Scheduled" sidebar lets you pause, resume, edit or run a task now. Runs happen **remotely even when the computer is asleep**. Paid plans only. | VERIFIED (P5) |
| Memory | Categorized "topic" entries are saved during chats (2026-07-10). You can view, edit and delete them. Project-scoped memory can be isolated. Sensitive topics are off by default. Some categories (government ID, financial account numbers, criminal history, immigration status) are never stored. Pause and reset are available. There are incognito chats and experimental memory import/export. Memory is on by default for Free, Pro and Max. | VERIFIED (P4, P6) |
| Chat search | RAG over past chats, shown as a tool call. Pro and above. | VERIFIED (P6) |
| Approvals | Auto mode (default on Pro, Max and Team) runs automated safety checks before actions. Manual mode (default on Enterprise) asks before each action. | VERIFIED (P7) |
| Connectors / plugins | A marketplace of connectors, skills and plugins. Microsoft 365 write tools (2026-07). Salesforce beta (2026-09). A developer portal for submitting plugins. | VERIFIED (P4) |
| Voice | Voice mode is in beta on all plans, on iOS, Android, desktop and web, and is designed for phones. It has hands-free and push-to-talk modes, can use connected apps such as Gmail, Calendar, Docs and Slack, and saves transcripts to history. | VERIFIED (P8) |
| Mobile extras | Health and fitness data analysis on iOS and Android (Pro and Max, US only, 2026-01). Interactive apps (live charts) in mobile (2026-03). iOS app intents, Shortcuts and widgets. | VERIFIED (P4); intents per support article title only (UNVERIFIED detail) |
| Dispatch | A persistent phone-to-desktop thread (2026-03-17) that gained computer use on 2026-03-23. It is **closed to new users** and superseded by cloud Cowork. | VERIFIED (P4, P7, P9) |
| Computer use | Research preview in Cowork for Pro and Max (2026-03-23). | VERIFIED (P4) |
| Claude in Chrome | Beta for paid plans since 2025-12-18, with workflow recording. Admins can set site allowlists and blocklists. | VERIFIED (P4) |
| Reflect / focus | Monthly "Reflect" recap of topics and work patterns. Break reminders and quiet hours. Beta, requires memory. | VERIFIED (P4) |
| Docs / Slides / Design | Created in any conversation. Artifacts on every plan. | VERIFIED (P4) |

---

## 3. Implications for Shadow

**Where Shadow already overlaps:**
- an approval-gated agent
- scheduled tasks
- a daily feed, which is close to Duet's morning brief
- memory
- an audit log
- BYOK models

**Where Shadow is structurally different:** it is local-first. Memory is encrypted on the user's own machine, the user brings their own keys, and there is no vendor-side retention.

- Duet's privacy model is strong on paper. But it is fully cloud-hosted, and its own pages do not state training use, retention periods, encryption at rest or data residency (P2).
- Shadow should lead with that gap, and back it with a verifiable audit log and local encryption.

**Weak spots in Claude that Shadow can exploit:**
- Duet is US-only, waitlisted, and limited to Pro and Max.
- Background checks use up plan limits.
- Duet cannot show its live browser.
- Errands and booking are weak.
- Reviewers report weak custom-connector support in scheduled runs and no true voice. UNVERIFIED

## 4. Features Shadow lacks, ranked by user value

Ranked by expected value to a single power user. Tags give the evidence status of the competitor feature, not of Shadow.

1. **Proactive, interrupt-only monitoring.** Poll connected sources every few hours, and message the user only when something needs attention, using user-set topics and frequency. Shadow's daily feed is pull-based. Duet adds push triage on top of the morning brief. VERIFIED (P1, P3)
2. **Exact-action approval cards with non-waivable classes.** Show the action, destination, full content and every recipient. Some action classes never get "don't ask again" (payments, deletes, account creation), and some are blocked outright even with approval (trading, moving money between accounts). VERIFIED (P2)
3. **Independent intent checker plus an outbound data-loss filter.** A second model or classifier, outside the working agent, checks that each action matches the user's request. A separate filter checks every outgoing message for credentials, card numbers and IDs, and can rewrite and resubmit a blocked message. This fits naturally into Shadow's approval gate and audit log. VERIFIED (P2)
4. **Credential isolation from the model.** Passwords are entered in a native form and encrypted with a single-use key. Tokens are placeholders, injected by a proxy outside the agent sandbox. The model never sees secrets and cannot write them to memory. Shadow's node could do this locally, which is a stronger story. VERIFIED (P2)
5. **Per-task pages with mid-task steering, and phone hand-off.** Each long task gets its own page with live progress and a way to redirect it. Desktop-started tasks show up on the phone with pending questions. VERIFIED (P2, P7)
6. **Inspectable, editable memory topics with sensitive-category defaults.** Memory is stored as categorized topics you can view, edit and delete. Some categories are excluded by default. Some never get stored. Memory can be scoped per project, paused, reset, and imported or exported. VERIFIED (P6)
7. **Conversational creation of scheduled tasks.** "Describe the task and cadence in chat, then confirm the proposed name, schedule and instructions," with a "run now" option and pause/resume. VERIFIED (P5)
8. **Hands-free voice mode with tool access.** Two-way voice that can call connectors and saves transcripts to history. VERIFIED (P8)
9. **Safe agent payments.** One-time virtual cards locked to a merchant and amount (Link, Shop Pay). This is high-trust and high-effort, so it should come later. VERIFIED (P1, P2)
10. **Self-identifying agent browser.** A distinct User-Agent, and a sandboxed browser driven only by fixed commands (open, click, type). VERIFIED (P2)
11. **Monthly "Reflect" recap.** Topics, peak hours and work patterns, generated from memory. Low effort, because Shadow already has the feed and memory. VERIFIED (P4)
12. **Living work products.** Dashboards, docs and decks that the agent keeps updated in place. VERIFIED (P1) for building them. The "kept updated" part is UNVERIFIED (Every).
