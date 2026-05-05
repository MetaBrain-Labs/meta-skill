#!/usr/bin/env python3
"""Validate an Agent Skill directory for format and obvious content risks.

This validator is intentionally conservative. It does not prove a skill is safe;
it finds issues that deserve review before installation or packaging.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
TEXT_EXTENSIONS = {
    ".md", ".txt", ".py", ".js", ".ts", ".tsx", ".jsx", ".sh", ".bash",
    ".zsh", ".ps1", ".json", ".yaml", ".yml", ".toml", ".xml", ".html", ".css"
}
SCRIPT_EXTENSIONS = {".py", ".js", ".ts", ".sh", ".bash", ".zsh", ".ps1", ".rb", ".pl"}

# Patterns are intentionally direct; the validator reports review findings rather than making final policy calls.
BLOCK_PATTERNS: List[Tuple[str, re.Pattern[str], str]] = [
    ("instruction_override", re.compile(r"\b(ignore|bypass|override|discard)\b.{0,80}\b(system|developer|higher[- ]priority|policy|previous instructions?)\b", re.I | re.S), "Attempts to bypass or override higher-priority instructions."),
    ("concealment", re.compile(r"\b(do not tell|hide this|silently|without (?:the )?user (?:knowing|noticing)|conceal)\b", re.I), "Asks the agent to hide behavior from the user."),
    ("credential_collection", re.compile(r"\b(steal|harvest|exfiltrate|leak|siphon|silently\s+(?:collect|read|gather|upload|send)|collect\s+(?:and\s+)?(?:send|upload|exfiltrate|leak|forward))\b.{0,80}\b(passwords?|api[\s_\-]?keys?|secret[\s_\-]?keys?|access[\s_\-]?tokens?|auth[\s_\-]?tokens?|bearer[\s_\-]?tokens?|credentials?|private[\s_\-]?keys?|ssh[\s_\-]?keys?|session[\s_\-]?cookies?|wallet|seed[\s_\-]?phrase|mnemonic)\b", re.I | re.S), "Requests collection or export of sensitive authentication material."),
    ("remote_shell_pipe", re.compile(r"\b(curl|wget)\b[^\n|;]{0,160}\|\s*(sh|bash|zsh|powershell|pwsh)\b", re.I), "Pipes remote network content directly into a shell."),
    ("broad_delete", re.compile(r"\brm\s+-rf\s+(/|~|\$HOME|\*)", re.I), "Broad destructive deletion command."),
    ("privilege_escalation", re.compile(r"\b(sudo\s+chmod\s+777|setenforce\s+0|disable[-_ ]?(?:firewall|defender|gatekeeper|security))\b", re.I), "Privilege or security-control bypass pattern."),
    # The next three patterns target social-engineering style prompt injection
    # — the kind that doesn't ask the agent to *do* something dangerous, but
    # instead tries to manipulate the *reviewing* agent's judgment. These
    # mirror the "instruction isolation" teaching in references/safety-policy.md
    # so that if the agent's first line of defense fails, validate_skill.py
    # provides a second.
    ("second_person_directive", re.compile(
        r"(?:^|[\n。.!?])\s*(?:你是|You are|You're)\s+(?:一个\s*)?(?:AI|Claude|the\s+agent|an?\s+(?:agent|assistant|reviewer))\b",
        re.I | re.M,
    ), "Skill content addresses the reviewing agent in second person — a common prompt-injection signature."),
    ("fake_authority_endorsement", re.compile(
        # English: "has been (audit|certif|review)ed by ...", "is (compliant|trusted|approved)"
        # Chinese: "已[经]?(过|经过)?[\\s\\S]{0,8}(审计|审查|认证|合规|背书|批准)"
        r"\b(?:has been|is)\s+(?:fully\s+)?(?:audited|certified|verified|approved|trusted|compliant|vetted)\b"
        r"|\b(?:soc\s*2|iso\s*27001|gdpr|hipaa)\s+(?:audited|certified|compliant|approved)\b"
        r"|已经?(?:过|经过)?[^\n。.]{0,12}(?:审计|审查|认证|合规|背书|批准|备案)",
        re.I,
    ), "Skill content claims external audits or certifications — third-party skills cannot self-attest trust."),
    ("skip_validation_request", re.compile(
        # English: "skip (the )?(validation|review|check|audit|warning)", "no need to (warn|validate|check)"
        # Chinese: "跳过|省略|不必|无需 ... 校验|审查|警告|确认|验证"
        r"\bskip\s+(?:the\s+)?(?:validation|review|check|audit|warning|safety\s+check)s?\b"
        r"|\bno\s+need\s+to\s+(?:warn|validate|check|review|audit)\b"
        r"|\bdo\s+not\s+(?:warn|validate|run\s+(?:the\s+)?(?:validator|checks?))\b"
        r"|(?:跳过|省略|不必|无需|不要)\s*[^\n。.]{0,8}(?:校验|审查|警告|确认|验证|审计)",
        re.I,
    ), "Skill content asks the reviewing agent to skip validation, review, or warnings."),
]

WARN_PATTERNS: List[Tuple[str, re.Pattern[str], str]] = [
    ("broad_tool_grant", re.compile(r"allowed-tools:\s*.*\b(Bash\([^)]*\*|Write|Edit|Delete|Network|WebFetch)\b", re.I), "Broad tool permission in frontmatter."),
    ("encoded_payload", re.compile(r"\b(base64\s+(-d|--decode)|FromBase64String|eval\s*\(|exec\s*\()", re.I), "Encoded payload or dynamic code execution pattern."),
    ("network_call", re.compile(r"\b(requests\.|urllib\.request|fetch\(|axios\.|curl\s+https?://|wget\s+https?://)"), "Script or instructions include network access; confirm purpose and endpoint."),
    ("chmod", re.compile(r"\bchmod\s+(777|\+x)\b", re.I), "Permission-changing command; confirm it is necessary and scoped."),
]

VAGUE_DESCRIPTIONS = ["helps with", "useful for", "does things", "various tasks", "assistant for", "general"]
SAFETY_DOC_HINTS = ("safety", "validation-rules", "policy", "security review", "validate_skill.py")


@dataclass
class Finding:
    level: str
    code: str
    message: str
    path: str | None = None
    line: int | None = None
    evidence: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate an Agent Skill directory.")
    parser.add_argument("skill_dir", help="Path to the skill directory")
    parser.add_argument("--json-out", help="Write full JSON report to this path")
    parser.add_argument("--fail-on-warning", action="store_true", help="Exit non-zero when warnings are present")
    return parser.parse_args()


def read_text(path: Path, max_bytes: int = 2_000_000) -> str:
    data = path.read_bytes()
    if len(data) > max_bytes:
        data = data[:max_bytes]
    return data.decode("utf-8", errors="replace")


def parse_frontmatter(text: str) -> Tuple[Dict[str, Any], str, str | None]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text, "SKILL.md must start with YAML frontmatter delimited by --- lines."
    raw = match.group(1)
    body = text[match.end():]
    try:
        import yaml  # type: ignore
        parsed = yaml.safe_load(raw) or {}
        if not isinstance(parsed, dict):
            return {}, body, "Frontmatter must parse as a mapping."
        return parsed, body, None
    except Exception:
        parsed: Dict[str, Any] = {}
        current_key: str | None = None
        for lineno, line in enumerate(raw.splitlines(), start=1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if line.startswith("  ") and current_key:
                # Best-effort nested metadata support; exact YAML validation requires PyYAML.
                continue
            if ":" not in line:
                return {}, body, f"Cannot parse frontmatter line {lineno!r}: {line}"
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            parsed[key] = value
            current_key = key
        return parsed, body, None


def line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def is_safety_context(text: str, match_start: int, in_safety_doc: bool = False) -> bool:
    """Heuristic: should this match be exempted as part of safety prose?

    The exemption is restricted to safety documentation files (matched against
    SAFETY_DOC_HINTS by the caller via the in_safety_doc flag). Inside those
    files we accept that attack examples are quoted on purpose to teach
    detection — for example references/safety-policy.md's "instruction
    isolation" section quotes prompt-injection samples verbatim.

    Outside safety docs we never exempt by keyword. A malicious skill can
    easily sprinkle "审查 / risk / validator / injection" into its own SKILL.md
    to game a keyword-only exemption — that is precisely the social-
    engineering vector the new BLOCK rules are meant to catch.
    """
    if not in_safety_doc:
        return False
    window_start = max(0, match_start - 220)
    window_end = min(len(text), match_start + 220)
    window = text[window_start:window_end].lower()
    safety_words = (
        # English
        "do not", "must not", "reject", "quarantine", "unsafe", "blocked",
        "blocking", "warning", "safety", "risk", "review", "pattern",
        "validator", "validation", "attack", "injection", "malicious",
        "fixture", "example",
        # Chinese
        "审查", "攻击", "拒绝", "隔离", "风险", "校验", "示例",
        "不可信", "恶意", "样本", "向量", "心理姿态", "引述",
    )
    return any(w in window for w in safety_words)


def add(f: List[Finding], level: str, code: str, message: str, path: str | None = None, line: int | None = None, evidence: str | None = None) -> None:
    if evidence:
        evidence = " ".join(evidence.strip().split())[:240]
    f.append(Finding(level=level, code=code, message=message, path=path, line=line, evidence=evidence))


def validate_format(skill_dir: Path, findings: List[Finding]) -> Tuple[Dict[str, Any], str]:
    if not skill_dir.exists() or not skill_dir.is_dir():
        add(findings, "error", "missing_directory", "Skill directory does not exist or is not a directory.", str(skill_dir))
        return {}, ""

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        add(findings, "error", "missing_skill_md", "Skill directory must contain SKILL.md.", str(skill_md))
        return {}, ""

    text = read_text(skill_md)
    frontmatter, body, error = parse_frontmatter(text)
    if error:
        add(findings, "error", "frontmatter", error, str(skill_md), 1)
        return frontmatter, body

    name = str(frontmatter.get("name", "")).strip()
    description = str(frontmatter.get("description", "")).strip()
    compatibility = frontmatter.get("compatibility")

    if not name:
        add(findings, "error", "missing_name", "Frontmatter must include a non-empty name.", str(skill_md), 1)
    else:
        if len(name) > 64:
            add(findings, "error", "name_too_long", "Name must be at most 64 characters.", str(skill_md), 1, name)
        if not NAME_RE.match(name):
            add(findings, "error", "invalid_name", "Name must use lowercase letters, numbers, and single hyphens; it cannot start/end with a hyphen.", str(skill_md), 1, name)
        if skill_dir.name != name:
            add(findings, "error", "name_directory_mismatch", "Frontmatter name must match parent directory name.", str(skill_md), 1, f"name={name}, dir={skill_dir.name}")

    if not description:
        add(findings, "error", "missing_description", "Frontmatter must include a non-empty description.", str(skill_md), 1)
    else:
        if len(description) > 1024:
            add(findings, "error", "description_too_long", "Description must be at most 1024 characters.", str(skill_md), 1)
        if len(description) < 60 or any(v in description.lower() for v in VAGUE_DESCRIPTIONS):
            add(findings, "warning", "weak_description", "Description appears short or vague; make it trigger-focused and specific.", str(skill_md), 1, description)

    if compatibility is not None and len(str(compatibility)) > 500:
        add(findings, "error", "compatibility_too_long", "Compatibility must be at most 500 characters.", str(skill_md), 1)

    line_count = text.count("\n") + 1
    word_count = len(re.findall(r"\S+", text))
    if line_count > 500:
        add(findings, "warning", "skill_md_long", "SKILL.md is longer than 500 lines; move detail to references/.", str(skill_md), None, str(line_count))
    if word_count > 5000:
        add(findings, "warning", "skill_md_context_heavy", "SKILL.md is above the recommended context budget; split optional detail into references/.", str(skill_md), None, str(word_count))

    evals_path = skill_dir / "evals" / "evals.json"
    if not evals_path.exists():
        add(findings, "warning", "missing_evals", "No evals/evals.json found. Add 2-3 realistic test prompts when practical.", str(skill_dir))
    else:
        # Detect unfilled scaffolding from create_skill.py --with-evals.
        # Markers: "PLEASE REPLACE" (English) or "请替换" (Chinese).
        try:
            evals_text = evals_path.read_text(encoding="utf-8")
            import json as _json
            evals_data = _json.loads(evals_text)
            unfilled = 0
            empty = 0
            for e in evals_data.get("evals", []):
                blob = f"{e.get('prompt','')} {e.get('expected_output','')}"
                if "PLEASE REPLACE" in blob or "请替换" in blob:
                    unfilled += 1
                elif not e.get("prompt", "").strip():
                    empty += 1
            if unfilled or empty:
                detail = []
                if unfilled:
                    detail.append(f"{unfilled} entries still contain PLEASE REPLACE / 请替换 markers")
                if empty:
                    detail.append(f"{empty} entries have empty prompts")
                add(findings, "warning", "evals_stub_unfilled",
                    "evals/evals.json contains scaffolding placeholders; replace before shipping.",
                    str(evals_path), None, "; ".join(detail))
        except Exception:
            # Don't surface JSON parse errors here; format validation handles those.
            pass

    if not frontmatter.get("license") and not any((skill_dir / name).exists() for name in ("LICENSE", "LICENSE.txt", "COPYING")):
        add(findings, "warning", "missing_license", "No license field or LICENSE file found.", str(skill_dir))

    return frontmatter, text


# Directories whose files should never be opened by the validator's content
# scan. tests/ and evals/fixtures/ contain deliberately crafted bad samples
# (e.g. the bad-skill fixture used to verify that the scanner detects
# instruction overrides). Treating them as part of the host skill would cause
# false positives and defeat the purpose of having them.
SCAN_SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", "tests"}
SCAN_SKIP_PREFIXES = ("evals/fixtures",)
# Specific files to exclude from content scanning. validate_skill.py itself
# necessarily contains the full literal text of every malicious pattern it
# scans for (in BLOCK_PATTERNS / WARN_PATTERNS), so scanning it produces
# guaranteed false positives. The is_safety_context heuristic catches most
# but not all of these — a file-level exemption is the only reliable fix.
SCAN_SKIP_FILES = {"scripts/validate_skill.py"}
# Directories that are not packaged or hashed because they are pure scaffolding
# (caches, virtualenvs) — fixtures ARE hashed so tampering is visible.
HASH_SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", "tests"}


def _is_scan_skipped(rel_parts: tuple[str, ...]) -> bool:
    if any(part in SCAN_SKIP_DIRS for part in rel_parts):
        return True
    rel = "/".join(rel_parts)
    if rel in SCAN_SKIP_FILES:
        return True
    return any(rel == prefix or rel.startswith(prefix + "/") for prefix in SCAN_SKIP_PREFIXES)


def iter_text_files(skill_dir: Path) -> Iterable[Path]:
    for path in skill_dir.rglob("*"):
        if not path.is_file():
            continue
        if _is_scan_skipped(path.relative_to(skill_dir).parts):
            continue
        if path.suffix.lower() in TEXT_EXTENSIONS or path.name == "SKILL.md":
            yield path


def validate_content(skill_dir: Path, findings: List[Finding]) -> None:
    for path in iter_text_files(skill_dir):
        rel = str(path.relative_to(skill_dir))
        try:
            text = read_text(path)
        except Exception as exc:
            add(findings, "warning", "read_error", f"Could not read text file: {exc}", rel)
            continue

        safety_doc = any(hint in rel.lower() for hint in SAFETY_DOC_HINTS)
        for code, pattern, message in BLOCK_PATTERNS:
            for match in pattern.finditer(text):
                if is_safety_context(text, match.start(), in_safety_doc=safety_doc):
                    continue
                add(findings, "error", code, message, rel, line_for_offset(text, match.start()), match.group(0))
        for code, pattern, message in WARN_PATTERNS:
            for match in pattern.finditer(text):
                if is_safety_context(text, match.start(), in_safety_doc=safety_doc):
                    continue
                add(findings, "warning", code, message, rel, line_for_offset(text, match.start()), match.group(0))

        if path.suffix.lower() in SCRIPT_EXTENSIONS and path.stat().st_size > 250_000:
            add(findings, "warning", "large_script", "Large executable script; inspect manually before use.", rel, None, str(path.stat().st_size))


def file_hashes(skill_dir: Path) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for path in sorted(p for p in skill_dir.rglob("*") if p.is_file()):
        if any(part in HASH_SKIP_DIRS for part in path.relative_to(skill_dir).parts):
            continue
        rel = str(path.relative_to(skill_dir))
        result[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def make_report(skill_dir: Path, findings: List[Finding], frontmatter: Dict[str, Any]) -> Dict[str, Any]:
    errors = [asdict(f) for f in findings if f.level == "error"]
    warnings = [asdict(f) for f in findings if f.level == "warning"]
    return {
        "skill_dir": str(skill_dir),
        "name": frontmatter.get("name"),
        "status": "failed" if errors else ("passed_with_warnings" if warnings else "passed"),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "file_hashes": file_hashes(skill_dir) if skill_dir.exists() and skill_dir.is_dir() else {},
    }


def main() -> int:
    args = parse_args()
    skill_dir = Path(args.skill_dir).resolve()
    findings: List[Finding] = []
    frontmatter, _ = validate_format(skill_dir, findings)
    if skill_dir.exists() and skill_dir.is_dir():
        validate_content(skill_dir, findings)
    report = make_report(skill_dir, findings, frontmatter)

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({k: report[k] for k in ("skill_dir", "name", "status", "error_count", "warning_count")}, indent=2, ensure_ascii=False))
    for f in findings:
        loc = f.path or ""
        if f.line:
            loc += f":{f.line}"
        print(f"[{f.level.upper()}] {f.code} {loc} - {f.message}")
        if f.evidence:
            print(f"  evidence: {f.evidence}")

    if report["error_count"]:
        return 2
    if args.fail_on_warning and report["warning_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
