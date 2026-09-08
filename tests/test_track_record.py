import json
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.track_record import _predicted_winner, build_track_record  # noqa: E402


def test_predicted_winner_picks_higher_probability_team():
    game = {"home_team": "KC", "away_team": "DEN", "home_win_prob": 62.0, "away_win_prob": 38.0}
    assert _predicted_winner(game) == "KC"

    game2 = {"home_team": "KC", "away_team": "DEN", "home_win_prob": 38.0, "away_win_prob": 62.0}
    assert _predicted_winner(game2) == "DEN"


def test_predicted_winner_defaults_to_home_on_exact_tie():
    game = {"home_team": "SEA", "away_team": "NE", "home_win_prob": 50.0, "away_win_prob": 50.0}
    assert _predicted_winner(game) == "SEA"


FAKE_GAMES = pd.DataFrame([
    {"season": 2026, "week": 1, "game_type": "REG", "home_team": "JAX", "away_team": "CLE",
     "home_score": 30.0, "away_score": 10.0},  # JAX won
])


def _write_fake_predictions(tmp_path, week, home_wp, away_wp):
    data = {
        "season": 2026, "week": week,
        "games": [{"home_team": "JAX", "away_team": "CLE", "home_win_prob": home_wp, "away_win_prob": away_wp}],
    }
    path = tmp_path / f"predictions_2026_wk{week}.json"
    with open(path, "w") as f:
        json.dump(data, f)
    return path


def test_both_teams_get_identical_credit_for_a_correct_call(tmp_path):
    """
    The exact rule that got corrected once already: if we correctly predict
    JAX beats CLE, BOTH teams get credited as a correct call -- 1-0 each --
    not a real win/loss record for either team.
    """
    _write_fake_predictions(tmp_path, 1, home_wp=90.0, away_wp=10.0)  # correctly favored JAX

    with patch("app.track_record.DATA_DIR", tmp_path), \
         patch("app.data_pipeline.fetch_games", return_value=FAKE_GAMES):
        record = build_track_record(2026)

    assert record["teams"]["JAX"] == {"correct": 1, "total": 1}
    assert record["teams"]["CLE"] == {"correct": 1, "total": 1}, (
        "CLE should ALSO show 1-0 (a correct call), not 0-1 -- "
        "the tally tracks prediction accuracy for games a team played in, "
        "not that team's actual win/loss record."
    )


def test_both_teams_get_identical_credit_for_an_incorrect_call(tmp_path):
    _write_fake_predictions(tmp_path, 1, home_wp=20.0, away_wp=80.0)  # incorrectly favored CLE

    with patch("app.track_record.DATA_DIR", tmp_path), \
         patch("app.data_pipeline.fetch_games", return_value=FAKE_GAMES):
        record = build_track_record(2026)

    assert record["teams"]["JAX"] == {"correct": 0, "total": 1}
    assert record["teams"]["CLE"] == {"correct": 0, "total": 1}, (
        "Both teams should show the SAME 0-1 (an incorrect call) -- "
        "not one team credited and the other not."
    )


def test_ungraded_future_game_is_skipped_not_counted(tmp_path):
    future_games = pd.DataFrame([
        {"season": 2026, "week": 2, "game_type": "REG", "home_team": "KC", "away_team": "DEN",
         "home_score": None, "away_score": None},
    ])
    _write_fake_predictions(tmp_path, 2, home_wp=58.0, away_wp=42.0)

    with patch("app.track_record.DATA_DIR", tmp_path), \
         patch("app.data_pipeline.fetch_games", return_value=future_games):
        record = build_track_record(2026)

    assert record["overall"] == {"correct": 0, "total": 0}
    assert record["weeks"] == {}


def test_overall_and_week_totals_match_sum_of_team_games_divided_by_two(tmp_path):
    """Sanity check: total graded games should be internally consistent."""
    _write_fake_predictions(tmp_path, 1, home_wp=90.0, away_wp=10.0)

    with patch("app.track_record.DATA_DIR", tmp_path), \
         patch("app.data_pipeline.fetch_games", return_value=FAKE_GAMES):
        record = build_track_record(2026)

    assert record["overall"]["total"] == 1
    assert record["weeks"]["1"]["total"] == 1
    total_team_games = sum(t["total"] for t in record["teams"].values())
    assert total_team_games == record["overall"]["total"] * 2
