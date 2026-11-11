from __future__ import annotations

import re
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from yaml.tokens import AliasToken, AnchorToken

MAX_ROOM_YAML_BYTES = 256 * 1024
MAX_PUZZLES = 100
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
    "meta": {"answer"},
    "image_hotspot": {"regions"},
}


class RoomValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def _is_text(value: Any, *, minimum: int = 1, maximum: int = 4096) -> bool:
    return isinstance(value, str) and minimum <= len(value.strip()) <= maximum


def _normalized_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


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
) -> dict[str, Any]:
    errors: list[str] = []
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
        elif puzzle_type == "image_hotspot":
            regions = puzzle.get("regions")
            if (
                not isinstance(regions, list)
                or not regions
                or len(regions) > 50
                or not all(
                    isinstance(region, dict)
                    and set(region) == {"x", "y", "w", "h"}
                    and all(
                        type(region[key]) in {int, float}
                        and 0 <= region[key] <= 100
                        for key in ("x", "y", "w", "h")
                    )
                    and region["w"] > 0
                    and region["h"] > 0
                    and region["x"] + region["w"] <= 100
                    and region["y"] + region["h"] <= 100
                    for region in regions
                )
            ):
                errors.append(
                    f"{label}.regions must contain 1-50 percentage rectangles "
                    "with x, y, w, and h within the image."
                )
            if not puzzle.get("image"):
                errors.append(f"{label}.image is required for image_hotspot.")
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

    if errors:
        raise RoomValidationError(errors)
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
    return validate_room(data, room_dir)
