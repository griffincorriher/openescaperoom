from __future__ import annotations

import string
import time
from dataclasses import dataclass, field
from typing import Any
from random import SystemRandom

from app.escape.checkers import check_answer
from app.escape.store import RoomStore
from app.games import Game
from app.lobby import LobbyManager


class EscapeEngineError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass
class TeamProgress:
    team_id: str
    name: str
    members: set[str]
    solved: set[str] = field(default_factory=set)
    skipped: set[str] = field(default_factory=set)
    opened: dict[str, set[str]] = field(default_factory=dict)
    hints_used: dict[str, int] = field(default_factory=dict)
    hint_penalty_sec: int = 0
    skip_penalty_sec: int = 0
    wrong_attempts: dict[str, int] = field(default_factory=dict)
    solves_by_player: dict[str, int] = field(default_factory=dict)
    solve_times: dict[str, float] = field(default_factory=dict)
    unlock_times: dict[str, float] = field(default_factory=dict)
    cooldowns: dict[str, float] = field(default_factory=dict)
    finished_at: float | None = None


@dataclass
class EscapeGameState:
    game_id: str
    room_id: str
    started_at: float
    time_limit_sec: int
    teams: dict[str, TeamProgress]
    events: list[dict[str, Any]] = field(default_factory=list)
    ended_at: float | None = None
    end_reason: str | None = None
    paused_at: float | None = None
    elapsed_before_pause: float = 0


def encode_cipher(text: str, method: str, shift: int = 0) -> str:
    if method == "reverse":
        return text[::-1]
    if method == "atbash":
        return text.translate(
            str.maketrans(
                string.ascii_lowercase + string.ascii_uppercase,
                string.ascii_lowercase[::-1] + string.ascii_uppercase[::-1],
            )
        )
    if method == "caesar":
        def shift_character(character: str) -> str:
            if "a" <= character <= "z":
                return chr((ord(character) - ord("a") + shift) % 26 + ord("a"))
            if "A" <= character <= "Z":
                return chr((ord(character) - ord("A") + shift) % 26 + ord("A"))
            return character

        return "".join(shift_character(character) for character in text)
    raise EscapeEngineError("invalid_cipher_method")


