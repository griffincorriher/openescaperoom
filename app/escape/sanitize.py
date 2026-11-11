from __future__ import annotations

import io
import stat
import warnings
import zlib
import zipfile
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

import yaml
from PIL import Image, ImageOps, UnidentifiedImageError
from yaml.tokens import AliasToken, AnchorToken

from app.config import UploadsConfig
from app.escape.loader import MAX_ROOM_YAML_BYTES, RoomValidationError, validate_room

MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGE_WIDTH = 1920
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_AUDIO_BYTES = 5 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
MAX_UPLOAD_BODY_OVERHEAD = 64 * 1024
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".mp3", ".yaml", ".md"}


class UploadValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def _safe_member_path(filename: str) -> PurePosixPath:
    if (
        not filename
        or "\x00" in filename
        or "\\" in filename
        or filename.startswith("/")
        or len(filename) > 1024
        or PureWindowsPath(filename).is_absolute()
        or PureWindowsPath(filename).drive
        or any(part in {"", ".", ".."} for part in filename.split("/"))
    ):
        raise UploadValidationError(["The archive contains an unsafe file path."])
    path = PurePosixPath(filename)
    if path.is_absolute() or any(
        part in {"", ".", ".."} or len(part) > 255 for part in path.parts
    ):
        raise UploadValidationError(["The archive contains an unsafe file path."])
    return path


def _read_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    *,
    limit: int,
) -> bytes:
    if info.file_size > limit:
        raise UploadValidationError([f"{info.filename} exceeds its allowed size."])
    output = bytearray()
    try:
        with archive.open(info) as member:
            while chunk := member.read(min(64 * 1024, limit + 1 - len(output))):
                output.extend(chunk)
                if len(output) > limit:
                    raise UploadValidationError(
                        [f"{info.filename} exceeds its allowed size."]
                    )
    except (
        OSError,
        RuntimeError,
        ValueError,
        EOFError,
        zlib.error,
        zipfile.BadZipFile,
        NotImplementedError,
    ) as exc:
        raise UploadValidationError(["The archive contains an unreadable file."]) from exc
    if len(output) != info.file_size:
        raise UploadValidationError(["The archive contains a truncated file."])
    return bytes(output)


def _check_magic(path: PurePosixPath, content: bytes) -> None:
    extension = path.suffix.lower()
    valid = {
        ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": content.startswith(b"\xff\xd8\xff"),
        ".jpeg": content.startswith(b"\xff\xd8\xff"),
        ".webp": (
            len(content) >= 12
            and content[:4] == b"RIFF"
            and content[8:12] == b"WEBP"
        ),
        ".mp3": content.startswith(b"ID3")
        or (
            len(content) >= 2
            and content[0] == 0xFF
            and content[1] & 0xE0 == 0xE0
        ),
        ".yaml": True,
        ".md": True,
    }
    if not valid.get(extension, False):
        raise UploadValidationError(
            [f"{path.name} does not match an allowed file type."]
        )


def _sanitize_image(path: PurePosixPath, content: bytes) -> bytes:
    image_format = {
        ".png": "PNG",
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".webp": "WEBP",
    }[path.suffix.lower()]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise UploadValidationError(
                        [f"{path.name} exceeds the image pixel limit."]
                    )
                image.load()
                image = ImageOps.exif_transpose(image)
                if image.width > MAX_IMAGE_WIDTH:
                    height = max(1, round(image.height * MAX_IMAGE_WIDTH / image.width))
                    image = image.resize(
                        (MAX_IMAGE_WIDTH, height), Image.Resampling.LANCZOS
                    )
                if image_format == "JPEG" and image.mode not in {"L", "RGB"}:
                    image = image.convert("RGB")
                output = io.BytesIO()
                image.save(output, format=image_format)
    except UploadValidationError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as exc:
        raise UploadValidationError([f"{path.name} is not a valid safe image."]) from exc
    return output.getvalue()


def _load_room_yaml(content: bytes) -> Any:
    if len(content) > MAX_ROOM_YAML_BYTES:
        raise UploadValidationError(["room.yaml is larger than 256 KB."])
    try:
        text = content.decode("utf-8-sig")
        if any(
            isinstance(token, (AliasToken, AnchorToken))
            for token in yaml.scan(text)
        ):
            raise UploadValidationError(
                ["room.yaml cannot use YAML anchors or aliases."]
            )
        return yaml.safe_load(text)
    except UploadValidationError:
        raise
    except (UnicodeError, yaml.YAMLError) as exc:
        raise UploadValidationError(["room.yaml is not valid UTF-8 YAML."]) from exc


