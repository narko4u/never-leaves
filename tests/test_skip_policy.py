"""Every skip says why.

A skip that says nothing is indistinguishable from a pass nobody tried. G2
says a skip carries its reason, and this test is what keeps that true for
the next skip somebody adds.

The scan is a small resolver, not a grep. It follows imports, aliases,
unpacking and reassignment, and it reads a body in the order it will run,
so a call is judged by what a name meant at that moment, in that scope. A
starred argument is never accepted as a reason, because we cannot see
inside it.
"""

import ast
from pathlib import Path

TESTS = Path(__file__).parent
KINDS = ("pytest", "mark", "skip", "skipif")


def _fresh(inherited=None) -> dict:
    names = {"pytest": {"pytest"}, "mark": set(), "skip": set(), "skipif": set()}
    if inherited:
        for kind in KINDS:
            names[kind] |= inherited[kind]
    return names


def _copy(names) -> dict:
    return {kind: set(names[kind]) for kind in KINDS}


def _ref_kind(node, names):
    """What a name or attribute expression refers to, if anything."""
    if isinstance(node, ast.Name):
        for kind in KINDS:
            if node.id in names[kind]:
                return kind
        return None
    if not isinstance(node, ast.Attribute):
        return None
    base = node.value
    if isinstance(base, ast.Name) and base.id in names["pytest"]:
        if node.attr in ("mark", "skip", "skipif"):
            return node.attr
        return None
    if node.attr == "skipif" and _ref_kind(base, names) == "mark":
        return "skipif"
    return None


def _expr_kind(node, names):
    kind = _ref_kind(node, names)
    return kind if kind in ("skip", "skipif") else None


def _bind_target(target, value, names):
    """Bind one assignment target, including tuple unpacking."""
    if isinstance(target, ast.Name):
        kind = _ref_kind(value, names)
        for kind_name in KINDS:
            names[kind_name].discard(target.id)
        if kind:
            names[kind].add(target.id)
        return
    if isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, (ast.Tuple, ast.List)):
        if len(target.elts) == len(value.elts):
            for element, item in zip(target.elts, value.elts):
                _bind_target(element, item, names)


def _bind_import(node, names):
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name == "pytest":
                names["pytest"].add(alias.asname or "pytest")
        return
    if node.level:
        return
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
        if module == "pytest" and alias.name in ("skip", "skipif", "mark"):
            names[alias.name].add(local)
        elif module == "pytest.mark" and alias.name == "skipif":
            names["skipif"].add(local)


def _states_reason(node: ast.Call) -> bool:
    """An explicit reason keyword, or a positional argument we can see."""
    if any(keyword.arg == "reason" for keyword in node.keywords):
        return True
    return any(not isinstance(arg, ast.Starred) for arg in node.args)


def _check_calls(node, names, bad, name):
    """Judge every call in an expression, as the names stand right now."""
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        kind = _expr_kind(call.func, names)
        if kind == "skipif":
            if not any(keyword.arg == "reason" for keyword in call.keywords):
                bad.append("%s:%d skipif without reason" % (name, call.lineno))
        elif kind == "skip" and not _states_reason(call):
            bad.append("%s:%d skip without a reason" % (name, call.lineno))


def _body(statements, names, bad, name):
    for statement in statements:
        _visit(statement, names, bad, name)


def _visit(statement, names, bad, name):
    if isinstance(statement, (ast.Import, ast.ImportFrom)):
        _bind_import(statement, names)
        return

    if isinstance(statement, ast.Assign):
        _check_calls(statement.value, names, bad, name)
        for target in statement.targets:
            _bind_target(target, statement.value, names)
        return

    if isinstance(statement, ast.AnnAssign):
        if statement.value is not None:
            _check_calls(statement.value, names, bad, name)
            _bind_target(statement.target, statement.value, names)
        return

    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for decorator in statement.decorator_list:
            _check_calls(decorator, names, bad, name)
        for default in list(statement.args.defaults) + [
            item for item in statement.args.kw_defaults if item is not None
        ]:
            _check_calls(default, names, bad, name)
        _body(statement.body, _fresh(names), bad, name)
        return

    if isinstance(statement, ast.ClassDef):
        for decorator in statement.decorator_list:
            _check_calls(decorator, names, bad, name)
        _body(statement.body, _fresh(names), bad, name)
        return

    # Anything else is read in field order, so the test of an `if` is judged
    # before its branches and a `try` before its handlers.
    for _, value in ast.iter_fields(statement):
        if isinstance(value, list):
            for item in value:
                if isinstance(item, ast.stmt):
                    _visit(item, names, bad, name)
                elif isinstance(item, ast.expr):
                    _check_calls(item, names, bad, name)
                elif isinstance(item, ast.ExceptHandler):
                    _body(item.body, names, bad, name)
        elif isinstance(value, ast.expr):
            _check_calls(value, names, bad, name)


def violations(source: str, name: str = "<test>") -> list:
    """Every silent skip in a source string, as file:line text."""
    tree = ast.parse(source, filename=name)
    bad = []
    _body(tree.body, _fresh(), bad, name)
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


def test_the_scanner_follows_an_alias_chain():
    assert violations("import pytest\n\np = pytest\ns = p.skip\n\ndef test_x():\n    s()\n")


def test_the_scanner_follows_a_mark_alias():
    assert violations(
        "import pytest\n\nm = pytest.mark\n\n@m.skipif(True)\ndef test_x():\n    pass\n"
    )


def test_the_scanner_follows_an_unpacked_assignment():
    assert violations(
        "import pytest\n\na, b = pytest, pytest.mark\n\n@b.skipif(True)\ndef test_x():\n    pass\n"
    )


def test_a_reassigned_name_is_taken_at_its_word():
    assert not violations("import pytest\n\nf = pytest.skip\nf = len\n\ndef test_x():\n    f()\n")


def test_a_call_before_a_reassignment_is_still_judged():
    """The binding that was live at the call decides, not the last one."""
    found = violations(
        "import pytest\n\ndef test_a():\n    s = pytest.skip\n    s()\n    s = len\n    s()\n"
    )

    assert len(found) == 1
    assert "skip without a reason" in found[0]


def test_a_local_alias_does_not_leak_into_another_function():
    assert not violations(
        "import pytest\n\ndef a():\n    s = pytest.skip\n\ndef test_b():\n    s()\n"
    )


def test_the_scanner_accepts_a_reason():
    assert not violations('import pytest\n\ndef test_x():\n    pytest.skip("no model here")\n')


def test_the_scanner_accepts_a_reason_through_an_import():
    assert not violations('from pytest import skip\n\ndef test_x():\n    skip("no model here")\n')
