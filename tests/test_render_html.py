import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.render_html import _load_json_safely  # noqa: E402


def test_missing_file_returns_none(tmp_path):
    assert _load_json_safely(tmp_path / "does_not_exist.json") is None


def test_empty_file_returns_none_not_a_crash(tmp_path):
    """
    Regression test for a real production incident: manually emptying a
    corrupted auto-generated file (the standard recovery step for a git
    collision) left a 0-byte file, which crashed the entire site
    regeneration because json.load() can't parse an empty string. This
    must degrade gracefully instead.
    """
    p = tmp_path / "track_record_2026.json"
    p.write_text("")
    assert _load_json_safely(p) is None


def test_whitespace_only_file_returns_none(tmp_path):
    p = tmp_path / "track_record_2026.json"
    p.write_text("   \n  \n")
    assert _load_json_safely(p) is None


def test_corrupted_conflict_marker_file_returns_none_not_a_crash(tmp_path):
    """The exact real corruption pattern seen in production: leftover git
    merge-conflict markers committed directly into a JSON file."""
    p = tmp_path / "track_record_2026.json"
    p.write_text('{\n  "overall": {"correct": 1, "total": 1},\n<<<<<<< HEAD\n}')
    assert _load_json_safely(p) is None


def test_valid_json_loads_normally(tmp_path):
    p = tmp_path / "track_record_2026.json"
    p.write_text('{"overall": {"correct": 5, "total": 8}}')
    result = _load_json_safely(p)
    assert result == {"overall": {"correct": 5, "total": 8}}
