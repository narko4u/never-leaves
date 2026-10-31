"""A skip must carry its reason, checked when it happens.

The scan in tests/test_skip_policy.py reads source, so it catches the forms a
person writes. This hook catches the rest: a reason built at run time, a name
reached through a dict, a branch the environment chose. It judges authorship,
not text, because pytest writes fallback text of its own: a bare
@pytest.mark.skip becomes "unconditional skip", and a skipif given a string
condition becomes that condition. Neither was written by the author, so neither
counts as a reason. A reason the author typed, even the same words, does.
"""

import pytest

SKIP_MARKS = ("skip", "skipif")


def _mark_states_a_reason(item) -> bool:
    for mark in item.iter_markers():
        if mark.name in SKIP_MARKS:
            reason = mark.kwargs.get("reason")
            if isinstance(reason, str) and reason.strip():
                return True
    return False


def pytest_collection_modifyitems(items):
    for item in items:
        marks = [mark.name for mark in item.iter_markers() if mark.name in SKIP_MARKS]
        item.pb_skip_mark = bool(marks)
        item.pb_mark_reason = _mark_states_a_reason(item)


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

    if getattr(item, "pb_skip_mark", False) and not getattr(item, "pb_mark_reason", False):
        reasonless = True
    else:
        reasonless = not _raised_reason(call)

    if reasonless:
        report.outcome = "failed"
        report.longrepr = "%s: skipped without a reason" % item.nodeid
