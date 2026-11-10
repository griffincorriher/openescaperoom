# Build spec

An open-source (MIT), self-hostable party game framework. Version 1 is a team escape room engine. Any number of games run at once on one server, each joined with a short code. Its lobby, teams, timer and results form a shared shell that later games plug into.

**Security goal:** every configuration a self-hoster can choose is safe, including a public server where strangers create games and upload rooms. Defaults are locked down; opening things up is a deliberate config change, never a security downgrade.

## Stack and constraints

No Node, no npm, no build step: everything runs from one FastAPI process on one port.

- **Backend:** Python, FastAPI, native WebSockets, PyYAML (safe loader only), Pillow for re-encoding images.
- **Frontend:** plain HTML and vanilla JS as ES modules (`<script type="module">`). No inline scripts anywhere.
- **Styling:** Flowbite + the Tailwind browser build + Chart.js, saved in `static/vendor/`. No CDN calls.
- **Hosting:** anywhere Python runs: a laptop, SageMaker Studio, or a public host (VPS, Fly.io, Render, Railway, Lightsail). Behind a path prefix (SageMaker serves under `/jupyter/default/proxy/8000/`), so all asset paths are relative and the WebSocket URL is built from `window.location` (`wss://` on https).
- **Single instance:** all state is in memory, so the app runs as one process. No horizontal scaling.
- **State:** game data is never written to disk, and there is no database or external storage. Game state (players, teams, progress, event log, results) and uploaded room zips and files live only in server memory. The only file the app ever writes is `config.yaml` on first run (see Config). Logs go to stdout and never contain game content. Bundled rooms are read from `rooms/` at startup. A restart ends all games and clears uploaded rooms.

## Games and join codes

- **Create game:** pick a room, get a 5-character join code from an unambiguous alphabet (no 0/O, 1/I/L). The creator becomes that game's host.
- **Join:** open `/join/<CODE>` or type the code on the home page.
- **Host token:** on creation the server issues a random token (`secrets.token_urlsafe(32)`), stored in the creator's browser for that game. Every host action carries it and is checked with `hmac.compare_digest`. A token only works for its own game. If the host disconnects, the game keeps running and host controls return when they reconnect with the token.
- **Isolation:** games share nothing. Every WebSocket connection belongs to exactly one game, and the server rejects any action aimed at another game.
- **Lifecycle:** a game is deleted from memory `games.idle_minutes` after it ends, or after that long with no connected players.
- **Who can create games:** `games.create: key` (default) requires the `admin_key`; `anyone` opens creation to the public, protected by the rate limits below.

## Config

All settings live in `config.yaml`, read once at startup. Nothing in the browser can change them; editing the file and restarting is the only way. **First run:** if `config.yaml` is missing, the server copies `config.example.yaml` to `config.yaml`, generates a random `admin_key` into it, and prints the key once at startup. The key then survives restarts. If the folder isn't writable, it falls back to the example defaults with an in-memory key and says so in the log.

```yaml
server:
  port: 8000
  trusted_proxies: []            # IPs of a reverse proxy whose X-Forwarded-For is trusted
  allowed_origins: []            # extra WebSocket origins; same-origin is always allowed

security:
  admin_key: ""                  # env GAME_ADMIN_KEY overrides; generated on first run

games:
  create: key                    # key | anyone
  max_concurrent: 50
  max_players_per_game: 40
  max_teams_per_game: 10
  idle_minutes: 30
  creates_per_ip_per_hour: 10

rooms:
  preload_dir: rooms             # bundled rooms, read at startup, never written

uploads:
  enabled: false                 # false = the upload feature does not exist on the server
  who: key                       # key | anyone
  visibility: private            # private = only the uploader's games | public = everyone's room picker
  ttl_minutes: 120               # unused uploaded rooms are dropped from memory after this
  max_zip_mb: 50
  max_unzipped_mb: 200
  max_files: 200
  max_total_memory_mb: 1024      # oldest uploaded rooms are evicted past this
  per_ip_per_hour: 5

game:
  max_team_size: 8
  skip_penalty_sec: 300          # added when the host skips a puzzle for a team

limits:
  ws_messages_per_sec: 20
  ws_connections_per_ip: 10
  join_attempts_per_ip_per_min: 20
```

