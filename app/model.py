"""
The scoring model itself. This is a direct Python port of the logic that
was hand-validated (and manually checked against real 2025 stats) in the
prototype phase -- same weights, same formula, same calibration. If you
change anything here, re-run scripts/backfill_correlations.py first to make
sure it's still justified.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import exp

from config import (
    GAMES_PER_SEASON,
    HOME_FIELD_EDGE,
    LOGIT_SCALE,
    MAX_WIN_PROB,
    MIN_WIN_PROB,
    NEUTRAL_SITE_EDGE,
    WEIGHTS,
)


def zscore(value: float, mean: float, std: float) -> float:
    if not std:
        return 0.0
    return (value - mean) / std


@dataclass
class TeamComponents:
    """Standardized (z-scored) values for each model input, for one team."""
    strength: float
    turnover: float
    ypp: float
    explosive: float
    third_down: float
    redzone: float
    cpoe: float
    sack_protect: float
    ball_security: float
    off_epa_standalone: float
    def_epa_standalone: float

    def weighted_total(self) -> float:
        return (
            self.strength * WEIGHTS["strength"]
            + self.turnover * WEIGHTS["turnover"]
            + self.ypp * WEIGHTS["ypp"]
            + self.explosive * WEIGHTS["explosive"]
            + self.third_down * WEIGHTS["third_down"]
            + self.redzone * WEIGHTS["redzone"]
            + self.cpoe * WEIGHTS["cpoe"]
            + self.sack_protect * WEIGHTS["sack_protect"]
            + self.ball_security * WEIGHTS["ball_security"]
            # off/def EPA standalone are intentionally excluded -- see config.py
        )


def score_team(stats: dict, league: dict) -> tuple[float, TeamComponents]:
    """
    Compute a team's weighted composite score against league norms.

    `stats` is one row of team-season features (see features.build_team_stats).
    `league` is the dict from features.compute_league_norms.
    """
    def z(key: str) -> float:
        return zscore(stats[key], league[key]["mean"], league[key]["std"])

    strength = 0.5 * z("point_diff_per_g") + 0.5 * z("epa_margin")
    comps = TeamComponents(
        strength=strength,
        turnover=z("turnover_margin"),
        ypp=z("ypp_margin"),
        explosive=z("off_explosive_rate") - z("def_explosive_rate"),
        third_down=z("third_down_pct"),
        redzone=z("redzone_td_rate"),
        cpoe=z("cpoe"),
        sack_protect=-z("sack_rate_allowed"),
        ball_security=-z("int_rate"),
        off_epa_standalone=z("off_epa_per_play"),  # display-only -- weight is 0, see config.py
        def_epa_standalone=z("def_epa_per_play"),
    )
    return comps.weighted_total(), comps


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + exp(-x))


@dataclass
class GamePrediction:
    home_team: str
    away_team: str
    home_win_prob: float          # 0-100
    away_win_prob: float          # 0-100
    home_score_est: float
    away_score_est: float
    feature_breakdown: list[dict] = field(default_factory=list)


def predict_game(
    home_stats: dict,
    away_stats: dict,
    league: dict,
    league_avg_ppg: float,
    neutral_site: bool = False,
) -> GamePrediction:
    """
    The core prediction function. Everything else in the app exists to feed
    this function clean inputs and present its output.
    """
    home_total, home_comps = score_team(home_stats, league)
    away_total, away_comps = score_team(away_stats, league)

    diff = home_total - away_total
    edge = NEUTRAL_SITE_EDGE if neutral_site else HOME_FIELD_EDGE
    logit = edge + LOGIT_SCALE * diff
    home_wp = sigmoid(logit) * 100

    # Regulation: clamp to [MIN_WIN_PROB, MAX_WIN_PROB]. No matter how
    # lopsided the underlying stats are, the model never claims more
    # certainty than "any given Sunday" allows for in a sport this random.
    home_wp = max(MIN_WIN_PROB, min(MAX_WIN_PROB, home_wp))
    away_wp = 100 - home_wp

    home_field_scoring_bump = 1.0 if neutral_site else 1.02
    home_score_est = home_stats["ppg"] * (away_stats["papg"] / league_avg_ppg) * home_field_scoring_bump
    away_score_est = away_stats["ppg"] * (home_stats["papg"] / league_avg_ppg)

    labels = {
        "strength": "Strength Composite (Point Diff + EPA Margin)",
        "turnover": "Turnover Margin",
        "ypp": "Yards per Play Margin",
        "explosive": "Explosive Play Rate",
        "third_down": "Third Down Conversion %",
        "redzone": "Red Zone TD Rate",
        "cpoe": "Completion % Over Expected",
        "sack_protect": "Pass Protection (Sack Rate Allowed)",
        "ball_security": "Ball Security (INT Rate)",
    }
    breakdown = []
    for key, label in labels.items():
        w = WEIGHTS[key]
        home_val = getattr(home_comps, key)
        away_val = getattr(away_comps, key)
        weighted_diff = (home_val - away_val) * w
        breakdown.append({
            "key": key,
            "label": label,
            "weight": w,
            "weighted_diff": round(weighted_diff, 4),
            "favors": "home" if weighted_diff >= 0 else "away",
        })

    return GamePrediction(
        home_team=home_stats.get("team", "HOME"),
        away_team=away_stats.get("team", "AWAY"),
        home_win_prob=round(home_wp, 1),
        away_win_prob=round(away_wp, 1),
        home_score_est=round(home_score_est, 1),
        away_score_est=round(away_score_est, 1),
        feature_breakdown=breakdown,
    )
