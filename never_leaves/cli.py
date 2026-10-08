"""Command line entry point.

One command does the whole job. It proves it cannot reach a network,
loads local weights, drafts the document, checks every figure in the
draft against your notes, writes the file and records what it did.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import claims, document, isolation, ledger, model, templates

BANNER = "=" * 62
WARN = "!" * 62


def _proof_block(report: isolation.IsolationReport) -> str:
    state = "yes" if report.isolated else "NO"
    lines = [
        BANNER,
        " NEVER LEAVES - proof of isolation",
        BANNER,
        "  isolated            %s" % state,
        "  mechanism           %s" % report.mechanism,
        "  interfaces          %s" % (", ".join(report.interfaces) or "none"),
        "  interfaces up       %s" % (", ".join(report.interfaces_up) or "none"),
        "  routes              %d" % len(report.routes),
        "  open IP sockets     %d" % report.inet_sockets,
        "  checked at          %s" % report.checked_at,
        BANNER,
        "  %s" % report.detail,
        BANNER,
    ]
    return "\n".join(lines)


def _die(message: str, code: int = 2):
    print("error: %s" % message, file=sys.stderr)
    raise SystemExit(code)


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", help="path to a .gguf file or an ollama model name")
    parser.add_argument("--out", help="where to write the document")
    parser.add_argument("--ledger", help="path to the run ledger")
    parser.add_argument("--threads", type=int, help="CPU threads for inference")
    parser.add_argument("--max-tokens", type=int, default=700, help="draft length ceiling")
    parser.add_argument("--json", action="store_true", help="print a machine readable result")
    parser.add_argument("--full-fingerprint", action="store_true",
                        help="hash the whole model file, which is slow but exact")
    parser.add_argument("--no-isolate", action="store_true",
                        help="do not enter a namespace. The guarantee is lost and will be reported as lost.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="never-leaves",
        description="Draft real documents offline, from notes, on a local open-weight model.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    for key in ("quote", "report"):
        p = sub.add_parser(key, help="draft a %s from notes" % key)
        p.add_argument("note", help="path to a text file of notes or - to read stdin")
        p.add_argument("--client", default=None, help="client name, if known")
        p.add_argument("--site", default=None, help="site address, if known")
        p.add_argument("--job", default=None, help="your job reference, if you use one")
        _common(p)

    p_check = sub.add_parser("check", help="prove the isolation and exit")
    _common(p_check)

    p_models = sub.add_parser("models", help="list local weights found on this machine")
    _common(p_models)

    p_runs = sub.add_parser("runs", help="show recent runs from the local ledger")
    p_runs.add_argument("-n", type=int, default=10, help="how many runs to show")
    _common(p_runs)

    return parser


def _read_note(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    target = Path(path).expanduser()
    if not target.is_file():
        _die("notes file not found: %s" % target)
    return target.read_text(encoding="utf-8", errors="replace")


def _facts(args) -> dict:
    facts = {}
    for key in ("client", "site", "job"):
        value = getattr(args, key, None)
        if value:
            facts[key.replace("job", "job reference").title()] = value
    return facts


def _draft(args, doc_type, note: str, facts: dict):
    ref = model.discover(args.model)
    print("  model               %s" % ref.describe())
    if ref.notice:
        print(WARN)
        print(" NOTE: %s" % ref.notice)
        print(WARN)
    print(BANNER)
    print("  loading weights into this process...")
    try:
        llm = model.load(ref, n_threads=args.threads)
    except Exception as exc:  # noqa: BLE001 - the loader's failure mode is its own
        _die(model.load_hint(ref, exc))
    print("  drafting...")
    result = model.generate(
        llm,
        doc_type.system,
        doc_type.instruction(note, facts),
        max_tokens=args.max_tokens,
    )
    return ref, result


def _run_document(args, doc_type):
    report = isolation.ensure_isolated(sys.argv[1:], allow_unverified=args.no_isolate)
    print(_proof_block(report))
    if not report.isolated:
        print(WARN)
        print(" WARNING: isolation was not established. This run is NOT private.")
        print(WARN)

    note = _read_note(args.note)
    facts = _facts(args)
    ref, result = _draft(args, doc_type, note, facts)

    draft_check = claims.check(result["text"], note)
    run = {
        "model": ref.name,
        "model_sha256": model.fingerprint(ref, full=args.full_fingerprint)["sha256"],
        "input_sha256": ledger.sha256_text(note),
        "output_sha256": ledger.sha256_text(result["text"]),
        "prompt_tokens": result["prompt_tokens"],
        "completion_tokens": result["completion_tokens"],
    }

    rendered = document.render(doc_type, result["text"], facts, draft_check, report, run)

    out = Path(args.out).expanduser() if args.out else Path(
        "%s.%s.md" % (Path(args.note).stem if args.note != "-" else "stdin", doc_type.key)
    )
    out.write_text(rendered, encoding="utf-8")

    final = isolation.inspect()
    record = ledger.build_record(doc_type, run, draft_check, final, args.note)
    record["output_path"] = str(out)
    ledger_path = ledger.append(record, Path(args.ledger) if args.ledger else None)

    if args.json:
        print(json.dumps({
            "output": str(out),
            "ledger": str(ledger_path),
            "isolation": final.to_dict(),
            "check": draft_check.to_dict(),
            "run": run,
        }, indent=2))
        return 0

    print()
    print("  document            %s" % out)
    print("  words               %d" % draft_check.word_count)
    print("  ledger              %s" % ledger_path)
    print()
    print("  BEFORE YOU SEND IT")
    for line in draft_check.lines():
        print("   - %s" % line)
    print()
    print("  isolation re-checked after drafting: %s"
          % ("still isolated, still no route" if final.isolated else "PROBLEM, see ledger"))
    return 0


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in ("quote", "report"):
        return _run_document(args, templates.get(args.command))

    if args.command == "check":
        report = isolation.ensure_isolated(sys.argv[1:], allow_unverified=args.no_isolate)
        print(_proof_block(report))
        if args.json:
            print(report.to_json())
        return 0 if report.isolated else 1

    if args.command == "models":
        # No isolation banner here: this command never drafts anything, so it
        # makes no privacy claim. Inspecting the network would report "NO"
        # and read as a failure of the tool rather than what it is, which is
        # a listing that does not need a namespace.
        print(BANNER)
        print(" NEVER LEAVES - local weights")
        print(BANNER)
        try:
            ref = model.discover(args.model)
            print("  selected            %s" % ref.describe())
            if ref.notice:
                print("  note                %s" % ref.notice)
        except model.NoModelFound as exc:
            print("  selected            none: %s" % exc)
        found = model.find_ggufs()
        print("  gguf files found    %d" % len(found))
        for path in found:
            print("   - %s" % path)
        return 0

    if args.command == "runs":
        records = ledger.read_all(Path(args.ledger) if args.ledger else None)
        if not records:
            print("no runs recorded yet")
            return 0
        for record in records[-args.n:]:
            print("%s  %-7s  %4s words  money-flags=%d  %s" % (
                record.get("at", "?"),
                record.get("document", "?"),
                record.get("words", "?"),
                len(record.get("unsourced_money") or []),
                record.get("output_path", ""),
            ))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except isolation.IsolationUnavailable as exc:
        _die(str(exc))
