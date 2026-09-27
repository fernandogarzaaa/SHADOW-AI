# Roadmap
- v0.1 Shadow Inbox + Memory
- v0.2 Shadow Learns Me
- v0.3 Shadow Acts
- v0.4 AXIOM compression
- v0.5 Ghost autonomous desktop workflows
- v1.0 App Store-ready release

## Assistant parity program (Cookie / Muse.AI features, reimplemented local-first)

Each phase ships as its own PR, one at a time, green CI before merge.
- Phase 1: Persona (SOUL). Assistant identity API (`GET/PUT /persona`: name,
  avatar emoji, vibe, status) + mobile Assistant profile screen. The vibe is
  real behavior: it becomes the frontier-model system prompt. (shipped)
- Phase 2: Memory cards. Dated memory entries UI with semantic search.
  Newest-first paginated `GET /memory/recent` (limit clamped 1-200, sensitive
  excluded by default) and `DELETE /memory/{item_id}` (revoke + audit), plus a
  mobile Memory screen: semantic search, "remember something" composer,
  dated cards with category, source, and per-card forget, and a MEMORY card on
  the Assistant profile linking to it. Sorted in Python so no new plaintext
  timestamp column leaks. (shipped)
- Phase 3: Goals. Goal tracking with progress and briefings. `POST /goals`,
  `GET /goals?status=`, `GET /goals/briefing`, `GET /goals/{id}`,
  `PATCH /goals/{id}`, `DELETE /goals/{id}`, `POST /goals/{id}/progress`;
  progress entries (note + optional 0-100 percent, newest-first); the briefing
  flags stale (7+ days), due-within-7-days, and overdue goals plus completed
  this week and recent entries. Mobile Goals tab (hidden until a node is
  linked) with a briefing card, progress bars, a new-goal composer, and a
  goal detail screen with a progress timeline, log-progress composer, and
  complete/reopen/abandon/delete actions. Audited
  (`goal_created/updated/deleted/progress`) and persisted encrypted in the
  runtime DB when configured. (shipped)
- Phase 4: Feed + Ideas. Scheduled editorial feed and idea cards. (shipped)
- Phase 5: Scheduling + proactive. Reminders with recurrence, proactive push on firing, quiet hours, reminder feed units. (shipped)
- Phase 6: Artifacts, voice, media. Documents, TTS/voice notes, image generation.

Spine across all phases: local-first, encrypted at rest, user-owned data,
Sentinel-audited, offline-capable. More robust than the reference: no vendor
cloud dependency, every behavior in the real execution path.
