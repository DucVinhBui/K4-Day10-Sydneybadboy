from __future__ import annotations

import math
import random
from typing import Any

import pandas as pd

from core.utils import now_utc, write_json
from ingestion.cleaning import refresh_derived_columns

CORRUPTION_SEED = 42
DROP_LATEST_FRACTION = 0.20
BLANK_SUMMARY_ROWS = 3
NOISE_ROWS = 3
TRUNCATE_TITLE_ROWS = 3
TRUNCATED_TITLE_LENGTH = 7
STALE_DATE_ROWS = 6
STALE_SHIFT_DAYS = 365
DUPLICATE_ROWS = 3
NOISE_TOKENS = ["#@!%", "lorem", "��", "&&&", "zxqv", "0xDEADBEEF", "~~~", "ipsum"]


def _inject_noise(text: str, rng: random.Random) -> str:
    """Chen token rac sau moi 2 tu va them rac vao dau cau (mo phong loi encoding / scraping)."""
    words = text.split()
    noisy: list[str] = [rng.choice(NOISE_TOKENS), rng.choice(NOISE_TOKENS)]
    for position, word in enumerate(words, start=1):
        noisy.append(word)
        if position % 2 == 0:
            noisy.append(rng.choice(NOISE_TOKENS))
    return " ".join(noisy)


def _take(pool: list[int], count: int, rng: random.Random) -> list[int]:
    chosen = sorted(rng.sample(pool, min(count, len(pool))))
    for index in chosen:
        pool.remove(index)
    return chosen


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Tiem 6 dang loi du lieu co kiem soat (deterministic voi seed co dinh) va ghi corruption log."""
    rng = random.Random(CORRUPTION_SEED)
    working = df.copy().sort_values(["published", "paper_id"], ascending=[False, True]).reset_index(drop=True)
    input_rows = len(working)
    log_entries: list[dict[str, Any]] = []

    def log(kind: str, description: str, rows: pd.DataFrame, **extra: Any) -> None:
        log_entries.append(
            {
                "type": kind,
                "description": description,
                "affected_rows": int(len(rows)),
                "affected_paper_ids": rows["paper_id"].tolist(),
                **extra,
            }
        )

    # 1. Drop latest records: mat 20% ban ghi moi nhat (ingestion bo sot du lieu tuoi).
    drop_count = math.ceil(len(working) * DROP_LATEST_FRACTION)
    dropped = working.head(drop_count)
    log(
        "drop_latest_records",
        f"Removed the {drop_count} most recently published records ({DROP_LATEST_FRACTION:.0%}).",
        dropped,
        latest_published_before=str(working["published"].max()),
    )
    working = working.iloc[drop_count:].reset_index(drop=True)

    # Chon cac tap dong roi nhau cho tung loai loi de moi loi deu quan sat duoc.
    pool = list(range(len(working)))

    # 2. Blank summary.
    blank_idx = _take(pool, BLANK_SUMMARY_ROWS, rng)
    log("blank_summary", "Replaced summary with an empty string.", working.loc[blank_idx])
    working.loc[blank_idx, "summary"] = ""

    # 3. Inject noise vao summary.
    noise_idx = _take(pool, NOISE_ROWS, rng)
    log("inject_noise", "Injected garbage tokens into the summary text.", working.loc[noise_idx])
    for index in noise_idx:
        working.at[index, "summary"] = _inject_noise(str(working.at[index, "summary"]), rng)

    # 4. Truncate title xuong < 8 ky tu.
    truncate_idx = _take(pool, TRUNCATE_TITLE_ROWS, rng)
    log(
        "truncate_title",
        f"Truncated title to {TRUNCATED_TITLE_LENGTH} characters.",
        working.loc[truncate_idx],
        original_titles=working.loc[truncate_idx, "title"].tolist(),
    )
    for index in truncate_idx:
        working.at[index, "title"] = str(working.at[index, "title"])[:TRUNCATED_TITLE_LENGTH]

    # 5. Stale date: lui ngay xuat ban ve 365 ngay truoc.
    stale_idx = _take(pool, STALE_DATE_ROWS, rng)
    log(
        "stale_date",
        f"Shifted published date back by {STALE_SHIFT_DAYS} days.",
        working.loc[stale_idx],
        original_published=working.loc[stale_idx, "published"].tolist(),
    )
    for index in stale_idx:
        shifted = pd.Timestamp(working.at[index, "published"]) - pd.Timedelta(days=STALE_SHIFT_DAYS)
        working.at[index, "published"] = shifted.date().isoformat()
        working.at[index, "updated"] = working.at[index, "published"]
        working.at[index, "age_days"] = int(working.at[index, "age_days"]) + STALE_SHIFT_DAYS

    # 6. Duplicate rows: nhan ban mot so dong (sau khi da bi lam ban).
    duplicate_idx = sorted(rng.sample(range(len(working)), min(DUPLICATE_ROWS, len(working))))
    duplicates = working.loc[duplicate_idx]
    log("duplicate_rows", "Appended exact duplicate rows (same paper_id).", duplicates)
    working = pd.concat([working, duplicates], ignore_index=True)

    # 7. Rebuild cac cot dan xuat (text_for_embedding, summary_chars...) tu du lieu da bi lam ban.
    working = refresh_derived_columns(working)

    write_json(
        output_log_path,
        {
            "created_at": now_utc().isoformat(),
            "seed": CORRUPTION_SEED,
            "input_rows": input_rows,
            "output_rows": int(len(working)),
            "corruption_types": len(log_entries),
            "corruptions": log_entries,
        },
    )
    return working
