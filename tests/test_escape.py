from pathlib import Path
import shutil

import pytest
import yaml

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
from app.escape.engine import EscapeEngine, EscapeEngineError
from app.escape.checkers import check_answer
from app.escape.loader import RoomValidationError, load_room, validate_room
from app.escape.store import RoomStore
from app.games import GameRegistry
from app.lobby import LobbyManager, LobbyTeam

ROOM_DIR = Path(__file__).resolve().parents[1] / "rooms" / "first-light"


def make_config():
    return AppConfig(
        server=ServerConfig(8000, (), ()),
        security=SecurityConfig("test-admin-key"),
        games=GamesConfig("key", 50, 40, 10, 30, 10),
        rooms=RoomsConfig("rooms"),
        uploads=UploadsConfig(False, "key", "private", 120, 50, 200, 200, 1024, 5),
        game=GameConfig(8, 300),
        limits=LimitsConfig(20, 10, 20),
    )


def make_engine():
    config = make_config()
    rooms = RoomStore(config)
    rooms.load_bundled_rooms()
    games = GameRegistry(config)
    lobbies = LobbyManager(config)
    game = games.create("escape-host-player", "first-light")
    lobby = lobbies.create_game(game)
    games.join(game.code, "escape-guest-player")
    lobbies.add_player(game, "escape-guest-player")
    lobby.players["escape-host-player"].name = "Host"
    lobby.players["escape-guest-player"].name = "Guest"
    lobby.teams["team-test-1"] = LobbyTeam("team-test-1", "Astronomers")
    lobby.players["escape-host-player"].team_id = "team-test-1"
    lobby.players["escape-guest-player"].team_id = "team-test-1"
    engine = EscapeEngine(rooms, lobbies)
    engine.start(game, now=100)
    return game, engine


def test_room_loader_rejects_unhashable_types_and_invalid_dependency_values():
    data = yaml.safe_load((ROOM_DIR / "room.yaml").read_text(encoding="utf-8"))
    data["puzzles"][0]["type"] = ["text"]
    data["puzzles"][1]["requires"] = [{"bad": "dependency"}]

    with pytest.raises(RoomValidationError) as error:
        validate_room(data, ROOM_DIR)

    assert "type is unsupported" in str(error.value)
    assert "requires must be a list of puzzle ids" in str(error.value)


def test_room_loader_rejects_prestory_that_reveals_answer():
    data = yaml.safe_load((ROOM_DIR / "room.yaml").read_text(encoding="utf-8"))
    data["puzzles"][0]["prestory"] = "The east-facing observatory is quiet."

    with pytest.raises(RoomValidationError, match="prestory must not contain its answer"):
        validate_room(data, ROOM_DIR)


def test_room_loader_validates_hotspot_rectangles_and_image(tmp_path):
    data = yaml.safe_load((ROOM_DIR / "room.yaml").read_text(encoding="utf-8"))
    puzzle = data["puzzles"][0]
    puzzle["type"] = "image_hotspot"
    puzzle.pop("answers")
    puzzle["image"] = "assets/hotspot.png"
    puzzle["regions"] = [{"x": 20, "y": 30, "w": 15, "h": 10}]
    room_dir = tmp_path / "first-light"
    room_dir.mkdir()
    shutil.copyfile(ROOM_DIR / "room.yaml", room_dir / "room.yaml")
    assets = room_dir / "assets"
    assets.mkdir()
    image = assets / "hotspot.png"
    image.write_bytes(b"placeholder")
    assert validate_room(data, room_dir)["puzzle_by_id"]["compass"]["type"] == (
        "image_hotspot"
    )
    puzzle["regions"] = [{"x": 90, "y": 30, "w": 15, "h": 10}]
    with pytest.raises(RoomValidationError, match="regions must contain"):
        validate_room(data, room_dir)


def test_room_loader_rejects_yaml_aliases_and_accepts_bundled_room(tmp_path):
    loaded = load_room(ROOM_DIR)
    assert loaded["meta"]["id"] == "first-light"
    assert len(loaded["puzzles"]) == 5
    assert loaded["min_team_size"] == 1
    assert loaded["max_team_size"] == 8
    alias_room = tmp_path / "alias-room"
    alias_room.mkdir()
    (alias_room / "room.yaml").write_text(
        "meta: &shared {}\ncopy: *shared\n", encoding="utf-8"
    )
    with pytest.raises(RoomValidationError, match="cannot use YAML anchors or aliases"):
        load_room(alias_room)