**Example setups:**

| Setup | `games.create` | `uploads.enabled` | `uploads.who` | `uploads.visibility` |
| --- | --- | --- | --- | --- |
| Out of the box / private | key | false | — | — |
| Work team, trusted authors | key | true | key | public |
| Public site, bundled rooms only | anyone | false | — | — |
| Public site, anyone uploads | anyone | true | anyone | private |

## Security

**Threat model:** assume every player, every WebSocket message and every uploaded file is hostile. Nothing a client sends is trusted.

### Feature switches are real

When `uploads.enabled` is false, the upload and template routes are never registered (404), the upload page is not served or linked, and the WebSocket hub has no upload actions. Re-enabling a button in dev tools does nothing because there is no endpoint behind it. The same applies to `games.create: key`: creating without the key is refused server-side.

### Uploaded rooms

- **YAML:** parsed only with `yaml.safe_load` (never `yaml.load`, which can run code). Anchors and aliases are rejected (blocks "billion laughs" YAML bombs). `room.yaml` max 256 KB. Every field is checked against the schema; unknown fields are rejected.
- **File types:** allowlist by extension *and* by magic bytes: PNG, JPG, WEBP, MP3, `.yaml`, `.md`. SVG, HTML, JS, archives and everything else reject the whole zip.
- **Images:** decoded with Pillow under a pixel cap (`Image.MAX_IMAGE_PIXELS`, about 40 MP), then re-encoded to fresh PNG/WEBP with metadata stripped and width capped at 1920 px. The original bytes are discarded.
- **Audio:** magic-byte check, 5 MB cap per file, served only as `audio/mpeg`.
- **Markdown (`HOST_GUIDE.md`):** shown as plain text only, never rendered as HTML.
- **Zip:** no `../` or absolute paths, no symlinks, no nested archives; limits on zip size, unzipped size, compression ratio and file count.
- **Never executed, never written to disk.** Files are held as bytes in memory and served with a fixed `Content-Type` from the allowlist.
- **Private uploads (`visibility: private`):** the uploader gets a room token and only games they create with it can use the room. Strangers' content is only ever seen by the people they invited.
- **Memory:** per-IP upload limits, a total memory cap with oldest-first eviction, and a TTL for unused rooms.

### Browser side

- **Player text is never HTML:** player names, team names, host messages and every value from a room file are inserted with `textContent`, never `innerHTML`. Names max 24 characters, team names 30, host messages 200; WebSocket messages max 4 KB.
- **Content Security Policy** on every page: `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'`. (`unsafe-inline` styles only, because the Tailwind browser build injects a style tag. Verify the Tailwind and Chart.js builds work under this policy.)
- **Headers:** `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`.

### Server side

