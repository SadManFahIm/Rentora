#!/usr/bin/env python3
"""Append this run's coverage to a persistent history and regenerate a chart.

GitHub-native alternative to Codecov: every CI run (main push or PR branch)
appends one row to `history-<branch>.csv` and regenerates `history-<branch>.html`
(a self-contained SVG chart) plus an `index.html` that links every branch's
history. The CI job commits these onto the `coverage-history` branch so the
trend survives and is viewable in the repo.

Usage:
    BRANCH=main python3 scripts/coverage_history.py <backend.xml> <frontend.xml> <out_dir>

`out_dir` must already exist and contain the optional previous `history-*.csv`
files pulled from the coverage-history branch.
"""

import csv
import datetime
import os
import re
import sys
import xml.etree.ElementTree as ET


def sanitize_branch(name):
    """Filesystem-safe branch name (PR refs like `refs/pull/1/merge` included)."""
    return re.sub(r"[^A-Za-z0-9_.-]", "-", name) or "unknown"


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


def _page(title, body):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Rentora</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; margin: 2rem auto; max-width: 900px; padding: 0 1rem; color: #1f2937; background: #fff; }}
  h1 {{ font-size: 1.5rem; }}
  .latest {{ display: flex; gap: 1.5rem; flex-wrap: wrap; margin: 1.5rem 0; }}
  .card {{ flex: 1; min-width: 180px; border: 1px solid #e5e7eb; border-radius: 12px; padding: 1rem; }}
  .card .val {{ font-size: 2rem; font-weight: 700; }}
  .card .label {{ color: #6b7280; font-size: 0.85rem; }}
  .good {{ color: #16a34a; }} .mid {{ color: #d97706; }} .bad {{ color: #dc2626; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; }}
  th, td {{ padding: 0.5rem 0.75rem; text-align: left; border-bottom: 1px solid #f3f4f6; }}
  th {{ color: #6b7280; font-weight: 600; }}
  svg {{ width: 100%; height: 220px; }}
  .nav {{ margin: 1rem 0 2rem; display: flex; flex-wrap: wrap; gap: 0.5rem; }}
  .nav a {{ text-decoration: none; border: 1px solid #e5e7eb; border-radius: 999px; padding: 0.35rem 0.8rem; font-size: 0.8rem; color: #374151; }}
  .nav a.active {{ background: #f3f4f6; border-color: #d1d5db; font-weight: 600; }}
  .note {{ color: #9ca3af; font-size: 0.75rem; margin-top: 2rem; }}
</style>
</head>
<body>{body}</body>
</html>"""


def render_chart(rows, branch, out_path):
    """Self-contained HTML with an inline SVG bar chart + table for one branch."""
    latest = rows[-1] if rows else {}
    body = f'<h1>📊 Coverage History — <code>{branch}</code></h1>\n'
    if latest:
        body += f"""<div class="latest">
  <div class="card"><div class="val"> {latest.get("merged", "—")}%</div><div class="label">Merged line rate</div></div>
  <div class="card"><div class="val"> {latest.get("frontend", "—")}%</div><div class="label">Frontend line rate</div></div>
  <div class="card"><div class="val"> {latest.get("backend", "—")}%</div><div class="label">Backend line rate</div></div>
  <div class="card"><div class="val">{latest.get("sha", "—")}</div><div class="label">Latest commit</div></div>
</div>
"""
    recent = rows[-30:]
    bar_w, gap, height, baseline = 40, 12, 160, 180
    width = max(320, len(recent) * (bar_w + gap))
    bars, labels = [], []
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
    body += f"""<svg viewBox="0 0 {width} {baseline + 30}" role="img" aria-label="Coverage over time for {branch}">
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
    body += f"""<table>
  <thead><tr><th>Date</th><th>Commit</th><th>Backend</th><th>Frontend</th><th>Merged</th></tr></thead>
  <tbody>{rows_html}</tbody>
</table>
<p class="note">Updated automatically by GitHub Actions on every push/PR. Thresholds: ≥75% green, 50–74% amber, &lt;50% red.</p>
"""
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(_page(f"Coverage History — {branch}", body))


def render_index(out_dir, active_branch):
    """Overview page linking every branch's history (active branch highlighted)."""
    branch_files = sorted(
        f[len("history-") : -len(".csv")]
        for f in os.listdir(out_dir)
        if f.startswith("history-") and f.endswith(".csv")
    )
    nav = '<div class="nav">'
    for b in branch_files:
        active = ' class="active"' if b == active_branch else ""
        nav += f'<a{active} href="history-{b}.html">{b}</a>'
    nav += "</div>"

    # Embed the active branch's chart (or main's if available).
    embed = active_branch if active_branch in branch_files else (
        "main" if "main" in branch_files else (branch_files[0] if branch_files else None)
    )
    if embed:
        with open(os.path.join(out_dir, f"history-{embed}.html"), encoding="utf-8") as fh:
            inner = fh.read()
        body = inner.split("<body>", 1)[1].split("</body>", 1)[0]
    else:
        body = "<p>No coverage history recorded yet.</p>"

    body = (
        '<h1>📊 Coverage History — All Branches</h1>'
        + nav
        + body
    )
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(_page("Coverage History — All Branches", body))


def main():
    if len(sys.argv) != 4:
        print("usage: coverage_history.py <backend.xml> <frontend.xml> <out_dir>", file=sys.stderr)
        return 2

    backend_xml, frontend_xml, out_dir = sys.argv[1:]
    os.makedirs(out_dir, exist_ok=True)

    branch = sanitize_branch(os.environ.get("BRANCH", "main"))
    sha = os.environ.get("GITHUB_SHA", "local")[:7]
    date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")

    backend = line_rate(backend_xml)
    frontend = line_rate(frontend_xml)

    csv_path = os.path.join(out_dir, f"history-{branch}.csv")
    rows = parse_history(csv_path)

    # Replace a row for the same sha if it already exists (retry/force-push).
    rows = [r for r in rows if r.get("sha", "") != sha]

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
        writer = csv.DictWriter(fh, fieldnames=["date", "sha", "backend", "frontend", "merged"])
        writer.writeheader()
        writer.writerows(rows)

    render_chart(rows, branch, os.path.join(out_dir, f"history-{branch}.html"))
    render_index(out_dir, branch)
    print(
        f"history[{branch}]: backend {backend:.0f}% frontend {frontend:.0f}% "
        f"merged {merged:.0f}% ({len(rows)} rows)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
