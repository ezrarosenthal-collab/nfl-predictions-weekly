"""
Market line handling.

nflverse's games.csv already carries spread_line / home_moneyline /
away_moneyline / total_line for every scheduled game (it mirrors a
consensus sportsbook line), which is what the prototype used. That's the
default source below since it needs no API key and is already wired into
data_pipeline.fetch_games().

If you want a live, more frequently-updated line instead, drop in a call to
a real odds API (e.g. the-odds-api.com -- free tier available) inside
fetch_live_odds() and prefer it when ODDS_API_KEY is set. The interface
(a dict of spread/moneyline/total per game) stays the same either way, so
nothing downstream needs to change.
"""
from __future__ import annotations

import os

import pandas as pd

ODDS_API_KEY = os.environ.get("ODDS_API_KEY")  # optional, unset by default


def fair_odds_from_moneyline(ml_home: float, ml_away: float) -> tuple[float, float]:
    """
    Convert two American moneylines into vig-free ("fair") win probabilities
    that sum to 100%.
    """
    implied_home = -ml_home / (-ml_home + 100) if ml_home < 0 else 100 / (ml_home + 100)
    implied_away = 100 / (ml_away + 100) if ml_away > 0 else -ml_away / (-ml_away + 100)
    overround = implied_home + implied_away
    return (implied_home / overround * 100, implied_away / overround * 100)


def get_game_odds(game_row: pd.Series) -> dict:
    """
    Pull the odds fields already present on a nflverse games.csv row into a
    clean dict. Returns None values gracefully if a line hasn't posted yet
    (common for games far in the future).
    """
    ml_home = game_row.get("home_moneyline")
    ml_away = game_row.get("away_moneyline")
    fair_home = fair_away = None
    if pd.notna(ml_home) and pd.notna(ml_away):
        fair_home, fair_away = fair_odds_from_moneyline(float(ml_home), float(ml_away))

    return {
        "spread_line": game_row.get("spread_line"),
        "total_line": game_row.get("total_line"),
        "moneyline_home": ml_home,
        "moneyline_away": ml_away,
        "fair_odds_home": round(fair_home, 1) if fair_home is not None else None,
        "fair_odds_away": round(fair_away, 1) if fair_away is not None else None,
    }


def fetch_live_odds(season: int, week: int) -> dict:
    """
    Placeholder for a live odds-API integration. Wire this up to
    the-odds-api.com (or your preferred provider) if you want lines that
    update more often than nflverse's daily refresh.

    Expected return shape: {game_id: {spread_line, total_line,
    moneyline_home, moneyline_away}} -- same keys as get_game_odds() so
    generate_predictions.py doesn't need to care which source is active.
    """
    if not ODDS_API_KEY:
        raise RuntimeError(
            "ODDS_API_KEY not set -- falling back to nflverse's built-in "
            "lines via get_game_odds(). Set ODDS_API_KEY and implement this "
            "function if you want a live, more frequently-updated source."
        )
    raise NotImplementedError("Wire up your odds provider of choice here.")
