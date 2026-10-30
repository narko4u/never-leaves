"""Every skip says why.

A skip that says nothing is indistinguishable from a pass nobody tried. G2
says a skip carries its reason, and this test is what keeps that true for
the next skip somebody adds.
"""

import ast
from pathlib import Path

TESTS = Path(__file__).parent


def _kind(node: ast.Call):
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Attribute):
        if func.value.attr == "mark" and func.attr == "skipif":
            return "skipif"
    if isinstance(func, ast.Attribute) and func.attr == "skip":
        if isinstance(func.value, ast.Name) and func.value.id == "pytest":
            return "skip"
    return None


def violations(source: str, name: str = "<test>") -> list:
    """Every silent skip in a source string, as file:line text."""
    tree = ast.parse(source, filename=name)
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        kind = _kind(node)
        if kind is None:
            continue
        keywords = {kw.arg for kw in node.keywords}
        if kind == "skipif":
            if "reason" not in keywords:
                bad.append("%s:%d skipif without reason" % (name, node.lineno))
        elif not node.args and "reason" not in keywords:
            bad.append("%s:%d skip without a reason" % (name, node.lineno))
    return bad


def test_every_skip_states_its_reason():
    bad = []
    for path in sorted(TESTS.glob("test_*.py")):
        bad.extend(violations(path.read_text(), path.name))
    assert not bad, "a skip must say why:\n" + "\n".join(bad)


def test_the_scanner_catches_a_silent_skip():
    assert violations("import pytest\n\ndef test_x():\n    pytest.skip()\n")


def test_the_scanner_catches_a_silent_skipif():
    assert violations("import pytest\n\n@pytest.mark.skipif(True)\ndef test_x():\n    pass\n")


def test_the_scanner_accepts_a_reason():
    assert not violations('import pytest\n\ndef test_x():\n    pytest.skip("no model here")\n')
