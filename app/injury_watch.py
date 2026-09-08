"""
Hourly QB injury/status watch.

## History worth keeping: the first version of this used ESPN's free,
unofficial public API. It was written defensively and tested against a
simulated response before ever running for real -- and the very first live
run (on GitHub Actions' actual servers, which have full internet access)
came back with a 403 Forbidden on every single request. That's not a bug
in the code; ESPN's anti-bot protection blocks well-known automation IP
ranges (GitHub Actions, AWS, etc.) outright, regardless of headers. That's
a wall, not something to route around by trying harder with the same tool.

## What this uses instead: nflverse's official injury reports.
Same trusted open-data project already powering the rest of this backend
(play-by-play, schedules), sourced from the NFL's own weekly injury report
data, delivered the same reliable way (a GitHub release download) as
everything else in this project. Since app/data_pipeline.py already proved
GitHub-hosted downloads work fine from GitHub Actions, this has none of the
blocking risk the ESPN attempt had.

The real, remaining limits (stated plainly, not smoothed over):
- Update cadence: nflverse's injuries file is refreshed as the league's own
  reports come in (typically a few times a week during the season --
  Wednesday/Thursday/Friday practice reports plus the final game-day
  status). Checking hourly costs nothing extra, but don't expect to see a
  brand-new entry appear the instant an injury happens; it will show up
  once the official report reflects it, same as it would on nfl.com.
- This only catches injuries to the QB *already listed* in qb_meta.py. A
  totally new, unlisted starter still needs a manual qb_meta.py update.
"""
from __future__ import annotations

import logging

from app.data_pipeline import fetch_injuries

logger = logging.getLogger(__name__)

# Official NFL injury-report designations worth flagging. ("Doubtful" and
# "IR" are included for completeness even though nflverse's report_status
# column has so far only been observed to contain Out/Questionable/Doubtful.)
CONCERNING_STATUSES = {"out", "doubtful", "questionable", "injured reserve", "ir", "pup"}


def get_qb_injury_alert(team: str, current_starter_name: str, season: int, week: int) -> str | None:
    """
    Checks the official injury report for this team/week for the
    currently-listed starting QB (by name, matched on last name -- nflverse
    full_name is "First Last"). Returns a human-readable alert string, or
    None if nothing concerning is listed for that player.
    """
    if not current_starter_name:
        return None

    try:
        injuries = fetch_injuries(season)
    except Exception:  # noqa: BLE001 -- never let a fetch failure crash the hourly job
        logger.exception("Failed to fetch injury report for %s", season)
        return None

    last_name = current_starter_name.split()[-1].lower()
    team_injuries = injuries[
        (injuries["team"] == team)
        & (injuries["week"] == week)
        & (injuries["full_name"].str.lower().str.endswith(last_name))
    ]

    for _, row in team_injuries.iterrows():
        status = row.get("report_status")
        if isinstance(status, str) and status.lower() in CONCERNING_STATUSES:
            detail_parts = [p for p in (row.get("report_primary_injury"), row.get("report_secondary_injury")) if isinstance(p, str)]
            detail = f" ({', '.join(detail_parts)})" if detail_parts else ""
            return f"{row['full_name']} listed as {status}{detail} on this week's official injury report."
    return None
