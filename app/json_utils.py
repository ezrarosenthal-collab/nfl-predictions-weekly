"""
Shared, resilient JSON loading for the auto-generated data files this
project passes between scripts (predictions, track record, player props).

Why this exists: several independent scheduled workflows write to the
same files, and a real, recurring failure mode is one of them getting
corrupted mid-collision (a leftover git merge-conflict marker, or an
empty file from manual recovery). Every script that reads one of these
files should treat "missing," "empty," and "corrupted" all the same way
-- skip/return None -- rather than crash. This was first built into
scripts/render_html.py and app/track_record.py; consolidated here so
every reader (including scripts/hourly_injury_check.py, which was still
using a raw json.load() and crashing on exactly this) gets the same
protection instead of needing the fix applied piecemeal, file by file,
after each new failure.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_json_safely(path: Path):
    """
    Loads a JSON file, treating "doesn't exist," "empty," and "corrupted/
    unparseable" all the same way: return None rather than raise. Callers
    should treat None as "no data available yet" and continue, not as an
    error to propagate.
    """
    if not path.exists():
        return None
    try:
        content = path.read_text()
        if not content.strip():
            logger.warning("%s exists but is empty -- treating as no data yet.", path)
            return None
        return json.loads(content)
    except json.JSONDecodeError:
        logger.warning(
            "%s exists but isn't valid JSON (corrupted?) -- treating as no data "
            "yet rather than crashing. It will be regenerated the next time its "
            "own workflow runs successfully.", path
        )
        return None
