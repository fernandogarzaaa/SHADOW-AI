# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
- **First-owner pairing needs a setup code.** Previously the first `/pair/confirm` on a node with no devices became the owner, so anyone who reached the port first (or after any in-memory restart) owned the node. The node now prints a single-use bootstrap code to its terminal; the code rotates after 5 wrong tries. `SHADOW_BOOTSTRAP_CODE` pins one for headless installs.
- **No more permanent lockout after 30 days.** Sessions renew automatically when used, `POST /devices/{id}/renew` renews explicitly, and if every owner has expired the bootstrap code reopens.
- **Request signature v2** (`x-shadow-signature-version: 2`) also signs the query string, a digest of the raw body and the device id. v1 still works, but a device that has used v2 can't fall back to v1 (`sig_downgrade`); `SHADOW_REQUIRE_SIG_V2=true` disables v1. All clients now sign with v2.
- **Explicit consent for calendar/email tools** now comes only from a verified approval for that exact action. Before, the flag was set for exactly the tools that required it, on every execution path.
- SSRF: special-purpose ranges (CGNAT, ULA, IPv4-mapped, 6to4) are blocked via `is_global`; DNS pinning is per thread instead of swapping `socket.getaddrinfo` process-wide.
- Chunked request bodies are capped too, and auth rejects unknown devices before reading the body. The rate limiter keys on the verified device id, not a client-supplied header.
- Key files are created 0600 atomically under `SHADOW_DATA_DIR`. The Docker image excludes `data/`, `.env` and `.venv`, runs unprivileged, and keeps keys on the `/data` volume.
- Dashboard: strict CSP, no inline script or handlers, and a non-extractable signing key.

### Fixed
- Mobile and iOS pairing read `shared_secret`, which the node didn't return; the node now returns both `secret` and `shared_secret`.
- `GET /audit` lost core audit events after the first read. It now returns the paged envelope (`items`, `count`, `next_cursor`) with `event_type` and `limit` filters.
- Every question created a pending approval (and a push notification). Approvals are now created only for actions that can actually run.
- With the placeholder local model, "simple" questions were answered with a canned string even when a cloud model was approved; cloud failures were also disguised as answers. Approved cloud requests now go to the cloud model, and failures are reported as `degraded` with the error.
- The grounding retry sent unredacted context to the cloud model.
- `/pair/confirm` race (pop outside the lock); runtime SQLite access is now locked; nonce rows are pruned.
- The dashboard got a 401 on every panel with auth on, its Approvals panel crashed on the paged response, Actions self-approved, and OAuth sign-in never completed.
- The iOS app didn't compile (syntax errors, invalid launch storyboard). It now builds and pairs with a real node.

### Changed
- Anthropic provider: default model `claude-opus-5-5`, `max_tokens` 16000 (`SHADOW_MODEL_MAX_TOKENS`), handles `refusal`/`max_tokens` stop reasons, retries 429/529 with `retry-after`, and enables the server-side refusal fallback on the first-party API. Gemini default is `gemini-2.5-flash`.
- Dashboard rebuilt: browser pairing, Overview, Goals, Schedule, Feed, Panels, Devices (approve pending pairings, add a phone), audit filtering, WCAG AA contrast, system theme, reduced motion, mobile layout.
- `make run` binds 127.0.0.1 and persists state to `./data`; `run.py` honours `SHADOW_HOST`/`SHADOW_PORT`.
- Dependencies: `mcp>=2,<3` (matches the code), `pyyaml` declared; dev tools moved to `requirements-dev.txt`.
- `APP_VERSION` is `0.1.0` (was `1.0.0-rc`).
- Docs: removed 13 files that were copies of the PRD; new `THREAT_MODEL.md` and `AUTHENTICATED_TRANSPORT.md`; `docs/API.md` endpoint reference is generated (`scripts/gen_api_docs.py`).

## [0.1.0] - 2026-10-13

### Fixed
- **README quickstart and `make run` did not start the server.** `pip install -r requirements.txt` followed by `uvicorn shadow_node.main:app --app-dir apps/shadow-node` crashed with `ModuleNotFoundError: No module named 'agent_core'`, because the four `packages/*` libraries were never importable (only pytest's `pythonpath` and the Dockerfile's `PYTHONPATH` set them up). The README and runbook now `pip install -e .` / `pip install .`, `make setup` installs the project, `make run` sets `PYTHONPATH` like `make demo`, and CI boots the server the README way and checks `/health` (200) and `/memory` (401).
- **Device credentials could break on restart.** A freshly generated node master secret was written as raw bytes and read back with `strip()`; when the random bytes began or ended with a whitespace byte (~4.6% of new nodes) the secret changed on the next boot and every derived device token stopped verifying. New key files are written as hex; existing raw files load as before. This was also the intermittent `test_paired_device_persists_across_restart` CI failure on main (af335c8, b96c582).
- Web dashboard on small screens (<720px): the sidebar was `display:none`, which removed all navigation and the emergency-pause switch on phones. It is now a top bar with scrollable section tabs and the pause switch.
- Web dashboard keyboard/screen-reader access: section links are real links (`href`, `aria-current`), the emergency pause is a `role="switch"` operable with Space/Enter, inputs have labels, result areas and the toast are live regions, visible focus outlines.
- Dashboard API errors from FastAPI validation (array `detail`) were shown as `[object Object]`; they now render the messages. `esc()` also escapes quotes, and server values placed in attributes/onclick are escaped.
- `pip install -e .` (and `pip install .`) from the repo root now works: the root `pyproject.toml`
  declares the project and maps all five packages (`shadow_node`, `agent_core`, `memory_engine`,
  `axiom_adapter`, `ghost_adapter`), and ships `shadow_node/policy.yaml` and the `web/` dashboard
  as package data.

### Added
- `uv.lock` for reproducible installs of the root project.
- Dependabot for uv, bun (`apps/mobile`) and GitHub Actions, weekly.
- CI step that installs the package into a clean venv and checks the data files are present.
- This changelog.

### Changed
- `.gitignore` now covers Python build artifacts (`build/`, `dist/`, `*.egg-info/`).
