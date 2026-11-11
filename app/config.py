from __future__ import annotations

import ipaddress
import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

import yaml

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ConfigError(ValueError):
    """Raised when the server configuration is invalid."""


@dataclass(frozen=True)
class ServerConfig:
    port: int
    trusted_proxies: tuple[str, ...]
    allowed_origins: tuple[str, ...]


@dataclass(frozen=True)
class SecurityConfig:
    admin_key: str


@dataclass(frozen=True)
class GamesConfig:
    create: str
    max_concurrent: int
    max_players_per_game: int
    max_teams_per_game: int
    idle_minutes: int
    creates_per_ip_per_hour: int


@dataclass(frozen=True)
class RoomsConfig:
    preload_dir: str


@dataclass(frozen=True)
class UploadsConfig:
    enabled: bool
    who: str
    visibility: str
    ttl_minutes: int
    max_zip_mb: int
    max_unzipped_mb: int
    max_files: int
    max_total_memory_mb: int
    per_ip_per_hour: int


@dataclass(frozen=True)
class GameConfig:
    max_team_size: int
    skip_penalty_sec: int


@dataclass(frozen=True)
class LimitsConfig:
    ws_messages_per_sec: int
    ws_connections_per_ip: int
    join_attempts_per_ip_per_min: int


@dataclass(frozen=True)
class AppConfig:
    server: ServerConfig
    security: SecurityConfig
    games: GamesConfig
    rooms: RoomsConfig
    uploads: UploadsConfig
    game: GameConfig
    limits: LimitsConfig


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"Unable to read configuration file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Configuration file {path} must contain a YAML mapping.")
    return data


