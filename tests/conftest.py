"""A skip must carry its reason, checked when it happens.

The scan in tests/test_skip_policy.py reads source, so it catches the forms a
person writes. This hook catches the rest: a reason built at run time, a name
reached through a dict, a branch the environment chose.

It judges authorship rather than text, because pytest writes filler of its own:
a bare @pytest.mark.skip becomes "unconditional skip", and a skipif given a
string condition becomes that condition. And it judges the marker that actually
fired: a reasoned marker that never triggered cannot vouch for a reasonless one
that did.
"""

import pytest

SKIP_MARKS = ("skip", "skipif")


def pytest_collection_modifyitems(items):
    for item in items:
        marks = [mark for mark in item.iter_markers() if mark.name in SKIP_MARKS]
        reasons = set()
        for mark in marks:
            reason = mark.kwargs.get("reason")
            if isinstance(reason, str) and reason.strip():
                reasons.add(reason.strip())
        item.pb_skip_marks = bool(marks)
        item.pb_authored_reasons = reasons


def _raised_reason(call) -> str:
    excinfo = getattr(call, "excinfo", None)
    if excinfo is None:
        return ""
    return str(getattr(excinfo.value, "msg", "") or "").strip()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if getattr(report, "wasxfail", None):
        return
    if not report.skipped:
        return

    raised = _raised_reason(call)
    if report.when == "setup" and getattr(item, "pb_skip_marks", False):
        # A marker fired. Its words count only if some marker on this item
        # carries them; filler written by pytest matches nothing.
        reasonless = raised not in getattr(item, "pb_authored_reasons", set())
    else:
        reasonless = not raised

    if reasonless:
        report.outcome = "failed"
        report.longrepr = "%s: skipped without a reason" % item.nodeid
