from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from core.config import Settings
from core.utils import now_utc, read_json, write_text

STATES = [("baseline", "Baseline"), ("corrupted", "Corrupted"), ("repaired", "Repaired")]
METRICS = [
    ("retrieval_hit_rate", "Hit Rate", 1.0),
    ("mean_token_f1", "Token F1", 1.0),
    ("judge_accuracy", "Judge Acc.", 1.0),
    ("mean_judge_score", "Judge Score", 5.0),
]
AGE_BINS = [(0, 30), (31, 60), (61, 90), (91, 120), (121, 150), (151, 180), (181, 365), (366, 10_000)]


def _load(path: Path) -> Any:
    return read_json(path) if path.exists() else None


def _metric_chart(metrics: dict[str, dict[str, Any]]) -> str:
    width, height, pad = 640, 240, 36
    group_w = (width - pad * 2) / len(METRICS)
    bar_w = group_w / 4
    parts = [f'<svg viewBox="0 0 {width} {height + 40}" role="img" aria-label="Metrics by state">']
    parts.append(f'<line x1="{pad}" y1="{height}" x2="{width - pad}" y2="{height}" class="axis"/>')
    for m_index, (key, label, scale) in enumerate(METRICS):
        x0 = pad + m_index * group_w + bar_w / 2
        for s_index, (state, _) in enumerate(STATES):
            value = (metrics.get(state) or {}).get(key)
            if not isinstance(value, (int, float)):
                continue
            bar_h = (height - 20) * float(value) / scale
            x = x0 + s_index * bar_w
            parts.append(
                f'<rect class="bar {state}" x="{x:.1f}" y="{height - bar_h:.1f}" width="{bar_w - 4:.1f}" '
                f'height="{bar_h:.1f}"><title>{label} — {state}: {value:.3f}</title></rect>'
                f'<text class="val" x="{x + (bar_w - 4) / 2:.1f}" y="{height - bar_h - 4:.1f}">{value:.2f}</text>'
            )
        parts.append(f'<text class="lbl" x="{x0 + bar_w * 1.5:.1f}" y="{height + 20}">{label}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _age_histogram(rows: list[dict[str, Any]], threshold: int) -> str:
    counts = [sum(1 for row in rows if low <= int(row.get("age_days", -1)) <= high) for low, high in AGE_BINS]
    width, height, pad = 640, 200, 36
    bar_w = (width - pad * 2) / len(AGE_BINS)
    peak = max(counts + [1])
    parts = [f'<svg viewBox="0 0 {width} {height + 40}" role="img" aria-label="Age distribution">']
    parts.append(f'<line x1="{pad}" y1="{height}" x2="{width - pad}" y2="{height}" class="axis"/>')
    for index, ((low, high), count) in enumerate(zip(AGE_BINS, counts, strict=True)):
        bar_h = (height - 20) * count / peak
        x = pad + index * bar_w
        stale = "stale" if low > threshold else "fresh"
        label = f"{low}-{high}" if high < 10_000 else f">{low - 1}"
        parts.append(
            f'<rect class="bar {stale}" x="{x + 3:.1f}" y="{height - bar_h:.1f}" width="{bar_w - 6:.1f}" height="{bar_h:.1f}">'
            f"<title>{label} days: {count} papers</title></rect>"
            f'<text class="val" x="{x + bar_w / 2:.1f}" y="{height - bar_h - 4:.1f}">{count}</text>'
            f'<text class="lbl" x="{x + bar_w / 2:.1f}" y="{height + 20}">{label}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _quality_table(reports: dict[str, dict[str, Any]]) -> str:
    names: list[str] = []
    status: dict[str, dict[str, bool]] = {}
    for state, report in reports.items():
        for check in (report or {}).get("checks", []):
            name = check["expectation"] + (f" ({check['column']})" if check.get("column") else "")
            if name not in names:
                names.append(name)
            status.setdefault(name, {})[state] = check["success"]
    head = "".join(f"<th>{label}</th>" for state, label in STATES if state in reports)
    body = []
    for name in names:
        cells = "".join(
            f'<td class="{"pass" if status[name].get(state) else "fail"}">'
            f'{"PASS" if status[name].get(state) else "FAIL" if state in status[name] else "-"}</td>'
            for state, _ in STATES
            if state in reports
        )
        body.append(f"<tr><td><code>{html.escape(name)}</code></td>{cells}</tr>")
    return f"<table><thead><tr><th>Expectation</th>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def build_dashboard(settings: Settings, output_path: Path | None = None) -> Path:
    """Sinh dashboard HTML tinh (khong can server) tu cac artifact quality/freshness/metrics."""
    paths = settings.paths
    output_path = output_path or paths.project_dir / "data" / "reports" / "dashboard.html"
    metrics = {
        "baseline": _load(paths.baseline_metrics),
        "corrupted": _load(paths.corrupted_metrics),
        "repaired": _load(paths.repaired_metrics),
    }
    quality = {
        state: report
        for state, report in {
            "baseline": _load(paths.baseline_quality_report),
            "corrupted": _load(paths.corrupted_quality_report),
            "repaired": _load(paths.quality_dir / "repaired_quality_report.json"),
        }.items()
        if report
    }
    freshness = {
        "baseline": _load(paths.freshness_report),
        "corrupted": _load(paths.quality_dir / "corrupted_freshness_report.json"),
        "repaired": _load(paths.quality_dir / "repaired_freshness_report.json"),
    }
    clean_rows = _load(paths.clean_json) or []
    corrupted_rows = _load(paths.corrupted_clean_json) or []
    corruption_log = _load(paths.corruption_log) or {}

    tiles = []
    for state, label in STATES:
        m = metrics.get(state) or {}
        q = quality.get(state) or {}
        f = freshness.get(state) or {}
        gate = "PASS" if q.get("success") else "FAIL" if q else "-"
        fresh = f.get("status", "-")
        tiles.append(
            f'<div class="tile {state}"><h3>{label}</h3>'
            f'<div class="big">{m.get("retrieval_hit_rate", 0):.2f}</div><div class="cap">Hit rate</div>'
            f'<div class="row"><span>Token F1</span><b>{m.get("mean_token_f1", 0):.3f}</b></div>'
            f'<div class="row"><span>Quality gate</span><b class="{gate.lower()}">{gate}</b></div>'
            f'<div class="row"><span>Freshness</span><b class="{"pass" if fresh == "FRESH" else "fail"}">{fresh}</b></div>'
            "</div>"
        )

    log_rows = "".join(
        f"<tr><td><code>{html.escape(entry['type'])}</code></td><td>{entry['affected_rows']}</td>"
        f"<td>{html.escape(entry['description'])}</td></tr>"
        for entry in corruption_log.get("corruptions", [])
    )
    threshold = settings.freshness_threshold_days

    page = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Data Observability Dashboard</title>
<style>
:root {{ --bg:#f7f7f5; --card:#fff; --ink:#1d1d1b; --muted:#6b6b66; --line:#deded8;
  --baseline:#2f6fbd; --corrupted:#c8553d; --repaired:#3a8f5c; --pass:#2e7d4f; --fail:#b3261e; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#161614; --card:#20201e; --ink:#ecece6; --muted:#a3a39b;
  --line:#3a3a36; --baseline:#6ea4e6; --corrupted:#e8826c; --repaired:#6cc58f; --pass:#6cc58f; --fail:#f28b82; }} }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 system-ui, sans-serif; }}
main {{ max-width:1040px; margin:0 auto; padding:24px 16px 48px; }}
h1 {{ font-size:24px; margin:0 0 4px; }} .sub {{ color:var(--muted); margin:0 0 24px; }}
section {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px; margin-bottom:16px; overflow-x:auto; }}
h2 {{ font-size:16px; margin:0 0 12px; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; margin-bottom:16px; }}
.tile {{ background:var(--card); border:1px solid var(--line); border-top:4px solid var(--baseline); border-radius:10px; padding:14px; }}
.tile.corrupted {{ border-top-color:var(--corrupted); }} .tile.repaired {{ border-top-color:var(--repaired); }}
.tile h3 {{ margin:0; font-size:14px; color:var(--muted); }} .big {{ font-size:34px; font-weight:700; }}
.cap {{ color:var(--muted); font-size:12px; margin-bottom:8px; }}
.row {{ display:flex; justify-content:space-between; border-top:1px solid var(--line); padding:4px 0; }}
.pass {{ color:var(--pass); }} .fail {{ color:var(--fail); }}
svg {{ width:100%; height:auto; }} .axis {{ stroke:var(--line); }}
.bar.baseline {{ fill:var(--baseline); }} .bar.corrupted {{ fill:var(--corrupted); }} .bar.repaired {{ fill:var(--repaired); }}
.bar.fresh {{ fill:var(--baseline); }} .bar.stale {{ fill:var(--corrupted); }}
.val, .lbl {{ fill:var(--ink); font-size:11px; text-anchor:middle; }} .lbl {{ fill:var(--muted); }}
.legend span {{ display:inline-flex; align-items:center; gap:6px; margin-right:14px; color:var(--muted); font-size:13px; }}
.legend i {{ width:10px; height:10px; border-radius:2px; display:inline-block; }}
table {{ border-collapse:collapse; width:100%; font-size:13px; }} th, td {{ text-align:left; padding:6px 8px; border-bottom:1px solid var(--line); }}
.grid2 {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:16px; }}
</style></head><body><main>
<h1>Data Observability Dashboard</h1>
<p class="sub">Crossref → Clean → GX 1.x Gate → ChromaDB → RAG eval · generated {now_utc().strftime('%Y-%m-%d %H:%M UTC')}</p>
<div class="tiles">{''.join(tiles)}</div>
<section><h2>RAG metrics: Baseline vs Corrupted vs Repaired</h2>
<div class="legend"><span><i style="background:var(--baseline)"></i>Baseline</span><span><i style="background:var(--corrupted)"></i>Corrupted</span><span><i style="background:var(--repaired)"></i>Repaired</span></div>
{_metric_chart(metrics)}</section>
<div class="grid2">
<section><h2>Paper age — clean data (threshold {threshold} days)</h2>{_age_histogram(clean_rows, threshold)}</section>
<section><h2>Paper age — corrupted data</h2>{_age_histogram(corrupted_rows, threshold)}</section>
</div>
<section><h2>Great Expectations 1.x quality gate</h2>{_quality_table(quality)}</section>
<section><h2>Injected corruptions (seed {corruption_log.get('seed', '-')})</h2>
<table><thead><tr><th>Type</th><th>Rows</th><th>Description</th></tr></thead><tbody>{log_rows}</tbody></table></section>
</main></body></html>
"""
    write_text(output_path, page)
    return output_path
