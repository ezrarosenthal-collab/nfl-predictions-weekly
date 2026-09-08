"""
The hourly job. Deliberately lightweight: it does NOT re-download play-by-
play data or recompute the model (that's the Tuesday job's work, and
re-pulling ~20MB of data 24x a day for no reason would be wasteful). It
just checks the official injury report for every team in this week's
games -- every position, not just QB -- and, if anything concerning is
listed, attaches it to that game's entry in the already-generated
predictions file, then re-renders the page.

This prints a line for every team it checks (not just when something is
found), specifically so the coverage is visible in the Action's log --
you should be able to count 32 team-checks (16 games x 2) in a normal
full week, or fewer on a bye week.

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

    print(f"[hourly_injury_check] Checking {len(predictions['games'])} games "
          f"({len(predictions['games']) * 2} teams) for week {week}...")

    changed = False
    teams_checked = 0
    for g in predictions["games"]:
        for side, team_key in (("home", "home_team"), ("away", "away_team")):
            team = g[team_key]
            teams_checked += 1

            # Full report, every position -- not just the named starting QB.
            team_alerts = injury_watch.get_team_injury_report(team, args.season, week)
            field = f"{side}_team_injuries"
            if g.get(field) != team_alerts:
                g[field] = team_alerts
                changed = True

            if team_alerts:
                print(f"[hourly_injury_check]   {team} ({g['away_team']} @ {g['home_team']}): "
                      f"{len(team_alerts)} flagged -- " + "; ".join(team_alerts))
            else:
                print(f"[hourly_injury_check]   {team} ({g['away_team']} @ {g['home_team']}): clear")

            # Keep the QB-specific alert too -- this is the one that matters
            # for the model's overrides workflow (a QB change is what
            # actually invalidates the trailing-stat prediction).
            qb = QB_META.get(team)
            if qb:
                qb_alert = injury_watch.get_qb_injury_alert(team, qb["name"], args.season, week)
                qb_field = f"{side}_qb_injury_alert"
                if g.get(qb_field) != qb_alert:
                    g[qb_field] = qb_alert
                    changed = True

    print(f"[hourly_injury_check] Checked {teams_checked} teams total.")

    if not changed:
        print("[hourly_injury_check] No injury-status changes found this run.")
        return

    with open(predictions_path, "w") as f:
        json.dump(predictions, f, indent=2, default=str)

    out = render(predictions_path)
    print(f"[hourly_injury_check] Updated predictions and re-rendered {out}")


if __name__ == "__main__":
    main()
