"""
Hourly QB injury/status watch, using ESPN's free public (but unofficial and
undocumented) sports API. No API key needed, no cost.

Honesty check, up front: this is not an official, documented API. ESPN can
change its response shape without notice. This module is written
defensively (broad try/except per team, multiple fallback paths for where
the data might live in the response) specifically because of that. The
first time this runs for real, check the GitHub Action's log output to
confirm it's actually finding injury data -- see SETUP.md.

Endpoint used: site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{id}
This is the same "site" API that espn.com's own web pages call, which tends
to return richer embedded data (player names, positions, statuses already
filled in) rather than ESPN's more RESTful "core" API, which mostly returns
bare {"$ref": "..."} links that need extra follow-up requests.

ESPN's numeric team IDs are stable and well-documented by the hobbyist
community that reverse-engineered this API, but are NOT guaranteed by ESPN
-- if a team ever seems to return another team's data, that ID is the
first thing to double check.
"""
from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

ESPN_SITE_API = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}"

# Some of ESPN's endpoints reject requests with no User-Agent or an obvious
# script/library default one (observed: a bare `requests` default UA gets a
# 403). A normal browser-like UA is enough to get through.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

# our-abbreviation -> ESPN's numeric team id
ESPN_TEAM_IDS = {
    "ARI": 22, "ATL": 1, "BAL": 33, "BUF": 2, "CAR": 29, "CHI": 3, "CIN": 4,
    "CLE": 5, "DAL": 6, "DEN": 7, "DET": 8, "GB": 9, "HOU": 34, "IND": 11,
    "JAX": 30, "KC": 12, "LAC": 24, "LA": 14, "LV": 13, "MIA": 15, "MIN": 16,
    "NE": 17, "NO": 18, "NYG": 19, "NYJ": 20, "PHI": 21, "PIT": 23, "SF": 25,
    "SEA": 26, "TB": 27, "TEN": 10, "WAS": 28,
}

# Statuses worth flagging -- "Active"/"Probable" etc. are not
CONCERNING_STATUSES = {"out", "doubtful", "questionable", "injured reserve", "ir", "pup"}


def fetch_team_injuries(team_abbr: str, timeout: int = 15) -> list[dict]:
    """
    Returns a list of {name, position, status, detail} for one team's
    current injury report. Returns an empty list (not an error) if ESPN's
    response doesn't match any expected shape, so one team's weird response
    never takes down the whole hourly check.
    """
    espn_id = ESPN_TEAM_IDS.get(team_abbr)
    if espn_id is None:
        logger.warning("No ESPN team id mapped for %s", team_abbr)
        return []

    url = ESPN_SITE_API.format(team_id=espn_id) + "?enable=injuries"
    try:
        resp = requests.get(url, timeout=timeout, headers=_HEADERS)
        resp.raise_for_status()
        data = resp.json()
    except Exception:  # noqa: BLE001 -- network/parsing issues should never crash the hourly job
        logger.exception("Failed to fetch/parse ESPN injuries for %s", team_abbr)
        return []

    # Defensive parsing: try the couple of shapes this endpoint is known to
    # return depending on ESPN's mood. Log clearly if none match so it's
    # obvious from the Action's log output that this needs a look.
    raw_injuries = None
    try:
        raw_injuries = data.get("team", {}).get("injuries")
    except AttributeError:
        pass
    if raw_injuries is None:
        raw_injuries = data.get("injuries")
    if raw_injuries is None:
        logger.warning("ESPN response for %s had no recognizable 'injuries' key -- API shape may have changed", team_abbr)
        return []

    out = []
    for entry in raw_injuries:
        try:
            athlete = entry.get("athlete", {})
            name = athlete.get("displayName") or entry.get("displayName")
            position = (athlete.get("position") or {}).get("abbreviation") or entry.get("position")
            status = entry.get("status") or (entry.get("type") or {}).get("description")
            detail = (entry.get("details") or {}).get("detail") or entry.get("shortComment")
            if name and status:
                out.append({"name": name, "position": position, "status": status, "detail": detail})
        except Exception:  # noqa: BLE001 -- one malformed entry shouldn't drop the rest
            continue
    return out


def get_qb_injury_alert(team_abbr: str, current_starter_name: str) -> str | None:
    """
    Checks whether the team's currently-listed starting QB (from
    app/qb_meta.py) shows up on the injury report with a concerning status.
    Returns a human-readable alert string, or None if nothing's flagged.

    Note the real limit here: this only catches injuries to the QB *already
    listed* in qb_meta.py. If a totally new, unlisted player is suddenly
    starting, this won't know to look for them -- that's still something a
    human needs to update qb_meta.py for occasionally.
    """
    injuries = fetch_team_injuries(team_abbr)
    if not injuries:
        return None

    # Match specifically on the named starter -- NOT "any QB on the
    # report," since a backup QB's injury shouldn't trigger a false alarm
    # about a healthy starter. Matching on last name is a pragmatic choice
    # since ESPN's display names are usually "First Last."
    for inj in injuries:
        name_matches = current_starter_name and inj["name"].split()[-1].lower() == current_starter_name.split()[-1].lower()
        if name_matches and inj["status"].lower() in CONCERNING_STATUSES:
            detail = f" ({inj['detail']})" if inj.get("detail") else ""
            return f"{inj['name']} listed as {inj['status']}{detail} on the latest injury report."
    return None