def test_type_checkers_cover_all_puzzle_types_and_reject_malformed_answers():
    examples = [
        ({"type": "text", "answers": ["Bright star"]}, "bright star"),
        ({"type": "multiple_choice", "answer": "Green"}, "green"),
        ({"type": "lock", "answer": "7294"}, "7-2-9-4"),
        ({"type": "split_clue", "answer": "star"}, "STAR!"),
        ({"type": "cipher", "answer": "secret"}, "Secret"),
        ({"type": "meta", "answer": "open door"}, "Open, door"),
        (
            {
                "type": "ordering",
                "items": ["new moon", "quarter", "full moon"],
            },
            ["new-moon", "quarter", "full moon"],
        ),
        (
            {
                "type": "image_hotspot",
                "regions": [{"x": 20, "y": 30, "w": 15, "h": 10}],
            },
            {"x": 25, "y": 35},
        ),
    ]
    assert all(check_answer(puzzle, answer) for puzzle, answer in examples)
    assert not check_answer(
        {"type": "image_hotspot", "regions": [{"x": 20, "y": 30, "w": 15, "h": 10}]},
        {"x": float("nan"), "y": 35},
    )
    assert not check_answer({"type": "text", "answers": ["answer"]}, ["answer"])


def test_engine_keeps_hotspot_regions_private_and_checks_coordinate_answers():
    game, engine = make_engine()
    puzzle = engine.rooms.get("first-light")["puzzle_by_id"]["compass"]
    puzzle["type"] = "image_hotspot"
    puzzle.pop("answers")
    puzzle["regions"] = [{"x": 20, "y": 30, "w": 15, "h": 10}]

    public = engine.open_puzzle(game, "escape-host-player", "compass", now=100)
    assert public["type"] == "image_hotspot"
    assert "regions" not in public
    with pytest.raises(EscapeEngineError, match="invalid_answer"):
        engine.submit_answer(
            game, "escape-host-player", "compass", {"x": 101, "y": 40}, now=100
        )
    assert engine.submit_answer(
        game, "escape-host-player", "compass", {"x": 25, "y": 35}, now=100
    )["correct"]


def test_engine_unlocks_puzzles_enforces_cooldown_and_hides_answers():
    game, engine = make_engine()
    snapshot = engine.snapshot(game, recipient_id="escape-host-player", now=100)
    assert snapshot["phase"] == "playing"
    assert snapshot["code"] == game.code
    assert {puzzle["id"] for puzzle in snapshot["puzzles"] if puzzle["state"] == "open"} == {
        "compass",
        "spectrum",
        "rhythm",
        "night-sky",
    }

    puzzle = engine.open_puzzle(
        game, "escape-host-player", "compass", now=100
    )
    assert puzzle["prompt"]
    assert "answer" not in puzzle
    assert "solve_text" not in puzzle
    host_clue = engine.open_puzzle(
        game, "escape-host-player", "night-sky", now=100
    )
    guest_clue = engine.open_puzzle(
        game, "escape-guest-player", "night-sky", now=100
    )
    assert host_clue["fragment"] != guest_clue["fragment"]
    assert "fragments" not in host_clue
    assert engine.submit_answer(
        game, "escape-host-player", "compass", "wrong", now=101
    )["correct"] is False
    with pytest.raises(EscapeEngineError, match="answer_cooldown"):
        engine.submit_answer(
            game, "escape-host-player", "compass", "east", now=102
        )

    assert engine.take_hint(
        game, "escape-host-player", "compass", now=102
    )["hint"] == "Think about where the sun rises."
    assert engine.submit_answer(
        game, "escape-host-player", "compass", "east", now=107
    )["correct"] is True
    snapshot = engine.snapshot(game, recipient_id="escape-host-player", now=107)
    assert next(item for item in snapshot["puzzles"] if item["id"] == "compass")[
        "state"
    ] == "solved"
    assert next(item for item in snapshot["puzzles"] if item["id"] == "beacon")[
        "state"
    ] == "locked"


