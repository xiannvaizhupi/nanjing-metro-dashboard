#!/usr/bin/env python3
"""
Batch fetch #昨日客流# posts for a date range and output JSON.

Example:
  python3 weibo_batch_fetch.py --start 2025-01-01 --end 2025-09-08 \
    --cookie-file weibo_cookie.txt --out data/weibo_2025_01_01_2025_09_08.json
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, date
from typing import Dict, List, Optional

import requests

UID_NANJING_METRO = "2638276292"
MOBILE_TIMELINE_URL = "https://m.weibo.cn/api/container/getIndex"
MOBILE_EXTEND_URL = "https://m.weibo.cn/statuses/extend"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"https://m.weibo.cn/u/{UID_NANJING_METRO}",
}


class FetchError(RuntimeError):
    pass


def load_cookie(cookie_file: Optional[str]) -> Optional[str]:
    env_cookie = os.getenv("WEIBO_COOKIE")
    if env_cookie:
        return env_cookie.strip()
    if cookie_file and os.path.exists(cookie_file):
        with open(cookie_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    default_file = "weibo_cookie.txt"
    if os.path.exists(default_file):
        with open(default_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None


def parse_cookie_value(cookie_str: str) -> Dict[str, str]:
    cookies = {}
    for part in cookie_str.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name and value:
            cookies[name] = value
    return cookies


def apply_cookie_headers(session: requests.Session, cookie_str: str, cookie_keys: Optional[List[str]]) -> None:
    cookie_map = parse_cookie_value(cookie_str)
    if cookie_keys:
        cookie_map = {k: v for k, v in cookie_map.items() if k in cookie_keys}
    cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_map.items()])
    session.headers.update({"Cookie": cookie_str})
    xsrf = cookie_map.get("XSRF-TOKEN") or cookie_map.get("XSRF-TOKEN".lower())
    if xsrf:
        session.headers.update({"X-XSRF-TOKEN": xsrf})


def strip_html(text: str) -> str:
    text = text.replace("<br />", "\n").replace("<br>", "\n")
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def parse_created_at(created_at: str) -> Optional[date]:
    # Example: "Wed Mar 12 09:00:00 +0800 2026"
    try:
        dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
        return dt.date()
    except Exception:
        return None


def parse_metro_text(text: str, year_hint: Optional[int]) -> Optional[Dict]:
    pattern = r"(?:#昨日客流#)?南京地铁(\d{1,2})月(\d{1,2})日客运量(\d+(?:\.\d+)?)[^，]*，(.+?)（以上单位: 万）"
    match = re.search(pattern, text)
    if not match:
        return None

    month = int(match.group(1))
    day = int(match.group(2))
    total = float(match.group(3))
    lines_data = match.group(4)

    if year_hint is None:
        year = datetime.now().year
    else:
        year = year_hint

    date_str = f"{year:04d}-{month:02d}-{day:02d}"

    lines = {}
    for line_num, passenger in re.findall(r"(?<!S)(\d+)号线[：:]?(\d+(?:\.\d+)?)", lines_data):
        lines[f"L{line_num}"] = float(passenger)
    for line_num, passenger in re.findall(r"S(\d+)号线[：:]?(\d+(?:\.\d+)?)", lines_data):
        lines[f"S{line_num}"] = float(passenger)

    d = datetime.strptime(date_str, "%Y-%m-%d")
    is_weekend = d.weekday() >= 5

    return {
        "date": date_str,
        "total": total,
        "lines": lines,
        "is_weekend": is_weekend,
        "note": "",
    }


def fetch_page(session: requests.Session, since_id: Optional[str]) -> Dict:
    params = {
        "type": "uid",
        "value": UID_NANJING_METRO,
        "containerid": f"107603{UID_NANJING_METRO}",
    }
    if since_id:
        params["since_id"] = since_id
    resp = session.get(MOBILE_TIMELINE_URL, params=params, headers=HEADERS, timeout=20)
    if resp.status_code != 200:
        raise FetchError(f"mobile timeline request failed: {resp.status_code}")
    payload = resp.json()
    if payload.get("ok") != 1:
        raise FetchError(f"mobile timeline response not ok: {payload.get('ok')}")
    return payload.get("data", {}) or {}


def fetch_long_text(session: requests.Session, mid: str) -> Optional[str]:
    resp = session.get(MOBILE_EXTEND_URL, params={"id": mid}, headers=HEADERS, timeout=20)
    if resp.status_code != 200:
        return None
    payload = resp.json()
    return payload.get("data", {}).get("longTextContent")


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch fetch #昨日客流# posts for a date range")
    parser.add_argument("--start", required=True, help="start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="end date YYYY-MM-DD")
    parser.add_argument("--cookie-file", type=str, default=None, help="path to cookie file")
    parser.add_argument("--out", type=str, default="data/weibo_batch.json", help="output json path")
    parser.add_argument("--sleep", type=float, default=0.3, help="sleep seconds between pages")
    parser.add_argument("--max-pages", type=int, default=500, help="safety limit for pages")
    parser.add_argument("--cookie-keys", type=str, default="SUB,SUBP,SCF,SSOLoginState,ALF,XSRF-TOKEN,WBPSESS,_T_WM,MLOGIN,WEIBOCN_FROM", help="comma-separated cookie keys to keep")
    args = parser.parse_args()

    start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_date = datetime.strptime(args.end, "%Y-%m-%d").date()
    if end_date < start_date:
        print("end date must be >= start date", file=sys.stderr)
        return 2

    cookie = load_cookie(args.cookie_file)
    if not cookie:
        print("Missing cookie. Set WEIBO_COOKIE or provide --cookie-file.", file=sys.stderr)
        return 2

    session = requests.Session()
    cookie_keys = [k for k in args.cookie_keys.split(",") if k]
    apply_cookie_headers(session, cookie, cookie_keys)

    results = {}
    fetched_pages = 0
    since_id = None
    while fetched_pages <= args.max_pages:
        data = fetch_page(session, since_id)
        cards = data.get("cards", []) or []
        if not cards:
            break

        oldest_date_in_page = None
        for card in cards:
            mblog = card.get("mblog") or card.get("card_group", [{}])[0].get("mblog")
            if not mblog:
                continue
            created_at = mblog.get("created_at", "")
            created_date = parse_created_at(created_at)
            if created_date is not None:
                oldest_date_in_page = created_date
            text = mblog.get("text") or ""
            if "昨日客流" not in text:
                continue
            mid = str(mblog.get("id") or "")
            if mblog.get("isLongText"):
                long_text = fetch_long_text(session, mid)
                if long_text:
                    text = long_text
            clean = strip_html(text)
            year_hint = created_date.year if created_date else None
            parsed = parse_metro_text(clean, year_hint)
            if not parsed:
                continue
            parsed_date = datetime.strptime(parsed["date"], "%Y-%m-%d").date()
            if start_date <= parsed_date <= end_date:
                results[parsed["date"]] = parsed

        if oldest_date_in_page and oldest_date_in_page < start_date:
            break

        since_id = (data.get("cardlistInfo") or {}).get("since_id") or since_id
        fetched_pages += 1
        time.sleep(args.sleep)

    output_list = [results[k] for k in sorted(results.keys())]
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(output_list, f, ensure_ascii=False, indent=2)

    print(f"Fetched {len(output_list)} records to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
