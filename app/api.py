"""
FastAPI app serving predictions to the frontend.

Run with: uvicorn app.api:app --reload

Endpoints:
  GET /predictions?season=2026&week=1
      Full slate for a week, in the same shape the React dashboard consumes.
  GET /predictions/{season}/{week}/{away}/{home}
      Single game, full detail (feature breakdown, snapshot, bet info).
  GET /explain
      The model's research (10 stats + R^2) and weights, for the "why"
      panel in the UI.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import RESEARCH, REJECTED_STATS, WEIGHTS
from scripts.generate_predictions import build_week_predictions

app = FastAPI(title="DailyPredictionNFL API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten before shipping to production
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/predictions")
def get_predictions(season: int, week: int):
    try:
        return build_week_predictions(season, week)
    except Exception as exc:  # noqa: BLE001 -- surface a clean 500 with the real reason
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/predictions/{season}/{week}/{away}/{home}")
def get_single_game(season: int, week: int, away: str, home: str):
    slate = build_week_predictions(season, week)
    for game in slate["games"]:
        if game["away_team"] == away.upper() and game["home_team"] == home.upper():
            return game
    raise HTTPException(status_code=404, detail=f"{away} @ {home} not found in week {week} of {season}")


@app.get("/explain")
def explain():
    return {
        "research": RESEARCH,
        "rejected_stats": REJECTED_STATS,
        "weights": WEIGHTS,
        "methodology": (
            "10 stats selected by correlation against 5 years (2021-2025, "
            "160 team-seasons) of real outcomes computed from actual "
            "play-by-play. Weights set from R^2 magnitude, then manually "
            "discounted wherever a stat is heavily collinear with EPA "
            "Margin to avoid double-counting the same signal twice. "
            "See config.py and scripts/backfill_correlations.py."
        ),
    }


@app.get("/health")
def health():
    return {"status": "ok"}
