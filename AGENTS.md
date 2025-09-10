# Repository Guidelines

## Project Structure & Module Organization
- `main.py`: Plugin entry (class `WallabagPlugin`) registered via `@register`.
- `metadata.yaml`: Plugin metadata used by AstrBot marketplace.
- `_conf_schema.json`: Config schema surfaced in AstrBot WebUI.
- `requirements.txt`: Python dependencies for this plugin.
- Docs: `README.md` (usage), `develop.md` (dev notes), `development-plan.md` (roadmap).
- Runtime data: `data/wallabag/` created automatically for cache (e.g., `saved_urls.json`). Do not commit runtime data.

## Build, Test, and Development Commands
- Create venv: `python -m venv .venv && .venv\Scripts\activate`
- Install deps: `pip install -r requirements.txt`
- Lint & format: `ruff check .` and `ruff format .`
- Run locally: start AstrBot, place this folder under `AstrBot/data/plugins/`, enable the plugin in WebUI, then use “Reload plugin” to pick up code changes (see `develop.md`).
- Optional tests (if added): `pytest -q`

## Coding Style & Naming Conventions
- Python 3.8+; 4‑space indentation; UTF‑8 files.
- Naming: modules `snake_case.py` (entry file must be `main.py`), classes `PascalCase`, functions/vars `snake_case`.
- Use type hints where practical.
- Network I/O must be async (`aiohttp`/`httpx`). Do not use `requests`.
- Use `from astrbot.api import logger` for logging; avoid printing.
- Keep handlers inside the plugin class; register commands with `astrbot.api.event.filter`.
- Persist only under `data/` (e.g., `data/wallabag/`), not in the plugin folder.

## Testing Guidelines
- Framework: `pytest` (recommended). Place tests in `tests/` with names like `test_*.py`.
- Aim to cover URL extraction/validation and message handlers with async tests.
- Mock or stub `astrbot.api` interfaces as needed; avoid network by mocking `aiohttp` calls.
- Run: `pytest -q` and keep tests independent/isolated.

## Commit & Pull Request Guidelines
- Commits: imperative mood, concise scope. Examples:
  - `feat: add auto-save cache for URLs`
  - `fix: handle token refresh failures`
- PRs must include: purpose/summary, linked issue(s), configuration/schema changes, and updates to `README.md`/`metadata.yaml` when behavior or config changes. Add logs/screenshots where useful.

## Security & Configuration Tips
- Never commit credentials; set `wallabag_url`, `client_id`, `client_secret`, `username`, `password` via AstrBot WebUI.
- Avoid logging tokens or sensitive payloads; prefer high‑level status logs.
- Respect timeouts and retries; fail gracefully and keep the plugin responsive.
