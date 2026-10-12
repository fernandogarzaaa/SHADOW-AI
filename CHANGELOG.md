# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
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
