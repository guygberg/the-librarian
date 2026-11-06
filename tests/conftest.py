import pytest

from support.fixtures import fixtures_dir  # noqa: F401


@pytest.fixture(autouse=True)
def _no_real_claude_sessions(tmp_path, monkeypatch):
    """The default Claude projects folder is under HOME; tests must never import the
    developer's own sessions."""
    monkeypatch.setenv("HOME", str(tmp_path / "no-home"))


@pytest.fixture
def home(tmp_path):
    return tmp_path / "home"
