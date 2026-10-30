"""What the command line does when it cannot keep its promise.

G4 says a run that cannot establish isolation exits non-zero and says so.
The check command is the one a user runs to find out whether they are
protected, so a check that cannot answer must never look like a pass.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _run(args, path):
    env = dict(os.environ)
    env["PATH"] = str(path)
    env.pop("PYTHONPATH", None)
    return subprocess.run(
        [sys.executable, "-m", "never_leaves"] + args,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
    )


def test_check_exits_two_when_unshare_is_missing(tmp_path):
    empty = tmp_path / "empty-path"
    empty.mkdir()

    result = _run(["check"], empty)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "unshare" in result.stderr
    assert "not found" in result.stderr


def test_the_missing_tool_is_named_on_stderr_not_stdout(tmp_path):
    empty = tmp_path / "empty-path"
    empty.mkdir()

    result = _run(["check"], empty)

    assert "unshare" not in result.stdout
