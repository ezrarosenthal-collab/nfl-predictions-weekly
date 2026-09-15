import json
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.track_record import _grade_spread_pick, _predicted_winner, build_track_record  # noqa: E402
from app.model import spread_pick  # noqa: E402


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


# --- Against-the-spread (ATS) tests -----------------------------------

def test_spread_pick_picks_home_when_our_margin_beats_the_line():
    # Home favored by 3 per the market; we think they win by 10 -- take home.
    pick = spread_pick(home_score_est=24.0, away_score_est=14.0, spread_line=3.0)
    assert pick["pick_home"] is True
    assert pick["our_margin"] == 10.0
    assert pick["edge_points"] == 7.0


def test_spread_pick_picks_away_when_our_margin_is_worse_than_the_line():
    # Home favored by 7 per the market; we only think they win by 2 -- take away (the points).
    pick = spread_pick(home_score_est=20.0, away_score_est=18.0, spread_line=7.0)
    assert pick["pick_home"] is False


def test_spread_pick_none_when_no_market_line():
    assert spread_pick(24.0, 14.0, None) is None


def test_grade_spread_pick_matches_real_2026_week1_sea_ne_push():
    """
    Regression test using the exact real game that surfaced this: SEA
    (home) was favored by 3.0, our model also projected the game as
    essentially a pick'em (our margin ~0.0, so we took NE +3), and the
    real final score was SEA 13, NE 10 -- a margin of exactly 3, a real
    push against this exact line. Verified against real data before this
    was ever shipped, not assumed.
    """
    game = {
        "home_team": "SEA", "away_team": "NE",
        "spread_pick": spread_pick(home_score_est=22.9, away_score_est=22.6, spread_line=3.0),
    }
    result = _grade_spread_pick(game, home_score=13, away_score=10)
    assert result == "push"


def test_grade_spread_pick_win_and_loss():
    # We pick home to cover a 3-point favorite; they win by 10 -- a win for us.
    game_win = {"home_team": "A", "away_team": "B",
                "spread_pick": spread_pick(24.0, 14.0, spread_line=3.0)}
    assert _grade_spread_pick(game_win, home_score=24, away_score=14) == "win"

    # Same pick, but they only win by 1 -- a loss against the spread.
    game_loss = {"home_team": "A", "away_team": "B",
                 "spread_pick": spread_pick(24.0, 14.0, spread_line=3.0)}
    assert _grade_spread_pick(game_loss, home_score=21, away_score=20) == "loss"


def test_grade_spread_pick_none_when_no_pick_saved():
    game = {"home_team": "A", "away_team": "B", "spread_pick": None}
    assert _grade_spread_pick(game, home_score=24, away_score=14) is None


def test_build_track_record_includes_ats_fields(tmp_path):
    games = pd.DataFrame([
        {"season": 2026, "week": 1, "game_type": "REG", "home_team": "SEA", "away_team": "NE",
         "home_score": 13.0, "away_score": 10.0},
    ])
    data = {
        "season": 2026, "week": 1,
        "games": [{
            "home_team": "SEA", "away_team": "NE",
            "home_win_prob": 50.0, "away_win_prob": 50.0,
            "spread_pick": spread_pick(22.9, 22.6, spread_line=3.0),
        }],
    }
    path = tmp_path / "predictions_2026_wk1.json"
    with open(path, "w") as f:
        json.dump(data, f)

    with patch("app.track_record.DATA_DIR", tmp_path), \
         patch("app.data_pipeline.fetch_games", return_value=games):
        record = build_track_record(2026)

    assert record["ats_overall"] == {"wins": 0, "losses": 0, "pushes": 1}
    assert record["ats_weeks"]["1"] == {"wins": 0, "losses": 0, "pushes": 1}


def test_load_all_predictions_skips_empty_file_instead_of_crashing(tmp_path):
    """
    Regression test for the exact real failure: an auto-generated
    predictions file left empty mid-recovery from a git collision should
    be skipped, not crash the whole grading run.
    """
    good_path = tmp_path / "predictions_2026_wk1.json"
    with open(good_path, "w") as f:
        json.dump({"season": 2026, "week": 1, "games": []}, f)

    empty_path = tmp_path / "predictions_2026_wk2.json"
    empty_path.write_text("")  # exactly what "select all, delete" leaves behind

    with patch("app.track_record.DATA_DIR", tmp_path):
        from app.track_record import _load_all_predictions
        result = _load_all_predictions(2026)

    assert 1 in result
    assert 2 not in result  # skipped, not crashed


def test_load_all_predictions_skips_corrupted_file_instead_of_crashing(tmp_path):
    good_path = tmp_path / "predictions_2026_wk1.json"
    with open(good_path, "w") as f:
        json.dump({"season": 2026, "week": 1, "games": []}, f)

    corrupted_path = tmp_path / "predictions_2026_wk2.json"
    corrupted_path.write_text('{"season": 2026, <<<<<<< HEAD\n"week": 2}')

    with patch("app.track_record.DATA_DIR", tmp_path):
        from app.track_record import _load_all_predictions
        result = _load_all_predictions(2026)

    assert 1 in result
    assert 2 not in result
