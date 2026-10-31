"""Isolation tests.

The important one is the last: it launches a real subprocess inside a
real network namespace and asserts, from the inside, that egress is
impossible. If that test ever goes green on a machine that can reach the
internet, the guarantee is a lie.

That test needs the kernel to permit an unprivileged user namespace. Where
it does not, the test skips and says why. A skip is not a pass.
"""

import json
import shutil
import subprocess
import sys

import pytest

from never_leaves import isolation


def _namespace_capability() -> tuple:
    """Ask the kernel, not the filesystem, whether a namespace is possible.

    Having the unshare binary is not the question. Some kernels refuse to
    write /proc/self/uid_map, which is Ubuntu's default from 24.04 onward,
    and a machine that refuses it cannot evaluate the guarantee at all. The
    reason travels with the answer so a skip explains itself.
    """
    if shutil.which("unshare") is None:
        return False, "unshare was not found on this machine"
    probe = subprocess.run(
        ["unshare", "-rn", "--", "true"], capture_output=True, text=True
    )
    if probe.returncode != 0:
        first = (probe.stderr or "").strip().splitlines()
        detail = f": {first[0]}" if first else ""
        return False, f"the kernel refused an unprivileged user namespace{detail}"
    return True, "ok"


_NAMESPACES, _NAMESPACE_REASON = _namespace_capability()


def test_interfaces_parse_includes_loopback():
    assert "lo" in isolation.read_interfaces()


def test_routes_returns_a_list():
    assert isinstance(isolation.read_routes(), list)


def test_socket_count_is_an_int():
    assert isinstance(isolation.count_inet_sockets(), int)
    assert isolation.count_inet_sockets() >= 0


def test_report_roundtrips_through_json():
    report = isolation.inspect()
    payload = json.loads(report.to_json())
    assert payload["isolated"] == report.isolated
    assert payload["interfaces"] == report.interfaces
    assert report.checked_at.endswith("+00:00") or "T" in report.checked_at


def test_summary_is_honest_about_each_state():
    report = isolation.inspect()
    if report.isolated:
        assert report.summary().startswith("ISOLATED")
    else:
        assert report.summary().startswith("NOT ISOLATED")


