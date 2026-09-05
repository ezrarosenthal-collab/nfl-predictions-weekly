import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from app.features import FEATURE_COLUMNS, blend_team_stats  # noqa: E402


def _stats_df(rows: dict[str, dict]) -> pd.DataFrame:
    """Build a minimal team-stats DataFrame from {team: {col: val}} for testing."""
    records = []
    for team, vals in rows.items():
        row = {c: 0.0 for c in FEATURE_COLUMNS + ["pf", "pa"]}
        row["team"] = team
        row["games"] = vals.get("games", 17)
        row.update(vals)
        records.append(row)
    return pd.DataFrame(records)


def test_zero_current_games_is_pure_prior_season():
    prior = _stats_df({"AAA": {"off_epa_per_play": 0.10}})
    current = _stats_df({"AAA": {"off_epa_per_play": 0.50, "games": 0}})
    blended = blend_team_stats(prior, current, k=4.0)
    row = blended[blended.team == "AAA"].iloc[0]
    assert row["blend_weight_on_current_season"] == 0.0
    assert abs(row["off_epa_per_play"] - 0.10) < 1e-9


def test_weight_formula_matches_games_over_games_plus_k():
    prior = _stats_df({"AAA": {"off_epa_per_play": 0.0}})
    current = _stats_df({"AAA": {"off_epa_per_play": 1.0, "games": 2}})
    blended = blend_team_stats(prior, current, k=4.0)
    row = blended[blended.team == "AAA"].iloc[0]
    # weight = 2 / (2 + 4) = 0.333...
    assert abs(row["blend_weight_on_current_season"] - (2 / 6)) < 1e-3
    assert abs(row["off_epa_per_play"] - (2 / 6)) < 1e-3  # 0*(1-w) + 1*w = w


def test_more_games_means_more_trust_in_current_season():
    prior = _stats_df({"AAA": {"off_epa_per_play": 0.0}})
    early = _stats_df({"AAA": {"off_epa_per_play": 1.0, "games": 1}})
    late = _stats_df({"AAA": {"off_epa_per_play": 1.0, "games": 12}})

    early_blend = blend_team_stats(prior, early, k=4.0)
    late_blend = blend_team_stats(prior, late, k=4.0)

    w_early = early_blend[early_blend.team == "AAA"].iloc[0]["blend_weight_on_current_season"]
    w_late = late_blend[late_blend.team == "AAA"].iloc[0]["blend_weight_on_current_season"]
    assert w_late > w_early
    assert w_late > 0.7  # by 12 games, should be trusting the actual season heavily


def test_team_missing_from_current_season_falls_back_to_prior():
    """E.g. data gap or a team not yet found in current-season pbp."""
    prior = _stats_df({"AAA": {"off_epa_per_play": 0.20}})
    current = _stats_df({"BBB": {"off_epa_per_play": 0.90, "games": 5}})
    blended = blend_team_stats(prior, current, k=4.0)
    row = blended[blended.team == "AAA"].iloc[0]
    assert row["blend_weight_on_current_season"] == 0.0
    assert abs(row["off_epa_per_play"] - 0.20) < 1e-9
