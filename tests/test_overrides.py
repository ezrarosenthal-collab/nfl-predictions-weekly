import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.overrides import apply_override  # noqa: E402


def test_override_recomputes_score_to_match_new_win_prob():
    """
    Regression test: the same win%/score contradiction bug was found to
    reappear whenever a manual override changed the win probability,
    because the score had already been computed using the ORIGINAL
    (pre-override) win probability. Applying an override must also
    recompute the score so the two numbers still agree.
    """
    # A raw model prediction where the home team was originally the
    # underdog (lower win prob, lower score) before any override.
    raw_prediction = {
        "home_team": "IND", "away_team": "BAL",
        "home_win_prob": 35.0, "away_win_prob": 65.0,
        "home_score_est": 20.0, "away_score_est": 24.0,
    }
    overrides = {
        (2026, 1, "BAL", "IND"): {
            "final_override_home_wp": 62.0,  # override FLIPS the favorite to home (IND)
            "context": "test override",
        }
    }
    result = apply_override(dict(raw_prediction), 2026, 1, "BAL", "IND", overrides)

    assert result["home_win_prob"] == 62.0
    assert result["home_win_prob"] > result["away_win_prob"]
    # The critical check: score must now agree with the NEW win prob, not the old one
    assert result["home_score_est"] > result["away_score_est"], (
        "IND now has the higher win probability after the override, so it "
        "must also have the higher projected score -- the override broke "
        "that if this fails."
    )
