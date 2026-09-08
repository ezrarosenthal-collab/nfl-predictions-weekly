import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.injury_watch import CONCERNING_STATUSES, get_qb_injury_alert, get_team_injury_report  # noqa: E402

FAKE_INJURIES = pd.DataFrame([
    {"season": 2026, "team": "PHI", "week": 1, "position": "QB", "full_name": "Tanner McKee",
     "report_status": "Out", "report_primary_injury": "Thumb", "report_secondary_injury": None},
    {"season": 2026, "team": "PIT", "week": 1, "position": "QB", "full_name": "Skylar Thompson",
     "report_status": "Questionable", "report_primary_injury": "Hamstring", "report_secondary_injury": None},
    {"season": 2026, "team": "GB", "week": 1, "position": "QB", "full_name": "Jordan Love",
     "report_status": None, "report_primary_injury": None, "report_secondary_injury": None},
])


def test_flags_concerning_status_for_matching_starter():
    with patch("app.injury_watch.fetch_injuries", return_value=FAKE_INJURIES):
        alert = get_qb_injury_alert("PHI", "Tanner McKee", 2026, 1)
    assert alert is not None
    assert "Out" in alert
    assert "Thumb" in alert


def test_no_alert_when_starter_has_no_report_status():
    """Jordan Love appears on the report (practice-only note) but has no
    official report_status -- that's not concerning enough to flag."""
    with patch("app.injury_watch.fetch_injuries", return_value=FAKE_INJURIES):
        alert = get_qb_injury_alert("GB", "Jordan Love", 2026, 1)
    assert alert is None


def test_no_alert_when_starter_not_on_report_at_all():
    with patch("app.injury_watch.fetch_injuries", return_value=FAKE_INJURIES):
        alert = get_qb_injury_alert("KC", "Patrick Mahomes", 2026, 1)
    assert alert is None


def test_no_alert_when_backup_flagged_but_starter_is_fine():
    """Regression guard: matching must be by the SPECIFIC starter's name,
    not 'any QB entry for this team' -- a real bug caught in the ESPN
    version of this module before it ever shipped."""
    with patch("app.injury_watch.fetch_injuries", return_value=FAKE_INJURIES):
        alert = get_qb_injury_alert("PIT", "Aaron Rodgers", 2026, 1)  # a different, healthy PIT QB
    assert alert is None


def test_fetch_failure_returns_none_not_an_exception():
    with patch("app.injury_watch.fetch_injuries", side_effect=Exception("network down")):
        alert = get_qb_injury_alert("KC", "Patrick Mahomes", 2026, 1)
    assert alert is None


def test_empty_starter_name_returns_none():
    alert = get_qb_injury_alert("KC", "", 2026, 1)
    assert alert is None


def test_concerning_statuses_are_lowercase_for_case_insensitive_matching():
    assert all(s == s.lower() for s in CONCERNING_STATUSES)


def test_team_injury_report_includes_all_positions_not_just_qb():
    multi_position = pd.concat([FAKE_INJURIES, pd.DataFrame([
        {"season": 2026, "team": "PHI", "week": 1, "position": "WR", "full_name": "Test Receiver",
         "report_status": "Doubtful", "report_primary_injury": "Ankle", "report_secondary_injury": None},
        {"season": 2026, "team": "PHI", "week": 1, "position": "OT", "full_name": "Test Tackle",
         "report_status": "Out", "report_primary_injury": "Knee", "report_secondary_injury": None},
    ])], ignore_index=True)
    with patch("app.injury_watch.fetch_injuries", return_value=multi_position):
        alerts = get_team_injury_report("PHI", 2026, 1)
    assert len(alerts) == 3  # McKee (QB) + Receiver (WR) + Tackle (OT)
    assert any("WR" in a for a in alerts)
    assert any("OT" in a for a in alerts)


def test_team_injury_report_excludes_non_concerning_statuses():
    with patch("app.injury_watch.fetch_injuries", return_value=FAKE_INJURIES):
        alerts = get_team_injury_report("GB", 2026, 1)  # Jordan Love has no report_status
    assert alerts == []


def test_team_injury_report_fetch_failure_returns_empty_list():
    with patch("app.injury_watch.fetch_injuries", side_effect=Exception("network down")):
        alerts = get_team_injury_report("KC", 2026, 1)
    assert alerts == []
