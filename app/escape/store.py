from __future__ import annotations

import hmac
import logging
import secrets
from pathlib import Path
import time
from typing import Any

from app.config import AppConfig, PROJECT_ROOT
from app.escape.loader import RoomValidationError, load_room
from app.escape.sanitize import UploadValidationError

logger = logging.getLogger(__name__)

ASSET_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class RoomStoreError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class UploadedRoom:
    def __init__(
        self,
        token: str,
        assets: dict[str, tuple[bytes, str]],
        size_bytes: int,
        created_at: float,
        published: bool,
    ) -> None:
        self.token = token
        self.assets = assets
        self.size_bytes = size_bytes
        self.created_at = created_at
        self.last_used_at = created_at
        self.published = published


class RoomStore:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.rooms: dict[str, dict[str, Any]] = {}
        self.room_dirs: dict[str, Path] = {}
        self.uploaded_rooms: dict[str, UploadedRoom] = {}

    def load_bundled_rooms(self) -> None:
        configured_dir = Path(self.config.rooms.preload_dir)
        if not configured_dir.is_absolute():
            configured_dir = PROJECT_ROOT / configured_dir
        if not configured_dir.exists():
            logger.info("Bundled rooms directory does not exist: %s", configured_dir)
            return
        if not configured_dir.is_dir():
            raise RuntimeError(f"Bundled rooms path is not a directory: {configured_dir}")
        for room_dir in sorted(configured_dir.iterdir()):
            if not room_dir.is_dir() or not (room_dir / "room.yaml").is_file():
                continue
            try:
                room = load_room(room_dir)
            except RoomValidationError as exc:
                logger.warning(
                    "Skipping invalid bundled room '%s': %s",
                    room_dir.name,
                    "; ".join(exc.errors),
                )
                continue
            room_id = room["meta"]["id"]
            if room_id in self.rooms:
                logger.warning("Skipping duplicate bundled room id '%s'.", room_id)
                continue
            self.rooms[room_id] = room
            self.room_dirs[room_id] = room_dir.resolve()
            logger.info("Loaded bundled room '%s'.", room_id)

    def get(self, room_id: str) -> dict[str, Any] | None:
        return self.rooms.get(room_id)

    def catalog(self, room_tokens: dict[str, str] | None = None) -> list[dict[str, Any]]:
        room_tokens = room_tokens or {}
        bundled = [
            self._catalog_entry(room_id, room, uploaded=False)
            for room_id, room in self.rooms.items()
            if room_id not in self.uploaded_rooms
        ]
        uploaded = [
            self._catalog_entry(room_id, room, uploaded=True)
            for room_id, room in self.rooms.items()
            if room_id in self.uploaded_rooms
            and (
                (
                    self.config.uploads.visibility == "public"
                    and self.uploaded_rooms[room_id].published
                )
                or self._token_matches(
                    self.uploaded_rooms[room_id].token,
                    room_tokens.get(room_id, ""),
                )
            )
        ]
        uploaded.sort(
            key=lambda entry: self.uploaded_rooms[entry["id"]].created_at,
            reverse=True,
        )
        return bundled + uploaded

    def _catalog_entry(
        self,
        room_id: str, room: dict[str, Any], *, uploaded: bool
    ) -> dict[str, Any]:
        return {
            "id": room_id,
            "title": room["meta"]["title"],
            "author": room["meta"]["author"],
            "difficulty": room["meta"]["difficulty"],
            "est_minutes": room["meta"]["est_minutes"],
            "team_size": room["meta"]["team_size"],
            "tags": list(room["meta"]["tags"]),
            "intro": room["story"]["intro"],
            "uploaded": uploaded,
            "published": (
                self.uploaded_rooms[room_id].published if uploaded else True
            ),
        }

    def can_access(self, room_id: str, room_token: str | None = None) -> bool:
        if room_id not in self.rooms:
            return False
        uploaded = self.uploaded_rooms.get(room_id)
        if uploaded is None:
            return True
        if (
            self.config.uploads.visibility == "public"
            and uploaded.published
        ):
            return True
        return self._token_matches(uploaded.token, room_token or "")

    def requires_upload_token(self, room_id: str) -> bool:
        uploaded = self.uploaded_rooms.get(room_id)
        return (
            uploaded is not None
            and (
                self.config.uploads.visibility == "private"
                or not uploaded.published
            )
        )

    @staticmethod
    def _token_matches(expected: str, supplied: str) -> bool:
        return hmac.compare_digest(expected.encode("utf-8"), supplied.encode("utf-8"))

    def add_uploaded(
        self,
        room: dict[str, Any],
        assets: dict[str, tuple[bytes, str]],
        *,
        room_token: str | None = None,
        active_room_ids: set[str] | None = None,
        now: float | None = None,
    ) -> str:
        room_id = room["meta"]["id"]
        active_room_ids = active_room_ids or set()
        current_time = time.monotonic() if now is None else now
        existing = self.uploaded_rooms.get(room_id)
        if room_id in self.rooms and existing is None:
            raise RoomStoreError("room_id_conflicts_with_bundled")
        if existing is not None:
            if not self._token_matches(existing.token, room_token or ""):
                raise RoomStoreError("room_id_already_uploaded")
            if room_id in active_room_ids:
                raise RoomStoreError("room_in_use")

        size_bytes = sum(len(content) for content, _ in assets.values())
        memory_limit = self.config.uploads.max_total_memory_mb * 1024 * 1024
        if size_bytes > memory_limit:
            raise UploadValidationError(
                ["This room exceeds the server's uploaded-room memory limit."]
            )
        total_size = sum(upload.size_bytes for upload in self.uploaded_rooms.values())
        if existing is not None:
            total_size -= existing.size_bytes
        evictions: list[str] = []
        candidates = sorted(
            (
                (stored_id, upload)
                for stored_id, upload in self.uploaded_rooms.items()
                if stored_id != room_id and stored_id not in active_room_ids
            ),
            key=lambda item: item[1].created_at,
        )
        for stored_id, upload in candidates:
            if total_size + size_bytes <= memory_limit:
                break
            evictions.append(stored_id)
            total_size -= upload.size_bytes
        if total_size + size_bytes > memory_limit:
            raise UploadValidationError(
                ["The server's uploaded-room memory limit is currently full."]
            )

        for evicted_id in evictions:
            self.rooms.pop(evicted_id, None)
            self.uploaded_rooms.pop(evicted_id, None)
        token = existing.token if existing is not None else secrets.token_urlsafe(32)
        self.rooms[room_id] = room
        self.room_dirs.pop(room_id, None)
        self.uploaded_rooms[room_id] = UploadedRoom(
            token,
            assets,
            size_bytes,
            current_time,
            published=self.config.uploads.visibility != "public",
        )
        return token

    def publish(self, room_id: str, room_token: str) -> None:
        uploaded = self.uploaded_rooms.get(room_id)
        if (
            uploaded is None
            or self.config.uploads.visibility != "public"
            or not self._token_matches(uploaded.token, room_token)
        ):
            raise RoomStoreError("room_not_found")
        uploaded.published = True

    def mark_used(self, room_id: str, *, now: float | None = None) -> None:
        uploaded = self.uploaded_rooms.get(room_id)
        if uploaded is not None:
            uploaded.last_used_at = time.monotonic() if now is None else now

    def cleanup_uploads(
        self, active_room_ids: set[str], *, now: float | None = None
    ) -> int:
        current_time = time.monotonic() if now is None else now
        ttl_seconds = self.config.uploads.ttl_minutes * 60
        expired = [
            room_id
            for room_id, uploaded in self.uploaded_rooms.items()
            if room_id not in active_room_ids
            and current_time - uploaded.last_used_at >= ttl_seconds
        ]
        for room_id in expired:
            self.uploaded_rooms.pop(room_id, None)
            self.rooms.pop(room_id, None)
        return len(expired)

    def asset(self, room_id: str, relative_path: str) -> tuple[Path | bytes, str] | None:
        room_dir = self.room_dirs.get(room_id)
        room = self.rooms.get(room_id)
        if room is None:
            return None
        declared_paths = {
            room["meta"].get("cover"),
            room["story"].get("intro_image"),
            room["story"].get("outro_image"),
            *(puzzle.get("image") for puzzle in room["puzzles"]),
        }
        uploaded = self.uploaded_rooms.get(room_id)
        if uploaded is not None and "HOST_GUIDE.md" in uploaded.assets:
            declared_paths.add("HOST_GUIDE.md")
        if relative_path not in declared_paths:
            return None
        if uploaded is not None:
            asset = uploaded.assets.get(relative_path)
            return asset if asset is not None else None
        if room_dir is None:
            return None
        path = (room_dir / relative_path).resolve()
        try:
            path.relative_to(room_dir)
        except ValueError:
            return None
        if not path.is_file():
            return None
        media_type = ASSET_MEDIA_TYPES.get(path.suffix.lower())
        return (path, media_type) if media_type is not None else None
