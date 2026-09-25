from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import now_utc, read_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe, save_clean_artifacts
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.dashboard import build_dashboard
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import format_console_comparison, generate_corruption_report
from retrieval.index import LocalEmbeddingIndex


def _dataset_fingerprint(df: pd.DataFrame) -> str:
    content = df.drop(columns=["age_days"], errors="ignore").to_json(orient="records", force_ascii=False)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def repair_from_raw(settings: Settings, run_date) -> pd.DataFrame:
    """Idempotent repair: luon tai tao clean dataset tu raw snapshot bat bien, khong sua tay du lieu hong."""
    records = load_raw_records(settings.paths.raw_records_json)
    return build_clean_dataframe(records, run_date)


def _needs_repair(quality: dict[str, Any], freshness: dict[str, Any]) -> list[str]:
    reasons = [f"quality:{name}" for name in quality.get("failed_expectations", [])]
    if not freshness.get("is_fresh", False):
        reasons.append("freshness:stale_ratio_exceeded")
    return reasons


def main() -> None:
    settings = load_settings()
    paths = settings.paths
    run_date = now_utc()

    missing = [path for path in (paths.clean_json, paths.baseline_metrics, paths.eval_testset) if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing Phase 1 artifacts, run `python script/run_phase1.py` first: "
            + ", ".join(str(path.relative_to(paths.project_dir)) for path in missing)
        )

    # 1. Load baseline.
    baseline_metrics = read_json(paths.baseline_metrics)
    clean_df = pd.read_json(paths.clean_json, orient="records", dtype={"published": str, "updated": str})
    print(f"[corruption] Loaded baseline clean dataset: {len(clean_df)} rows")

    # 2-3. Corrupt + save artifacts.
    corrupted_df = corrupt_clean_dataframe(clean_df, paths.corruption_log)
    save_clean_artifacts(corrupted_df, paths.corrupted_clean_csv, paths.corrupted_clean_json)
    corruption_log = read_json(paths.corruption_log)
    print(f"[corruption] Injected {corruption_log['corruption_types']} corruption types -> {len(corrupted_df)} rows")

    # 4. Observability tren du lieu hong.
    corrupted_quality = run_data_quality_checks(corrupted_df, settings, "corrupted")
    corrupted_freshness = build_freshness_report(
        corrupted_df, settings, paths.quality_dir / "corrupted_freshness_report.json"
    )
    print(
        f"[corruption] Quality gate success={corrupted_quality['success']} "
        f"failed={corrupted_quality['failed_expectations']} | freshness={corrupted_freshness['status']}"
    )

    # 5. Co tinh bypass gate de do "silent failure": index + evaluate tren du lieu hong.
    corrupted_index = LocalEmbeddingIndex.build(corrupted_df, settings, paths.corrupted_embeddings_json)
    corrupted_metrics = evaluate_pipeline(
        settings, corrupted_index, paths.eval_testset, paths.corrupted_metrics, paths.corrupted_answers
    ).summary

    # 6. Auto-repair: gate phat hien vi pham -> tai tao tu raw (idempotent).
    repair_reasons = _needs_repair(corrupted_quality, corrupted_freshness)
    print(f"[repair] Triggered by: {repair_reasons or ['manual run']}")
    repaired_df = repair_from_raw(settings, run_date)
    second_pass = repair_from_raw(settings, run_date)
    save_clean_artifacts(repaired_df, paths.repaired_clean_csv, paths.repaired_clean_json)

    repaired_quality = run_data_quality_checks(repaired_df, settings, "repaired")
    repaired_freshness = build_freshness_report(
        repaired_df, settings, paths.quality_dir / "repaired_freshness_report.json"
    )
    if not repaired_quality["success"]:
        raise RuntimeError("Repaired dataset still fails the quality gate: " + ", ".join(repaired_quality["failed_expectations"]))

    # 7. Evaluate repaired dataset tren cung test set.
    repaired_index = LocalEmbeddingIndex.build(repaired_df, settings, paths.repaired_embeddings_json)
    repaired_metrics = evaluate_pipeline(
        settings, repaired_index, paths.eval_testset, paths.repaired_metrics, paths.repaired_answers
    ).summary

    baseline_fingerprint = _dataset_fingerprint(clean_df)
    repaired_fingerprint = _dataset_fingerprint(repaired_df)
    repair_summary = {
        "source": str(paths.raw_records_json.relative_to(paths.project_dir)),
        "trigger_reasons": ", ".join(repair_reasons) or "manual run",
        "repaired_rows": len(repaired_df),
        "chroma_collection": repaired_index.collection_name,
        "repaired_fingerprint": repaired_fingerprint,
        "baseline_fingerprint": baseline_fingerprint,
        "matches_baseline": repaired_fingerprint == baseline_fingerprint,
        "idempotent_rerun_identical": repaired_fingerprint == _dataset_fingerprint(second_pass),
    }
    print(f"[repair] {repair_summary}")

    # 8. Comparison report.
    generate_corruption_report(
        paths.comparison_report,
        baseline_metrics,
        corrupted_metrics,
        repaired_metrics,
        corrupted_quality,
        repaired_quality,
        corrupted_freshness,
        repaired_freshness,
        corruption_log=corruption_log,
        repair_summary=repair_summary,
    )
    print()
    print(format_console_comparison(baseline_metrics, corrupted_metrics, repaired_metrics))
    print()
    print(f"[corruption] Report -> {paths.comparison_report.relative_to(paths.project_dir)}")
    dashboard = build_dashboard(settings)
    print(f"[corruption] Dashboard -> {dashboard.relative_to(paths.project_dir)}")
