#!/usr/bin/env python3
"""Rank skill search candidates with a simple, inspectable rubric."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Rank skill candidates.")
    p.add_argument("candidates_json", help="JSON from search_skills.py or a list of candidates")
    p.add_argument("--query", default="", help="Original user query")
    p.add_argument("--validation-dir", help="Directory containing <skill-name>.validation.json files")
    p.add_argument("--out", help="Write ranked JSON")
    return p.parse_args()


def terms(text: str) -> List[str]:
    return [t.lower() for t in re.findall(r"[a-zA-Z0-9_\-]+", text) if len(t) > 1]


def validation_score(name: str, validation_dir: str | None) -> tuple[int, list[str]]:
    if not validation_dir:
        return 10, ["not yet validated"]
    path = Path(validation_dir) / f"{name}.validation.json"
    if not path.exists():
        return 8, ["validation report missing"]
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("error_count", 0):
        return 0, [f"{data.get('error_count')} validation errors"]
    if data.get("warning_count", 0):
        return 14, [f"{data.get('warning_count')} validation warnings"]
    return 20, ["validation passed"]


# Tokens that suggest a skill is bound to a specific host platform, agent
# runtime, or proprietary toolchain. When a skill's compatibility/description
# only mentions these, portability is reduced; when no platform binding is
# declared, portability is treated as the default (highest).
PLATFORM_LOCK_TOKENS = (
    "claude code", "claude desktop", "anthropic console",
    "codex cli", "openai", "chatgpt",
    "copilot", "cursor",
    "windows only", "macos only", "linux only",
)
PORTABILITY_HINTS = ("platform-neutral", "cross-platform", "platform agnostic", "any agent")


def portability_score(candidate: Dict[str, Any]) -> tuple[int, str]:
    """Score portability based on the candidate's own declarations.

    Reads `compatibility` (preferred) and `description` from the candidate
    payload. Source-of-origin alone is never used as a portability signal —
    that conflates trust with portability and unfairly penalizes hosts.

    Special case: candidates discovered via awesome-list indexes never
    expose a `compatibility` field, because the search path scrapes README
    links and cannot read the target skill's frontmatter. For these we
    score "unknown — needs manual fetch" at 6 rather than the optimistic
    "no platform binding declared" 8 used for first-party sources where
    we did read the frontmatter and saw it was simply absent.
    """
    compat = str(candidate.get("compatibility", "")).lower()
    desc = str(candidate.get("description", "")).lower()
    blob = f"{compat} {desc}"
    source_kind = candidate.get("source_kind", "")

    if any(hint in blob for hint in PORTABILITY_HINTS):
        return 10, "portable: explicitly platform-neutral"
    locks = [tok for tok in PLATFORM_LOCK_TOKENS if tok in blob]
    if locks:
        return 6, f"platform binding declared: {', '.join(locks)}"
    if compat:
        # Has a compatibility note but no neutral/lock keywords — partial credit,
        # caller should read the note manually.
        return 8, "compatibility note present; review manually"
    if source_kind == "awesome-index":
        # We never had a chance to read frontmatter — score as unknown,
        # not optimistically "assumed portable".
        return 6, "compatibility unknown (awesome-index source; fetch SKILL.md to confirm)"
    return 8, "no platform binding declared (assumed portable)"


def score_candidate(c: Dict[str, Any], q_terms: List[str], validation_dir: str | None) -> Dict[str, Any]:
    name = str(c.get("name", ""))
    desc = str(c.get("description", ""))
    blob = f"{name} {desc} {c.get('path', '')}".lower()
    matched = [t for t in q_terms if t in blob]
    intent = int(35 * (len(matched) / max(len(q_terms), 1))) if q_terms else 20
    provenance = 15 if c.get("source_id") in {"anthropics-skills", "openai-skills", "github-awesome-copilot", "agentskills-reference"} else 9
    portability, portability_reason = portability_score(c)
    scope = 10 if 40 <= len(desc) <= 500 else 6
    maintenance = 8 if c.get("ref") and c.get("url") else 5
    val, val_reasons = validation_score(name, validation_dir)
    total = intent + provenance + val + portability + scope + maintenance
    c = dict(c)
    c["rubric_score"] = total
    c["rubric_reasons"] = [
        f"intent {intent}/35; matched {matched}",
        f"provenance {provenance}/15",
        f"validation {val}/20: {', '.join(val_reasons)}",
        f"portability {portability}/10: {portability_reason}",
        f"scope {scope}/10",
        f"maintenance/license signal {maintenance}/10"
    ]
    c["recommendation"] = "recommend" if total >= 80 else ("caveated" if total >= 65 else ("reference-only" if total >= 50 else "do-not-recommend"))
    return c


def main() -> int:
    args = parse_args()
    data = json.loads(Path(args.candidates_json).read_text(encoding="utf-8"))
    candidates = data.get("results", data if isinstance(data, list) else [])
    ranked = [score_candidate(c, terms(args.query or data.get("query", "")), args.validation_dir) for c in candidates]
    ranked.sort(key=lambda c: c.get("rubric_score", 0), reverse=True)
    payload = {"query": args.query or data.get("query", ""), "results": ranked}
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
