#!/usr/bin/env python3
"""Validate and package an Agent Skill as a .skill archive."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict


# Directories that should never be included in a packaged .skill archive
# or its file-hash manifest. Keep this in sync with validate_skill.py's
# iter_text_files exclusion set.
EXCLUDE_DIRS = {".git", "__pycache__", ".venv", "node_modules", "tests"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Package a skill directory into a .skill archive.")
    p.add_argument("skill_dir", help="Skill directory")
    p.add_argument("--out", default="dist", help="Output directory")
    p.add_argument("--allow-warnings", action="store_true", help="Package even if validation warnings exist")
    p.add_argument("--skip-validation", action="store_true", help="Do not run bundled validator")
    return p.parse_args()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_hashes(skill_dir: Path) -> Dict[str, str]:
    hashes = {}
    for path in sorted(p for p in skill_dir.rglob("*") if p.is_file()):
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        hashes[str(path.relative_to(skill_dir))] = sha256(path)
    return hashes


def run_validation(skill_dir: Path, report_path: Path) -> Dict:
    validator = Path(__file__).resolve().parent / "validate_skill.py"
    result = subprocess.run([sys.executable, "-S", str(validator), str(skill_dir), "--json-out", str(report_path)], text=True, capture_output=True)
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
    else:
        report = {"status": "failed", "error_count": 1, "warning_count": 0, "errors": [{"message": result.stderr or result.stdout}]}
    return report


def main() -> int:
    args = parse_args()
    skill_dir = Path(args.skill_dir).expanduser().resolve()
    if not skill_dir.is_dir():
        raise SystemExit(f"Not a directory: {skill_dir}")
    name = skill_dir.name
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    validation_path = out_dir / f"{name}.validation.json"

    validation = {"status": "skipped", "error_count": 0, "warning_count": 0}
    if not args.skip_validation:
        validation = run_validation(skill_dir, validation_path)
        if validation.get("error_count", 0):
            raise SystemExit(f"Validation failed. See {validation_path}")
        if validation.get("warning_count", 0) and not args.allow_warnings:
            raise SystemExit(f"Validation has warnings. Re-run with --allow-warnings or fix them. See {validation_path}")

    archive = out_dir / f"{name}.skill"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(p for p in skill_dir.rglob("*") if p.is_file()):
            if any(part in EXCLUDE_DIRS for part in path.parts):
                continue
            zf.write(path, arcname=f"{name}/{path.relative_to(skill_dir)}")

    manifest = {
        "name": name,
        "packaged_at": datetime.now(timezone.utc).isoformat(),
        "archive": archive.name,
        "archive_sha256": sha256(archive),
        "validation_status": validation.get("status"),
        "validation_error_count": validation.get("error_count", 0),
        "validation_warning_count": validation.get("warning_count", 0),
        "files": collect_hashes(skill_dir),
    }
    manifest_path = out_dir / f"{name}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"archive": str(archive), "manifest": str(manifest_path), "validation": validation.get("status")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
