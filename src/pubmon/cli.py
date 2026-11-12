"""Command entry point; operational commands arrive in later milestones."""

import argparse
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Show available scaffold options without pretending the pipeline is implemented."""
    parser = argparse.ArgumentParser(
        prog="pubmon", description="Publication monitor — Milestone 1 development scaffold"
    )
    parser.add_argument("--version", action="version", version="pubmon 0.1.0")
    parser.parse_args(argv)
    parser.print_help()
    return 0
