from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def minimal(fixtures: Path) -> Path:
    return fixtures / "valid" / "minimal"


@pytest.fixture
def full_featured(fixtures: Path) -> Path:
    return fixtures / "valid" / "full-featured"


@pytest.fixture
def sub_agent(fixtures: Path) -> Path:
    return fixtures / "valid" / "sub-agent"
