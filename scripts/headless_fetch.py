#!/usr/bin/env python3
"""Fetch a public web page for research with optional Playwright support.

If Playwright is installed, this can render JavaScript-heavy pages. Otherwise it
falls back to urllib and saves the raw HTML.

Network access is restricted by hostname allowlist:

* By default the allowlist is loaded from ``config/repositories.json`` plus a
  small set of host suffixes used by the bundled fetchers (github.com,
  raw.githubusercontent.com, api.github.com).
* Pass ``--allow-host`` (repeatable) to add more allowed hostnames or suffixes
  for a single invocation. Use ``--allow-any-host`` only when you have an
  explicit, audited reason — this disables the safety boundary.

The allowlist is enforced before any network call. A request to a non-allowed
host exits with status 2 and a clear error message.

This tool reads public documentation. Do not use it to bypass authentication
or access private resources.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# Hosts the rest of the meta-skill toolchain already talks to.
DEFAULT_ALLOWED_SUFFIXES = (
    "github.com",
    "raw.githubusercontent.com",
    "api.github.com",
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch a page with optional headless browser rendering.")
    p.add_argument("url")
    p.add_argument("--out", required=True)
    p.add_argument("--text", action="store_true", help="Save visible text instead of HTML when Playwright is available")
    p.add_argument("--timeout-ms", type=int, default=30000)
    p.add_argument(
        "--allow-host",
        action="append",
        default=[],
        metavar="HOST",
        help="Additional allowed hostname or suffix (repeatable). Matched as suffix, e.g. 'docs.example.com'.",
    )
    p.add_argument(
        "--repositories-config",
        default="",
        help="Path to repositories.json. Hosts derived from this file are added to the allowlist. Defaults to config/repositories.json relative to the script.",
    )
    p.add_argument(
        "--allow-any-host",
        action="store_true",
        help="Disable hostname allowlist. Use only with explicit user authorization.",
    )
    return p.parse_args()


def hosts_from_repositories_config(config_path: Path) -> list[str]:
    """Extract hostnames referenced in repositories.json call_methods URLs.

    The repositories registry only lists known-good public sources, so any
    hostname mentioned there is by definition acceptable for fetching.
    """
    if not config_path.exists():
        return []
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    hosts: set[str] = set()
    for source in data.get("sources", []):
        homepage = source.get("homepage", "")
        host = urllib.parse.urlparse(homepage).hostname
        if host:
            hosts.add(host)
        for value in (source.get("call_methods") or {}).values():
            # call_methods values may include shell command strings; pull
            # out anything that parses as a URL.
            for token in str(value).split():
                if token.startswith(("http://", "https://")):
                    h = urllib.parse.urlparse(token).hostname
                    if h:
                        hosts.add(h)
    return sorted(hosts)


def is_host_allowed(host: str, allowlist: list[str]) -> bool:
    host = host.lower()
    for allowed in allowlist:
        allowed = allowed.lower().strip()
        if not allowed:
            continue
        if host == allowed or host.endswith("." + allowed):
            return True
    return False


def fetch_urllib(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "meta-skill-headless-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_playwright(url: str, text_mode: bool, timeout_ms: int) -> str:
    from playwright.sync_api import sync_playwright  # type: ignore

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        content = page.locator("body").inner_text(timeout=timeout_ms) if text_mode else page.content()
        browser.close()
        return content


def main() -> int:
    args = parse_args()

    parsed = urllib.parse.urlparse(args.url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        print(f"Refusing to fetch unsupported URL: {args.url}", file=sys.stderr)
        return 2

    if not args.allow_any_host:
        config_path = Path(args.repositories_config) if args.repositories_config else (
            Path(__file__).resolve().parent.parent / "config" / "repositories.json"
        )
        allowlist = list(DEFAULT_ALLOWED_SUFFIXES) + hosts_from_repositories_config(config_path) + list(args.allow_host)
        if not is_host_allowed(parsed.hostname, allowlist):
            print(
                f"Refusing to fetch host {parsed.hostname!r}: not in allowlist.\n"
                f"Allowlist: {sorted(set(allowlist))}\n"
                "Pass --allow-host <host> to extend the allowlist for this run, "
                "or --allow-any-host only with explicit user authorization.",
                file=sys.stderr,
            )
            return 2

    try:
        content = fetch_playwright(args.url, args.text, args.timeout_ms)
        mode = "playwright"
    except Exception as exc:
        content = fetch_urllib(args.url)
        mode = f"urllib fallback after Playwright unavailable or failed: {exc}"
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    print(f"Saved {out} ({mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
