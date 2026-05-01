"""Custom argparse parser and formatter for the mcp-tools-sql CLI.

Mirrors the help-infrastructure used by the `mcp_coder` CLI so the
`--help` UX is consistent across the related projects:

* :class:`HelpHintArgumentParser` — prints a "Try '<prog> --help' for
  more information." hint on parse errors and exits with code 2.
* :class:`WideHelpFormatter` — wider column alignment for `--help` output.
"""

from __future__ import annotations

import argparse
import sys
from typing import NoReturn


class HelpHintArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that points users at ``--help`` on parse errors.

    Subparsers created via :meth:`add_subparsers` automatically inherit
    this class, so the hint is emitted at every level of the CLI.
    """

    def error(self, message: str) -> NoReturn:
        """Print a usage error plus a help hint and exit with code 2."""
        self.print_usage(sys.stderr)
        sys.stderr.write(f"{self.prog}: error: {message}\n")
        sys.stderr.write(f"Try '{self.prog} --help' for more information.\n")
        sys.exit(2)


class WideHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Help formatter with a wider option column for nicer alignment."""

    def __init__(
        self,
        prog: str,
        indent_increment: int = 2,
        max_help_position: int = 32,
        width: int | None = None,
    ) -> None:
        super().__init__(
            prog,
            indent_increment=indent_increment,
            max_help_position=max_help_position,
            width=width,
        )
