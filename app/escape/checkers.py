from __future__ import annotations

import math
import unicodedata
from typing import Any


def normalize_answer(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _finite_number(value: object) -> bool:
    return type(value) is int or (type(value) is float and math.isfinite(value))


def is_hotspot_hit(
    regions: object, tolerance: object, x: object, y: object
) -> tuple[bool, int | None]:
    if (
        not _finite_number(x)
        or not _finite_number(y)
        or not 0 <= x <= 100
        or not 0 <= y <= 100
    ):
        return False, None
    if (
        not _finite_number(tolerance)
        or not 0 <= tolerance <= 10
        or not isinstance(regions, list)
    ):
        return False, None
    for index, region in enumerate(regions):
        if not isinstance(region, dict) or set(region) != {"x", "y", "w", "h"}:
            continue
        values = [region[key] for key in ("x", "y", "w", "h")]
        if any(
            not _finite_number(value)
            for value in values
        ):
            continue
        left = max(0.0, region["x"] - tolerance)
        top = max(0.0, region["y"] - tolerance)
        right = min(100.0, region["x"] + region["w"] + tolerance)
        bottom = min(100.0, region["y"] + region["h"] + tolerance)
        if left <= x <= right and top <= y <= bottom:
            return True, index
    return False, None


def _check_hotspot(puzzle: dict[str, Any], answer: object) -> bool:
    if not isinstance(answer, dict) or set(answer) != {"x", "y"}:
        return False
    hit, _ = is_hotspot_hit(
        puzzle.get("regions"),
        puzzle.get("tolerance", 0),
        answer["x"],
        answer["y"],
    )
    return hit


def _check_matching(puzzle: dict[str, Any], answer: object) -> bool:
    left = puzzle.get("left")
    right = puzzle.get("right")
    return (
        isinstance(left, list)
        and isinstance(right, list)
        and isinstance(answer, list)
        and len(left) == len(right) == len(answer)
        and all(
            isinstance(actual, str)
            and isinstance(expected, str)
            and normalize_answer(actual) == normalize_answer(expected)
            for actual, expected in zip(answer, right, strict=True)
        )
    )


def _check_pick_all(puzzle: dict[str, Any], answer: object) -> bool:
    expected = puzzle.get("answer")
    if (
        not isinstance(expected, list)
        or not isinstance(answer, list)
        or len(answer) != len(expected)
        or not all(isinstance(item, str) for item in expected)
        or not all(isinstance(item, str) for item in answer)
    ):
        return False
    normalized_answer = [normalize_answer(item) for item in answer]
    normalized_expected = [normalize_answer(item) for item in expected]
    return (
        all(normalized_answer)
        and all(normalized_expected)
        and len(set(normalized_answer)) == len(normalized_answer)
        and len(set(normalized_expected)) == len(normalized_expected)
        and set(normalized_answer) == set(normalized_expected)
    )


def check_answer(puzzle: dict[str, Any], answer: object) -> bool:
    puzzle_type = puzzle.get("type")
    if puzzle_type == "image_hotspot":
        return _check_hotspot(puzzle, answer)
    if puzzle_type == "matching":
        return _check_matching(puzzle, answer)
    if puzzle_type == "pick_all":
        return _check_pick_all(puzzle, answer)
    if puzzle_type == "ordering":
        expected = puzzle.get("items")
        return (
            isinstance(answer, list)
            and isinstance(expected, list)
            and len(answer) == len(expected)
            and all(
                isinstance(actual, str)
                and isinstance(correct, str)
                and normalize_answer(actual) == normalize_answer(correct)
                for actual, correct in zip(answer, expected, strict=True)
            )
        )
    if not isinstance(answer, str):
        return False
    if puzzle_type == "text":
        correct_answers = puzzle.get("answers", [])
    elif puzzle_type in {
        "multiple_choice",
        "lock",
        "split_clue",
        "cipher",
        "meta",
    }:
        correct_answers = [puzzle.get("answer", "")]
    else:
        return False
    return any(
        isinstance(correct, str)
        and normalize_answer(correct) == normalize_answer(answer)
        for correct in correct_answers
    )
