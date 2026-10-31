"""When a run goes ahead without a namespace, it says so out loud.

An opt-out is not a quiet mode. The line begins NOT ISOLATED and names what
the process can still reach. When the kernel tables could not be read the
line says that too, because an unread table is not a clean one. Every test
sets the report it is judging, so the host's own network does not decide
whether the case runs.
"""

import json

import pytest

from never_leaves import cli, isolation


def _report(**overrides):
    fields = dict(
        isolated=False,
        mechanism="test",
        interfaces=["eth0"],
        interfaces_up=["eth0"],
        routes=["default"],
        inet_sockets=3,
        default_route=True,
        kernel_namespace=False,
        checked_at="2026-10-31T00:00:00+00:00",
        detail="A non-loopback interface exists: eth0.",
    )
    fields.update(overrides)
    return isolation.IsolationReport(**fields)


def test_a_read_table_names_what_was_seen():
    reason = _report().not_isolated_reason()

    assert reason == "A non-loopback interface exists: eth0."
    assert "could not be read" not in reason


def test_an_unreadable_table_says_network_access_remains_possible():
    reason = _report(detail="could not read /proc/net/dev", unreadable=["dev"]).not_isolated_reason()

    assert "could not be read" in reason
    assert "network access remains possible" in reason


def test_check_prints_the_line_for_an_unreadable_report(monkeypatch, capsys):
    report = _report(
        detail="could not read /proc/net/dev",
        unreadable=["dev"],
        kernel_namespace=True,
    )
    monkeypatch.setattr(isolation, "ensure_isolated", lambda *a, **k: report)

    cli.main(["check", "--no-isolate"])

    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if l.startswith("NOT ISOLATED"))
    assert "network access remains possible" in line


def test_check_json_keeps_isolated_false(monkeypatch, capsys):
    monkeypatch.setattr(isolation, "ensure_isolated", lambda *a, **k: _report())

    cli.main(["check", "--no-isolate", "--json"])

    out = capsys.readouterr().out
    assert json.loads(out[out.index("{") :])["isolated"] is False


@pytest.mark.parametrize("command", ["quote", "report"])
def test_document_commands_say_it_too(monkeypatch, capsys, command):
    report = _report(detail="could not read /proc/net/dev", unreadable=["dev"])
    monkeypatch.setattr(isolation, "ensure_isolated", lambda *a, **k: report)

    def stop(*args, **kwargs):
        raise RuntimeError("stop after the warning")

    monkeypatch.setattr(cli, "_read_note", stop)

    with pytest.raises((RuntimeError, SystemExit)):
        cli.main([command, "notes.txt", "--no-isolate"])

    out = capsys.readouterr().out
    assert "NOT ISOLATED" in out
    assert "network access remains possible" in out
