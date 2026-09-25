from __future__ import annotations

from core.utils import read_json
from ingestion.corruption import corrupt_clean_dataframe
from observability.quality import build_freshness_report, run_data_quality_checks


def test_quality_gate_passes_on_clean_data(clean_df, settings):
    report = run_data_quality_checks(clean_df, settings, "baseline")
    assert report["success"] is True
    assert report["expectations_total"] >= 6
    assert (settings.paths.quality_dir / "baseline_quality_report.json").exists()
    types = {check["expectation"] for check in report["checks"]}
    assert {
        "expect_table_row_count_to_be_between",
        "expect_column_values_to_not_be_null",
        "expect_column_values_to_be_unique",
        "expect_column_value_lengths_to_be_between",
    } <= types


def test_freshness_report_on_clean_data(clean_df, settings):
    report = build_freshness_report(clean_df, settings, settings.paths.freshness_report)
    assert report["total_rows"] == 24
    assert report["stale_rows"] == 1
    assert report["is_fresh"] is True
    assert report["latest_published"] == "2026-07-22"


def test_corruption_injects_six_types_and_is_detected(clean_df, settings):
    corrupted = corrupt_clean_dataframe(clean_df, settings.paths.corruption_log)
    log = read_json(settings.paths.corruption_log)
    assert [entry["type"] for entry in log["corruptions"]] == [
        "drop_latest_records",
        "blank_summary",
        "inject_noise",
        "truncate_title",
        "stale_date",
        "duplicate_rows",
    ]
    assert len(corrupted) == 24 - 5 + 3
    assert not corrupted["paper_id"].is_unique

    quality = run_data_quality_checks(corrupted, settings, "corrupted")
    assert quality["success"] is False
    failed = " ".join(quality["failed_expectations"])
    assert "expect_column_values_to_be_unique(paper_id)" in failed
    assert "expect_column_value_lengths_to_be_between(summary)" in failed
    assert "expect_column_value_lengths_to_be_between(title)" in failed
    assert "expect_column_values_to_not_match_regex(summary)" in failed

    freshness = build_freshness_report(corrupted, settings, settings.paths.quality_dir / "c.json")
    assert freshness["is_fresh"] is False


def test_corruption_is_deterministic(clean_df, settings, tmp_path):
    first = corrupt_clean_dataframe(clean_df, tmp_path / "a.json")
    second = corrupt_clean_dataframe(clean_df, tmp_path / "b.json")
    assert first.equals(second)
