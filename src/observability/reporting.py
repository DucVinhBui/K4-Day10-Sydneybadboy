from __future__ import annotations

from typing import Any

from core.utils import now_utc, write_text

METRIC_ROWS = [
    ("retrieval_hit_rate", "Retrieval Hit Rate"),
    ("mean_token_f1", "Mean Token F1"),
    ("judge_accuracy", "Judge Accuracy"),
    ("mean_judge_score", "Mean Judge Score (1-5)"),
]


def _fmt(value: Any, digits: int = 4) -> str:
    if isinstance(value, bool):
        return "✅ True" if value else "❌ False"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    if value is None:
        return "-"
    return str(value)


def _delta(new: Any, old: Any) -> str:
    if not isinstance(new, (int, float)) or not isinstance(old, (int, float)):
        return "-"
    diff = float(new) - float(old)
    return f"{diff:+.4f}"


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(" --- " for _ in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(_fmt(cell) for cell in row) + " |")
    return "\n".join(lines)


def _quality_rows(quality: dict[str, Any]) -> list[list[Any]]:
    rows = []
    for check in quality.get("checks", []):
        unexpected = check.get("unexpected_count")
        observed = check.get("observed_value")
        rows.append(
            [
                f"`{check['expectation']}`",
                check.get("column") or "(table)",
                check["success"],
                observed if observed is not None else unexpected,
            ]
        )
    return rows


def _freshness_rows(freshness: dict[str, Any]) -> list[list[Any]]:
    keys = [
        "latest_published",
        "oldest_published",
        "latest_age_days",
        "stale_rows",
        "total_rows",
        "stale_ratio",
        "max_stale_ratio",
        "threshold_days",
        "is_fresh",
    ]
    return [[f"`{key}`", freshness.get(key)] for key in keys if key in freshness]


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    sections: list[str] = [
        "# Phase 1 Report — Baseline Data Pipeline",
        "",
        f"_Generated at {now_utc().isoformat()}_",
        "",
        "## 1. Source & Lineage",
        "",
        _table(["Field", "Value"], [[f"`{key}`", value] for key, value in source_summary.items()]),
        "",
        "## 2. Baseline RAG Evaluation",
        "",
        _table(["Metric", "Value"], [[label, metrics.get(key)] for key, label in METRIC_ROWS] + [["Samples", metrics.get("samples")]]),
        "",
    ]

    by_type = metrics.get("by_question_type") or {}
    if by_type:
        sections += [
            "### Breakdown by question type",
            "",
            _table(
                ["Question type", "Samples", "Hit Rate", "Token F1", "Judge Accuracy"],
                [
                    [name, values["samples"], values["retrieval_hit_rate"], values["mean_token_f1"], values["judge_accuracy"]]
                    for name, values in by_type.items()
                ],
            ),
            "",
        ]

    sections += [
        "## 3. Data Quality Gate (Great Expectations 1.x)",
        "",
        f"- Engine: `{quality.get('engine')}`",
        f"- Overall success: **{quality.get('success')}** "
        f"({quality.get('expectations_passed')}/{quality.get('expectations_total')} expectations passed)",
        f"- Rows validated: {quality.get('row_count')}",
        "",
        _table(["Expectation", "Column", "Success", "Observed / Unexpected"], _quality_rows(quality)),
        "",
        "## 4. Freshness SLA",
        "",
        f"Rule: alert when more than {freshness.get('max_stale_ratio', 0.25):.0%} of papers have "
        f"`age_days > {freshness.get('threshold_days')}`. Status: **{freshness.get('status', '-')}**",
        "",
        _table(["Field", "Value"], _freshness_rows(freshness)),
        "",
        "## 5. Conclusion",
        "",
        (
            "Baseline data passed the quality gate and the freshness SLA; the index is safe to serve."
            if quality.get("success") and freshness.get("is_fresh")
            else "Baseline data did NOT fully pass quality/freshness checks — investigate before serving."
        ),
        "",
    ]
    write_text(report_path, "\n".join(sections))


