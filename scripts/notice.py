#!/usr/bin/env python3
"""Minimum client version and announcements of a room server (GET/PUT /admin/notice).

Usage:
    notice.py show
    notice.py min 1.1.3            clients below 1.1.3 must update; "" lifts the minimum
    notice.py announce <id> <title> [body] [--days N]
    notice.py remove <id>

Environment:
    ASOULTAPPO_URL          server address, default http://127.0.0.1:8000
    ASOULTAPPO_ADMIN_KEY    the server's admin key

A minimum also turns away every client before 1.1.3: those send no version and only show an error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def call(method: str, body: dict | None = None) -> dict:
    url = os.environ.get("ASOULTAPPO_URL", "http://127.0.0.1:8000").rstrip("/") + "/admin/notice"
    key = os.environ.get("ASOULTAPPO_ADMIN_KEY", "")
    if not key:
        sys.exit("ASOULTAPPO_ADMIN_KEY is not set")
    req = urllib.request.Request(
        url, method=method, data=json.dumps(body).encode() if body is not None else None,
        headers={"X-Admin-Key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"{e.code}: {e.read().decode(errors='replace')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    sub.add_parser("min").add_argument("version")
    announce = sub.add_parser("announce")
    announce.add_argument("id")
    announce.add_argument("title")
    announce.add_argument("body", nargs="?", default="")
    announce.add_argument("--days", type=float, default=0, help="stop showing it after this many days")
    sub.add_parser("remove").add_argument("id")
    args = parser.parse_args()

    notice = call("GET")
    if args.cmd == "min":
        notice["minVersion"] = args.version
    elif args.cmd == "announce":
        item = {"id": args.id, "title": args.title, "body": args.body,
                "until": time.time() + args.days * 86400 if args.days else 0}
        notice["announcements"] = [a for a in notice["announcements"] if a["id"] != args.id] + [item]
    elif args.cmd == "remove":
        notice["announcements"] = [a for a in notice["announcements"] if a["id"] != args.id]
    if args.cmd != "show":
        notice = call("PUT", notice)
    print(json.dumps(notice, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
