"""Rendering the finished document.

The output is Markdown, because Markdown is what a person can read, edit
and turn into anything else. The draft is never presented as final. It
arrives stamped as a draft, it carries a short record of how it was
produced and it ends with the list of things the operator still has to
check.
"""

from __future__ import annotations

from datetime import datetime, timezone

BANNER = "> **DRAFT.** Written on your machine by a local model. Read it, fix it, then send it."


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def render(
    doc_type,
    body: str,
    facts: dict,
    draft_check,
    isolation,
    run: dict,
) -> str:
    lines = []
    lines.append("<!-- never-leaves: produced offline by a local model -->")
    lines.append("")
    heading = doc_type.title
    client = facts.get("Client") if facts else None
    if client:
        heading = "%s for %s" % (heading, client)
    lines.append("# %s" % heading)
    lines.append("")
    lines.append(BANNER)
    lines.append("")

    if facts:
        lines.append("| Field | Value |")
        lines.append("|---|---|")
        for key, value in facts.items():
            lines.append("| %s | %s |" % (key.replace("_", " ").title(), value))
        lines.append("")

    lines.append(body.strip())
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Before you send this")
    lines.append("")
    for line in draft_check.lines():
        lines.append("- %s" % line)
    lines.append("")

    lines.append("## Run record")
    lines.append("")
    lines.append("| Item | Value |")
    lines.append("|---|---|")
    lines.append("| Produced | %s |" % run.get("produced_at", _stamp()))
    lines.append("| Document | %s |" % doc_type.key)
    lines.append("| Model | %s |" % run.get("model", "unknown"))
    lines.append("| Model file sha256 | %s |" % (run.get("model_sha256") or "not computed"))
    lines.append("| Notes sha256 | %s |" % run.get("input_sha256", "unknown"))
    lines.append("| Draft sha256 | %s |" % run.get("output_sha256", "unknown"))
    lines.append("| Network | %s |" % ("kernel-isolated, no route" if isolation.isolated else "NOT ISOLATED"))
    lines.append("| Interfaces | %s |" % (", ".join(isolation.interfaces) or "none"))
    lines.append("| Open IP sockets | %d |" % isolation.inet_sockets)
    lines.append("")
    lines.append(
        "This record exists so you can tell later whether this file changed after "
        "you produced it. It is written to your disk and to nowhere else."
    )
    lines.append("")
    return "\n".join(lines)
