#!/usr/bin/env python3
"""Gate review findings against the review surface.

Every finding must anchor to the diff. This script decides, per finding,
whether it is:

  DIFF-CONTAINED  the line is an added (or removed) line in the diff   -> blocking-eligible
  DIFF-CAUSED     the line is outside the diff, but caused_by names a
                  real hunk in the diff                               -> blocking-eligible
  PR-LEVEL        a property of the change as a whole (no tests, title
                  does not match scope, migration without rollback)   -> blocking-eligible
  DIFF-ADJACENT   a context line inside a hunk, no causal chain       -> appendix
  PRE-EXISTING    outside the diff, no causal chain                   -> appendix
  NOT-IN-PR       the file is not in the diff at all                   -> appendix

Appendix findings are never blocking and never counted in the verdict. A
finding with no line, an unknown severity, or a caused_by that points at
nothing real is rejected as malformed — the gate refuses to produce a verdict
until it is fixed, rather than silently demoting a real diff-caused finding.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

SEVERITIES = ("BLOCKER", "MAJOR", "MINOR", "NIT")
BLOCKING_CLASSES = ("DIFF-CONTAINED", "DIFF-CAUSED", "PR-LEVEL")
APPENDIX_CLASSES = ("DIFF-ADJACENT", "PRE-EXISTING", "NOT-IN-PR")
MALFORMED_CLASSES = ("UNANCHORED", "BAD-SEVERITY", "INVALID-CHAIN")


def index_surface(surface: dict[str, Any]) -> dict[str, dict[str, Any]]:
    idx: dict[str, dict[str, Any]] = {}
    for f in surface.get("files", []):
        idx[f["path"]] = {
            "added": set(f.get("added_lines", [])),
            "removed": set(f.get("removed_lines", [])),
            "context": set(f.get("context_lines", [])),
            "hunks": {h["id"]: h for h in f.get("hunks", [])},
            "generated": bool(f.get("generated")),
            "change_kind": f.get("change_kind", "modified"),
        }
        old = f.get("old_path")
        if old and old != f["path"] and old not in idx:
            idx[old] = idx[f["path"]]  # findings may cite the pre-rename path
    return idx


def resolve_chain(chain: str, idx: dict[str, dict[str, Any]]) -> tuple[bool, str]:
    """caused_by is 'path:H3' or 'path:142'. Returns (valid, explanation)."""
    if ":" not in chain:
        return False, "caused_by must be 'path:HUNK_ID' or 'path:LINE' (e.g. app/X.php:H1)"
    path, ref = chain.rsplit(":", 1)
    path, ref = path.strip(), ref.strip()
    entry = idx.get(path)
    if entry is None:
        return False, f"caused_by cites '{path}', which is not in the diff"
    if ref.upper().startswith("H"):
        if ref.upper() in {k.upper() for k in entry["hunks"]}:
            return True, f"chain anchored to {path}:{ref.upper()}"
        return False, f"caused_by cites hunk {ref} of {path}, which has no such hunk"
    if ref.isdigit():
        n = int(ref)
        if n in entry["added"]:
            return True, f"chain anchored to added line {path}:{n}"
        if n in entry["removed"]:
            return True, f"chain anchored to removed line {path}:{n}"
        return False, f"caused_by cites {path}:{n}, which is not an added or removed line"
    return False, f"caused_by reference '{ref}' is neither a hunk id nor a line number"


def classify(finding: dict[str, Any], idx: dict[str, dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": finding.get("id") or "(unnamed)",
        "file": finding.get("file"),
        "line": finding.get("line"),
        "side": (finding.get("side") or "new").lower(),
        "severity": str(finding.get("severity", "")).upper(),
        "claim": finding.get("claim", ""),
        "caused_by": finding.get("caused_by"),
        "notes": [],
    }

    if out["severity"] not in SEVERITIES:
        out["klass"] = "BAD-SEVERITY"
        out["reason"] = f"severity must be one of {', '.join(SEVERITIES)}; got {out['severity'] or '(missing)'}"
        return out

    if str(finding.get("scope", "")).lower() == "pr-level":
        out["klass"] = "PR-LEVEL"
        out["reason"] = "a property of the change as a whole, not of one line"
        return out

    if not out["file"]:
        out["klass"] = "UNANCHORED"
        out["reason"] = "no file. Give file+line, or set scope: 'pr-level' if it is about the whole change"
        return out

    if out["line"] is None:
        out["klass"] = "UNANCHORED"
        out["reason"] = "file is in the diff but no line given — name the line or use scope: 'pr-level'"
        return out

    try:
        line = int(out["line"])
    except (TypeError, ValueError):
        out["klass"] = "UNANCHORED"
        out["reason"] = f"line must be an integer; got {out['line']!r}"
        return out

    # The causal chain is resolved BEFORE asking whether the finding's own file
    # is in the diff. A diff-caused finding lives, by definition, in a file the
    # diff does not touch — that is the whole point of the class.
    chain_ok, chain_why = (False, "")
    if out["caused_by"]:
        chain_ok, chain_why = resolve_chain(str(out["caused_by"]), idx)
        if not chain_ok:
            out["klass"] = "INVALID-CHAIN"
            out["reason"] = chain_why
            return out

    entry = idx.get(out["file"])
    if entry is None:
        if chain_ok:
            out["klass"] = "DIFF-CAUSED"
            out["reason"] = f"{out['file']}:{line} is outside the diff, but {chain_why}"
            return out
        out["klass"] = "NOT-IN-PR"
        out["reason"] = (
            f"{out['file']} is not in this diff and no caused_by was given — "
            "this PR cannot be blocked on it"
        )
        return out

    in_added = out["side"] == "new" and line in entry["added"]
    in_removed = out["side"] == "old" and line in entry["removed"]
    if in_added or in_removed:
        out["klass"] = "DIFF-CONTAINED"
        out["reason"] = f"{'added' if in_added else 'removed'} line {out['file']}:{line}"
        if entry["generated"]:
            out["notes"].append(
                "file is generated — make sure the claim is about the dependency/version decision, "
                "not the shape of a machine-written line"
            )
        if chain_ok:
            out["notes"].append("caused_by not needed for a diff-contained finding")
        return out

    if chain_ok:
        out["klass"] = "DIFF-CAUSED"
        out["reason"] = f"outside the diff, but {chain_why}"
        return out

    # A context line, or a line inside a hunk's new range that the diff did not
    # record as context (truncated or context-free diff). Either way the diff
    # showed it without changing it.
    in_hunk_range = next(
        (h["id"] for h in entry["hunks"].values()
         if h["new_start"] <= line <= h["new_end"]),
        None,
    )
    if line in entry["context"] or in_hunk_range:
        out["klass"] = "DIFF-ADJACENT"
        where = f"a context line in {in_hunk_range}" if in_hunk_range else "a context line"
        out["reason"] = (
            f"{out['file']}:{line} is {where} — shown by the diff, not changed by it. "
            "Add caused_by naming the hunk that breaks it, or leave it in the appendix"
        )
        return out

    out["klass"] = "PRE-EXISTING"
    nearest = min(entry["added"], key=lambda n: abs(n - line)) if entry["added"] else None
    hint = f" Nearest added line in this file is {nearest} — check the line number." if nearest else ""
    out["reason"] = (
        f"{out['file']}:{line} is not touched by this diff and no caused_by was given. "
        f"This PR did not introduce it.{hint}"
    )
    return out


def gate(findings: list[dict[str, Any]], surface: dict[str, Any]) -> dict[str, Any]:
    idx = index_surface(surface)
    results = [classify(f, idx) for f in findings]

    malformed = [r for r in results if r["klass"] in MALFORMED_CLASSES]
    blocking_pool = [r for r in results if r["klass"] in BLOCKING_CLASSES]
    appendix = [r for r in results if r["klass"] in APPENDIX_CLASSES]

    for r in appendix:
        if r["severity"] in ("BLOCKER", "MAJOR"):
            r["notes"].append(
                f"DEMOTED: {r['severity']} -> appendix (non-blocking). "
                "Severity describes the bug; scope decides whether this PR pays for it"
            )

    blocking = [r for r in blocking_pool if r["severity"] in ("BLOCKER", "MAJOR")]
    nits = [r for r in blocking_pool if r["severity"] in ("MINOR", "NIT")]

    if malformed:
        verdict, exit_code = "INPUT-REJECTED", 3
    elif blocking:
        verdict, exit_code = "REQUEST-CHANGES", 1
    elif nits:
        verdict, exit_code = "APPROVE-WITH-NITS", 0
    else:
        verdict, exit_code = "APPROVE", 0

    total = len(results)
    in_scope = len(blocking_pool)
    discipline: list[str] = []
    if total >= 4 and in_scope * 2 < total:
        discipline.append(
            f"SCOPE DRIFT: {total - in_scope} of {total} findings are out of scope for this PR. "
            "The author will act on the in-scope ones and skim the rest — move the appendix to its own issue"
        )
    if blocking_pool and all(r["klass"] == "PR-LEVEL" for r in blocking_pool):
        discipline.append(
            "Every blocking finding is PR-level. Confirm you actually read the changed lines"
        )

    return {
        "schema": "scope_gate.v1",
        "verdict": verdict,
        "exit_code": exit_code,
        "counts": {
            "total": total,
            "blocking": len(blocking),
            "nits": len(nits),
            "appendix": len(appendix),
            "malformed": len(malformed),
        },
        "malformed": malformed,
        "blocking": blocking,
        "nits": nits,
        "appendix": appendix,
        "discipline_notes": discipline,
    }


def _fmt(r: dict[str, Any]) -> list[str]:
    loc = f"{r['file']}:{r['line']}" if r["file"] and r["line"] is not None else (r["file"] or "(whole PR)")
    head = f"  [{r['severity']}] {loc}  ({r['klass']})  {r['id']}"
    lines = [head]
    if r["claim"]:
        lines.append(f"      {r['claim']}")
    lines.append(f"      why: {r['reason']}")
    for n in r["notes"]:
        lines.append(f"      note: {n}")
    return lines


def render_text(g: dict[str, Any]) -> str:
    c = g["counts"]
    out = [
        f"SCOPE GATE -> {g['verdict']}",
        f"  {c['total']} findings: {c['blocking']} blocking, {c['nits']} nits, "
        f"{c['appendix']} appendix, {c['malformed']} malformed",
        "",
    ]
    if g["malformed"]:
        out.append("MALFORMED — fix these, the gate will not issue a verdict until then")
        for r in g["malformed"]:
            out.extend(_fmt(r))
        out.append("")
    if g["blocking"]:
        out.append("BLOCKING — caused by this PR")
        for r in g["blocking"]:
            out.extend(_fmt(r))
        out.append("")
    if g["nits"]:
        out.append("NITS — in scope, not blocking")
        for r in g["nits"]:
            out.extend(_fmt(r))
        out.append("")
    if g["appendix"]:
        out.append("APPENDIX — observed, out of scope for this PR (never blocking)")
        for r in g["appendix"]:
            out.extend(_fmt(r))
        out.append("")
    if g["discipline_notes"]:
        out.append("REVIEWER DISCIPLINE")
        for n in g["discipline_notes"]:
            out.append(f"  - {n}")
    return "\n".join(out).rstrip()


SAMPLE_SURFACE = {
    "schema": "review_surface.v1",
    "files": [
        {
            "path": "app/Services/EntitlementService.php",
            "old_path": "app/Services/EntitlementService.php",
            "change_kind": "modified",
            "added_lines": [42, 43, 44, 45, 46],
            "removed_lines": [42, 43],
            "context_lines": [40, 41, 47, 48],
            "hunks": [{"id": "H1", "old_start": 40, "old_end": 48, "new_start": 40, "new_end": 51,
                       "added": 5, "removed": 2, "header": "-40,9 +40,12", "section": "class EntitlementService"}],
            "generated": False, "generated_reason": "", "whitespace_or_move_only": False,
            "added_count": 5, "removed_count": 2,
        }
    ],
    "totals": {},
}

SAMPLE_FINDINGS = [
    {"id": "F1", "file": "app/Services/EntitlementService.php", "line": 43, "severity": "BLOCKER",
     "claim": "seen($txnId) is checked but never recorded, so the dedupe never takes effect on retry"},
    {"id": "F2", "file": "app/Http/Controllers/PurchaseController.php", "line": 88, "severity": "MAJOR",
     "claim": "still calls grant() with two arguments; the third is now required for dedupe",
     "caused_by": "app/Services/EntitlementService.php:H1"},
    {"id": "F3", "file": "app/Services/EntitlementService.php", "line": 41, "severity": "MAJOR",
     "claim": "this whole class does raw SQL string building"},
    {"id": "F4", "scope": "pr-level", "severity": "MAJOR",
     "claim": "changes idempotency behaviour of entitlement granting with no test for the retry path"},
    {"id": "F5", "file": "app/Services/LegacyBillingService.php", "line": 12, "severity": "BLOCKER",
     "claim": "unrelated service logs full receipt payloads"},
    {"id": "F6", "file": "app/Services/EntitlementService.php", "line": 44, "severity": "NIT",
     "claim": "early return could use a guard clause helper"},
    {"id": "F7", "file": "app/Services/EntitlementService.php", "line": 210, "severity": "MAJOR",
     "claim": "revoke() further down the same class has no dedupe at all"},
]


def load(path: str | None, sample: Any, key: str | None = None) -> Any:
    if path is None:
        return sample
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if key and isinstance(data, dict) and key in data:
        return data[key]
    return data


def main() -> int:
    p = argparse.ArgumentParser(
        description="Classify review findings against the review surface; keep only diff-caused findings blocking.",
        epilog="Exit codes: 0 approve / approve-with-nits, 1 request-changes, 3 malformed findings (no verdict issued).",
    )
    p.add_argument("--findings", metavar="FILE",
                   help="JSON: a list of findings, or {'findings': [...]}")
    p.add_argument("--surface", metavar="FILE",
                   help="review surface JSON from diff_surface_builder.py")
    p.add_argument("--sample", action="store_true", help="run on a built-in sample (one finding of each class)")
    p.add_argument("--output", choices=["text", "json"], default="text", help="output format (default: text)")
    p.add_argument("--print-schema", action="store_true", help="print the findings input schema and exit")
    p.add_argument("--out", metavar="FILE", help="write output to FILE instead of stdout")
    args = p.parse_args()

    if args.print_schema:
        print(json.dumps({
            "findings": [{
                "id": "F1 (optional label)",
                "file": "path/as/it/appears/in/the/diff.php  (omit only with scope: pr-level)",
                "line": "integer line number",
                "side": "new (default) | old — use 'old' when the finding is about a removed line",
                "severity": "BLOCKER | MAJOR | MINOR | NIT",
                "claim": "what is wrong, in one sentence",
                "caused_by": "path:H1 or path:142 — required when the line is outside the diff",
                "scope": "pr-level — only for findings about the whole change (no file/line)",
            }]
        }, indent=2))
        return 0

    if args.sample:
        findings, surface = SAMPLE_FINDINGS, SAMPLE_SURFACE
    else:
        if not args.findings or not args.surface:
            sys.exit("pass --findings FILE and --surface FILE, or --sample")
        findings = load(args.findings, None, key="findings")
        surface = load(args.surface, None)

    if not isinstance(findings, list):
        sys.exit("findings must be a JSON list, or an object with a 'findings' list")
    if not isinstance(surface, dict) or "files" not in surface:
        sys.exit("surface must be review surface JSON (an object with a 'files' key)")

    g = gate(findings, surface)
    rendered = json.dumps(g, indent=2) if args.output == "json" else render_text(g)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(rendered + "\n")
        print(f"wrote {args.out}  verdict={g['verdict']}")
    else:
        print(rendered)
    return g["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
