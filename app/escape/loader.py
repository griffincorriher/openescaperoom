from __future__ import annotations

import base64
import io
import logging
import math
import re
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from PIL import Image, UnidentifiedImageError
from yaml.tokens import AliasToken, AnchorToken

MAX_ROOM_YAML_BYTES = 256 * 1024
MAX_PUZZLES = 100
HOTSPOT_MIN_TAP_PERCENT = 2
HOTSPOT_MAX_COVERAGE_PERCENT = 25
HOTSPOT_LOW_RESOLUTION_PIXELS = 400
MAX_HOTSPOT_IMAGE_PIXELS = 40_000_000
MAX_HOTSPOT_PREVIEW_BYTES = 8 * 1024 * 1024
logger = logging.getLogger(__name__)
ROOM_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PUZZLE_ID_PATTERN = ROOM_ID_PATTERN
TEAM_SIZE_PATTERN = re.compile(r"^(\d+)(?:-(\d+))?$")
DIFFICULTIES = {"easy", "medium", "hard"}
PUZZLE_TYPES = {
    "text",
    "multiple_choice",
    "lock",
    "split_clue",
    "cipher",
    "ordering",
    "matching",
    "pick_all",
    "meta",
    "image_hotspot",
}
ROOT_FIELDS = {"meta", "settings", "story", "puzzles"}
META_FIELDS = {
    "id",
    "title",
    "author",
    "difficulty",
    "est_minutes",
    "team_size",
    "tags",
    "cover",
}
SETTINGS_FIELDS = {
    "time_limit_min",
    "hint_penalty_sec",
    "wrong_answer_cooldown_sec",
}
STORY_FIELDS = {"intro", "intro_image", "outro", "outro_image"}
PUZZLE_COMMON_FIELDS = {
    "id",
    "title",
    "prestory",
    "type",
    "prompt",
    "image",
    "overlay_text",
    "requires",
    "hints",
    "solve_text",
    "gives",
}
PUZZLE_TYPE_FIELDS = {
    "text": {"answers"},
    "multiple_choice": {"options", "answer"},
    "lock": {"format", "length", "answer"},
    "split_clue": {"fragments", "answer"},
    "cipher": {"method", "shift", "plaintext", "answer"},
    "ordering": {"items", "answer"},
    "matching": {"left", "right", "answer"},
    "pick_all": {"options", "answer"},
    "meta": {"answer"},
    "image_hotspot": {"regions", "tolerance"},
}


class RoomValidationError(ValueError):
    def __init__(
        self,
        errors: list[str],
        *,
        warnings: list[str] | None = None,
        hotspots: list[dict[str, Any]] | None = None,
    ) -> None:
        self.errors = errors
        self.warnings = warnings or []
        self.hotspots = hotspots or []
        super().__init__("; ".join(errors))


def _is_text(value: Any, *, minimum: int = 1, maximum: int = 4096) -> bool:
    return isinstance(value, str) and minimum <= len(value.strip()) <= maximum


def _normalized_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _finite_number(value: Any) -> bool:
    return type(value) is int or (type(value) is float and math.isfinite(value))


def _preview_regions(regions: Any) -> list[dict[str, float]]:
    if not isinstance(regions, list):
        return []
    preview: list[dict[str, float]] = []
    for region in regions:
        if not isinstance(region, dict):
            continue
        preview.append(
            {
                key: float(max(-100, min(100, region[key])))
                if key in region and _finite_number(region[key])
                else 0.0
                for key in ("x", "y", "w", "h")
            }
        )
    return preview


def _hotspot_union_area(regions: list[dict[str, float]], tolerance: float) -> float:
    rectangles = [
        (
            max(0.0, region["x"] - tolerance),
            min(100.0, region["x"] + region["w"] + tolerance),
            max(0.0, region["y"] - tolerance),
            min(100.0, region["y"] + region["h"] + tolerance),
        )
        for region in regions
    ]
    x_edges = sorted({edge for left, right, _, _ in rectangles for edge in (left, right)})
    area = 0.0
    for left, right in zip(x_edges, x_edges[1:]):
        if right <= left:
            continue
        intervals = sorted(
            (top, bottom)
            for rect_left, rect_right, top, bottom in rectangles
            if rect_left < right and rect_right > left
        )
        covered_y = 0.0
        if intervals:
            start, end = intervals[0]
            for top, bottom in intervals[1:]:
                if top > end:
                    covered_y += end - start
                    start, end = top, bottom
                else:
                    end = max(end, bottom)
            covered_y += end - start
        area += (right - left) * covered_y
    return area / 100.0


