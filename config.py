"""
Central configuration for the prediction model.

Every constant here was set from the correlation research done against real
2021-2025 play-by-play (see scripts/backfill_correlations.py to reproduce
it). Nothing in this file is a guess — change it only after re-running the
validation script and confirming the new numbers still hold up.
"""

# ---------------------------------------------------------------------------
# nflverse data sources (all confirmed reachable as of this build)
# ---------------------------------------------------------------------------
NFLVERSE_PBP_URL = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.csv.gz"
NFLVERSE_GAMES_URL = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"

# ---------------------------------------------------------------------------
# Feature set: the 10 stats validated against 5 years of real outcomes.
# R2 values are from the 160-team-season correlation study.
# ---------------------------------------------------------------------------
RESEARCH = [
    {"key": "point_diff_per_g", "label": "Point Differential / Game", "r2": 0.801},
    {"key": "epa_margin", "label": "EPA Margin (Off - Def per play)", "r2": 0.765},
    {"key": "off_epa_per_play", "label": "Offensive EPA per Play", "r2": 0.549},
    {"key": "ypp_margin", "label": "Yards per Play Margin", "r2": 0.545},
    {"key": "third_down_pct", "label": "Third Down Conversion %", "r2": 0.416},
    {"key": "turnover_margin", "label": "Turnover Margin", "r2": 0.367},
    {"key": "def_epa_per_play", "label": "Defensive EPA per Play", "r2": 0.324},
    {"key": "cpoe", "label": "Completion % Over Expected (CPOE)", "r2": 0.280},
    {"key": "explosive_rate", "label": "Explosive Play Rate (Off - Def)", "r2": 0.259},
    {"key": "redzone_td_rate", "label": "Red Zone TD Rate (Offense)", "r2": 0.186},
]

# Stats tested during research that did NOT hold up — kept here so nobody
# re-adds them without re-checking. See backfill_correlations.py.
REJECTED_STATS = [
    {"key": "avg_start_fieldpos", "label": "Average starting field position", "r2": 0.016},
    {"key": "penalty_yds_per_g", "label": "Net penalty yards / game", "r2": 0.000},
    {"key": "sack_rate_generated", "label": "Defensive sack rate generated", "r2": 0.063},
]

# ---------------------------------------------------------------------------
# Model weights: the base multiplier applied to each standardized (z-scored)
# feature diff before summing into the logit. Set from R^2 magnitude, then
# manually discounted wherever a stat is heavily collinear with EPA Margin
# (documented per-weight) to avoid double-counting the same signal twice.
#
# "strength" = 0.5 * z(point_diff_per_g) + 0.5 * z(epa_margin), the two
# most predictive-but-mutually-correlated stats collapsed into one input.
# ---------------------------------------------------------------------------
WEIGHTS = {
    "strength": 1.00,       # point_diff + epa_margin, combined 50/50
    "turnover": 0.55,       # ~40% overlaps with EPA -- most independent axis after strength
    "explosive": 0.35,      # ~50% overlaps with EPA
    "cpoe": 0.30,           # ~43% overlaps with offensive EPA -- distinct QB-accuracy signal
    "ypp": 0.30,            # 88% collinear with EPA margin -- heavily discounted
    "redzone": 0.28,        # ~38% overlaps with EPA
    "third_down": 0.25,     # ~80% overlaps with EPA -- heavily discounted
    "sack_protect": 0.22,   # ~28% overlaps with EPA
    "ball_security": 0.22,  # ~18% overlaps with EPA -- mostly independent
    # Standalone off/def EPA are intentionally 0: already inside "strength"
    # via epa_margin. Compute and display them for transparency; never add
    # them into the logit a second time.
    "off_epa_standalone": 0.0,
    "def_epa_standalone": 0.0,
}

# ---------------------------------------------------------------------------
# UNIFIED MARGIN MODEL
#
# Both the win probability and the projected score now come from the SAME
# number: a predicted point margin, derived from the combined 10-stat
# composite (which already includes point_diff_per_g -- i.e. the raw
# offense/defense scoring averages -- blended with EPA margin). There is
# no separate formula for "how likely to win" vs. "what's the score" --
# they cannot contradict each other because they're the same calculation.
#
# These three constants were FIT against real data, not assumed: 1,359
# real games, 2021-2025, regressing actual final-score margin against each
# matchup's composite-score difference (see
# scripts/backfill_correlations.py for the reproducible fit).
#
#   predicted_margin = MARGIN_SLOPE * composite_diff + home_field_points
#   win_prob_home = normal_cdf(predicted_margin / GAME_MARGIN_SIGMA)
#
# Sanity check against real sportsbook behavior (this is what confirmed the
# fit is right, not just that R^2 looked reasonable): a +3 point predicted
# margin implies a 60.0% win probability, matching how a real -3 favorite
# prices in the market almost exactly; +7 -> 72.2%; +10 -> 80.0%; +14 -> 88.0%.
# ---------------------------------------------------------------------------
MARGIN_SLOPE = 1.9363                # points per 1 composite z-unit of difference
HOME_FIELD_ADVANTAGE_POINTS = 2.08   # fit from real data; matches the well-known modern-NFL ~2 point home edge
NEUTRAL_SITE_ADVANTAGE_POINTS = 0.3  # small nominal-home-team edge for a neutral-site game (assumption, not fit -- too few neutral-site games in the sample to fit reliably)
GAME_MARGIN_SIGMA = 11.8933          # single-game "any given Sunday" noise, in points. This IS the regulation -- it isn't an arbitrary cap, it's literally how much of a single NFL game's outcome the combined stats can't explain (R^2 = 0.297 at the single-game level)

# Extra safety clamp on top of the statistical model above: even though the
# normal-CDF calibration above naturally keeps probabilities reasonable, we
# still hard-clamp as a final guardrail. 90/10 already implies the favorite
# should win 9 times out of 10 -- that's about as confident as any single
# NFL game prediction should ever claim to be.
MIN_WIN_PROB = 10.0
MAX_WIN_PROB = 90.0

# Games per regular season (used to convert season totals to per-game rates)
GAMES_PER_SEASON = 17

# Explosive play thresholds (yards), matching the convention used in the
# correlation research
EXPLOSIVE_RUN_YARDS = 10
EXPLOSIVE_PASS_YARDS = 15

# Red zone: opponent's 20-yard line or closer (yardline_100 <= 20)
REDZONE_YARDLINE_100 = 20
