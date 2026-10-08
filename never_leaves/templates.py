"""Document types.

A small local model does not write a professional document on its own. It
writes a decent first draft if the job is narrow and the shape is fixed
for it. So the shape is fixed here, in code and the model is only asked
to fill it in.

The system prompt carries one rule above all others and it is the rule
that keeps a tradie out of trouble: never invent a number. A missing rate
becomes a placeholder and the tool lists every placeholder at the end so
nothing goes out to a client with a hole in it.
"""

from __future__ import annotations

from dataclasses import dataclass

PLACEHOLDER_EXAMPLES = "[RATE] [TOTAL] [CLIENT NAME] [SITE ADDRESS] [DATE] [TERMS]"

_BASE_RULES = """You are drafting for an Australian tradesperson who is standing on a job site.

Rules, in order of importance:
1. Never invent a number. Not a price, a rate, a quantity, a measurement, a date or a duration. If you need a figure and it is not given to you, write it as a placeholder in capitals inside square brackets, for example {examples}.
2. Never invent a person, a company, an address, a licence number or a legal claim.
3. Use only the facts in the notes you are given. Do not add plausible detail that is not there.
4. If the notes are too thin to fill a section, write the placeholder or state plainly what is missing. A short honest document beats a long invented one.
5. Write in plain Australian English. Short sentences. No marketing language.
6. Output Markdown only. Use exactly the headings you are given, in the same order and nothing before the first heading.
""".format(examples=PLACEHOLDER_EXAMPLES)


@dataclass
class DocType:
    key: str
    title: str
    sections: list
    guidance: str

    @property
    def system(self) -> str:
        return _BASE_RULES

    def instruction(self, note: str, facts: dict) -> str:
        lines = ["Produce a %s." % self.title, "", "Required headings, in order:"]
        lines += ["## %s" % s for s in self.sections]
        lines += ["", "How to fill them:", self.guidance]
        if facts:
            lines += ["", "Known job details. Treat these as the only true facts:",
                      "```json", __import__("json").dumps(facts, indent=2), "```"]
        lines += ["", "The notes as written by the tradesperson:", "```", note.strip(), "```"]
        return "\n".join(lines)


QUOTE = DocType(
    key="quote",
    title="Quote",
    sections=[
        "Scope of work",
        "What is included",
        "What is excluded",
        "Price",
        "Timeframe",
        "Terms",
    ],
    guidance="""Scope of work: describe the work as the notes describe it, nothing more.
What is included: only what the notes say is included.
What is excluded: only what the notes say is excluded. If the notes do not say, write [EXCLUSIONS].
Price: a Markdown table whose first row is exactly | Item | Rate | Total |. One row per line item. Put [RATE] and [TOTAL] in the cells for any figure the notes do not supply. Never place a placeholder in the header row and never compute a subtotal from invented rates.
Timeframe: only if the notes give one, otherwise [TIMEFRAME].
Terms: two or three plain sentences covering a deposit, variations and how the client accepts. Use [DEPOSIT] if no figure is given.""",
)

REPORT = DocType(
    key="report",
    title="Site report",
    sections=[
        "Site and attendance",
        "Observations",
        "Work carried out",
        "Findings",
        "Recommended next steps",
        "Attachments and evidence",
    ],
    guidance="""Site and attendance: where and when, only if stated, otherwise placeholders.
Observations: what was seen, in plain factual sentences. No diagnosis the notes do not support.
Work carried out: only work the notes say was done.
Findings: what needs attention. If the notes do not identify a cause, say the cause was not determined.
Recommended next steps: concrete, one per line.
Attachments and evidence: list only photographs or documents the notes mention, otherwise write none recorded.""",
)

TYPES = {t.key: t for t in (QUOTE, REPORT)}


def get(key: str) -> DocType:
    if key not in TYPES:
        raise KeyError("unknown document type %r, choose from %s" % (key, ", ".join(TYPES)))
    return TYPES[key]
