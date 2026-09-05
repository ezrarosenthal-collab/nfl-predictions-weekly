"""
Reproduces the research behind config.RESEARCH and config.WEIGHTS: pulls
2021-2025 play-by-play, builds team-season stats, and correlates each
candidate feature against actual win percentage.

Run this whenever you're tempted to add, remove, or re-weight a feature --
it's the actual evidence, not a one-time result to take on faith. If you add
a new candidate stat, add it to CANDIDATES below and re-run.

Usage:
    python scripts/backfill_correlations.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from app import data_pipeline, features  # noqa: E402

SEASONS = [2021, 2022, 2023, 2024, 2025]

CANDIDATES = {
    "Point Differential / Game": "point_diff_per_g",
    "EPA Margin (Off - Def per play)": "epa_margin",
    "Offensive EPA per Play": "off_epa_per_play",
    "Yards per Play Margin": "ypp_margin",
    "Third Down Conversion %": "third_down_pct",
    "Turnover Margin": "turnover_margin",
    "Defensive EPA per Play": "def_epa_per_play",
    "Completion % Over Expected (CPOE)": "cpoe",
    "Offensive Explosive Play Rate": "off_explosive_rate",
    "Defensive Explosive Play Rate Allowed": "def_explosive_rate",
    "Red Zone TD Rate (Offense)": "redzone_td_rate",
    "Sack Rate Allowed (Offense)": "sack_rate_allowed",
    "INT Rate (Offense)": "int_rate",
}


def build_multi_season_dataset() -> pd.DataFrame:
    games_df = data_pipeline.fetch_games()
    frames = []
    for season in SEASONS:
        pbp = data_pipeline.fetch_pbp(season)
        team_stats = features.build_team_stats(pbp, games_df, season)
        team_stats["season"] = season
        team_stats["win_pct"] = (
            team_stats["pf"] / team_stats["pf"]  # placeholder, replaced below
        )
        frames.append(team_stats)
    all_stats = pd.concat(frames, ignore_index=True)

    # win_pct needs real win totals, not just points -- recompute from games
    reg = games_df[(games_df["season"].isin(SEASONS)) & (games_df["game_type"] == "REG")]
    reg = reg.dropna(subset=["home_score", "away_score"])
    records = []
    for _, g in reg.iterrows():
        hw = 1 if g["home_score"] > g["away_score"] else (0.5 if g["home_score"] == g["away_score"] else 0)
        records.append({"season": g["season"], "team": g["home_team"], "win": hw})
        records.append({"season": g["season"], "team": g["away_team"], "win": 1 - hw if g["home_score"] != g["away_score"] else 0.5})
    wins = pd.DataFrame(records).groupby(["season", "team"]).agg(wins=("win", "sum"), games=("win", "count")).reset_index()
    wins["win_pct"] = wins["wins"] / wins["games"]

    all_stats = all_stats.drop(columns=["win_pct"]).merge(wins[["season", "team", "win_pct"]], on=["season", "team"])
    return all_stats


def main():
    print(f"Building team-season dataset for {SEASONS}...")
    df = build_multi_season_dataset()
    print(f"{len(df)} team-seasons.\n")

    results = []
    for label, col in CANDIDATES.items():
        r = df["win_pct"].corr(df[col])
        results.append((label, col, r, r ** 2))

    results.sort(key=lambda x: -x[3])
    print(f"{'Stat':45s} {'r':>8s} {'R^2':>8s}")
    print("-" * 65)
    for label, col, r, r2 in results:
        print(f"{label:45s} {r:8.3f} {r2:8.3f}")

    out = pd.DataFrame(results, columns=["stat", "column", "correlation", "r_squared"])
    out.to_csv("data/correlation_results.csv", index=False)
    print("\nWrote data/correlation_results.csv")


if __name__ == "__main__":
    main()
