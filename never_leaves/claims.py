"""Check the draft against the source, before a human signs it.

This is the second promise of the tool and it exists because of a real
failure. Asked for a two sentence explanation during development, the
model produced a confident and completely wrong answer. A small local
model is not a genius. It is fast, private and free and those are three
real advantages, but it will occasionally state a number it made up.

So the draft is not sent. It is checked. Every number in the draft is
looked up in the notes the tradesperson actually wrote. Anything that
cannot be traced is reported as unsourced, with the figures that hurt
most, meaning money, listed first.

The rule this enforces is the one the whole tool is built around: a claim
without evidence is not a claim.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MONEY = re.compile(r"\$\s?\d[\d,]*(?:\.\d{1,2})?")
# The sign is captured deliberately. A model that turns 400mm into -400mm has
# corrupted a fact and comparing normalised values is how that gets caught.
NUMBER = re.compile(r"(?<![A-Za-z0-9.])(-?\d[\d,]*(?:\.\d+)?)")
PLACEHOLDER = re.compile(r"\[([A-Z][A-Z0-9 _/-]{1,40})\]")
SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*\S)\s*$", re.MULTILINE)


def _normalise(token: str) -> str:
    """Compare numbers by value, so 1,200 and 1200 are the same figure."""
    cleaned = token.replace(",", "").lstrip("$").strip()
    try:
        value = float(cleaned)
    except ValueError:
        return cleaned
    if value == int(value):
        return str(int(value))
    return ("%.2f" % value).rstrip("0").rstrip(".")


def numbers_in(text: str) -> set:
    return {_normalise(m.group(0)) for m in NUMBER.finditer(text or "")}


def money_in(text: str) -> set:
    return {_normalise(m.group(0)) for m in MONEY.finditer(text or "")}


@dataclass
class DraftCheck:
    """What could not be traced back to the source notes."""

    unsourced_money: list = field(default_factory=list)
    unsourced_numbers: list = field(default_factory=list)
    placeholders: list = field(default_factory=list)
    headings: list = field(default_factory=list)
    word_count: int = 0

    @property
    def clean(self) -> bool:
        return not self.unsourced_money and not self.unsourced_numbers

    def to_dict(self) -> dict:
        return {
            "unsourced_money": self.unsourced_money,
            "unsourced_numbers": self.unsourced_numbers,
            "placeholders": self.placeholders,
            "headings": self.headings,
            "word_count": self.word_count,
            "clean": self.clean,
        }

    def lines(self) -> list:
        """Human readable findings, money first because that is what costs."""
        out = []
        if self.unsourced_money:
            out.append(
                "MONEY TO CHECK. These figures are in the draft and are not in your notes: %s"
                % ", ".join("$" + m for m in self.unsourced_money)
            )
        if self.unsourced_numbers:
            out.append(
                "FIGURE TO CHECK. These appear in the draft and not in your notes: %s"
                % ", ".join(self.unsourced_numbers)
            )
        if self.placeholders:
            out.append("FILL THESE IN. %s" % ", ".join("[" + p + "]" for p in self.placeholders))
        if self.clean and not self.placeholders:
            out.append("Every figure in the draft traces back to your notes.")
        return out


def check(draft: str, source: str) -> DraftCheck:
    """Find every claim in the draft that the source cannot support."""
    draft = draft or ""
    source = source or ""

    source_numbers = numbers_in(source)
    draft_money = money_in(draft)

    unsourced_money = sorted(
        (m for m in draft_money if m not in source_numbers),
        key=lambda s: float(s) if s.replace(".", "", 1).isdigit() else 0,
        reverse=True,
    )
    unsourced_numbers = sorted(
        n
        for n in numbers_in(draft)
        if n not in source_numbers and n not in draft_money
    )

    placeholders = sorted({p.strip() for p in PLACEHOLDER.findall(draft)})
    headings = [h.strip() for h in HEADING.findall(draft)]

    return DraftCheck(
        unsourced_money=unsourced_money,
        unsourced_numbers=unsourced_numbers,
        placeholders=placeholders,
        headings=headings,
        word_count=len(draft.split()),
    )