- **WebSocket Origin check:** connections from origins other than the server's own (plus `allowed_origins`) are refused, which blocks other websites from opening sockets with a visitor's browser.
- **Rate limits:** game creation, join attempts (so codes can't be brute-forced), WebSocket messages and connections per IP, uploads per IP. Answer cooldowns stop lock brute-forcing.
- **Client IP:** taken from `X-Forwarded-For` only when the request comes from a `trusted_proxies` address; otherwise the socket address. This keeps per-IP limits from being spoofed.
- **Secrets:** `admin_key`, host tokens and room tokens are compared with `hmac.compare_digest` and never logged.
- **Answers never leave the server,** except to the host token in playtest mode.

## GitHub repo

Public, MIT licensed, runs after a clone with no extra setup.

- `config.example.yaml` is committed; `config.yaml` is in `.gitignore` so nobody pushes their `admin_key`.
- `rooms/` ships with a free sample room so a fresh clone is playable immediately.
- `requirements.txt` pins exact versions; Dependabot keeps them updated.
- `Dockerfile` for public hosting (Python only, runs as a non-root user).
- `SECURITY.md` explains how to report a vulnerability.
- `README.md` covers: run locally, run on SageMaker Studio (proxy path, idle timeout), public hosting (HTTPS, single instance, `trusted_proxies`), the example setups, and making a room (`docs/ROOM_AUTHORING.md`).
- `static/vendor/` includes Flowbite, the Tailwind browser build and Chart.js with their licenses.

## Architecture

The server owns all game state; browsers only send actions and draw the snapshot they receive.

1. A player clicks something (join team, submit answer, take hint) and the browser sends an action over the WebSocket.
2. The server checks it (right game, right role, rate limit), updates the game state, and checks answers.
3. The server pushes a fresh snapshot to everyone affected in that game: the lobby, one team, or the host.
4. Each browser redraws from the snapshot.

```
app/
├── main.py              # FastAPI app, config, static files, routes, security headers
├── config.py            # load + validate config.yaml, fall back to example defaults
├── security.py          # tokens, rate limits, origin check, client IP
├── ws.py                # WebSocket hub: connections, per-game broadcast
├── games.py             # game registry: codes, create/join, lifecycle cleanup
├── lobby.py             # players, teams, host controls (shared by all games)
├── escape/
│   ├── engine.py        # game state, unlocks, timer, hints, scoring, event log
│   ├── loader.py        # reads room.yaml, builds the puzzle graph
│   ├── validator.py     # zip + room checks, returns errors/warnings
│   ├── sanitize.py      # image re-encoding, magic-byte checks
│   ├── checkers.py      # answer matching per puzzle type
│   └── store.py         # in-memory room store: bundled + uploaded, tokens, eviction
rooms/                   # bundled rooms (read-only), includes the free sample room
templates/               # template.zip for authors, shipped with the code
static/
├── vendor/              # tailwind.browser.js, flowbite.min.js, chart.umd.js
├── sounds/              # small CC0 sound effects
├── core/                # socket.js, state.js, ui.js (timer, toasts, modals)
├── puzzles/             # one module per puzzle type
└── pages/               # home.html, join.html, play.html, host.html, upload.html
config.example.yaml
Dockerfile
SECURITY.md
```

**Puzzle plugins:** each file in `static/puzzles/` exports `render(el, puzzle, submit)`, and each has a matching checker in `checkers.py`. Adding a puzzle type means adding those two pieces. The client never receives answers.

**Player identity:** each browser gets a random player ID in `localStorage`. On reconnect or refresh, the server matches the ID within that game and restores the player's name and team.

**Startup room check:** every room in `rooms/` is validated at startup. A broken room is skipped with a clear log message; the server still starts.

## Lobby and teams

Players form their own teams; the host can fix things up. Every change shows live on every screen in that game.

### Player actions

| Action | Who | Rules |
| --- | --- | --- |
| Create team | Anyone | Names a team and joins it automatically. Duplicate names are blocked. Max `games.max_teams_per_game`. |
| Join team | Anyone | Click a team card. Disabled when the team is at the room's max `team_size`. |
| Change team | Anyone | Same as join: clicking another team moves you. |
| Leave team | Anyone | Back to the Unassigned pool. |
| Delete team | Host | Only when the team is empty; the button shows only on empty teams. |

### Host controls

- Move a player between teams by dragging.
- Auto-balance: spread unassigned players into the smallest teams.
- Rename a team.
- Lock teams to freeze switching before start.

### When the host presses Start

- Empty teams are ignored and left off the leaderboard.
- Unassigned players are auto-assigned to the smallest teams, with no prompt. Each sees a toast naming their team; the host sees a summary.
- A team below the room's minimum size triggers a warning the host can override.
- Teams are then fixed; only the host's move control changes them.

### Late joiners

- They pick their own team from a list showing each team's progress ("Team Owls · 4 of 8 solved").
- They may push a team over its max size (but not the game over `max_players_per_game`).
- They land on the team's current state and see the prestory of any puzzle that's open.
- Open `split_clue` puzzles re-deal fragments so the new player gets one and nobody loses theirs.

## Gameplay

All teams in a game play the same room at the same time, racing on one shared clock.

- **Intro:** every player sees the room's intro slide at start; the clock begins when the host starts the game.
- **Prestory slides:** when a puzzle unlocks for a team, each member sees its prestory as a full-screen slide with a Begin button. It can be reopened from the puzzle screen.
- **Puzzle map:** the team's home screen. Every puzzle shows as locked, open or solved, so the team can split up across parallel branches.
- **Shared progress:** a solve unlocks the next puzzles for the whole team at once and shows the `solve_text` to everyone.
- **Answers:** checked only on the server. Matching ignores case, spaces and punctuation. A wrong answer starts a short cooldown (`wrong_answer_cooldown_sec`) for that puzzle.
- **Hints:** revealed one at a time, shared with the whole team, and each adds `hint_penalty_sec` to the team's time.
- **Split clues:** fragments are dealt round-robin to the team's members; each player sees only their own.
- **Meta puzzle:** shows the fragments the team has collected from `gives` fields so far.
- **Finish:** solving the meta shows the outro slide and the team's final time.
- **Time's up:** play stops, every team sees the outro, and the results page shows.

### Host controls during play

- **Pause / resume:** freezes the clock and puzzle input for every team, with a "Paused" overlay.
- **Add time:** adds minutes to the shared clock.
- **End early:** stops the game and goes straight to results.
- **Skip puzzle:** solves a puzzle for one stuck team, adds `game.skip_penalty_sec` to their time, and logs it so it shows in their results. No player gets solve credit.
- **Message:** a toast to one team or everyone (200 characters max).
- **Kick player:** removes a player; that player ID can't rejoin the same game.

### Playtest mode

Anyone allowed to create games can playtest any room they can access, solo, with answers shown under each puzzle. A playtest is a private one-player game: no join code, no leaderboard, and it counts toward `max_concurrent`.

### Polish

- **Team activity feed:** a side panel showing each teammate's attempts, solves and hints ("Sam tried 1234 on the safe ✗"), so nobody repeats a wrong guess.
- **Confetti and sound:** a short sound and confetti burst on each solve, a bigger one on finishing. Sounds are small CC0 files in `static/sounds/`, with a mute toggle remembered per browser.
- **Dark mode:** Flowbite dark mode, following the system setting with a manual toggle.

**Leaderboard ranking:** most puzzles solved, then lowest time including hint penalties. The host sees it live; players see it at the end.

### Results page

Shown to everyone in the game when it ends, in four panels:

1. **Team standings:** rank, team, puzzles solved, final time (raw time + hint penalty shown separately), hints used.
2. **Race chart:** one line per team, puzzles solved (y) over minutes elapsed (x), drawn as step lines. Hints used show as small markers on each team's line; hovering a step shows the puzzle and who solved it.
3. **Awards:** see below.
4. **Your stats:** your puzzles solved, average solve speed, and the awards you won. No player leaderboard.

**How stats are counted:**

- A solve is credited to the player who submitted the correct answer.
- Solve speed = time from the puzzle unlocking for that team to the correct submission. Average speed is the mean across that player's solves.
- Players with zero solves show "—" for speed.
- Stats live in memory with the game and are deleted with it.
- **No export of game data, ever:** no CSV, JSON or image download of the event log, stats or results, for players or host.

**Event log:** the engine records every unlock, puzzle open, wrong answer, correct answer, hint and skip with a timestamp, player and team. The race chart, stats and awards are all computed from this log at game end.

### Play another room

A game code is a session that can run several rounds back to back.

- On the results page the host clicks **Play another room**, which opens the room picker for the host only.
- Players keep seeing the results, with a banner: "Host is picking the next room…"
- The host picks a room and everyone returns to the lobby with the **same join code, players and teams**. Teams are unlocked so people can switch if they want; the host can lock and start as usual.
- Starting the next round deletes the previous round's event log and results from memory.
- Late joiners can still use the same code between rounds.

**Session scoreboard:** from round 2 onward, the results page adds a panel totalling every round in this session, per team: rounds played, wins, total puzzles solved, total time. Ranked by wins, then total puzzles, then lowest total time. Teams are tracked by team ID, so a renamed team keeps its record; a team created mid-session starts at zero; a deleted team stays listed, greyed out. It lives in memory with the session and is deleted with it.

### Awards

Each award shows only if someone earned it. Ties share the award.

| Award | Goes to | Rule |
| --- | --- | --- |
| Speed Demon | Player | Fastest single solve (unlock to correct answer) |
| Clutch | Player | Submitted the correct answer to the meta puzzle (one per finishing team) |
| Brute Forcer | Player | Most wrong answers, minimum 5 |
| Lone Wolf | Player | Most solves on puzzles no teammate had opened |
| Workhorse | Player | Most solves overall |
| Hint Hoarder | Team | Most hints used |
| Photo Finish | Team | Finished within 60 seconds of another team |

## Room uploads (only when `uploads.enabled: true`)

1. The author downloads `template.zip` from the upload page.
2. The author uploads the finished zip (needs the `admin_key` when `uploads.who: key`).
3. The server unzips it in memory, sanitizes it, and runs the validator rules from `docs/ROOM_AUTHORING.md`.
4. The page shows errors (block the upload) and warnings (allowed).
5. A passing room is loaded into memory. With `visibility: private`, the uploader gets a room token and can create games or playtest with it. With `visibility: public`, it appears in every room picker after the uploader marks it ready.

**Nothing persists:** uploaded rooms disappear on restart, after `ttl_minutes` unused, or when evicted for memory. To make a room permanent, commit its folder to `rooms/`. Re-uploading a room with the same `id` and token replaces it.

## Room picker

Creating a game opens a grid of every room this person can play, with "Upload new room" as the last tile.

- **Grid:** responsive rows and columns (1 column on phones, 2 on tablets, 3–4 on desktop). Bundled rooms first, then uploaded rooms, newest first.
- **Room tile:** cover image, title, difficulty badge, estimated minutes, team size, tags, author. Uploaded rooms carry an "Uploaded" badge; private ones a "Private" badge.
- **Which rooms appear:** the server builds the list per person: bundled rooms, public uploaded rooms, and private uploads whose room token is in this browser. Private rooms never appear for anyone else.
- **Clicking a room:** opens a detail modal with the cover, the intro text, and two buttons: **Create game** (gets the join code and opens the lobby) and **Playtest**.
- **Upload tile:** the last tile, shown only when the server says this person may upload. If uploads are off, the server never sends the tile, and the upload endpoint doesn't exist. With `uploads.who: key`, clicking it asks for the admin key first.
- **After an upload:** the modal shows validator errors and warnings. A passing room appears in the grid immediately, highlighted, with its detail modal open.

## Screens

| Screen | Who | Flowbite pieces |
| --- | --- | --- |
| Home | Everyone | Create game button, join-code input |
| Name entry | Players | Input, button |
| Room picker | Game creator | Responsive card grid, badges, room detail modal, upload tile |
| Join / team lobby | Everyone in the game | Join code display, team cards, avatar groups, Unassigned list, create-team modal |
| Intro and prestory slides | Players | Full-screen modal over the image, Begin button |
| Puzzle map | Players | Card grid with lock/check icons, progress bar, timer, activity feed |
| Puzzle view | Players | Per-type puzzle module, hint accordion, answer input, toasts |
| Host dashboard | Host | Team progress table, badges, start/lock/pause controls, messages, live leaderboard |
| Results | Everyone in the game | Standings table, race chart, award cards, your stats |
| Upload modal (from the upload tile) | Uploaders (uploads on only) | File dropzone, validator alerts |

## Later (not v1)

- Other games on the shared shell: Codenames, Quiplash-style, Who Said It?
- Post-game stats per room: slowest puzzle, most-used hints.
- Room ratings after each game.
- Host "live events" mid-game (power outage, clue swap).
- Cross-team trading puzzles.
- Visual room editor that writes the zip.
- Interactive puzzle types: match pairs, memory flip, Connections-style grouping, drag onto image, flashlight/UV reveal, jigsaw, sliding tiles, lights out, Simon says, radio dial, simultaneous buttons, split controls. Add a `reveals:` field so finishing one uncovers a clue (overlay text) needed by another puzzle. Server still verifies every completion.
- Ambient audio per room/puzzle, projector mode for the host's shared screen, colorblind-safe palettes.
- Season ladder: team points across sessions (would need storage).
