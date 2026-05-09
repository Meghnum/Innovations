# presentation-builder/tests/conftest.py
from pathlib import Path
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
GOLDEN_DIR = Path(__file__).parent / "golden"

@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR

@pytest.fixture
def golden_dir() -> Path:
    return GOLDEN_DIR

@pytest.fixture
def sample_csv(fixtures_dir) -> Path:
    return fixtures_dir / "sample.csv"

@pytest.fixture
def sample_xlsx(fixtures_dir) -> Path:
    return fixtures_dir / "sample_clean.xlsx"

@pytest.fixture
def sample_pdf(fixtures_dir) -> Path:
    return fixtures_dir / "sample.pdf"

@pytest.fixture
def sample_pii(fixtures_dir) -> Path:
    return fixtures_dir / "sample_pii.csv"

@pytest.fixture
def sample_messy(fixtures_dir) -> Path:
    return fixtures_dir / "sample_messy.xlsx"
