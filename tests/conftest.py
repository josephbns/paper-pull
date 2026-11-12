"""Shared recording safeguards; normal test runs prohibit network access."""

import pytest


@pytest.fixture
def vcr_config():
    """Remove credentials and contact details before writing any HTTP cassette."""
    return {
        "filter_query_parameters": ["api_key", "mailto", "email"],
        "filter_headers": ["authorization", "user-agent"],
        "decode_compressed_response": True,
    }


@pytest.fixture
def source_settings(monkeypatch):
    """Use inert synthetic credentials for mocked transport tests only."""
    from pathlib import Path

    from pubmon.config import load_config

    monkeypatch.setenv("OPENALEX_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("PUBMON_EMAIL", "synthetic@example.invalid")
    return load_config(Path(__file__).resolve().parents[1])


@pytest.fixture
def api_fixture():
    """Load the hand-written public-shape JSON fixtures."""
    import json
    from pathlib import Path

    def read(name):
        path = Path(__file__).parent / "fixtures/api" / name
        return json.loads(path.read_text())

    return read


@pytest.fixture
def project(tmp_path):
    """Prepare an isolated synthetic project for end-to-end workflow tests."""
    import shutil
    from pathlib import Path

    from pubmon.config import load_config

    root = Path(__file__).resolve().parents[1]
    (tmp_path / "config").mkdir()
    for name in ("settings.example.toml", "arxiv_query.txt"):
        shutil.copyfile(root / "config" / name, tmp_path / "config" / name)
    return load_config(tmp_path)
