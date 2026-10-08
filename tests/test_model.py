"""Model discovery and fingerprinting.

The load and generate test is slow, so it only runs when
NEVER_LEAVES_SLOW=1 is set. Everything else is fast.
"""

import os

import pytest

from never_leaves import model


def _have_ollama_model():
    try:
        model.resolve_ollama(model.DEFAULT_OLLAMA_MODEL)
        return True
    except model.NoModelFound:
        return False


def test_ollama_manifest_resolves_to_a_real_blob():
    if not _have_ollama_model():
        pytest.skip("no ollama model on this machine")
    ref = model.resolve_ollama(model.DEFAULT_OLLAMA_MODEL)
    assert ref.path.is_file()
    assert ref.size_bytes > 100_000_000
    assert ref.origin == "ollama"


def test_the_blob_is_actually_gguf():
    if not _have_ollama_model():
        pytest.skip("no ollama model on this machine")
    ref = model.resolve_ollama(model.DEFAULT_OLLAMA_MODEL)
    with open(ref.path, "rb") as handle:
        assert handle.read(4) == b"GGUF"


def test_an_explicit_file_wins(tmp_path):
    fake = tmp_path / "tiny.gguf"
    fake.write_bytes(b"GGUF" + b"\x00" * 64)
    ref = model.discover(str(fake))
    assert ref.path == fake
    assert ref.origin == "file"
    assert ref.size_bytes == 68


def test_fingerprint_records_size_without_hashing(tmp_path):
    fake = tmp_path / "tiny.gguf"
    fake.write_bytes(b"GGUF" + b"\x00" * 64)
    ref = model.discover(str(fake))
    info = model.fingerprint(ref, full=False)
    assert info["size_bytes"] == 68
    assert info["sha256"] is None


def test_fingerprint_can_be_exact(tmp_path):
    fake = tmp_path / "tiny.gguf"
    fake.write_bytes(b"GGUF" + b"\x00" * 64)
    ref = model.discover(str(fake))
    info = model.fingerprint(ref, full=True)
    assert len(info["sha256"]) == 64


def test_missing_model_raises_a_clear_error(tmp_path):
    with pytest.raises(model.NoModelFound):
        model.resolve_ollama("definitely-not-installed:latest")


@pytest.mark.skipif(
    os.environ.get("NEVER_LEAVES_SLOW") != "1",
    reason="set NEVER_LEAVES_SLOW=1 to run inference",
)
def test_real_inference_returns_text():
    ref = model.discover()
    llm = model.load(ref, n_ctx=512)
    result = model.generate(llm, "You are terse.", "Say the word ready.", max_tokens=16)
    assert result["text"]
    assert result["completion_tokens"] >= 1
