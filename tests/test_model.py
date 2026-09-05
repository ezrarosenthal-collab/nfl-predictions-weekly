import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.model import sigmoid, zscore, predict_game


def test_sigmoid_midpoint():
    assert abs(sigmoid(0.0) - 0.5) < 1e-9


def test_sigmoid_bounds():
    assert 0 < sigmoid(-100) < 0.001
    assert 0.999 < sigmoid(100) <= 1


def test_zscore_basic():
    assert zscore(10, mean=10, std=5) == 0
    assert zscore(15, mean=10, std=5) == 1
    assert zscore(5, mean=10, std=5) == -1


def test_zscore_zero_std_safe():
    assert zscore(5, mean=5, std=0) == 0.0


LEAGUE = {
    "point_diff_per_g": {"mean": 0.0, "std": 6.25},
    "epa_margin": {"mean": 0.0, "std": 0.13},
    "turnover_margin": {"mean": 0.0, "std": 8.6},
    "off_explosive_rate": {"mean": 0.126, "std": 0.017},
    "def_explosive_rate": {"mean": 0.126, "std": 0.018},
    "third_down_pct": {"mean": 0.398, "std": 0.046},
    "redzone_td_rate": {"mean": 0.189, "std": 0.027},
    "sack_rate_allowed": {"mean": 0.069, "std": 0.021},
    "int_rate": {"mean": 0.020, "std": 0.007},
    "ypp_margin": {"mean": 0.0, "std": 0.71},
    "cpoe": {"mean": 0.58, "std": 3.38},
    "off_epa_per_play": {"mean": 0.0, "std": 0.08},
    "def_epa_per_play": {"mean": 0.0, "std": 0.08},
}


def _dummy_team(**overrides):
    base = dict(
        team="TST", ppg=22.9, papg=22.9, point_diff_per_g=0.0, epa_margin=0.0,
        turnover_margin=0, off_explosive_rate=0.126, def_explosive_rate=0.126,
        third_down_pct=0.398, redzone_td_rate=0.189, sack_rate_allowed=0.069,
        int_rate=0.020, ypp_margin=0.0, cpoe=0.58, off_epa_per_play=0.0,
        def_epa_per_play=0.0,
    )
    base.update(overrides)
    return base


def test_identical_teams_home_favored_only_by_field_advantage():
    """Two league-average teams: home team should win a modest, not extreme, edge."""
    home = _dummy_team(team="HOME")
    away = _dummy_team(team="AWAY")
    pred = predict_game(home, away, LEAGUE, league_avg_ppg=22.9, neutral_site=False)
    assert 50 < pred.home_win_prob < 60, "home field alone shouldn't be worth more than ~10pts"


def test_neutral_site_smaller_edge_than_home():
    home = _dummy_team(team="HOME")
    away = _dummy_team(team="AWAY")
    home_game = predict_game(home, away, LEAGUE, league_avg_ppg=22.9, neutral_site=False)
    neutral_game = predict_game(home, away, LEAGUE, league_avg_ppg=22.9, neutral_site=True)
    assert neutral_game.home_win_prob < home_game.home_win_prob


def test_much_better_team_favored_but_not_absurdly_confident():
    """
    Regression test for the calibration bug found in the prototype: a big
    mismatch should NOT produce a >90% single-game win probability.
    """
    strong = _dummy_team(team="STRONG", point_diff_per_g=10, epa_margin=0.2,
                          turnover_margin=10, ypp_margin=1.2, cpoe=5)
    weak = _dummy_team(team="WEAK", point_diff_per_g=-8, epa_margin=-0.15,
                        turnover_margin=-8, ypp_margin=-0.8, cpoe=-3)
    pred = predict_game(strong, weak, LEAGUE, league_avg_ppg=22.9, neutral_site=False)
    assert pred.home_win_prob <= 90, "single-game win prob should never exceed the regulated cap"
    assert pred.home_win_prob > 65, "but a real mismatch should still be clearly favored"


def test_even_extreme_mismatch_respects_the_regulated_cap():
    """
    'Any given Sunday' regulation: no matter how lopsided the inputs are,
    the model must never claim more than MAX_WIN_PROB / less than
    MIN_WIN_PROB confidence in a single game.
    """
    from config import MAX_WIN_PROB, MIN_WIN_PROB

    extreme_strong = _dummy_team(team="STRONG", point_diff_per_g=25, epa_margin=0.5,
                                  turnover_margin=25, ypp_margin=3.0, cpoe=15,
                                  redzone_td_rate=0.4, third_down_pct=0.6)
    extreme_weak = _dummy_team(team="WEAK", point_diff_per_g=-25, epa_margin=-0.5,
                                turnover_margin=-25, ypp_margin=-3.0, cpoe=-15,
                                redzone_td_rate=0.05, third_down_pct=0.15)
    pred = predict_game(extreme_strong, extreme_weak, LEAGUE, league_avg_ppg=22.9, neutral_site=False)
    assert pred.home_win_prob == MAX_WIN_PROB, "an absurd mismatch should hit the cap exactly, not exceed it"
    assert pred.away_win_prob == 100 - MAX_WIN_PROB == MIN_WIN_PROB


def test_feature_breakdown_sums_reasonably():
    home = _dummy_team(team="HOME", point_diff_per_g=5)
    away = _dummy_team(team="AWAY", point_diff_per_g=-5)
    pred = predict_game(home, away, LEAGUE, league_avg_ppg=22.9)
    strength_row = next(f for f in pred.feature_breakdown if f["key"] == "strength")
    assert strength_row["favors"] == "home"
