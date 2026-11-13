"""Public discovery and local review commands; keys are read only from the environment."""

import argparse
import json
import logging
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values

from pubmon.backtest import run_backtest
from pubmon.config import Settings, load_config
from pubmon.decisions import import_decisions
from pubmon.pipeline import run
from pubmon.profile import available_profiles, load_profile
from pubmon.sources.common import LaneFailed
from pubmon.sources.openalex import lookup_institutions
from pubmon.store import Store

logger = logging.getLogger(__name__)

PROFILE_HELP = "Profile name from profiles/ (or set PUBMON_PROFILE), e.g. cleveland-clinic"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pubmon", description="Publication monitor")
    parser.add_argument("--version", action="version", version="pubmon 0.1.0")
    parser.add_argument("--project-dir", default=".", help="Project directory containing config/")
    parser.add_argument("--profile", help=PROFILE_HELP)
    # SUPPRESS lets `pubmon run --profile X` and `pubmon --profile X run` both work.
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--profile", default=argparse.SUPPRESS, help=PROFILE_HELP)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser(
        "check-profile",
        parents=[shared],
        help="Check a profile and print what it will search for, without calling any API",
    )
    lookup = commands.add_parser(
        "resolve-institutions", parents=[shared], help="List public institution candidates"
    )
    lookup.add_argument("names", nargs="*", help="Defaults to the profile partner and IBM names")
    execute = commands.add_parser(
        "run", parents=[shared], help="Fetch, reconcile and export one row per paper"
    )
    for option in ("dry-run", "backfill", "xlsx"):
        execute.add_argument("--" + option, action="store_true")
    master = execute.add_mutually_exclusive_group()
    master.add_argument("--no-master", action="store_true")
    master.add_argument("--master", type=Path)
    execute.add_argument(
        "--fixtures", type=Path, help="Explicit offline replay directory; never calls APIs"
    )
    decisions = commands.add_parser(
        "import-decisions", parents=[shared], help="Import a locally reviewed CSV"
    )
    decisions.add_argument("path", type=Path)
    decisions.add_argument(
        "--demo", action="store_true", help="Use isolated synthetic replay history"
    )
    status = commands.add_parser("status", parents=[shared], help="Show the last ten runs")
    status.add_argument("--demo", action="store_true", help="Use isolated synthetic replay history")
    backtest = commands.add_parser(
        "backtest", parents=[shared], help="Compare stored history with the master, read-only"
    )
    backtest.add_argument("--master", type=Path, required=True)
    backtest.add_argument(
        "--since", default="2023-01-01", help="Inclusive publication cutoff (YYYY-MM-DD)"
    )
    backtest.add_argument(
        "--demo", action="store_true", help="Use isolated synthetic replay history"
    )
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


def load_settings(project_dir: str, profile: str | None) -> Settings:
    """Use the named profile, else an existing local settings.toml, else stop with help.

    There is deliberately no silent default: running another QIC's criteria by accident
    would produce plausible-looking but wrong results.
    """
    saved = dotenv_values(Path(project_dir) / ".env", interpolate=False).get("PUBMON_PROFILE")
    name = profile or os.environ.get("PUBMON_PROFILE") or saved
    if name:
        return load_profile(project_dir, name)
    if (Path(project_dir) / "config/settings.toml").exists():
        logger.warning("Using older config/settings.toml; new setups use --profile <name>")
        return load_config(project_dir)
    names = ", ".join(available_profiles(project_dir)) or "none yet; see docs/SETUP.md"
    raise ValueError(f"Choose a profile with --profile <name>. Available: {names}")


def _dispatch(args: argparse.Namespace) -> int:
    settings = load_settings(args.project_dir, getattr(args, "profile", None))
    root = settings.project_dir
    if args.command == "check-profile":
        print(json.dumps(profile_summary(settings), indent=2, ensure_ascii=False))
        return 0
    if args.command == "resolve-institutions":
        _lookup(
            lookup_institutions(settings, args.names or [settings.partner_name, settings.ibm_name])
        )
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
    state_root = settings.workspace_dir or root
    state_root = state_root / "demo" if args.demo else state_root
    database = state_root / "data/pubmon.db"
    if args.command == "backtest":
        print(
            json.dumps(
                run_backtest(database, root / args.master, state_root / "out", since=args.since)
            )
        )
        return 0
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


def profile_summary(settings: Settings) -> dict:
    """Describe what a profile will do, so a new user can check it before any API call."""
    people = settings.watchlist or ()
    names = {
        side: sorted({p.name for p in people if p.side == side}) for side in ("IBM", "PARTNER")
    }
    return {
        "profile": settings.profile_name or "config/settings.toml (older format)",
        "partner": f"{settings.partner_name} ({settings.partner_label})",
        "start_date": settings.start_date,
        "workspace": str(settings.workspace_dir),
        "openalex_ibm_ids": list(settings.ibm_institution_ids),
        "openalex_partner_ids": list(settings.partner_institution_ids),
        "partner_people": len(names["PARTNER"]),
        "ibm_people": len(names["IBM"]),
        "backup_tab_people": list(settings.backup_names),
        "topic_terms": list(settings.tag_terms),
        "broad_terms": list(settings.broad_terms),
        "hardware_terms": list(settings.hardware_terms),
        "master_path_set": settings.master_path is not None,
        "api_key_set": bool(settings.openalex_api_key),
        "contact_email_set": bool(settings.email),
        "arxiv_query": settings.read_arxiv_query(),
    }


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
