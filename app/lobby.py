from __future__ import annotations

import re
import secrets
import unicodedata
from dataclasses import dataclass, field

from app.config import AppConfig
from app.games import Game

PLAYER_NAME_MAX_LENGTH = 24
TEAM_NAME_MAX_LENGTH = 30
TEAM_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,32}$")


class LobbyError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass
class LobbyPlayer:
    player_id: str
    name: str | None = None
    team_id: str | None = None


@dataclass
class LobbyTeam:
    team_id: str
    name: str


@dataclass
class LobbyState:
    players: dict[str, LobbyPlayer] = field(default_factory=dict)
    teams: dict[str, LobbyTeam] = field(default_factory=dict)
    teams_locked: bool = False
    phase: str = "lobby"


class LobbyManager:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.states: dict[str, LobbyState] = {}

    def create_game(self, game: Game) -> LobbyState:
        state = LobbyState()
        self.states[game.game_id] = state
        for player_id in game.players:
            state.players[player_id] = LobbyPlayer(player_id)
        if game.is_playtest:
            team_id = secrets.token_urlsafe(12)
            state.teams[team_id] = LobbyTeam(team_id, "Playtest")
            player = state.players[game.host_player_id]
            player.name = "Playtester"
            player.team_id = team_id
        return state

    def add_player(self, game: Game, player_id: str) -> None:
        state = self._state(game)
        state.players.setdefault(player_id, LobbyPlayer(player_id))

    def remove_player(self, game: Game, player_id: str) -> None:
        state = self._state(game)
        state.players.pop(player_id, None)

    def remove_game(self, game_id: str) -> None:
        self.states.pop(game_id, None)

    def prune(self, active_game_ids: set[str]) -> None:
        for game_id in self.states.keys() - active_game_ids:
            self.states.pop(game_id, None)

    def snapshot(self, game: Game, *, recipient_id: str) -> dict[str, object]:
        state = self._state(game)
        return {
            "type": "lobby.snapshot",
            "game_id": game.game_id,
            "code": game.code,
            "is_playtest": game.is_playtest,
            "phase": state.phase,
            "teams_locked": state.teams_locked,
            "is_host": recipient_id == game.host_player_id,
            "player_id": recipient_id,
            "max_players": self.config.games.max_players_per_game,
            "max_teams": self.config.games.max_teams_per_game,
            "max_team_size": game.max_team_size,
            "players": [
                {
                    "player_id": player.player_id,
                    "name": player.name or "Choosing a name",
                    "team_id": player.team_id,
                    "connected": bool(
                        game.players.get(player.player_id)
                        and game.players[player.player_id].connected
                    ),
                    "is_host": player.player_id == game.host_player_id,
                }
                for player in state.players.values()
            ],
            "teams": [
                {
                    "team_id": team.team_id,
                    "name": team.name,
                    "player_count": self._team_size(state, team.team_id),
                    "max_team_size": game.max_team_size,
                    "solved": 0,
                    "player_ids": [
                        player.player_id
                        for player in state.players.values()
                        if player.team_id == team.team_id
                    ],
                }
                for team in state.teams.values()
            ],
        }

    def handle(
        self,
        game: Game,
        player_id: str,
        *,
        is_host: bool,
        action: str,
        payload: dict[str, object],
    ) -> dict[str, object] | None:
        state = self._state(game)
        player = state.players.get(player_id)
        if player is None:
            raise LobbyError("player_not_found")
        if game.is_playtest and action not in {"lobby.set_name", "lobby.start"}:
            raise LobbyError("playtest_solo_only")

        if action == "lobby.set_name":
            player.name = self._validated_name(
                payload.get("name"), PLAYER_NAME_MAX_LENGTH, "invalid_player_name"
            )
        elif action == "lobby.create_team":
            self._require_lobby_open(state)
            self._require_teams_unlocked(state)
            self._require_named_player(player)
            name = self._validated_name(
                payload.get("name"), TEAM_NAME_MAX_LENGTH, "invalid_team_name"
            )
            if len(state.teams) >= self.config.games.max_teams_per_game:
                raise LobbyError("max_teams_reached")
            self._require_unique_team_name(state, name)
            team_id = secrets.token_urlsafe(9)
            state.teams[team_id] = LobbyTeam(team_id, name)
            player.team_id = team_id
        elif action == "lobby.join_team":
            if state.phase == "lobby":
                self._require_teams_unlocked(state)
            elif player.team_id is not None:
                raise LobbyError("teams_locked")
            self._require_named_player(player)
            team_id = self._require_team_id(payload.get("team_id"))
            team = state.teams.get(team_id)
            if team is None:
                raise LobbyError("team_not_found")
            if (
                state.phase == "lobby"
                and player.team_id != team_id
                and self._team_size(state, team_id) >= game.max_team_size
            ):
                raise LobbyError("team_full")
            player.team_id = team_id
        elif action == "lobby.leave_team":
            self._require_lobby_open(state)
            self._require_teams_unlocked(state)
            self._require_named_player(player)
            player.team_id = None
        elif action == "lobby.delete_team":
            self._require_host(is_host)
            self._require_lobby_open(state)
            team_id = self._require_team_id(payload.get("team_id"))
            if team_id not in state.teams:
                raise LobbyError("team_not_found")
            if self._team_size(state, team_id):
                raise LobbyError("team_not_empty")
            state.teams.pop(team_id)
        elif action == "lobby.rename_team":
            self._require_host(is_host)
            team_id = self._require_team_id(payload.get("team_id"))
            team = state.teams.get(team_id)
            if team is None:
                raise LobbyError("team_not_found")
            name = self._validated_name(
                payload.get("name"), TEAM_NAME_MAX_LENGTH, "invalid_team_name"
            )
            self._require_unique_team_name(state, name, except_team_id=team_id)
            team.name = name
        elif action == "lobby.move_player":
            self._require_host(is_host)
            target_player_id = payload.get("player_id")
            if not isinstance(target_player_id, str) or target_player_id not in state.players:
                raise LobbyError("player_not_found")
            team_id = payload.get("team_id")
            if team_id is None:
                state.players[target_player_id].team_id = None
            else:
                validated_team_id = self._require_team_id(team_id)
                if validated_team_id not in state.teams:
                    raise LobbyError("team_not_found")
                if (
                    state.phase == "lobby"
                    and state.players[target_player_id].team_id != validated_team_id
                    and self._team_size(state, validated_team_id) >= game.max_team_size
                ):
                    raise LobbyError("team_full")
                state.players[target_player_id].team_id = validated_team_id
        elif action == "lobby.auto_balance":
            self._require_host(is_host)
            self._require_lobby_open(state)
            assignments = self._plan_auto_balance(state, game.max_team_size)
            for target_player_id, team_id in assignments:
                state.players[target_player_id].team_id = team_id
            return {
                "type": "lobby.auto_balanced",
                "assigned_count": len(assignments),
            }
        elif action == "lobby.lock_teams":
            self._require_host(is_host)
            self._require_lobby_open(state)
            locked = payload.get("locked")
            if type(locked) is not bool:
                raise LobbyError("invalid_lock_state")
            state.teams_locked = locked
        elif action == "lobby.start":
            self._require_host(is_host)
            self._require_lobby_open(state)
            if any(not value.name for value in state.players.values()):
                raise LobbyError("names_required")
            assignments = self._plan_auto_balance(state, game.max_team_size)
            future_sizes = {
                team_id: self._team_size(state, team_id) for team_id in state.teams
            }
            for _, team_id in assignments:
                future_sizes[team_id] += 1
            active_teams = {
                team_id: size for team_id, size in future_sizes.items() if size > 0
            }
            if not active_teams:
                raise LobbyError("no_teams")
            minimum_size = game.min_team_size
            undersized = [
                {
                    "team_id": team_id,
                    "name": state.teams[team_id].name,
                    "player_count": size,
                    "min_team_size": minimum_size,
                }
                for team_id, size in active_teams.items()
                if size < minimum_size
            ]
            if undersized and payload.get("override_minimum") is not True:
                return {"type": "lobby.start_warning", "undersized_teams": undersized}
            for target_player_id, team_id in assignments:
                state.players[target_player_id].team_id = team_id
            state.teams = {
                team_id: team
                for team_id, team in state.teams.items()
                if future_sizes[team_id] > 0
            }
            state.teams_locked = True
            state.phase = "playing"
            return {
                "type": "lobby.started",
                "auto_assigned": [
                    {
                        "player_id": target_player_id,
                        "name": state.players[target_player_id].name or "Player",
                        "team_id": team_id,
                        "team_name": state.teams[team_id].name,
                    }
                    for target_player_id, team_id in assignments
                ],
            }
        else:
            raise LobbyError("unsupported_lobby_action")
        return None

    def _state(self, game: Game) -> LobbyState:
        state = self.states.get(game.game_id)
        if state is None:
            state = self.create_game(game)
        for player_id in game.players:
            state.players.setdefault(player_id, LobbyPlayer(player_id))
        return state

    @staticmethod
    def _validated_name(value: object, max_length: int, error_code: str) -> str:
        if not isinstance(value, str):
            raise LobbyError(error_code)
        name = value.strip()
        if not name or len(name) > max_length:
            raise LobbyError(error_code)
        if any(unicodedata.category(character).startswith("C") for character in name):
            raise LobbyError(error_code)
        return name

    @staticmethod
    def _require_team_id(value: object) -> str:
        if not isinstance(value, str) or not TEAM_ID_PATTERN.fullmatch(value):
            raise LobbyError("team_not_found")
        return value

    @staticmethod
    def _require_host(is_host: bool) -> None:
        if not is_host:
            raise LobbyError("host_only")

    @staticmethod
    def _require_lobby_open(state: LobbyState) -> None:
        if state.phase != "lobby":
            raise LobbyError("game_already_started")

    @staticmethod
    def _require_teams_unlocked(state: LobbyState) -> None:
        if state.teams_locked:
            raise LobbyError("teams_locked")

    @staticmethod
    def _require_named_player(player: LobbyPlayer) -> None:
        if not player.name:
            raise LobbyError("name_required")

    @staticmethod
    def _require_unique_team_name(
        state: LobbyState, name: str, *, except_team_id: str | None = None
    ) -> None:
        normalized = name.casefold()
        if any(
            team.team_id != except_team_id and team.name.casefold() == normalized
            for team in state.teams.values()
        ):
            raise LobbyError("duplicate_team_name")

    def _team_size(self, state: LobbyState, team_id: str) -> int:
        return sum(player.team_id == team_id for player in state.players.values())

    def _plan_auto_balance(
        self, state: LobbyState, max_team_size: int
    ) -> list[tuple[str, str]]:
        sizes = {team_id: self._team_size(state, team_id) for team_id in state.teams}
        candidates = [
            player.player_id for player in state.players.values() if player.team_id is None
        ]
        assignments: list[tuple[str, str]] = []
        for player_id in candidates:
            available_teams = [
                team_id
                for team_id, size in sizes.items()
                if size < max_team_size
            ]
            if not available_teams:
                raise LobbyError("team_capacity")
            team_id = min(available_teams, key=lambda value: (sizes[value], value))
            sizes[team_id] += 1
            assignments.append((player_id, team_id))
        return assignments
