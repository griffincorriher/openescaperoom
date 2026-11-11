# Party Games Server

## Run locally

Install the Python dependencies and start the server:

```sh
python -m pip install -r requirements.txt
python -m app
```

On first run, the server creates `config.yaml` with a generated `admin_key`
and prints that key once. Keep the file private; it is excluded from Git.
Set `GAME_ADMIN_KEY` to override the configured key, or `GAME_CONFIG_PATH` to
choose a different config file.

The server has no database or persistent game storage. Do not expose it on a
public network without HTTPS and a deliberate review of its access settings.
The default requires an admin key to create games and disables room uploads.

Create a game from the home page using the admin key when creation is
key-restricted. Share its five-character code so others can join from the home
page or from `/join/<CODE>`. The host token stays in the creating browser for
reconnects. In the lobby, everyone chooses a name and can create or join a
team. The host can rename teams, move players, auto-balance, lock teams, and
start the session. The included **The First Light** room is a complete starter
room for testing: open available puzzles, ask for hints, solve the team meta
puzzle, and compare the race chart and results. Games, progress, timers and
event logs are held in memory and disappear when the server restarts.

Bundled rooms are loaded from `rooms/<room-id>/room.yaml` at startup. Invalid
rooms are skipped and reported in the server log. The room format and
validation rules are documented in [docs/ROOM_AUTHORING.md](docs/ROOM_AUTHORING.md).

To test **The First Light**, create a team and start the game. Open the four
available puzzles; the split clue is different for each teammate. Use the
puzzle controls to submit answers, try hints, and order the moon phases. The
final answer is `east green full moon star`. The timer, team progress, and
results appear in the game view.

Use **Playtest solo** beside **Create game** to start a private, one-player
session with answers shown on the puzzle map; playtests have no join code or
leaderboard. During a live game, the host dashboard can pause or resume play,
add time, skip a puzzle for one team, message teams, remove a player, or end
early. Players see their team's activity feed and a paused overlay when
appropriate. Dark mode and sound preferences are stored in the browser.

## Run tests

```sh
python -m pip install -r requirements-dev.txt
python -m pytest
```

## Run with the apps Docker Compose stack

From the parent `apps` directory:

```sh
docker compose up --build openescaperoom
```

The service is available at `http://localhost:8004`. Its config (including the
generated admin key) is stored in the `openescaperoom-config` Docker volume.
To view the first-run key, use `docker compose logs openescaperoom`.

The application is a single in-memory instance; restarting it ends any games.
Uploaded rooms also exist only in memory and disappear after a restart. To
enable uploads, set `uploads.enabled: true` in `config.yaml` and restart.
`uploads.who` chooses whether uploads are open or require the admin key;
`uploads.visibility` controls whether uploaded rooms are public or private.
Public uploads stay visible only to the uploader until they review and publish
them. Private-room access tokens are stored in the uploader's browser.

## Hosting and security

- **Docker:** use the Compose service above. It runs as a non-root user, has a
  read-only root filesystem, and persists only `/config/config.yaml`.
- **Behind a reverse proxy:** terminate HTTPS at the proxy and set
  `server.trusted_proxies` to the proxy's exact IP address or network before
  relying on `X-Forwarded-For` for rate limits. WebSockets must be proxied.
- **Path prefixes:** the app uses relative asset URLs and derives its WebSocket
  URL from the current page, so it can run beneath a proxy path.
- **SageMaker Studio:** with the default server port, open
  `/jupyter/default/proxy/8000/` beneath the Studio URL. Studio administrators
  control the idle-session timeout; stopping or timing out the Studio session
  stops the server and clears all in-memory games and uploads.
- **Public deployments:** use one server instance; state is in memory and is
  not shared across replicas. Keep game creation key-restricted unless public
  creation is intended. Uploads are opt-in and should remain disabled unless
  required.

Example config choices:

| Use | `games.create` | `uploads.enabled` | `uploads.who` | `uploads.visibility` |
| --- | --- | --- | --- | --- |
| Private server | `key` | `false` | — | — |
| Trusted room authors | `key` | `true` | `key` | `public` |
| Public games, bundled rooms | `anyone` | `false` | — | — |
| Public games and private uploads | `anyone` | `true` | `anyone` | `private` |

Read [SECURITY.md](SECURITY.md) before deploying publicly. Room package
structure and upload constraints are in [docs/ROOM_AUTHORING.md](docs/ROOM_AUTHORING.md).

## Frontend assets

The interface uses Flowbite 3.1.2 (including its precompiled Tailwind-based
stylesheet) and Chart.js 4.5.1, vendored in `static/vendor/` so the app makes
no CDN requests and needs no Node/npm build step. Their MIT license texts are
included alongside the bundles.