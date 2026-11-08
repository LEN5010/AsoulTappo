#!/usr/bin/env python3
"""Point a release's latest.json at github.com download links.

tauri-action writes each platform's `url` as the REST asset endpoint
(api.github.com/repos/<repo>/releases/assets/<id>). Without a token that endpoint allows
60 requests per hour per IP, which players behind a shared IP run out of, and some networks
reach github.com but not api.github.com. The release page's own download links
(github.com/<repo>/releases/download/<tag>/<name>) redirect to the same file, so the URLs
are rewritten to those and latest.json is uploaded again. The signatures cover the files,
not the URLs, and stay valid.

Usage:
    python scripts/fix_updater_urls.py v1.0.1 [--repo LEN5010/AsoulTappo] [--dry-run]

Needs the GitHub CLI, signed in or with GH_TOKEN set.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ASSET_ENDPOINT = re.compile(r"^https://api\.github\.com/repos/[^/]+/[^/]+/releases/assets/(\d+)$")


def gh(*args: str) -> str:
    done = subprocess.run(["gh", *args], capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit(f"gh {' '.join(args[:2])} failed: {done.stderr.strip()}")
    return done.stdout


def rewrite(manifest: dict, links: dict[str, str]) -> int:
    """Replace asset-endpoint URLs in place with the release's download links; returns how many changed."""
    changed = 0
    for name, platform in manifest.get("platforms", {}).items():
        found = ASSET_ENDPOINT.match(platform.get("url", ""))
        if not found:
            continue
        link = links.get(found.group(1))
        if link is None:
            raise SystemExit(f"{name}: asset {found.group(1)} is not in this release")
        platform["url"] = link
        changed += 1
    return changed


def main() -> None:
    ap = argparse.ArgumentParser(description="Point a release's latest.json at github.com download links.")
    ap.add_argument("tag", help="release tag, e.g. v1.0.1")
    ap.add_argument("--repo", default="LEN5010/AsoulTappo")
    ap.add_argument("--dry-run", action="store_true", help="print the rewritten latest.json instead of uploading it")
    args = ap.parse_args()

    release = json.loads(gh("api", f"repos/{args.repo}/releases/tags/{args.tag}"))
    links = {str(asset["id"]): asset["browser_download_url"] for asset in release["assets"]}
    with tempfile.TemporaryDirectory() as tmp:
        gh("release", "download", args.tag, "--repo", args.repo, "--pattern", "latest.json", "--dir", tmp)
        path = Path(tmp) / "latest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        changed = rewrite(manifest, links)
        text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        if args.dry_run:
            sys.stdout.write(text)
            return
        if not changed:
            print("latest.json already uses download links")
            return
        path.write_text(text, encoding="utf-8")
        gh("release", "upload", args.tag, str(path), "--repo", args.repo, "--clobber")
        print(f"latest.json: {changed} URL(s) now point at github.com")


if __name__ == "__main__":
    main()
