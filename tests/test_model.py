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


def _write_store(root, repo, tag, blob_name, payload=b"GGUF" + b"\x00" * 2048):
    manifests = root / "manifests" / "registry.ollama.ai" / "library" / repo
    manifests.mkdir(parents=True, exist_ok=True)
    blobs = root / "blobs"
    blobs.mkdir(parents=True, exist_ok=True)
    blob = blobs / blob_name
    blob.write_bytes(payload)
    (manifests / tag).write_text(
        '{"layers": [{"mediaType": "application/vnd.ollama.image.model",'
        ' "digest": "%s"}]}' % blob_name.replace("-", ":", 1)
    )
    return blob


def test_a_store_outside_the_home_directory_is_searched(tmp_path, monkeypatch):
    """A system install keeps its weights somewhere other than the home dir."""
    store = tmp_path / "system-ollama"
    _write_store(store, "testonly", "1b", "sha256-cafebabe")
    monkeypatch.setenv("OLLAMA_MODELS", str(store))
    assert store in model.ollama_roots()


def test_a_model_outside_the_home_directory_resolves(tmp_path, monkeypatch):
    """Found in the store, with the blob read from that same store."""
    store = tmp_path / "system-ollama"
    blob = _write_store(store, "testonly", "1b", "sha256-cafebabe")
    monkeypatch.setenv("OLLAMA_MODELS", str(store))
    ref = model.resolve_ollama("testonly:1b")
    assert ref.path == blob
    assert ref.size_bytes == 2052
    assert ref.origin == "ollama"


def test_a_digest_is_read_from_its_own_store(tmp_path, monkeypatch):
    """A digest in one store must not be looked up in another one."""
    store = tmp_path / "other-ollama"
    _write_store(store, "testonly", "2b", "sha256-cafecafe")
    (store / "blobs" / "sha256-cafecafe").unlink()
    monkeypatch.setenv("OLLAMA_MODELS", str(store))
    with pytest.raises(model.NoModelFound):
        model.resolve_ollama("testonly:2b")


def test_a_substituted_model_is_announced(monkeypatch):
    """If the default is missing, whatever gets used instead is said out loud."""
    if not model._manifest_files() and not model.find_ggufs():
        pytest.skip("no local weights on this machine")
    # Both halves of the default have to be absent for anything used in its
    # place to count as a substitution.
    monkeypatch.setattr(model, "DEFAULT_OLLAMA_MODEL", "definitely-not-installed:latest")
    monkeypatch.setattr(model, "DEFAULT_MODEL_STEM", "definitely-not-downloaded")
    ref = model.discover()
    assert ref.notice
    assert "definitely-not-installed" in ref.notice


def test_the_default_model_is_looked_for_as_a_file_first(tmp_path, monkeypatch):
    """A loose GGUF of the default model wins over the ollama tag.

    ollama's Gemma 3 export does not load on this loader, so the file form of
    the same model is the one worth preferring. It is the default, not a
    substitute, so nothing is announced.
    """
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    expected = models_dir / "gemma-3-4b-it-Q4_K_M.gguf"
    expected.write_bytes(b"GGUF" + b"\x00" * 64)
    monkeypatch.setattr(model, "SEARCH_DIRS", (models_dir,))
    monkeypatch.setattr(model, "DEFAULT_MODEL_STEM", "gemma-3-4b-it")
    ref = model.discover()
    assert ref.path == expected
    assert ref.origin == "file"
    assert ref.notice is None


def test_a_file_that_is_not_the_default_model_is_still_a_substitution(tmp_path, monkeypatch):
    """Some other loose GGUF is a substitute and must be announced as one."""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    other = models_dir / "some-other-model.gguf"
    other.write_bytes(b"GGUF" + b"\x00" * 64)
    monkeypatch.setattr(model, "SEARCH_DIRS", (models_dir,))
    monkeypatch.setattr(model, "DEFAULT_MODEL_STEM", "gemma-3-4b-it")
    monkeypatch.setattr(model, "DEFAULT_OLLAMA_MODEL", "definitely-not-installed:latest")
    monkeypatch.setattr(model, "_manifest_files", lambda: [])
    ref = model.discover()
    assert ref.path == other
    assert ref.notice
    assert "some-other-model" in ref.notice
