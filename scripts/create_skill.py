#!/usr/bin/env python3
"""Create a scaffold for a platform-neutral Agent Skill."""
from __future__ import annotations

import argparse
import json
import re
import textwrap
from pathlib import Path
from typing import Any

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

_SKILL_MD_TEMPLATE = """---
name: {name}
description: {description}
license: {license}{frontmatter_extra}
---

# {title}

{goal}{body_sections}"""


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create an Agent Skill scaffold.")
    p.add_argument("--name", required=True, help="Skill name; lowercase letters, numbers, hyphens")
    p.add_argument("--description", required=True, help="Trigger-focused skill description")
    p.add_argument("--goal", required=True, help="What the skill enables the agent to do")
    p.add_argument("--title", default="", help="Optional H1 title for SKILL.md. Defaults to a Latin Title Case derived from --name (e.g. 'weekly-report' → 'Weekly Report'). For Chinese/Japanese/Korean skills, pass an explicit --title to avoid the awkward Latin fallback.")
    p.add_argument("--out", required=True, help="Output skill directory")
    p.add_argument("--license", default="MIT", help="License frontmatter value")
    p.add_argument("--compatibility", default="", help="Compatibility note for frontmatter (e.g. 'Requires Python 3.10+')")
    p.add_argument("--metadata", default="", help="Additional frontmatter fields as JSON string, e.g. '{\"version\":\"0.1.0\"}'")
    p.add_argument("--with-scripts", action="store_true", help="Create scripts/ directory and a placeholder utility")
    p.add_argument("--with-evals", action="store_true", help="Create evals/evals.json stub")
    p.add_argument("--force", action="store_true", help="Allow writing into an existing directory")
    p.add_argument("--config", default="", help="Path to JSON config file for detailed skill definition")
    p.add_argument("--workflow", default="", help="Optional: workflow steps, comma or newline separated")
    p.add_argument("--defaults", default="", help="Optional: default behaviors, comma or newline separated")
    p.add_argument("--validation", default="", help="Optional: validation rules, comma or newline separated")
    p.add_argument("--ref", action="append", default=[], dest="refs", metavar="FILE:DESCRIPTION",
                   help="Optional: create a reference file. Repeatable. Bare filenames are placed under references/ "
                        "(e.g. --ref 'api-errors.md:How to handle API errors' creates references/api-errors.md). "
                        "Pass an explicit path with '/' to opt out.")
    return p.parse_args()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_config(config_path: str) -> dict[str, Any]:
    if config_path:
        return json.loads(Path(config_path).read_text(encoding="utf-8"))
    return {}


def resolve_value(arg_value: str, config: dict[str, Any], key: str, default: Any = None) -> Any:
    if arg_value:
        return arg_value
    if key in config:
        return config[key]
    return default


def _detect_language(*texts: str) -> str:
    """Return 'zh' if any provided text contains CJK characters, else 'en'.

    The detection is deliberately CJK-vs-Latin only — we don't try to
    distinguish e.g. Japanese vs Chinese, because the punctuation choice
    is the same (full-width period) for both.
    """
    blob = " ".join(t for t in texts if t)
    for ch in blob:
        if "\u4e00" <= ch <= "\u9fff":
            return "zh"
    return "en"


def _terminal_period(lang: str) -> str:
    return "。" if lang == "zh" else "."


def _resolve_title(explicit_title: str, name: str, lang: str) -> str:
    """Return the H1 title for the generated SKILL.md.

    Priority:
    1. An explicit --title (or config["title"]) wins. This is the recommended
       path for non-Latin-script skills, because `name` is restricted to
       lowercase Latin + hyphens by the spec, which produces awkward H1 titles
       like "Weekly Report" inside an otherwise-Chinese SKILL.md.
    2. For English-language skills, fall back to the historical behavior:
       Title Case the name with hyphens replaced by spaces ("weekly-report"
       → "Weekly Report").
    3. For non-English skills with no --title, fall back to the raw name
       (e.g. "weekly-report"). It is a worse title than a hand-written one,
       but at least it does not mix scripts; the user is encouraged via
       --help to supply --title in this case.
    """
    if explicit_title:
        return explicit_title
    if lang == "en":
        return name.replace("-", " ").title()
    return name


