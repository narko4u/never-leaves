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
SYSTEM_OLLAMA_ROOT = Path("/usr/share/ollama/.ollama/models")
OLLAMA_MANIFESTS = OLLAMA_ROOT / "manifests"
OLLAMA_BLOBS = OLLAMA_ROOT / "blobs"
DEFAULT_OLLAMA_MODEL = "gemma3:4b"
# The same model as a loose GGUF file. A file on disk is the form whose
# loadability we can actually verify, so it is tried first.
DEFAULT_MODEL_STEM = "gemma-3-4b-it"

SEARCH_DIRS = (
    Path.home() / ".cache" / "never-leaves" / "models",
    Path.home() / "models",
    Path.cwd() / "models",
)


def ollama_roots() -> list:
    """Every place ollama might keep weights, most specific first.

    A per user install keeps them under the home directory. The system
    service, which is what the official installer sets up on Linux, keeps
    them under /usr/share/ollama where any user can read them. Reading
    only the home directory finds nothing at all on such a machine, and
    finding nothing is worse than being slow: the search moves on and
    takes whatever it finds next.
    """
    candidates = []
    override = os.environ.get("OLLAMA_MODELS")
    if override:
        candidates.append(Path(override).expanduser())
    candidates.append(OLLAMA_ROOT)
    candidates.append(SYSTEM_OLLAMA_ROOT)
    candidates.append(Path("/var/lib/ollama/models"))
    roots = []
    seen = set()
    for path in candidates:
        key = str(path)
        if key not in seen and path.is_dir():
            seen.add(key)
            roots.append(path)
    return roots


class NoModelFound(RuntimeError):
    """Raised when we cannot find any local weights to run."""


@dataclass
class ModelRef:
    name: str
    path: Path
    origin: str
    size_bytes: int
    notice: str = None

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
    """Every manifest file, across every root ollama might be using."""
    found = []
    for root in ollama_roots():
        manifests = root / "manifests"
        if manifests.is_dir():
            found.extend(path for path in manifests.rglob("*") if path.is_file())
    return sorted(found)


def _blobs_dir(manifest: Path) -> Path:
    """The blob store belonging to the root this manifest came from.

    Two roots can hold weights at once and a blob digest only means
    anything inside its own store, so the manifest decides where to look.
    """
    for parent in manifest.parents:
        if parent.name == "manifests":
            return parent.parent / "blobs"
    return OLLAMA_BLOBS


def resolve_ollama(name: str) -> ModelRef:
    """Turn an ollama model name such as gemma3:4b into its blob.

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
            blob = _blobs_dir(manifest) / layer["digest"].replace(":", "-")
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

    # The default model, as a loose GGUF, is tried before the ollama tag.
    # ollama's own Gemma 3 export omits a hyperparameter that this loader
    # requires, so resolving the tag can hand back a file that will not
    # load at all.
    for path in find_ggufs():
        if path.stem.startswith(DEFAULT_MODEL_STEM):
            return ModelRef(path.stem, path, "file", path.stat().st_size)

    try:
        return resolve_ollama(DEFAULT_OLLAMA_MODEL)
    except NoModelFound:
        pass

    ggufs = find_ggufs()
    if ggufs:
        path = ggufs[0]
        return ModelRef(
            path.stem,
            path,
            "file",
            path.stat().st_size,
            notice="%s is not installed. Using the .gguf at %s instead."
            % (DEFAULT_OLLAMA_MODEL, path),
        )

    # Last resort: anything ollama happens to have. This is a
    # substitution, so it is announced rather than quietly swapped in.
    available = []
    for manifest in _manifest_files():
        label = "%s:%s" % (manifest.parent.name, manifest.name)
        ref = _blob_from_manifest(manifest, label)
        if ref:
            available.append(ref)
    if available:
        available.sort(key=lambda ref: ref.name)
        ref = available[0]
        ref.notice = (
            "%s is not installed. Using %s from a local ollama store instead."
            % (DEFAULT_OLLAMA_MODEL, ref.name)
        )
        return ref

    raise NoModelFound(
        "no local weights found. Point NEVER_LEAVES_MODEL at a .gguf file, "
        "pass --model, or pull a model with ollama."
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


def load_hint(ref: ModelRef, exc: Exception) -> str:
    """Turn a loader failure into something the operator can act on.

    A traceback out of a C library tells a tradesperson nothing. The one
    failure worth naming is the ollama Gemma 3 export, because it looks
    like a working install and is not one.
    """
    detail = str(exc)
    lines = [
        "could not load %s" % ref.path,
        "  the loader said: %s" % detail,
    ]
    looks_like_gemma3 = "gemma3" in detail or "gemma3" in ref.name
    if ref.origin == "ollama" and looks_like_gemma3:
        lines += [
            "",
            "  This is a known incompatibility, not a fault in your setup.",
            "  ollama's Gemma 3 export omits gemma3.attention.layer_norm_rms_epsilon,",
            "  which this loader treats as required. A GGUF converted by the llama.cpp",
            "  toolchain carries the key and loads. Use one of these instead:",
            "",
            "    curl -L -o ~/models/gemma-3-4b-it-Q4_K_M.gguf \\",
            "      https://huggingface.co/bartowski/google_gemma-3-4b-it-GGUF/resolve/main/google_gemma-3-4b-it-Q4_K_M.gguf",
            "",
            "  Or pass any other model: never-leaves quote notes.txt --model /path/to.gguf",
        ]
    return "\n".join(lines)


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
