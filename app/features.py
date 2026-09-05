"""
Turns raw play-by-play into the team-season (or rolling-window) stats the
model consumes. Every function here reproduces, exactly, the aggregation
logic used to build and validate the model against 2021-2025 -- this is not
a simplified re-implementation, it's the same code path.

Two entry points:
  - build_team_stats(pbp, games, through_week=None)
      Full-season (or "through week N" for in-season use) aggregates per
      team. This is what feeds the model for any given prediction.
  - compute_league_norms(team_stats)
      Mean/std per feature across the league, needed to z-score any two
      teams against the field before comparing them.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import EXPLOSIVE_PASS_YARDS, EXPLOSIVE_RUN_YARDS, REDZONE_YARDLINE_100

FEATURE_COLUMNS = [
    "ppg", "papg", "off_epa_per_play", "def_epa_per_play", "epa_margin",
    "point_diff_per_g", "turnover_margin", "off_explosive_rate",
    "def_explosive_rate", "third_down_pct", "redzone_td_rate",
    "sack_rate_allowed", "int_rate", "ypp_off", "ypp_def", "ypp_margin",
    "cpoe",
]


def _scrimmage_plays(pbp: pd.DataFrame) -> pd.DataFrame:
    """Real offensive plays only: pass or run, with a valid EPA value."""
    df = pbp[(pbp["play_type"].isin(["pass", "run"])) & pbp["epa"].notna()].copy()
    df["explosive"] = np.where(
        df["pass"] == 1,
        df["yards_gained"] >= EXPLOSIVE_PASS_YARDS,
        df["yards_gained"] >= EXPLOSIVE_RUN_YARDS,
    )
    return df


def build_team_stats(
    pbp: pd.DataFrame,
    games: pd.DataFrame,
    season: int,
    through_week: int | None = None,
) -> pd.DataFrame:
    """
    Build one row per team with every feature the model needs.

    Parameters
    ----------
    pbp : play-by-play for the relevant season(s) (from data_pipeline.fetch_pbp)
    games : schedule/results (from data_pipeline.fetch_games)
    season : season to aggregate. If you want a *prior*-season baseline for
        a Week 1 prediction (no current-season data exists yet), pass the
        prior season here.
    through_week : if set, only include weeks <= this value (rolling
        in-season stats). If None, use the full season.
    """
    pbp = pbp[pbp["season"] == season]
    if through_week is not None:
        pbp = pbp[pbp["week"] <= through_week]

    scrim = _scrimmage_plays(pbp)

    # --- wins / points, from games (source of truth for scores) ----------
    reg = games[(games["season"] == season) & (games["game_type"] == "REG")]
    if through_week is not None:
        reg = reg[reg["week"] <= through_week]
    reg = reg.dropna(subset=["home_score", "away_score"])

    records = []
    for _, g in reg.iterrows():
        records.append({"team": g["home_team"], "pf": g["home_score"], "pa": g["away_score"]})
        records.append({"team": g["away_team"], "pf": g["away_score"], "pa": g["home_score"]})
    scores = pd.DataFrame(records)
    games_played = scores.groupby("team").size().rename("games")
    pf = scores.groupby("team")["pf"].sum()
    pa = scores.groupby("team")["pa"].sum()

    # --- EPA / success / explosive, offense and defense -------------------
    off = scrim.groupby("posteam").agg(
        off_epa_per_play=("epa", "mean"),
        off_success_rate=("success", "mean"),
        off_explosive_rate=("explosive", "mean"),
        ypp_off=("yards_gained", "mean"),
    )
    deff = scrim.groupby("defteam").agg(
        def_epa_per_play=("epa", "mean"),
        def_success_rate=("success", "mean"),
        def_explosive_rate=("explosive", "mean"),
        ypp_def=("yards_gained", "mean"),
    )

    # --- third down % (offense) -------------------------------------------
    third = pbp[(pbp["down"] == 3) & pbp["play_type"].isin(["pass", "run"])]
    third_down = third.groupby("posteam")["third_down_converted"].mean().rename("third_down_pct")

    # --- red zone TD rate (offense, per red-zone play) --------------------
    rz = scrim[scrim["yardline_100"] <= REDZONE_YARDLINE_100].copy()
    rz["td"] = (rz["pass_touchdown"] == 1) | (rz["rush_touchdown"] == 1)
    redzone = rz.groupby("posteam")["td"].mean().rename("redzone_td_rate")

    # --- turnovers: giveaways (offense) / takeaways (defense) -------------
    giveaways = pbp[(pbp["interception"] == 1) | (pbp["fumble_lost"] == 1)]
    give = giveaways.groupby("posteam").size().rename("giveaways")
    take = giveaways.groupby("defteam").size().rename("takeaways")

    # --- sack rate allowed (offense) ---------------------------------------
    dropbacks = pbp[(pbp["pass_attempt"] == 1) | (pbp["sack"] == 1)]
    sack_off = dropbacks.groupby("posteam").agg(sacks=("sack", "sum"), dropbacks=("sack", "count"))
    sack_off["sack_rate_allowed"] = sack_off["sacks"] / sack_off["dropbacks"]

    # --- INT rate (offense, per attempt) -----------------------------------
    int_off = pbp[pbp["pass_attempt"] == 1].groupby("posteam").agg(
        ints=("interception", "sum"), att=("pass_attempt", "sum")
    )
    int_off["int_rate"] = int_off["ints"] / int_off["att"]

    # --- CPOE (offense) ------------------------------------------------------
    cpoe = pbp[pbp["cpoe"].notna()].groupby("posteam")["cpoe"].mean().rename("cpoe")

    # --- assemble ------------------------------------------------------------
    teams = sorted(set(pf.index) | set(off.index))
    out = pd.DataFrame(index=teams)
    out["games"] = games_played
    out["pf"] = pf
    out["pa"] = pa
    out = out.join(off).join(deff).join(third_down).join(redzone)
    out = out.join(give).join(take)
    out = out.join(sack_off["sack_rate_allowed"]).join(int_off["int_rate"]).join(cpoe)

    out["giveaways"] = out["giveaways"].fillna(0)
    out["takeaways"] = out["takeaways"].fillna(0)
    out["turnover_margin"] = out["takeaways"] - out["giveaways"]
    out["ppg"] = out["pf"] / out["games"]
    out["papg"] = out["pa"] / out["games"]
    out["point_diff_per_g"] = (out["pf"] - out["pa"]) / out["games"]
    out["epa_margin"] = out["off_epa_per_play"] - out["def_epa_per_play"]
    out["ypp_margin"] = out["ypp_off"] - out["ypp_def"]

    out.index.name = "team"
    return out.reset_index()


def compute_league_norms(team_stats: pd.DataFrame) -> dict:
    """Mean/std per feature, used to z-score any team against the league."""
    feats = [
        "point_diff_per_g", "epa_margin", "turnover_margin", "off_explosive_rate",
        "def_explosive_rate", "third_down_pct", "redzone_td_rate",
        "sack_rate_allowed", "int_rate", "ypp_margin", "cpoe",
        "off_epa_per_play", "def_epa_per_play",  # display-only, not weighted in the logit
    ]
    return {
        f: {"mean": float(team_stats[f].mean()), "std": float(team_stats[f].std())}
        for f in feats
    }


def blend_team_stats(prior: pd.DataFrame, current: pd.DataFrame, k: float = 4.0) -> pd.DataFrame:
    """
    Blends last season's full-season stats with this season's stats so far,
    weighted by how many games of *current*-season data exist. This is what
    makes Week 2, 3, 4... actually learn from what just happened instead of
    ignoring it until some arbitrary number of weeks have passed.

    weight = games_played / (games_played + k)
      - 0 games played (bye-affected edge case, or team missing from current
        data): weight = 0, pure prior-season stats.
      - games_played = k (default 4): weight = 0.5, an even blend.
      - As games_played grows, weight -> 1, i.e. the season's actual stats
        take over almost entirely by mid-season -- which is the correct
        behavior, not a bug: by week 10, this year's team IS the team.

    This is a simple, transparent shrinkage rule, not a fitted model. If you
    want to tune it, the one number that matters is `k`: lower values trust
    new data faster, higher values are more conservative early in the season.
    """
    merged = prior.merge(current, on="team", how="left", suffixes=("_prior", "_current"))
    all_cols = FEATURE_COLUMNS + ["pf", "pa"]

    out_rows = []
    for _, row in merged.iterrows():
        games_current = row.get("games_current")
        games_current = 0 if pd.isna(games_current) else games_current
        weight = games_current / (games_current + k) if (games_current + k) > 0 else 0.0

        blended = {"team": row["team"], "games": games_current}
        for col in all_cols:
            prior_val = row.get(f"{col}_prior", row.get(col))
            current_val = row.get(f"{col}_current")
            if pd.isna(current_val):
                blended[col] = prior_val
            else:
                blended[col] = (1 - weight) * prior_val + weight * current_val
        blended["blend_weight_on_current_season"] = round(weight, 3)
        out_rows.append(blended)

    return pd.DataFrame(out_rows)
