from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

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
from app.main import CONTENT_SECURITY_POLICY, create_app


def make_config() -> AppConfig:
    return AppConfig(
        server=ServerConfig(8000, (), ()),
        security=SecurityConfig("test-admin-key"),
        games=GamesConfig("key", 50, 40, 10, 30, 10),
        rooms=RoomsConfig("rooms"),
        uploads=UploadsConfig(False, "key", "private", 120, 50, 200, 200, 1024, 5),
        game=GameConfig(8, 300),
        limits=LimitsConfig(20, 10, 20),
    )


def test_home_serves_static_page_with_security_headers():
    with TestClient(create_app(make_config())) as client:
        response = client.get("/")
        module_response = client.get("/static/puzzles/text.js")
        client_script_response = client.get("/static/client.js")
        style_response = client.get("/static/style.css")

    assert response.status_code == 200
    assert "Party Games Server" in response.text
    assert 'id="create-game-form"' in response.text
    assert 'id="create-game-form" method="post"' in response.text
    assert 'id="room-upload-tools" class="room-upload-tools" hidden' in response.text
    assert 'id="upload-room-form"' in response.text
    assert 'id="room-upload-dropzone" class="room-upload-dropzone"' in response.text
    assert 'id="browse-room-file" class="button button-secondary room-upload-browse-button"' in response.text
    assert 'id="room-archive" class="room-upload-file-input"' in response.text
    assert "M12 5v9m-5 0H5a1 1 0 0 0-1 1v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4a1 1 0 0 0-1-1h-2M8 9l4-5 4 5m1 8h.01" in response.text
    assert 'id="host-guide-preview" hidden' in response.text
    assert 'id="room-publish-tools" hidden' in response.text
    assert 'id="publish-room-button"' in response.text
    assert "static/client.js?v=36" in response.text
    assert "static/style.css?v=31" in response.text
    assert 'id="app-toast"' in response.text
    assert 'id="lobby-notice"' not in response.text
    assert "Game created. Choose your name to get started." not in client_script_response.text
    assert 'showToast("Save your player name before creating a team.", "warning")' in client_script_response.text
    assert 'showToast("Join code copied to clipboard.", "success")' in client_script_response.text
    assert "openHostControlsButton.hidden = !canControl;" in client_script_response.text
    assert 'browseRoomFileButton.addEventListener("click"' in client_script_response.text
    assert 'roomUploadDropzone.addEventListener("drop"' in client_script_response.text
    assert 'roomUploadDropzone.classList.add("is-dragging")' in client_script_response.text
    assert 'label.textContent = "Copied!"' not in client_script_response.text
    assert "static/vendor/flowbite.min.css?v=3.1.2" in response.text
    assert "static/vendor/flowbite.min.js?v=3.1.2" in response.text
    assert "static/vendor/chart.umd.min.js?v=4.5.1" in response.text
    assert 'id="home-hero"' in response.text
    assert 'id="home-grid"' in response.text
    assert 'id="connection-strip" class="connection-strip" hidden' in response.text
    assert "<span>Server</span>" not in response.text
    assert response.text.index('id="connection-strip"') < response.text.index('id="lobby-phase"')
    assert 'class="lobby-phase-group"' in response.text
    assert 'id="game-code"' in response.text
    assert 'id="open-host-controls"' in response.text
    assert 'id="host-controls-modal" tabindex="-1" aria-hidden="true" class="modal-backdrop host-controls-modal hidden"' in response.text
    assert 'id="close-host-controls"' in response.text
    assert 'id="game-host-controls"' in response.text
    assert 'data-modal-target="host-controls-modal" data-modal-toggle="host-controls-modal"' in response.text
    assert 'id="results-view"' in response.text
    assert 'id="results-home-button"' in response.text
    assert 'id="copy-lobby-code"' in response.text
    assert 'id="copy-game-code"' in response.text
    assert 'id="copy-results-game-code"' in response.text
    assert response.text.count('class="code-copy-icon"') == 3
    assert 'id="create-team-button" type="submit"' in response.text
    assert 'id="team-name-help"' in response.text
    assert 'aria-labelledby="setup-heading"' in response.text
    assert response.text.index('id="player-name-form"') < response.text.index('id="teams-heading"')
    assert 'class="game-layout"' in response.text
    assert response.text.index('id="puzzle-map"') < response.text.index('id="team-activity"')
    assert response.text.index('id="team-activity"') < response.text.index('id="game-host-controls"')
    assert response.text.index('id="game-view"') < response.text.index('id="results-view"')
    assert 'data-modal-toggle="end-game-modal"' in response.text
    assert 'id="join-game-form"' in response.text
    assert 'id="join-code-label">5-character game code</label>' in response.text
    assert response.text.count('class="join-code-digit" data-join-code-digit') == 5
    assert 'id="join-code" name="join-code" type="hidden"' in response.text
    assert "function setJoinCode(value)" in client_script_response.text
    assert "function placePuzzlePanel(puzzleId)" in client_script_response.text
    assert "card.append(puzzlePanel);" in client_script_response.text
    assert "const xAxisBuffer = Math.max(0.03, maxElapsedMinutes * 0.015);" in client_script_response.text
    assert "const xAxisMax = Math.ceil((maxElapsedMinutes + xAxisBuffer) * 10) / 10;" in client_script_response.text
    assert "min: -xAxisBuffer,\n          max: xAxisMax," in client_script_response.text
    assert 'precision: 1,\n            callback: (value) =>\n              value < 0 ? "" : Number(value).toFixed(1).replace(/\\.0$/, "")' in client_script_response.text
    assert "min: -0.2,\n          max: snapshot.puzzles.length + 0.2," in client_script_response.text
    assert """afterBuildTicks: (scale) => {
            scale.ticks = Array.from(
              { length: snapshot.puzzles.length + 1 },
              (_, value) => ({ value }),
            );
          },""" in client_script_response.text
    assert "autoSkip: false,\n            stepSize: 1," in client_script_response.text
    assert "callback: (value) => String(value)" in client_script_response.text
    assert ".game-sidebar .game-header .code-pill {\n  width: 100%;" in style_response.text
    assert ".game-sidebar .game-header .timer-card {\n  width: 100%;" in style_response.text
    assert ".player-row {\n  margin: 0;\n  padding-block: 0.55rem;\n  border: 0;" in style_response.text
    assert "game-sidebar {\n    order: 1;" in style_response.text
    assert "html[data-theme=\"dark\"] .button-quiet {\n  border-color: #465744;\n  background: #202821;\n  color: #c2d0b6;" in style_response.text
    assert 'input,\nselect {\n  width: 100%;\n  min-height: 2.9rem;\n  padding: 0.65rem 0.85rem;\n  border: 1px solid #b8c9ad;\n  background: #e8f0e2;' in style_response.text
    assert 'html[data-theme="dark"] input,\nhtml[data-theme="dark"] select {\n  border-color: #61795a;\n  background: #2d3b2d;\n  color: #f0eee4;' in style_response.text
    assert "background: #151721" not in style_response.text
    assert "border-color: #3a3d4d" not in style_response.text
    assert "text-slate-" not in response.text
    assert "text-slate-" not in client_script_response.text
    assert "#c4c6d3" not in client_script_response.text
    assert 'showToast("Enter all 5 characters of the game code.", "warning")' in client_script_response.text
    assert module_response.status_code == 200
    flowbite_css_response = client.get("/static/vendor/flowbite.min.css")
    flowbite_response = client.get("/static/vendor/flowbite.min.js")
    chart_response = client.get("/static/vendor/chart.umd.min.js")
    assert flowbite_css_response.status_code == 200
    assert flowbite_response.status_code == 200
    assert chart_response.status_code == 200
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_room_catalog_returns_loaded_bundled_rooms():
    with TestClient(create_app(make_config())) as client:
        response = client.get("/api/rooms")

    assert response.status_code == 200
    assert [room["id"] for room in response.json()["rooms"]] == ["first-light"]


