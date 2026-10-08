"""The local run ledger.

One line of JSON per run, appended to a file in your home directory. It
is deliberately small and deliberately local. Its purpose is ordinary: a
month later you should be able to answer "what did I produce, from what,
with which weights" without keeping the original notes around.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LEDGER = Path.home() / ".local" / "share" / "never-leaves" / "runs.jsonl"


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def append(record: dict, path: Path = None) -> Path:
    target = Path(path).expanduser() if path else DEFAULT_LEDGER
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True)
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    return target


def read_all(path: Path = None) -> list:
    target = Path(path).expanduser() if path else DEFAULT_LEDGER
    if not target.exists():
        return []
    records = []
    for line in target.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    return records


def build_record(doc_type, run: dict, draft_check, isolation, input_path: str) -> dict:
    return {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "document": doc_type.key,
        "source": input_path,
        "input_sha256": run.get("input_sha256"),
        "output_sha256": run.get("output_sha256"),
        "model": run.get("model"),
        "model_sha256": run.get("model_sha256"),
        "prompt_tokens": run.get("prompt_tokens"),
        "completion_tokens": run.get("completion_tokens"),
        "words": draft_check.word_count,
        "unsourced_money": draft_check.unsourced_money,
        "unsourced_numbers": draft_check.unsourced_numbers,
        "placeholders": draft_check.placeholders,
        "isolated": isolation.isolated,
        "interfaces": isolation.interfaces,
        "open_ip_sockets": isolation.inet_sockets,
    }
