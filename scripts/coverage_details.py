#!/usr/bin/env python3
"""Append a "worst files" table to the CodeCoverageSummary markdown.

Reads Cobertura XML reports (backend + frontend), finds the files with the
lowest line coverage, and appends a markdown table to the summary file that
the sticky-pull-request-comment action later posts to the PR.

Usage:
    python3 scripts/coverage_details.py <report1.xml> [<report2.xml> ...] <summary.md>
"""

import os
import sys
import xml.etree.ElementTree as ET


def parse_files(path):
    """Return list of (filename, line_rate, lines_valid) from a cobertura XML."""
    root = ET.parse(path).getroot()
    files = []
    for cls in root.iter("class"):
        fname = cls.get("filename")
        if not fname:
            continue
        try:
            rate = float(cls.get("line-rate", "0"))
        except ValueError:
            rate = 0.0
        # <class> carries no line count attr in coverage.py/v8 output — count
        # the nested <line> elements instead.
        valid = len(cls.findall(".//line"))
        files.append((fname, rate, valid))
    return files


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        print(
            "usage: coverage_details.py <report.xml>... <summary.md>", file=sys.stderr
        )
        return 2

    summary_path = args[-1]
    reports = args[:-1]

    files = []
    for report in reports:
        files.extend(parse_files(report))

    # Skip trivial files (e.g. __init__, empty stubs) — only meaningful code.
    meaningful = [f for f in files if f[2] >= 5]
    if not meaningful:
        print("No meaningful files found in reports.", file=sys.stderr)
        return 0

    # Sort by line rate ascending, tie-broken by most lines first (bigger risk).
    worst = sorted(meaningful, key=lambda f: (f[1], -f[2]))[:10]

    def fmt(pct):
        p = pct * 100
        icon = "✔" if p >= 75 else "➖" if p >= 50 else "❌"
        return f"{p:.0f}% {icon}"

    rows = "\n".join(
        f"| `{fname}` | {fmt(rate)} | {valid} lines |" for fname, rate, valid in worst
    )

    section = (
        "\n\n### 📉 Lowest coverage files\n\n"
        "| File | Line Rate | Lines |\n"
        "| --- | --- | --- |\n"
        f"{rows}\n\n"
        "_Top 10 worst by line rate — good candidates for the next tests._\n"
    )

    # The summary file is written by CodeCoverageSummary's Docker step as
    # root, so appending in place fails for the runner user. Recreate the
    # file (delete + rewrite) — the directory is owned by the runner.
    try:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(section)
    except PermissionError:
        with open(summary_path, encoding="utf-8") as fh:
            content = fh.read()
        with open(summary_path + ".new", "w", encoding="utf-8") as fh:
            fh.write(content + section)
        os.replace(summary_path + ".new", summary_path)

    print(f"Appended {len(worst)} worst files to {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
