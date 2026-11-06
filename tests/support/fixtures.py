import pytest
from fixtures.build import build


@pytest.fixture
def fixtures_dir(tmp_path):
    """The base fixture set, built into a fresh temp folder."""
    target = tmp_path / "fixtures"
    build(target)
    return target
