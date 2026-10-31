"""A skip must carry its reason, checked when it happens.

The scan in tests/test_skip_policy.py reads source, so it catches the forms a
person writes. This hook catches the rest: a reason built at run time, a name
reached through a dict, a branch the environment chose. It runs after every
test phase and turns a reasonless skip into a failure that names the test.
"""

import pytest


def _reason(report) -> str:
    """The words after 'Skipped:' in a report, or an empty string."""
    longrepr = report.longrepr
    text = longrepr[2] if isinstance(longrepr, tuple) and len(longrepr) == 3 else longrepr
    text = str(text or "").strip()
    if text == "Skipped":
        return ""
    if text.startswith("Skipped:"):
        text = text[len("Skipped:"):].strip()
    # pytest fills this in for a bare @pytest.mark.skip; nobody wrote it.
    return "" if text == "unconditional skip" else text


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if getattr(report, "wasxfail", None):
        return
    if report.skipped and not _reason(report):
        report.outcome = "failed"
        report.longrepr = "%s: skipped without a reason" % item.nodeid
