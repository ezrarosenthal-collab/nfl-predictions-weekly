"""
Player-level projections: RB1/WR1/WR2/TE1 per team, matched against that
week's specific opponent's defense-vs-position performance.

Honest scope, stated up front:
- "RB1/WR1/WR2/TE1" here means "the player with the most usage at that
  position last season" (carries for RB, targets for WR/TE) -- the same
  data-driven starting point the team model uses for QBs (qb_meta.py), and
  it has the exact same limitation: a trade, injury, or a rookie winning a
  job over the offseason can make this stale, the same way Kyler Murray
  moving to Minnesota made the trailing-stats QB assumption wrong for that
  team. This is NOT continuously re-verified against current news -- it's
  last season's real usage data, which is a reasonable starting point but
  can drift out of date the same way team-level QB assumptions can.
- Touchdown volume specifically is one of the least stable, highest-
  variance stats in football even for a heavily-used player in a good
  matchup -- see the "favorable red zone" scoring function below for how
  that's handled honestly (a qualitative signal, not a false-precision
  probability).
"""
from __future__ import annotations

import pandas as pd

STATS_PLAYER_WEEK_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.csv"


def fetch_player_stats_week(season: int) -> pd.DataFrame:
    import requests
    import io
    resp = requests.get(STATS_PLAYER_WEEK_URL.format(season=season), timeout=60)
    resp.raise_for_status()
    return pd.read_csv(io.BytesIO(resp.content), low_memory=False)


def get_skill_players(stats: pd.DataFrame, team: str) -> dict:
    """
    Returns {rb1, wr1, wr2, te1}, each a dict of that player's season
    per-game usage/production, or None if the team has no qualifying
    player at that position in the data.
    """
    team_stats = stats[stats["team"] == team]

    def top_player(position: str, sort_col: str, n: int = 1) -> list[dict]:
        pos_df = team_stats[team_stats["position"] == position]
        agg = pos_df.groupby("player_display_name").agg(
            games=("week", "nunique"),
            carries=("carries", "sum"), rushing_yards=("rushing_yards", "sum"), rushing_tds=("rushing_tds", "sum"),
            targets=("targets", "sum"), receptions=("receptions", "sum"),
            receiving_yards=("receiving_yards", "sum"), receiving_tds=("receiving_tds", "sum"),
        ).reset_index()
        agg = agg[agg["games"] >= 4]  # filter out one-off/practice-squad noise
        if agg.empty:
            return []
        agg = agg.sort_values(sort_col, ascending=False)
        return agg.head(n).to_dict("records")

    rb = top_player("RB", "carries", 1)
    wr = top_player("WR", "targets", 2)
    te = top_player("TE", "targets", 1)

    def with_per_game(p):
        if not p:
            return None
        g = p["games"]
        p["carries_per_g"] = round(p["carries"] / g, 1)
        p["rush_yds_per_g"] = round(p["rushing_yards"] / g, 1)
        p["targets_per_g"] = round(p["targets"] / g, 1)
        p["rec_yds_per_g"] = round(p["receiving_yards"] / g, 1)
        p["total_tds"] = p["rushing_tds"] + p["receiving_tds"]
        p["td_per_g"] = round(p["total_tds"] / g, 2)
        return p

    return {
        "rb1": with_per_game(rb[0]) if rb else None,
        "wr1": with_per_game(wr[0]) if len(wr) > 0 else None,
        "wr2": with_per_game(wr[1]) if len(wr) > 1 else None,
        "te1": with_per_game(te[0]) if te else None,
    }


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


def project_player_vs_opponent(player: dict, position: str, opponent: str, defense_allowed: dict) -> dict:
    """
    Matchup-adjusted projection: player's own per-game average, scaled by
    how much more/less yardage this specific opponent allows at that
    position versus the league average. Same "strength of schedule"
    adjustment idea used throughout the team-level model.
    """
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


def redzone_favorability_score(player: dict, position: str, opponent: str, defense_allowed: dict) -> float:
    """
    A qualitative "how favorable is this matchup for scoring" signal, NOT
    a touchdown probability -- TDs are too high-variance for that framing
    to be honest. Combines the player's own TD-per-game rate (a proxy for
    their role in their offense's scoring, since there's no literal
    "red zone touches" column in the public data) with how many TDs the
    opponent allows at that position relative to league average.
    """
    pos_data = defense_allowed[position]
    opp_tds_per_g = pos_data["by_team"].get(opponent, {}).get("tds_per_g", pos_data["league_avg_tds_per_g"])
    opp_factor = opp_tds_per_g / pos_data["league_avg_tds_per_g"] if pos_data["league_avg_tds_per_g"] else 1.0
    return round(player["td_per_g"] * opp_factor, 3)
