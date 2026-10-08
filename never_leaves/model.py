"""Local model loading.

There is no model server here, no port and no socket. The weights are
mapped straight from a GGUF file that is already on the disk, inside this
process. That is the whole reason the offline guarantee is cheap to make:
with no server there is nothing to connect to and with no connection
there is nothing to leak.

Any GGUF works. The model is a parameter, not a dependency, which is the
practical part of the argument for open weights.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass
from pathlib import Path

OLLAMA_ROOT = Path.home() / ".ollama" / "models"
OLLAMA_MANIFESTS = OLLAMA_ROOT / "manifests"
OLLAMA_BLOBS = OLLAMA_ROOT / "blobs"
DEFAULT_OLLAMA_MODEL = "qwen3:4b-instruct"

SEARCH_DIRS = (
    Path.home() / ".cache" / "never-leaves" / "models",
    Path.home() / "models",
    Path.cwd() / "models",
)


class NoModelFound(RuntimeError):
    """Raised when we cannot find any local weights to run."""


@dataclass
class ModelRef:
    name: str
    path: Path
    origin: str
    size_bytes: int

    def to_dict(self) -> dict:
        d = asdict(self)
        d["path"] = str(self.path)
        return d

    def describe(self) -> str:
        return "%s (%.1f GB, %s) at %s" % (
            self.name,
            self.size_bytes / 1e9,
            self.origin,
            self.path,
        )


def _manifest_files() -> list:
    if not OLLAMA_MANIFESTS.exists():
        return []
    return sorted(OLLAMA_MANIFESTS.rglob("*"))


def resolve_ollama(name: str) -> ModelRef:
    """Turn an ollama model name such as qwen3:4b-instruct into its blob.

    ollama keeps a manifest per model and the manifest names the weight
    layer. Reading the manifest, rather than guessing at filenames, is how
    we get the right file even when two blobs are nearly the same size.
    """
    if ":" in name:
        repo, tag = name.split(":", 1)
    else:
        repo, tag = name, "latest"
    suffix = Path(repo) / tag

    for manifest in _manifest_files():
        if manifest.name == tag and str(manifest.parent).endswith(str(Path(repo))):
            ref = _blob_from_manifest(manifest, name)
            if ref:
                return ref
    # Fall back to a suffix match, which covers odd registry prefixes.
    for manifest in _manifest_files():
        if str(manifest).endswith(str(suffix)):
            ref = _blob_from_manifest(manifest, name)
            if ref:
                return ref
    raise NoModelFound("no ollama manifest found for %s" % name)


def _blob_from_manifest(manifest: Path, name: str) -> ModelRef:
    import json

    try:
        data = json.loads(manifest.read_text())
    except (OSError, ValueError):
        return None
    for layer in data.get("layers", []):
        if layer.get("mediaType") == "application/vnd.ollama.image.model":
            blob = OLLAMA_BLOBS / layer["digest"].replace(":", "-")
            if blob.exists():
                return ModelRef(
                    name=name,
                    path=blob,
                    origin="ollama",
                    size_bytes=blob.stat().st_size,
                )
    return None


def find_ggufs() -> list:
    found = []
    for directory in SEARCH_DIRS:
        if directory.is_dir():
            found.extend(sorted(directory.glob("*.gguf")))
    return found


def discover(preferred: str = None) -> ModelRef:
    """Find usable weights, in order of how explicit the operator was."""
    explicit = preferred or os.environ.get("NEVER_LEAVES_MODEL")
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return ModelRef(path.stem, path, "file", path.stat().st_size)
        return resolve_ollama(explicit)

    try:
        return resolve_ollama(DEFAULT_OLLAMA_MODEL)
    except NoModelFound:
        pass

    ggufs = find_ggufs()
    if ggufs:
        path = ggufs[0]
        return ModelRef(path.stem, path, "file", path.stat().st_size)

    for manifest in _manifest_files():
        ref = _blob_from_manifest(manifest, manifest.name)
        if ref:
            return ref

    raise NoModelFound(
        "no local weights found. Point NEVER_LEAVES_MODEL at a .gguf file, "
        "pass --model or pull a model with ollama."
    )


def fingerprint(ref: ModelRef, full: bool = False) -> dict:
    """Identify the exact weights used for this run.

    Size and modification time are always recorded because they are free.
    The full digest is opt in, because hashing several gigabytes costs more
    time than most jobs take.
    """
    stat = ref.path.stat()
    out = {
        "name": ref.name,
        "origin": ref.origin,
        "size_bytes": stat.st_size,
        "mtime": int(stat.st_mtime),
        "sha256": None,
    }
    if full:
        digest = hashlib.sha256()
        with open(ref.path, "rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        out["sha256"] = digest.hexdigest()
    return out


def load(ref: ModelRef, n_ctx: int = 4096, n_threads: int = None):
    """Load the weights into this process. No server, no pipeline, no port."""
    from llama_cpp import Llama

    threads = n_threads or max(1, (os.cpu_count() or 4) - 2)
    return Llama(
        model_path=str(ref.path),
        n_ctx=n_ctx,
        n_threads=threads,
        n_batch=256,
        verbose=False,
    )


def generate(llm, system: str, user: str, max_tokens: int = 700,
             temperature: float = 0.2) -> dict:
    out = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    usage = out.get("usage") or {}
    return {
        "text": (out["choices"][0]["message"]["content"] or "").strip(),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
    }
