# Party Games Server

An open-source (MIT), self-hostable multiplayer party game framework, starting with a team escape room engine. Many games run at once on one server, each joined with a short code. People self-host it anywhere: a laptop, SageMaker Studio behind a work network, or a public website where strangers create games and upload rooms.

**Read `docs/SPEC.md` before writing any code.** It is the source of truth. `docs/ROOM_AUTHORING.md` is the author-facing room format; the engine must accept exactly that format.

## Security is the top priority

Every configuration a self-hoster can choose must be safe, including public creation + public uploads. Assume every player, message and uploaded file is hostile. Defaults are locked down. See the Security section of the spec; key rules:

- **Feature switches are real.** Disabled features have no routes or WebSocket actions (404), not just hidden UI.
- **Uploads:** `yaml.safe_load` only, no YAML anchors/aliases; extension + magic-byte allowlist (no SVG/HTML/JS); images re-encoded with Pillow under a pixel cap; zip path/size/ratio/count limits; uploaded files never executed and never written to disk.
- **Player text is never HTML.** Always `textContent`, never `innerHTML`. Enforce length limits.
- **Strict CSP**, no inline scripts, `nosniff`, WebSocket Origin check.
- **Tokens:** `secrets.token_urlsafe`, compared with `hmac.compare_digest`, never logged. Host tokens are scoped to one game.
- **Rate limits** per IP (creation, joins, messages, uploads). Client IP from `X-Forwarded-For` only via `trusted_proxies`.
- **Answers never leave the server** (except playtest to the host).

## Hard constraints

- **Backend:** Python + FastAPI + native WebSockets. PyYAML, Pillow, uvicorn. Nothing else unless necessary.
- **Frontend:** plain HTML + vanilla JS ES modules. **No Node, no npm, no build step, no React/Vite.**
- **Styling:** Flowbite + Tailwind browser build + Chart.js, vendored in `static/vendor/`. **No CDN calls.**
- **Path prefix safe:** may run behind a proxy path (SageMaker: `/jupyter/default/proxy/8000/`). All asset paths relative; WebSocket URL built from `window.location`.
- **Game data is never written to disk.** Game state, event logs, results and uploaded zips/files live only in memory. No database, no external storage. Single instance. The only file the app writes is `config.yaml` on first run. Logs to stdout, never containing game content.
- **No export of game data.** Never add CSV/JSON/image downloads of the event log, stats or results.
- **Server is authoritative.** Browsers send actions, receive snapshots, redraw.
- **Config** read once at startup from `config.yaml`. On first run, copy `config.example.yaml` to `config.yaml` with a generated `admin_key` and print it once; if not writable, fall back to defaults with an in-memory key.

## Build order

1. Skeleton: config loading + validation, FastAPI app, security headers/CSP, static serving, WebSocket hub with Origin check, rate limits, reconnect via player IDs.
2. Game registry: create game (join codes, host tokens), join by code, isolation, idle cleanup, `games.create` key gating.
3. Shared lobby: name entry, teams (create/join/change/leave, host delete-if-empty), host controls, start rules, late joiners.
4. Escape room engine: room loader + validator, puzzle graph, prestory slides, puzzle map, hints, timer, split clues, meta puzzle, event log, results page (race chart, awards, your stats).
5. Puzzle type modules (`static/puzzles/*.js` + server checkers) for every type in the spec.
6. Host dashboard: pause/resume, add time, end early, skip puzzle, messages, kick, playtest mode, activity feed, polish.
7. Uploads (only when enabled): sanitizer, private/public visibility, room tokens, memory cap/TTL.
8. Free sample room in `rooms/`, README, LICENSE, SECURITY.md, Dockerfile.

Write tests for the security rules (feature switches, upload sanitizing, token scoping, text escaping) as you go.

## Context

- A Telestrations game already exists separately (FastAPI; frontend unknown). The shell should let other games plug in later.
- Keep setup to `pip install -r requirements.txt` then `python -m app`.
