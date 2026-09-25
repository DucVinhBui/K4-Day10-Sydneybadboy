from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
import shutil

import pytest

from core.config import load_settings
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import load_raw_records

PROJECT_DIR = Path(__file__).resolve().parents[1]
RUN_DATE = datetime(2026, 9, 25, tzinfo=UTC)


@pytest.fixture()
def settings(tmp_path):
    """Settings tro vao mot project tam, chi co raw snapshot (khong dung mang)."""
    raw_dir = tmp_path / "data" / "raw"
    raw_dir.mkdir(parents=True)
    for name in ("crossref_response.json", "crossref_records.json"):
        shutil.copy(PROJECT_DIR / "data" / "raw" / name, raw_dir / name)
    return replace(load_settings(tmp_path), refresh_source=False, llm_provider="mock")


@pytest.fixture()
def run_date():
    return RUN_DATE


@pytest.fixture()
def clean_df(settings):
    return build_clean_dataframe(load_raw_records(settings.paths.raw_records_json), RUN_DATE)
