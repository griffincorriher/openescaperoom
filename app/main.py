from __future__ import annotations

import asyncio
import hmac
import io
import json
import logging
import zipfile
from contextlib import asynccontextmanager
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import AppConfig, load_config
from app.escape.engine import EscapeEngine
from app.escape.sanitize import (
    MAX_UPLOAD_BODY_OVERHEAD,
    UploadValidationError,
    sanitize_room_zip,
)
from app.escape.store import RoomStore, RoomStoreError
from app.games import GameRegistry
from app.lobby import LobbyManager
from app.security import SlidingWindowRateLimiter, get_client_ip, origin_is_allowed
from app.ws import WebSocketHub, cleanup_idle_games

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"
SAMPLE_ROOM_DIR = PROJECT_ROOT / "rooms" / "first-light"
logger = logging.getLogger(__name__)
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; media-src 'self'; connect-src 'self'; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
)


def create_app(config: AppConfig | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.config = config or load_config()
        application.state.games = GameRegistry(application.state.config)
        application.state.lobbies = LobbyManager(application.state.config)
        application.state.rooms = RoomStore(application.state.config)
        application.state.rooms.load_bundled_rooms()
        application.state.upload_limiter = SlidingWindowRateLimiter()
        application.state.upload_semaphore = asyncio.Semaphore(1)
        if application.state.config.uploads.enabled:
            application.add_api_route(
                "/template.zip",
                room_template,
                methods=["GET"],
                include_in_schema=False,
            )
            application.add_api_route(
                "/api/uploads",
                upload_room,
                methods=["POST"],
                include_in_schema=False,
            )
            application.add_api_route(
                "/api/uploads/{room_id}/publish",
                publish_upload,
                methods=["POST"],
                include_in_schema=False,
            )
        application.state.escape_engine = EscapeEngine(
            application.state.rooms, application.state.lobbies
        )
        application.state.ws_hub = WebSocketHub(
            application.state.config,
            application.state.games,
            application.state.lobbies,
            application.state.rooms,
            application.state.escape_engine,
        )
        cleanup_task = asyncio.create_task(
            cleanup_idle_games(
                application.state.games,
                application.state.lobbies,
                application.state.ws_hub,
            )
        )
        try:
            yield
        finally:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass

    application = FastAPI(title="Party Games Server", lifespan=lifespan)

    @application.middleware("http")
    async def add_security_headers(request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @application.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @application.get("/healthz", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/api/rooms", include_in_schema=False)
    async def room_catalog(request: Request) -> Response:
        return JSONResponse(
            {
                "rooms": application.state.rooms.catalog(
                    _request_room_tokens(request)
                ),
                "can_upload": application.state.config.uploads.enabled,
                "can_publish": (
                    application.state.config.uploads.enabled
                    and application.state.config.uploads.visibility == "public"
                ),
            },
            headers={"Cache-Control": "no-store", "Vary": "X-Room-Tokens"},
        )

    @application.get("/join/{code}", include_in_schema=False)
    async def join_by_code(code: str) -> RedirectResponse:
        return RedirectResponse(
            f"../../?join={quote(code, safe='')}", status_code=307
        )

    @application.get("/rooms/{room_id}/assets/{asset_path:path}", include_in_schema=False)
    async def room_asset(
        room_id: str, asset_path: str, request: Request
    ) -> Response:
        room_store: RoomStore | None = getattr(application.state, "rooms", None)
        if room_store is None:
            raise HTTPException(status_code=404)
        if room_store.requires_upload_token(room_id):
            game_id = request.query_params.get("game_id", "")
            player_id = request.query_params.get("player_id", "")
            game = application.state.games.games_by_id.get(game_id)
            if (
                game is None
                or game.room_id != room_id
                or player_id not in game.players
            ):
                raise HTTPException(status_code=404)
        asset = room_store.asset(room_id, asset_path)
        if asset is None:
            raise HTTPException(status_code=404)
        content, media_type = asset
        if isinstance(content, bytes):
            return Response(
                content,
                media_type=media_type,
                headers={"Cache-Control": "private, no-store"},
            )
        return FileResponse(
            content,
            media_type=media_type,
            headers={"Cache-Control": "private, no-store"},
        )

    @application.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        current_config: AppConfig = websocket.app.state.config
        if not origin_is_allowed(
            websocket.headers.get("origin"),
            websocket.headers.get("host"),
            current_config.server.allowed_origins,
        ):
            await websocket.close(code=1008, reason="Origin not allowed")
            return
        player_id = websocket.query_params.get("player_id", "")
        await websocket.app.state.ws_hub.serve(websocket, player_id)

    application.mount(
        "/static",
        StaticFiles(directory=STATIC_DIR, check_dir=True),
        name="static",
    )
    return application


def _request_room_tokens(request: Request) -> dict[str, str]:
    value = request.headers.get("x-room-tokens", "")
    if not value:
        return {}
    if len(value) > 16 * 1024:
        raise HTTPException(status_code=400, detail="room_tokens_too_large")
    try:
        tokens = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid_room_tokens") from exc
    if (
        not isinstance(tokens, dict)
        or not all(
            isinstance(room_id, str)
            and isinstance(token, str)
            and 1 <= len(room_id) <= 64
            and 16 <= len(token) <= 128
            for room_id, token in tokens.items()
        )
    ):
        raise HTTPException(status_code=400, detail="invalid_room_tokens")
    return tokens


async def room_template() -> Response:
    if not SAMPLE_ROOM_DIR.is_dir():
        raise HTTPException(status_code=404)
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(SAMPLE_ROOM_DIR.rglob("*")):
            if path.is_file():
                archive.write(
                    path,
                    (Path("first-light") / path.relative_to(SAMPLE_ROOM_DIR)).as_posix(),
                )
        archive.writestr(
            "first-light/HOST_GUIDE.md",
            "Edit this plain-text guide with the host's solution walkthrough.\n",
        )
    return Response(
        output.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="template.zip"'},
    )


async def upload_room(request: Request) -> dict[str, object]:
    async with request.app.state.upload_semaphore:
        return await _process_room_upload(request)


async def _process_room_upload(request: Request) -> dict[str, object]:
    config: AppConfig = request.app.state.config
    request_origin = request.headers.get("origin")
    if request_origin and not origin_is_allowed(
        request_origin,
        request.headers.get("host"),
        config.server.allowed_origins,
    ):
        raise HTTPException(status_code=403, detail="origin_not_allowed")

    remote_address = request.client.host if request.client else None
    client_ip = get_client_ip(
        remote_address,
        request.headers.get("x-forwarded-for"),
        config.server.trusted_proxies,
    )
    if not request.app.state.upload_limiter.allow(
        client_ip,
        limit=config.uploads.per_ip_per_hour,
        window_seconds=3600,
    ):
        raise HTTPException(status_code=429, detail="upload_rate_limited")

    maximum_body = (
        config.uploads.max_zip_mb * 1024 * 1024 + MAX_UPLOAD_BODY_OVERHEAD
    )
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            parsed_length = int(content_length)
            if parsed_length < 0:
                raise ValueError
            if parsed_length > maximum_body:
                raise HTTPException(status_code=413, detail="upload_too_large")
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="invalid_content_length"
            ) from exc

    content_type = request.headers.get("content-type", "")
    if "\r" in content_type or "\n" in content_type:
        raise HTTPException(status_code=400, detail="invalid_content_type")
    try:
        content_type_bytes = content_type.encode("ascii")
    except UnicodeEncodeError as exc:
        raise HTTPException(status_code=400, detail="invalid_content_type") from exc
    header = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type_bytes + b"\r\n\r\n"
    )
    if (
        header.get_content_type() != "multipart/form-data"
        or not header.get_boundary()
    ):
        raise HTTPException(status_code=400, detail="multipart_required")

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > maximum_body:
            raise HTTPException(status_code=413, detail="upload_too_large")
    mime_message = BytesParser(policy=policy.default).parsebytes(
        b"MIME-Version: 1.0\r\n"
        + b"Content-Type: "
        + content_type_bytes
        + b"\r\n\r\n"
        + bytes(body)
    )
    if not mime_message.is_multipart():
        raise HTTPException(status_code=400, detail="invalid_multipart")
    archive_bytes: bytes | None = None
    supplied_key = ""
    key_seen = False
    field_count = 0
    for part in mime_message.iter_parts():
        field_count += 1
        if field_count > 2:
            raise HTTPException(status_code=400, detail="invalid_multipart")
        if part.is_multipart():
            raise HTTPException(status_code=400, detail="invalid_multipart")
        field_name = part.get_param(
            "name", header="content-disposition", unquote=True
        )
        value = part.get_payload(decode=True) or b""
        if field_name == "archive":
            if archive_bytes is not None or not part.get_filename():
                raise HTTPException(status_code=400, detail="invalid_archive_field")
            archive_bytes = value
        elif field_name == "admin_key":
            if key_seen:
                raise HTTPException(status_code=400, detail="invalid_admin_key")
            key_seen = True
            try:
                supplied_key = value.decode(part.get_content_charset() or "utf-8")
            except (LookupError, UnicodeError) as exc:
                raise HTTPException(
                    status_code=400, detail="invalid_admin_key"
                ) from exc
        else:
            raise HTTPException(status_code=400, detail="invalid_upload_field")
    if archive_bytes is None:
        raise HTTPException(status_code=400, detail="archive_required")
    if config.uploads.who == "key" and not hmac.compare_digest(
        config.security.admin_key.encode("utf-8"),
        supplied_key.encode("utf-8"),
    ):
        raise HTTPException(status_code=403, detail="invalid_admin_key")

    room_tokens = _request_room_tokens(request)
    try:
        room, assets, host_guide = await asyncio.to_thread(
            sanitize_room_zip, archive_bytes, config.uploads
        )
        token = request.app.state.rooms.add_uploaded(
            room,
            assets,
            room_token=room_tokens.get(room["meta"]["id"]),
            active_room_ids={
                game.room_id
                for game in request.app.state.games.games_by_id.values()
                if game.room_id is not None
            },
        )
    except UploadValidationError as exc:
        raise HTTPException(
            status_code=422, detail={"errors": exc.errors, "warnings": []}
        ) from exc
    except RoomStoreError as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
    logger.info("Accepted an uploaded room.")
    return {
        "room": request.app.state.rooms._catalog_entry(
            room["meta"]["id"], room, uploaded=True
        ),
        "room_token": token,
        "warnings": [],
        "host_guide": host_guide,
    }


async def publish_upload(room_id: str, request: Request) -> dict[str, object]:
    config: AppConfig = request.app.state.config
    request_origin = request.headers.get("origin")
    if request_origin and not origin_is_allowed(
        request_origin,
        request.headers.get("host"),
        config.server.allowed_origins,
    ):
        raise HTTPException(status_code=403, detail="origin_not_allowed")
    room_token = _request_room_tokens(request).get(room_id, "")
    try:
        request.app.state.rooms.publish(room_id, room_token)
    except RoomStoreError as exc:
        raise HTTPException(status_code=404, detail=exc.code) from exc
    return {"room_id": room_id, "published": True}


app = create_app()
