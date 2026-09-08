# DailyPredictionNFL — Backend

Python backend for the NFL prediction model. Mirrors the validated methodology
built and manually verified in the prototype phase:

- 10 stats selected by real correlation analysis against 5 years of outcomes
  (2021–2025, 160 team-seasons, computed from actual play-by-play — not
  assumption).
- A weighted composite model (`app/model.py`) — same weights, same formula,
  same calibration as the version already checked against the Week 1 2026
  slate. **Every prediction is capped between 10% and 90%** — no matter how
  lopsided a matchup's stats are, the model never claims more single-game
  certainty than that. "Any given Sunday" is a real phenomenon in the NFL;
  a model that outputs 96% or 98% for any single game is overconfident
  about a sport with this much inherent variance (see `config.py`:
  `MIN_WIN_PROB` / `MAX_WIN_PROB`).
- **Win probability and the projected score are the same calculation, not
  two.** Earlier versions computed them independently, which could (and
  did) produce a real contradiction: a team shown with a *higher* win
  probability but a *lower* projected score. Fixed by fitting a single
  "predicted margin" (in real points) from the combined 10-stat composite
  against 1,359 actual NFL games (2021-2025), then deriving both outputs
  from that one margin. The fit was sanity-checked against real sportsbook
  behavior: a +3 point predicted margin implies ~60% win probability,
  matching how an actual -3 favorite prices in the market. See `config.py`
  (`MARGIN_SLOPE`, `HOME_FIELD_ADVANTAGE_POINTS`, `GAME_MARGIN_SIGMA`) and
  `scripts/backfill_correlations.py` for the reproducible fit.
- An **overrides layer** (`app/overrides.py` + `data/overrides.json`) that is
  the single most important thing this project learned in the prototype
  phase: trailing full-season stats are blind to Week 1 QB changes, injuries,
  and trades. About half of a typical Week 1 slate needs a manual or
  semi-automated correction on top of the pure stat model.

## Project layout

```
nfl_backend/
  config.py                 League constants, model weights, calibration
  app/
    data_pipeline.py        Pulls play-by-play + schedule from nflverse
    features.py             Turns raw play-by-play into team-season stats
    model.py                Scoring, win probability, feature breakdown
    odds.py                 Market line fetching + fair-odds conversion
    overrides.py            Manual context layer (QB changes, trades, injuries)
    api.py                  FastAPI app — serves predictions to the frontend
  data/
    overrides.json          Editable file — this is what a human updates weekly
  scripts/
    generate_predictions.py Weekly orchestration: pipeline → features → model → JSON
    backfill_correlations.py Reproduces the 5-year stat-validation research
  tests/
    test_model.py
```

## Setup

```bash
pip install -r requirements.txt
```

## Weekly run

```bash
python scripts/generate_predictions.py --season 2026 --week 1
```

This writes `data/predictions_2026_wk1.json` in the exact shape the React
frontend already consumes (`TEAM_STATS`-style per-team blocks + a `GAMES`
array with model probabilities, market lines, and — where present in
`overrides.json` — a `finalOverride` and human-readable `context` string).

## Serving the API

```bash
uvicorn app.api:app --reload
```

Endpoints:
- `GET /predictions?season=2026&week=1` — full slate, same shape as the JSON file
- `GET /predictions/{season}/{week}/{away}/{home}` — single game, full detail
- `GET /explain` — the model's weights and the research behind them

## The overrides file is the important part

`data/overrides.json` is a small, human-edited file. Every week, before
publishing predictions, someone (or an automated injury-report scraper —
see `TODO` in `app/overrides.py`) should check it against real news for any
game where the pure model's win probability looks extreme. The pattern from
Week 1 2026: teams with a new starting QB, a key trade, or a starter who
missed significant time to injury the previous season need a manual
`final_override_home_wp` and a `context` string, or the model will
confidently give a number that's wrong for a reason a human would catch in
five minutes.

## Automation: the free, fully-working part

