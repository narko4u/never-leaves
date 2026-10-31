"""When a run goes ahead without a namespace, it says so out loud.

An opt-out is not a quiet mode. The line begins NOT ISOLATED, names what
the process can still reach, and the report keeps isolated false so nothing
downstream can mistake the run for a protected one.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _run(args, env):
    return subprocess.run(
        [sys.executable, "-m", "never_leaves"] + args,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
    )


def _env_without_tools(tmp_path):
    empty = tmp_path / "empty-path"
    empty.mkdir()
    env = dict(os.environ)
    env["PATH"] = str(empty)
    env.pop("PYTHONPATH", None)
    return env


def test_no_isolate_prints_the_not_isolated_line(tmp_path):
    result = _run(["check", "--no-isolate"], _env_without_tools(tmp_path))

    lines = [line for line in result.stdout.splitlines() if line.startswith("NOT ISOLATED")]
    assert lines, result.stdout
    assert "reach" in lines[0] or "interface" in lines[0] or "socket" in lines[0]


def test_the_report_still_says_it_was_not_isolated(tmp_path):
    result = _run(["check", "--no-isolate", "--json"], _env_without_tools(tmp_path))

    data = json.loads(result.stdout[result.stdout.index("{") :])
    assert data["isolated"] is False
