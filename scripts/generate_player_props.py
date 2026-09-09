"""
Generates player-level projections (RB1/WR1/WR2/TE1 per team, matchup-
adjusted against that week's specific opponent) for every game in a week.

Usage:
    python scripts/generate_player_props.py --season 2026 --week 1

Uses the PRIOR season's player usage data as the starting point for "who
is this team's RB1/WR1/WR2/TE1" -- same reasoning as the team-level model
using prior-season stats for a Week 1 prediction. This is real, data-
driven usage, not a guess -- but it can go stale exactly the way the QB
assumption can (a trade, a released veteran, a rookie winning a camp
battle). It is NOT re-verified against current news the way the flagship
Week 1 2026 team predictions were. Treat it as a real, useful starting
signal, not a guarantee of a team's actual current depth chart.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import data_pipeline  # noqa: E402
from app.player_props import (  # noqa: E402
    compute_position_defense_allowed,
    fetch_player_stats_week,
    get_skill_players,
    project_player_vs_opponent,
    redzone_favorability_score,
)


def build_game_props(home: str, away: str, stats, defense_allowed: dict) -> dict:
    home_players = get_skill_players(stats, home)
    away_players = get_skill_players(stats, away)

    def enrich_side(players: dict, opponent: str) -> dict:
        out = {}
        for slot, player in players.items():
            if not player:
                out[slot] = None
                continue
            position = "RB" if slot == "rb1" else ("TE" if slot == "te1" else "WR")
            proj = project_player_vs_opponent(player, position, opponent, defense_allowed)
            rz = redzone_favorability_score(player, position, opponent, defense_allowed)
            out[slot] = {**player, "position": position, **proj, "redzone_favorability": rz}
        return out

    return {
        "home": enrich_side(home_players, away),
        "away": enrich_side(away_players, home),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    args = parser.parse_args()

    # Same prior-season-baseline logic as the team model for a Week 1 slate;
    # for later weeks this would ideally blend in current-season usage too
    # (a natural follow-up, not built yet -- flagged rather than assumed).
    stats_season = args.season - 1
    stats = fetch_player_stats_week(stats_season)
    defense_allowed = compute_position_defense_allowed(stats)

    week_games = data_pipeline.get_week_games(args.season, args.week)

    props_by_game = []
    for _, g in week_games.iterrows():
        props = build_game_props(g["home_team"], g["away_team"], stats, defense_allowed)
        props_by_game.append({"home_team": g["home_team"], "away_team": g["away_team"], **props})

    out_path = Path(f"data/player_props_{args.season}_wk{args.week}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(props_by_game, f, indent=2, default=str)
    print(f"[generate_player_props] Wrote {len(props_by_game)} games to {out_path}")


if __name__ == "__main__":
    main()