def test_websocket_origin_and_player_id_reconnect():
    app = create_app(make_config())
    with TestClient(app) as client:
        with client.websocket_connect(
            "/ws?player_id=player-id-123456", headers={"origin": "http://testserver"}
        ) as first:
            first.send_json({"type": "ping"})
            assert first.receive_json() == {"type": "pong"}

        with client.websocket_connect(
            "/ws?player_id=player-id-123456", headers={"origin": "http://testserver"}
        ) as first:
            with client.websocket_connect(
                "/ws?player_id=player-id-123456", headers={"origin": "http://testserver"}
            ) as second:
                with pytest.raises(WebSocketDisconnect):
                    first.receive_json()
                second.send_json({"type": "ping"})
                assert second.receive_json() == {"type": "pong"}

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws?player_id=player-id-123456", headers={"origin": "https://attacker.test"}):
                pass


def test_game_creation_key_gate_join_and_host_reconnect():
    app = create_app(make_config())
    with TestClient(app) as client:
        with client.websocket_connect(
            "/ws?player_id=host-player-123456", headers={"origin": "http://testserver"}
        ) as host:
            host.send_json({"type": "game.create", "admin_key": "incorrect🔑"})
            assert host.receive_json() == {"type": "error", "error": "invalid_admin_key"}
            host.send_json({"type": "game.create", "admin_key": "incorrect"})
            assert host.receive_json() == {"type": "error", "error": "invalid_admin_key"}

            host.send_json({"type": "game.create", "admin_key": "test-admin-key"})
            created = host.receive_json()
            assert created["type"] == "game.created"
            assert host.receive_json()["type"] == "lobby.snapshot"
            assert len(created["code"]) == 5
            assert len(created["host_token"]) >= 40
            assert app.state.games.games_by_id[created["game_id"]].players[
                "host-player-123456"
            ].connected

            with client.websocket_connect(
                "/ws?player_id=guest-player-123456",
                headers={"origin": "http://testserver"},
            ) as guest:
                guest.send_json({"type": "game.join", "code": created["code"].lower()})
                joined = guest.receive_json()
                assert joined["type"] == "game.joined"
                assert joined["game_id"] == created["game_id"]
                assert guest.receive_json()["type"] == "lobby.snapshot"
                assert host.receive_json()["type"] == "lobby.snapshot"

                host.send_json({"type": "game.join", "code": created["code"]})
                assert host.receive_json() == {
                    "type": "error",
                    "error": "already_in_game",
                }

        assert not app.state.games.games_by_id[created["game_id"]].players[
            "host-player-123456"
        ].connected

        with client.websocket_connect(
            "/ws?player_id=host-player-123456", headers={"origin": "http://testserver"}
        ) as host:
            host.send_json(
                {
                    "type": "game.reconnect",
                    "game_id": created["game_id"],
                    "host_token": created["host_token"],
                }
            )
            reconnected = host.receive_json()
            assert reconnected == {
                "type": "game.reconnected",
                "game_id": created["game_id"],
                "code": created["code"],
                "is_host": True,
            }