def _ref_line_template(lang: str) -> str:
    """Return a format-string template for one reference bullet.

    The template uses {file} and {desc} placeholders. The connective ("when"
    in English; "时" / nothing in Chinese) is folded in here so that the
    output reads naturally in the chosen language rather than mixing scripts.
    """
    if lang == "zh":
        # Chinese: 描述形如"用户需要复用文档模板"或"处理 API 错误时"——
        # 直接拼"<描述>，读取 `<file>`"读起来最自然,避免在描述前再前置连词。
        return "- {desc}，读取 `{file}`{period}"
    return "- Read `{file}` when {desc}{period}"


def _strip_trailing_period(s: str) -> str:
    """Strip a trailing English or Chinese sentence-ending period."""
    return s.rstrip().rstrip(".。")


def _parse_list(value: Any) -> list[str]:
    """Split a CLI/config-supplied value into a clean list of items.

    Accepts either a JSON list or a delimited string. The string can use:
    * actual newlines (one item per line)
    * literal "\\n" sequences typed in shells where escapes are not interpreted
      (common when the user runs `--workflow "step1\\nstep2"` from bash)
    * commas
    * semicolons (Chinese ；is also accepted)
    """
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        # Promote literal "\n" / "\r\n" sequences to real newlines so that
        # `--workflow "a\nb"` from a shell produces two items, not one.
        normalized = value.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
        if "\n" in normalized:
            return [line.strip(" \t-*") for line in normalized.splitlines() if line.strip()]
        # Allow ; ；as alternative separators alongside ,
        for sep in (";", "；"):
            normalized = normalized.replace(sep, ",")
        return [item.strip() for item in normalized.split(",") if item.strip()]
    return []


def _build_frontmatter_extra(compatibility: str, metadata_str: str) -> str:
    parts: list[str] = []
    if compatibility:
        parts.append(f"\ncompatibility: {compatibility}")
    if metadata_str:
        try:
            meta = json.loads(metadata_str)
            for k, v in meta.items():
                parts.append(f"\n{k}: {json.dumps(v, ensure_ascii=False)}")
        except json.JSONDecodeError:
            parts.append(f"\nmetadata: {metadata_str}")
    return "".join(parts)


def _parse_refs(raw_refs: list[str]) -> list[dict[str, str]]:
    """Parse --ref entries.

    Each entry is "FILE:DESCRIPTION". The FILE is normalized to live under
    references/ so that the directory layout matches SKILL.md's documented
    convention. If the user explicitly types a different prefix (e.g.
    "scripts/foo.py:..."), respect it. If they pass just a filename
    ("api-errors.md:..."), treat it as references/api-errors.md.
    """
    result: list[dict[str, str]] = []
    for raw in raw_refs:
        if ":" not in raw:
            continue
        filename, desc = raw.split(":", 1)
        filename = filename.strip()
        if filename and "/" not in filename:
            filename = f"references/{filename}"
        result.append({"file": filename, "description": desc.strip()})
    return result


