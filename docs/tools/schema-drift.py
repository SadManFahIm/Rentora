#!/usr/bin/env python3
"""Diff two OpenAPI schema dumps and print a compact Markdown drift report.

Used by the CI `schema-drift` job: the PR head's schema is compared against
the base branch's schema. Any endpoint or component-schema change is listed
so reviewers see the API contract moving before merging — and the report is
posted as a PR comment.

Usage:
    python schema-drift.py base.json head.json [--out drift.md]

Exit code:
    0  — no drift (or only description/doc-comment changes)
    1  — drift found
    2  — error

Notes:
    - Component *properties* are compared by (name -> type-token); type-token
      resolves one level of $ref so `{"$ref": "#/components/schemas/RoomOwner"}`
      reports as `RoomOwner`. Nested ref targets are themselves diffed as
      components, so this stays readable without full recursion.
    - `description` / `title` / `example` fields are ignored (doc changes are
      not contract drift).
    - Enum value changes ARE reported (they break clients).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def type_token(schema: dict) -> str:
    """A compact, comparable signature for one schema object."""
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "allOf" in schema:
        return "allOf<" + "|".join(type_token(x) for x in schema["allOf"]) + ">"
    if "anyOf" in schema:
        return "anyOf<" + "|".join(type_token(x) for x in schema["anyOf"]) + ">"
    if "oneOf" in schema:
        return "oneOf<" + "|".join(type_token(x) for x in schema["oneOf"]) + ">"
    t = schema.get("type")
    if t == "array":
        items = schema.get("items", {})
        return f"array<{type_token(items)}>"
    if t == "string" and "enum" in schema:
        return "enum<" + ",".join(sorted(str(v) for v in schema["enum"])) + ">"
    if t == "object" and "properties" in schema:
        # Inline object (e.g. inline_serializer / raw dicts) — recurse shallow.
        inner = ",".join(
            f"{k}:{type_token(v)}" for k, v in sorted(schema["properties"].items())
        )
        return "object<" + inner + ">"
    return t or "?"


def property_map(component: dict) -> dict[str, str]:
    props = component.get("properties", {})
    return {name: type_token(schema) for name, schema in props.items()}


def diff_components(base: dict, head: dict) -> list[str]:
    lines: list[str] = []
    base_comps = base.get("components", {}).get("schemas", {})
    head_comps = head.get("components", {}).get("schemas", {})
    added = sorted(set(head_comps) - set(base_comps))
    removed = sorted(set(base_comps) - set(head_comps))
    if added:
        lines.append("#### Components added")
        lines.extend(f"- `{name}`" for name in added)
    if removed:
        lines.append("#### Components removed")
        lines.extend(f"- `{name}`" for name in removed)

    changed: list[tuple[str, list[str]]] = []
    for name in sorted(set(base_comps) & set(head_comps)):
        b_props = property_map(base_comps[name])
        h_props = property_map(head_comps[name])
        prop_lines: list[str] = []
        for prop in sorted(set(b_props) | set(h_props)):
            b_t, h_t = b_props.get(prop), h_props.get(prop)
            if b_t == h_t:
                continue
            if b_t is None:
                prop_lines.append(f"- `{prop}` **added**: `{h_t}`")
            elif h_t is None:
                prop_lines.append(f"- `{prop}` **removed** (was `{b_t}`)")
            else:
                prop_lines.append(f"- `{prop}` changed: `{b_t}` → `{h_t}`")
        if prop_lines:
            changed.append((name, prop_lines))
    if changed:
        lines.append("#### Component schema changes")
        for name, prop_lines in changed:
            lines.append(f"- **{name}**")
            lines.extend(f"  {line}" for line in prop_lines)
    return lines


def operation_id(op: dict) -> str:
    # Doc fields deliberately excluded — a wording change is not contract drift.
    return op.get("operationId") or op.get("summary") or ""


def endpoint_key(path: str, method: str) -> str:
    return f"{method.upper()} {path}"


def operation_contract(op: dict) -> str:
    """A signature covering request/response schema refs (ignoring status codes
    other than 2xx/4xx summaries to keep the report tight)."""
    req = ""
    rb = op.get("requestBody", {})
    content = rb.get("content", {}) if isinstance(rb, dict) else {}
    if content:
        schema = next(iter(content.values())).get("schema", {})
        req = f" req={type_token(schema)}"
    resp = ""
    for status, r in op.get("responses", {}).items():
        if status.startswith("2"):
            content = r.get("content", {})
            if content:
                schema = next(iter(content.values())).get("schema", {})
                resp += f" resp{status}={type_token(schema)}"
    return f"{operation_id(op)}{req}{resp}"


def diff_endpoints(base: dict, head: dict) -> list[str]:
    lines: list[str] = []
    b_paths = base.get("paths", {})
    h_paths = head.get("paths", {})
    for path in sorted(set(h_paths) - set(b_paths)):
        methods = ", ".join(
            m.upper()
            for m in h_paths[path]
            if m in ("get", "post", "put", "patch", "delete")
        )
        lines.append(f"- `{path}` **added** ({methods})")
    for path in sorted(set(b_paths) - set(h_paths)):
        methods = ", ".join(
            m.upper()
            for m in b_paths[path]
            if m in ("get", "post", "put", "patch", "delete")
        )
        lines.append(f"- `{path}` **removed** ({methods})")

    changed: list[str] = []
    for path in sorted(set(b_paths) & set(h_paths)):
        b_op, h_op = b_paths[path], h_paths[path]
        for method in ("get", "post", "put", "patch", "delete"):
            if method not in b_op and method not in h_op:
                continue
            if method not in b_op:
                changed.append(f"- `{endpoint_key(path, method)}` **added**")
                continue
            if method not in h_op:
                changed.append(f"- `{endpoint_key(path, method)}` **removed**")
                continue
            if operation_contract(b_op[method]) != operation_contract(h_op[method]):
                changed.append(
                    f"- `{endpoint_key(path, method)}` contract changed:\n"
                    f"    - base: {operation_contract(b_op[method])}\n"
                    f"    - head: {operation_contract(h_op[method])}"
                )
    if changed:
        lines.append("#### Endpoint changes")
        lines.extend(changed)
    return lines


def build_report(base: dict, head: dict) -> str:
    ep = diff_endpoints(base, head)
    comp = diff_components(base, head)
    if not ep and not comp:
        return ""
    lines = ["## 🧬 API schema drift", ""]
    if ep:
        lines.extend(ep)
        lines.append("")
    if comp:
        lines.extend(comp)
        lines.append("")
    lines.append(
        "_Generated by `docs/tools/schema-drift.py` — a contract change here "
        "means the frontend contract check and API docs need review._"
    )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base", help="OpenAPI JSON dump of the base branch")
    ap.add_argument("head", help="OpenAPI JSON dump of the head (PR) branch")
    ap.add_argument("--out", help="Write report to this file (otherwise stdout)")
    args = ap.parse_args()
    try:
        base = load(args.base)
        head = load(args.head)
    except Exception as exc:  # noqa: BLE001 - CLI tool; any load failure is a clear error message
        print(f"error: failed to load schema: {exc}", file=sys.stderr)
        return 2
    report = build_report(base, head)
    if not report:
        print("No API schema drift detected.")
        return 0
    if args.out:
        Path(args.out).write_text(report + "\n", encoding="utf-8")
        print(f"Drift found — report written to {args.out}")
    else:
        print(report)
    return 1


if __name__ == "__main__":
    import os

    # The report contains emoji; force UTF-8 on Windows consoles that default
    # to cp1252.
    if (
        os.name == "nt"
        and sys.stdout.encoding
        and sys.stdout.encoding.lower() != "utf-8"
    ):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
