import pytest

from support.fixtures import fixtures_dir  # noqa: F401


@pytest.fixture
def home(tmp_path):
    return tmp_path / "home"
