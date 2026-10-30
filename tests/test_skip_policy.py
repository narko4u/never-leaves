"""Every skip says why.

A skip that says nothing is indistinguishable from a pass nobody tried. G2
says a skip carries its reason, and this test is what keeps that true for
the next skip somebody adds.

The scanner resolves imports rather than matching text, so a skip counts
however it was brought into the module: `pytest.skip`, `import pytest as
pt`, or `from pytest import skip`. A starred argument is not accepted as a
reason, because we cannot see inside it.
"""

import ast
from pathlib import Path

TESTS = Path(__file__).parent


def _names(tree) -> dict:
    """Which local names refer to pytest, its skip, skipif and mark.

    Imports are not the only way a name arrives. `from pytest import *`
    binds the helpers directly, and `f = pytest.skip` binds them by
    assignment, so both are followed.
    """
    names = {"pytest": {"pytest"}, "skip": set(), "skipif": set(), "mark": set()}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "pytest":
                    names["pytest"].add(alias.asname or "pytest")
        elif isinstance(node, ast.ImportFrom) and not node.level:
            module = node.module or ""
            for alias in node.names:
                if alias.name == "*":
                    if module == "pytest":
                        names["skip"].add("skip")
                        names["skipif"].add("skipif")
                        names["mark"].add("mark")
                    elif module == "pytest.mark":
                        names["skipif"].add("skipif")
                    continue
                local = alias.asname or alias.name
                if module == "pytest" and alias.name == "skip":
                    names["skip"].add(local)
                elif module == "pytest" and alias.name == "mark":
                    names["mark"].add(local)
                elif module == "pytest.mark" and alias.name == "skipif":
                    names["skipif"].add(local)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        kind = _expr_kind(value, names)
        if kind is None:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                names[kind].add(target.id)
    return names


def _expr_kind(node, names):
    """What a name or attribute expression refers to, if it is a skip."""
    if isinstance(node, ast.Name):
        if node.id in names["skip"]:
            return "skip"
        if node.id in names["skipif"]:
            return "skipif"
        return None
    if not isinstance(node, ast.Attribute):
        return None
    base = node.value
    if node.attr == "skip" and isinstance(base, ast.Name) and base.id in names["pytest"]:
        return "skip"
    if node.attr == "skipif":
        if isinstance(base, ast.Attribute) and base.attr == "mark":
            owner = base.value
            if isinstance(owner, ast.Name):
                if owner.id in names["pytest"] or owner.id in names["mark"]:
                    return "skipif"
        if isinstance(base, ast.Name) and base.id in names["mark"]:
            return "skipif"
    return None


def _kind(node: ast.Call, names):
    return _expr_kind(node.func, names)


def _states_reason(node: ast.Call) -> bool:
    """An explicit reason keyword, or a positional argument we can see."""
    if any(keyword.arg == "reason" for keyword in node.keywords):
        return True
    return any(not isinstance(arg, ast.Starred) for arg in node.args)


def violations(source: str, name: str = "<test>") -> list:
    """Every silent skip in a source string, as file:line text."""
    tree = ast.parse(source, filename=name)
    names = _names(tree)
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        kind = _kind(node, names)
        if kind is None:
            continue
        if kind == "skipif":
            if not any(keyword.arg == "reason" for keyword in node.keywords):
                bad.append("%s:%d skipif without reason" % (name, node.lineno))
        elif not _states_reason(node):
            bad.append("%s:%d skip without a reason" % (name, node.lineno))
    return bad


def violations_in_tree(root: Path) -> list:
    """Every silent skip under a directory, naming the file and line."""
    bad = []
    for path in sorted(root.rglob("*.py")):
        bad.extend(violations(path.read_text(), str(path.relative_to(root))))
    return bad


def test_every_skip_states_its_reason():
    bad = violations_in_tree(TESTS)
    assert not bad, "a skip must say why:\n" + "\n".join(bad)


def test_the_scan_reaches_conftest_and_nested_files(tmp_path):
    """A helper or a nested module can skip too, and must be scanned."""
    (tmp_path / "nested").mkdir()
    (tmp_path / "conftest.py").write_text("import pytest\n\ndef test_x():\n    pytest.skip()\n")
    (tmp_path / "nested" / "test_nested.py").write_text(
        "import pytest\n\ndef test_y():\n    pytest.skip()\n"
    )

    found = violations_in_tree(tmp_path)

    assert len(found) == 2
    assert any("conftest.py" in line for line in found)
    assert any("test_nested.py" in line for line in found)


def test_the_scanner_catches_a_silent_skip():
    assert violations("import pytest\n\ndef test_x():\n    pytest.skip()\n")


def test_the_scanner_catches_a_silent_skipif():
    assert violations("import pytest\n\n@pytest.mark.skipif(True)\ndef test_x():\n    pass\n")


def test_the_scanner_catches_an_imported_skip():
    assert violations("from pytest import skip\n\ndef test_x():\n    skip()\n")


def test_the_scanner_catches_an_aliased_module():
    assert violations("import pytest as pt\n\ndef test_x():\n    pt.skip()\n")


def test_the_scanner_catches_an_imported_skipif():
    assert violations("from pytest.mark import skipif\n\n@skipif(True)\ndef test_x():\n    pass\n")


def test_a_starred_argument_is_not_a_reason():
    assert violations("import pytest\n\ndef test_x(*args):\n    pytest.skip(*args)\n")


def test_the_scanner_catches_a_wildcard_import():
    assert violations("from pytest import *\n\ndef test_x():\n    skip()\n")


def test_the_scanner_catches_an_assigned_alias():
    assert violations("import pytest\n\nf = pytest.skip\n\ndef test_x():\n    f()\n")


def test_the_scanner_accepts_a_reason():
    assert not violations('import pytest\n\ndef test_x():\n    pytest.skip("no model here")\n')


def test_the_scanner_accepts_a_reason_through_an_import():
    assert not violations('from pytest import skip\n\ndef test_x():\n    skip("no model here")\n')
