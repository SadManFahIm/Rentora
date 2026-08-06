#!/usr/bin/env python3
"""Append this run's coverage to a persistent history and regenerate a chart.

GitHub-native alternative to Codecov: each main push appends one row to
`coverage/history.csv` and regenerates `coverage/index.html` (self-contained
SVG chart, no external assets). The CI job commits these onto the
`coverage-history` branch so the trend survives and is viewable in the repo.

Usage:
    python3 scripts/coverage_history.py <backend.xml> <frontend.xml> <out_dir>

`out_dir` must already exist and contain an optional previous `history.csv`.
"""

import csv
import datetime
import os
import sys
import xml.etree.ElementTree as ET


def line_rate(path):
    """Overall line rate (0..100) for a cobertura XML."""
    root = ET.parse(path).getroot()
    rate = float(root.get("line-rate", "0") or 0)
    return rate * 100


def parse_history(path):
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    return []


def render_chart(rows, out_path):
    """Self-contained HTML with an inline SVG bar chart + table."""
    latest = rows[-1] if rows else {}
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Coverage History — Rentora</title>
<style>
  body { font-family: system-ui, -apple-system, sans-serif; margin: 2rem auto; max-width: 900px; padding: 0 1rem; color: #1f2937; background: #fff; }
  h1 { font-size: 1.5rem; }
  .latest { display: flex; gap: 1.5rem; flex-wrap: wrap; margin: 1.5rem 0; }
  .card { flex: 1; min-width: 180px; border: 1px solid #e5e7eb; border-radius: 12px; padding: 1rem; }
  .card .val { font-size: 2rem; font-weight: 700; }
  .card .label { color: #6b7280; font-size: 0.85rem; }
  .good { color: #16a34a; } .mid { color: #d97706; } .bad { color: #dc2626; }
  table { border-collapse: collapse; width: 100%; font-size: 0.85rem; }
  th, td { padding: 0.5rem 0.75rem; text-align: left; border-bottom: 1px solid #f3f4f6; }
  th { color: #6b7280; font-weight: 600; }
  svg { width: 100%; height: 220px; }
  .note { color: #9ca3af; font-size: 0.75rem; margin-top: 2rem; }
</style>
</head>
<body>
<h1>📊 Coverage History</h1>
"""

    if latest:
        html += f"""<div class="latest">
  <div class="card"><div class="val"> {latest.get("merged", "—")}%</div><div class="label">Merged line rate</div></div>
  <div class="card"><div class="val"> {latest.get("frontend", "—")}%</div><div class="label">Frontend line rate</div></div>
  <div class="card"><div class="val"> {latest.get("backend", "—")}%</div><div class="label">Backend line rate</div></div>
  <div class="card"><div class="val">{latest.get("sha", "—")}</div><div class="label">Latest commit</div></div>
</div>
"""

    # SVG bar chart (last 30 runs), bars colored by threshold.
    recent = rows[-30:]
    bar_w, gap, height, baseline = 40, 12, 160, 180
    width = max(320, len(recent) * (bar_w + gap))
    bars = []
    labels = []
    for i, r in enumerate(recent):
        pct = float(r.get("merged", 0) or 0)
        h = max(2, height * pct / 100)
        x = i * (bar_w + gap)
        fill = "#16a34a" if pct >= 75 else "#d97706" if pct >= 50 else "#dc2626"
        bars.append(
            f'<rect x="{x}" y="{baseline - h}" width="{bar_w}" height="{h}" fill="{fill}" rx="3">'
            f"<title>{r.get('date', '')} — {pct:.0f}%</title></rect>"
        )
        labels.append(
            f'<text x="{x + bar_w / 2}" y="{baseline + 16}" font-size="9" text-anchor="middle" fill="#9ca3af">{r.get("sha", "")[:5]}</text>'
        )
    html += f"""<svg viewBox="0 0 {width} {baseline + 30}" role="img" aria-label="Coverage over time">
  <line x1="0" y1="{baseline - height}" x2="{width}" y2="{baseline - height}" stroke="#f3f4f6"/>
  <line x1="0" y1="{baseline - height * 0.75}" x2="{width}" y2="{baseline - height * 0.75}" stroke="#f3f4f6"/>
  <line x1="0" y1="{baseline - height * 0.5}" x2="{width}" y2="{baseline - height * 0.5}" stroke="#f3f4f6"/>
  <line x1="0" y1="{baseline - height * 0.25}" x2="{width}" y2="{baseline - height * 0.25}" stroke="#f3f4f6"/>
  <line x1="0" y1="{baseline}" x2="{width}" y2="{baseline}" stroke="#e5e7eb"/>
  {" ".join(bars)}{" ".join(labels)}
</svg>
"""

    rows_html = "".join(
        f"<tr><td>{r.get('date', '')}</td><td><code>{r.get('sha', '')}</code></td>"
        f"<td>{r.get('backend', '')}%</td><td>{r.get('frontend', '')}%</td>"
        f"<td>{r.get('merged', '')}%</td></tr>"
        for r in reversed(rows[-20:])
    )
    html += f"""<table>
  <thead><tr><th>Date</th><th>Commit</th><th>Backend</th><th>Frontend</th><th>Merged</th></tr></thead>
  <tbody>{rows_html}</tbody>
</table>
<p class="note">Updated automatically by GitHub Actions on every push to <code>main</code>. Thresholds: ≥75% green, 50–74% amber, &lt;50% red.</p>
</body>
</html>"""

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)


def main():
    if len(sys.argv) != 4:
        print(
            "usage: coverage_history.py <backend.xml> <frontend.xml> <out_dir>",
            file=sys.stderr,
        )
        return 2

    backend_xml, frontend_xml, out_dir = sys.argv[1:]
    sha = os.environ.get("GITHUB_SHA", "local")[:7]
    date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")

    backend = line_rate(backend_xml)
    frontend = line_rate(frontend_xml)

    csv_path = os.path.join(out_dir, "history.csv")
    rows = parse_history(csv_path)

    # Replace a row for the same sha if it already exists (retry/force-push).
    rows = [r for r in rows if r.get("sha", "") != sha]

    # Line totals aren't in the root element, so approximate "merged" as the
    # average of the two report rates.
    merged = round((backend + frontend) / 2, 1)
    rows.append(
        {
            "date": date,
            "sha": sha,
            "backend": f"{backend:.0f}",
            "frontend": f"{frontend:.0f}",
            "merged": f"{merged:.0f}",
        }
    )

    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["date", "sha", "backend", "frontend", "merged"]
        )
        writer.writeheader()
        writer.writerows(rows)

    render_chart(rows, os.path.join(out_dir, "index.html"))
    print(
        f"history: backend {backend:.0f}% frontend {frontend:.0f}% merged {merged:.0f}% ({len(rows)} rows)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