def main() -> int:
    args = parse_args()
    name = args.name.strip()
    if not NAME_RE.match(name):
        raise SystemExit("Invalid --name. Use lowercase letters, numbers, and single hyphens only.")
    if len(args.description) > 1024:
        raise SystemExit("--description must be <= 1024 characters.")

    out = Path(args.out).expanduser().resolve()
    # The skill directory must be named after the skill itself so that
    # validate_skill.py's name_directory_mismatch check passes. If the user
    # passed --out pointing at a parent directory, append the skill name.
    if out.name != name:
        out = out / name
    if out.exists() and any(out.iterdir()) and not args.force:
        raise SystemExit(f"Output directory is not empty: {out}. Use --force to write anyway.")
    out.mkdir(parents=True, exist_ok=True)

    config = load_config(args.config)

    raw_goal = resolve_value(args.goal, config, "goal", args.goal)
    lang = _detect_language(args.description, raw_goal)
    period = _terminal_period(lang)
    goal = _strip_trailing_period(raw_goal)
    explicit_title = resolve_value(args.title, config, "title", "").strip()
    title = _resolve_title(explicit_title, name, lang)

    # --- build body sections only when explicitly provided ---
    workflow_items = _parse_list(resolve_value(args.workflow, config, "workflow", None))
    defaults_items = _parse_list(resolve_value(args.defaults, config, "defaults", None))
    validation_items = _parse_list(resolve_value(args.validation, config, "validation", None))

    refs_from_args = _parse_refs(args.refs)
    refs_from_config: list[dict[str, str]] = []
    if config.get("references"):
        refs_config = config["references"]
        if isinstance(refs_config, list):
            for r in refs_config:
                if isinstance(r, dict):
                    refs_from_config.append({"file": r.get("file", ""), "description": r.get("description", "")})
                elif isinstance(r, str) and ":" in r:
                    filename, desc = r.split(":", 1)
                    refs_from_config.append({"file": filename.strip(), "description": desc.strip()})
    all_refs = refs_from_args + refs_from_config

    sections: list[str] = []
    if workflow_items:
        wf_heading = "## 工作流" if lang == "zh" else "## Workflow"
        parts = [wf_heading, ""]
        for i, step in enumerate(workflow_items, 1):
            parts.append(f"{i}. {step}")
        sections.append("\n".join(parts))
    if defaults_items:
        df_heading = "## 默认值" if lang == "zh" else "## Defaults"
        parts = [df_heading, ""]
        for item in defaults_items:
            parts.append(f"- {item}")
        sections.append("\n".join(parts))
    if all_refs:
        ref_heading = "## 参考文档" if lang == "zh" else "## References"
        parts = [ref_heading, ""]
        ref_template = _ref_line_template(lang)
        for ref in all_refs:
            desc = _strip_trailing_period(ref["description"])
            parts.append(ref_template.format(file=ref["file"], desc=desc, period=period))
        sections.append("\n".join(parts))
    if validation_items:
        if lang == "zh":
            parts = ["## 校验", "", "在最终输出前，确认：", ""]
        else:
            parts = ["## Validation", "", "Before final output, check:", ""]
        for item in validation_items:
            parts.append(f"- {item}")
        sections.append("\n".join(parts))
    body = ("\n\n" + "\n\n".join(sections)) if sections else ""

    # --- frontmatter extras ---
    compatibility_val = resolve_value(args.compatibility, config, "compatibility", "")
    metadata_val = resolve_value(args.metadata, config, "metadata", "")
    frontmatter_extra = _build_frontmatter_extra(
        compatibility_val,
        metadata_val if isinstance(metadata_val, str) else json.dumps(metadata_val, ensure_ascii=False)
    )

    skill_md = _SKILL_MD_TEMPLATE.format(
        name=name,
        description=args.description,
        license=args.license,
        frontmatter_extra=frontmatter_extra,
        title=title,
        goal=f"{goal}{period}",
        body_sections=body,
    )
    skill_md = skill_md.rstrip() + "\n"

    write(out / "SKILL.md", skill_md)

    # --- references: only create when explicitly requested ---
    for ref in all_refs:
        ref_file = ref["file"]
        ref_path = out / ref_file
        if not ref_path.suffix:
            ref_path = ref_path.with_suffix(".md")
        ref_desc = ref.get("description", "TBD")
        write(ref_path, f"# {ref_path.stem.replace('-', ' ').title()}\n\n{ref_desc}.\n")

    write(out / "README.md", f"# {name}\n\nGenerated Agent Skill scaffold.\n")
    write(out / "LICENSE", "MIT License\n")

    if args.with_scripts:
        if lang == "zh":
            scripts_readme = (
                "# 脚本\n\n"
                "在此目录放置确定性的辅助脚本——例如校验、解析、转换、报告生成、代码检查等。\n"
                "判断标准:同一动作在多次运行中都会重复时,封装为脚本比每次让模型重新生成代码更稳定。\n\n"
                "脚本应自包含、提供清晰的错误信息,并避免隐式的网络调用。\n"
            )
        else:
            scripts_readme = (
                "# Scripts\n\n"
                "Put deterministic helper scripts here — validation, parsing, conversion, "
                "report generation, linting, and so on.\n"
                "Rule of thumb: when the same action repeats across runs, wrapping it as a "
                "script is more reliable than asking the model to regenerate code each time.\n\n"
                "Scripts should be self-contained, give clear error messages, and avoid "
                "implicit network calls.\n"
            )
        write(out / "scripts" / "README.md", scripts_readme)
        write(out / "scripts" / "validate_output.py", textwrap.dedent("""\
            #!/usr/bin/env python3
            import sys
            from pathlib import Path

            def main() -> int:
                if len(sys.argv) != 2:
                    print('Usage: validate_output.py <path>')
                    return 2
                path = Path(sys.argv[1])
                if not path.exists():
                    print(f'Missing path: {path}')
                    return 1
                print(f'OK: {path}')
                return 0

            if __name__ == '__main__':
                raise SystemExit(main())
        """))

    if args.with_evals:
        evals_config = config.get("evals", [])
        if evals_config and isinstance(evals_config, list):
            evals_list: list[dict[str, Any]] = []
            for i, e in enumerate(evals_config):
                evals_list.append({
                    "id": i + 1,
                    "prompt": e.get("prompt", ""),
                    "expected_output": e.get("expected_output", ""),
                    "files": e.get("files", [])
                })
        else:
            # No config provided — emit a single seed eval derived from the
            # description and goal, plus an explicit TODO marker so the user
            # knows this is scaffolding to be replaced rather than ground truth.
            # Two more empty stubs are added because SKILL.md asks for 2-3
            # realistic prompts; emitting just one would tempt users to ship
            # an under-tested skill.
            todo_marker = "请替换" if lang == "zh" else "PLEASE REPLACE"
            seed_prompt = (
                "（{m}）一段贴近真实用户表达的自然语言提示。例如能让 skill 触发的具体场景描述,"
                "包含用户口语化的细节,而不是规整术语。当前 description: {d}".format(
                    m=todo_marker, d=args.description[:80]
                )
                if lang == "zh" else
                "({m}) A natural-language user prompt that should trigger this skill, "
                "phrased the way a real user would (with hesitations and concrete details, "
                "not a clean technical statement). Current description: {d}".format(
                    m=todo_marker, d=args.description[:80]
                )
            )
            seed_expected = (
                "（{m}）skill 应当采取的关键步骤,以及最终交付物的形态。"
                "Goal: {g}".format(m=todo_marker, g=goal)
                if lang == "zh" else
                "({m}) The key steps the skill should take and the shape of the "
                "final deliverable. Goal: {g}".format(m=todo_marker, g=goal)
            )
            evals_list = [
                {"id": 1, "prompt": seed_prompt, "expected_output": seed_expected, "files": []},
                {"id": 2, "prompt": f"({todo_marker}) ", "expected_output": f"({todo_marker}) ", "files": []},
                {"id": 3, "prompt": f"({todo_marker}) ", "expected_output": f"({todo_marker}) ", "files": []},
            ]
        evals = {
            "skill_name": name,
            "_note": (
                "Replace each ({m}) marker with a realistic prompt before shipping. "
                "Aim for 2-3 prompts that span the skill's main triggers. "
                "Empty or marker-only entries are flagged by validate_skill.py."
            ).format(m="请替换" if lang == "zh" else "PLEASE REPLACE"),
            "evals": evals_list
        }
        write(out / "evals" / "evals.json", json.dumps(evals, indent=2, ensure_ascii=False) + "\n")

    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
