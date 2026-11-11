from __future__ import annotations

import asyncio
import hmac
import json
import re
from dataclasses import dataclass

from fastapi import WebSocket, WebSocketDisconnect

from app.config import AppConfig
from app.escape.engine import EscapeEngine, EscapeEngineError
from app.escape.store import RoomStore
from app.games import Game, GameRegistry, GameRegistryError
from app.lobby import LobbyError, LobbyManager
from app.security import ConnectionLimiter, SlidingWindowRateLimiter, get_client_ip

PLAYER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
MAX_MESSAGE_BYTES = 4096
IDLE_CLEANUP_INTERVAL_SECONDS = 30


@dataclass
class PlayerConnection:
    websocket: WebSocket
    client_ip: str
    player_id: str
    game_id: str | None = None
    is_host: bool = False


class WebSocketHub:
    def __init__(
        self,
        config: AppConfig,
        games: GameRegistry,
        lobbies: LobbyManager,
        rooms: RoomStore,
        escape_engine: EscapeEngine,
    ) -> None:
        self.config = config
        self.games = games
        self.lobbies = lobbies
        self.rooms = rooms
        self.escape_engine = escape_engine
        self.connections: dict[tuple[str | None, str], PlayerConnection] = {}
        self._connection_limiter = ConnectionLimiter()
        self._message_limiter = SlidingWindowRateLimiter()
        self._create_limiter = SlidingWindowRateLimiter()
        self._join_limiter = SlidingWindowRateLimiter()
        self._lock = asyncio.Lock()

    async def serve(self, websocket: WebSocket, player_id: str) -> None:
        if not PLAYER_ID_PATTERN.fullmatch(player_id):
            await websocket.close(code=1008, reason="Invalid player ID")
            return

        remote_address = websocket.client.host if websocket.client else None
        client_ip = get_client_ip(
            remote_address,
            websocket.headers.get("x-forwarded-for"),
            self.config.server.trusted_proxies,
        )

        async with self._lock:
            connection_key = (None, player_id)
            previous = self.connections.get(connection_key)
            replacing_ip = previous.client_ip if previous else None
            if not self._connection_limiter.acquire(
                client_ip,
                limit=self.config.limits.ws_connections_per_ip,
                replacing_ip=replacing_ip,
            ):
                await websocket.close(code=4429, reason="Too many connections")
                return
            connection = PlayerConnection(websocket, client_ip, player_id)
            accepted = False
            try:
                await websocket.accept()
                accepted = True
            finally:
                if not accepted:
                    self._connection_limiter.release(client_ip)
            if previous is not None:
                self._disconnect(previous)
            self.connections[connection_key] = connection
            if previous:
                self._connection_limiter.release(previous.client_ip)

        if previous:
            await previous.websocket.close(code=4001, reason="Reconnected")

        try:
            await self._receive_messages(connection)
        except WebSocketDisconnect:
            pass
        finally:
            async with self._lock:
                current_key = (connection.game_id, player_id)
                current = self.connections.get(current_key)
                if current is not None and current.websocket is websocket:
                    self.connections.pop(current_key)
                    self._disconnect(connection)
                    self._connection_limiter.release(client_ip)

    def _disconnect(self, connection: PlayerConnection) -> None:
        if connection.game_id is not None:
            self.games.disconnect_player(connection.game_id, connection.player_id)

    async def _associate(
        self, connection: PlayerConnection, game: Game, *, is_host: bool
    ) -> None:
        key = (game.game_id, connection.player_id)
        previous: PlayerConnection | None = None
        async with self._lock:
            current_key = (connection.game_id, connection.player_id)
            if self.connections.get(current_key) is connection:
                self.connections.pop(current_key)
            previous = self.connections.get(key)
            if previous is not None and previous is not connection:
                self.connections.pop(key)
                self._disconnect(previous)
                self._connection_limiter.release(previous.client_ip)
            connection.game_id = game.game_id
            connection.is_host = is_host
            self.connections[key] = connection
            self.games.connect_player(game, connection.player_id)
        if previous is not None and previous is not connection:
            await previous.websocket.close(code=4001, reason="Reconnected")

    async def _receive_messages(self, connection: PlayerConnection) -> None:
        websocket = connection.websocket
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            if message.get("bytes") is not None:
                await websocket.close(code=1003, reason="Text messages only")
                return

            text = message.get("text")
            if text is None or len(text.encode("utf-8")) > MAX_MESSAGE_BYTES:
                await websocket.close(code=1009, reason="Message too large")
                return
            if not self._message_limiter.allow(
                connection.client_ip,
                limit=self.config.limits.ws_messages_per_sec,
                window_seconds=1,
            ):
                await websocket.close(code=4429, reason="Message rate limit exceeded")
                return

            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "error": "invalid_message"})
                continue
            if not isinstance(payload, dict) or not isinstance(payload.get("type"), str):
                await websocket.send_json({"type": "error", "error": "unsupported_message"})
                continue
            action = payload["type"]
            if action == "ping":
                await websocket.send_json({"type": "pong"})
            elif action == "game.leave":
                await self._leave_ended_game(connection)
            elif action == "rooms.list":
                await websocket.send_json(
                    {"type": "rooms.list", "rooms": self.rooms.catalog()}
                )
            elif action == "game.create":
                await self._create_game(connection, payload)
            elif action == "game.playtest":
                await self._create_game(connection, payload, is_playtest=True)
            elif action == "game.join":
                await self._join_game(connection, payload)
            elif action == "game.reconnect":
                await self._reconnect_game(connection, payload)
            elif action.startswith("lobby."):
                await self._lobby_action(connection, action, payload)
            elif action.startswith("puzzle."):
                await self._puzzle_action(connection, action, payload)
            elif action.startswith("host."):
                await self._host_action(connection, action, payload)
            else:
                await websocket.send_json({"type": "error", "error": "unsupported_message"})

    async def _send_lobby_snapshot(self, game: Game) -> None:
        for connection in tuple(self.connections.values()):
            if connection.game_id == game.game_id:
                lobby_snapshot = self.lobbies.snapshot(
                    game, recipient_id=connection.player_id
                )
                await connection.websocket.send_json(lobby_snapshot)
                lobby_state = self.lobbies.states.get(game.game_id)
                lobby_player = (
                    lobby_state.players.get(connection.player_id)
                    if lobby_state is not None
                    else None
                )
                if (
                    game.game_id in self.escape_engine.games
                    and lobby_player is not None
                    and lobby_player.team_id is not None
                ):
                    await connection.websocket.send_json(
                        self.escape_engine.snapshot(
                            game, recipient_id=connection.player_id
                        )
                    )

    async def _send_game_snapshots(self, game: Game) -> None:
        lobby_state = self.lobbies.states.get(game.game_id)
        if lobby_state is None:
            return
        for connection in tuple(self.connections.values()):
            player = lobby_state.players.get(connection.player_id)
            if (
                connection.game_id == game.game_id
                and player is not None
                and player.team_id is not None
            ):
                await connection.websocket.send_json(
                    self.escape_engine.snapshot(
                        game, recipient_id=connection.player_id
                    )
                )

    async def _broadcast_team_event(
        self, game_id: str, team_id: str, event: dict[str, object]
    ) -> None:
        state = self.escape_engine.games.get(game_id)
        if state is None:
            return
        team = state.teams.get(team_id)
        if team is None:
            return
        for player_id in team.members:
            connection = self.connections.get((game_id, player_id))
            if connection is not None:
                await connection.websocket.send_json(event)

    async def _broadcast_game_event(self, game: Game, event: dict[str, object]) -> None:
        for connection in tuple(self.connections.values()):
            if connection.game_id == game.game_id:
                await connection.websocket.send_json(event)

    async def _lobby_action(
        self,
        connection: PlayerConnection,
        action: str,
        payload: dict[str, object],
    ) -> None:
        websocket = connection.websocket
        game = (
            self.games.games_by_id.get(connection.game_id)
            if connection.game_id is not None
            else None
        )
        if game is None:
            await websocket.send_json({"type": "error", "error": "not_in_game"})
            return
        if connection.is_host != (connection.player_id == game.host_player_id):
            await websocket.send_json({"type": "error", "error": "host_only"})
            return
        try:
            result = self.lobbies.handle(
                game,
                connection.player_id,
                is_host=connection.is_host,
                action=action,
                payload=payload,
            )
        except LobbyError as exc:
            await websocket.send_json({"type": "error", "error": exc.code})
            return
        if result is not None and result.get("type") == "lobby.started":
            try:
                self.escape_engine.start(game)
            except EscapeEngineError as exc:
                await websocket.send_json({"type": "error", "error": exc.code})
                return
            await self._broadcast_game_event(game, result)
        elif result is not None:
            await websocket.send_json(result)
        if result is None or result.get("type") == "lobby.started":
            await self._send_lobby_snapshot(game)

    async def _puzzle_action(
        self,
        connection: PlayerConnection,
        action: str,
        payload: dict[str, object],
    ) -> None:
        websocket = connection.websocket
        game = (
            self.games.games_by_id.get(connection.game_id)
            if connection.game_id is not None
            else None
        )
        if game is None:
            await websocket.send_json({"type": "error", "error": "not_in_game"})
            return
        puzzle_id = payload.get("puzzle_id")
        if not isinstance(puzzle_id, str):
            await websocket.send_json({"type": "error", "error": "puzzle_not_found"})
            return
        try:
            if action == "puzzle.open":
                puzzle = self.escape_engine.open_puzzle(
                    game, connection.player_id, puzzle_id
                )
                await websocket.send_json({"type": "game.puzzle", "puzzle": puzzle})
                state = self.escape_engine.games[game.game_id]
                team = self.escape_engine._team_for_player(
                    state, connection.player_id
                )
                activity = {
                    "type": "game.activity",
                    "activity": {
                        "type": "open",
                        "puzzle_id": puzzle_id,
                        "elapsed_sec": self.escape_engine.clock(game)[
                            "elapsed_sec"
                        ],
                        "player_id": connection.player_id,
                    },
                }
                for player_id in team.members - {connection.player_id}:
                    recipient = self.connections.get((game.game_id, player_id))
                    if recipient is not None:
                        await recipient.websocket.send_json(activity)
                return
            if action == "puzzle.submit":
                result = self.escape_engine.submit_answer(
                    game, connection.player_id, puzzle_id, payload.get("answer")
                )
                state = self.escape_engine.games[game.game_id]
                team = self.escape_engine._team_for_player(state, connection.player_id)
                await self._broadcast_team_event(
                    game.game_id,
                    team.team_id,
                    {
                        "type": "game.answer_result",
                        "puzzle_id": puzzle_id,
                        **result,
                    },
                )
                if state.ended_at is not None:
                    self.games.end_game(game.game_id)
                await self._send_game_snapshots(game)
                return
            if action == "puzzle.hint":
                result = self.escape_engine.take_hint(
                    game, connection.player_id, puzzle_id
                )
                state = self.escape_engine.games[game.game_id]
                team = self.escape_engine._team_for_player(state, connection.player_id)
                await self._broadcast_team_event(
                    game.game_id,
                    team.team_id,
                    {
                        "type": "game.hint",
                        "puzzle_id": puzzle_id,
                        **result,
                    },
                )
                await self._send_game_snapshots(game)
                return
            await websocket.send_json(
                {"type": "error", "error": "unsupported_message"}
            )
        except EscapeEngineError as exc:
            await websocket.send_json({"type": "error", "error": exc.code})

    async def _host_action(
        self,
        connection: PlayerConnection,
        action: str,
        payload: dict[str, object],
    ) -> None:
        websocket = connection.websocket
        game = (
            self.games.games_by_id.get(connection.game_id)
            if connection.game_id is not None
            else None
        )
        if game is None:
            await websocket.send_json({"type": "error", "error": "not_in_game"})
            return
        if not connection.is_host or connection.player_id != game.host_player_id:
            await websocket.send_json({"type": "error", "error": "host_only"})
            return
        try:
            if action in {"host.pause", "host.resume"}:
                await self._broadcast_game_event(
                    game,
                    self.escape_engine.set_paused(game, action == "host.pause"),
                )
                return
            if action == "host.add_time":
                minutes = payload.get("minutes")
                if type(minutes) is not int or not 1 <= minutes <= 120:
                    raise EscapeEngineError("invalid_time_amount")
                await self._broadcast_game_event(
                    game, self.escape_engine.add_time(game, minutes * 60)
                )
                return
            if action == "host.end_early":
                self.escape_engine.end_early(game)
                self.games.end_game(game.game_id)
                await self._send_game_snapshots(game)
                return
            if action == "host.skip":
                team_id = payload.get("team_id")
                puzzle_id = payload.get("puzzle_id")
                if not isinstance(team_id, str) or not isinstance(puzzle_id, str):
                    raise EscapeEngineError("invalid_host_action")
                self.escape_engine.skip_puzzle(game, team_id, puzzle_id)
                state = self.escape_engine.games[game.game_id]
                if state.ended_at is not None:
                    self.games.end_game(game.game_id)
                await self._send_game_snapshots(game)
                return
            if action == "host.message":
                text = payload.get("text")
                team_id = payload.get("team_id")
                if (
                    not isinstance(text, str)
                    or not text.strip()
                    or len(text) > 200
                    or not isinstance(team_id, str)
                    or any(ord(char) < 32 and char not in "\t\n" for char in text)
                ):
                    raise EscapeEngineError("invalid_host_message")
                event = {
                    "type": "game.host_message",
                    "text": text.strip(),
                    "team_id": team_id,
                }
                if event["team_id"] == "all":
                    await self._broadcast_game_event(game, event)
                else:
                    state = self.escape_engine.games.get(game.game_id)
                    if state is not None:
                        team = state.teams.get(event["team_id"])
                        if team is None:
                            raise EscapeEngineError("team_not_found")
                        await self._broadcast_team_event(
                            game.game_id, team.team_id, event
                        )
                    else:
                        lobby = self.lobbies.states.get(game.game_id)
                        if lobby is None or event["team_id"] not in lobby.teams:
                            raise EscapeEngineError("team_not_found")
                        for player in lobby.players.values():
                            if player.team_id == event["team_id"]:
                                recipient = self.connections.get(
                                    (game.game_id, player.player_id)
                                )
                                if recipient is not None:
                                    await recipient.websocket.send_json(event)
                return
            if action == "host.kick":
                player_id = payload.get("player_id")
                if not isinstance(player_id, str) or player_id == game.host_player_id:
                    raise EscapeEngineError("invalid_player_id")
                if player_id not in game.players:
                    raise EscapeEngineError("player_not_found")
                game.kicked_player_ids.add(player_id)
                self.lobbies.remove_player(game, player_id)
                if game.game_id in self.escape_engine.games:
                    self.escape_engine.remove_player(game, player_id)
                game.players.pop(player_id, None)
                async with self._lock:
                    target = self.connections.pop((game.game_id, player_id), None)
                    if target is not None:
                        self._disconnect(target)
                        self._connection_limiter.release(target.client_ip)
                if target is not None:
                    await target.websocket.send_json({"type": "game.kicked"})
                    await target.websocket.close(code=4003, reason="Removed by host")
                await self._send_lobby_snapshot(game)
                return
            await websocket.send_json(
                {"type": "error", "error": "unsupported_message"}
            )
        except EscapeEngineError as exc:
            await websocket.send_json({"type": "error", "error": exc.code})

    async def tick(self) -> None:
        self.escape_engine.tick()
        for game_id, game in tuple(self.games.games_by_id.items()):
            engine_state = self.escape_engine.games.get(game_id)
            if (
                engine_state is not None
                and engine_state.ended_at is not None
                and game.ended_at is None
            ):
                self.games.end_game(game_id)
                await self._send_game_snapshots(game)
            elif engine_state is not None and engine_state.ended_at is None:
                await self._broadcast_game_event(
                    game,
                    self.escape_engine.clock(game),
                )

    async def _create_game(
        self,
        connection: PlayerConnection,
        payload: dict[str, object],
        *,
        is_playtest: bool = False,
    ) -> None:
        websocket = connection.websocket
        if not await self._require_unassigned(connection):
            return
        if not self._create_limiter.allow(
            connection.client_ip,
            limit=self.config.games.creates_per_ip_per_hour,
            window_seconds=3600,
        ):
            await websocket.close(code=4429, reason="Game creation rate limit exceeded")
            return

        supplied_key = payload.get("admin_key")
        if not isinstance(supplied_key, str):
            supplied_key = ""
        if self.config.games.create == "key" and not hmac.compare_digest(
            self.config.security.admin_key.encode("utf-8"),
            supplied_key.encode("utf-8"),
        ):
            await websocket.send_json({"type": "error", "error": "invalid_admin_key"})
            return

        room_id = payload.get("room_id")
        if not self.rooms.rooms:
            await websocket.send_json({"type": "error", "error": "no_rooms_available"})
            return
        if room_id is None and len(self.rooms.rooms) == 1:
            room_id = next(iter(self.rooms.rooms))
        elif room_id is None:
            await websocket.send_json({"type": "error", "error": "room_required"})
            return
        if not isinstance(room_id, str):
            await websocket.send_json({"type": "error", "error": "invalid_room_id"})
            return
        room = self.rooms.get(room_id)
        supplied_room_token = payload.get("room_token")
        if supplied_room_token is not None and not isinstance(supplied_room_token, str):
            await websocket.send_json({"type": "error", "error": "room_not_found"})
            return
        if room is None or not self.rooms.can_access(room_id, supplied_room_token):
            await websocket.send_json({"type": "error", "error": "room_not_found"})
            return
        try:
            game = self.games.create(
                connection.player_id, room_id, is_playtest=is_playtest
            )
            self.rooms.mark_used(room_id)
            game.min_team_size = room["min_team_size"]
            game.max_team_size = min(
                game.max_team_size, room["max_team_size"]
            )
            self.lobbies.create_game(game)
            await self._associate(connection, game, is_host=True)
        except GameRegistryError as exc:
            await websocket.send_json({"type": "error", "error": exc.code})
            return
        await websocket.send_json(
            {
                "type": "game.created",
                "game_id": game.game_id,
                "code": game.code,
                "host_token": game.host_token,
                "room_id": game.room_id,
                "is_playtest": game.is_playtest,
            }
        )
        await self._send_lobby_snapshot(game)

    async def _join_game(
        self, connection: PlayerConnection, payload: dict[str, object]
    ) -> None:
        websocket = connection.websocket
        if not await self._require_unassigned(connection):
            return
        if not self._join_limiter.allow(
            connection.client_ip,
            limit=self.config.limits.join_attempts_per_ip_per_min,
            window_seconds=60,
        ):
            await websocket.close(code=4429, reason="Game join rate limit exceeded")
            return
        code = payload.get("code")
        if not isinstance(code, str):
            await websocket.send_json({"type": "error", "error": "invalid_join_code"})
            return
        try:
            game = self.games.join(code, connection.player_id)
            self.lobbies.add_player(game, connection.player_id)
            await self._associate(connection, game, is_host=False)
        except GameRegistryError as exc:
            await websocket.send_json({"type": "error", "error": exc.code})
            return
        await websocket.send_json(
            {
                "type": "game.joined",
                "game_id": game.game_id,
                "code": game.code,
                "room_id": game.room_id,
            }
        )
        await self._send_lobby_snapshot(game)

    async def _reconnect_game(
        self, connection: PlayerConnection, payload: dict[str, object]
    ) -> None:
        websocket = connection.websocket
        if not await self._require_unassigned(connection):
            return
        game_id = payload.get("game_id")
        host_token = payload.get("host_token")
        if not isinstance(game_id, str):
            await websocket.send_json({"type": "error", "error": "game_not_found"})
            return
        if host_token is not None and not isinstance(host_token, str):
            await websocket.send_json({"type": "error", "error": "invalid_host_token"})
            return
        try:
            game, is_host = self.games.reconnect(
                game_id, connection.player_id, host_token
            )
            await self._associate(connection, game, is_host=is_host)
        except GameRegistryError as exc:
            await websocket.send_json({"type": "error", "error": exc.code})
            return
        await websocket.send_json(
            {
                "type": "game.reconnected",
                "game_id": game.game_id,
                "code": game.code,
                "is_host": is_host,
            }
        )
        await self._send_lobby_snapshot(game)

    async def _require_unassigned(self, connection: PlayerConnection) -> bool:
        if connection.game_id is None:
            return True
        await connection.websocket.send_json(
            {"type": "error", "error": "already_in_game"}
        )
        return False

    async def _leave_ended_game(self, connection: PlayerConnection) -> None:
        game_id = connection.game_id
        game = self.games.games_by_id.get(game_id) if game_id is not None else None
        if game_id is not None and game is not None and game.ended_at is None:
            await connection.websocket.send_json(
                {"type": "error", "error": "game_in_progress"}
            )
            return

        already_assigned = False
        async with self._lock:
            if connection.game_id != game_id:
                already_assigned = True
            elif game_id is not None:
                self._disconnect(connection)
                previous_key = (game_id, connection.player_id)
                if self.connections.get(previous_key) is connection:
                    self.connections.pop(previous_key)
                    self.connections[(None, connection.player_id)] = connection
                connection.game_id = None
                connection.is_host = False

        if already_assigned:
            await connection.websocket.send_json(
                {"type": "error", "error": "already_in_game"}
            )
            return
        await connection.websocket.send_json({"type": "game.left"})


async def cleanup_idle_games(
    games: GameRegistry, lobbies: LobbyManager, ws_hub: WebSocketHub
) -> None:
    last_cleanup = 0.0
    while True:
        await asyncio.sleep(1)
        await ws_hub.tick()
        if asyncio.get_running_loop().time() - last_cleanup >= IDLE_CLEANUP_INTERVAL_SECONDS:
            games.cleanup_idle()
            lobbies.prune(set(games.games_by_id))
            ws_hub.escape_engine.prune(set(games.games_by_id))
            ws_hub.rooms.cleanup_uploads(
                {
                    game.room_id
                    for game in games.games_by_id.values()
                    if game.room_id is not None
                }
            )
            last_cleanup = asyncio.get_running_loop().time()
