"""
Pulls raw play-by-play and schedule data from nflverse's public GitHub
releases. This is the same source used to build and validate the model
(235,933 real plays, 2021-2025).

nflverse publishes a new play_by_play_{season}.csv.gz partway through the
season and keeps it updated, so calling fetch_pbp(season=2026) mid-season
returns whatever games have been played so far -- which is exactly what the
weekly pipeline needs for rolling in-season stats.
"""
from __future__ import annotations

import io
import logging
from functools import lru_cache

import pandas as pd
import requests

from config import NFLVERSE_GAMES_URL, NFLVERSE_PBP_URL

logger = logging.getLogger(__name__)

PBP_COLUMNS = [
    "season", "week", "season_type", "posteam", "defteam", "play_type", "epa",
    "success", "yards_gained", "pass", "rush", "sack", "interception",
    "fumble_lost", "third_down_converted", "third_down_failed", "yardline_100",
    "touchdown", "pass_touchdown", "rush_touchdown", "qb_hit", "pass_attempt",
    "complete_pass", "air_yards", "penalty", "drive", "posteam_type", "down",
    "cpoe", "passer_player_name",
]


def _get(url: str, timeout: int = 60) -> bytes:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.content


@lru_cache(maxsize=8)
def fetch_pbp(season: int, season_type: str = "REG") -> pd.DataFrame:
    """
    Download one season's play-by-play. Cached in-process since this file
    doesn't change within a run.
    """
    url = NFLVERSE_PBP_URL.format(season=season)
    logger.info("Fetching play-by-play for %s from %s", season, url)
    raw = _get(url)
    df = pd.read_csv(
        io.BytesIO(raw),
        compression="gzip",
        low_memory=False,
        usecols=lambda c: c in PBP_COLUMNS,
    )
    if season_type:
        df = df[df["season_type"] == season_type]
    return df


@lru_cache(maxsize=1)
def fetch_games() -> pd.DataFrame:
    """
    Download the full historical + current-season schedule, including
    market lines (spread_line, home_moneyline, away_moneyline, total_line)
    where sportsbooks have posted them.
    """
    logger.info("Fetching schedules/games from %s", NFLVERSE_GAMES_URL)
    raw = _get(NFLVERSE_GAMES_URL)
    return pd.read_csv(io.BytesIO(raw), low_memory=False)


def fetch_multi_season_pbp(seasons: list[int]) -> pd.DataFrame:
    """Concatenate several seasons of regular-season play-by-play."""
    frames = [fetch_pbp(s) for s in seasons]
    return pd.concat(frames, ignore_index=True)


def get_week_games(season: int, week: int) -> pd.DataFrame:
    """All games for a given season/week, regular season only."""
    games = fetch_games()
    return games[
        (games["season"] == season)
        & (games["week"] == week)
        & (games["game_type"] == "REG")
    ].copy()
