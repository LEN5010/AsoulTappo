#!/usr/bin/env python3
"""Check the local AsoulTappo server and report changes in health."""

import argparse
from contextlib import closing
from http.client import HTTPException
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ENV_PREFIX = "ASOULTAPPO_MONITOR_"
DAY_OFFSET = 8 * 3600
HOUR = 3600
MB = 1_000_000
GB = 1_000_000_000
DB_TIMEOUT = 2
PROBE_TIMEOUT = 10
PROBE_GAP = 5
PROBES = 3
SUBJECT = "AsoulTappo 服务巡检"
HTTP_ERRORS = (OSError, HTTPException, ValueError)


def day_of(ts):
    return time.strftime("%Y-%m-%d", time.gmtime(ts + DAY_OFFSET))


def parse_args(argv, environ):
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Email env: ASOULTAPPO_MONITOR_RESEND_KEY, ASOULTAPPO_MONITOR_FROM, ASOULTAPPO_MONITOR_TO.",
    )
    for option, description in (
        ("db", "SQLite database path"),
        ("url", "Server base URL"),
        ("state", "State file path"),
    ):
        env = ENV_PREFIX + option.upper()
        default = environ.get(env) or None
        parser.add_argument(f"--{option}", default=default, required=default is None,
                            help=f"{description} (env {env})")

    parser.add_argument("--saves-10m", type=int, default=40, help="10-minute save limit (default: 40)")
    parser.add_argument("--saves-60m", type=int, default=120, help="60-minute save limit (default: 120)")
    parser.add_argument("--stall-seconds", type=float, default=3, help="Slow probe in seconds (default: 3)")
    parser.add_argument("--stall-probes", type=int, choices=range(1, PROBES + 1), default=2,
                        help="Slow or failed probes needed to alert (default: 2)")
    parser.add_argument("--growth-mb", type=int, default=50, help="Hourly growth in decimal MB (default: 50)")
    parser.add_argument("--free-gb", type=int, default=3, help="Minimum free disk in decimal GB (default: 3)")
    parser.add_argument("--shards", type=int, default=2_000_000, help="Shards issued per run (default: 2000000)")
    parser.add_argument("--dry-run", action="store_true", help="Print alerts without sending or saving state")
    args = parser.parse_args(argv)
    args.db = Path(args.db).resolve()
    args.state = Path(args.state)
    if args.state.resolve() in {Path(str(args.db) + suffix) for suffix in ("", "-wal", "-shm", "-journal")}:
        parser.error("--state must be separate from the SQLite files")
    if not 0 <= args.stall_seconds < float("inf"):
        parser.error("--stall-seconds must be a finite nonnegative number")
    for option in ("saves_10m", "saves_60m", "growth_mb", "free_gb", "shards"):
        if getattr(args, option) < 0:
            parser.error(f"--{option.replace('_', '-')} must be nonnegative")
    return args


def load_state(path):
    empty = {"sizes": [], "shards": {}, "alerts": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return empty
    if not isinstance(state, dict):
        return empty

    sizes = state.get("sizes", [])
    if not isinstance(sizes, list) or not all(
        isinstance(sample, list) and len(sample) == 2
        and isinstance(sample[0], (int, float)) and 0 <= sample[0] < float("inf")
        and isinstance(sample[1], int) and sample[1] >= 0
        for sample in sizes
    ):
        return empty

    shards = state.get("shards", {})
    if not isinstance(shards, dict) or (shards and (
        not isinstance(shards.get("day"), str)
        or not isinstance(shards.get("sums"), dict)
        or not all(isinstance(value, int) and value >= 0 for value in shards["sums"].values())
    )):
        return empty

    alerts = state.get("alerts", {})
    if not isinstance(alerts, dict) or not all(
        isinstance(alert, dict) and isinstance(alert.get("failing"), bool)
        and isinstance(alert.get("sent"), (int, float)) and 0 <= alert["sent"] < float("inf")
        and isinstance(alert.get("pending"), list) and all(isinstance(line, str) for line in alert["pending"])
        for alert in alerts.values()
    ):
        return empty
    return {"sizes": sizes, "shards": shards, "alerts": alerts}


def write_state(path, state):
    file = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False)
    temp = Path(file.name)
    try:
        with file:
            json.dump(state, file, ensure_ascii=False)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def read_database(path, now, day):
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=DB_TIMEOUT)) as db:
        db.execute("PRAGMA query_only=ON")
        saves_10m, saves_60m = db.execute(
            "SELECT COUNT(CASE WHEN created >= ? THEN 1 END), COUNT(*) "
            "FROM players WHERE created BETWEEN ? AND ?",
            (now - 600, now - HOUR, now),
        ).fetchone()
        shards = dict(db.execute(
            "SELECT source, SUM(amount) FROM shard_ledger WHERE day = ? AND amount > 0 GROUP BY source",
            (day,),
        ))
    return saves_10m, saves_60m, shards


def check_shards(state, day, sums, threshold):
    previous = state["shards"]
    state["shards"] = {"day": day, "sums": sums}
    if previous.get("day") != day:
        return None
    increases = [(source, amount - previous["sums"].get(source, 0)) for source, amount in sums.items()]
    increases = [(source, delta) for source, delta in increases if delta > 0]
    total = sum(delta for _, delta in increases)
    if total <= threshold:
        return ""
    largest = sorted(increases, key=lambda pair: (-pair[1], pair[0]))[:3]
    sources = "，".join(f"{source} +{delta}" for source, delta in largest)
    return f"本次增加 {total}，阈值 > {threshold}。{sources}"


