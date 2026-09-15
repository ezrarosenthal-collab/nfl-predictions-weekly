"""
Grades saved predictions against real final scores and maintains a running
track record: overall record, record by week, and a per-team accuracy
tally.

Team accuracy tally, defined precisely (this matters, got corrected once
already): for a given graded game, BOTH teams involved get the same
correct/incorrect credit -- it's "was our prediction for a game this team
played in right," not "did this team win." If we correctly predicted
Jaguars over Browns, that's a correct call for BOTH the Jaguars AND the
Browns, 1-0 each, not 1-0 for Jacksonville and 0-1 for Cleveland.

This only grades games that (a) have a saved prediction file for that
week, since we need to know what we predicted, and (b) have a final score
in the schedule data. It's safe to run repeatedly -- it always rebuilds
the full record from scratch off whatever prediction files and final
scores currently exist, rather than trying to increment a running total,
which avoids any risk of double-counting a game that gets checked more
than once (which will happen constantly, by design, given how many times
a day this runs).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app import data_pipeline

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _predicted_winner(game: dict) -> str:
    """
    Whichever team had the higher win probability in the saved prediction.
    On an exact 50/50 (a real, intended outcome of the model's regulation
    cap -- see config.py), this defaults to the home team. That's a
    simplification worth knowing about: a true coin-flip game doesn't have
    a meaningful "pick" to grade, but every game needs one answer to keep
    the record-keeping simple.
    """
    return game["home_team"] if game["home_win_prob"] >= game["away_win_prob"] else game["away_team"]


def _grade_spread_pick(game: dict, home_score: float, away_score: float) -> str | None:
    """
    Grades our saved spread_pick (app/model.py's spread_pick(), computed
    at prediction time from the same margin the win probability comes
    from) against the real final score.

    spread_line convention (verified against real odds data): POSITIVE
    means the home team is favored by that many points. Returns "win",
    "loss", "push" (exact tie against the line -- excluded from the
    record, standard sports-betting convention), or None if there was no
    saved spread pick for this game (no market line was available at
    prediction time).
    """
    pick = game.get("spread_pick")
    if not pick:
        return None
    spread_line = pick["market_line"]
    actual_margin = home_score - away_score

    if actual_margin > spread_line:
        covered = "home"
    elif actual_margin < spread_line:
        covered = "away"
    else:
        return "push"

    our_side = "home" if pick["pick_home"] else "away"
    return "win" if our_side == covered else "loss"


def _load_all_predictions(season: int) -> dict[int, dict]:
    """{week_number: predictions_dict} for every predictions file on disk for this season."""
    out = {}
    for path in sorted(DATA_DIR.glob(f"predictions_{season}_wk*.json")):
        with open(path) as f:
            data = json.load(f)
        out[data["week"]] = data
    return out


def build_track_record(season: int) -> dict:
    games_df = data_pipeline.fetch_games()
    completed = games_df[
        (games_df["season"] == season)
        & (games_df["game_type"] == "REG")
        & games_df["home_score"].notna()
        & games_df["away_score"].notna()
    ]
    # (home_team, away_team, week) -> (actual winner, home_score, away_score)
    actual_results = {}
    for _, g in completed.iterrows():
        winner = g["home_team"] if g["home_score"] > g["away_score"] else g["away_team"]
        actual_results[(g["week"], g["home_team"], g["away_team"])] = (winner, g["home_score"], g["away_score"])

    predictions_by_week = _load_all_predictions(season)

    overall = {"correct": 0, "total": 0}
    weeks: dict[str, dict] = {}
    teams: dict[str, dict] = {}
    ats_overall = {"wins": 0, "losses": 0, "pushes": 0}
    ats_weeks: dict[str, dict] = {}

    for week, pred_data in predictions_by_week.items():
        week_record = {"correct": 0, "total": 0}
        ats_week_record = {"wins": 0, "losses": 0, "pushes": 0}

        for g in pred_data["games"]:
            key = (week, g["home_team"], g["away_team"])
            if key not in actual_results:
                continue  # game hasn't been played yet -- nothing to grade

            actual, home_score, away_score = actual_results[key]
            predicted = _predicted_winner(g)
            is_correct = predicted == actual

            overall["total"] += 1
            overall["correct"] += int(is_correct)
            week_record["total"] += 1
            week_record["correct"] += int(is_correct)

            for team in (g["home_team"], g["away_team"]):
                teams.setdefault(team, {"correct": 0, "total": 0})
                teams[team]["total"] += 1
                teams[team]["correct"] += int(is_correct)

            ats_result = _grade_spread_pick(g, home_score, away_score)
            if ats_result == "win":
                ats_overall["wins"] += 1
                ats_week_record["wins"] += 1
            elif ats_result == "loss":
                ats_overall["losses"] += 1
                ats_week_record["losses"] += 1
            elif ats_result == "push":
                ats_overall["pushes"] += 1
                ats_week_record["pushes"] += 1
            # None (no market line available) -> not counted anywhere, not even as a push

        if week_record["total"] > 0:
            weeks[str(week)] = week_record
        if sum(ats_week_record.values()) > 0:
            ats_weeks[str(week)] = ats_week_record

    return {
        "season": season,
        "overall": overall,
        "weeks": weeks,
        "teams": teams,
        "ats_overall": ats_overall,
        "ats_weeks": ats_weeks,
    }


def save_track_record(season: int) -> Path:
    record = build_track_record(season)
    out_path = DATA_DIR / f"track_record_{season}.json"
    with open(out_path, "w") as f:
        json.dump(record, f, indent=2)
    return out_path