class EscapeEngine:
    def __init__(self, rooms: RoomStore, lobbies: LobbyManager) -> None:
        self.rooms = rooms
        self.lobbies = lobbies
        self.games: dict[str, EscapeGameState] = {}

    def start(self, game: Game, *, now: float | None = None) -> EscapeGameState:
        if game.game_id in self.games:
            raise EscapeEngineError("game_already_started")
        room = self._room_for(game)
        lobby = self.lobbies.states.get(game.game_id)
        if lobby is None:
            raise EscapeEngineError("lobby_not_found")
        teams: dict[str, TeamProgress] = {}
        for team_id, team in lobby.teams.items():
            members = {
                player.player_id
                for player in lobby.players.values()
                if player.team_id == team_id
            }
            if members:
                teams[team_id] = TeamProgress(team_id, team.name, members)
        if not teams:
            raise EscapeEngineError("no_teams")
        current_time = time.monotonic() if now is None else now
        state = EscapeGameState(
            game_id=game.game_id,
            room_id=game.room_id or "",
            started_at=current_time,
            time_limit_sec=room["settings"]["time_limit_min"] * 60,
            teams=teams,
        )
        self.games[game.game_id] = state
        for team in teams.values():
            for puzzle_id in self._unlocked_ids(room, team):
                team.unlock_times[puzzle_id] = 0
                self._record(
                    state,
                    "unlock",
                    current_time,
                    team_id=team.team_id,
                    puzzle_id=puzzle_id,
                    elapsed_sec=0,
                )
        return state

    def snapshot(
        self, game: Game, *, recipient_id: str, now: float | None = None
    ) -> dict[str, Any]:
        state = self._state(game)
        room = self._room_for(game)
        self._sync_members(game, state)
        team = self._team_for_player(state, recipient_id)
        current_time = time.monotonic() if now is None else now
        elapsed = self._elapsed(state, current_time)
        remaining = max(0, state.time_limit_sec - int(elapsed))
        team_snapshots = []
        for progress in state.teams.values():
            team_elapsed = self._team_elapsed(state, progress, current_time)
            team_snapshots.append(
                {
                    "team_id": progress.team_id,
                    "name": progress.name,
                    "solved_count": len(progress.solved) - len(progress.skipped),
                    "skipped_count": len(progress.skipped),
                    "total_puzzles": len(room["puzzles"]),
                    "hints_used": sum(progress.hints_used.values()),
                    "finished": progress.finished_at is not None,
                    "elapsed_sec": int(team_elapsed),
                    "adjusted_sec": (
                        int(team_elapsed)
                        + progress.hint_penalty_sec
                        + progress.skip_penalty_sec
                    ),
                }
            )
        solved_puzzles = []
        for event in state.events:
            if (
                event["type"] == "solve"
                and event["team_id"] == team.team_id
            ):
                solved_puzzles.append(
                    {
                        "puzzle_id": event["puzzle_id"],
                        "puzzle_title": room["puzzle_by_id"][event["puzzle_id"]]["title"],
                        "player_id": event["player_id"],
                        "player_name": (
                            self.lobbies.states[game.game_id].players[event["player_id"]].name
                            or "Player"
                            if event["player_id"] in self.lobbies.states[game.game_id].players
                            else "Player"
                        ),
                        "elapsed_sec": event["elapsed_sec"],
                    }
                )
        team_puzzles = []
        for puzzle in room["puzzles"]:
            puzzle_id = puzzle["id"]
            unlocked = puzzle_id in self._unlocked_ids(room, team)
            team_puzzles.append(
                {
                    "id": puzzle_id,
                    "title": puzzle["title"],
                    "type": puzzle["type"],
                    "state": (
                        "skipped"
                        if puzzle_id in team.skipped
                        else "solved"
                        if puzzle_id in team.solved
                        else "open"
                        if unlocked
                        else "locked"
                    ),
                    "hints_used": team.hints_used.get(puzzle_id, 0),
                    "solve_text": (
                        puzzle["solve_text"] if puzzle_id in team.solved else None
                    ),
                    **(
                        {
                            "answer": (
                                list(
                                    zip(puzzle["left"], puzzle["right"], strict=True)
                                )
                                if puzzle["type"] == "matching"
                                else puzzle.get(
                                    "answers",
                                    puzzle.get("answer", puzzle.get("regions")),
                                )
                            )
                        }
                        if game.is_playtest and recipient_id == game.host_player_id
                        else {}
                    ),
                }
            )

        game_snapshot: dict[str, Any] = {
            "type": "game.snapshot",
            "game_id": game.game_id,
            "code": game.code,
            "room_id": state.room_id,
            "room_title": room["meta"]["title"],
            "phase": "results" if state.ended_at is not None else "playing",
            "end_reason": state.end_reason,
            "elapsed_sec": int(elapsed),
            "remaining_sec": remaining,
            "paused": state.paused_at is not None,
            "intro": room["story"]["intro"],
            "intro_image": room["story"].get("intro_image"),
            "outro": room["story"]["outro"],
            "outro_image": room["story"].get("outro_image"),
            "player_id": recipient_id,
            "is_host": recipient_id == game.host_player_id,
            "is_playtest": game.is_playtest,
            "team_id": team.team_id,
            "team_name": team.name,
            "team_solved": len(team.solved) - len(team.skipped),
            "team_skipped": len(team.skipped),
            "teams": team_snapshots,
            "puzzles": team_puzzles,
            "solves": solved_puzzles,
            "activity": self._activity_for_team(state, team),
        }
        if state.ended_at is not None:
            results = self.results(game, now=current_time)
            lobby = self.lobbies.states.get(game.game_id)
            player_names = {
                player_id: player.name or "Player"
                for player_id, player in lobby.players.items()
            } if lobby else {}
            team_names = {
                team_id: progress.name for team_id, progress in state.teams.items()
            }
            for player in results["player_stats"]:
                player["name"] = player_names.get(player["player_id"], "Player")
            for event in results["race"]:
                event["team_name"] = team_names.get(event["team_id"], "Team")
                event["player_name"] = player_names.get(
                    event["player_id"], "Player"
                )
            for award in results["awards"]:
                recipient = (
                    player_names.get(award["player_id"])
                    if "player_id" in award
                    else team_names.get(award.get("team_id"), "Team")
                )
                award["label"] = f'{award["name"]}: {recipient or "Player"}'
            if game.is_playtest:
                results = {"player_stats": results["player_stats"]}
            game_snapshot["results"] = results
        return game_snapshot

    def _activity_for_team(
        self, state: EscapeGameState, team: TeamProgress
    ) -> list[dict[str, Any]]:
        return [
            {
                "type": event["type"],
                "puzzle_id": event.get("puzzle_id"),
                "elapsed_sec": int(
                    max(
                        0,
                        event.get(
                            "elapsed_sec",
                            event["timestamp"] - state.started_at,
                        ),
                    )
                ),
                "player_id": event.get("player_id"),
            }
            for event in state.events
            if event.get("team_id") == team.team_id
            and event["type"] in {"open", "wrong", "solve", "hint", "skip"}
        ][-30:]

    def open_puzzle(
        self, game: Game, player_id: str, puzzle_id: str, *, now: float | None = None
    ) -> dict[str, Any]:
        state, room, team, current_time = self._active_context(
            game, player_id, now=now
        )
        puzzle = room["puzzle_by_id"].get(puzzle_id)
        if puzzle is None:
            raise EscapeEngineError("puzzle_not_found")
        if puzzle_id not in self._unlocked_ids(room, team):
            raise EscapeEngineError("puzzle_locked")
        team.opened.setdefault(puzzle_id, set()).add(player_id)
        self._record(
            state,
            "open",
            current_time,
            player_id=player_id,
            team_id=team.team_id,
            puzzle_id=puzzle_id,
            elapsed_sec=round(self._elapsed(state, current_time), 3),
        )
        return self._public_puzzle(puzzle, team, player_id, room)

    def submit_answer(
        self,
        game: Game,
        player_id: str,
        puzzle_id: str,
        answer: object,
        *,
        now: float | None = None,
    ) -> dict[str, Any]:
        state, room, team, current_time = self._active_context(
            game, player_id, now=now
        )
        puzzle = room["puzzle_by_id"].get(puzzle_id)
        if puzzle is None:
            raise EscapeEngineError("puzzle_not_found")
        if puzzle_id not in self._unlocked_ids(room, team):
            raise EscapeEngineError("puzzle_locked")
        if puzzle_id in team.solved:
            raise EscapeEngineError("puzzle_already_solved")
        cooldown = team.cooldowns.get(puzzle_id, 0)
        if current_time < cooldown:
            raise EscapeEngineError("answer_cooldown")
        valid_hotspot_answer = (
            puzzle["type"] == "image_hotspot"
            and isinstance(answer, dict)
            and set(answer) == {"x", "y"}
            and all(
                type(answer[key]) in {int, float}
                and 0 <= answer[key] <= 100
                for key in ("x", "y")
            )
        )
        valid_text_answer = (
            isinstance(answer, str) and bool(answer.strip()) and len(answer) <= 512
        )
        valid_order_answer = (
            isinstance(answer, list)
            and len(answer) <= 20
            and all(isinstance(item, str) and len(item) <= 200 for item in answer)
        )
        valid_pick_answer = (
            puzzle["type"] == "pick_all"
            and isinstance(answer, list)
            and len(answer) <= 10
            and all(isinstance(item, str) and len(item) <= 200 for item in answer)
        )
        if not (
            valid_hotspot_answer
            or valid_text_answer
            or valid_order_answer
            or valid_pick_answer
        ):
            raise EscapeEngineError("invalid_answer")

        correct = check_answer(puzzle, answer)
        if correct:
            team.solved.add(puzzle_id)
            elapsed = self._elapsed(state, current_time)
            team.solve_times[puzzle_id] = elapsed
            team.solves_by_player[player_id] = team.solves_by_player.get(player_id, 0) + 1
            self._record(
                state,
                "solve",
                current_time,
                player_id=player_id,
                team_id=team.team_id,
                puzzle_id=puzzle_id,
                elapsed_sec=round(elapsed, 3),
                solve_text=puzzle["solve_text"],
            )
            for newly_unlocked in self._unlocked_ids(room, team):
                if newly_unlocked not in team.unlock_times:
                    team.unlock_times[newly_unlocked] = elapsed
                    self._record(
                        state,
                        "unlock",
                        current_time,
                        team_id=team.team_id,
                        puzzle_id=newly_unlocked,
                        elapsed_sec=round(elapsed, 3),
                    )
            meta_id = next(
                item["id"] for item in room["puzzles"] if item["type"] == "meta"
            )
            if puzzle_id == meta_id:
                team.finished_at = current_time
                self._record(
                    state,
                    "finish",
                    current_time,
                    player_id=player_id,
                    team_id=team.team_id,
                    puzzle_id=puzzle_id,
                    elapsed_sec=round(self._elapsed(state, current_time), 3),
                )
                if all(
                    progress.finished_at is not None for progress in state.teams.values()
                ):
                    self._end(state, current_time, "finished")
        else:
            team.wrong_attempts[player_id] = team.wrong_attempts.get(player_id, 0) + 1
            cooldown_seconds = room["settings"]["wrong_answer_cooldown_sec"]
            team.cooldowns[puzzle_id] = current_time + cooldown_seconds
            self._record(
                state,
                "wrong",
                current_time,
                player_id=player_id,
                team_id=team.team_id,
                puzzle_id=puzzle_id,
                elapsed_sec=round(self._elapsed(state, current_time), 3),
            )
        return {"correct": correct, "cooldown_sec": room["settings"]["wrong_answer_cooldown_sec"]}

    def set_paused(
        self, game: Game, paused: bool, *, now: float | None = None
    ) -> dict[str, Any]:
        state = self._state(game)
        current_time = time.monotonic() if now is None else now
        if state.ended_at is not None:
            raise EscapeEngineError("game_over")
        if paused:
            if state.paused_at is None:
                state.elapsed_before_pause = self._elapsed(state, current_time)
                state.paused_at = current_time
        elif state.paused_at is not None:
            pause_duration = current_time - state.paused_at
            state.started_at += pause_duration
            for team in state.teams.values():
                if team.finished_at is not None:
                    team.finished_at += pause_duration
            state.paused_at = None
        return self.clock(game, now=current_time)

    def add_time(
        self, game: Game, seconds: int, *, now: float | None = None
    ) -> dict[str, Any]:
        state = self._state(game)
        if state.ended_at is not None:
            raise EscapeEngineError("game_over")
        if type(seconds) is not int or not 1 <= seconds <= 7200:
            raise EscapeEngineError("invalid_time_amount")
        state.time_limit_sec += seconds
        current_time = time.monotonic() if now is None else now
        self._record(state, "time_added", current_time, seconds=seconds)
        return self.clock(game, now=current_time)

    def end_early(self, game: Game, *, now: float | None = None) -> None:
        state = self._state(game)
        if state.ended_at is not None:
            raise EscapeEngineError("game_over")
        current_time = time.monotonic() if now is None else now
        self._end(state, current_time, "host_ended")

    def skip_puzzle(
        self,
        game: Game,
        team_id: str,
        puzzle_id: str,
        *,
        now: float | None = None,
    ) -> dict[str, Any]:
        state = self._state(game)
        room = self._room_for(game)
        team = state.teams.get(team_id)
        puzzle = room["puzzle_by_id"].get(puzzle_id)
        if team is None:
            raise EscapeEngineError("team_not_found")
        if puzzle is None:
            raise EscapeEngineError("puzzle_not_found")
        if state.ended_at is not None:
            raise EscapeEngineError("game_over")
        if puzzle_id in team.solved:
            raise EscapeEngineError("puzzle_already_solved")
        if puzzle_id not in self._unlocked_ids(room, team):
            raise EscapeEngineError("puzzle_locked")
        current_time = time.monotonic() if now is None else now
        team.solved.add(puzzle_id)
        team.skipped.add(puzzle_id)
        team.solve_times[puzzle_id] = self._elapsed(state, current_time)
        team.skip_penalty_sec += game.skip_penalty_sec
        self._record(
            state,
            "skip",
            current_time,
            team_id=team_id,
            puzzle_id=puzzle_id,
            elapsed_sec=round(self._elapsed(state, current_time), 3),
        )
        for newly_unlocked in self._unlocked_ids(room, team):
            if newly_unlocked not in team.unlock_times:
                team.unlock_times[newly_unlocked] = self._elapsed(state, current_time)
                self._record(
                    state,
                    "unlock",
                    current_time,
                    team_id=team.team_id,
                    puzzle_id=newly_unlocked,
                    elapsed_sec=round(team.unlock_times[newly_unlocked], 3),
                )
        if puzzle["type"] == "meta":
            team.finished_at = (
                state.started_at + state.elapsed_before_pause
                if state.paused_at is not None
                else current_time
            )
        if all(progress.finished_at is not None for progress in state.teams.values()):
            self._end(state, current_time, "finished")
        return {"team_id": team_id, "puzzle_id": puzzle_id}

    def remove_player(self, game: Game, player_id: str) -> None:
        state = self._state(game)
        for team in state.teams.values():
            team.members.discard(player_id)
            team.wrong_attempts.pop(player_id, None)
            team.solves_by_player.pop(player_id, None)
            for opened in team.opened.values():
                opened.discard(player_id)

    def take_hint(
        self, game: Game, player_id: str, puzzle_id: str, *, now: float | None = None
    ) -> dict[str, Any]:
        state, room, team, current_time = self._active_context(
            game, player_id, now=now
        )
        puzzle = room["puzzle_by_id"].get(puzzle_id)
        if puzzle is None:
            raise EscapeEngineError("puzzle_not_found")
        if puzzle_id not in self._unlocked_ids(room, team):
            raise EscapeEngineError("puzzle_locked")
        if puzzle_id in team.solved:
            raise EscapeEngineError("puzzle_already_solved")
        hint_index = team.hints_used.get(puzzle_id, 0)
        hints = puzzle["hints"]
        if hint_index >= len(hints):
            raise EscapeEngineError("no_hints_left")
        team.hints_used[puzzle_id] = hint_index + 1
        penalty = room["settings"]["hint_penalty_sec"]
        team.hint_penalty_sec += penalty
        self._record(
            state,
            "hint",
            current_time,
            player_id=player_id,
            team_id=team.team_id,
            puzzle_id=puzzle_id,
            hint_index=hint_index,
            penalty_sec=penalty,
            elapsed_sec=round(self._elapsed(state, current_time), 3),
        )
        return {
            "hint": hints[hint_index],
            "hint_index": hint_index,
            "hints_remaining": len(hints) - hint_index - 1,
        }

    def tick(self, *, now: float | None = None) -> list[str]:
        current_time = time.monotonic() if now is None else now
        expired: list[str] = []
        for state in self.games.values():
            if (
                state.ended_at is None
                and self._elapsed(state, current_time) >= state.time_limit_sec
            ):
                self._end(state, current_time, "time_up")
                expired.append(state.game_id)
        return expired

    def clock(self, game: Game, *, now: float | None = None) -> dict[str, Any]:
        state = self._state(game)
        current_time = time.monotonic() if now is None else now
        elapsed = int(self._elapsed(state, current_time))
        return {
            "type": "game.clock",
            "game_id": game.game_id,
            "phase": "results" if state.ended_at is not None else "playing",
            "elapsed_sec": elapsed,
            "remaining_sec": max(0, state.time_limit_sec - elapsed),
            "paused": state.paused_at is not None,
        }

    def prune(self, active_game_ids: set[str]) -> None:
        for game_id in self.games.keys() - active_game_ids:
            self.games.pop(game_id)

    def results(self, game: Game, *, now: float | None = None) -> dict[str, Any]:
        state = self._state(game)
        current_time = time.monotonic() if now is None else now
        standings = []
        for team in state.teams.values():
            elapsed = int(self._team_elapsed(state, team, current_time))
            skipped = sum(
                1
                for event in state.events
                if event.get("team_id") == team.team_id and event["type"] == "skip"
            )
            solved = sum(
                1
                for event in state.events
                if event.get("team_id") == team.team_id and event["type"] == "solve"
            )
            standings.append(
                {
                    "team_id": team.team_id,
                    "name": team.name,
                    "solved": solved,
                    "skipped": skipped,
                    "time_sec": elapsed,
                    "hint_penalty_sec": team.hint_penalty_sec,
                    "skip_penalty_sec": team.skip_penalty_sec,
                    "adjusted_sec": (
                        elapsed + team.hint_penalty_sec + team.skip_penalty_sec
                    ),
                    "hints_used": sum(team.hints_used.values()),
                    "finished": team.finished_at is not None,
                }
            )
        standings.sort(key=lambda result: (-result["solved"], result["adjusted_sec"]))
        for rank, result in enumerate(standings, start=1):
            result["rank"] = rank
        stats: dict[str, dict[str, Any]] = {}
        for team in state.teams.values():
            for player_id in team.members:
                stats[player_id] = {
                    "player_id": player_id,
                    "solves": team.solves_by_player.get(player_id, 0),
                    "wrong_answers": team.wrong_attempts.get(player_id, 0),
                    "solve_speeds_sec": [],
                    "awards": [],
                }
        race = [
            {
                "team_id": event["team_id"],
                "puzzle_id": event["puzzle_id"],
                "elapsed_sec": event["elapsed_sec"],
                "player_id": event["player_id"],
            }
            for event in state.events
            if event["type"] == "solve"
        ]
        for team in state.teams.values():
            for event in state.events:
                if event.get("team_id") == team.team_id and event["type"] == "solve":
                    player_stats = stats.get(event.get("player_id"))
                    if player_stats is not None:
                        player_stats["solve_speeds_sec"].append(
                            event["elapsed_sec"]
                            - team.unlock_times.get(event["puzzle_id"], 0)
                        )
        speed_entries = [
            (speed, player_id)
            for player_id, player_stats in stats.items()
            for speed in player_stats["solve_speeds_sec"]
        ]
        awards: list[dict[str, Any]] = []
        if speed_entries:
            fastest = min(speed for speed, _ in speed_entries)
            awards.extend(
                {"name": "Speed Demon", "player_id": player_id}
                for speed, player_id in speed_entries
                if speed == fastest
            )
        for player_id, player_stats in stats.items():
            player_stats["average_solve_speed_sec"] = (
                round(sum(player_stats["solve_speeds_sec"]) / len(player_stats["solve_speeds_sec"]), 1)
                if player_stats["solve_speeds_sec"]
                else None
            )
        max_solves = max((item["solves"] for item in stats.values()), default=0)
        max_wrong = max((item["wrong_answers"] for item in stats.values()), default=0)
        if max_solves:
            awards.extend(
                {"name": "Workhorse", "player_id": player_id}
                for player_id, item in stats.items()
                if item["solves"] == max_solves
            )
        if max_wrong >= 5:
            awards.extend(
                {"name": "Brute Forcer", "player_id": player_id}
                for player_id, item in stats.items()
                if item["wrong_answers"] == max_wrong
            )
        max_hints = max((team.hint_penalty_sec for team in state.teams.values()), default=0)
        if max_hints:
            awards.extend(
                {"name": "Hint Hoarder", "team_id": team.team_id}
                for team in state.teams.values()
                if team.hint_penalty_sec == max_hints
            )
        finished_teams = [
            team for team in state.teams.values() if team.finished_at is not None
        ]
        for team in finished_teams:
            meta_id = next(
                item["id"]
                for item in self._room_for(game)["puzzles"]
                if item["type"] == "meta"
            )
            clutch_solvers = [
                event["player_id"]
                for event in state.events
                if event["type"] == "solve"
                and event["team_id"] == team.team_id
                and event["puzzle_id"] == meta_id
            ]
            awards.extend(
                {"name": "Clutch", "player_id": player_id}
                for player_id in clutch_solvers
            )
        for award in awards:
            player_id = award.get("player_id")
            if player_id in stats:
                stats[player_id]["awards"].append(award["name"])
        return {
            "standings": standings,
            "race": race,
            "awards": awards,
            "player_stats": list(stats.values()),
        }

    def _active_context(
        self,
        game: Game,
        player_id: str,
        *,
        now: float | None = None,
    ) -> tuple[EscapeGameState, dict[str, Any], TeamProgress, float]:
        state = self._state(game)
        room = self._room_for(game)
        self._sync_members(game, state)
        team = self._team_for_player(state, player_id)
        current_time = time.monotonic() if now is None else now
        if state.ended_at is not None:
            raise EscapeEngineError("game_over")
        if state.paused_at is not None:
            raise EscapeEngineError("game_paused")
        if self._elapsed(state, current_time) >= state.time_limit_sec:
            self._end(state, current_time, "time_up")
            raise EscapeEngineError("game_over")
        if team.finished_at is not None:
            raise EscapeEngineError("team_finished")
        return state, room, team, current_time

    def _room_for(self, game: Game) -> dict[str, Any]:
        room = self.rooms.get(game.room_id or "")
        if room is None:
            raise EscapeEngineError("room_not_found")
        return room

    def _state(self, game: Game) -> EscapeGameState:
        state = self.games.get(game.game_id)
        if state is None:
            raise EscapeEngineError("game_not_started")
        return state

    @staticmethod
    def _team_for_player(state: EscapeGameState, player_id: str) -> TeamProgress:
        for team in state.teams.values():
            if player_id in team.members:
                return team
        raise EscapeEngineError("player_not_on_team")

    @staticmethod
    def _unlocked_ids(room: dict[str, Any], team: TeamProgress) -> set[str]:
        return {
            puzzle["id"]
            for puzzle in room["puzzles"]
            if set(puzzle["requires"]).issubset(team.solved)
        }

    def _public_puzzle(
        self,
        puzzle: dict[str, Any],
        team: TeamProgress,
        player_id: str,
        room: dict[str, Any],
    ) -> dict[str, Any]:
        fields = (
            "id",
            "title",
            "type",
            "prompt",
            "image",
            "overlay_text",
            "prestory",
            "solve_text",
            "format",
            "length",
            "options",
            "items",
            "left",
            "right",
            "method",
            "shift",
            "fragments",
        )
        public = {key: puzzle[key] for key in fields if key in puzzle}
        public.pop("solve_text", None)
        public["hints_used"] = team.hints_used.get(puzzle["id"], 0)
        public["revealed_hints"] = puzzle["hints"][: public["hints_used"]]
        if puzzle["type"] == "meta":
            public["collected_fragments"] = [
                {"title": candidate["title"], "gives": candidate["gives"]}
                for candidate in room["puzzles"]
                if candidate["id"] in team.solved and "gives" in candidate
            ]
        if puzzle["type"] == "cipher":
            public["encoded_text"] = encode_cipher(
                puzzle["plaintext"], puzzle["method"], puzzle.get("shift", 0)
            )
            public.pop("shift", None)
        if puzzle["type"] == "split_clue":
            fragments = puzzle["fragments"]
            player_index = sorted(team.members).index(player_id)
            public["fragment"] = fragments[player_index % len(fragments)]
            public.pop("fragments", None)
        if puzzle["type"] == "ordering":
            public["items"] = list(puzzle["items"])
            SystemRandom().shuffle(public["items"])
        if puzzle["type"] == "matching":
            public["left"] = list(puzzle["left"])
            public["right"] = list(puzzle["right"])
            while public["right"] == puzzle["right"]:
                SystemRandom().shuffle(public["right"])
        return public

    @staticmethod
    def _record(
        state: EscapeGameState,
        event_type: str,
        timestamp: float,
        **details: Any,
    ) -> None:
        state.events.append(
            {"type": event_type, "timestamp": timestamp, **details}
        )

    def _sync_members(self, game: Game, state: EscapeGameState) -> None:
        lobby = self.lobbies.states.get(game.game_id)
        if lobby is None:
            return
        for team_id, progress in state.teams.items():
            lobby_team = lobby.teams.get(team_id)
            if lobby_team is not None:
                progress.name = lobby_team.name
            progress.members = {
                player.player_id
                for player in lobby.players.values()
                if player.team_id == team_id
            }

    @staticmethod
    def _elapsed(state: EscapeGameState, now: float) -> float:
        if state.paused_at is not None:
            return state.elapsed_before_pause
        end = state.ended_at if state.ended_at is not None else now
        return max(0, min(state.time_limit_sec, end - state.started_at))

    def _team_elapsed(
        self, state: EscapeGameState, team: TeamProgress, now: float
    ) -> float:
        if team.finished_at is not None:
            return max(0, team.finished_at - state.started_at)
        return self._elapsed(state, now)

    def _end(self, state: EscapeGameState, now: float, reason: str) -> None:
        if state.ended_at is None:
            if state.paused_at is not None:
                pause_duration = now - state.paused_at
                state.started_at += pause_duration
                for team in state.teams.values():
                    if team.finished_at is not None:
                        team.finished_at += pause_duration
                state.paused_at = None
            state.ended_at = now
            state.end_reason = reason
            self._record(state, "end", now, reason=reason)