def check_size(args, state, now):
    samples = [sample for sample in state["sizes"] if now - HOUR <= sample[0] <= now]
    state["sizes"] = samples
    try:
        size = args.db.stat().st_size
        wal = Path(f"{args.db}-wal")
        try:
            size += wal.stat().st_size
        except FileNotFoundError:
            pass
        free = shutil.disk_usage(args.db).free
    except FileNotFoundError:
        return None
    except OSError:
        return "磁盘状态读取失败"

    growth = size - min(samples, key=lambda sample: sample[0])[1] if samples else 0
    samples.append([now, size])
    problems = []
    if growth > args.growth_mb * MB:
        problems.append(f"近 1 小时增长 {growth / MB:.2f} MB，阈值 > {args.growth_mb} MB")
    if free < args.free_gb * GB:
        problems.append(f"剩余 {free / GB:.2f} GB，阈值 < {args.free_gb} GB")
    return "。".join(problems)


def probe(url, opener, monotonic):
    started = monotonic()
    try:
        with opener(url, timeout=PROBE_TIMEOUT) as response:
            result = json.load(response)
    except HTTP_ERRORS:
        return None
    if not isinstance(result, dict) or result.get("status") != "ok":
        return None
    waited = result.get("waited")
    if type(waited) not in (int, float) or not 0 <= waited < float("inf"):
        return None
    return max(monotonic() - started, waited)


def check_stalls(args, opener, monotonic, sleep):
    url = args.url.rstrip("/") + "/healthz/store"
    durations = []
    for attempt in range(PROBES):
        if attempt:
            sleep(PROBE_GAP)
        durations.append(probe(url, opener, monotonic))
    bad = sum(duration is None or duration > args.stall_seconds for duration in durations)
    if bad < args.stall_probes:
        return ""
    readings = " / ".join("失败" if duration is None else f"{duration:.3f} 秒" for duration in durations)
    return (f"慢或失败 {bad}/{PROBES} 次，阈值 ≥ {args.stall_probes} 次，"
            f"慢请求 > {args.stall_seconds:g} 秒。{readings}")


def collect_checks(args, state, now, opener, monotonic, sleep):
    day = day_of(now)
    checks = {}
    try:
        saves_10m, saves_60m, shards = read_database(args.db, now, day)
    except (sqlite3.Error, OSError):
        checks["数据库读取"] = f"读取失败，锁等待上限 {DB_TIMEOUT} 秒"
    else:
        checks["数据库读取"] = ""
        checks["新增存档"] = ""
        if saves_10m >= args.saves_10m or saves_60m >= args.saves_60m:
            checks["新增存档"] = (
                f"10 分钟 {saves_10m} 个，阈值 ≥ {args.saves_10m}。"
                f"60 分钟 {saves_60m} 个，阈值 ≥ {args.saves_60m}"
            )
        checks["碎片发放"] = check_shards(state, day, shards, args.shards)

    checks["数据库容量"] = check_size(args, state, now)
    checks["存储探针"] = check_stalls(args, opener, monotonic, sleep)
    return checks


def queue_alerts(alerts, checks, now):
    for check, problem in checks.items():
        if problem is None:
            continue
        alert = alerts.get(check)
        if problem:
            if alert is None:
                alert = alerts[check] = {"failing": False, "sent": 0, "pending": []}
            if not alert["failing"]:
                alert["pending"].append(f"异常：{check}，{problem}")
            elif not alert["pending"] and now - alert["sent"] >= HOUR:
                alert["pending"].append(f"持续异常：{check}，{problem}")
            alert["failing"] = True
        elif alert and alert["failing"]:
            alert["pending"].append(f"恢复：{check}")
            alert["failing"] = False
    return [line for alert in alerts.values() for line in alert["pending"]]


def mark_sent(alerts, now):
    for check, alert in list(alerts.items()):
        if alert["failing"]:
            if alert["pending"]:
                alert.update(sent=now, pending=[])
        else:
            del alerts[check]


def send_resend(subject, body, *, key, sender, recipient, opener):
    if not sender or not recipient:
        raise ValueError("Missing sender or recipient")
    data = json.dumps({"from": sender, "to": [recipient], "subject": subject, "text": body}).encode("utf-8")
    request = Request("https://api.resend.com/emails", data=data, method="POST",
                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                               "User-Agent": "asoultappo-monitor"})
    with opener(request, timeout=10):
        pass


def main(argv=None, *, environ=None, clock=time.time, monotonic=time.monotonic, sleep=time.sleep,
         opener=urlopen, mail_sender=send_resend):
    environ = os.environ if environ is None else environ
    args = parse_args(argv, environ)
    try:
        state = load_state(args.state)
    except OSError:
        print("巡检状态读取失败")
        return 1

    checks = collect_checks(args, state, clock(), opener, monotonic, sleep)
    alerts = state["alerts"]
    lines = queue_alerts(alerts, checks, clock())
    key = environ.get(ENV_PREFIX + "RESEND_KEY")
    if lines:
        body = "\n".join(lines)
        if args.dry_run or not key:
            print(body)
            mark_sent(alerts, clock())
        else:
            try:
                mail_sender(SUBJECT, body, key=key, sender=environ.get(ENV_PREFIX + "FROM"),
                            recipient=environ.get(ENV_PREFIX + "TO"), opener=opener)
            except HTTPError as error:
                print(f"告警邮件发送失败，HTTP {error.code}，下次重试")
                error.close()
            except HTTP_ERRORS:
                print("告警邮件发送失败，下次重试")
            else:
                mark_sent(alerts, clock())

    if not args.dry_run:
        try:
            write_state(args.state, state)
        except OSError:
            print("巡检状态写入失败")
            return 1
    failing = [check for check, problem in checks.items() if problem]
    names = "：" + "、".join(failing) if failing else ""
    print(f"巡检完成，异常 {len(failing)} 项{names}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
