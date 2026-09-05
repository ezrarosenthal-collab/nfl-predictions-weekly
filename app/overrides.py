"""
The overrides layer.

This exists because of the single biggest finding from the prototype phase:
roughly half of a real Week 1 slate has a pure-stats prediction that's wrong
for a reason a human would catch immediately -- a new starting QB, a key
trade, a starter who missed significant time to injury the previous season.
A trailing-stats model has zero visibility into any of that.

Rather than pretend the pure model is the final answer, every prediction
passes through this layer, which can:
  1. Attach a human-readable `context` string explaining what the trailing
     stats can't see (shown in the UI regardless of whether it changes the
     number).
  2. Optionally set `final_override_home_wp`, which the frontend/generator
     uses INSTEAD OF the raw model number when present.

`data/overrides.json` is the source of truth and is meant to be hand-edited
weekly. This module just loads and applies it.

TODO (automation path): a lot of this could be semi-automated by pulling
ESPN's or the NFL's injury API for "OUT"/"IR" designations on starting QBs
week over week, and auto-flagging (not auto-overriding) any game where a
team's Week 1 starter differs from whoever took the most offensive snaps in
the trailing dataset. That would catch the Kyler Murray / Jayden Daniels /
Patrick Mahomes / Joe Burrow class of cases automatically and surface them
for human review instead of requiring someone to already know to look.
"""
from __future__ import annotations

import json
from pathlib import Path

from config import GAME_MARGIN_SIGMA, MAX_WIN_PROB, MIN_WIN_PROB

DEFAULT_OVERRIDES_PATH = Path(__file__).resolve().parent.parent / "data" / "overrides.json"


def load_overrides(path: Path = DEFAULT_OVERRIDES_PATH) -> dict:
    """
    Returns {(season, week, away, home): override_dict}. Missing file is
    not an error -- it just means no games have manual context yet.
    """
    if not path.exists():
        return {}
    with open(path) as f:
        raw = json.load(f)

    out = {}
    for entry in raw.get("games", []):
        key = (entry["season"], entry["week"], entry["away"], entry["home"])
        out[key] = entry
    return out


def apply_override(prediction: dict, season: int, week: int, away: str, home: str, overrides: dict) -> dict:
    """
    Given a raw model prediction dict (as built by generate_predictions.py),
    attach any matching override's context and, if present, replace the win
    probabilities with the human-adjusted final call. The raw model number
    is always preserved as `raw_model_home_wp` / `raw_model_away_wp` so nobody
    loses the ability to see what the pure stats said.
    """
    key = (season, week, away, home)
    ov = overrides.get(key)

    prediction["raw_model_home_wp"] = prediction["home_win_prob"]
    prediction["raw_model_away_wp"] = prediction["away_win_prob"]
    prediction["context"] = None
    prediction["bet"] = None

    if ov:
        prediction["context"] = ov.get("context")
        if ov.get("final_override_home_wp") is not None:
            # Same regulation as the model itself: even a manually-researched
            # override (a team that just cut its starting QB, etc.) still
            # can't claim more certainty than "any given Sunday" allows.
            home_wp = max(MIN_WIN_PROB, min(MAX_WIN_PROB, float(ov["final_override_home_wp"])))
            prediction["home_win_prob"] = home_wp
            prediction["away_win_prob"] = round(100 - home_wp, 1)

            # Critical: the score projection must be recomputed too, or an
            # override can reintroduce the exact "higher win% but lower
            # score" contradiction the raw model was fixed to avoid. Keep
            # the total points from the original model estimate, but
            # re-split it using the margin implied by the *overridden* win
            # probability -- using the same real, fitted margin/probability
            # relationship as the model itself (see config.GAME_MARGIN_SIGMA),
            # not an arbitrary conversion constant.
            from statistics import NormalDist
            projected_total = prediction["home_score_est"] + prediction["away_score_est"]
            implied_margin = NormalDist().inv_cdf(home_wp / 100) * GAME_MARGIN_SIGMA
            prediction["home_score_est"] = round(projected_total / 2 + implied_margin / 2, 1)
            prediction["away_score_est"] = round(projected_total / 2 - implied_margin / 2, 1)
        if ov.get("bet"):
            prediction["bet"] = ov["bet"]

    return prediction