def sanitize_room_zip(
    content: bytes, config: UploadsConfig
) -> tuple[dict[str, Any], dict[str, tuple[bytes, str]], str | None]:
    max_zip_bytes = config.max_zip_mb * 1024 * 1024
    if len(content) > max_zip_bytes:
        raise UploadValidationError(["The archive exceeds the configured zip size limit."])
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise UploadValidationError(["The uploaded file is not a valid zip archive."]) from exc

    with archive:
        infos = archive.infolist()
        if not infos or len(infos) > config.max_files:
            raise UploadValidationError(
                [f"The archive must contain between 1 and {config.max_files} entries."]
            )
        paths: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
        total_declared = 0
        try:
            for info in infos:
                path = _safe_member_path(info.filename.rstrip("/"))
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise UploadValidationError(
                        ["The archive cannot contain symbolic links."]
                    )
                if info.flag_bits & 0x1:
                    raise UploadValidationError(
                        ["Encrypted archives are not supported."]
                    )
                if info.is_dir():
                    continue
                if info.compress_type not in {
                    zipfile.ZIP_STORED,
                    zipfile.ZIP_DEFLATED,
                }:
                    raise UploadValidationError(
                        ["The archive uses an unsupported compression method."]
                    )
                if path.suffix.lower() not in ALLOWED_EXTENSIONS:
                    raise UploadValidationError(
                        [f"{path.name} uses a file type that is not allowed."]
                    )
                if info.file_size and (
                    info.compress_size == 0
                    or info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
                ):
                    raise UploadValidationError(
                        [f"{path.name} exceeds the compression ratio limit."]
                    )
                total_declared += info.file_size
                if total_declared > config.max_unzipped_mb * 1024 * 1024:
                    raise UploadValidationError(
                        ["The archive exceeds the configured unzipped size limit."]
                    )
                paths.append((info, path))
        except UploadValidationError:
            raise

        root_prefix: str | None = None
        if not any(path.as_posix() == "room.yaml" for _, path in paths):
            first_parts = {path.parts[0] for _, path in paths if len(path.parts) > 1}
            if len(first_parts) == 1 and all(len(path.parts) > 1 for _, path in paths):
                root_prefix = first_parts.pop()
                paths = [
                    (info, PurePosixPath(*path.parts[1:]))
                    for info, path in paths
                ]

        if any(path.as_posix() == "room.yaml" for _, path in paths) is False:
            raise UploadValidationError(
                ["The archive must contain room.yaml at its root."]
            )
        names = [path.as_posix() for _, path in paths]
        if len(set(names)) != len(names):
            raise UploadValidationError(["The archive contains duplicate file paths."])

        assets: dict[str, tuple[bytes, str]] = {}
        yaml_content: bytes | None = None
        host_guide: str | None = None
        total_sanitized = 0
        for info, path in paths:
            extension = path.suffix.lower()
            limit = (
                MAX_ROOM_YAML_BYTES
                if extension == ".yaml"
                else 256 * 1024
                if extension == ".md"
                else MAX_IMAGE_BYTES
                if extension in {".png", ".jpg", ".jpeg", ".webp"}
                else MAX_AUDIO_BYTES
                if extension == ".mp3"
                else config.max_unzipped_mb * 1024 * 1024
            )
            member_content = _read_member(archive, info, limit=limit)
            _check_magic(path, member_content)
            if path.as_posix() == "room.yaml":
                yaml_content = member_content
                continue
            if extension in {".png", ".jpg", ".jpeg", ".webp"}:
                member_content = _sanitize_image(path, member_content)
                media_type = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".webp": "image/webp",
                }[extension]
            elif extension == ".mp3":
                media_type = "audio/mpeg"
            elif extension == ".md":
                try:
                    host_guide = member_content.decode("utf-8")
                except UnicodeError as exc:
                    raise UploadValidationError(
                        [f"{path.name} must be UTF-8 text."]
                    ) from exc
                if len(member_content) > 256 * 1024:
                    raise UploadValidationError(
                        [f"{path.name} exceeds the 256 KB text limit."]
                    )
                media_type = "text/plain; charset=utf-8"
            else:
                media_type = "application/yaml"
            assets[path.as_posix()] = (member_content, media_type)
            total_sanitized += len(member_content)
            if total_sanitized > config.max_unzipped_mb * 1024 * 1024:
                raise UploadValidationError(
                    ["The sanitized archive exceeds the configured memory limit."]
                )

        if yaml_content is None:
            raise UploadValidationError(["The archive must contain room.yaml at its root."])
        data = _load_room_yaml(yaml_content)
        try:
            room = validate_room(data, None, set(assets))
        except RoomValidationError as exc:
            raise UploadValidationError(exc.errors) from exc
        assets["room.yaml"] = (yaml_content, "application/yaml")
        total_sanitized += len(yaml_content)
        if total_sanitized > config.max_unzipped_mb * 1024 * 1024:
            raise UploadValidationError(
                ["The sanitized archive exceeds the configured memory limit."]
            )
        if root_prefix and room["meta"]["id"] != root_prefix:
            raise UploadValidationError(
                ["The room id must match the archive's top-level folder."]
            )
        return room, assets, host_guide
