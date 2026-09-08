"""
The hourly job. Deliberately lightweight: it does NOT re-download play-by-
play data or recompute the model (that's the Tuesday job's work, and
re-pulling ~20MB of data 24x a day for no reason would be wasteful). It
just checks ESPN's injury report for each game's two starting QBs and, if
either shows a concerning status, attaches an alert to that game's entry in
the already-generated predictions file, then re-renders the page.

Usage:
    python scripts/hourly_injury_check.py --season 2026
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import injury_watch, schedule  # noqa: E402
from app.qb_meta import QB_META  # noqa: E402
from scripts.render_html import render  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    args = parser.parse_args()

    week = schedule.current_week(args.season)
    predictions_path = Path(f"data/predictions_{args.season}_wk{week}.json")

    if not predictions_path.exists():
        print(f"[hourly_injury_check] {predictions_path} doesn't exist yet -- "
              f"nothing to check until the weekly pipeline has run at least once.")
        return

    with open(predictions_path) as f:
        predictions = json.load(f)

    changed = False
    for g in predictions["games"]:
        for side, team_key in (("home", "home_team"), ("away", "away_team")):
            team = g[team_key]
            qb = QB_META.get(team)
            if not qb:
                continue
            alert = injury_watch.get_qb_injury_alert(team, qb["name"], args.season, week)
            field = f"{side}_qb_injury_alert"
            if g.get(field) != alert:
                g[field] = alert
                changed = True
                if alert:
                    print(f"[hourly_injury_check] ALERT for {team} ({g['away_team']} @ {g['home_team']}): {alert}")

    if not changed:
        print("[hourly_injury_check] No injury-status changes found this run.")
        return

    with open(predictions_path, "w") as f:
        json.dump(predictions, f, indent=2, default=str)

    out = render(predictions_path)
    print(f"[hourly_injury_check] Updated predictions and re-rendered {out}")


if __name__ == "__main__":
    main()
