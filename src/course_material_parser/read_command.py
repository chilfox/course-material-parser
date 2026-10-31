"""Entry point for the ``read`` CLI, which gives agents access to parsed material.

Stub only: subcommands are added by later implementation work. This module must never
import Docling, so reader startup stays fast.
"""

import argparse
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI with ``argv`` (default ``sys.argv[1:]``) and return the exit code."""
    parser = argparse.ArgumentParser(
        prog="read",
        description="Read parsed material stored under library_root.",
    )
    parser.parse_args(argv)
    return 0
