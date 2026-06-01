"""
export/cli.py
-------------
Argument-Parser für export_sqlite.py.
"""

import argparse
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Zoo Guide — SQLite Export")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Alle aktiven Zoos exportieren"
    )
    parser.add_argument(
        "--zoo",
        action="append",
        dest="zoos",
        metavar="SLUG",
        help="Zoo-Slug (z.B. zoo_berlin), wiederholbar"
    )
    args = parser.parse_args()

    if not args.all and not args.zoos:
        parser.print_help()
        sys.exit(1)

    return args
