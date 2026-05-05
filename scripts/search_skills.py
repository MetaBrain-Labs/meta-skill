#!/usr/bin/env python3
"""Search configured public skill repositories.

This script uses only the Python standard library. It can search GitHub repo trees
for SKILL.md files and simple awesome-list README links. It never executes third-
party code.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Search public Agent Skill repositories.")
    p.add_argument("query", help="Search query")
    p.add_argument("--config", default="config/repositories.json", help="Repository registry JSON")
    p.add_argument("--limit", type=int, default=10, help="Maximum candidates to print")
    p.add_argument("--out", help="Write JSON results")
    p.add_argument("--source", action="append", help="Restrict to source id; can be repeated")
    p.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"), help="GitHub token for higher rate limits")
    p.add_argument(
        "--include-spec",
        action="store_true",
        help="Include sources marked purpose=specification (spec/reference repos). "
             "By default these are skipped because they do not host installable skills.",
    )
    return p.parse_args()


# Keywords that signal the user is actually looking for the spec/reference,
# not for an installable skill. When present in the query, specification
# sources are auto-included even without --include-spec.
SPEC_INTENT_KEYWORDS = (
    "spec", "specification", "reference", "标准", "规范", "参考实现", "schema",
)


def query_implies_spec(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in SPEC_INTENT_KEYWORDS)


def http_get(url: str, token: str | None = None) -> bytes:
    headers = {"User-Agent": "meta-skill-search/1.0", "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def load_json_url(url: str, token: str | None = None) -> Any:
    return json.loads(http_get(url, token).decode("utf-8"))


def parse_frontmatter(text: str) -> Dict[str, str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    raw = m.group(1)
    fm: Dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or line.startswith(" "):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm


def terms(query: str) -> List[str]:
    return [t.lower() for t in re.findall(r"[a-zA-Z0-9_\-]+", query) if len(t) > 1]


def score_text(query_terms: List[str], *texts: str) -> Tuple[float, List[str]]:
    blob = "\n".join(texts).lower()
    if not query_terms:
        return 0.0, []
    hits = [t for t in query_terms if t in blob]
    score = len(hits) / len(query_terms)
    exact_bonus = 0.25 if " ".join(query_terms) in blob else 0.0
    return min(1.0, score + exact_bonus), [f"matched: {', '.join(hits)}"] if hits else []


def raw_url(owner: str, repo: str, ref: str, path: str) -> str:
    quoted = "/".join(urllib.parse.quote(part) for part in path.split("/"))
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{quoted}"


def tree_url(owner: str, repo: str, ref: str) -> str:
    return f"https://api.github.com/repos/{owner}/{repo}/git/trees/{urllib.parse.quote(ref)}?recursive=1"


def search_github_repo(source: Dict[str, Any], q_terms: List[str], token: str | None) -> List[Dict[str, Any]]:
    owner, repo, ref = source["owner"], source["repo"], source.get("ref", "main")
    roots = source.get("skill_roots", [])
    data = load_json_url(tree_url(owner, repo, ref), token)
    paths = [item["path"] for item in data.get("tree", []) if item.get("type") == "blob" and item.get("path", "").endswith("/SKILL.md")]
    if roots:
        paths = [p for p in paths if any(p.startswith(root.rstrip("/") + "/") or p == root.rstrip("/") + "/SKILL.md" for root in roots)]
    results = []
    for skill_md_path in paths[: source.get("default_limit_per_source", 200)]:
        skill_path = skill_md_path.rsplit("/", 1)[0]
        try:
            text = http_get(raw_url(owner, repo, ref, skill_md_path), token).decode("utf-8", errors="replace")
        except Exception as exc:
            continue
        fm = parse_frontmatter(text)
        name = fm.get("name") or skill_path.rstrip("/").split("/")[-1]
        description = fm.get("description", "")
        compatibility = fm.get("compatibility", "")
        s, reasons = score_text(q_terms, name, description, skill_path)
        if s <= 0 and q_terms:
            continue
        priority = float(source.get("priority", 0)) / 10.0
        results.append({
            "name": name,
            "description": description,
            "compatibility": compatibility,
            "source_id": source["id"],
            "source_name": source.get("name"),
            "source_kind": "github-repo",
            "repo": f"{owner}/{repo}",
            "ref": ref,
            "path": skill_path,
            "url": f"https://github.com/{owner}/{repo}/tree/{ref}/{skill_path}",
            "raw_skill_url": raw_url(owner, repo, ref, skill_md_path),
            "score": round((s * 0.8) + (priority * 0.2), 4),
            "reasons": reasons + [f"source priority {source.get('priority', 0)}"],
            "call_methods": source.get("call_methods", {})
        })
    return results


def search_awesome_index(source: Dict[str, Any], q_terms: List[str], token: str | None) -> List[Dict[str, Any]]:
    owner, repo, ref = source["owner"], source["repo"], source.get("ref", "main")
    results: List[Dict[str, Any]] = []
    for index_path in source.get("index_paths", ["README.md"]):
        try:
            text = http_get(raw_url(owner, repo, ref, index_path), token).decode("utf-8", errors="replace")
        except Exception:
            continue
        for title, url in LINK_RE.findall(text):
            if not ("skill" in title.lower() or "skills" in url.lower() or "officialskills" in url.lower() or "github.com" in url.lower()):
                continue
            s, reasons = score_text(q_terms, title, url)
            if s <= 0 and q_terms:
                continue
            priority = float(source.get("priority", 0)) / 10.0
            results.append({
                "name": re.sub(r"[^a-zA-Z0-9_.-]+", "-", title).strip("-")[:80] or title,
                "description": title,
                "source_id": source["id"],
                "source_name": source.get("name"),
                "source_kind": "awesome-index",
                "repo": f"{owner}/{repo}",
                "ref": ref,
                "path": index_path,
                "url": url,
                "score": round((s * 0.75) + (priority * 0.25), 4),
                "reasons": reasons + ["awesome-list link; fetch original source before recommending"],
                "call_methods": source.get("call_methods", {})
            })
    return results


def diagnose(errors: List[Dict[str, str]], have_token: bool) -> str | None:
    """Return a human-actionable diagnosis when search yields no results.

    Returns None when no specific guidance is warranted.
    """
    if not errors:
        return None
    rate_codes = ("403", "429", "Forbidden", "rate limit")
    rate_limited = sum(1 for e in errors if any(code in str(e.get("error", "")) for code in rate_codes))
    if rate_limited >= max(1, len(errors) // 2):
        if not have_token:
            return (
                "All or most sources returned rate-limit / forbidden errors. "
                "GitHub's unauthenticated API quota is very low (about 60/hour per IP). "
                "Set GITHUB_TOKEN in the environment, or pass --token <pat>, then retry. "
                "If you have no network access at all, ask the user for a local repository "
                "copy, a tarball, or specific candidate URLs and skip this script."
            )
        return (
            "All or most sources returned rate-limit / forbidden errors even with a token. "
            "Wait a few minutes and retry, or restrict --source to one repository at a time."
        )
    network_errs = sum(1 for e in errors if "URLError" in str(e.get("error", "")) or "Name or service" in str(e.get("error", "")))
    if network_errs >= max(1, len(errors) // 2):
        return (
            "Most sources failed with network errors. The host appears to be offline. "
            "Ask the user for a local repository copy, a tarball, or specific candidate URLs."
        )
    return None


def main() -> int:
    args = parse_args()
    config_path = Path(args.config)
    if not config_path.exists():
        # Allow running from scripts/ directory.
        alt = Path(__file__).resolve().parents[1] / args.config
        config_path = alt if alt.exists() else config_path
    config = json.loads(config_path.read_text(encoding="utf-8"))
    wanted = set(args.source or [])
    q_terms = terms(args.query)
    include_spec = args.include_spec or query_implies_spec(args.query)
    skipped_spec_sources: List[str] = []
    all_results: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []
    for source in config.get("sources", []):
        if wanted and source.get("id") not in wanted:
            continue
        # Skip specification/reference repos unless the user explicitly wants them
        # or restricted the search to this source via --source.
        if (
            source.get("purpose") == "specification"
            and not include_spec
            and source.get("id") not in wanted
        ):
            skipped_spec_sources.append(source.get("id", ""))
            continue
        try:
            if source.get("kind") == "github-repo":
                all_results.extend(search_github_repo(source, q_terms, args.token))
            elif source.get("kind") == "awesome-index":
                all_results.extend(search_awesome_index(source, q_terms, args.token))
        except urllib.error.HTTPError as exc:
            errors.append({"source_id": source.get("id", ""), "error": f"HTTP {exc.code}: {exc.reason}"})
        except Exception as exc:
            errors.append({"source_id": source.get("id", ""), "error": str(exc)})

    all_results.sort(key=lambda r: r.get("score", 0), reverse=True)
    payload: Dict[str, Any] = {"query": args.query, "results": all_results[: args.limit], "errors": errors}
    if skipped_spec_sources:
        payload["skipped_spec_sources"] = skipped_spec_sources

    diagnosis = diagnose(errors, have_token=bool(args.token))
    if diagnosis and not all_results:
        payload["diagnosis"] = diagnosis
        # Surface the diagnosis on stderr so it is hard to miss in interactive use.
        print(f"\n[search_skills] {diagnosis}\n", file=sys.stderr)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if all_results or not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
