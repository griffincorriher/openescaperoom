from __future__ import annotations

import io
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin

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
from app.escape.sanitize import UploadValidationError, sanitize_room_zip
from app.main import create_app

ROOM_DIR = Path(__file__).resolve().parents[1] / "rooms" / "first-light"


def make_uploads_config(
    *, enabled: bool = True, who: str = "anyone", visibility: str = "private"
) -> AppConfig:
    return AppConfig(
        server=ServerConfig(8000, (), ()),
        security=SecurityConfig("test-admin-key"),
        games=GamesConfig("anyone", 50, 40, 10, 30, 10),
        rooms=RoomsConfig("rooms"),
        uploads=UploadsConfig(enabled, who, visibility, 120, 50, 200, 200, 1, 5),
        game=GameConfig(8, 300),
        limits=LimitsConfig(20, 10, 20),
    )


def room_archive(*, extra_files: dict[str, bytes] | None = None) -> bytes:
    room_yaml = (ROOM_DIR / "room.yaml").read_text(encoding="utf-8")
    room_yaml = room_yaml.replace("id: first-light", "id: community-room")
    if extra_files and "assets/cover.png" in extra_files:
        room_yaml = room_yaml.replace(
            "  tags:\n", "  cover: assets/cover.png\n  tags:\n"
        )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("community-room/room.yaml", room_yaml)
        for path in ROOM_DIR.rglob("*"):
            if path.is_file() and path.name != "room.yaml":
                archive.write(
                    path,
                    f"community-room/{path.relative_to(ROOM_DIR).as_posix()}",
                )
        for path, content in (extra_files or {}).items():
            archive.writestr(f"community-room/{path}", content)
    return output.getvalue()


def png_with_metadata() -> bytes:
    output = io.BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("unsafe", "metadata should be discarded")
    Image.new("RGB", (4, 4), "green").save(output, format="PNG", pnginfo=metadata)
    return output.getvalue()


def test_upload_sanitizes_image_and_keeps_markdown_as_text():
    archive = room_archive(
        extra_files={
            "assets/cover.png": png_with_metadata(),
            "HOST_GUIDE.md": b"<script>not html</script>",
        }
    )

    room, assets, guide = sanitize_room_zip(
        archive, make_uploads_config().uploads
    )

    assert room["meta"]["id"] == "community-room"
    image_bytes, image_type = assets["assets/cover.png"]
    with Image.open(io.BytesIO(image_bytes)) as image:
        assert image.format == "PNG"
        assert "unsafe" not in image.info
    assert image_type == "image/png"
    assert guide == "<script>not html</script>"
    assert assets["HOST_GUIDE.md"][1] == "text/plain; charset=utf-8"


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("../escape.txt", b"nope", "unsafe file path"),
        ("assets/active.js", b"alert(1)", "not allowed"),
    ],
)
def test_upload_rejects_unsafe_zip_members(name, content, message):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("community-room/room.yaml", "meta: {}\n")
        archive.writestr(name, content)

    with pytest.raises(UploadValidationError, match=message):
        sanitize_room_zip(output.getvalue(), make_uploads_config().uploads)