`.github/workflows/weekly_update.yml` runs the entire pipeline every Tuesday
at 13:00 UTC (a few hours after Monday Night Football ends) via **GitHub
Actions**, which is free for public repos with no time limit. It:

1. Auto-detects the current week from the real schedule (`app/schedule.py`)
   — Week 1 becomes Week 2 becomes Week 3 automatically; nobody edits a
   config number each week.
2. Re-runs the full stats pipeline against nflverse's latest play-by-play.
3. Runs an **automated QB-change detector** (`app/qb_watch.py`) that
   compares each team's most recent starting QB (by pass attempts) against
   who started earlier in the season, and flags a note on the page when
   they differ.
4. Renders the updated static site (`scripts/render_html.py`) and commits
   it to `docs/`, which GitHub Pages serves automatically.

Enable it once: push this repo to GitHub, then Settings → Pages → Source →
`main` branch, `/docs` folder. From then on the site updates itself,
completely free, forever, with zero further action.

### What the QB-change detector actually catches (validated against real data)

Tested against real 2025 in-season data, heading into Week 15, it correctly
flagged (among others): **IND** switching from Daniel Jones to Riley
Leonard (the Achilles injury), and **CIN** switching to a healthy Joe
Burrow from Jacoby Flacco — exactly the class of change that required
manual research for Week 1 2026. This part is real and free.

### What it honestly can't catch — and why that's a hard limit, not a bug

The Week 1 2026 research also required things no free, code-only detector
can see:
- **A trade** that changes a team's roster without changing who's at QB
  (Myles Garrett to the Rams, A.J. Brown to the Patriots) — the play-by-play
  won't reflect it until the new player has actually played, which for a
  season-opener preview is too late by definition.
- **A coaching change's** scheme impact, before any games exist to measure it.
- **An injury that hasn't happened yet.**

Catching those requires either a human doing the same kind of research we
did for Week 1, or a scheduled step that has an LLM read that week's NFL
news and produce `data/overrides.json` entries automatically — which is a
real, buildable next step, but has a genuine ongoing API cost (unlike
everything else in this repo, which is free). If you want that wired up,
say so and it's a small addition to the same workflow file.

## Hourly QB injury check (`.github/workflows/hourly_injury_check.yml`)

Runs every hour, for free, and closes part of the gap described above: an
**injury that hasn't happened yet** at Tuesday's weekly run can happen by
Wednesday, and this catches it without waiting a full week.

**This went through a real pivot worth knowing about.** The first version
used ESPN's free, unofficial public API, written defensively and tested
against a simulated response. The very first live run — on GitHub Actions'
real servers, with real internet access — came back `403 Forbidden` on
every single request. That's not a code bug; ESPN's anti-bot protection
blocks well-known automation IP ranges (GitHub Actions, AWS, etc.)
outright, no matter what headers are sent. Fighting that with retries or
different headers wouldn't have helped — it's a wall, not a bug.

**What it uses now:** nflverse's official injury reports — the same
trusted open-data project already powering the rest of this backend
(play-by-play, schedules), sourced directly from the NFL's own weekly
injury report data (`report_status`: Out / Doubtful / Questionable),
delivered as a plain GitHub release download — the exact same reliable
mechanism already proven to work for every other data source in this
project. This was verified against real historical data before shipping:
querying the real 2025 Week 1 report correctly returned Tanner McKee
(Out, Thumb) and Skylar Thompson (Questionable, Hamstring), and correctly
returned nothing for a healthy Patrick Mahomes.

**Real limits, stated plainly:**
- This only catches injuries to the QB *already listed* in `qb_meta.py`.
  If a totally different, unlisted player suddenly starts, this has no way
  to know to look for them — `qb_meta.py` still needs occasional manual
  updates when a team's starter changes.
- Update cadence matches the NFL's own official injury report schedule
  (a few times a week during the season, not truly real-time) — checking
  hourly costs nothing extra, but don't expect an entry to appear the
  instant an injury happens on the field.
