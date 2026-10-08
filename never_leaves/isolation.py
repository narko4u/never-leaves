"""Kernel-enforced isolation for Never Leaves.

Never Leaves refuses to read your notes unless it can first prove it is
incapable of sending them anywhere. That proof is not a setting and it is
not a promise. It is a Linux network namespace in which this process has
no usable network interface and no route of any kind.

The check is deliberately suspicious of itself. An environment variable
can be set by anybody, so the marker only records an intention. The
kernel tables say whether the intention is actually true. Only the second
one counts and both must agree before a single byte of your note is read.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

MARKER = "NEVER_LEAVES_ISOLATED"

_PROC = Path("/proc/net")
_DEV = _PROC / "dev"
_ROUTE = _PROC / "route"
_INET = ("tcp", "tcp6", "udp", "udp6")


@dataclass
class IsolationReport:
    """What the kernel says about this process's ability to reach a network."""

    isolated: bool
    mechanism: str
    interfaces: list
    interfaces_up: list
    routes: list
    inet_sockets: int
    default_route: bool
    kernel_namespace: bool
    checked_at: str
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def summary(self) -> str:
        if self.isolated:
            return (
                "ISOLATED. %d network interface(s) present, none up. "
                "Routes: %d. Open IP sockets: %d."
                % (len(self.interfaces), len(self.routes), self.inet_sockets)
            )
        return "NOT ISOLATED. This process can reach a network."


def _rows(path: Path) -> list:
    try:
        return [ln for ln in path.read_text().splitlines()[1:] if ln.strip()]
    except OSError:
        return []


def read_interfaces() -> list:
    """Interface names from /proc/net/dev, skipping the two header lines."""
    try:
        lines = _DEV.read_text().splitlines()[2:]
    except OSError:
        return []
    names = []
    for line in lines:
        name = line.split(":", 1)[0].strip()
        if name:
            names.append(name)
    return names


def read_interface_states() -> dict:
    """Interface name to operational state, via /sys/class/net."""
    states = {}
    for name in read_interfaces():
        try:
            states[name] = (Path("/sys/class/net") / name / "operstate").read_text().strip()
        except OSError:
            states[name] = "unknown"
    return states


def read_routes() -> list:
    return [ln.split()[0] for ln in _rows(_ROUTE)]


def count_inet_sockets() -> int:
    """Open IP sockets across tcp, tcp6, udp and udp6.

    This matters more than it looks. A namespace with no interfaces still
    cannot stop a process that inherited an already-open socket from its
    parent. Counting them is how we rule that out.
    """
    return sum(len(_rows(_PROC / proto)) for proto in _INET)


def inspect() -> IsolationReport:
    """Observe, without trusting any marker, whether egress is possible."""
    interfaces = read_interfaces()
    states = read_interface_states()
    up = sorted(n for n, s in states.items() if s == "up")
    routes = read_routes()
    default_route = any(r != "lo" for r in routes)
    sockets = count_inet_sockets()

    only_loopback = all(n == "lo" for n in interfaces)
    isolated = only_loopback and not up and not routes and sockets == 0

    if isolated:
        detail = (
            "Only the loopback interface exists and it is not up. The route "
            "table is empty and no IP sockets are open, so outbound traffic "
            "was impossible rather than merely unused."
        )
    elif not only_loopback:
        detail = "A non-loopback interface exists: %s." % ", ".join(
            n for n in interfaces if n != "lo"
        )
    elif up:
        detail = "An interface is up: %s." % ", ".join(up)
    elif routes:
        detail = "A route exists: %s." % ", ".join(routes)
    else:
        detail = "%d IP socket(s) are already open." % sockets

    return IsolationReport(
        isolated=isolated,
        mechanism="linux network namespace via unshare -rn",
        interfaces=interfaces,
        interfaces_up=up,
        routes=routes,
        inet_sockets=sockets,
        default_route=default_route,
        kernel_namespace=os.environ.get(MARKER) == "1",
        checked_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        detail=detail,
    )


class IsolationUnavailable(RuntimeError):
    """Raised when the machine cannot give us a namespace and we must not proceed."""


def supported() -> tuple:
    if not shutil.which("unshare"):
        return False, "unshare was not found, so this machine cannot give us a namespace"
    return True, "ok"


def re_exec_isolated(argv: list) -> None:
    """Replace this process with an identical one inside a fresh netns.

    unshare -rn creates a user and network namespace together. The network
    namespace starts with a loopback device that is down, which is exactly
    the state we want to be able to prove.
    """
    env = dict(os.environ)
    env[MARKER] = "1"
    cmd = ["unshare", "-rn", "--", sys.executable, "-m", "never_leaves"] + list(argv)
    os.execvpe(cmd[0], cmd, env)


def ensure_isolated(argv: list, allow_unverified: bool = False) -> IsolationReport:
    """Guarantee isolation before any user data is touched.

    Returns the verified report. Refuses to continue when isolation cannot
    be established, unless the operator explicitly opts out, in which case
    the returned report says so honestly and the caller must surface it.
    """
    report = inspect()
    if report.isolated and report.kernel_namespace:
        return report

    if os.environ.get(MARKER) == "1":
        # We were launched into a namespace, yet egress is still possible.
        # That is a contradiction and it is not safe to continue.
        raise IsolationUnavailable(
            "launched inside a namespace but egress is still possible: " + report.detail
        )

    ok, why = supported()
    if not ok:
        if allow_unverified:
            return report
        raise IsolationUnavailable(why + ". Re-run with --no-isolate to accept that risk.")

    re_exec_isolated(argv)
    raise AssertionError("unreachable: os.execvpe should not return")
