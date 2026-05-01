"""verify subcommand."""

from __future__ import annotations

import argparse


def add_subparser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register `verify` subparser (no subcommand-level flags; uses top-level)."""
    subparsers.add_parser("verify", help="Validate configuration and exit.")


def run(args: argparse.Namespace) -> int:
    """Entry point. Returns process exit code."""
    raise NotImplementedError("verify: implemented in steps 5-9")