def _hotspot_image_details(
    image_path: str,
    *,
    room_dir: Path | None,
    available_assets: set[str] | None,
    asset_data: dict[str, bytes] | None,
    label: str,
    errors: list[str],
    warnings: list[str],
) -> tuple[int, int, bytes | None]:
    if not isinstance(image_path, str) or not image_path.strip():
        errors.append(f"{label}.image is required for image_hotspot.")
        return 0, 0, None
    if "\x00" in image_path or "\\" in image_path:
        errors.append(f"{label}.image must be inside the room folder.")
        return 0, 0, None
    path = PurePosixPath(image_path)
    if path.is_absolute() or any(part in {"..", "", "."} for part in path.parts):
        errors.append(f"{label}.image must be inside the room folder.")
        return 0, 0, None
    if available_assets is not None:
        if image_path not in available_assets:
            errors.append(f"{label}.image file not found: {image_path}")
            return 0, 0, None
        image_bytes = (asset_data or {}).get(image_path)
        if image_bytes is None:
            warnings.append(
                f"{label}.image could not be inspected because file content is unavailable."
            )
            return 0, 0, None
        source: str | io.BytesIO = io.BytesIO(image_bytes)
    elif room_dir is not None:
        resolved = (room_dir / Path(*path.parts)).resolve()
        try:
            resolved.relative_to(room_dir.resolve())
        except ValueError:
            errors.append(f"{label}.image must be inside the room folder.")
            return 0, 0, None
        if not resolved.is_file():
            errors.append(f"{label}.image file not found: {image_path}")
            return 0, 0, None
        image_bytes = None
        source = str(resolved)
    else:
        warnings.append(
            f"{label}.image could not be checked because room files are unavailable."
        )
        return 0, 0, None

    allowed_formats = {
        ".png": "PNG",
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".webp": "WEBP",
    }
    expected_format = allowed_formats.get(path.suffix.lower())
    if expected_format is None:
        errors.append(f"{label}.image must reference a PNG, JPG, or WEBP image.")
        return 0, 0, image_bytes

    try:
        with Image.open(source) as image:
            if image.format != expected_format:
                raise UnidentifiedImageError("Image format does not match extension.")
            width, height = image.size
            if width * height > MAX_HOTSPOT_IMAGE_PIXELS:
                errors.append(f"{label}.image exceeds the image pixel limit.")
                return width, height, image_bytes
            image.load()
    except (
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        errors.append(f"{label}.image could not be read as an image: {image_path}")
        return 0, 0, image_bytes

    if min(width, height) < HOTSPOT_LOW_RESOLUTION_PIXELS:
        warnings.append(
            f"{label}.image is only {min(width, height)}px on its shorter side "
            "and may look blurry."
        )
    return width, height, image_bytes


def _validate_hotspot_regions(
    regions: Any,
    tolerance: float,
    *,
    label: str,
    errors: list[str],
    warnings: list[str],
) -> list[dict[str, float]]:
    if not isinstance(regions, list) or not regions:
        errors.append(f"{label}.regions must contain at least one region.")
        return []
    if len(regions) > 50:
        errors.append(f"{label}.regions must contain no more than 50 regions.")
        return []

    valid_regions: list[dict[str, float]] = []
    for index, region in enumerate(regions):
        region_label = f"{label}.regions[{index}]"
        if not isinstance(region, dict):
            errors.append(f"{region_label} must be a mapping.")
            continue
        if set(region) != {"x", "y", "w", "h"}:
            errors.append(f"{region_label} must contain only x, y, w, and h.")
            continue
        valid = True
        for key in ("x", "y", "w", "h"):
            value = region[key]
            if not _finite_number(value):
                errors.append(f"{region_label}.{key} must be a number.")
                valid = False
            elif key in {"x", "y"} and not 0 <= value <= 100:
                errors.append(f"{region_label}.{key} must be between 0 and 100.")
                valid = False
            elif key in {"w", "h"} and value <= 0:
                errors.append(f"{region_label}.{key} must be greater than 0.")
                valid = False
        if not valid:
            continue
        if region["x"] + region["w"] > 100:
            errors.append(
                f"{region_label} extends past the right edge "
                f"(x + w = {region['x'] + region['w']:g})."
            )
            continue
        if region["y"] + region["h"] > 100:
            errors.append(
                f"{region_label} extends past the bottom edge "
                f"(y + h = {region['y'] + region['h']:g})."
            )
            continue

        normalized_region = {
            key: float(region[key]) for key in ("x", "y", "w", "h")
        }
        valid_regions.append(normalized_region)
        padded_width = min(100.0, normalized_region["x"] + normalized_region["w"] + tolerance) - max(
            0.0, normalized_region["x"] - tolerance
        )
        padded_height = min(100.0, normalized_region["y"] + normalized_region["h"] + tolerance) - max(
            0.0, normalized_region["y"] - tolerance
        )
        if min(padded_width, padded_height) < HOTSPOT_MIN_TAP_PERCENT:
            warnings.append(
                f"{region_label} is very small "
                f"(w {padded_width:g}%, h {padded_height:g}%) and may be hard "
                "to tap on a phone."
            )

    if valid_regions:
        coverage = _hotspot_union_area(valid_regions, tolerance)
        if coverage > HOTSPOT_MAX_COVERAGE_PERCENT:
            warnings.append(
                f"{label} regions cover {coverage:.0f}% of the image; "
                "random clicks may succeed."
            )
    return valid_regions


def _validate_asset_path(
    value: Any,
    room_dir: Path | None,
    field: str,
    errors: list[str],
    available_assets: set[str] | None = None,
) -> None:
    if value is None:
        return
    if not isinstance(value, str) or "\x00" in value or "\\" in value:
        errors.append(f"{field} must be a relative asset path.")
        return
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"..", "", "."} for part in path.parts):
        errors.append(f"{field} must stay within the room folder.")
        return
    if available_assets is not None:
        if value not in available_assets:
            errors.append(f"{field} points to a missing asset.")
            return
    else:
        if room_dir is None:
            errors.append(f"{field} points to a missing asset.")
            return
        resolved = (room_dir / Path(*path.parts)).resolve()
        try:
            resolved.relative_to(room_dir.resolve())
        except ValueError:
            errors.append(f"{field} must stay within the room folder.")
            return
        if not resolved.is_file():
            errors.append(f"{field} points to a missing asset.")
            return
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        errors.append(f"{field} must reference a PNG, JPG, or WEBP image.")


