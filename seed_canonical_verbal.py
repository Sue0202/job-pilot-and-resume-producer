#!/usr/bin/env python3
"""Idempotent canonical verbal seed utility.

Usage:
    python seed_canonical_verbal.py
    python seed_canonical_verbal.py --dry-run
"""

import argparse
import json
import sys
from pathlib import Path

import database as db

import canonical_verbal  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Seed canonical verbal outputs into jobpilot.db")
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not insert")
    parser.add_argument("--db", type=str, default="", help="Optional DB path override")
    args = parser.parse_args()

    if args.db:
        db.DB_PATH = Path(args.db)

    db.init_db()
    report = canonical_verbal.seed_canonical_verbal_outputs(dry_run=args.dry_run)

    print(json.dumps(report, indent=2))
    print(
        f"\nSummary: inserted={len(report['inserted'])}, "
        f"idempotent={len(report['skipped_idempotent'])}, "
        f"protected={len(report['skipped_user_protected'])}, "
        f"missing={len(report['skipped_missing'])}, "
        f"ambiguous={len(report['skipped_ambiguous'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
