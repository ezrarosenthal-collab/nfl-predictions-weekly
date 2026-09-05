"""
The one command the Tuesday-morning cron job runs. Auto-detects the
current week, regenerates predictions, and renders the site.

Usage:
    python scripts/weekly_pipeline.py --season 2026
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import schedule  # noqa: E402
from scripts.generate_predictions import build_week_predictions  # noqa: E402
from scripts.render_html import render  # noqa: E402
import json  # noqa: E402


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

    out_path = render(predictions_path)
    print(f"[weekly_pipeline] rendered site to {out_path}")

    qb_flags = [g for g in result["games"] if g.get("qb_watch")]
    if qb_flags:
        print(f"[weekly_pipeline] {len(qb_flags)} game(s) flagged by automated QB-change detection:")
        for g in qb_flags:
            print(f"  - {g['away_team']} @ {g['home_team']}: {g['qb_watch']}")


if __name__ == "__main__":
    main()
