from __future__ import annotations

import hmac
import re
import secrets
import time
from dataclasses import dataclass, field

from app.config import AppConfig

JOIN_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
JOIN_CODE_PATTERN = re.compile(r"^[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{5}$")
GAME_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,64}$")
ROOM_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
MAX_CODE_GENERATION_ATTEMPTS = 32


class GameRegistryError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass
class GamePlayer:
    player_id: str
    connected: bool = False


@dataclass
class Game:
    game_id: str
    code: str
    host_token: str
    host_player_id: str
    room_id: str | None
    created_at: float
    last_activity: float
    players: dict[str, GamePlayer] = field(default_factory=dict)
    kicked_player_ids: set[str] = field(default_factory=set)
    ended_at: float | None = None
    min_team_size: int = 1
    max_team_size: int = 8
    is_playtest: bool = False
    skip_penalty_sec: int = 300


class GameRegistry:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.games_by_id: dict[str, Game] = {}
        self.game_id_by_code: dict[str, str] = {}

    def create(
        self,
        player_id: str,
        room_id: str | None = None,
        *,
        is_playtest: bool = False,
        now: float | None = None,
    ) -> Game:
        current_time = time.monotonic() if now is None else now
        if len(self.games_by_id) >= self.config.games.max_concurrent:
            raise GameRegistryError("game_limit_reached")
        if room_id is not None and not ROOM_ID_PATTERN.fullmatch(room_id):
            raise GameRegistryError("invalid_room_id")

        code = "" if is_playtest else self._new_join_code()
        game_id = self._new_game_id()
        game = Game(
            game_id=game_id,
            code=code,
            host_token=secrets.token_urlsafe(32),
            host_player_id=player_id,
            room_id=room_id,
            created_at=current_time,
            last_activity=current_time,
            players={player_id: GamePlayer(player_id=player_id)},
            max_team_size=self.config.game.max_team_size,
            is_playtest=is_playtest,
            skip_penalty_sec=self.config.game.skip_penalty_sec,
        )
        self.games_by_id[game_id] = game
        if code:
            self.game_id_by_code[code] = game_id
        return game

    def join(self, code: str, player_id: str, *, now: float | None = None) -> Game:
        normalized_code = code.upper()
        if not JOIN_CODE_PATTERN.fullmatch(normalized_code):
            raise GameRegistryError("invalid_join_code")
        game_id = self.game_id_by_code.get(normalized_code)
        game = self.games_by_id.get(game_id) if game_id else None
        if game is None:
            raise GameRegistryError("game_not_found")
        if game.is_playtest:
            raise GameRegistryError("game_not_found")
        if game.ended_at is not None:
            raise GameRegistryError("game_ended")
        if player_id in game.kicked_player_ids:
            raise GameRegistryError("player_kicked")
        player = game.players.get(player_id)
        if player is None and len(game.players) >= self.config.games.max_players_per_game:
            raise GameRegistryError("game_full")
        if player is None:
            game.players[player_id] = GamePlayer(player_id=player_id)
        game.last_activity = time.monotonic() if now is None else now
        return game

    def reconnect(
        self,
        game_id: str,
        player_id: str,
        host_token: str | None = None,
        *,
        now: float | None = None,
    ) -> tuple[Game, bool]:
        if not GAME_ID_PATTERN.fullmatch(game_id):
            raise GameRegistryError("game_not_found")
        game = self.games_by_id.get(game_id)
        if game is None:
            raise GameRegistryError("game_not_found")
        if player_id not in game.players:
            if player_id in game.kicked_player_ids:
                raise GameRegistryError("player_kicked")
            raise GameRegistryError("player_not_found")

        is_host = player_id == game.host_player_id
        if is_host and (
            not isinstance(host_token, str)
            or not hmac.compare_digest(
                game.host_token.encode("utf-8"), host_token.encode("utf-8")
            )
        ):
            raise GameRegistryError("invalid_host_token")
        game.last_activity = time.monotonic() if now is None else now
        game.players[player_id].connected = True
        return game, is_host

    def connect_player(self, game: Game, player_id: str, *, now: float | None = None) -> None:
        player = game.players.get(player_id)
        if player is None:
            raise GameRegistryError("player_not_found")
        player.connected = True
        game.last_activity = time.monotonic() if now is None else now

    def disconnect_player(
        self, game_id: str, player_id: str, *, now: float | None = None
    ) -> None:
        game = self.games_by_id.get(game_id)
        if game is None:
            return
        player = game.players.get(player_id)
        if player is not None:
            player.connected = False
            game.last_activity = time.monotonic() if now is None else now

    def end_game(self, game_id: str, *, now: float | None = None) -> None:
        game = self.games_by_id.get(game_id)
        if game is not None:
            game.ended_at = time.monotonic() if now is None else now
            game.last_activity = game.ended_at

    def cleanup_idle(self, *, now: float | None = None) -> int:
        current_time = time.monotonic() if now is None else now
        idle_seconds = self.config.games.idle_minutes * 60
        expired_ids = [
            game_id
            for game_id, game in self.games_by_id.items()
            if (
                game.ended_at is not None
                and current_time - game.ended_at >= idle_seconds
            )
            or (
                game.ended_at is None
                and not any(player.connected for player in game.players.values())
                and current_time - game.last_activity >= idle_seconds
            )
        ]
        for game_id in expired_ids:
            game = self.games_by_id.pop(game_id)
            if game.code:
                self.game_id_by_code.pop(game.code, None)
        return len(expired_ids)

    def _new_join_code(self) -> str:
        for _ in range(MAX_CODE_GENERATION_ATTEMPTS):
            code = "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(5))
            if code not in self.game_id_by_code:
                return code
        raise GameRegistryError("join_code_generation_failed")

    def _new_game_id(self) -> str:
        while True:
            game_id = secrets.token_urlsafe(16)
            if game_id not in self.games_by_id:
                return game_id
