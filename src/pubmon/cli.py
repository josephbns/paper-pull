"""Public discovery and local review commands; keys are read only from the environment."""

import argparse
import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from pubmon.config import load_config
from pubmon.decisions import import_decisions
from pubmon.pipeline import run
from pubmon.sources.common import LaneFailed
from pubmon.sources.openalex import lookup_institutions
from pubmon.store import Store

logger = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pubmon", description="Publication monitor")
    parser.add_argument("--version", action="version", version="pubmon 0.1.0")
    parser.add_argument("--project-dir", default=".", help="Project directory containing config/")
    commands = parser.add_subparsers(dest="command")
    lookup = commands.add_parser("resolve-institutions", help="List public institution candidates")
    lookup.add_argument("names", nargs="+")
    execute = commands.add_parser("run", help="Fetch, reconcile and export one row per paper")
    for option in ("dry-run", "backfill", "xlsx"):
        execute.add_argument("--" + option, action="store_true")
    master = execute.add_mutually_exclusive_group()
    master.add_argument("--no-master", action="store_true")
    master.add_argument("--master", type=Path)
    execute.add_argument(
        "--fixtures", type=Path, help="Explicit offline replay directory; never calls APIs"
    )
    decisions = commands.add_parser("import-decisions", help="Import a locally reviewed CSV")
    decisions.add_argument("path", type=Path)
    decisions.add_argument(
        "--demo", action="store_true", help="Use isolated synthetic replay history"
    )
    status = commands.add_parser("status", help="Show the last ten runs")
    status.add_argument("--demo", action="store_true", help="Use isolated synthetic replay history")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch commands and return a nonzero status for failed or partial collection."""
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    run_id = datetime.now(UTC).isoformat()
    try:
        return _dispatch(args)
    except (LaneFailed, ValueError, OSError) as exc:
        logger.error("[run_id=%s] %s", run_id, exc)
        return 1
    except Exception as exc:  # noqa: BLE001 - avoid leaking request URLs in unexpected CLI errors
        logger.error("[run_id=%s] Command failed: %s", run_id, type(exc).__name__)
        return 1


def _dispatch(args: argparse.Namespace) -> int:
    settings = load_config(args.project_dir)
    root = settings.project_dir
    if args.command == "resolve-institutions":
        _lookup(lookup_institutions(settings, args.names))
        return 0
    if args.command == "run":
        result = run(
            settings,
            master_path=root / args.master if args.master else None,
            no_master=args.no_master,
            dry_run=args.dry_run,
            backfill=args.backfill,
            xlsx=args.xlsx,
            fixtures=root / args.fixtures if args.fixtures else None,
        )
        print(json.dumps(result))
        return 2 if result["status"] == "partial" else 0
    database = (root / "demo" if args.demo else root) / "data/pubmon.db"
    if not database.exists():
        if args.command == "status":
            print("[]")
            return 0
        raise ValueError("No history database exists; run collection before importing decisions")
    with Store(database) as store:
        if args.command == "status":
            print(json.dumps(store.list_runs()))
        else:
            result = import_decisions(
                root / args.path, store, decided_at=datetime.now(UTC).isoformat()
            )
            print(json.dumps(result))
            return 2 if result["invalid"] else 0
    return 0


def _lookup(rows: list[dict]) -> None:
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