def test_engine_finishes_meta_puzzle_and_builds_results():
    game, engine = make_engine()
    answers = [
        ("compass", "east", 110),
        ("spectrum", "green", 120),
        ("rhythm", ["new moon", "first quarter", "full moon"], 130),
        ("night-sky", "star", 135),
        ("beacon", "east green full moon star", 140),
    ]
    for puzzle_id, answer, now in answers[:-1]:
        result = engine.submit_answer(
            game, "escape-host-player", puzzle_id, answer, now=now
        )
        assert result["correct"] is True

    meta = engine.open_puzzle(game, "escape-host-player", "beacon", now=138)
    assert {fragment["title"] for fragment in meta["collected_fragments"]} == {
        "The Compass",
        "The Spectrum",
        "The Rhythm",
        "The Night Sky",
    }
    assert "answer" not in meta
    puzzle_id, answer, now = answers[-1]
    assert engine.submit_answer(
        game, "escape-host-player", puzzle_id, answer, now=now
    )["correct"]

    snapshot = engine.snapshot(game, recipient_id="escape-host-player", now=140)
    assert snapshot["phase"] == "results"
    assert snapshot["end_reason"] == "finished"
    assert len(snapshot["results"]["race"]) == 5
    host_stats = next(
        player
        for player in snapshot["results"]["player_stats"]
        if player["name"] == "Host"
    )
    assert host_stats["solves"] == 5
    assert any(award["name"] == "Clutch" for award in snapshot["results"]["awards"])


def test_host_controls_freeze_clock_add_time_end_and_skip_without_player_credit():
    game, engine = make_engine()
    initial = engine.clock(game, now=110)
    assert initial["elapsed_sec"] == 10
    paused = engine.set_paused(game, True, now=110)
    assert paused["paused"] is True
    assert engine.clock(game, now=200)["elapsed_sec"] == 10
    resumed = engine.set_paused(game, False, now=200)
    assert resumed["paused"] is False
    assert engine.clock(game, now=205)["elapsed_sec"] == 15

    before_add = engine.clock(game, now=205)
    updated = engine.add_time(game, 60, now=205)
    assert updated["remaining_sec"] == before_add["remaining_sec"] + 60
    with pytest.raises(EscapeEngineError, match="invalid_time_amount"):
        engine.add_time(game, 0, now=206)

    team_id = next(iter(engine.games[game.game_id].teams))
    engine.skip_puzzle(game, team_id, "compass", now=210)
    team = engine.games[game.game_id].teams[team_id]
    assert team.solved == {"compass"}
    assert team.skipped == {"compass"}
    assert team.solves_by_player == {}
    assert team.skip_penalty_sec == game.skip_penalty_sec
    snapshot = engine.snapshot(game, recipient_id="escape-host-player", now=210)
    compass = next(item for item in snapshot["puzzles"] if item["id"] == "compass")
    assert compass["state"] == "skipped"
    assert snapshot["team_solved"] == 0
    assert snapshot["team_skipped"] == 1
    engine.end_early(game, now=215)
    results = engine.snapshot(game, recipient_id="escape-host-player", now=215)[
        "results"
    ]
    assert results["standings"][0]["solved"] == 0
    assert results["standings"][0]["skipped"] == 1


def test_playtest_is_private_and_reveals_answers_only_in_host_snapshot():
    config = make_config()
    rooms = RoomStore(config)
    rooms.load_bundled_rooms()
    games = GameRegistry(config)
    game = games.create("escape-host-player", "first-light", is_playtest=True)
    lobbies = LobbyManager(config)
    lobby = lobbies.create_game(game)
    engine = EscapeEngine(rooms, lobbies)
    engine.start(game, now=100)

    snapshot = engine.snapshot(game, recipient_id="escape-host-player", now=100)
    assert game.code == ""
    assert game.game_id not in games.game_id_by_code.values()
    assert snapshot["is_playtest"] is True
    assert snapshot["code"] == ""
    assert next(item for item in snapshot["puzzles"] if item["id"] == "compass")[
        "answer"
    ] == ["east"]
    engine.end_early(game, now=110)
    playtest_results = engine.snapshot(
        game, recipient_id="escape-host-player", now=110
    )["results"]
    assert "standings" not in playtest_results
    assert lobby.teams
