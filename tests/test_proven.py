"""A report describes. A proof establishes.

`check --json` says `proven` true only when the tables were read and the
process is the one that was launched into the namespace, so a caller can
gate on it without parsing prose. These tests run the real command.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from never_leaves import isolation

ROOT = Path(__file__).parent.parent


def _json_from(stdout: str) -> dict:
    return json.loads(stdout[stdout.index("{") :])


def _run(args, env=None):
    return subprocess.run(
        [sys.executable, "-m", "never_leaves"] + args,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
    )


def test_check_json_is_proven_inside_the_namespace():
    ok, why = isolation.supported()
    if not ok:
        pytest.skip("no namespace on this machine: %s" % why)

    result = _run(["check", "--json"])

    data = _json_from(result.stdout)
    assert data["isolated"] is True
    assert data["kernel_namespace"] is True
    assert data["proven"] is True
    assert result.returncode == 0


def test_check_json_is_not_proven_when_the_namespace_is_not_entered(tmp_path):
    empty = tmp_path / "empty-path"
    empty.mkdir()
    env = dict(os.environ)
    env["PATH"] = str(empty)
    env.pop("PYTHONPATH", None)

    result = _run(["check", "--no-isolate", "--json"], env=env)

    data = _json_from(result.stdout)
    assert data["proven"] is False
    assert data["isolated"] is False
    assert "proven" in data
