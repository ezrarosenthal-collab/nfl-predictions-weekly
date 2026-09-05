"""
Weekly orchestration: pipeline -> features -> model -> overrides -> JSON.

Usage:
    python scripts/generate_predictions.py --season 2026 --week 1

Baseline-stats logic:
  - Week 1 of a season: no current-season data exists yet, so use the
    *prior* season's full-season stats as the baseline -- same as using
    2025 stats for Week 1 of 2026.
  - Week 2+: BLEND last season's stats with this season's stats so far
    (features.blend_team_stats), weighted by how many current-season games
    each team has played. Early in the season that's mostly last year's
    numbers with a growing nudge from this year's results; by mid-season
    it's almost entirely this year's actual performance. This is what
    makes the model genuinely learn week over week instead of freezing on
    a stale prior-season number for the first month.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import data_pipeline, features, model, odds, overrides as overrides_mod, qb_watch, schedule  # noqa: E402
from app.qb_meta import QB_META  # noqa: E402

BLEND_K = 4.0  # see features.blend_team_stats -- games needed to reach a 50/50 blend


def _snapshot_fields(stats: dict) -> dict:
    """The subset of raw team stats shown in the season-stats snapshot table."""
    fields = [
        "ppg", "papg", "off_epa_per_play", "def_epa_per_play", "epa_margin",
        "turnover_margin", "off_explosive_rate", "def_explosive_rate",
        "third_down_pct", "redzone_td_rate", "cpoe", "sack_rate_allowed", "int_rate",
    ]
    return {f: round(stats[f], 4) if stats.get(f) is not None else None for f in fields}


def _build_baseline_team_stats(season: int, week: int):
    """
    Returns (team_stats_df, meta) where meta describes what went into the
    baseline (for transparency in the output JSON).
    """
    prior_pbp = data_pipeline.fetch_pbp(season - 1)
    games_df = data_pipeline.fetch_games()
    prior_stats = features.build_team_stats(prior_pbp, games_df, season - 1)

    if week == 1:
        return prior_stats, {"mode": "prior_season_only", "prior_season": season - 1}

    current_pbp = data_pipeline.fetch_pbp(season)
    current_stats = features.build_team_stats(current_pbp, games_df, season, through_week=week - 1)

    blended = features.blend_team_stats(prior_stats, current_stats, k=BLEND_K)
    avg_games = float(blended["games"].mean())
    avg_weight = float(blended["blend_weight_on_current_season"].mean())
    return blended, {
        "mode": "blended",
        "prior_season": season - 1,
        "current_season_games_through_week": week - 1,
        "avg_current_season_games_played": round(avg_games, 1),
        "avg_weight_on_current_season": round(avg_weight, 3),
    }


def build_week_predictions(season: int, week: int) -> dict:
    team_stats, baseline_meta = _build_baseline_team_stats(season, week)
    league_norms = features.compute_league_norms(team_stats)
    league_avg_ppg = float(team_stats["ppg"].mean())

    stats_by_team = {row["team"]: row.to_dict() for _, row in team_stats.iterrows()}

    games_df = data_pipeline.fetch_games()
    week_games = games_df[
        (games_df["season"] == season) & (games_df["week"] == week) & (games_df["game_type"] == "REG")
    ].copy()
    override_map = overrides_mod.load_overrides()

    # Automated QB-change detection (see app/qb_watch.py for what this can
    # and can't catch). Uses the *current* season's pbp so far, since it's
    # comparing recent starters against earlier ones within the same season.
    try:
        current_season_pbp = data_pipeline.fetch_pbp(season)
        qb_changes = qb_watch.detect_starter_changes(current_season_pbp, season, week)
    except Exception:  # noqa: BLE001 -- QB-watch is a bonus signal, never block the pipeline on it
        qb_changes = {}

    out_games = []
    for _, g in week_games.iterrows():
        home, away = g["home_team"], g["away_team"]
        if home not in stats_by_team or away not in stats_by_team:
            continue  # team not found in baseline stats (e.g. bye-affected data gap)

        neutral = str(g.get("location", "")).strip().lower() == "neutral"
        pred = model.predict_game(
            home_stats=stats_by_team[home],
            away_stats=stats_by_team[away],
            league=league_norms,
            league_avg_ppg=league_avg_ppg,
            neutral_site=neutral,
        )
        pred_dict = {
            "home_team": home,
            "away_team": away,
            "kickoff": g.get("gameday"),
            "time_et": g.get("gametime"),
            "location": g.get("location"),
            "home_win_prob": pred.home_win_prob,
            "away_win_prob": pred.away_win_prob,
            "home_score_est": pred.home_score_est,
            "away_score_est": pred.away_score_est,
            "feature_breakdown": pred.feature_breakdown,
            "market": odds.get_game_odds(g),
            # Raw stats for every game (not just ones with a manual
            # override) so the site can always show the full season-stats
            # snapshot table and QB info, not just the researched games.
            "home_stats": _snapshot_fields(stats_by_team[home]),
            "away_stats": _snapshot_fields(stats_by_team[away]),
            "home_qb": QB_META.get(home),
            "away_qb": QB_META.get(away),
        }
        pred_dict = overrides_mod.apply_override(pred_dict, season, week, away, home, override_map)

        watch_notes = []
        for team in (home, away):
            change = qb_changes.get(team)
            if change:
                watch_notes.append(
                    f"{team}'s starting QB in the most recent game "
                    f"({change['recent_starter']}) differs from earlier this season "
                    f"({', '.join(change['earlier_starters'])}) -- trailing stats may not "
                    f"reflect the current starter."
                )
        pred_dict["qb_watch"] = " ".join(watch_notes) if watch_notes else None

        out_games.append(pred_dict)

    return {
        "season": season,
        "week": week,
        "baseline": baseline_meta,
        "league_avg_ppg": round(league_avg_ppg, 2),
        "games": out_games,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, default=None, help="Omit to auto-detect the current week from the schedule")
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    week = args.week if args.week is not None else schedule.current_week(args.season)
    print(f"Using week {week}" + (" (auto-detected)" if args.week is None else ""))

    result = build_week_predictions(args.season, week)

    out_path = args.out or f"data/predictions_{args.season}_wk{week}.json"
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=str)

    print(f"Wrote {len(result['games'])} games to {out_path}")


if __name__ == "__main__":
    main()