def test_join_path_redirects_to_home_with_code():
    with TestClient(create_app(make_config())) as client:
        response = client.get("/join/abc23", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "../../?join=abc23"


def test_public_creation_and_join_attempt_rate_limit():
    config = make_config()
    public_config = replace(config, games=replace(config.games, create="anyone"))
    with TestClient(create_app(public_config)) as client:
        with client.websocket_connect(
            "/ws?player_id=public-host-player-123",
            headers={"origin": "http://testserver"},
        ) as websocket:
            websocket.send_json({"type": "game.create"})
            created = websocket.receive_json()
            assert created["type"] == "game.created"

    limited_config = replace(
        config, limits=replace(config.limits, join_attempts_per_ip_per_min=1)
    )
    with TestClient(create_app(limited_config)) as client:
        with client.websocket_connect(
            "/ws?player_id=join-attempt-player",
            headers={"origin": "http://testserver"},
        ) as websocket:
            websocket.send_json({"type": "game.join", "code": "00000"})
            assert websocket.receive_json() == {
                "type": "error",
                "error": "invalid_join_code",
            }
            websocket.send_json({"type": "game.join", "code": "00000"})
            with pytest.raises(WebSocketDisconnect) as disconnect:
                websocket.receive_json()
            assert disconnect.value.code == 4429


def test_lobby_actions_broadcast_state_and_enforce_host_controls():
    app = create_app(make_config())
    with TestClient(app) as client:
        with client.websocket_connect(
            "/ws?player_id=lobby-host-player-123",
            headers={"origin": "http://testserver"},
        ) as host:
            host.send_json({"type": "game.create", "admin_key": "test-admin-key"})
            created = host.receive_json()
            assert created["type"] == "game.created"
            assert host.receive_json()["type"] == "lobby.snapshot"

            host.send_json({"type": "lobby.set_name", "name": "Host"})
            host_snapshot = host.receive_json()
            assert host_snapshot["players"][0]["name"] == "Host"

            host.send_json({"type": "lobby.create_team", "name": "Owls"})
            host_snapshot = host.receive_json()
            team_id = host_snapshot["teams"][0]["team_id"]
            assert host_snapshot["players"][0]["team_id"] == team_id

            with client.websocket_connect(
                "/ws?player_id=lobby-guest-player-123",
                headers={"origin": "http://testserver"},
            ) as guest:
                guest.send_json({"type": "game.join", "code": created["code"]})
                assert guest.receive_json()["type"] == "game.joined"
                guest_snapshot = guest.receive_json()
                assert guest_snapshot["type"] == "lobby.snapshot"
                assert len(guest_snapshot["players"]) == 2
                assert host.receive_json()["type"] == "lobby.snapshot"

                guest.send_json({"type": "lobby.set_name", "name": "Guest"})
                assert guest.receive_json()["type"] == "lobby.snapshot"
                assert host.receive_json()["type"] == "lobby.snapshot"

                guest.send_json(
                    {"type": "lobby.lock_teams", "locked": True}
                )
                assert guest.receive_json() == {"type": "error", "error": "host_only"}

                host.send_json({"type": "lobby.lock_teams", "locked": True})
                assert host.receive_json()["teams_locked"] is True
                assert guest.receive_json()["teams_locked"] is True

                guest.send_json(
                    {"type": "lobby.join_team", "team_id": team_id}
                )
                assert guest.receive_json() == {"type": "error", "error": "teams_locked"}

                host.send_json(
                    {
                        "type": "lobby.move_player",
                        "player_id": "lobby-guest-player-123",
                        "team_id": team_id,
                    }
                )
                assert host.receive_json()["teams"][0]["player_count"] == 2
                assert guest.receive_json()["teams"][0]["player_count"] == 2

                host.send_json({"type": "lobby.start"})
                started = host.receive_json()
                assert started["type"] == "lobby.started"
                assert guest.receive_json()["type"] == "lobby.started"
                host_snapshot = host.receive_json()
                guest_snapshot = guest.receive_json()
                assert host_snapshot["phase"] == guest_snapshot["phase"] == "playing"
                assert host_snapshot["teams_locked"]
                assert len(host_snapshot["teams"]) == 1


def test_websocket_room_selection_and_escape_gameplay():
    app = create_app(make_config())
    with TestClient(app) as client:
        with client.websocket_connect(
            "/ws?player_id=escape-host-player-123",
            headers={"origin": "http://testserver"},
        ) as host:
            host.send_json({"type": "rooms.list"})
            rooms = host.receive_json()
            assert rooms["type"] == "rooms.list"
            assert [room["id"] for room in rooms["rooms"]] == ["first-light"]

            host.send_json(
                {
                    "type": "game.create",
                    "admin_key": "test-admin-key",
                    "room_id": "first-light",
                }
            )
            created = host.receive_json()
            assert created["type"] == "game.created"
            assert created["room_id"] == "first-light"
            host.receive_json()

            host.send_json({"type": "lobby.set_name", "name": "Host"})
            host.receive_json()
            host.send_json({"type": "lobby.create_team", "name": "Stars"})
            host.receive_json()
            host.send_json({"type": "lobby.start"})
            assert host.receive_json()["type"] == "lobby.started"
            assert host.receive_json()["type"] == "lobby.snapshot"
            started = host.receive_json()
            assert started["type"] == "game.snapshot"
            assert started["room_title"] == "The First Light"

            host.send_json({"type": "puzzle.open", "puzzle_id": "compass"})
            opened = host.receive_json()
            assert opened["type"] == "game.puzzle"
            assert "answer" not in opened["puzzle"]
            assert "solve_text" not in opened["puzzle"]
            host.send_json(
                {
                    "type": "puzzle.submit",
                    "puzzle_id": "compass",
                    "answer": "east",
                }
            )
            answer_result = host.receive_json()
            assert answer_result["type"] == "game.answer_result"
            assert answer_result["correct"] is True
            updated = host.receive_json()
            assert updated["type"] == "game.snapshot"
            assert next(
                item for item in updated["puzzles"] if item["id"] == "compass"
            )["state"] == "solved"

            events = app.state.escape_engine.games[created["game_id"]].events
            assert all("answer" not in event for event in events)


def test_playing_game_allows_late_joiner_to_choose_full_team():
    app = create_app(make_config())
    with TestClient(app) as client:
        with client.websocket_connect(
            "/ws?player_id=late-host-player-123",
            headers={"origin": "http://testserver"},
        ) as host:
            host.send_json({"type": "game.create", "admin_key": "test-admin-key"})
            created = host.receive_json()
            host.receive_json()
            host.send_json({"type": "lobby.set_name", "name": "Host"})
            host.receive_json()
            host.send_json({"type": "lobby.create_team", "name": "Owls"})
            snapshot = host.receive_json()
            team_id = snapshot["teams"][0]["team_id"]
            host.send_json({"type": "lobby.start"})
            assert host.receive_json()["type"] == "lobby.started"
            host.receive_json()

            with client.websocket_connect(
                "/ws?player_id=late-guest-player-123",
                headers={"origin": "http://testserver"},
            ) as guest:
                guest.send_json({"type": "game.join", "code": created["code"]})
                assert guest.receive_json()["type"] == "game.joined"
                snapshot = guest.receive_json()
                assert snapshot["phase"] == "playing"
                guest.send_json({"type": "lobby.set_name", "name": "Late"})
                guest.receive_json()
                guest.send_json({"type": "lobby.join_team", "team_id": team_id})
                snapshot = guest.receive_json()
                assert snapshot["teams"][0]["player_count"] == 2


def test_websocket_rate_limit_and_message_size():
    config = replace(make_config(), limits=LimitsConfig(1, 10, 20))
    with TestClient(create_app(config)) as client:
        with client.websocket_connect(
            "/ws?player_id=player-id-123456", headers={"origin": "http://testserver"}
        ) as websocket:
            websocket.send_json({"type": "ping"})
            assert websocket.receive_json() == {"type": "pong"}
            websocket.send_json({"type": "ping"})
            with pytest.raises(WebSocketDisconnect) as disconnect:
                websocket.receive_json()
            assert disconnect.value.code == 4429

    with TestClient(create_app(make_config())) as client:
        with client.websocket_connect(
            "/ws?player_id=player-id-123456", headers={"origin": "http://testserver"}
        ) as websocket:
            websocket.send_text("x" * 4097)
            with pytest.raises(WebSocketDisconnect) as disconnect:
                websocket.receive_json()
            assert disconnect.value.code == 1009


def test_private_playtest_enforces_key_gate_and_supports_host_controls():
    app = create_app(make_config())
    with TestClient(app) as client:
        with client.websocket_connect(
            "/ws?player_id=playtest-host-player-123",
            headers={"origin": "http://testserver"},
        ) as host:
            host.send_json(
                {"type": "game.playtest", "admin_key": "test-admin-key"}
            )
            created = host.receive_json()
            assert created["type"] == "game.created"
            assert created["is_playtest"] is True
            assert created["code"] == ""
            lobby = host.receive_json()
            assert lobby["type"] == "lobby.snapshot"
            assert lobby["is_playtest"] is True

            host.send_json({"type": "lobby.set_name", "name": "Tester"})
            host.receive_json()
            host.send_json({"type": "lobby.start"})
            assert host.receive_json()["type"] == "lobby.started"
            host.receive_json()
            started = host.receive_json()
            assert started["type"] == "game.snapshot"
            assert started["is_playtest"] is True
            assert next(item for item in started["puzzles"] if item["id"] == "compass")[
                "answer"
            ] == ["east"]
            host.send_json({"type": "game.leave"})
            assert host.receive_json() == {
                "type": "error",
                "error": "game_in_progress",
            }

            host.send_json({"type": "host.pause"})
            paused = host.receive_json()
            assert paused["type"] == "game.clock"
            assert paused["paused"] is True
            host.send_json({"type": "host.add_time", "minutes": 2})
            assert host.receive_json()["remaining_sec"] >= paused["remaining_sec"] + 120
            host.send_json({"type": "host.end_early"})
            results = host.receive_json()
            assert results["type"] == "game.snapshot"
            assert results["phase"] == "results"
            assert "standings" not in results["results"]

            host.send_json({"type": "game.leave"})
            assert host.receive_json() == {"type": "game.left"}
            host.send_json({"type": "game.create", "admin_key": "test-admin-key"})
            next_game = host.receive_json()
            assert next_game["type"] == "game.created"
            assert next_game["game_id"] != created["game_id"]
            assert host.receive_json()["type"] == "lobby.snapshot"


def test_host_kick_prevents_same_player_id_from_rejoining():
    app = create_app(make_config())
    with TestClient(app) as client:
        with client.websocket_connect(
            "/ws?player_id=kick-host-player-123",
            headers={"origin": "http://testserver"},
        ) as host:
            host.send_json({"type": "game.create", "admin_key": "test-admin-key"})
            created = host.receive_json()
            host.receive_json()
            with client.websocket_connect(
                "/ws?player_id=kick-guest-player-123",
                headers={"origin": "http://testserver"},
            ) as guest:
                guest.send_json({"type": "game.join", "code": created["code"]})
                assert guest.receive_json()["type"] == "game.joined"
                guest.receive_json()
                host.receive_json()

                host.send_json(
                    {"type": "host.kick", "player_id": "kick-guest-player-123"}
                )
                assert host.receive_json()["type"] == "lobby.snapshot"
                assert guest.receive_json() == {"type": "game.kicked"}
                with pytest.raises(WebSocketDisconnect):
                    guest.receive_json()

            with client.websocket_connect(
                "/ws?player_id=kick-guest-player-123",
                headers={"origin": "http://testserver"},
            ) as guest:
                guest.send_json({"type": "game.join", "code": created["code"]})
                assert guest.receive_json() == {
                    "type": "error",
                    "error": "player_kicked",
                }


def test_host_messages_are_scoped_and_skip_has_no_player_credit():
    app = create_app(make_config())
    with TestClient(app) as client:
        with client.websocket_connect(
            "/ws?player_id=control-host-player-123",
            headers={"origin": "http://testserver"},
        ) as host:
            host.send_json({"type": "game.create", "admin_key": "test-admin-key"})
            created = host.receive_json()
            host.receive_json()
            host.send_json({"type": "lobby.set_name", "name": "Host"})
            host.receive_json()
            host.send_json({"type": "lobby.create_team", "name": "Hosts"})
            host.receive_json()

            with client.websocket_connect(
                "/ws?player_id=control-guest-player-123",
                headers={"origin": "http://testserver"},
            ) as guest:
                guest.send_json({"type": "game.join", "code": created["code"]})
                guest.receive_json()
                guest_lobby = guest.receive_json()
                host.receive_json()
                guest.send_json({"type": "lobby.set_name", "name": "Guest"})
                guest_lobby = guest.receive_json()
                host.receive_json()
                guest.send_json({"type": "lobby.create_team", "name": "Guests"})
                guest_lobby = guest.receive_json()
                host.receive_json()
                guest_team_id = next(
                    player["team_id"]
                    for player in guest_lobby["players"]
                    if player["player_id"] == "control-guest-player-123"
                )

                host.send_json({"type": "lobby.start"})
                assert host.receive_json()["type"] == "lobby.started"
                assert guest.receive_json()["type"] == "lobby.started"
                host.receive_json()
                guest.receive_json()
                host.receive_json()
                guest.receive_json()

                guest.send_json({"type": "host.pause"})
                assert guest.receive_json() == {"type": "error", "error": "host_only"}

                host.send_json(
                    {
                        "type": "host.skip",
                        "team_id": guest_team_id,
                        "puzzle_id": "compass",
                    }
                )
                host_snapshot = host.receive_json()
                guest_snapshot = guest.receive_json()
                assert next(
                    item for item in guest_snapshot["puzzles"]
                    if item["id"] == "compass"
                )["state"] == "skipped"
                assert next(
                    item for item in host_snapshot["teams"]
                    if item["team_id"] == guest_team_id
                )["skipped_count"] == 1

                host.send_json(
                    {
                        "type": "host.message",
                        "team_id": guest_team_id,
                        "text": "Check the observatory.",
                    }
                )
                assert guest.receive_json() == {
                    "type": "game.host_message",
                    "text": "Check the observatory.",
                    "team_id": guest_team_id,
                }

                host.send_json(
                    {"type": "host.message", "team_id": "all", "text": "One minute."}
                )
                expected_message = {
                    "type": "game.host_message",
                    "text": "One minute.",
                    "team_id": "all",
                }
                assert host.receive_json() == expected_message
                assert guest.receive_json() == expected_message
