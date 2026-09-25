# Phase 1 Report — Baseline Data Pipeline

_Generated at 2026-09-25T09:06:48.642476+00:00_

## 1. Source & Lineage

| Field | Value |
| --- | --- |
| `source_api` | Crossref REST API |
| `fetch_mode` | snapshot |
| `query` | agentic retrieval augmented generation large language model |
| `filter` | from-pub-date:2026-03-29,has-abstract:true |
| `raw_response` | data/raw/crossref_response.json |
| `raw_records` | 24 |
| `clean_rows` | 24 |
| `chroma_collection` | papers-baseline |
| `embedding_model` | sentence-transformers/all-MiniLM-L6-v2 |
| `llm_provider` | mock |
| `run_date` | 2026-09-25 |

## 2. Baseline RAG Evaluation

| Metric | Value |
| --- | --- |
| Retrieval Hit Rate | 1.0000 |
| Mean Token F1 | 1.0000 |
| Judge Accuracy | 1.0000 |
| Mean Judge Score (1-5) | 5.0000 |
| Samples | 10 |

### Breakdown by question type

| Question type | Samples | Hit Rate | Token F1 | Judge Accuracy |
| --- | --- | --- | --- | --- |
| authors | 3 | 1.0000 | 1.0000 | 1.0000 |
| categories | 2 | 1.0000 | 1.0000 | 1.0000 |
| date | 2 | 1.0000 | 1.0000 | 1.0000 |
| summary | 3 | 1.0000 | 1.0000 | 1.0000 |

## 3. Data Quality Gate (Great Expectations 1.x)

- Engine: `great_expectations 1.18.0`
- Overall success: **True** (8/8 expectations passed)
- Rows validated: 24

| Expectation | Column | Success | Observed / Unexpected |
| --- | --- | --- | --- |
| `expect_table_row_count_to_be_between` | (table) | ✅ True | 24 |
| `expect_column_values_to_not_be_null` | paper_id | ✅ True | 0 |
| `expect_column_values_to_be_unique` | paper_id | ✅ True | 0 |
| `expect_column_values_to_not_be_null` | title | ✅ True | 0 |
| `expect_column_value_lengths_to_be_between` | title | ✅ True | 0 |
| `expect_column_values_to_not_be_null` | text_for_embedding | ✅ True | 0 |
| `expect_column_value_lengths_to_be_between` | summary | ✅ True | 0 |
| `expect_column_values_to_not_match_regex` | summary | ✅ True | 0 |

## 4. Freshness SLA

Rule: alert when more than 25% of papers have `age_days > 180`. Status: **FRESH**

| Field | Value |
| --- | --- |
| `latest_published` | 2026-07-22 |
| `oldest_published` | 2026-03-28 |
| `latest_age_days` | 65 |
| `stale_rows` | 1 |
| `total_rows` | 24 |
| `stale_ratio` | 0.0417 |
| `max_stale_ratio` | 0.2500 |
| `threshold_days` | 180 |
| `is_fresh` | ✅ True |

## 5. Conclusion

Baseline data passed the quality gate and the freshness SLA; the index is safe to serve.