@pytest.mark.skipif(not _NAMESPACES, reason=_NAMESPACE_REASON)
def test_inside_a_namespace_egress_is_impossible(tmp_path):
    """The real guarantee, asserted from inside the box."""
    probe = (
        "import json;"
        "from never_leaves import isolation;"
        "print(json.dumps(isolation.inspect().to_dict()))"
    )
    result = subprocess.run(
        ["unshare", "-rn", "--", sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["isolated"] is True
    assert report["interfaces"] == ["lo"]
    assert report["interfaces_up"] == []
    assert report["routes"] == []
    assert report["inet_sockets"] == 0


@pytest.mark.skipif(not _NAMESPACES, reason=_NAMESPACE_REASON)
def test_no_route_means_no_route(tmp_path):
    """No route table entry and no IP socket means a connect must fail."""
    probe = (
        "import socket;"
        "\ntry:\n"
        "    socket.create_connection(('1.1.1.1', 443), timeout=3)\n"
        "    print('REACHABLE')\n"
        "except OSError:\n"
        "    print('BLOCKED')\n"
    )
    result = subprocess.run(
        ["unshare", "-rn", "--", sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert "BLOCKED" in result.stdout
    assert "REACHABLE" not in result.stdout


def test_unreadable_table_is_not_a_proof(monkeypatch, tmp_path):
    """A table we cannot read must not read as a table with nothing in it."""
    net = tmp_path / "net"
    monkeypatch.setattr(isolation, "_PROC", net)
    monkeypatch.setattr(isolation, "_DEV", net / "dev")
    monkeypatch.setattr(isolation, "_ROUTE", net / "route")

    report = isolation.inspect()

    assert report.isolated is False
    assert str(net / "dev") in report.detail
    assert report.unreadable
    assert report.summary().startswith("UNPROVEN")


def test_only_the_missing_table_is_named(monkeypatch, tmp_path):
    """A readable table is evidence. Only the unreadable one is reported."""
    net = tmp_path / "net"
    net.mkdir()
    (net / "dev").write_text("h1\nh2\n  lo: 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0\n")
    monkeypatch.setattr(isolation, "_PROC", net)
    monkeypatch.setattr(isolation, "_DEV", net / "dev")
    monkeypatch.setattr(isolation, "_ROUTE", net / "route")

    report = isolation.inspect()

    assert str(net / "route") in report.unreadable
    assert str(net / "dev") not in report.detail


class _CountingTable:
    """A kernel table that records how many times it was read."""

    def __init__(self, text=None, error=None):
        self.text = text
        self.error = error
        self.reads = 0

    def read_text(self):
        self.reads += 1
        if self.error:
            raise PermissionError(self.error)
        return self.text

    def __str__(self):
        return "counting-table"


def _fake_net(tmp_path):
    net = tmp_path / "net"
    net.mkdir()
    for proto in ("tcp", "tcp6", "udp", "udp6"):
        (net / proto).write_text("sl local remote st\n")
    return net


def test_each_table_is_read_once(monkeypatch, tmp_path):
    """Two reads are two truths. The check must rest on one."""
    net = _fake_net(tmp_path)
    dev = _CountingTable("h1\nh2\n  lo: 0\n")
    route = _CountingTable("Iface Destination\n")
    monkeypatch.setattr(isolation, "_PROC", net)
    monkeypatch.setattr(isolation, "_DEV", dev)
    monkeypatch.setattr(isolation, "_ROUTE", route)
    monkeypatch.setattr(isolation, "_states_for", lambda names: {n: "down" for n in names})

    report = isolation.inspect()

    assert report.isolated is True
    assert dev.reads == 1
    assert route.reads == 1


def test_failure_during_observation_is_not_a_pass(monkeypatch, tmp_path):
    """The read that fails is the read that counts, and it must not pass."""
    net = _fake_net(tmp_path)
    dev = _CountingTable(error="permission denied")
    route = _CountingTable("Iface Destination\n")
    monkeypatch.setattr(isolation, "_PROC", net)
    monkeypatch.setattr(isolation, "_DEV", dev)
    monkeypatch.setattr(isolation, "_ROUTE", route)

    report = isolation.inspect()

    assert report.isolated is False
    assert "counting-table" in report.detail
    assert dev.reads == 1


def _not_isolated():
    return isolation.IsolationReport(
        isolated=False,
        mechanism="test",
        interfaces=[],
        interfaces_up=[],
        routes=[],
        inet_sockets=0,
        default_route=False,
        kernel_namespace=False,
        checked_at="2026-10-31T00:00:00+00:00",
        detail="not isolated",
    )


def test_exec_refusal_is_a_refusal_not_a_traceback(monkeypatch):
    """A kernel that refuses the namespace must reach the caller as a refusal."""
    monkeypatch.setattr(isolation, "inspect", _not_isolated)
    monkeypatch.setattr(isolation, "supported", lambda: (True, "ok"))

    def refused(argv):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(isolation, "re_exec_isolated", refused)

    with pytest.raises(isolation.IsolationUnavailable) as caught:
        isolation.ensure_isolated([])

    assert "could not enter a network namespace" in str(caught.value)
    assert "Operation not permitted" in str(caught.value)


def test_binary_vanishing_between_check_and_exec_is_a_refusal(monkeypatch):
    monkeypatch.setattr(isolation, "inspect", _not_isolated)
    monkeypatch.setattr(isolation, "supported", lambda: (True, "ok"))

    def gone(argv):
        raise FileNotFoundError(2, "No such file or directory")

    monkeypatch.setattr(isolation, "re_exec_isolated", gone)

    with pytest.raises(isolation.IsolationUnavailable) as caught:
        isolation.ensure_isolated([])

    assert "could not enter a network namespace" in str(caught.value)


class _Probe:
    def __init__(self, returncode, stderr=""):
        self.returncode = returncode
        self.stderr = stderr


def test_supported_refuses_a_kernel_that_denies_the_namespace(monkeypatch):
    """unshare installed but the kernel saying no is not support."""
    monkeypatch.setattr(isolation.shutil, "which", lambda name: "/usr/bin/unshare")
    monkeypatch.setattr(
        isolation.subprocess,
        "run",
        lambda *a, **k: _Probe(1, "unshare: unshare failed: Operation not permitted\n"),
    )

    ok, why = isolation.supported()

    assert ok is False
    assert "Operation not permitted" in why


def test_supported_runs_the_probe_and_accepts_it(monkeypatch):
    calls = []
    monkeypatch.setattr(isolation.shutil, "which", lambda name: "/usr/bin/unshare")
    monkeypatch.setattr(
        isolation.subprocess, "run", lambda argv, **k: calls.append(argv) or _Probe(0)
    )

    assert isolation.supported() == (True, "ok")
    assert calls == [["unshare", "-rn", "--", "true"]]


def test_supported_names_a_missing_binary(monkeypatch):
    monkeypatch.setattr(isolation.shutil, "which", lambda name: None)

    ok, why = isolation.supported()

    assert ok is False
    assert "unshare was not found" in why


def test_supported_survives_a_binary_that_vanishes(monkeypatch):
    monkeypatch.setattr(isolation.shutil, "which", lambda name: "/usr/bin/unshare")

    def gone(*a, **k):
        raise FileNotFoundError(2, "No such file or directory")

    monkeypatch.setattr(isolation.subprocess, "run", gone)

    ok, why = isolation.supported()

    assert ok is False
    assert "could not be run" in why


def test_supported_survives_a_binary_without_execute_permission(monkeypatch):
    monkeypatch.setattr(isolation.shutil, "which", lambda name: "/usr/bin/unshare")

    def denied(*a, **k):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(isolation.subprocess, "run", denied)

    ok, why = isolation.supported()

    assert ok is False
    assert "Permission denied" in why