def _merge_config(base: dict[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    unknown_sections = set(overrides) - set(base)
    if unknown_sections:
        raise ConfigError(f"Unknown configuration section: {sorted(unknown_sections)[0]}")

    merged = {section: dict(values) for section, values in base.items()}
    for section, values in overrides.items():
        if not isinstance(values, dict):
            raise ConfigError(f"Configuration section '{section}' must be a mapping.")
        unknown_keys = set(values) - set(merged[section])
        if unknown_keys:
            raise ConfigError(
                f"Unknown configuration key: {section}.{sorted(unknown_keys)[0]}"
            )
        merged[section].update(values)
    return merged


def _require_int(value: Any, name: str, minimum: int, maximum: int | None = None) -> int:
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        limit = f" and at most {maximum}" if maximum is not None else ""
        raise ConfigError(f"'{name}' must be an integer between {minimum}{limit}.")
    return value


def _require_string(value: Any, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ConfigError(f"'{name}' must be a non-empty string.")
    return value


def _validate_origin(value: Any) -> str:
    origin = _require_string(value, "server.allowed_origins entry")
    try:
        parsed = urlsplit(origin)
        valid_port = parsed.port is None or 1 <= parsed.port <= 65535
    except ValueError:
        raise ConfigError("'server.allowed_origins' entries must be HTTP(S) origins.") from None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or not valid_port
    ):
        raise ConfigError("'server.allowed_origins' entries must be HTTP(S) origins.")
    return origin.rstrip("/")


def _validate_config(data: dict[str, Any]) -> AppConfig:
    server = data["server"]
    security = data["security"]
    games = data["games"]
    rooms = data["rooms"]
    uploads = data["uploads"]
    game = data["game"]
    limits = data["limits"]

    trusted_proxies = server["trusted_proxies"]
    if not isinstance(trusted_proxies, list) or not all(
        isinstance(value, str) for value in trusted_proxies
    ):
        raise ConfigError("'server.trusted_proxies' must be a list of IP addresses or networks.")
    try:
        for proxy in trusted_proxies:
            ipaddress.ip_network(proxy, strict=False)
    except ValueError as exc:
        raise ConfigError("'server.trusted_proxies' contains an invalid IP address or network.") from exc

    allowed_origins = server["allowed_origins"]
    if not isinstance(allowed_origins, list):
        raise ConfigError("'server.allowed_origins' must be a list.")

    admin_key = _require_string(security["admin_key"], "security.admin_key")
    create_policy = _require_string(games["create"], "games.create")
    upload_policy = _require_string(uploads["who"], "uploads.who")
    upload_visibility = _require_string(uploads["visibility"], "uploads.visibility")
    if create_policy not in {"key", "anyone"}:
        raise ConfigError("'games.create' must be 'key' or 'anyone'.")
    if upload_policy not in {"key", "anyone"}:
        raise ConfigError("'uploads.who' must be 'key' or 'anyone'.")
    if upload_visibility not in {"private", "public"}:
        raise ConfigError("'uploads.visibility' must be 'private' or 'public'.")
    if type(uploads["enabled"]) is not bool:
        raise ConfigError("'uploads.enabled' must be a boolean.")

    return AppConfig(
        server=ServerConfig(
            port=_require_int(server["port"], "server.port", 1, 65535),
            trusted_proxies=tuple(trusted_proxies),
            allowed_origins=tuple(_validate_origin(value) for value in allowed_origins),
        ),
        security=SecurityConfig(admin_key=admin_key),
        games=GamesConfig(
            create=create_policy,
            max_concurrent=_require_int(games["max_concurrent"], "games.max_concurrent", 1),
            max_players_per_game=_require_int(
                games["max_players_per_game"], "games.max_players_per_game", 1
            ),
            max_teams_per_game=_require_int(
                games["max_teams_per_game"], "games.max_teams_per_game", 1
            ),
            idle_minutes=_require_int(games["idle_minutes"], "games.idle_minutes", 1),
            creates_per_ip_per_hour=_require_int(
                games["creates_per_ip_per_hour"], "games.creates_per_ip_per_hour", 1
            ),
        ),
        rooms=RoomsConfig(preload_dir=_require_string(rooms["preload_dir"], "rooms.preload_dir")),
        uploads=UploadsConfig(
            enabled=uploads["enabled"],
            who=upload_policy,
            visibility=upload_visibility,
            ttl_minutes=_require_int(uploads["ttl_minutes"], "uploads.ttl_minutes", 1),
            max_zip_mb=_require_int(uploads["max_zip_mb"], "uploads.max_zip_mb", 1),
            max_unzipped_mb=_require_int(
                uploads["max_unzipped_mb"], "uploads.max_unzipped_mb", 1
            ),
            max_files=_require_int(uploads["max_files"], "uploads.max_files", 1),
            max_total_memory_mb=_require_int(
                uploads["max_total_memory_mb"], "uploads.max_total_memory_mb", 1
            ),
            per_ip_per_hour=_require_int(uploads["per_ip_per_hour"], "uploads.per_ip_per_hour", 1),
        ),
        game=GameConfig(
            max_team_size=_require_int(game["max_team_size"], "game.max_team_size", 1),
            skip_penalty_sec=_require_int(
                game["skip_penalty_sec"], "game.skip_penalty_sec", 0
            ),
        ),
        limits=LimitsConfig(
            ws_messages_per_sec=_require_int(
                limits["ws_messages_per_sec"], "limits.ws_messages_per_sec", 1
            ),
            ws_connections_per_ip=_require_int(
                limits["ws_connections_per_ip"], "limits.ws_connections_per_ip", 1
            ),
            join_attempts_per_ip_per_min=_require_int(
                limits["join_attempts_per_ip_per_min"],
                "limits.join_attempts_per_ip_per_min",
                1,
            ),
        ),
    )


def load_config(
    config_path: str | Path | None = None,
    *,
    example_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> AppConfig:
    """Load and validate settings, creating a persistent admin key on first run."""
    env = os.environ if environ is None else environ
    if config_path is None:
        config_path = env.get("GAME_CONFIG_PATH", str(PROJECT_ROOT / "config.yaml"))
    path = Path(config_path)
    example = Path(example_path) if example_path is not None else PROJECT_ROOT / "config.example.yaml"
    defaults = _read_yaml(example)

    generated_key: str | None = None
    if path.exists():
        data = _merge_config(defaults, _read_yaml(path))
    else:
        data = _merge_config(defaults, {})
        generated_key = secrets.token_urlsafe(32)
        data["security"]["admin_key"] = generated_key

    env_key = env.get("GAME_ADMIN_KEY")
    if env_key is not None:
        data["security"]["admin_key"] = env_key
        generated_key = None

    config = _validate_config(data)
    if generated_key is not None:
        created_file = False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created_file = True
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                yaml.safe_dump(data, file, sort_keys=False)
        except OSError as exc:
            if created_file:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                except OSError as cleanup_error:
                    logger.warning("Could not remove incomplete config.yaml: %s", cleanup_error)
            logger.warning(
                "Could not persist config.yaml; using an in-memory admin key: %s", exc
            )
            logger.warning("Generated admin_key for this run: %s", generated_key)
        else:
            logger.warning("Generated admin_key (saved to config.yaml): %s", generated_key)
    return config
