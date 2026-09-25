from __future__ import annotations

from typing import Any

import pandas as pd

from core.utils import compact_join, first_sentence, write_json

MIN_DOCUMENTS = 10
# 10 cau hoi phu du 4 nhom nghiep vu.
QUESTION_PLAN = ["summary", "authors", "date", "categories", "summary", "authors", "date", "categories", "summary", "authors"]


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        return [part.strip() for part in value.split(";") if part.strip()]
    return []


def _make_question(question_type: str, row: pd.Series) -> tuple[str, str]:
    title = row["title"]
    if question_type == "summary":
        return f"What is the summary of the paper '{title}'?", first_sentence(row["summary"])
    if question_type == "authors":
        answer = row.get("authors_joined") or compact_join(_as_list(row.get("authors")))
        return f"Who authored the paper '{title}'?", answer
    if question_type == "date":
        return f"When was the paper '{title}' published?", str(row["published"])
    if question_type == "categories":
        answer = row.get("categories_joined") or compact_join(_as_list(row.get("categories")))
        return f"What categories does the paper '{title}' belong to?", answer
    raise ValueError(f"Unknown question type: {question_type}")


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Sinh bo 10 cau hoi benchmark co dinh (deterministic) tu cleaned dataframe."""
    if len(df) < MIN_DOCUMENTS:
        raise ValueError(f"Need at least {MIN_DOCUMENTS} clean documents to build a test set, got {len(df)}.")

    # Chi dung paper co title khong chua dau nhay don (qa.py trich title bang regex '...').
    candidates = df[~df["title"].str.contains("'", regex=False)]
    candidates = candidates.sort_values(["published", "paper_id"], ascending=[False, True]).reset_index(drop=True)
    if len(candidates) < len(QUESTION_PLAN):
        raise ValueError("Not enough papers with quotable titles to build the test set.")

    # Chon paper trai deu tu moi nhat -> cu nhat de phu nhieu giai doan thoi gian.
    step = (len(candidates) - 1) / (len(QUESTION_PLAN) - 1)
    positions = [round(i * step) for i in range(len(QUESTION_PLAN))]

    test_set: list[dict[str, Any]] = []
    for number, (question_type, position) in enumerate(zip(QUESTION_PLAN, positions, strict=True), start=1):
        row = candidates.iloc[position]
        question, ground_truth = _make_question(question_type, row)
        test_set.append(
            {
                "id": f"eval_{number:03d}",
                "question_type": question_type,
                "question": question,
                "ground_truth": ground_truth,
                "ground_truth_doc_ids": [row["paper_id"]],
            }
        )

    write_json(output_path, test_set)
    return test_set
