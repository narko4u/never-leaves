"""A skip must carry its reason, checked when it happens.

The scan in tests/test_skip_policy.py reads source, so it catches the forms a
person writes. This hook catches the rest: a reason built at run time, a name
reached through a dict, a branch the environment chose.

Three things are separated here because they look alike in a report:

* which marker actually fired, computed the way pytest computes it, rather
  than guessed from the message it printed;
* whether that marker carried words of the author's, including a positional
  argument, which pytest wraps as "unconditional skip (...)" in its report;
* a skip raised by a fixture, which no marker explains and is judged on its
  own message.
"""

import pytest

try:  # pytest's own condition evaluation, so our answer matches its answer.
    from _pytest.skipping import evaluate_condition as _evaluate_condition
except Exception:  # pragma: no cover - only on a pytest that moved it
    _evaluate_condition = None


def _conditions(mark):
    if "condition" in mark.kwargs:
        return (mark.kwargs["condition"],)
    return mark.args


def _fires(item, mark) -> bool:
    conditions = _conditions(mark)
    if not conditions:
        return True
    for condition in conditions:
        if _evaluate_condition is not None:
            try:
                result, _ = _evaluate_condition(item, mark, condition)
            except Exception:
                continue
        else:  # pragma: no cover
            result = bool(condition)
        if result:
            return True
    return False


def fired_mark(item):
    """The marker pytest would act on, in pytest's order: skipif, then skip."""
    for mark in item.iter_markers(name="skipif"):
        if _fires(item, mark):
            return mark
    for mark in item.iter_markers(name="skip"):
        return mark
    return None


def mark_written_by_author(mark) -> bool:
    reason = mark.kwargs.get("reason")
    if isinstance(reason, str) and reason.strip():
        return True
    if mark.name == "skip" and mark.args and str(mark.args[0]).strip():
        return True
    return False


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
    if report.when == "setup":
        mark = fired_mark(item)
        reasonless = not mark_written_by_author(mark) if mark is not None else not raised
    else:
        reasonless = not raised

    if reasonless:
        report.outcome = "failed"
        report.longrepr = "%s: skipped without a reason" % item.nodeid
