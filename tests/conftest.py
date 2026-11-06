import pytest


@pytest.fixture
def home(tmp_path):
    return tmp_path / "home"
