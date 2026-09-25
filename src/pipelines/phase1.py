from __future__ import annotations

from typing import Any

import pandas as pd

from core.config import Settings, load_settings, normalized_provider
from core.utils import now_utc, read_json, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion import crossref
from ingestion.cleaning import build_clean_dataframe, save_clean_artifacts
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex
from retrieval.qa import answer_question

DEMO_QUESTIONS = [
    "Which papers discuss freshness SLAs for LLM knowledge augmentation?",
    "How can Great Expectations be used for automated data quality profiling?",
]


def load_or_build_test_set(df: pd.DataFrame, settings: Settings) -> list[dict[str, Any]]:
    """Giu test set co dinh giua cac lan chay de so sanh cong bang; chi sinh lai khi can."""
    path = settings.paths.eval_testset
    if path.exists() and not settings.refresh_test_set:
        test_set = read_json(path)
        known_ids = set(df["paper_id"])
        if test_set and all(doc_id in known_ids for item in test_set for doc_id in item["ground_truth_doc_ids"]):
            return test_set
        print("[phase1] Test set cu khong khop corpus hien tai -> sinh lai.")
    return build_test_set(df, path)


def run_agent_demo(settings: Settings, index: LocalEmbeddingIndex) -> list[dict[str, Any]]:
    """Demo tool-calling agent; neu provider khong ho tro (mock / thieu key) thi fallback extractive QA."""
    results: list[dict[str, Any]] = []
    agent = None
    agent_error = None
    if normalized_provider(settings) != "mock":
        try:
            from retrieval.agent import build_agent

            agent = build_agent(settings, index)
        except Exception as exc:  # thieu API key, provider khong ho tro tool calling...
            agent_error = f"{type(exc).__name__}: {exc}"

    for question in DEMO_QUESTIONS:
        entry: dict[str, Any] = {"question": question, "provider": settings.llm_provider}
        if agent is not None:
            try:
                from retrieval.agent import run_agent_question

                entry["mode"] = "agent"
                entry["answer"] = run_agent_question(agent, question)
                results.append(entry)
                continue
            except Exception as exc:
                agent_error = f"{type(exc).__name__}: {exc}"
        fallback = answer_question(question, settings=settings, index=index)
        entry.update(
            {
                "mode": "extractive_fallback",
                "answer": fallback.answer,
                "retrieved_titles": fallback.retrieved_titles,
                "agent_error": agent_error,
            }
        )
        results.append(entry)
    return results


def main() -> None:
    settings = load_settings()
    paths = settings.paths
    run_date = now_utc()
    print(f"[phase1] Run date: {run_date.isoformat()} | LLM provider: {settings.llm_provider}")

    # 1-2. Ingestion + raw preservation.
    records = crossref.fetch_source_records(settings)
    print(f"[phase1] Ingested {len(records)} records (mode={crossref.last_fetch_mode}).")

    # 3-4. Cleaning.
    df = build_clean_dataframe(records, run_date)
    save_clean_artifacts(df, paths.clean_csv, paths.clean_json)
    print(f"[phase1] Clean rows: {len(df)} -> {paths.clean_csv.relative_to(paths.project_dir)}")

    # 5. Quality gate + freshness TRUOC khi cho du lieu vao vector store.
    quality = run_data_quality_checks(df, settings, "baseline")
    freshness = build_freshness_report(df, settings, paths.freshness_report)
    print(
        f"[phase1] Quality gate success={quality['success']} "
        f"({quality['expectations_passed']}/{quality['expectations_total']}), freshness={freshness['status']}"
    )
    if not quality["success"]:
        raise RuntimeError(
            "Quality gate failed on baseline data, refusing to index: "
            + ", ".join(quality["failed_expectations"])
        )

    # 6. Embedding + ChromaDB index.
    index = LocalEmbeddingIndex.build(df, settings, paths.embeddings_json)
    print(f"[phase1] Indexed {index.collection.count()} docs into Chroma collection '{index.collection_name}'.")

    # 7-8. Test set + evaluation.
    test_set = load_or_build_test_set(df, settings)
    bundle = evaluate_pipeline(settings, index, paths.eval_testset, paths.baseline_metrics, paths.baseline_answers)
    metrics = bundle.summary
    print(
        f"[phase1] Baseline on {len(test_set)} questions: hit_rate={metrics['retrieval_hit_rate']:.4f} "
        f"token_f1={metrics['mean_token_f1']:.4f} judge_acc={metrics['judge_accuracy']:.4f}"
    )

    # 9. Agent demo (khong bat buoc cho metrics).
    write_json(paths.demo_answers, run_agent_demo(settings, index))

    # 10. Report.
    source_summary = {
        "source_api": settings.source_api,
        "fetch_mode": crossref.last_fetch_mode,
        "query": settings.source_query,
        "filter": settings.source_filter,
        "raw_response": str(paths.raw_api_response.relative_to(paths.project_dir)),
        "raw_records": len(records),
        "clean_rows": len(df),
        "chroma_collection": index.collection_name,
        "embedding_model": settings.embedding_model,
        "llm_provider": settings.llm_provider,
        "run_date": run_date.date().isoformat(),
    }
    generate_phase1_report(paths.baseline_report, source_summary, metrics, quality, freshness)
    print(f"[phase1] Report -> {paths.baseline_report.relative_to(paths.project_dir)}")
