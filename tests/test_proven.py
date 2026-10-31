"""A report describes. A proof establishes.

`proven` is true only when the tables were read clean and this process is
the one launched into the namespace. The rule is tested directly, the
unreadable case is tested with the marker set, and the refusal path is
tested to see that a caller still gets a report saying proven false.
"""

import json

import pytest

from never_leaves import cli, isolation


def _report(**overrides):
    fields = dict(
        isolated=False,
        mechanism="test",
        interfaces=["eth0"],
        interfaces_up=[],
        routes=[],
        inet_sockets=0,
        default_route=True,
        kernel_namespace=False,
        checked_at="2026-10-31T00:00:00+00:00",
        detail="A non-loopback interface exists: eth0.",
    )
    fields.update(overrides)
    return isolation.IsolationReport(**fields)


def test_clean_tables_only_count_with_the_marker(monkeypatch):
    monkeypatch.delenv(isolation.MARKER, raising=False)
    assert isolation.proven_by_tables(True) is False

    monkeypatch.setenv(isolation.MARKER, "1")
    assert isolation.proven_by_tables(True) is True


def test_dirty_tables_are_never_proven(monkeypatch):
    monkeypatch.setenv(isolation.MARKER, "1")
    assert isolation.proven_by_tables(False) is False


def test_unreadable_tables_are_not_proven_even_with_the_marker(monkeypatch, tmp_path):
    net = tmp_path / "net"
    monkeypatch.setattr(isolation, "_PROC", net)
    monkeypatch.setattr(isolation, "_DEV", net / "dev")
    monkeypatch.setattr(isolation, "_ROUTE", net / "route")
    monkeypatch.setenv(isolation.MARKER, "1")

    report = isolation.inspect()

    assert report.unreadable
    assert report.proven is False
    assert report.kernel_namespace is True


def test_the_report_carries_proven_false():
    assert json.loads(_report().to_json())["proven"] is False


def test_refusal_still_emits_a_report(monkeypatch, capsys):
    def refuse(*args, **kwargs):
        raise isolation.IsolationUnavailable("the kernel refused a namespace")

    monkeypatch.setattr(isolation, "ensure_isolated", refuse)

    with pytest.raises(SystemExit) as caught:
        cli.main(["check", "--json"])

    out = capsys.readouterr().out
    assert caught.value.code == 2
    assert json.loads(out[out.index("{") :])["proven"] is False
