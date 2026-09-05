"""
Automated QB-change detection.

This is the honest, free alternative to what a human did manually for
Week 1 2026 (reading articles to learn Kyler Murray got cut, Jayden Daniels
got hurt, etc.). It can't read news, but it doesn't need to: whoever took
the most pass attempts for a team in its most recent games *is* the
starting QB, as a matter of fact, not opinion. So instead of asking "did
the news change," this asks "did the answer to 'who's throwing the ball
for this team' change" -- which is the actual signal that made every
Week 1 override necessary in the first place.

What this catches automatically, for free, every week:
  - A new starter takes over from injury (Mahomes -> backup -> Mahomes again)
  - A benching or QB competition resolves differently than expected
  - A trade/free-agency signing puts a new name under center

What this does NOT catch (the real limit, worth being upfront about):
  - A trade that changes a team's *supporting cast* without changing the QB
    (Myles Garrett to the Rams, A.J. Brown to the Patriots) -- the play-by-
    play won't show that until the new player actually appears in the data,
    which for a Week 1 preview is by definition too late.
  - A coaching change's scheme impact, before it's shown up in any games.
  - An injury that hasn't happened yet (obviously).
  These require either a human doing what we did for Week 1, or a paid
  LLM-in-the-loop step that reads news weekly (real but non-zero ongoing
  cost, unlike everything else in this pipeline).
"""
from __future__ import annotations

import pandas as pd


def get_weekly_qb_starters(pbp: pd.DataFrame, season: int, week: int) -> dict[str, str]:
    """
    Returns {team: qb_player_id} for whoever had the most pass attempts for
    that team in the given week. Requires a 'passer_player_id' or similar
    column -- nflverse's play_by_play includes 'passer_player_name'.
    """
    week_pbp = pbp[(pbp["season"] == season) & (pbp["week"] == week) & (pbp["pass_attempt"] == 1)]
    if "passer_player_name" not in week_pbp.columns:
        return {}
    counts = week_pbp.groupby(["posteam", "passer_player_name"]).size().reset_index(name="attempts")
    starters = counts.loc[counts.groupby("posteam")["attempts"].idxmax()]
    return dict(zip(starters["posteam"], starters["passer_player_name"]))


def detect_starter_changes(
    pbp: pd.DataFrame, season: int, upcoming_week: int, lookback_weeks: int = 3
) -> dict[str, dict]:
    """
    For every team, compares "who started at QB most recently" against
    "who started earlier this season" (or last season, for Week 1). Flags
    a team when those differ -- that's a real, free, automatic signal that
    something changed and the trailing-season stats might be stale for
    that team's passing game, without needing to read a single article.

    Returns {team: {"recent_starter": ..., "earlier_starter": ..., "changed": bool}}
    """
    if upcoming_week <= 1:
        return {}  # no in-season signal exists yet; Week 1 needs the manual layer

    recent_week = upcoming_week - 1
    earliest_week = max(1, recent_week - lookback_weeks)

    recent = get_weekly_qb_starters(pbp, season, recent_week)
    earlier_frames = [
        get_weekly_qb_starters(pbp, season, w) for w in range(earliest_week, recent_week)
    ]

    out = {}
    for team, recent_qb in recent.items():
        earlier_qbs = {frame.get(team) for frame in earlier_frames if frame.get(team)}
        earlier_qbs.discard(recent_qb)
        if earlier_qbs:
            out[team] = {
                "recent_starter": recent_qb,
                "earlier_starters": sorted(earlier_qbs),
                "changed": True,
            }
    return out