def validate_room(
    data: Any,
    room_dir: Path | None,
    available_assets: set[str] | None = None,
    *,
    asset_data: dict[str, bytes] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    validation_warnings: list[str] = []
    if not isinstance(data, dict):
        raise RoomValidationError(["room.yaml must contain a mapping."])
    unknown = set(data) - ROOT_FIELDS
    missing = ROOT_FIELDS - set(data)
    if unknown:
        errors.append(f"Unknown room field: {sorted(unknown, key=str)[0]}")
    if missing:
        errors.append(f"Missing room field: {sorted(missing, key=str)[0]}")

    meta = data.get("meta")
    settings = data.get("settings")
    story = data.get("story")
    puzzles = data.get("puzzles")
    if not isinstance(meta, dict):
        errors.append("meta must be a mapping.")
        meta = {}
    if not isinstance(settings, dict):
        errors.append("settings must be a mapping.")
        settings = {}
    if not isinstance(story, dict):
        errors.append("story must be a mapping.")
        story = {}
    if not isinstance(puzzles, list) or not puzzles:
        errors.append("puzzles must be a non-empty list.")
        puzzles = []

    for label, mapping, fields in (
        ("meta", meta, META_FIELDS),
        ("settings", settings, SETTINGS_FIELDS),
        ("story", story, STORY_FIELDS),
    ):
        unknown_fields = set(mapping) - fields
        if unknown_fields:
            errors.append(
                f"Unknown {label} field: {sorted(unknown_fields, key=str)[0]}"
            )

    room_id = meta.get("id")
    if not isinstance(room_id, str) or not ROOM_ID_PATTERN.fullmatch(room_id):
        errors.append("meta.id must be lowercase words separated by hyphens.")
    elif room_dir is not None and room_dir.name != room_id:
        errors.append("meta.id must match its room folder name.")
    for key in ("title", "author"):
        if not _is_text(meta.get(key), maximum=120):
            errors.append(f"meta.{key} must be 1-120 characters.")
    if not isinstance(meta.get("difficulty"), str) or meta["difficulty"] not in DIFFICULTIES:
        errors.append("meta.difficulty must be easy, medium, or hard.")
    if type(meta.get("est_minutes")) is not int or not 1 <= meta["est_minutes"] <= 240:
        errors.append("meta.est_minutes must be an integer from 1 to 240.")
    team_size = meta.get("team_size")
    team_match = TEAM_SIZE_PATTERN.fullmatch(team_size) if isinstance(team_size, str) else None
    if not team_match or int(team_match.group(1)) < 1:
        errors.append("meta.team_size must be a number or a range such as '3-6'.")
        minimum_team_size, maximum_team_size = 1, 8
    else:
        minimum_team_size = int(team_match.group(1))
        maximum_team_size = int(team_match.group(2) or team_match.group(1))
        if maximum_team_size < minimum_team_size or maximum_team_size > 40:
            errors.append("meta.team_size range must be ordered and no higher than 40.")
    tags = meta.get("tags")
    if (
        not isinstance(tags, list)
        or not 1 <= len(tags) <= 10
        or not all(_is_text(tag, maximum=30) for tag in tags)
    ):
        errors.append("meta.tags must contain 1-10 short strings.")

    for key, maximum in (
        ("time_limit_min", 240),
        ("hint_penalty_sec", 3600),
        ("wrong_answer_cooldown_sec", 300),
    ):
        value = settings.get(key)
        if type(value) is not int or value < 0 or value > maximum:
            errors.append(f"settings.{key} must be an integer from 0 to {maximum}.")
    if type(settings.get("time_limit_min")) is int and settings["time_limit_min"] < 1:
        errors.append("settings.time_limit_min must be at least 1.")

    for key in ("intro", "outro"):
        if not _is_text(story.get(key), maximum=2000):
            errors.append(f"story.{key} must be 1-2000 characters.")
    for key in ("intro_image", "outro_image"):
        _validate_asset_path(
            story.get(key), room_dir, f"story.{key}", errors, available_assets
        )
    _validate_asset_path(
        meta.get("cover"), room_dir, "meta.cover", errors, available_assets
    )

    if len(puzzles) > MAX_PUZZLES:
        errors.append(f"A room may contain no more than {MAX_PUZZLES} puzzles.")
    by_id: dict[str, dict[str, Any]] = {}
    for index, puzzle in enumerate(puzzles):
        label = f"puzzles[{index}]"
        if not isinstance(puzzle, dict):
            errors.append(f"{label} must be a mapping.")
            continue
        puzzle_id = puzzle.get("id")
        if not isinstance(puzzle_id, str) or not PUZZLE_ID_PATTERN.fullmatch(puzzle_id):
            errors.append(f"{label}.id must be lowercase words separated by hyphens.")
        elif puzzle_id in by_id:
            errors.append(f"Duplicate puzzle id: {puzzle_id}")
        else:
            by_id[puzzle_id] = puzzle

        puzzle_type = puzzle.get("type")
        if not isinstance(puzzle_type, str) or puzzle_type not in PUZZLE_TYPES:
            errors.append(f"{label}.type is unsupported.")
        allowed_fields = PUZZLE_COMMON_FIELDS | (
            PUZZLE_TYPE_FIELDS.get(puzzle_type, set())
            if isinstance(puzzle_type, str)
            else set()
        )
        unknown_puzzle_fields = set(puzzle) - allowed_fields
        if unknown_puzzle_fields:
            errors.append(
                f"Unknown {label} field: {sorted(unknown_puzzle_fields, key=str)[0]}"
            )
        for key in ("title", "prompt", "prestory", "solve_text"):
            maximum = 2000 if key == "prestory" else 4000
            if not _is_text(puzzle.get(key), maximum=maximum):
                errors.append(f"{label}.{key} must be 1-{maximum} characters.")
        prestory = puzzle.get("prestory")
        if not isinstance(prestory, str) or len(prestory.split()) > 50:
            errors.append(f"{label}.prestory must be no more than 50 words.")
        if puzzle_type == "text":
            answers = puzzle.get("answers")
            if (
                not isinstance(answers, list)
                or not answers
                or not all(_is_text(answer, maximum=200) for answer in answers)
            ):
                errors.append(f"{label}.answers must be a non-empty list of answers.")
        elif puzzle_type == "multiple_choice":
            options = puzzle.get("options")
            if (
                not isinstance(options, list)
                or not 3 <= len(options) <= 5
                or not all(_is_text(option, maximum=200) for option in options)
            ):
                errors.append(f"{label}.options must contain 3-5 strings.")
            if isinstance(options, list) and puzzle.get("answer") not in options:
                errors.append(f"{label}.answer must match one of its options.")
        elif puzzle_type == "lock":
            if not isinstance(puzzle.get("format"), str) or puzzle["format"] not in {
                "digits",
                "letters",
                "directions",
            }:
                errors.append(f"{label}.format must be digits, letters, or directions.")
            if type(puzzle.get("length")) is not int or not 1 <= puzzle["length"] <= 32:
                errors.append(f"{label}.length must be an integer from 1 to 32.")
            if not _is_text(puzzle.get("answer"), maximum=200):
                errors.append(f"{label}.answer must be 1-200 characters.")
            elif type(puzzle.get("length")) is int:
                normalized_answer = _normalized_text(puzzle["answer"])
                format_pattern = (
                    {
                        "digits": r"[0-9]+",
                        "letters": r"[A-Za-z]+",
                        "directions": r"[NESWnesw]+",
                    }.get(puzzle["format"])
                    if isinstance(puzzle.get("format"), str)
                    else None
                )
                if len(normalized_answer) != puzzle["length"] or (
                    format_pattern is not None
                    and not re.fullmatch(format_pattern, normalized_answer)
                ):
                    errors.append(
                        f"{label}.answer must match its format and declared length."
                    )
        elif puzzle_type == "split_clue":
            fragments = puzzle.get("fragments")
            if (
                not isinstance(fragments, list)
                or not 2 <= len(fragments) <= 40
                or not all(_is_text(fragment, maximum=200) for fragment in fragments)
            ):
                errors.append(f"{label}.fragments must contain 2-40 strings.")
            if not _is_text(puzzle.get("answer"), maximum=200):
                errors.append(f"{label}.answer must be 1-200 characters.")
        elif puzzle_type == "cipher":
            if not isinstance(puzzle.get("method"), str) or puzzle["method"] not in {
                "caesar",
                "atbash",
                "reverse",
            }:
                errors.append(f"{label}.method must be caesar, atbash, or reverse.")
            shift = puzzle.get("shift", 0)
            if type(shift) is not int or not 0 <= shift <= 25:
                errors.append(f"{label}.shift must be an integer from 0 to 25.")
            if not _is_text(puzzle.get("plaintext"), maximum=1000):
                errors.append(f"{label}.plaintext must be 1-1000 characters.")
            if not _is_text(puzzle.get("answer"), maximum=200):
                errors.append(f"{label}.answer must be 1-200 characters.")
        elif puzzle_type == "ordering":
            items = puzzle.get("items")
            if (
                not isinstance(items, list)
                or not 2 <= len(items) <= 20
                or not all(_is_text(item, maximum=200) for item in items)
                or len(set(items)) != len(items)
            ):
                errors.append(f"{label}.items must contain 2-20 unique strings.")
            if puzzle.get("answer") != "ordered":
                errors.append(f"{label}.answer must be 'ordered'.")
        elif puzzle_type == "matching":
            left = puzzle.get("left")
            right = puzzle.get("right")
            valid_left = (
                isinstance(left, list)
                and 2 <= len(left) <= 20
                and all(_is_text(item, maximum=200) for item in left)
                and all(_normalized_text(item) for item in left)
                and len({_normalized_text(item) for item in left}) == len(left)
            )
            valid_right = (
                isinstance(right, list)
                and 2 <= len(right) <= 20
                and all(_is_text(item, maximum=200) for item in right)
                and all(_normalized_text(item) for item in right)
                and len({_normalized_text(item) for item in right}) == len(right)
            )
            if not valid_left:
                errors.append(
                    f"{label}.left must contain 2-20 unique, non-empty strings."
                )
            if not valid_right:
                errors.append(
                    f"{label}.right must contain 2-20 unique, non-empty strings."
                )
            if (
                isinstance(left, list)
                and isinstance(right, list)
                and len(left) != len(right)
            ):
                errors.append(f"{label}.left and {label}.right must have the same length.")
            if puzzle.get("answer") != "paired":
                errors.append(f"{label}.answer must be 'paired'.")
        elif puzzle_type == "pick_all":
            options = puzzle.get("options")
            answers = puzzle.get("answer")
            valid_options = (
                isinstance(options, list)
                and 3 <= len(options) <= 10
                and all(_is_text(option, maximum=200) for option in options)
                and all(_normalized_text(option) for option in options)
                and len({_normalized_text(option) for option in options})
                == len(options)
            )
            valid_answers = (
                isinstance(answers, list)
                and 1 <= len(answers) <= 10
                and all(_is_text(answer, maximum=200) for answer in answers)
                and all(_normalized_text(answer) for answer in answers)
                and len({_normalized_text(answer) for answer in answers})
                == len(answers)
            )
            if not valid_options:
                errors.append(
                    f"{label}.options must contain 3-10 unique strings."
                )
            if not valid_answers:
                errors.append(
                    f"{label}.answer must contain 1-10 unique correct options."
                )
            if valid_options and valid_answers:
                normalized_options = {_normalized_text(option) for option in options}
                if any(
                    _normalized_text(answer) not in normalized_options
                    for answer in answers
                ):
                    errors.append(
                        f"{label}.answer entries must match options."
                    )
        elif puzzle_type == "image_hotspot":
            tolerance = puzzle.get("tolerance", 0)
            if (
                not _finite_number(tolerance)
                or not 0 <= tolerance <= 10
            ):
                errors.append(
                    f"{label}.tolerance must be between 0 and 10."
                )
                tolerance = 0
            _validate_hotspot_regions(
                puzzle.get("regions"),
                float(tolerance),
                label=label,
                errors=errors,
                warnings=validation_warnings,
            )
            _hotspot_image_details(
                puzzle.get("image"),
                room_dir=room_dir,
                available_assets=available_assets,
                asset_data=asset_data,
                label=label,
                errors=errors,
                warnings=validation_warnings,
            )
        else:
            if not _is_text(puzzle.get("answer"), maximum=200):
                errors.append(f"{label}.answer must be 1-200 characters.")

        hints = puzzle.get("hints")
        if (
            not isinstance(hints, list)
            or len(hints) != 3
            or not all(_is_text(hint, maximum=500) for hint in hints)
        ):
            errors.append(f"{label}.hints must contain exactly 3 hints.")
        if puzzle_type != "ordering" and isinstance(prestory, str):
            prestory_normalized = _normalized_text(prestory)
            answer_values = (
                puzzle.get("answers")
                if puzzle_type == "text"
                else puzzle.get("answer")
                if puzzle_type == "pick_all"
                else [puzzle.get("answer")]
            )
            if isinstance(answer_values, list) and any(
                isinstance(answer, str)
                and len(_normalized_text(answer)) >= 3
                and _normalized_text(answer) in prestory_normalized
                for answer in answer_values
            ):
                errors.append(f"{label}.prestory must not contain its answer.")
        requires = puzzle.get("requires")
        if not isinstance(requires, list) or not all(
            isinstance(required_id, str) for required_id in requires
        ):
            errors.append(f"{label}.requires must be a list of puzzle ids.")
        elif len(set(requires)) != len(requires):
            errors.append(f"{label}.requires cannot contain duplicates.")
        for asset_field in ("image",):
            if puzzle_type != "image_hotspot":
                _validate_asset_path(
                    puzzle.get(asset_field),
                    room_dir,
                    f"{label}.{asset_field}",
                    errors,
                    available_assets,
                )
        if "gives" in puzzle and not _is_text(puzzle["gives"], maximum=100):
            errors.append(f"{label}.gives must be 1-100 characters.")

    puzzle_ids = set(by_id)
    initial_count = 0
    for puzzle_id, puzzle in by_id.items():
        requires = puzzle.get("requires")
        if not isinstance(requires, list):
            continue
        if not requires:
            initial_count += 1
        for required_id in requires:
            if not isinstance(required_id, str):
                continue
            if required_id not in puzzle_ids:
                errors.append(f"Puzzle '{puzzle_id}' requires unknown puzzle '{required_id}'.")
    if initial_count < 1:
        errors.append("At least one puzzle must be open at the start.")
    if sum(puzzle.get("type") == "meta" for puzzle in by_id.values()) != 1:
        errors.append("A room must contain exactly one meta puzzle.")

    if by_id:
        meta_puzzles = [puzzle for puzzle in by_id.values() if puzzle.get("type") == "meta"]
        give_ids = {
            puzzle_id
            for puzzle_id, puzzle in by_id.items()
            if "gives" in puzzle
        }
        if meta_puzzles:
            meta_requires = meta_puzzles[0].get("requires")
            if (
                isinstance(meta_requires, list)
                and all(isinstance(item, str) for item in meta_requires)
                and set(meta_requires) != give_ids
            ):
                errors.append("The meta puzzle must require every puzzle with a gives field.")

        visited: set[str] = set()
        visiting: set[str] = set()

        def visit(puzzle_id: str) -> None:
            if puzzle_id in visiting:
                errors.append(f"Puzzle requirements contain a cycle at '{puzzle_id}'.")
                return
            if puzzle_id in visited:
                return
            visiting.add(puzzle_id)
            for dependency in by_id[puzzle_id].get("requires", []):
                if isinstance(dependency, str) and dependency in by_id:
                    visit(dependency)
            visiting.remove(puzzle_id)
            visited.add(puzzle_id)

        for puzzle_id in by_id:
            visit(puzzle_id)

    hotspots: list[dict[str, Any]] = []
    preview_bytes = 0
    preview_data_urls: dict[str, str] = {}
    for index, puzzle in enumerate(puzzles):
        if not isinstance(puzzle, dict) or puzzle.get("type") != "image_hotspot":
            continue
        label = f"puzzles[{index}]"
        image_path = puzzle.get("image")
        image_data_url = None
        if isinstance(image_path, str) and image_path in (asset_data or {}):
            image_bytes = asset_data[image_path]
            if image_path in preview_data_urls:
                image_data_url = preview_data_urls[image_path]
            elif preview_bytes + len(image_bytes) <= MAX_HOTSPOT_PREVIEW_BYTES:
                extension = PurePosixPath(image_path).suffix.lower()
                media_type = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".webp": "image/webp",
                }.get(extension)
                if media_type:
                    image_data_url = (
                        f"data:{media_type};base64,"
                        f"{base64.b64encode(image_bytes).decode('ascii')}"
                    )
                    preview_data_urls[image_path] = image_data_url
                    preview_bytes += len(image_bytes)
        regions = puzzle.get("regions")
        hotspots.append(
            {
                "id": puzzle.get("id")
                if isinstance(puzzle.get("id"), str)
                else f"puzzle-{index + 1}",
                "title": puzzle.get("title")
                if isinstance(puzzle.get("title"), str)
                else "",
                "prompt": puzzle.get("prompt")
                if isinstance(puzzle.get("prompt"), str)
                else "",
                "image": image_path if isinstance(image_path, str) else "",
                "image_data_url": image_data_url,
                "regions": _preview_regions(regions),
                "tolerance": puzzle.get("tolerance", 0)
                if _finite_number(puzzle.get("tolerance", 0))
                else 0,
                "errors": [error for error in errors if error.startswith(label)],
                "warnings": [
                    warning
                    for warning in validation_warnings
                    if warning.startswith(label)
                ],
            }
        )

    if diagnostics is not None:
        diagnostics["warnings"] = validation_warnings
        diagnostics["hotspots"] = hotspots
    if errors:
        raise RoomValidationError(
            errors, warnings=validation_warnings, hotspots=hotspots
        )
    return {
        "meta": meta,
        "settings": settings,
        "story": story,
        "puzzles": puzzles,
        "min_team_size": minimum_team_size,
        "max_team_size": maximum_team_size,
        "puzzle_by_id": by_id,
    }


def load_room(room_dir: Path) -> dict[str, Any]:
    yaml_path = room_dir / "room.yaml"
    try:
        if yaml_path.stat().st_size > MAX_ROOM_YAML_BYTES:
            raise RoomValidationError(["room.yaml is larger than 256 KB."])
        content = yaml_path.read_text(encoding="utf-8")
        for token in yaml.scan(content):
            if isinstance(token, (AliasToken, AnchorToken)):
                raise RoomValidationError(["room.yaml cannot use YAML anchors or aliases."])
        data = yaml.safe_load(content)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise RoomValidationError([f"Could not read room.yaml: {exc}"]) from exc
    room_warnings: list[str] = []
    room = validate_room(data, room_dir, diagnostics={"warnings": room_warnings})
    for warning in room_warnings:
        logger.warning("Room '%s' validation warning: %s", room_dir.name, warning)
    return room
