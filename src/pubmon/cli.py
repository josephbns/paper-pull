"""Command entry point for public institution lookup and development help."""

import argparse
import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from pubmon.config import load_config
from pubmon.sources.common import LaneFailed
from pubmon.sources.openalex import lookup_institutions

logger = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    """Run implemented commands; fetching the full paper pipeline comes later."""
    parser = argparse.ArgumentParser(prog="pubmon", description="Publication monitor")
    parser.add_argument("--version", action="version", version="pubmon 0.1.0")
    parser.add_argument("--project-dir", default=".", help="Project directory containing config/")
    commands = parser.add_subparsers(dest="command")
    lookup = commands.add_parser("resolve-institutions", help="List public institution candidates")
    lookup.add_argument("names", nargs="+")
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    run_id = datetime.now(UTC).isoformat()
    try:
        settings = load_config(args.project_dir)
        rows = lookup_institutions(settings, args.names)
    except (LaneFailed, ValueError, OSError) as exc:
        logger.error("[run_id=%s] %s", run_id, exc)
        return 1
    print("id\tname\tROR\tcountry\tworks_count\tlineage")
    for row in rows:
        cells = [
            row.get(key)
            for key in ("id", "display_name", "ror", "country_code", "works_count", "lineage")
        ]
        print(
            "\t".join(
                str(cell if cell is not None else "").replace("\t", " ").replace("\n", " ")
                for cell in cells
            )
        )
    return 0
