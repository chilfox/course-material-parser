"""CLI seam: every command the skill instructions give agents matches the implemented CLIs.

Agents copy these commands as written, so a renamed or removed flag must fail here rather
than in an agent's session.
"""

import re
import shlex
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
INSTRUCTIONS = [SKILL_DIR / "SKILL.md", *sorted((SKILL_DIR / "references").glob("*.md"))]
COMMAND = re.compile(r"uv run --project <skill-dir> (parse|read) ([^`\n]+)")

# Each placeholder becomes a value the CLI accepts syntactically; the library is empty, so
# a documented command fails only on what it refers to, never on its usage.
PLACEHOLDERS = {
    "MATERIAL": "course/book",
    "PATH": "missing.json",
    "TYPE": "textbook",
    "SPEC": "3",
    "ID": "1-1",
}


def documented_commands() -> list[tuple[str, list[str]]]:
    """Return ``(cli, argv)`` for every CLI command line in the skill instructions."""
    commands = []
    for path in INSTRUCTIONS:
        for cli, rest in COMMAND.findall(path.read_text()):
            argv = [PLACEHOLDERS.get(arg, arg) for arg in shlex.split(rest) if arg != "..."]
            commands.append((cli, argv))
    return commands


def test_the_instructions_document_every_workflow_command():
    documented = {(cli, argv[0]) for cli, argv in documented_commands() if argv}

    assert documented >= {
        ("parse", "start"),
        ("parse", "inspect"),
        ("parse", "propose"),
        ("parse", "finalize"),
        ("read", "list"),
        ("read", "toc"),
        ("read", "get"),
        ("read", "render"),
    }


@pytest.mark.parametrize(
    ("cli", "argv"),
    [command for command in documented_commands() if command[1]],
    ids=lambda value: " ".join(value) if isinstance(value, list) else value,
)
def test_a_documented_command_is_valid_usage(request, cli, argv):
    result = request.getfixturevalue(f"run_{cli}")(*argv)

    if result.exit_code != 0:
        assert result.error["error"] != "invalid_request", result.error["message"]
