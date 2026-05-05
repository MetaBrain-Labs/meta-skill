#!/usr/bin/env python3
"""Small file helper for agents that need deterministic file operations."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    p = argparse.ArgumentParser(description="File operations for skill workflows.")
    sub = p.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("write")
    w.add_argument("path")
    w.add_argument("--text", required=True)

    a = sub.add_parser("append")
    a.add_argument("path")
    a.add_argument("--text", required=True)

    c = sub.add_parser("copy")
    c.add_argument("src")
    c.add_argument("dst")

    h = sub.add_parser("hash")
    h.add_argument("path")

    m = sub.add_parser("mkdir")
    m.add_argument("path")

    args = p.parse_args()
    if args.cmd == "write":
        path = Path(args.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args.text, encoding="utf-8")
        print(json.dumps({"path": str(path), "bytes": path.stat().st_size}))
    elif args.cmd == "append":
        path = Path(args.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(args.text)
        print(json.dumps({"path": str(path), "bytes": path.stat().st_size}))
    elif args.cmd == "copy":
        src, dst = Path(args.src), Path(args.dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(json.dumps({"src": str(src), "dst": str(dst), "sha256": sha256(dst)}))
    elif args.cmd == "hash":
        path = Path(args.path)
        print(json.dumps({"path": str(path), "sha256": sha256(path)}))
    elif args.cmd == "mkdir":
        path = Path(args.path)
        path.mkdir(parents=True, exist_ok=True)
        print(json.dumps({"path": str(path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
