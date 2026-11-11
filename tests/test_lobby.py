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
from app.games import GameRegistry
from app.lobby import LobbyError, LobbyManager, LobbyTeam


def create_lobby(*, max_team_size=8, max_teams_per_game=10):
    config = AppConfig(
        server=ServerConfig(8000, (), ()),
        security=SecurityConfig("test-admin-key"),
        games=GamesConfig("key", 50, 40, max_teams_per_game, 30, 10),
        rooms=RoomsConfig("rooms"),
        uploads=UploadsConfig(False, "key", "private", 120, 50, 200, 200, 1024, 5),
        game=GameConfig(max_team_size, 300),
        limits=LimitsConfig(20, 10, 20),
    )
    games = GameRegistry(config)
    lobby = LobbyManager(config)
    game = games.create("host-player")
    lobby.create_game(game)
    return config, games, lobby, game


def set_name(lobby, game, player_id, name, *, is_host=False):
    lobby.handle(
        game,
        player_id,
        is_host=is_host,
        action="lobby.set_name",
        payload={"name": name},
    )


def test_players_create_join_change_leave_and_delete_empty_teams():
    _, _, lobby, game = create_lobby(max_team_size=2)
    lobby.add_player(game, "guest-player")
    lobby.add_player(game, "other-player")
    set_name(lobby, game, "host-player", "Host", is_host=True)
    set_name(lobby, game, "guest-player", "Guest")
    set_name(lobby, game, "other-player", "Other")

    lobby.handle(
        game,
        "host-player",
        is_host=True,
        action="lobby.create_team",
        payload={"name": "Owls"},
    )
    state = lobby.states[game.game_id]
    owls = next(iter(state.teams))
    assert state.players["host-player"].team_id == owls

    with pytest.raises(LobbyError, match="duplicate_team_name"):
        lobby.handle(
            game,
            "guest-player",
            is_host=False,
            action="lobby.create_team",
            payload={"name": "OWLS"},
        )

    lobby.handle(
        game,
        "guest-player",
        is_host=False,
        action="lobby.join_team",
        payload={"team_id": owls},
    )
    with pytest.raises(LobbyError, match="team_full"):
        lobby.handle(
            game,
            "other-player",
            is_host=False,
            action="lobby.join_team",
            payload={"team_id": owls},
        )

    lobby.handle(
        game,
        "guest-player",
        is_host=False,
        action="lobby.leave_team",
        payload={},
    )
    lobby.handle(
        game,
        "host-player",
        is_host=True,
        action="lobby.create_team",
        payload={"name": "Foxes"},
    )
    foxes = next(team_id for team_id in state.teams if team_id != owls)
    lobby.handle(
        game,
        "host-player",
        is_host=True,
        action="lobby.join_team",
        payload={"team_id": owls},
    )
    lobby.handle(
        game,
        "host-player",
        is_host=True,
        action="lobby.delete_team",
        payload={"team_id": foxes},
    )
    assert foxes not in state.teams
    with pytest.raises(LobbyError, match="team_not_empty"):
        lobby.handle(
            game,
            "host-player",
            is_host=True,
            action="lobby.delete_team",
            payload={"team_id": owls},
        )


def test_team_names_and_player_names_enforce_limits_and_control_characters():
    _, _, lobby, game = create_lobby()
    for bad_name in (" ", "x" * 25, "line\nbreak"):
        with pytest.raises(LobbyError, match="invalid_player_name"):
            set_name(lobby, game, "host-player", bad_name, is_host=True)
    set_name(lobby, game, "host-player", "Host", is_host=True)

    with pytest.raises(LobbyError, match="invalid_team_name"):
        lobby.handle(
            game,
            "host-player",
            is_host=True,
            action="lobby.create_team",
            payload={"name": "x" * 31},
        )


