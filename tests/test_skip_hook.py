"""The hook is proved by running a nested suite, not by reading its source.

Each case builds a throwaway directory with this repository's conftest and a
single test module, runs pytest there, and judges the exit status. A skip with
no reason must fail the run and name the test; a skip with a reason must pass.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).parent
CONFTEST = TESTS / "conftest.py"


def _run_a_nested_suite(tmp_path, body):
    (tmp_path / "conftest.py").write_text(CONFTEST.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "test_case.py").write_text(body, encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(tmp_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )


def test_a_reasonless_skip_fails_the_run(tmp_path):
    result = _run_a_nested_suite(
        tmp_path,
        "import pytest\n\n\ndef test_bad():\n    pytest.skip()\n",
    )

    assert result.returncode != 0, result.stdout
    assert "skipped without a reason" in result.stdout + result.stderr


def test_a_mark_skip_without_a_reason_fails_the_run(tmp_path):
    result = _run_a_nested_suite(
        tmp_path,
        "import pytest\n\n\n@pytest.mark.skip\ndef test_bad():\n    pass\n",
    )

    assert result.returncode != 0, result.stdout
    assert "skipped without a reason" in result.stdout + result.stderr


def test_a_skipif_without_a_reason_fails_the_run(tmp_path):
    result = _run_a_nested_suite(
        tmp_path,
        "import pytest\n\n\n@pytest.mark.skipif(True)\ndef test_bad():\n    pass\n",
    )

    assert result.returncode != 0, result.stdout


def test_a_skip_with_a_reason_is_left_alone(tmp_path):
    result = _run_a_nested_suite(
        tmp_path,
        "import pytest\n\n\ndef test_good():\n    pytest.skip(\"the kernel has no namespaces here\")\n",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 skipped" in result.stdout


def test_a_reason_of_only_space_is_not_a_reason(tmp_path):
    result = _run_a_nested_suite(
        tmp_path,
        "import pytest\n\n\ndef test_bad():\n    pytest.skip(\"   \")\n",
    )

    assert result.returncode != 0, result.stdout
