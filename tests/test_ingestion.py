from __future__ import annotations

from dataclasses import asdict

from core.utils import read_json
from ingestion import crossref
from ingestion.crossref import fetch_source_records, load_raw_records, parse_crossref_payload


def test_parse_snapshot_matches_raw_records(settings):
    payload = read_json(settings.paths.raw_api_response)
    parsed = parse_crossref_payload(payload)
    expected = read_json(settings.paths.raw_records_json)
    assert len(parsed) == 24
    assert [asdict(record) for record in parsed] == expected


def test_parse_strips_jats_and_skips_invalid_items():
    payload = {
        "message": {
            "items": [
                {
                    "DOI": "10.1/ABC",
                    "title": ["  Hello   <i>World</i> "],
                    "abstract": "<jats:p>Some &amp; abstract text.</jats:p>",
                    "author": [{"given": "Ada", "family": "Lovelace"}, {"name": "Consortium"}],
                    "subject": ["AI"],
                    "published": {"date-parts": [[2026, 5]]},
                },
                {"DOI": "10.1/no-abstract", "title": ["x"], "published": {"date-parts": [[2026, 1, 1]]}},
                {"title": ["no doi"], "abstract": "abc", "published": {"date-parts": [[2026, 1, 1]]}},
            ]
        }
    }
    records = parse_crossref_payload(payload)
    assert len(records) == 1
    record = records[0]
    assert record.paper_id == "10.1/abc"
    assert record.title == "Hello World"
    assert record.summary == "Some & abstract text."
    assert record.authors == ["Ada Lovelace", "Consortium"]
    assert record.published == "2026-05-01"
    assert record.abs_url == "https://doi.org/10.1/abc"


def test_fetch_offline_uses_snapshot_and_writes_records(settings):
    settings.paths.raw_records_json.unlink()
    records = fetch_source_records(settings)
    assert len(records) == 24
    assert crossref.last_fetch_mode == "snapshot"
    assert settings.paths.raw_records_json.exists()
    assert load_raw_records(settings.paths.raw_records_json) == records


def test_fetch_falls_back_to_snapshot_when_api_fails(settings, monkeypatch):
    from dataclasses import replace

    def boom(_settings):
        raise RuntimeError("HTTP 429")

    monkeypatch.setattr(crossref, "_request_crossref", boom)
    records = fetch_source_records(replace(settings, refresh_source=True))
    assert len(records) == 24
    assert crossref.last_fetch_mode == "snapshot"
