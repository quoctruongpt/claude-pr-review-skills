#!/usr/bin/env python3
"""Allocate review attention inside the review surface.

Diff-scoped does not mean flat. This router reads a review surface (from
diff_surface_builder.py) and decides, per file, how deep to read and which
sibling skill to pull in. It also lists causal watch items: lines inside the
diff that can break code outside the diff, with the command to go find that
code.

It reports no findings of its own. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

# (regex over lowercased path, points, label, sibling skills/agents)
# Stacks: TypeScript/Node, React Native, Dart/Flutter, C#/.NET/Unity, PHP/Laravel, Go
PATH_SIGNALS: list[tuple[str, int, str, list[str]]] = [
    (r"(payment|billing|invoice|subscription|entitlement|receipt|purchase|iap|in_?app|refund|checkout|stripe|"
     r"revenuecat|storekit|play_?billing|wallet|coin|gem|currency|reward|ledger)",
     4, "money/entitlement path", ["breaker (agent)"]),
    (r"(webhook|callback|notification[s]?/|pubsub|/sns/|deeplink|deep_link|universal_?link)",
     4, "untrusted inbound payload", ["breaker (agent)"]),
    (r"(auth|login|logout|session|token|jwt|oauth|password|credential|permission|policy|acl|guard|middleware|"
     r"keychain|keystore|secure_?storage|encrypt|crypto)",
     4, "auth / trust boundary", ["breaker (agent)"]),
    (r"(migration[s]?/|/schema|\.sql$|schema\.prisma$|prisma/|drizzle|knexfile|typeorm|sequelize|"
     r"dbcontext|/entities/|drift|isar|hive|realm|sqflite|room)",
     4, "schema or data migration", ["migration"]),
    (r"(androidmanifest\.xml|info\.plist|\.entitlements$|podfile$|build\.gradle|gradle\.properties|"
     r"app\.json$|app\.config\.[jt]s$|eas\.json$|pubspec\.yaml$|\.csproj$|projectsettings/|"
     r"google-services|googleservice-info|firebase|proguard|codemagic|fastlane)",
     3, "mobile/native build & permissions", []),
    (r"(\.env|/config/|settings\.|appsettings|\.ya?ml$|\.tf$|helm/|/k8s/|dockerfile|docker-compose|"
     r"next\.config|nest-cli|tsconfig|babel\.config|metro\.config)",
     3, "config / infra surface", []),
    (r"(route[s]?[./]|/controllers?/|controller\.|/handlers?/|/resolvers?/|graphql|openapi|swagger|\.proto$|"
     r"/api/|trpc|/endpoints?/|/dto[s]?/|\.dto\.|/requests?/|/resources?/|/hubs?/)",
     2, "external API contract", []),
    (r"(queue|job[s]?/|worker|consumer|cron|scheduler|/task|isolate|background|bullmq|hangfire|"
     r"coroutine|horizon|goroutine)",
     2, "async execution path", ["breaker (agent)"]),
    (r"(redis|memcache|mutex|semaphore|concurren|/locks?[/.]|lock_manager|distributed_?lock|cache)",
     2, "shared-state / concurrency", ["breaker (agent)"]),
    (r"(/screens?/|/pages?/|/components?/|/widgets?/|/views?/|/ui/|\.tsx$|\.blade\.php$|\.xaml$|\.uxml$|\.uss$)",
     1, "UI surface", ["ui-ux-pro-max"]),
    (r"(/log|metric|telemetry|tracing|analytics|crashlytics|sentry|dashboard)",
     1, "observability surface", []),
]

TEST_RE = re.compile(
    r"(^|/)(tests?|spec|specs|__tests__|e2e|integration_test|test_driver|testing)/"
    r"|(_test\.|\.test\.|\.spec\.|\.e2e\.|test_[^/]+\.py$|Test\.php$|Tests?\.cs$|_test\.dart$|_test\.go$)"
    r"|(^|/)[^/]*\.Tests?/|(^|/)Tests/(EditMode|PlayMode)/"
)
DOC_RE = re.compile(r"\.(md|mdx|rst|txt|adoc)$|^(docs|documentation)/|(^|/)(readme|changelog|license)", re.I)

# Causal watch patterns: in-diff text that can break out-of-diff code.
_KW = r"(?!(?:if|for|while|switch|catch|return|await|new|throw|using|lock|foreach|sizeof|typeof|nameof|else|yield|case|in|is|as|out|ref|do|go|defer|delete|void\s+0)\b)"
SIG_RE = re.compile(
    # Go: func Name( / func (r *T) Name(
    r"\bfunc\s+(?:\([^)]*\)\s*)?(?P<name>[A-Za-z_]\w*)\s*[\[(]"
    # TS/JS/PHP: function name( / def name(
    r"|\b(?:def|function|fn|sub)\s+(?P<fname>[A-Za-z_]\w*)\s*[<(]"
    r"|\b(?:public|private|protected|static|final|async)\s+(?:static\s+)?function\s+(?P<pname>[A-Za-z_]\w*)\s*\("
    # TS/JS arrow: name = (..) => / name: async (..) =>
    r"|(?P<jsname>[A-Za-z_]\w*)\s*[:=]\s*(?:async\s*)?(?:<[^>]*>)?\((?P<jsargs>[^)]*)\)\s*(?::\s*[^=]+)?=>"
    # C# / Dart / TS class method: [modifiers] Type Name(args) { | => | async
    r"|^\s*(?:(?:public|private|protected|internal|static|async|override|virtual|abstract|sealed|readonly|"
    r"extern|partial|external|factory|export|default)\s+)*" + _KW +
    r"(?:[A-Za-z_][\w.]*(?:<[^()]*>)?\??(?:\[\])?\s+)" + _KW +
    r"(?P<mname>[A-Za-z_]\w*)\s*(?:<[^()]*>)?\([^;]*\)\s*(?:async\s*\*?|:\s*[^{;=]+|where\s+[^{]+)?\s*(?:\{.*$|=>.*$|$)"
)
EXPORT_RE = re.compile(
    r"^\s*(?:export\s+(?:default\s+)?|module\.exports|exports\.|public\s+|__all__|"
    r"func\s+(?:\([^)]*\)\s*)?[A-Z]|type\s+[A-Z]\w*\s|var\s+[A-Z]|const\s+[A-Z])"
)
DEFAULT_RE = re.compile(r"=\s*(?:true|false|null|nil|none|undefined|\d+(?:\.\d+)?|'[^']*'|\"[^\"]*\")\s*[,;)]?\s*$", re.I)
GUARD_RE = re.compile(
    r"\b(?:if\s*\(?\s*!|if\s+not\s|unless\s|assert\b|throw\b|raise\b|abort\s*\(|panic\s*\(|"
    r"return\s+(?:false|nil|null|err\b|res\.status\(4)|if\s+err\s*!=\s*nil|validate|authoriz|permit|can\s*\(|guard\b|"
    r"requireAuth|isAuthenticated|ensure|ThrowIf|ArgumentNullException|ArgumentException|Gate::|"
    r"safeParse|z\.object|ModelState\.IsValid)"
    r"|(?:\[Authorize|\[AllowAnonymous|@UseGuards|@Roles|@Is[A-Z]|\?\?\s*throw|->middleware\(|\$this->authorize)",
    re.I,
)
ENUM_RE = re.compile(
    r"\b(?:case|enum|const)\s+[A-Z][A-Za-z0-9_]*\s*[=:(,;{]"          # PHP/TS/Swift-style case/const
    r"|^\s*[A-Z][A-Z0-9_]{2,}\s*[=:,]"                                # SCREAMING_CASE member
    r"|^\s*[A-Z][A-Za-z0-9_]*\s*=\s*(?:['\"\d]|iota)"                # TS/C# enum member, Go iota
    r"|^\s*[A-Z]\w*\s+[A-Z]\w*\s*=\s*['\"\d]"                        # Go typed const: StatusX Status = "x"
    r"|^\s*\|\s*['\"][\w-]+['\"]"                                     # TS string-literal union variant
)


def _callers_cmd(name: str, path: str) -> str:
    # srcwalk has no Dart grammar; Dart falls back to rg
    if path.lower().endswith(".dart"):
        return f"rg -n -w '{name}' -g '*.dart'"
    return f"srcwalk trace callers {name}   # sweep: rg -n -w '{name}'"


def path_risk(path: str) -> tuple[int, list[str], list[str]]:
    low = path.lower()
    pts = 0
    labels: list[str] = []
    skills: list[str] = []
    for pattern, points, label, sib in PATH_SIGNALS:
        if re.search(pattern, low):
            pts += points
            labels.append(label)
            for s in sib:
                if s not in skills:
                    skills.append(s)
    return pts, labels, skills


def _sig_names(lines: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in lines:
        m = SIG_RE.search(line)
        if m:
            name = m.group("name") or m.group("fname") or m.group("pname") or m.group("jsname") or m.group("mname")
            if name:
                out.setdefault(name, line.strip())
    return out


def causal_watch(f: dict[str, Any]) -> list[dict[str, str]]:
    """In-diff lines that can break out-of-diff code. Watch items, not findings."""
    added = f.get("added_text")
    removed = f.get("removed_text")
    if added is None or removed is None:
        return []
    items: list[dict[str, str]] = []
    path = f["path"]

    old_sigs, new_sigs = _sig_names(removed), _sig_names(added)
    for name, old_line in old_sigs.items():
        new_line = new_sigs.get(name)
        if new_line is None:
            items.append({
                "kind": "SIGNATURE-REMOVED-OR-RENAMED",
                "symbol": name,
                "why": "callers outside the diff still reference the old name/arity",
                "find_callers": _callers_cmd(name, path),
            })
        elif re.sub(r"\s+", "", old_line) != re.sub(r"\s+", "", new_line):
            items.append({
                "kind": "SIGNATURE-CHANGED",
                "symbol": name,
                "why": "existing call sites outside the diff were written against the old parameters/return",
                "find_callers": _callers_cmd(name, path),
            })

    removed_only = [ln for ln in removed if ln.strip() and ln.strip() not in {a.strip() for a in added}]
    for ln in removed_only:
        if not EXPORT_RE.search(ln):
            continue
        m = SIG_RE.search(ln)
        sym = (m.group("name") or m.group("fname") or m.group("pname") or m.group("jsname") or m.group("mname")) if m else None
        if sym and sym in new_sigs:
            continue  # still exported, just reshaped — SIGNATURE-CHANGED already covers it
        items.append({
            "kind": "EXPORT-REMOVED",
            "symbol": sym or "(see removed lines)",
            "why": "importers outside the diff break at load time, not at review time",
            "find_callers": f"srcwalk deps {path}   # importers; sweep: rg -n -w '{sym or path.rsplit('/', 1)[-1].rsplit('.', 1)[0]}'",
        })
        break
    if any(GUARD_RE.search(ln) for ln in removed_only):
        items.append({
            "kind": "GUARD-REMOVED",
            "symbol": "(see removed lines)",
            "why": "a code path outside the diff may now be reachable, or reachable unvalidated — the bug will look pre-existing but this diff caused it",
            "find_callers": "trace who reaches this function; the newly reachable branch is in scope",
        })
    if any(DEFAULT_RE.search(ln) for ln in added) and any(DEFAULT_RE.search(ln) for ln in removed_only):
        items.append({
            "kind": "DEFAULT-CHANGED",
            "symbol": "(see changed assignment)",
            "why": "callers outside the diff that relied on the old default silently change behavior",
            "find_callers": "list every caller that omits this argument / config key",
        })
    # SQL DDL options (ALGORITHM=INSTANT) look like constants; enums live in code
    if not path.lower().endswith(".sql") and any(ENUM_RE.search(ln) for ln in added):
        items.append({
            "kind": "ENUM-VARIANT-ADDED",
            "symbol": "(see added constant/case)",
            "why": "switch/match statements outside the diff may fall through to a default branch — check the default is fail-closed",
            "find_callers": "find every switch/match on this type and check its default branch",
        })
    return items


def route(surface: dict[str, Any]) -> dict[str, Any]:
    files_out = []
    for f in surface["files"]:
        path = f["path"]
        kind = f["change_kind"]
        is_test = bool(TEST_RE.search(path))
        is_doc = bool(DOC_RE.search(path))
        machine_written = bool(f["generated"]) or kind == "binary"
        if machine_written or is_test:
            # A test sits on a risky path by name only; it carries no runtime risk itself
            pts, labels, skills = 0, [], []
        else:
            pts, labels, skills = path_risk(path)
        flags: list[str] = []

        if f["generated"]:
            depth, reason = "SKIP-LINES", f"generated ({f['generated_reason']}) — review the version bump, not the lines"
        elif kind == "binary":
            depth, reason = "SKIP-LINES", "binary — review why the asset changed, not its bytes"
        elif f["whitespace_or_move_only"]:
            depth, reason = "SCAN", "whitespace/move only — confirm nothing changed semantically, then move on"
        else:
            if f["added_count"] > 200 and not is_test:
                pts += 1
                flags.append("LARGE (>200 added lines — ask for a split before line-reviewing)")
            if f["removed_count"] > 20 and f["removed_count"] > 3 * max(f["added_count"], 1):
                pts += 2
                flags.append("DELETION-HEAVY (what used to call the deleted code?)")
            if is_test and f["removed_count"] > f["added_count"]:
                pts += 2
                flags.append("TEST-SHRANK (net test deletion — ask which case stopped being covered)")
            if is_doc:
                pts = max(pts - 1, 0)
            if pts >= 4:
                depth = "LINE-BY-LINE"
            elif pts >= 2:
                depth = "FOCUSED"
            else:
                depth = "SCAN"
            reason = ", ".join(labels) if labels else ("docs/prose" if is_doc else "no high-risk path signal")

        watch = causal_watch(f) if depth != "SKIP-LINES" and not is_test else []
        files_out.append({
            "path": path,
            "change_kind": kind,
            "added": f["added_count"],
            "removed": f["removed_count"],
            "risk_points": pts,
            "depth": depth,
            "reason": reason,
            "flags": flags,
            "sibling_skills": skills,
            "is_test": is_test,
            "causal_watch": watch,
        })

    order = {"LINE-BY-LINE": 0, "FOCUSED": 1, "SCAN": 2, "SKIP-LINES": 3}
    files_out.sort(key=lambda x: (order[x["depth"]], -x["risk_points"], x["path"]))

    code_files = [f for f in files_out if f["depth"] in ("LINE-BY-LINE", "FOCUSED") and not f["is_test"]]
    global_flags: list[str] = []
    if code_files and not any(f["is_test"] for f in files_out):
        global_flags.append(
            "NO-TEST-CHANGE — this PR changes reviewable logic and touches no test file. "
            "That is a PR-level finding (scope: pr-level), not a pre-existing one."
        )
    if any(f["causal_watch"] for f in files_out):
        global_flags.append(
            "CAUSAL-WATCH present — some diff lines can break code outside the diff. "
            "Findings there are diff-caused and must carry caused_by."
        )
    has_text = any("added_text" in f for f in surface["files"])
    if not has_text:
        global_flags.append(
            "Surface built without --keep-text, so causal watch was skipped. "
            "Rebuild with: diff_surface_builder.py ... --keep-text --output json"
        )

    all_skills: list[str] = []
    for f in files_out:
        for s in f["sibling_skills"]:
            if s not in all_skills:
                all_skills.append(s)

    return {
        "schema": "review_route.v1",
        "files": files_out,
        "global_flags": global_flags,
        "sibling_skills": all_skills,
        "attention": {
            "line_by_line": sum(1 for f in files_out if f["depth"] == "LINE-BY-LINE"),
            "focused": sum(1 for f in files_out if f["depth"] == "FOCUSED"),
            "scan": sum(1 for f in files_out if f["depth"] == "SCAN"),
            "skip_lines": sum(1 for f in files_out if f["depth"] == "SKIP-LINES"),
        },
    }


def render_text(r: dict[str, Any]) -> str:
    a = r["attention"]
    out = [
        "REVIEW ROUTE  (read in this order; everything below is inside the diff)",
        f"  line-by-line {a['line_by_line']}  focused {a['focused']}  scan {a['scan']}  skip-lines {a['skip_lines']}",
        "",
    ]
    for f in r["files"]:
        out.append(f"[{f['depth']}] {f['path']}  +{f['added']} -{f['removed']}  (risk {f['risk_points']})")
        out.append(f"    why: {f['reason']}")
        for fl in f["flags"]:
            out.append(f"    flag: {fl}")
        if f["sibling_skills"]:
            out.append(f"    pull in: {', '.join(f['sibling_skills'])}")
        for w in f["causal_watch"]:
            out.append(f"    watch {w['kind']} [{w['symbol']}] — {w['why']}")
            out.append(f"      find: {w['find_callers']}")
    if r["global_flags"]:
        out.append("")
        out.append("PR-LEVEL FLAGS")
        for fl in r["global_flags"]:
            out.append(f"  - {fl}")
    return "\n".join(out)


SAMPLE_SURFACE = {
    "schema": "review_surface.v1",
    "files": [
        {
            "path": "app/Services/EntitlementService.php",
            "old_path": "app/Services/EntitlementService.php",
            "change_kind": "modified",
            "added_lines": [42, 43, 44, 45, 46],
            "removed_lines": [42, 43],
            "context_lines": [40, 41, 42, 47, 48],
            "hunks": [{"id": "H1", "header": "-40,9 +40,12", "section": "class EntitlementService",
                       "old_start": 40, "old_end": 48, "new_start": 40, "new_end": 51, "added": 5, "removed": 2}],
            "generated": False, "generated_reason": "", "whitespace_or_move_only": False,
            "added_count": 5, "removed_count": 2,
            "added_text": [
                "    public function grant(string $userId, string $sku, ?string $txnId = null): void",
                "        if ($txnId !== null && $this->repo->seen($txnId)) {",
                "            return;",
                "        }",
                "        $this->repo->upsert($userId, $sku, $txnId);",
            ],
            "removed_text": [
                "    public function grant(string $userId, string $sku): void",
                "        $this->repo->upsert($userId, $sku);",
            ],
        },
        {
            "path": "package-lock.json", "old_path": "package-lock.json", "change_kind": "modified",
            "added_lines": [123], "removed_lines": [123], "context_lines": [], "hunks": [],
            "generated": True, "generated_reason": "lock/vendored file (package-lock.json)",
            "whitespace_or_move_only": False, "added_count": 1, "removed_count": 1,
            "added_text": ['    "lodash": "4.17.21",'], "removed_text": ['    "lodash": "4.17.20",'],
        },
    ],
    "totals": {},
}


def main() -> int:
    p = argparse.ArgumentParser(
        description="Allocate review depth inside a review surface and list causal watch items (in-diff lines that can break out-of-diff code).",
        epilog="Build the surface first: diff_surface_builder.py --git-range main...HEAD --keep-text --output json --out surface.json",
    )
    src = p.add_mutually_exclusive_group()
    src.add_argument("--surface", metavar="FILE", help="review surface JSON from diff_surface_builder.py")
    src.add_argument("--sample", action="store_true", help="run on a built-in sample surface")
    p.add_argument("--output", choices=["text", "json"], default="text", help="output format (default: text)")
    p.add_argument("--out", metavar="FILE", help="write output to FILE instead of stdout")
    args = p.parse_args()

    if args.sample:
        surface = SAMPLE_SURFACE
    elif args.surface:
        with open(args.surface, encoding="utf-8") as fh:
            surface = json.load(fh)
    elif not sys.stdin.isatty():
        surface = json.load(sys.stdin)
    else:
        sys.exit("no surface given: pass --surface FILE, --sample, or pipe surface JSON on stdin")

    if "files" not in surface:
        sys.exit("input is not a review surface (no 'files' key)")

    r = route(surface)
    rendered = json.dumps(r, indent=2) if args.output == "json" else render_text(r)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(rendered + "\n")
        print(f"wrote {args.out}")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
