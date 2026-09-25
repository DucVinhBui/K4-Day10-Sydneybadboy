from __future__ import annotations

from collections import Counter

from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from retrieval.index import LocalEmbeddingIndex
from retrieval.qa import answer_question


def test_build_test_set(clean_df, settings):
    test_set = build_test_set(clean_df, settings.paths.eval_testset)
    assert len(test_set) == 10
    counts = Counter(item["question_type"] for item in test_set)
    assert set(counts) == {"summary", "authors", "date", "categories"}
    assert len({item["id"] for item in test_set}) == 10
    assert settings.paths.eval_testset.exists()
    known = set(clean_df["paper_id"])
    assert all(doc_id in known for item in test_set for doc_id in item["ground_truth_doc_ids"])


def test_index_and_baseline_evaluation(clean_df, settings):
    index = LocalEmbeddingIndex.build(clean_df, settings, settings.paths.embeddings_json)
    assert index.collection.count() == 24
    assert index.collection_name == "papers-baseline"

    result = answer_question("Who authored the paper '" + clean_df.iloc[0]["title"] + "'?", settings, index)
    assert result.retrieved_doc_ids[0] == clean_df.iloc[0]["paper_id"]
    assert result.answer == clean_df.iloc[0]["authors_joined"]

    build_test_set(clean_df, settings.paths.eval_testset)
    bundle = evaluate_pipeline(
        settings, index, settings.paths.eval_testset, settings.paths.baseline_metrics, settings.paths.baseline_answers
    )
    assert bundle.summary["retrieval_hit_rate"] == 1.0
    assert bundle.summary["mean_token_f1"] == 1.0


def test_index_manifest_is_portable_and_loadable(clean_df, settings):
    from core.utils import read_json

    LocalEmbeddingIndex.build(clean_df, settings, settings.paths.embeddings_json)
    assert read_json(settings.paths.embeddings_json)["persist_path"] == "data/chroma"
    loaded = LocalEmbeddingIndex.load(settings)
    assert loaded.collection.count() == 24
    assert loaded.search("freshness SLA", top_k=1)
