"""Templates, rendering and the ledger."""

import json

import pytest

from never_leaves import claims, document, isolation, ledger, templates


def _check(draft, source="notes with 6 downlights and 18m of cable"):
    return claims.check(draft, source)


def test_every_document_type_is_complete():
    for key, doc_type in templates.TYPES.items():
        assert doc_type.key == key
        assert doc_type.sections, key
        assert doc_type.guidance, key
        assert "Never invent a number" in doc_type.system


def test_unknown_document_type_is_refused():
    with pytest.raises(KeyError):
        templates.get("invoice")


def test_instruction_carries_the_note_and_the_facts():
    text = templates.get("quote").instruction("six downlights", {"Client": "Jenna"})
    assert "six downlights" in text
    assert "Jenna" in text
    assert "## Price" in text


def test_instruction_works_without_facts():
    text = templates.get("report").instruction("nothing much happened", {})
    assert "nothing much happened" in text
    assert "Known job details" not in text


def test_render_marks_the_draft_and_records_the_run():
    doc_type = templates.get("quote")
    report = isolation.inspect()
    rendered = document.render(
        doc_type,
        "## Scope of work\n\nReplace six downlights.",
        {"Client": "Jenna"},
        _check("## Scope of work\n\nReplace 6 downlights."),
        report,
        {"model": "test-model", "input_sha256": "a" * 64, "output_sha256": "b" * 64},
    )
    assert "DRAFT" in rendered
    assert "# Quote for Jenna" in rendered
    assert "## Before you send this" in rendered
    assert "## Run record" in rendered
    assert "test-model" in rendered


def test_render_states_the_network_position_truthfully():
    doc_type = templates.get("quote")
    rendered = document.render(
        doc_type, "body", {}, _check("body"), isolation.inspect(), {}
    )
    if isolation.inspect().isolated:
        assert "kernel-isolated, no route" in rendered
    else:
        assert "NOT ISOLATED" in rendered


def test_ledger_appends_and_reads_back(tmp_path):
    path = tmp_path / "runs.jsonl"
    ledger.append({"document": "quote", "words": 10}, path)
    ledger.append({"document": "report", "words": 20}, path)
    records = ledger.read_all(path)
    assert [r["document"] for r in records] == ["quote", "report"]


def test_ledger_ignores_a_corrupt_line(tmp_path):
    path = tmp_path / "runs.jsonl"
    path.write_text('{"document": "quote"}\nnot json at all\n{"document": "report"}\n')
    assert len(ledger.read_all(path)) == 2


def test_ledger_missing_file_reads_empty(tmp_path):
    assert ledger.read_all(tmp_path / "nothing.jsonl") == []


def test_sha256_text_is_stable_and_distinct():
    assert ledger.sha256_text("a") == ledger.sha256_text("a")
    assert ledger.sha256_text("a") != ledger.sha256_text("b")
    assert len(ledger.sha256_text("a")) == 64


def test_run_record_has_the_fields_we_promise():
    doc_type = templates.get("quote")
    run = {"model": "m", "input_sha256": "x", "output_sha256": "y"}
    record = ledger.build_record(
        doc_type, run, _check("body"), isolation.inspect(), "note.txt"
    )
    for key in (
        "at", "document", "source", "input_sha256", "output_sha256",
        "model", "words", "unsourced_money", "placeholder" + "s",
        "isolated", "open_ip_sockets",
    ):
        assert key in record, key
    json.dumps(record)
