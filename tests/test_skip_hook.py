"""The hook is proved by running nested suites, not by reading its source.

Each case builds a throwaway directory with this repository's conftest and a
test module, runs pytest there, and judges the exit status and the report. The
last case runs one session holding both kinds, because a hook that failed
everything or nothing would pass the separate cases and still be useless.
"""

import subprocess
import sys
from pathlib import Path

TESTS = Path(__file__).parent
CONFTEST = TESTS / "conftest.py"


def _run_a_nested_suite(tmp_path, body):
    (tmp_path / "conftest.py").write_text(CONFTEST.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "test_case.py").write_text(body, encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rA", str(tmp_path)],
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


def test_a_string_condition_is_pytest_text_not_a_reason(tmp_path):
    """pytest uses the condition itself as the message; the author wrote none."""
    result = _run_a_nested_suite(
        tmp_path,
        "import pytest\n\n\n@pytest.mark.skipif(\"1 == 1\")\ndef test_bad():\n    pass\n",
    )

    assert result.returncode != 0, result.stdout
    assert "skipped without a reason" in result.stdout + result.stderr


def test_a_typed_reason_of_the_same_words_is_still_a_reason(tmp_path):
    """Authorship is the test, so the words pytest would invent count if typed."""
    result = _run_a_nested_suite(
        tmp_path,
        "import pytest\n\n\n@pytest.mark.skip(reason=\"unconditional skip\")\ndef test_good():\n    pass\n\n\ndef test_good_too():\n    pytest.skip(\"unconditional skip\")\n",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 skipped" in result.stdout


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


def test_one_session_holds_both_kinds(tmp_path):
    result = _run_a_nested_suite(
        tmp_path,
        "import pytest\n\n\ndef test_bad():\n    pytest.skip()\n\n\ndef test_good():\n    pytest.skip(\"the kernel has no namespaces here\")\n",
    )

    printed = result.stdout + result.stderr
    assert result.returncode != 0, printed
    assert "1 failed, 1 skipped" in printed
    assert "test_bad" in printed


def test_an_inactive_reasoned_mark_cannot_vouch_for_a_bare_skip(tmp_path):
    result = _run_a_nested_suite(
        tmp_path,
        "import pytest\n\n\n@pytest.mark.skipif(False, reason=\"only on windows\")\n@pytest.mark.skip\ndef test_bad():\n    pass\n",
    )

    assert result.returncode != 0, result.stdout
    assert "skipped without a reason" in result.stdout + result.stderr


def test_an_inactive_reasoned_mark_cannot_vouch_for_a_reasonless_skipif(tmp_path):
    result = _run_a_nested_suite(
        tmp_path,
        "import pytest\n\n\n@pytest.mark.skipif(False, reason=\"only on windows\")\n@pytest.mark.skipif(\"1 == 1\")\ndef test_bad():\n    pass\n",
    )

    assert result.returncode != 0, result.stdout
    assert "skipped without a reason" in result.stdout + result.stderr


def test_the_fired_reasoned_mark_still_counts(tmp_path):
    result = _run_a_nested_suite(
        tmp_path,
        "import pytest\n\n\n@pytest.mark.skipif(False, reason=\"only on windows\")\n@pytest.mark.skipif(\"1 == 1\", reason=\"the kernel has no namespaces\")\ndef test_good():\n    pass\n",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 skipped" in result.stdout


def test_a_positional_skip_reason_counts(tmp_path):
    """pytest wraps it as 'unconditional skip (...)'; the words are still the author's."""
    result = _run_a_nested_suite(
        tmp_path,
        "import pytest\n\n\n@pytest.mark.skip(\"the kernel has no namespaces\")\ndef test_good():\n    pass\n",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 skipped" in result.stdout


def test_a_fixture_skip_with_a_reason_is_left_alone(tmp_path):
    result = _run_a_nested_suite(
        tmp_path,
        "import pytest\n\n\n@pytest.fixture\ndef setup():\n    pytest.skip(\"no namespaces on this kernel\")\n\n\n@pytest.mark.skipif(False, reason=\"only on windows\")\ndef test_good(setup):\n    pass\n",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 skipped" in result.stdout


def test_a_fixture_skip_without_a_reason_fails(tmp_path):
    result = _run_a_nested_suite(
        tmp_path,
        "import pytest\n\n\n@pytest.fixture\ndef setup():\n    pytest.skip()\n\n\n@pytest.mark.skipif(False, reason=\"only on windows\")\ndef test_bad(setup):\n    pass\n",
    )

    assert result.returncode != 0, result.stdout
    assert "skipped without a reason" in result.stdout + result.stderr


def test_a_stateful_condition_is_asked_once_and_a_reasonless_skip_fails(tmp_path):
    """Evaluating the condition again would answer differently and hide the skip."""
    result = _run_a_nested_suite(
        tmp_path,
        "import pytest\n\ncalls = []\n\n\ndef _bump():\n    calls.append(1)\n    return len(calls) == 1\n\n\n@pytest.mark.skipif(\"_bump()\")\ndef test_bad():\n    pass\n\n\ndef test_asked_once():\n    assert len(calls) == 1, calls\n",
    )

    assert result.returncode != 0, result.stdout
    output = result.stdout + result.stderr
    assert "skipped without a reason" in output
    assert "1 passed" in output


def test_a_stateful_condition_with_a_reason_stays_skipped(tmp_path):
    result = _run_a_nested_suite(
        tmp_path,
        "import pytest\n\ncalls = []\n\n\ndef _bump():\n    calls.append(1)\n    return len(calls) == 1\n\n\n@pytest.mark.skipif(\"_bump()\", reason=\"the first pass only\")\ndef test_good():\n    pass\n\n\ndef test_asked_once():\n    assert len(calls) == 1, calls\n",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 skipped" in result.stdout


def test_the_selected_skip_mark_is_the_one_judged(tmp_path):
    """A reasoned mark that pytest never selects cannot vouch for the one it does."""
    result = _run_a_nested_suite(
        tmp_path,
        "import pytest\n\n\n@pytest.mark.skip(reason=\"never selected\")\n@pytest.mark.skip\ndef test_bad():\n    pass\n\n\n@pytest.mark.skip\n@pytest.mark.skip(reason=\"the reason that counts\")\ndef test_good():\n    pass\n",
    )

    output = result.stdout + result.stderr
    assert result.returncode != 0, result.stdout
    assert "1 skipped" in output
    assert "1 error" in output
    assert "test_bad: skipped without a reason" in output


def test_a_module_skip_without_a_reason_fails_the_run(tmp_path):
    result = _run_a_nested_suite(tmp_path, "import pytest\n\npytest.skip(allow_module_level=True)\n")

    assert result.returncode != 0, result.stdout
    assert "module skipped without a reason" in result.stdout + result.stderr


def test_a_module_skip_with_a_reason_stays_skipped(tmp_path):
    result = _run_a_nested_suite(
        tmp_path,
        "import pytest\n\npytest.skip(\"no kernel namespaces on this host\", allow_module_level=True)\n",
    )

    assert result.returncode in (0, 5), result.stdout + result.stderr
    assert "1 skipped" in result.stdout
