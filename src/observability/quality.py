from __future__ import annotations

import os
from typing import Any

import pandas as pd

os.environ.setdefault("GX_ANALYTICS_ENABLED", "false")

import great_expectations as gx  # noqa: E402
from great_expectations.data_context.types.base import ProgressBarsConfig  # noqa: E402

from core.config import Settings  # noqa: E402
from core.utils import now_utc, safe_slug, write_json  # noqa: E402

MIN_ROWS = 5
MAX_ROWS = 5000
MIN_SUMMARY_CHARS = 30
MIN_TITLE_CHARS = 8
MAX_STALE_RATIO = 0.25
# Token rac thuong gap khi scrape/encoding loi (replacement char, chuoi ky tu dac biet lap lai).
NOISE_REGEX = r"(?:�|[#@!%&~]{3,}|0x[0-9A-Fa-f]{6,})"


def _build_expectations() -> list[Any]:
    expectations: list[Any] = [
        gx.expectations.ExpectTableRowCountToBeBetween(min_value=MIN_ROWS, max_value=MAX_ROWS),
    ]
    for column in ("paper_id", "title", "text_for_embedding"):
        expectations.append(gx.expectations.ExpectColumnValuesToNotBeNull(column=column))
    expectations.extend(
        [
            gx.expectations.ExpectColumnValuesToBeUnique(column="paper_id"),
            gx.expectations.ExpectColumnValueLengthsToBeBetween(column="summary", min_value=MIN_SUMMARY_CHARS),
            # Mo rong ngoai 4 expectation bat buoc: bat title bi cat ngan va summary bi chen rac.
            gx.expectations.ExpectColumnValueLengthsToBeBetween(column="title", min_value=MIN_TITLE_CHARS),
            gx.expectations.ExpectColumnValuesToNotMatchRegex(column="summary", regex=NOISE_REGEX),
        ]
    )
    return expectations


def _stale_stats(df: pd.DataFrame, threshold_days: int) -> dict[str, Any]:
    total = int(len(df))
    ages = pd.to_numeric(df["age_days"], errors="coerce") if "age_days" in df else pd.Series(dtype=float)
    stale_rows = int((ages > threshold_days).sum())
    ratio = stale_rows / total if total else 1.0
    return {
        "threshold_days": threshold_days,
        "max_stale_ratio": MAX_STALE_RATIO,
        "stale_rows": stale_rows,
        "total_rows": total,
        "stale_ratio": round(ratio, 4),
        "is_fresh": bool(total and ratio <= MAX_STALE_RATIO),
    }


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Quality Gate chuan GX 1.x (ephemeral context) + freshness signal, ghi report vao data/quality/."""
    frame = df.copy()
    # GX pandas engine khong hash duoc list -> chuyen cac cot list sang chuoi cho viec validate.
    for column in frame.columns:
        if frame[column].apply(lambda value: isinstance(value, list)).any():
            frame[column] = frame[column].apply(lambda value: "; ".join(value) if isinstance(value, list) else value)

    context = gx.get_context(mode="ephemeral")
    context.variables.progress_bars = ProgressBarsConfig(globally=False)
    data_source = context.data_sources.add_pandas(name="papers_source")
    data_asset = data_source.add_dataframe_asset(name="papers_asset")
    batch_def = data_asset.add_batch_definition_whole_dataframe("papers_batch")
    batch = batch_def.get_batch(batch_parameters={"dataframe": frame})

    suite = context.suites.add(gx.ExpectationSuite(name=f"papers_{safe_slug(report_name)}_suite"))
    for expectation in _build_expectations():
        suite.add_expectation(expectation)
    validation = batch.validate(suite)

    checks: list[dict[str, Any]] = []
    for result in validation.results:
        config = result.expectation_config
        details = result.result or {}
        checks.append(
            {
                "expectation": config.type,
                "column": config.kwargs.get("column"),
                "kwargs": {key: value for key, value in config.kwargs.items() if key not in {"batch_id", "column"}},
                "success": bool(result.success),
                "observed_value": details.get("observed_value"),
                "unexpected_count": details.get("unexpected_count"),
                "unexpected_percent": details.get("unexpected_percent"),
                "partial_unexpected_list": [str(item) for item in details.get("partial_unexpected_list", [])[:5]],
            }
        )

    freshness = _stale_stats(df, settings.freshness_threshold_days)
    passed = sum(1 for check in checks if check["success"])
    report = {
        "report_name": report_name,
        "checked_at": now_utc().isoformat(),
        "engine": f"great_expectations {gx.__version__}",
        "success": bool(validation.success),
        "row_count": int(len(df)),
        "expectations_total": len(checks),
        "expectations_passed": passed,
        "expectations_failed": len(checks) - passed,
        "failed_expectations": [
            f"{check['expectation']}({check['column']})" if check["column"] else check["expectation"]
            for check in checks
            if not check["success"]
        ],
        "checks": checks,
        "freshness": freshness,
    }
    write_json(settings.paths.quality_dir / f"{safe_slug(report_name)}_quality_report.json", report)
    return report


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    published = pd.to_datetime(df["published"], errors="coerce", utc=True)
    ages = pd.to_numeric(df["age_days"], errors="coerce")
    stats = _stale_stats(df, settings.freshness_threshold_days)
    payload = {
        "checked_at": now_utc().isoformat(),
        "latest_published": published.max().date().isoformat() if published.notna().any() else None,
        "oldest_published": published.min().date().isoformat() if published.notna().any() else None,
        "latest_age_days": int(ages.min()) if ages.notna().any() else None,
        "median_age_days": float(ages.median()) if ages.notna().any() else None,
        **stats,
    }
    payload["status"] = "FRESH" if payload["is_fresh"] else "STALE_ALERT"
    write_json(report_path, payload)
    return payload
