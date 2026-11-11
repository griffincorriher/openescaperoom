import pytest

from app.config import (
    AppConfig,
    GameConfig,
    GamesConfig,
    LimitsConfig,
    RoomsConfig,
    SecurityConfig,
    ServerConfig,
    UploadsConfig,
)
from app.games import GameRegistry, GameRegistryError, JOIN_CODE_ALPHABET


def make_config(*, max_concurrent=50, max_players_per_game=40, idle_minutes=30):
    return AppConfig(
        server=ServerConfig(8000, (), ()),
        security=SecurityConfig("test-admin-key"),
        games=GamesConfig(
            "key", max_concurrent, max_players_per_game, 10, idle_minutes, 10
        ),
        rooms=RoomsConfig("rooms"),
        uploads=UploadsConfig(False, "key", "private", 120, 50, 200, 200, 1024, 5),
        game=GameConfig(8, 300),
        limits=LimitsConfig(20, 10, 20),
    )


def test_create_join_code_capacity_and_room_validation():
    registry = GameRegistry(make_config(max_concurrent=1, max_players_per_game=2))
    game = registry.create("host-player", "sample_room", now=10)

    assert len(game.code) == 5
    assert set(game.code) <= set(JOIN_CODE_ALPHABET)
    assert game.host_player_id == "host-player"
    assert game.room_id == "sample_room"
    assert len(game.host_token) >= 40
    assert registry.join(game.code.lower(), "guest-player", now=11) is game

    with pytest.raises(GameRegistryError, match="game_full"):
        registry.join(game.code, "another-player", now=12)
    with pytest.raises(GameRegistryError, match="game_limit_reached"):
        registry.create("another-host", now=13)
    with pytest.raises(GameRegistryError, match="invalid_room_id"):
        GameRegistry(make_config()).create("host-player", "../room")


def test_reconnect_requires_game_scoped_host_token():
    registry = GameRegistry(make_config())
    first = registry.create("host-one", now=10)
    second = registry.create("host-two", now=11)

    with pytest.raises(GameRegistryError, match="invalid_host_token"):
        registry.reconnect(second.game_id, "host-two", first.host_token, now=12)
    with pytest.raises(GameRegistryError, match="invalid_host_token"):
        registry.reconnect(second.game_id, "host-two", "🔑", now=12)

    game, is_host = registry.reconnect(
        first.game_id, "host-one", first.host_token, now=13
    )
    assert game is first
    assert is_host
    assert first.players["host-one"].connected

    guest = registry.join(first.code, "guest", now=14)
    game, is_host = registry.reconnect(first.game_id, "guest", now=15)
    assert game is guest
    assert not is_host


def test_idle_cleanup_preserves_active_games_and_removes_expired_codes():
    registry = GameRegistry(make_config(idle_minutes=1))
    active = registry.create("active-host", now=0)
    idle = registry.create("idle-host", now=0)
    ended = registry.create("ended-host", now=0)
    registry.connect_player(active, "active-host", now=0)
    registry.disconnect_player(idle.game_id, "idle-host", now=1)
    registry.connect_player(ended, "ended-host", now=0)
    registry.end_game(ended.game_id, now=2)

    assert registry.cleanup_idle(now=60) == 0
    assert registry.cleanup_idle(now=62) == 2
    assert active.game_id in registry.games_by_id
    assert idle.game_id not in registry.games_by_id
    assert ended.game_id not in registry.games_by_id
    with pytest.raises(GameRegistryError, match="game_not_found"):
        registry.join(idle.code, "late-player", now=63)


def test_game_codes_are_unique():
    registry = GameRegistry(make_config())
    games = [registry.create(f"host-{index}") for index in range(25)]

    assert len({game.code for game in games}) == len(games)
    assert len({game.game_id for game in games}) == len(games)