def test_upload_rejects_yaml_aliases_and_high_compression_ratio():
    alias_yaml = (ROOM_DIR / "room.yaml").read_text(encoding="utf-8").replace(
        "meta:\n", "meta: &metadata\n"
    )
    alias_output = io.BytesIO()
    with zipfile.ZipFile(alias_output, "w") as archive:
        archive.writestr(
            "community-room/room.yaml",
            alias_yaml + "\nextra: *metadata\n",
        )
    with pytest.raises(UploadValidationError, match="anchors or aliases"):
        sanitize_room_zip(alias_output.getvalue(), make_uploads_config().uploads)

    ratio_output = io.BytesIO()
    with zipfile.ZipFile(ratio_output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("community-room/room.yaml", "x" * 100_000)
    with pytest.raises(UploadValidationError, match="compression ratio"):
        sanitize_room_zip(ratio_output.getvalue(), make_uploads_config().uploads)


def test_upload_routes_are_absent_when_disabled():
    with TestClient(create_app(make_uploads_config(enabled=False))) as client:
        assert client.get("/template.zip").status_code == 404
        assert client.post("/api/uploads").status_code == 404
        assert client.post("/api/uploads/community-room/publish").status_code == 404


def test_template_download_contains_a_room_and_plain_text_guide():
    with TestClient(create_app(make_uploads_config())) as client:
        response = client.get("/template.zip")

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert "first-light/room.yaml" in names
        assert "first-light/HOST_GUIDE.md" in names
        assert b"plain-text" in archive.read("first-light/HOST_GUIDE.md")


def test_private_upload_needs_token_to_list_and_create_game():
    archive = room_archive(
        extra_files={"assets/cover.png": png_with_metadata()}
    )
    config = make_uploads_config()
    with TestClient(create_app(config)) as client:
        assert client.get("/template.zip").headers["content-type"] == "application/zip"
        response = client.post(
            "/api/uploads",
            files={"archive": ("community-room.zip", archive, "application/zip")},
        )
        assert response.status_code == 200
        uploaded = response.json()
        room_token = uploaded["room_token"]
        assert "room_token" not in client.get("/api/rooms").text

        catalog = client.get(
            "/api/rooms",
            headers={"X-Room-Tokens": f'{{"community-room":"{room_token}"}}'},
        )
        assert [room["id"] for room in catalog.json()["rooms"]] == [
            "first-light",
            "community-room",
        ]
        assert catalog.headers["cache-control"] == "no-store"
        assert "x-room-tokens" in catalog.headers["vary"].lower()

        assert client.get(
            "/rooms/community-room/assets/assets/cover.png"
        ).status_code == 404

        with client.websocket_connect(
            "/ws?player_id=upload-host-player-123456",
            headers={"origin": "http://testserver"},
        ) as websocket:
            websocket.send_json(
                {"type": "game.create", "room_id": "community-room"}
            )
            assert websocket.receive_json() == {
                "type": "error",
                "error": "room_not_found",
            }
            websocket.send_json(
                {
                    "type": "game.create",
                    "room_id": "community-room",
                    "room_token": room_token,
                }
            )
            created = websocket.receive_json()
            assert created["type"] == "game.created"
            websocket.receive_json()
            asset = client.get(
                "/rooms/community-room/assets/assets/cover.png",
                params={
                    "game_id": created["game_id"],
                    "player_id": "upload-host-player-123456",
                },
            )
            assert asset.status_code == 200
            assert asset.headers["content-type"] == "image/png"


def test_public_upload_is_private_until_uploader_publishes_it():
    archive = room_archive()
    with TestClient(create_app(make_uploads_config(visibility="public"))) as client:
            uploaded = client.post(
                "/api/uploads",
                files={"archive": ("community-room.zip", archive, "application/zip")},
            )
            assert uploaded.status_code == 200
            token = uploaded.json()["room_token"]
            assert uploaded.json()["room"]["published"] is False
            assert [room["id"] for room in client.get("/api/rooms").json()["rooms"]] == [
                "first-light"
            ]

            private_catalog = client.get(
                "/api/rooms",
                headers={"X-Room-Tokens": f'{{"community-room":"{token}"}}'},
            )
            assert [room["id"] for room in private_catalog.json()["rooms"]] == [
                "first-light",
                "community-room",
            ]
            assert client.post("/api/uploads/community-room/publish").status_code == 404

            with client.websocket_connect(
                "/ws?player_id=public-upload-host-123456",
                headers={"origin": "http://testserver"},
            ) as websocket:
                websocket.send_json({"type": "game.create", "room_id": "community-room"})
                assert websocket.receive_json() == {
                    "type": "error",
                    "error": "room_not_found",
                }

            published = client.post(
                "/api/uploads/community-room/publish",
                headers={"X-Room-Tokens": f'{{"community-room":"{token}"}}'},
            )
            assert published.status_code == 200
            assert published.json() == {
                "room_id": "community-room",
                "published": True,
            }
            public_catalog = client.get("/api/rooms")
            assert [room["id"] for room in public_catalog.json()["rooms"]] == [
                "first-light",
                "community-room",
            ]
            assert public_catalog.json()["rooms"][1]["published"] is True
            with client.websocket_connect(
                "/ws?player_id=public-upload-host-123456",
                headers={"origin": "http://testserver"},
            ) as websocket:
                websocket.send_json({"type": "game.create", "room_id": "community-room"})
                assert websocket.receive_json()["type"] == "game.created"


def test_upload_key_policy_requires_admin_key():
    archive = room_archive()
    with TestClient(create_app(make_uploads_config(who="key"))) as client:
        denied = client.post(
            "/api/uploads",
            files={"archive": ("community-room.zip", archive, "application/zip")},
        )
        accepted = client.post(
            "/api/uploads",
            files={
                "archive": ("community-room.zip", archive, "application/zip"),
                "admin_key": (None, "test-admin-key"),
            },
        )

    assert denied.status_code == 403
    assert accepted.status_code == 200
