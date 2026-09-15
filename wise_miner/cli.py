"""Command-line interface for WISE/NEOWISE Asteroid Miner."""

from __future__ import annotations

import argparse

from . import __project_name__, __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the lightweight CLI parser without importing scientific modules."""
    parser = argparse.ArgumentParser(
        prog="wise-neowise-miner",
        description=(
            "Back-search WISE/NEOWISE data and run conservative archival "
            "screening for an MPC asteroid designation."
        ),
    )
    parser.add_argument(
        "config",
        nargs="?",
        default="target.example.toml",
        help="Target TOML configuration file (default: target.example.toml).",
    )
    parser.add_argument(
        "--coverage-only",
        action="store_true",
        help="Stop after MPC + MOST coverage lookup.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{__project_name__} {__version__}",
    )
    return parser


def main() -> None:
    """Parse arguments, load configuration, and execute the pipeline."""
    args = build_parser().parse_args()

    # Import the scientific stack only after argparse handles --help/--version.
    # This keeps those lightweight commands usable even in a partial install.
    from .config import load_config
    from .pipeline import run_pipeline

    cfg = load_config(args.config)
    run_pipeline(cfg, coverage_only=args.coverage_only)
