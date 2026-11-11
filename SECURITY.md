# Security policy

## Supported versions

Security fixes are applied to the current `main` branch. Self-hosters should
upgrade to the latest reviewed revision and rebuild their container.

## Reporting a vulnerability

Please do not report security vulnerabilities in a public issue. Use GitHub's
private vulnerability reporting for this repository, or contact the repository
maintainer privately if private reporting is unavailable.

Include the affected component, the impact, and concise reproduction details.
Do not include real player data, credentials, admin keys, or private room
content. The maintainer will acknowledge the report and coordinate a fix and
disclosure timeline with the reporter.

## Deployment notes

- Keep `config.yaml` and `GAME_ADMIN_KEY` private.
- Keep game creation key-restricted unless public creation is intentional.
- Room uploads are disabled by default. Enable them only after reviewing
  `uploads.who`, `uploads.visibility`, and the memory and rate limits.
- Use HTTPS for public access and configure `server.trusted_proxies` narrowly.
- The server is single-instance and stores games and uploaded rooms in memory;
  restarts clear that state.

See [README.md](README.md) for deployment guidance and
[docs/ROOM_AUTHORING.md](docs/ROOM_AUTHORING.md) for room upload constraints.
