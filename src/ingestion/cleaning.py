from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import html
import re
from typing import Any

import pandas as pd

from core.utils import compact_join, ensure_parent, normalize_whitespace
from ingestion.crossref import PaperRecord

CLEAN_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors",
    "categories",
    "primary_category",
    "published",
    "updated",
    "abs_url",
    "pdf_url",
    "comment",
    "authors_joined",
    "categories_joined",
    "summary_chars",
    "age_days",
    "text_for_embedding",
]


def clean_text(value: Any) -> str:
    """Bo the JATS/HTML con sot, giai ma entity va gom khoang trang."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = re.sub(r"<[^>]+>", " ", str(value))
    return normalize_whitespace(html.unescape(text))


def _clean_list(values: Any) -> list[str]:
    if values is None or (isinstance(values, float) and pd.isna(values)):
        return []
    if isinstance(values, str):
        values = [part for part in re.split(r"[;,]", values)]
    cleaned: list[str] = []
    for value in values:
        item = clean_text(value)
        if item and item not in cleaned:
            cleaned.append(item)
    return cleaned


def _to_iso_date(value: Any) -> str | None:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return None
    return parsed.date().isoformat()


def build_text_for_embedding(row: dict[str, Any] | pd.Series) -> str:
    return "\n".join(
        [
            f"Title: {row['title']}",
            f"Authors: {row['authors_joined']}",
            f"Published: {row['published']}",
            f"Categories: {row['categories_joined']}",
            f"Summary: {row['summary']}",
        ]
    )


def refresh_derived_columns(df: pd.DataFrame, run_date: datetime | None = None) -> pd.DataFrame:
    """Tinh lai cac cot helper tu cac cot goc (dung chung cho cleaning, corruption, repair)."""
    out = df.copy()
    out["authors_joined"] = out["authors"].apply(lambda items: compact_join(items))
    out["categories_joined"] = out["categories"].apply(lambda items: compact_join(items))
    out["summary_chars"] = out["summary"].fillna("").str.len().astype(int)
    if run_date is not None:
        stamp = pd.Timestamp(run_date)
        today = (stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")).normalize()
        published = pd.to_datetime(out["published"], utc=True)
        out["age_days"] = (today - published).dt.days.astype(int)
    out["text_for_embedding"] = out.apply(build_text_for_embedding, axis=1)
    return out


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in records:
        raw = asdict(record) if isinstance(record, PaperRecord) else dict(record)
        published = _to_iso_date(raw.get("published"))
        updated = _to_iso_date(raw.get("updated")) or published
        categories = _clean_list(raw.get("categories"))
        rows.append(
            {
                "paper_id": clean_text(raw.get("paper_id")).lower(),
                "title": clean_text(raw.get("title")),
                "summary": clean_text(raw.get("summary")),
                "authors": _clean_list(raw.get("authors")),
                "categories": categories,
                "primary_category": clean_text(raw.get("primary_category"))
                or (categories[0] if categories else "Uncategorized"),
                "published": published,
                "updated": updated,
                "abs_url": clean_text(raw.get("abs_url")),
                "pdf_url": clean_text(raw.get("pdf_url")) or clean_text(raw.get("abs_url")),
                "comment": clean_text(raw.get("comment")),
            }
        )

    df = pd.DataFrame(rows, columns=CLEAN_COLUMNS[:11])
    if df.empty:
        return pd.DataFrame(columns=CLEAN_COLUMNS)

    # Loai row khong the dung cho RAG: thieu khoa, tieu de, tom tat hoac ngay xuat ban.
    valid = (df["paper_id"] != "") & (df["title"] != "") & (df["summary"] != "") & df["published"].notna()
    df = df[valid]

    # Khu trung lap theo paper_id, giu ban cap nhat moi nhat.
    df = df.sort_values(["paper_id", "updated"], ascending=[True, False]).drop_duplicates("paper_id", keep="first")

    df = refresh_derived_columns(df, run_date)
    df = df.sort_values(["published", "paper_id"], ascending=[False, True]).reset_index(drop=True)
    return df[CLEAN_COLUMNS]


def to_csv_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Ban CSV: ghep list thanh chuoi `; ` de de doc thay vi repr cua Python list."""
    out = df.copy()
    for column in ("authors", "categories"):
        if column in out.columns:
            out[column] = out[column].apply(lambda items: "; ".join(items) if isinstance(items, list) else items)
    return out


def save_clean_artifacts(df: pd.DataFrame, csv_path, json_path) -> None:
    ensure_parent(csv_path)
    ensure_parent(json_path)
    to_csv_frame(df).to_csv(csv_path, index=False)
    df.to_json(json_path, orient="records", indent=2, force_ascii=False)