def _analysis(
    baseline: dict[str, Any],
    corrupted: dict[str, Any],
    repaired: dict[str, Any],
    corrupted_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_quality: dict[str, Any],
) -> list[str]:
    lines: list[str] = []
    for key, label in METRIC_ROWS:
        base, bad, fixed = baseline.get(key), corrupted.get(key), repaired.get(key)
        if not all(isinstance(value, (int, float)) for value in (base, bad, fixed)):
            continue
        recovered = abs(fixed - base) < 1e-9
        lines.append(
            f"- **{label}:** {base:.4f} → {bad:.4f} ({bad - base:+.4f}) when corrupted, "
            f"{'fully recovered' if recovered else 'reached'} {fixed:.4f} after repair."
        )
    failed = corrupted_quality.get("failed_expectations") or []
    lines.append(
        f"- **Quality gate on corrupted data:** success = {corrupted_quality.get('success')}; "
        f"{len(failed)} expectation(s) failed: {', '.join(f'`{item}`' for item in failed) or 'none'}."
    )
    lines.append(
        f"- **Freshness on corrupted data:** stale ratio {corrupted_freshness.get('stale_ratio')} "
        f"(limit {corrupted_freshness.get('max_stale_ratio')}), is_fresh = {corrupted_freshness.get('is_fresh')}, "
        f"latest_published = {corrupted_freshness.get('latest_published')}."
    )
    lines.append(
        f"- **Quality gate after repair:** success = {repaired_quality.get('success')} "
        f"({repaired_quality.get('expectations_passed')}/{repaired_quality.get('expectations_total')} passed)."
    )
    lines.append(
        "- **Silent failure:** the corrupted index still answers every question without raising any error — "
        "only the quality gate, the freshness monitor and the benchmark reveal the damage."
    )
    return lines


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
    corruption_log: dict[str, Any] | None = None,
    repair_summary: dict[str, Any] | None = None,
) -> None:
    metric_rows = [
        [
            label,
            baseline_metrics.get(key),
            corrupted_metrics.get(key),
            repaired_metrics.get(key),
            _delta(corrupted_metrics.get(key), baseline_metrics.get(key)),
            _delta(repaired_metrics.get(key), baseline_metrics.get(key)),
        ]
        for key, label in METRIC_ROWS
    ]
    sections: list[str] = [
        "# Corruption Report — Baseline vs Corrupted vs Repaired",
        "",
        f"_Generated at {now_utc().isoformat()}_",
        "",
        "All three states are evaluated on the **same** `data/eval/test_set.json`.",
        "",
        "## 1. RAG Metrics — 3-State Comparison",
        "",
        _table(
            ["Metric", "Baseline", "Corrupted", "Repaired", "Δ Corrupted vs Baseline", "Δ Repaired vs Baseline"],
            metric_rows,
        ),
        "",
    ]

    types = sorted(
        set(baseline_metrics.get("by_question_type") or {})
        | set(corrupted_metrics.get("by_question_type") or {})
        | set(repaired_metrics.get("by_question_type") or {})
    )
    if types:
        rows = []
        for name in types:
            values = [
                (metrics.get("by_question_type") or {}).get(name, {})
                for metrics in (baseline_metrics, corrupted_metrics, repaired_metrics)
            ]
            rows.append(
                [name]
                + [value.get("retrieval_hit_rate") for value in values]
                + [value.get("mean_token_f1") for value in values]
            )
        sections += [
            "### Breakdown by question type",
            "",
            _table(
                ["Question type", "Hit (B)", "Hit (C)", "Hit (R)", "F1 (B)", "F1 (C)", "F1 (R)"],
                rows,
            ),
            "",
        ]

    if corruption_log:
        sections += [
            "## 2. Injected Corruptions",
            "",
            f"Seed `{corruption_log.get('seed')}` — rows {corruption_log.get('input_rows')} → "
            f"{corruption_log.get('output_rows')}.",
            "",
            _table(
                ["#", "Type", "Rows", "Description"],
                [
                    [index, f"`{entry['type']}`", entry["affected_rows"], entry["description"]]
                    for index, entry in enumerate(corruption_log.get("corruptions", []), start=1)
                ],
            ),
            "",
        ]

    quality_by_name = {
        check["expectation"] + (f"({check['column']})" if check.get("column") else ""): check["success"]
        for check in repaired_quality.get("checks", [])
    }
    quality_rows = []
    for check in corrupted_quality.get("checks", []):
        name = check["expectation"] + (f"({check['column']})" if check.get("column") else "")
        quality_rows.append(
            [
                f"`{name}`",
                check["success"],
                check.get("observed_value") if check.get("observed_value") is not None else check.get("unexpected_count"),
                quality_by_name.get(name),
            ]
        )
    sections += [
        "## 3. Data Quality Gate (GX 1.x) — Corrupted vs Repaired",
        "",
        f"- Corrupted: success = **{corrupted_quality.get('success')}** "
        f"({corrupted_quality.get('expectations_passed')}/{corrupted_quality.get('expectations_total')} passed)",
        f"- Repaired: success = **{repaired_quality.get('success')}** "
        f"({repaired_quality.get('expectations_passed')}/{repaired_quality.get('expectations_total')} passed)",
        "",
        _table(["Expectation", "Corrupted", "Corrupted observed / unexpected", "Repaired"], quality_rows),
        "",
        "## 4. Freshness SLA — Corrupted vs Repaired",
        "",
        _table(
            ["Field", "Corrupted", "Repaired"],
            [
                [f"`{key}`", corrupted_freshness.get(key), repaired_freshness.get(key)]
                for key in (
                    "latest_published",
                    "oldest_published",
                    "latest_age_days",
                    "stale_rows",
                    "total_rows",
                    "stale_ratio",
                    "is_fresh",
                    "status",
                )
            ],
        ),
        "",
    ]

    if repair_summary:
        sections += [
            "## 5. Idempotent Repair",
            "",
            _table(["Field", "Value"], [[f"`{key}`", value] for key, value in repair_summary.items()]),
            "",
        ]

    sections += [
        "## 6. Analysis",
        "",
        *_analysis(
            baseline_metrics,
            corrupted_metrics,
            repaired_metrics,
            corrupted_quality,
            corrupted_freshness,
            repaired_quality,
        ),
        "",
    ]
    write_text(report_path, "\n".join(sections))


def format_console_comparison(
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
) -> str:
    header = f"{'Metric':<26}{'Baseline':>12}{'Corrupted':>12}{'Repaired':>12}"
    lines = [header, "-" * len(header)]
    for key, label in METRIC_ROWS:
        values = [metrics.get(key) for metrics in (baseline_metrics, corrupted_metrics, repaired_metrics)]
        lines.append(f"{label:<26}" + "".join(f"{_fmt(value):>12}" for value in values))
    return "\n".join(lines)
