"""
Grades all available predictions against real final scores and saves the
updated track record. Safe to run as often as needed -- it always rebuilds
the full record from scratch (see app/track_record.py for why that's
intentional), so running it multiple times a day never double-counts.

Usage:
    python scripts/grade_predictions.py --season 2026
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.track_record import save_track_record  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    args = parser.parse_args()

    out_path = save_track_record(args.season)
    print(f"[grade_predictions] Wrote {out_path}")


if __name__ == "__main__":
    main()
