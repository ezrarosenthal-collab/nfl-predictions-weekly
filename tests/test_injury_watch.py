import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.injury_watch import CONCERNING_STATUSES, fetch_team_injuries, get_qb_injury_alert  # noqa: E402

FAKE_ESPN_RESPONSE = {
    "team": {
        "injuries": [
            {
                "athlete": {"displayName": "Test Quarterback", "position": {"abbreviation": "QB"}},
                "status": "Questionable",
                "details": {"detail": "Ankle"},
            },
            {
                "athlete": {"displayName": "Test Receiver", "position": {"abbreviation": "WR"}},
                "status": "Out",
                "details": {"detail": "Hamstring"},
            },
        ]
    }
}


def _mock_response(json_data, status_ok=True):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock() if status_ok else MagicMock(side_effect=Exception("HTTP error"))
    return resp


def test_fetch_team_injuries_parses_expected_shape():
    with patch("app.injury_watch.requests.get", return_value=_mock_response(FAKE_ESPN_RESPONSE)):
        injuries = fetch_team_injuries("KC")
    assert len(injuries) == 2
    qb_entry = next(i for i in injuries if i["position"] == "QB")
    assert qb_entry["name"] == "Test Quarterback"
    assert qb_entry["status"] == "Questionable"
    assert qb_entry["detail"] == "Ankle"


def test_fetch_team_injuries_returns_empty_list_on_bad_response_shape():
    """Never crash the hourly job -- an unrecognized shape returns [] with a logged warning, not an exception."""
    with patch("app.injury_watch.requests.get", return_value=_mock_response({"something_unexpected": True})):
        injuries = fetch_team_injuries("KC")
    assert injuries == []


def test_fetch_team_injuries_returns_empty_list_on_network_failure():
    with patch("app.injury_watch.requests.get", side_effect=Exception("network down")):
        injuries = fetch_team_injuries("KC")
    assert injuries == []


def test_fetch_team_injuries_unknown_team_returns_empty_list():
    injuries = fetch_team_injuries("ZZZ")  # not a real team code
    assert injuries == []


def test_get_qb_injury_alert_flags_concerning_status():
    with patch("app.injury_watch.requests.get", return_value=_mock_response(FAKE_ESPN_RESPONSE)):
        alert = get_qb_injury_alert("KC", "Test Quarterback")
    assert alert is not None
    assert "Questionable" in alert
    assert "Ankle" in alert


def test_get_qb_injury_alert_none_when_starter_not_on_report():
    with patch("app.injury_watch.requests.get", return_value=_mock_response(FAKE_ESPN_RESPONSE)):
        alert = get_qb_injury_alert("KC", "Someone Else Entirely")
    assert alert is None


def test_concerning_statuses_are_lowercase_for_case_insensitive_matching():
    assert all(s == s.lower() for s in CONCERNING_STATUSES)
