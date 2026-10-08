"""Isolation tests.

The important one is the last: it launches a real subprocess inside a
real network namespace and asserts, from the inside, that egress is
impossible. If that test ever goes green on a machine that can reach the
internet, the guarantee is a lie.
"""

import json
import shutil
import subprocess
import sys

import pytest

from never_leaves import isolation


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


@pytest.mark.skipif(shutil.which("unshare") is None, reason="unshare not available")
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


@pytest.mark.skipif(shutil.which("unshare") is None, reason="unshare not available")
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
