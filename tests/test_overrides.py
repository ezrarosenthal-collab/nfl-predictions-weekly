import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.overrides import apply_override  # noqa: E402
from app.model import spread_pick  # noqa: E402


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


def test_spread_pick_computed_after_override_matches_final_displayed_score():
    """
    Regression test for a real, found-in-production bug: the TB @ CIN
    Week 1 card showed "Projected 24.0 - 30.2" (a 6.2-point margin, the
    POST-override score) but "Model spread pick: TB +3.5 (our margin
    +0.6...)" -- a margin from the STALE pre-override score, because
    spread_pick was computed once, before the override ran, and never
    recomputed. The fix: always build spread_pick from whatever the FINAL
    home_score_est/away_score_est are, after any override has already
    been applied -- this test simulates exactly that ordering.
    """
    # Simulates generate_predictions.py's real flow: build the raw
    # prediction, apply the override (which changes the scores to match
    # the CIN 70% / TB 30% context-adjusted win probability), THEN --
    # correctly, per the fix -- compute spread_pick from the result.
    raw_prediction = {
        "home_team": "CIN", "away_team": "TB",
        "home_win_prob": 52.0, "away_win_prob": 48.0,
        "home_score_est": 24.6, "away_score_est": 24.0,  # our_margin would be +0.6 here
    }
    overrides = {
        (2026, 1, "TB", "CIN"): {
            "final_override_home_wp": 70.0,
            "context": "Healthy Burrow argues for a bigger gap than the raw model shows.",
        }
    }
    result = apply_override(dict(raw_prediction), 2026, 1, "TB", "CIN", overrides)

    # This is the fix under test: compute the pick from the FINAL scores,
    # not the ones present before apply_override ran.
    pick = spread_pick(result["home_score_est"], result["away_score_est"], spread_line=3.5)

    final_margin = result["home_score_est"] - result["away_score_est"]
    assert pick["our_margin"] == round(final_margin, 1), (
        "spread_pick's our_margin must match the actual displayed Projected "
        "score margin -- computing it from the pre-override scores (the "
        "original bug) produces a silently wrong, inconsistent-looking card."
    )
    # With the real override applied (CIN pushed up to 70%), CIN should
    # clearly cover a mere 3.5 -- the opposite of the buggy +0.6 reading
    # that incorrectly favored the underdog.
    assert pick["pick_home"] is True
