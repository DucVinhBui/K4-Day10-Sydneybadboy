from __future__ import annotations

from dataclasses import replace

from ingestion.cleaning import CLEAN_COLUMNS, build_clean_dataframe
from ingestion.crossref import load_raw_records


def test_clean_dataframe_shape_and_columns(clean_df):
    assert len(clean_df) == 24
    assert list(clean_df.columns) == CLEAN_COLUMNS
    assert clean_df["paper_id"].is_unique
    assert clean_df["published"].is_monotonic_decreasing


def test_text_for_embedding_has_five_parts(clean_df):
    for text in clean_df["text_for_embedding"]:
        lines = text.split("\n")
        assert [line.split(":")[0] for line in lines] == ["Title", "Authors", "Published", "Categories", "Summary"]


def test_age_days_is_relative_to_run_date(clean_df):
    row = clean_df[clean_df["paper_id"] == "10.1145/3637528.3671805"].iloc[0]
    assert row["published"] == "2026-03-28"
    assert row["age_days"] == 181


def test_dedup_and_filter_bad_rows(settings, run_date):
    records = load_raw_records(settings.paths.raw_records_json)
    duplicated = records + [records[0], replace(records[1], paper_id="10.9/empty", summary="  ")]
    df = build_clean_dataframe(duplicated, run_date)
    assert len(df) == 24
    assert "10.9/empty" not in set(df["paper_id"])
