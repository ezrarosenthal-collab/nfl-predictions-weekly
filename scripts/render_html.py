"""
Turns a predictions_{season}_wk{week}.json (from generate_predictions.py)
into the actual static site (site/template.html -> docs/index.html).

Usage:
    python scripts/render_html.py --season 2026 --week 2

This is the last step of the fully-automated weekly pipeline:
    generate_predictions.py  ->  produces the numbers
    render_html.py           ->  produces the webpage
    (git commit + push)      ->  GitHub Pages serves the new page

All three are chained together in .github/workflows/weekly_update.yml so
nobody has to run this by hand.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.team_meta import TEAM_META  # noqa: E402

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "site" / "template.html"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "docs"  # GitHub Pages default


def _day_bucket(kickoff: str | None) -> str:
    if not kickoff:
        return "TBD"
    try:
        d = datetime.fromisoformat(str(kickoff))
        return d.strftime("%a %-m/%-d")
    except ValueError:
        return str(kickoff)


def enrich_games(predictions: dict) -> list[dict]:
    """Attach display metadata (colors, names) the template needs."""
    out = []
    for g in predictions["games"]:
        home_meta = TEAM_META.get(g["home_team"], {"name": g["home_team"], "color": "#888"})
        away_meta = TEAM_META.get(g["away_team"], {"name": g["away_team"], "color": "#888"})
        enriched = dict(g)
        enriched["home_color"] = home_meta["color"]
        enriched["away_color"] = away_meta["color"]
        enriched["home_name"] = home_meta["name"]
        enriched["away_name"] = away_meta["name"]
        enriched["day"] = _day_bucket(g.get("kickoff"))
        out.append(enriched)
    return out


def _baseline_footer_text(baseline: dict) -> str:
    if baseline["mode"] == "prior_season_only":
        return f"Baseline stats: full {baseline['prior_season']} season (no current-season games yet)."
    return (
        f"Baseline stats: blend of {baseline['prior_season']} season and "
        f"{baseline['current_season_games_through_week']} game(s) of the current season "
        f"(avg {baseline['avg_weight_on_current_season']*100:.0f}% weight on current-season results so far)."
    )


def _load_track_record(season: int) -> dict | None:
    path = Path(__file__).resolve().parent.parent / "data" / f"track_record_{season}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def render(predictions_path: Path, output_path: Path | None = None) -> Path:
    with open(predictions_path) as f:
        predictions = json.load(f)

    predictions["games"] = enrich_games(predictions)
    predictions["track_record"] = _load_track_record(predictions["season"])
    predictions["team_names"] = TEAM_META

    template = TEMPLATE_PATH.read_text()
    season, week = predictions["season"], predictions["week"]
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = (
        template
        .replace("{{TITLE}}", f"DailyPredictionNFL — Week {week}, {season}")
        .replace("{{DESCRIPTION}}", f"NFL Week {week} {season} predictions for every game, updated automatically.")
        .replace("{{SUBTITLE}}", f"Week {week} · {season} Season · Auto-updated every Tuesday morning after Monday Night Football")
        .replace("{{GENERATED_AT}}", generated_at)
        .replace("{{FOOTER}}", (
            _baseline_footer_text(predictions["baseline"])
            + " Model weights and methodology unchanged from the validated version. Not betting advice."
        ))
        .replace("{{GAMES_JSON}}", json.dumps(predictions))
    )

    output_path = output_path or (OUTPUT_DIR / "index.html")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html)
    return output_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    args = parser.parse_args()

    predictions_path = Path(f"data/predictions_{args.season}_wk{args.week}.json")
    if not predictions_path.exists():
        raise SystemExit(f"{predictions_path} not found -- run generate_predictions.py first")

    out = render(predictions_path)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
