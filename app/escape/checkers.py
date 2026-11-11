from __future__ import annotations

import math
import unicodedata
from typing import Any


def normalize_answer(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _check_hotspot(puzzle: dict[str, Any], answer: object) -> bool:
    if not isinstance(answer, dict) or set(answer) != {"x", "y"}:
        return False
    x = answer["x"]
    y = answer["y"]
    if (
        type(x) not in {int, float}
        or type(y) not in {int, float}
        or not math.isfinite(x)
        or not math.isfinite(y)
        or not 0 <= x <= 100
        or not 0 <= y <= 100
    ):
        return False
    return any(
        region["x"] <= x <= region["x"] + region["w"]
        and region["y"] <= y <= region["y"] + region["h"]
        for region in puzzle.get("regions", [])
    )


def check_answer(puzzle: dict[str, Any], answer: object) -> bool:
    puzzle_type = puzzle.get("type")
    if puzzle_type == "image_hotspot":
        return _check_hotspot(puzzle, answer)
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
