# Corruption Report — Baseline vs Corrupted vs Repaired

_Generated at 2026-09-25T09:07:02.806173+00:00_

All three states are evaluated on the **same** `data/eval/test_set.json`.

## 1. RAG Metrics — 3-State Comparison

| Metric | Baseline | Corrupted | Repaired | Δ Corrupted vs Baseline | Δ Repaired vs Baseline |
| --- | --- | --- | --- | --- | --- |
| Retrieval Hit Rate | 1.0000 | 0.8000 | 1.0000 | -0.2000 | +0.0000 |
| Mean Token F1 | 1.0000 | 0.8842 | 1.0000 | -0.1158 | +0.0000 |
| Judge Accuracy | 1.0000 | 0.9000 | 1.0000 | -0.1000 | +0.0000 |
| Mean Judge Score (1-5) | 5.0000 | 4.4000 | 5.0000 | -0.6000 | +0.0000 |

### Breakdown by question type

| Question type | Hit (B) | Hit (C) | Hit (R) | F1 (B) | F1 (C) | F1 (R) |
| --- | --- | --- | --- | --- | --- | --- |
| authors | 1.0000 | 0.6667 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| categories | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| date | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| summary | 1.0000 | 0.6667 | 1.0000 | 1.0000 | 0.6140 | 1.0000 |

## 2. Injected Corruptions

Seed `42` — rows 24 → 22.

| # | Type | Rows | Description |
| --- | --- | --- | --- |
| 1 | `drop_latest_records` | 5 | Removed the 5 most recently published records (20%). |
| 2 | `blank_summary` | 3 | Replaced summary with an empty string. |
| 3 | `inject_noise` | 3 | Injected garbage tokens into the summary text. |
| 4 | `truncate_title` | 3 | Truncated title to 7 characters. |
| 5 | `stale_date` | 6 | Shifted published date back by 365 days. |
| 6 | `duplicate_rows` | 3 | Appended exact duplicate rows (same paper_id). |

## 3. Data Quality Gate (GX 1.x) — Corrupted vs Repaired

- Corrupted: success = **False** (4/8 passed)
- Repaired: success = **True** (8/8 passed)

| Expectation | Corrupted | Corrupted observed / unexpected | Repaired |
| --- | --- | --- | --- |
| `expect_table_row_count_to_be_between` | ✅ True | 22 | ✅ True |
| `expect_column_values_to_not_be_null(paper_id)` | ✅ True | 0 | ✅ True |
| `expect_column_values_to_be_unique(paper_id)` | ❌ False | 6 | ✅ True |
| `expect_column_values_to_not_be_null(title)` | ✅ True | 0 | ✅ True |
| `expect_column_value_lengths_to_be_between(title)` | ❌ False | 4 | ✅ True |
| `expect_column_values_to_not_be_null(text_for_embedding)` | ✅ True | 0 | ✅ True |
| `expect_column_value_lengths_to_be_between(summary)` | ❌ False | 3 | ✅ True |
| `expect_column_values_to_not_match_regex(summary)` | ❌ False | 4 | ✅ True |

## 4. Freshness SLA — Corrupted vs Repaired

| Field | Corrupted | Repaired |
| --- | --- | --- |
| `latest_published` | 2026-06-12 | 2026-07-22 |
| `oldest_published` | 2025-03-28 | 2026-03-28 |
| `latest_age_days` | 105 | 65 |
| `stale_rows` | 6 | 1 |
| `total_rows` | 22 | 24 |
| `stale_ratio` | 0.2727 | 0.0417 |
| `is_fresh` | ❌ False | ✅ True |
| `status` | STALE_ALERT | FRESH |

## 5. Idempotent Repair

| Field | Value |
| --- | --- |
| `source` | data/raw/crossref_records.json |
| `trigger_reasons` | quality:expect_column_values_to_be_unique(paper_id), quality:expect_column_value_lengths_to_be_between(title), quality:expect_column_value_lengths_to_be_between(summary), quality:expect_column_values_to_not_match_regex(summary), freshness:stale_ratio_exceeded |
| `repaired_rows` | 24 |
| `chroma_collection` | papers-repaired |
| `repaired_fingerprint` | ccc4c8d703c9c4c1 |
| `baseline_fingerprint` | ccc4c8d703c9c4c1 |
| `matches_baseline` | ✅ True |
| `idempotent_rerun_identical` | ✅ True |

## 6. Analysis

- **Retrieval Hit Rate:** 1.0000 → 0.8000 (-0.2000) when corrupted, fully recovered 1.0000 after repair.
- **Mean Token F1:** 1.0000 → 0.8842 (-0.1158) when corrupted, fully recovered 1.0000 after repair.
- **Judge Accuracy:** 1.0000 → 0.9000 (-0.1000) when corrupted, fully recovered 1.0000 after repair.
- **Mean Judge Score (1-5):** 5.0000 → 4.4000 (-0.6000) when corrupted, fully recovered 5.0000 after repair.
- **Quality gate on corrupted data:** success = False; 4 expectation(s) failed: `expect_column_values_to_be_unique(paper_id)`, `expect_column_value_lengths_to_be_between(title)`, `expect_column_value_lengths_to_be_between(summary)`, `expect_column_values_to_not_match_regex(summary)`.
- **Freshness on corrupted data:** stale ratio 0.2727 (limit 0.25), is_fresh = False, latest_published = 2026-06-12.
- **Quality gate after repair:** success = True (8/8 passed).
- **Silent failure:** the corrupted index still answers every question without raising any error — only the quality gate, the freshness monitor and the benchmark reveal the damage.
