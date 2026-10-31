"""A skip must carry its reason, checked when it happens.

The scan in tests/test_skip_policy.py reads source, so it catches the forms a
person writes. This hook catches the rest: a reason built at run time, a name
reached through a dict, a branch the environment chose.

Three things are separated here because they look alike in a report:

* which marker actually fired, recorded from the evaluation pytest itself made,
  so a condition with state is asked once and its answer is not second-guessed;
* whether that marker carried words of the author's, including a positional
  argument, which pytest wraps as "unconditional skip (...)" in its report;
* a skip raised by a test or a fixture, which no marker explains and is judged
  on its own message.
"""

import pytest

try:
    import _pytest.skipping as _skipping
except Exception:  # pragma: no cover - only on a pytest without that module
    _skipping = None

FIRED_SKIPIF = pytest.StashKey()


def _record_fired_condition():
    """Wrap pytest's own condition evaluation so the mark that fired is known.

    The wrapper calls the original and notes its answer. It never evaluates a
    condition itself, so a condition that changes state is still asked once.
    """
    if _skipping is None:
        return
    original = getattr(_skipping, "evaluate_condition", None)
    if original is None or getattr(original, "_pb_records_fired", False):
        return

    def evaluate_condition(item, mark, condition):
        result, reason = original(item, mark, condition)
        if result and getattr(mark, "name", None) == "skipif":
            stash = getattr(item, "stash", None)
            if stash is not None:
                stash.setdefault(FIRED_SKIPIF, []).append(mark)
        return result, reason

    evaluate_condition._pb_records_fired = True
    _skipping.evaluate_condition = evaluate_condition


_record_fired_condition()


def fired_skipif(item):
    stash = getattr(item, "stash", None)
    if stash is None:
        return None
    marks = stash.get(FIRED_SKIPIF, None)
    return marks[0] if marks else None


def _written_by_author(mark) -> bool:
    reason = mark.kwargs.get("reason")
    if isinstance(reason, str) and reason.strip():
        return True
    if mark.name == "skip" and mark.args and str(mark.args[0]).strip():
        return True
    return False


def _raised_by_a_mark(call) -> bool:
    excinfo = getattr(call, "excinfo", None)
    if excinfo is None:
        return False
    if getattr(excinfo.value, "_use_item_location", False):
        return True
    for entry in getattr(excinfo, "traceback", []) or []:
        if str(getattr(entry, "path", "")).endswith("_pytest/skipping.py"):
            return True
    return False


def _raised_reason(call) -> str:
    excinfo = getattr(call, "excinfo", None)
    if excinfo is None:
        return ""
    return str(getattr(excinfo.value, "msg", "") or "").strip()


def _the_skip_mark(item):
    """The skip mark pytest would select: iter_markers yields closest first."""
    for mark in item.iter_markers(name="skip"):
        return mark
    return None


def skip_was_reasonless(item, call) -> bool:
    mark = fired_skipif(item)
    if mark is not None:
        return not _written_by_author(mark)
    if _raised_by_a_mark(call):
        selected = _the_skip_mark(item)
        if selected is not None:
            return not _written_by_author(selected)
    return not _raised_reason(call)


def _collect_skip_reason(report) -> str:
    """Collection skips keep their words in a (path, line, 'Skipped: ...') tuple."""
    longrepr = report.longrepr
    if isinstance(longrepr, tuple) and len(longrepr) == 3:
        text = str(longrepr[2])
    else:
        text = str(longrepr or "")
    text = text.strip()
    if text in ("Skipped", "Skipped:"):
        return ""
    if text.startswith("Skipped:"):
        text = text[len("Skipped:"):]
    return text.strip()


@pytest.hookimpl(hookwrapper=True)
def pytest_make_collect_report(collector):
    """A module that skips during collection never becomes an item, so judge it here."""
    outcome = yield
    report = outcome.get_result()
    if not report.skipped:
        return
    if not _collect_skip_reason(report):
        report.outcome = "failed"
        report.longrepr = "%s: module skipped without a reason" % getattr(collector, "nodeid", "module")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if getattr(report, "wasxfail", None):
        return
    if not report.skipped:
        return

    if skip_was_reasonless(item, call):
        report.outcome = "failed"
        report.longrepr = "%s: skipped without a reason" % item.nodeid
