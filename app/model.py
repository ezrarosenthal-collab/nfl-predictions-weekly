"""
The scoring model itself. This is a direct Python port of the logic that
was hand-validated (and manually checked against real 2025 stats) in the
prototype phase -- same weights, same formula, same calibration. If you
change anything here, re-run scripts/backfill_correlations.py first to make
sure it's still justified.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import erf, exp, sqrt

from config import (
    GAME_MARGIN_SIGMA,
    GAMES_PER_SEASON,
    HOME_FIELD_ADVANTAGE_POINTS,
    MARGIN_SLOPE,
    MAX_WIN_PROB,
    MIN_WIN_PROB,
    NEUTRAL_SITE_ADVANTAGE_POINTS,
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
    """Kept for backward compatibility / tests -- no longer used in predict_game."""
    return 1.0 / (1.0 + exp(-x))


def normal_cdf(x: float) -> float:
    """Standard normal CDF via math.erf -- no scipy dependency needed."""
    return 0.5 * (1.0 + erf(x / sqrt(2)))


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

    UNIFIED MARGIN MODEL: win probability and the projected score both come
    from the same predicted_margin, computed from the same combined
    10-stat composite (which itself already includes point_diff_per_g --
    i.e. the raw offense/defense scoring averages -- blended with EPA
    margin). There is no separate, independent formula for either output
    anymore, so they cannot contradict each other. See config.py for the
    real-data fit behind MARGIN_SLOPE / HOME_FIELD_ADVANTAGE_POINTS /
    GAME_MARGIN_SIGMA.
    """
    home_total, home_comps = score_team(home_stats, league)
    away_total, away_comps = score_team(away_stats, league)

    composite_diff = home_total - away_total
    field_advantage = NEUTRAL_SITE_ADVANTAGE_POINTS if neutral_site else HOME_FIELD_ADVANTAGE_POINTS
    predicted_margin = MARGIN_SLOPE * composite_diff + field_advantage

    # Win probability: the real statistical relationship between a
    # predicted margin and how often that margin actually holds up,
    # fit from 1,359 real games -- not an arbitrary logistic curve.
    home_wp = normal_cdf(predicted_margin / GAME_MARGIN_SIGMA) * 100
    home_wp = max(MIN_WIN_PROB, min(MAX_WIN_PROB, home_wp))
    away_wp = 100 - home_wp

    # If the win probability got clamped by the regulation above, re-derive
    # the margin from the clamped probability so the score stays consistent
    # with what's actually displayed (rather than an unclamped, more
    # extreme margin the reader never sees the justification for).
    if home_wp in (MIN_WIN_PROB, MAX_WIN_PROB):
        # invert normal_cdf via its inverse (probit) using erf's inverse is
        # unnecessary here -- just solve numerically isn't needed either;
        # at the clamp boundary we simply cap the margin at whatever value
        # produces exactly that boundary probability, computed once as a
        # constant since GAME_MARGIN_SIGMA is fixed.
        from statistics import NormalDist
        boundary_z = NormalDist().inv_cdf(home_wp / 100)
        predicted_margin = boundary_z * GAME_MARGIN_SIGMA

    # Total points: this is where the general offense/defense scoring
    # averages (ppg / points allowed per game) feed in -- a separate,
    # complementary signal from the composite (how high- or low-scoring
    # this particular matchup should be), then split using the SAME
    # predicted_margin used for win probability above.
    home_field_scoring_bump = 1.0 if neutral_site else 1.02
    naive_home_pts = home_stats["ppg"] * (away_stats["papg"] / league_avg_ppg) * home_field_scoring_bump
    naive_away_pts = away_stats["ppg"] * (home_stats["papg"] / league_avg_ppg)
    projected_total = naive_home_pts + naive_away_pts

    home_score_est = projected_total / 2 + predicted_margin / 2
    away_score_est = projected_total / 2 - predicted_margin / 2

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
