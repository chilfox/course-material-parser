"""Shared CLI output: compact JSON results, the error envelope, and a JSON-erroring parser.

Every failure reaches the caller the same way: empty stdout, one JSON object
``{error, message, ...}`` on stderr, and exit code 1. Usage errors are ``invalid_request``
and unexpected exceptions are ``internal_error``.
"""

import argparse
import json
import sys
from collections.abc import Callable
from typing import Any, NoReturn


class CliError(Exception):
    """A failure to report in the error envelope.

    Args:
        code: The machine-readable error code, for example ``not_found``.
        message: What is wrong and what kind of fix is needed.
        **details: Extra facts the caller can't work out itself, added to the envelope.
    """

    def __init__(self, code: str, message: str, **details: Any) -> None:
        """Create the error with its envelope fields."""
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def envelope(self) -> dict[str, Any]:
        """Return the JSON object written to stderr."""
        return {"error": self.code, "message": self.message, **self.details}


class JsonArgumentParser(argparse.ArgumentParser):
    """An argument parser whose usage errors raise ``CliError('invalid_request')``.

    Subparsers created from it share the class, so their usage errors behave the same.
    """

    def error(self, message: str) -> NoReturn:
        """Raise the usage error as ``invalid_request`` instead of printing usage text."""
        raise CliError("invalid_request", f"{self.prog}: {message}")


def to_json(value: Any) -> str:
    """Return ``value`` as compact one-line JSON."""
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def json_line(value: Any) -> str:
    """Return ``value`` as one compact JSON line, ready to print as a command's output."""
    return to_json(value) + "\n"


def run_cli(command: Callable[[], str]) -> int:
    """Run ``command`` and return the process exit code.

    ``command`` returns the complete stdout text on success, so nothing reaches stdout
    when it fails part way. ``--help`` exits early through ``SystemExit``, whose code is
    returned as is. Any other exception becomes ``internal_error``, so callers never
    have to parse a traceback.
    """
    try:
        output = command()
    except SystemExit as exit_request:
        return exit_request.code if isinstance(exit_request.code, int) else 0
    except Exception as unexpected:
        error = (
            unexpected
            if isinstance(unexpected, CliError)
            else CliError("internal_error", f"{type(unexpected).__name__}: {unexpected}")
        )
        sys.stderr.write(json_line(error.envelope()))
        return 1
    sys.stdout.write(output)
    return 0
