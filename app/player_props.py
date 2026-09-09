"""
Player-level projections: RB1/WR1/WR2/TE1 per team, matched against that
week's specific opponent's defense-vs-position performance.

The "who is this team's current RB1/WR1/WR2/TE1" question is answered by
app/current_depth_charts.py -- a manually researched, individually
verified snapshot (RotoWire + LeagueStation depth charts, cross-checked
against real 2025 stats to classify each player as a rookie, a team
change, or a returning starter). This replaced an earlier automated
"most-used player last season" approach, which the manual research
confirmed would have been meaningfully wrong in real cases -- e.g. it
would have shown Kenneth Walker III as Seattle's RB1 using his 2025 Seahawks
stats, when he actually signed with Kansas City this offseason, and
Seattle's real current RB1 (Jadarian Price) is a rookie with no stats to
show at all.

Touchdown volume specifically is one of the least stable, highest-
variance stats in football even for a heavily-used player in a good
matchup -- see the "favorable red zone" scoring function below for how
that's handled honestly (a qualitative signal, not a false-precision
probability).
"""
from __future__ import annotations

import re

import pandas as pd

from app.current_depth_charts import DEPTH_CHART

STATS_PLAYER_WEEK_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.csv"


def fetch_player_stats_week(season: int) -> pd.DataFrame:
    import requests
    import io
    resp = requests.get(STATS_PLAYER_WEEK_URL.format(season=season), timeout=60)
    resp.raise_for_status()
    return pd.read_csv(io.BytesIO(resp.content), low_memory=False)


def _normalize_name(name: str) -> str:
    name = str(name).lower()
    name = re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b", "", name)
    name = re.sub(r"[^a-z ]", "", name)
    return " ".join(name.split())


def _player_season_line(stats: pd.DataFrame, player_name: str, position: str) -> dict | None:
    """
    Real 2025 per-game stats for a named player, regardless of which team
    they were on that season -- used for players who changed teams in the
    offseason. Returns None if the player has no 2025 stats at all (a
    rookie or otherwise unproven at the NFL level).
    """
    stats = stats.dropna(subset=["player_display_name"])
    norm_target = _normalize_name(player_name)
    matches = stats[stats["player_display_name"].apply(_normalize_name) == norm_target]
    matches = matches[matches["position"] == position]
    if matches.empty:
        return None

    prior_team = sorted(matches["team"].unique())[-1]  # most recent team on file for that player
    games = matches["week"].nunique()
    row = {
        "player_display_name": matches["player_display_name"].iloc[0],
        "games": games,
        "carries": matches["carries"].sum(),
        "rushing_yards": matches["rushing_yards"].sum(),
        "rushing_tds": matches["rushing_tds"].sum(),
        "targets": matches["targets"].sum(),
        "receptions": matches["receptions"].sum(),
        "receiving_yards": matches["receiving_yards"].sum(),
        "receiving_tds": matches["receiving_tds"].sum(),
        "prior_team_2025": prior_team,
    }
    row["carries_per_g"] = round(row["carries"] / games, 1)
    row["rush_yds_per_g"] = round(row["rushing_yards"] / games, 1)
    row["targets_per_g"] = round(row["targets"] / games, 1)
    row["rec_yds_per_g"] = round(row["receiving_yards"] / games, 1)
    row["total_tds"] = row["rushing_tds"] + row["receiving_tds"]
    row["td_per_g"] = round(row["total_tds"] / games, 2)
    return row


def get_skill_players(stats: pd.DataFrame, team: str) -> dict:
    """
    Returns {rb1, wr1, wr2, te1} using the manually researched current
    depth chart (app/current_depth_charts.py), not automated trailing
    usage. Each value is either:
      - None if the team has no chart entry for that slot
      - {"player_display_name": ..., "is_rookie": True} for a rookie/
        unproven player with no 2025 stats to show
      - a full stat dict (with "is_rookie": False and, if applicable,
        "prior_team_2025" set to a DIFFERENT team) otherwise
    """
    chart = DEPTH_CHART.get(team, {})
    out = {}
    for slot, position in [("rb1", "RB"), ("wr1", "WR"), ("wr2", "WR"), ("te1", "TE")]:
        name = chart.get(slot)
        if not name:
            out[slot] = None
            continue
        line = _player_season_line(stats, name, position)
        if line is None:
            out[slot] = {"player_display_name": name, "is_rookie": True}
        else:
            line["is_rookie"] = False
            line["team_changed"] = line["prior_team_2025"] != team
            out[slot] = line
    return out


