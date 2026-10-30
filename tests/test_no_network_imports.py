"""The package imports no network module.

K1 says Never Leaves has no runtime network dependency. That is a claim
about the source, so it can be checked against the source: every module in
the package is parsed, and any import of a library that can open a socket
fails the suite.

The point is not to police an author. It is that the claim in the README
stays true when somebody reaches for `requests` at 2am.
"""

import ast
from pathlib import Path

PACKAGE = Path(__file__).parent.parent / "never_leaves"

BANNED = {
    "socket",
    "ssl",
    "urllib",
    "http",
    "requests",
    "httpx",
    "smtplib",
    "ftplib",
    "telnetlib",
}


def network_imports(source: str, name: str = "<module>") -> list:
    """Every banned import in a source string, as file:line text."""
    tree = ast.parse(source, filename=name)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in BANNED:
                    found.append("%s:%d imports %s" % (name, node.lineno, root))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            root = (node.module or "").split(".")[0]
            if root in BANNED:
                found.append("%s:%d imports from %s" % (name, node.lineno, root))
    return found


def test_package_imports_no_network_module():
    bad = []
    for path in sorted(PACKAGE.rglob("*.py")):
        bad.extend(network_imports(path.read_text(), str(path.relative_to(PACKAGE.parent))))
    assert not bad, "the package must not import a network module:\n" + "\n".join(bad)


def test_the_scanner_catches_a_plain_import():
    assert network_imports("import socket\n")


def test_the_scanner_catches_a_from_import():
    assert network_imports("from urllib.request import urlopen\n")


def test_the_scanner_catches_an_alias():
    assert network_imports("import httpx as client\n")


def test_the_scanner_allows_local_and_stdlib_safe_imports():
    assert not network_imports("import json\nfrom pathlib import Path\nfrom __future__ import annotations\n")
