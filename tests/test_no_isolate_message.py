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


def test_a_clean_reading_without_a_namespace_is_not_a_pass(monkeypatch):
    """The trap: no unshare, but the tables read clean on this machine."""
    clean = _report(
        isolated=True,
        kernel_namespace=False,
        interfaces=["lo"],
        interfaces_up=["lo"],
        routes=[],
        inet_sockets=0,
        detail="Only loopback is present and no route exists.",
    )
    monkeypatch.setattr(isolation, "inspect", lambda: clean)
    monkeypatch.setattr(isolation, "supported", lambda: (False, "unshare is not available"))

    report = isolation.ensure_isolated([], allow_unverified=True)

    assert report.isolated is False
    assert report.kernel_namespace is False
    assert "network access remains possible" in report.not_isolated_reason()


def test_a_clean_reading_without_a_namespace_still_refuses(monkeypatch):
    clean = _report(isolated=True, kernel_namespace=False, interfaces=["lo"])
    monkeypatch.setattr(isolation, "inspect", lambda: clean)
    monkeypatch.setattr(isolation, "supported", lambda: (False, "unshare is not available"))

    with pytest.raises(isolation.IsolationUnavailable):
        isolation.ensure_isolated([])


def _complete_a_document(monkeypatch, tmp_path, out):
    clean = _report(
        isolated=True,
        kernel_namespace=False,
        interfaces=["lo"],
        interfaces_up=["lo"],
        routes=[],
        inet_sockets=0,
        detail="Only loopback is present and no route exists.",
    )
    monkeypatch.setattr(isolation, "inspect", lambda: clean)
    monkeypatch.setattr(isolation, "supported", lambda: (False, "unshare is not available"))
    monkeypatch.setattr(cli, "_read_note", lambda path: "Thirty metres of fencing.")
    monkeypatch.setattr(cli, "_facts", lambda args: {})

    class Weights:
        name = "test-model"

    monkeypatch.setattr(cli, "_draft", lambda *a, **k: (
        Weights(),
        {"text": "A draft.", "prompt_tokens": 3, "completion_tokens": 4},
    ))
    monkeypatch.setattr(cli.model, "fingerprint", lambda ref, full=False: {"sha256": "0" * 64})
    monkeypatch.setattr(cli.document, "render", lambda *a, **k: "rendered document")
    monkeypatch.setattr(cli.ledger, "append", lambda record, path: tmp_path / "runs.jsonl")
    return out


@pytest.mark.parametrize("command", ["quote", "report"])
def test_a_completed_run_keeps_the_unverified_status(monkeypatch, capsys, tmp_path, command):
    out = _complete_a_document(monkeypatch, tmp_path, tmp_path / "out.md")

    cli.main([command, "notes.txt", "--no-isolate", "--out", str(out), "--json"])

    printed = capsys.readouterr().out
    data = json.loads(printed[printed.index("{") :])
    assert data["isolation"]["isolated"] is False
    assert data["isolation"]["kernel_namespace"] is False
    assert "network access remains possible" in data["isolation"]["detail"]


def test_the_completion_message_says_not_isolated(monkeypatch, capsys, tmp_path):
    out = _complete_a_document(monkeypatch, tmp_path, tmp_path / "out.md")

    cli.main(["quote", "notes.txt", "--no-isolate", "--out", str(out)])

    printed = capsys.readouterr().out
    assert printed.count("NOT ISOLATED") >= 2
    assert "PROBLEM" not in printed
