from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import html
from pathlib import Path
import re
import time
from typing import Any

import requests

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json

CROSSREF_WORKS_URL = "https://api.crossref.org/works"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 20

# "live" khi lay tu Crossref API, "snapshot" khi doc file raw local (offline / fallback).
last_fetch_mode: str = "unknown"


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def _strip_markup(value: str) -> str:
    """Bo cac the JATS/HTML (vd `<jats:p>`) va giai ma HTML entity."""
    without_tags = re.sub(r"<[^>]+>", " ", value or "")
    return normalize_whitespace(html.unescape(without_tags))


def _first_text(value: Any) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    return normalize_whitespace(str(value or ""))


def _date_from_parts(node: Any) -> str | None:
    if not isinstance(node, dict):
        return None
    parts = (node.get("date-parts") or [[]])[0] or []
    if parts and parts[0]:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 and parts[1] else 1
        day = int(parts[2]) if len(parts) > 2 and parts[2] else 1
        return f"{year:04d}-{month:02d}-{day:02d}"
    date_time = node.get("date-time")
    if date_time:
        return str(date_time)[:10]
    return None


def _published_date(item: dict[str, Any]) -> str | None:
    for key in ("published", "published-online", "published-print", "issued", "created"):
        value = _date_from_parts(item.get(key))
        if value:
            return value
    return None


def _updated_date(item: dict[str, Any], published: str) -> str:
    for key in ("updated", "deposited", "indexed", "created"):
        value = _date_from_parts(item.get(key))
        if value:
            return max(value, published)
    return published


def _authors(item: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for author in item.get("author") or []:
        if not isinstance(author, dict):
            continue
        name = normalize_whitespace(
            " ".join(part for part in (author.get("given"), author.get("family")) if part)
        ) or normalize_whitespace(str(author.get("name") or ""))
        if name and name not in names:
            names.append(name)
    return names


def _pdf_url(item: dict[str, Any], fallback: str) -> str:
    for link in item.get("link") or []:
        if isinstance(link, dict) and "pdf" in str(link.get("content-type", "")).lower() and link.get("URL"):
            return str(link["URL"])
    return fallback


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    items = (payload.get("message") or {}).get("items") or []
    records: list[PaperRecord] = []
    seen: set[str] = set()
    for item in items:
        paper_id = normalize_whitespace(str(item.get("DOI") or "")).lower()
        title = _strip_markup(_first_text(item.get("title")))
        summary = _strip_markup(str(item.get("abstract") or ""))
        published = _published_date(item)
        # Bo record khong du dieu kien de index: thieu DOI, title, abstract hoac ngay xuat ban.
        if not paper_id or not title or not summary or not published or paper_id in seen:
            continue
        seen.add(paper_id)

        categories = [normalize_whitespace(str(subject)) for subject in item.get("subject") or [] if subject]
        abs_url = str(item.get("URL") or f"https://doi.org/{paper_id}")
        records.append(
            PaperRecord(
                paper_id=paper_id,
                title=title,
                summary=summary,
                authors=_authors(item),
                categories=categories,
                primary_category=categories[0] if categories else "Uncategorized",
                published=published,
                updated=_updated_date(item, published),
                abs_url=abs_url,
                pdf_url=_pdf_url(item, abs_url),
                comment=f"Crossref record {paper_id}",
            )
        )
    return records


def _request_crossref(settings: Settings) -> dict[str, Any]:
    params = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
        "sort": "published",
        "order": "desc",
    }
    headers = {"User-Agent": "day10-data-observability-lab/0.1 (educational use)"}
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(
                CROSSREF_WORKS_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
            )
            if response.status_code in RETRYABLE_STATUS_CODES:
                retry_after = response.headers.get("Retry-After", "")
                wait = float(retry_after) if retry_after.isdigit() else 2.0**attempt
                last_error = RuntimeError(f"Crossref returned HTTP {response.status_code}")
                print(f"[crossref] HTTP {response.status_code}, retry {attempt}/{MAX_ATTEMPTS} sau {wait:.0f}s")
                time.sleep(min(wait, 30.0))
                continue
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < MAX_ATTEMPTS:
                time.sleep(2.0**attempt)
    raise RuntimeError(f"Crossref API unavailable after {MAX_ATTEMPTS} attempts: {last_error}")


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Lay records tu Crossref (live) hoac snapshot local (offline), luu 2 raw artifacts.

    - Mac dinh (dev/offline): doc `data/raw/crossref_response.json` co san.
    - `REFRESH_SOURCE=1`: goi Crossref API; neu loi mang / 429 thi fallback ve snapshot.
    Snapshot chi bi ghi de khi goi API thanh cong va co record hop le.
    """
    global last_fetch_mode
    paths = settings.paths
    payload: dict[str, Any] | None = None

    if settings.refresh_source or not paths.raw_api_response.exists():
        try:
            live_payload = _request_crossref(settings)
            if parse_crossref_payload(live_payload):
                payload = live_payload
                last_fetch_mode = "live"
                write_json(paths.raw_api_response, payload)
            else:
                print("[crossref] Live API khong tra ve record hop le, dung snapshot local.")
        except RuntimeError as exc:
            print(f"[crossref] {exc}. Chuyen sang snapshot offline.")

    if payload is None:
        if not paths.raw_api_response.exists():
            raise FileNotFoundError(
                f"Khong goi duoc Crossref API va khong co snapshot tai {paths.raw_api_response}."
            )
        payload = read_json(paths.raw_api_response)
        last_fetch_mode = "snapshot"

    records = parse_crossref_payload(payload)
    write_json(paths.raw_records_json, [asdict(record) for record in records])
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    payload = read_json(Path(path))
    if isinstance(payload, dict) and "message" in payload:
        return parse_crossref_payload(payload)
    allowed = {field.name for field in fields(PaperRecord)}
    return [PaperRecord(**{key: value for key, value in row.items() if key in allowed}) for row in payload]