def test_host_controls_are_authorized_and_team_lock_blocks_player_switching():
    _, _, lobby, game = create_lobby()
    lobby.add_player(game, "guest-player")
    set_name(lobby, game, "host-player", "Host", is_host=True)
    set_name(lobby, game, "guest-player", "Guest")
    lobby.handle(
        game,
        "host-player",
        is_host=True,
        action="lobby.create_team",
        payload={"name": "Owls"},
    )
    team_id = next(iter(lobby.states[game.game_id].teams))

    with pytest.raises(LobbyError, match="host_only"):
        lobby.handle(
            game,
            "guest-player",
            is_host=False,
            action="lobby.lock_teams",
            payload={"locked": True},
        )
    lobby.handle(
        game,
        "host-player",
        is_host=True,
        action="lobby.lock_teams",
        payload={"locked": True},
    )
    with pytest.raises(LobbyError, match="teams_locked"):
        lobby.handle(
            game,
            "guest-player",
            is_host=False,
            action="lobby.join_team",
            payload={"team_id": team_id},
        )

    lobby.handle(
        game,
        "host-player",
        is_host=True,
        action="lobby.move_player",
        payload={"player_id": "guest-player", "team_id": team_id},
    )
    assert lobby.states[game.game_id].players["guest-player"].team_id == team_id


def test_host_move_respects_team_capacity_before_start():
    _, _, lobby, game = create_lobby(max_team_size=1)
    lobby.add_player(game, "guest-player")
    set_name(lobby, game, "host-player", "Host", is_host=True)
    set_name(lobby, game, "guest-player", "Guest")
    lobby.handle(
        game,
        "host-player",
        is_host=True,
        action="lobby.create_team",
        payload={"name": "Owls"},
    )
    team_id = next(iter(lobby.states[game.game_id].teams))

    with pytest.raises(LobbyError, match="team_full"):
        lobby.handle(
            game,
            "host-player",
            is_host=True,
            action="lobby.move_player",
            payload={"player_id": "guest-player", "team_id": team_id},
        )


def test_auto_balance_start_warning_and_override():
    _, games, lobby, game = create_lobby()
    game.min_team_size = 2
    for player_id in ("second-player", "third-player"):
        games.join(game.code, player_id)
        lobby.add_player(game, player_id)
        set_name(lobby, game, player_id, player_id)
    set_name(lobby, game, "host-player", "Host", is_host=True)
    lobby.handle(
        game,
        "host-player",
        is_host=True,
        action="lobby.create_team",
        payload={"name": "Owls"},
    )
    lobby.handle(
        game,
        "host-player",
        is_host=True,
        action="lobby.create_team",
        payload={"name": "Foxes"},
    )

    warning = lobby.handle(
        game,
        "host-player",
        is_host=True,
        action="lobby.start",
        payload={},
    )
    assert warning["type"] == "lobby.start_warning"
    assert game.game_id in lobby.states
    assert lobby.states[game.game_id].phase == "lobby"

    started = lobby.handle(
        game,
        "host-player",
        is_host=True,
        action="lobby.start",
        payload={"override_minimum": True},
    )
    assert started["type"] == "lobby.started"
    assert {entry["player_id"] for entry in started["auto_assigned"]} == {
        "second-player",
        "third-player",
    }
    state = lobby.states[game.game_id]
    assert state.phase == "playing"
    assert state.teams_locked
    assert len(state.teams) == 2
    assert all(player.team_id is not None for player in state.players.values())


def test_late_joiner_may_join_full_team_but_existing_players_cannot_switch():
    config, games, lobby, game = create_lobby(max_team_size=2)
    state = lobby.states[game.game_id]
    team_id = "static-team-id"
    state.teams[team_id] = LobbyTeam(team_id, "Owls")
    state.phase = "playing"
    state.teams_locked = True
    for player_id in ("host-player", "old-player"):
        games.join(game.code, player_id)
        lobby.add_player(game, player_id)
        state.players[player_id].name = player_id
        state.players[player_id].team_id = team_id
    games.join(game.code, "late-player")
    lobby.add_player(game, "late-player")
    set_name(lobby, game, "late-player", "Late")

    lobby.handle(
        game,
        "late-player",
        is_host=False,
        action="lobby.join_team",
        payload={"team_id": team_id},
    )
    assert lobby.snapshot(game, recipient_id="late-player")["teams"][0][
        "player_count"
    ] == 3

    with pytest.raises(LobbyError, match="teams_locked"):
        lobby.handle(
            game,
            "old-player",
            is_host=False,
            action="lobby.join_team",
            payload={"team_id": team_id},
        )
    assert config.game.max_team_size == 2
