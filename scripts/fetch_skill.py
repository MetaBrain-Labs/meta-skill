#!/usr/bin/env python3
"""Fetch a public GitHub skill directory or raw SKILL.md into a local workspace.

This script fetches text files and does not execute downloaded code.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

TREE_URL_RE = re.compile(r"https://github\.com/([^/]+)/([^/]+)/tree/([^/]+)/(.+)")
RAW_URL_RE = re.compile(r"https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)")
FRONTMATTER_NAME_RE = re.compile(r"\A---\s*\n.*?^name:\s*['\"]?([a-z0-9-]+)['\"]?\s*$", re.S | re.M)
TEXT_SUFFIXES = {".md", ".txt", ".py", ".js", ".ts", ".sh", ".bash", ".zsh", ".ps1", ".json", ".yaml", ".yml", ".toml", ".html", ".css"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch a GitHub skill into a local workspace.")
    p.add_argument("--url", required=True, help="GitHub tree URL or raw SKILL.md URL")
    p.add_argument("--out", required=True, help="Output workspace directory")
    p.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    p.add_argument("--max-files", type=int, default=200)
    return p.parse_args()


def http_get(url: str, token: str | None = None) -> bytes:
    headers = {"User-Agent": "meta-skill-fetch/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def raw_url(owner: str, repo: str, ref: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/" + "/".join(urllib.parse.quote(p) for p in path.split("/"))


def tree_api(owner: str, repo: str, ref: str) -> str:
    return f"https://api.github.com/repos/{owner}/{repo}/git/trees/{urllib.parse.quote(ref)}?recursive=1"


def skill_name_from_text(text: str, fallback: str) -> str:
    m = FRONTMATTER_NAME_RE.search(text)
    return m.group(1) if m else fallback


def parse_url(url: str) -> Tuple[str, str, str, str, bool]:
    m = TREE_URL_RE.match(url)
    if m:
        return m.group(1), m.group(2), m.group(3), m.group(4).rstrip("/"), False
    m = RAW_URL_RE.match(url)
    if m:
        path = m.group(4)
        if path.endswith("/SKILL.md"):
            path = path.rsplit("/", 1)[0]
        return m.group(1), m.group(2), m.group(3), path.rstrip("/"), True
    raise SystemExit("Only github.com tree URLs and raw.githubusercontent.com SKILL.md URLs are supported.")


def main() -> int:
    args = parse_args()
    owner, repo, ref, skill_path, raw_input = parse_url(args.url)
    skill_md = http_get(raw_url(owner, repo, ref, f"{skill_path}/SKILL.md"), args.token).decode("utf-8", errors="replace")
    name = skill_name_from_text(skill_md, skill_path.split("/")[-1])
    out_root = Path(args.out).expanduser().resolve()
    dest = out_root / name
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "SKILL.md").write_text(skill_md, encoding="utf-8")

    fetched = ["SKILL.md"]
    tree = json.loads(http_get(tree_api(owner, repo, ref), args.token).decode("utf-8"))
    prefix = skill_path.rstrip("/") + "/"
    for item in tree.get("tree", []):
        path = item.get("path", "")
        if item.get("type") != "blob" or not path.startswith(prefix) or path == prefix + "SKILL.md":
            continue
        rel = path[len(prefix):]
        if len(fetched) >= args.max_files:
            break
        suffix = Path(rel).suffix.lower()
        if suffix not in TEXT_SUFFIXES and Path(rel).name not in {"LICENSE", "LICENSE.txt", "README"}:
            continue
        data = http_get(raw_url(owner, repo, ref, path), args.token)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        fetched.append(rel)

    provenance = {
        "source_url": args.url,
        "owner": owner,
        "repo": repo,
        "ref": ref,
        "path": skill_path,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(fetched),
        "files": fetched,
        "note": "Fetched for inspection only. Scripts were not executed."
    }
    (out_root / f"{name}.provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
