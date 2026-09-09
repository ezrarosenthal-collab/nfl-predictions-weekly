"""
The one command the Tuesday-morning cron job runs. Auto-detects the
current week, regenerates predictions, and renders the site.

Usage:
    python scripts/weekly_pipeline.py --season 2026
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import schedule  # noqa: E402
from scripts.generate_predictions import build_week_predictions  # noqa: E402
from scripts.generate_player_props import build_game_props  # noqa: E402
from scripts.render_html import render  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    args = parser.parse_args()

    week = schedule.current_week(args.season)
    print(f"[weekly_pipeline] season={args.season} week={week} (auto-detected)")

    result = build_week_predictions(args.season, week)
    predictions_path = Path(f"data/predictions_{args.season}_wk{week}.json")
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    with open(predictions_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"[weekly_pipeline] wrote {len(result['games'])} games to {predictions_path}")

    try:
        from app import data_pipeline
        from app.player_props import compute_position_defense_allowed, fetch_player_stats_week
        stats = fetch_player_stats_week(args.season - 1)
        defense_allowed = compute_position_defense_allowed(stats)
        week_games = data_pipeline.get_week_games(args.season, week)
        props_by_game = [
            {"home_team": g["home_team"], "away_team": g["away_team"],
             **build_game_props(g["home_team"], g["away_team"], stats, defense_allowed)}
            for _, g in week_games.iterrows()
        ]
        props_path = Path(f"data/player_props_{args.season}_wk{week}.json")
        with open(props_path, "w") as f:
            json.dump(props_by_game, f, indent=2, default=str)
        print(f"[weekly_pipeline] wrote player props for {len(props_by_game)} games to {props_path}")
    except Exception:  # noqa: BLE001 -- player props are a bonus feature, never block the main pipeline on it
        logging.exception("[weekly_pipeline] player props generation failed, continuing without it")

    out_path = render(predictions_path)
    print(f"[weekly_pipeline] rendered site to {out_path}")

    qb_flags = [g for g in result["games"] if g.get("qb_watch")]
    if qb_flags:
        print(f"[weekly_pipeline] {len(qb_flags)} game(s) flagged by automated QB-change detection:")
        for g in qb_flags:
            print(f"  - {g['away_team']} @ {g['home_team']}: {g['qb_watch']}")


if __name__ == "__main__":
    main()
