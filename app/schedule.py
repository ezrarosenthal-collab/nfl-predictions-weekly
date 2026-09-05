"""
Figures out "what week is it" from the real schedule, so the weekly job
never needs a hardcoded --week argument. This is what makes Week 1 -> Week
2 -> Week 3... fully automatic: the cron job just runs "give me the next
unplayed week" every Tuesday and gets the right answer without anyone
updating a config.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from app import data_pipeline


def current_week(season: int, as_of: datetime | None = None) -> int:
    """
    Returns the next week whose games haven't all been played yet as of
    `as_of` (defaults to now). On a Tuesday morning after Monday Night
    Football, every game in the just-finished week has a final score, so
    this naturally rolls over to the next week.
    """
    as_of = as_of or datetime.now(timezone.utc)
    games = data_pipeline.fetch_games()
    reg = games[(games["season"] == season) & (games["game_type"] == "REG")].copy()
    reg["gameday"] = pd.to_datetime(reg["gameday"])

    for week in sorted(reg["week"].unique()):
        week_games = reg[reg["week"] == week]
        all_played = week_games["home_score"].notna().all() and week_games["away_score"].notna().all()
        # A week counts as "in progress or upcoming" once we've reached its
        # first game day, OR once any of its games are missing a final score.
        started = (week_games["gameday"] <= as_of.replace(tzinfo=None)).any()
        if not all_played or not started:
            return int(week)

    return int(reg["week"].max())  # season's over; stay on the last week