def compute_position_defense_allowed(stats: pd.DataFrame) -> dict:
    """
    Per-team, per-position, per-game yards/TDs allowed -- and the league
    average for each -- used to matchup-adjust a player's raw per-game
    average into a projection for a *specific* opponent.
    """
    out = {}
    for pos, yard_col, td_col in [
        ("RB", "rushing_yards", "rushing_tds"),
        ("WR", "receiving_yards", "receiving_tds"),
        ("TE", "receiving_yards", "receiving_tds"),
    ]:
        pos_df = stats[stats["position"] == pos]
        allowed = pos_df.groupby("opponent_team").agg(
            yards_allowed=(yard_col, "sum"), tds_allowed=(td_col, "sum"), games=("week", "nunique")
        )
        allowed["yards_per_g"] = allowed.yards_allowed / allowed.games
        allowed["tds_per_g"] = allowed.tds_allowed / allowed.games
        out[pos] = {
            "by_team": allowed[["yards_per_g", "tds_per_g"]].to_dict("index"),
            "league_avg_yards_per_g": allowed["yards_per_g"].mean(),
            "league_avg_tds_per_g": allowed["tds_per_g"].mean(),
        }
    return out


def project_player_vs_opponent(player: dict, position: str, opponent: str, defense_allowed: dict) -> dict | None:
    """
    Matchup-adjusted projection: player's own per-game average, scaled by
    how much more/less yardage this specific opponent allows at that
    position versus the league average. Same "strength of schedule"
    adjustment idea used throughout the team-level model.

    Returns None for a rookie/unproven player -- there's no real 2025
    season average to adjust, and projecting a number from nothing would
    be a fabricated stat dressed up as data.
    """
    if player.get("is_rookie"):
        return None

    pos_data = defense_allowed[position]
    opp_stats = pos_data["by_team"].get(opponent, {"yards_per_g": pos_data["league_avg_yards_per_g"], "tds_per_g": pos_data["league_avg_tds_per_g"]})
    matchup_factor = opp_stats["yards_per_g"] / pos_data["league_avg_yards_per_g"] if pos_data["league_avg_yards_per_g"] else 1.0

    base_yards = player["rush_yds_per_g"] if position == "RB" else player["rec_yds_per_g"]
    projected_yards = round(base_yards * matchup_factor, 1)

    return {
        "projected_yards": projected_yards,
        "matchup_factor": round(matchup_factor, 2),
        "opponent_allows_per_g": round(opp_stats["yards_per_g"], 1),
        "league_avg_allowed_per_g": round(pos_data["league_avg_yards_per_g"], 1),
    }


def redzone_favorability_score(player: dict, position: str, opponent: str, defense_allowed: dict) -> float | None:
    """
    A qualitative "how favorable is this matchup for scoring" signal, NOT
    a touchdown probability -- TDs are too high-variance for that framing
    to be honest. Combines the player's own TD-per-game rate (a proxy for
    their role in their offense's scoring, since there's no literal
    "red zone touches" column in the public data) with how many TDs the
    opponent allows at that position relative to league average.

    Returns None for a rookie/unproven player -- no real TD rate exists
    to build this signal from.
    """
    if player.get("is_rookie"):
        return None
    pos_data = defense_allowed[position]
    opp_tds_per_g = pos_data["by_team"].get(opponent, {}).get("tds_per_g", pos_data["league_avg_tds_per_g"])
    opp_factor = opp_tds_per_g / pos_data["league_avg_tds_per_g"] if pos_data["league_avg_tds_per_g"] else 1.0
    return round(player["td_per_g"] * opp_factor, 3)
