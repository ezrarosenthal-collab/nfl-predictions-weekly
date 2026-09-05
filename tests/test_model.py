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


def test_win_probability_and_score_can_never_contradict_each_other():
    """
    Regression test for a real bug: the win probability model and the
    score-projection model used to be computed independently, so a team
    could show a HIGHER win probability while being projected to score
    FEWER points than its opponent -- which makes no sense and was caught
    by a user looking at DAL @ NYG (NYG 52% to win, but Dallas somehow
    projected to outscore them). Both numbers are now derived from the
    same predicted_margin, so they can no longer disagree.
    """
    # Construct two teams where the win-probability drivers (turnover
    # margin, ball security) favor AWAY, but raw scoring average alone
    # would favor HOME -- exactly the shape of the bug that was found.
    home = _dummy_team(team="HOME", ppg=27.0, papg=24.0, point_diff_per_g=3.0,
                        epa_margin=0.02, turnover_margin=-5, int_rate=0.035)
    away = _dummy_team(team="AWAY", ppg=24.0, papg=25.0, point_diff_per_g=-1.0,
                        epa_margin=0.03, turnover_margin=6, int_rate=0.010)
    pred = predict_game(home, away, LEAGUE, league_avg_ppg=22.9, neutral_site=False)

    if pred.home_win_prob > pred.away_win_prob:
        assert pred.home_score_est >= pred.away_score_est, (
            f"HOME has higher win prob ({pred.home_win_prob}%) but a lower "
            f"projected score ({pred.home_score_est} vs {pred.away_score_est}) -- "
            f"this is the exact contradiction that must never happen."
        )
    else:
        assert pred.away_score_est >= pred.home_score_est, (
            f"AWAY has higher win prob ({pred.away_win_prob}%) but a lower "
            f"projected score ({pred.away_score_est} vs {pred.home_score_est}) -- "
            f"this is the exact contradiction that must never happen."
        )


def test_margin_calibration_matches_real_market_behavior():
    """
    The unified margin model's constants were fit against 1,359 real games
    (2021-2025). This locks in the sanity check that confirmed the fit is
    right: a real predicted margin of +3 points should imply roughly a 60%
    win probability -- matching how an actual -3 favorite prices in real
    sportsbook markets -- not some arbitrary number.
    """
    from app.model import normal_cdf
    from config import GAME_MARGIN_SIGMA

    wp_at_plus3 = normal_cdf(3 / GAME_MARGIN_SIGMA) * 100
    wp_at_plus7 = normal_cdf(7 / GAME_MARGIN_SIGMA) * 100
    wp_at_plus10 = normal_cdf(10 / GAME_MARGIN_SIGMA) * 100

    assert 57 < wp_at_plus3 < 63, f"a +3 margin should be ~60% (real-market-like), got {wp_at_plus3:.1f}%"
    assert 69 < wp_at_plus7 < 75, f"a +7 margin should be ~72% (real-market-like), got {wp_at_plus7:.1f}%"
    assert 77 < wp_at_plus10 < 83, f"a +10 margin should be ~80% (real-market-like), got {wp_at_plus10:.1f}%"
