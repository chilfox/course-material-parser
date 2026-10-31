import subprocess
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("command", ["parse", "read"])
def test_cli_help_runs_from_an_unrelated_working_directory(command, tmp_path):
    result = subprocess.run(
        ["uv", "run", "--project", str(SKILL_DIR), command, "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith(f"usage: {command}")
