#!/usr/bin/env python3
"""
Fetch Nanjing Metro #昨日客流# weibo text and parse it into JSON.

Usage:
  WEIBO_COOKIE='...' python3 weibo_yesterday_fetcher.py
  python3 weibo_yesterday_fetcher.py --cookie-file weibo_cookie.txt

Outputs:
  data/weibo_raw.txt
  data/weibo_parsed.json
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, date
from html import unescape
from typing import Optional, List, Dict, Tuple

import requests

UID_NANJING_METRO = "2638276292"
TIMELINE_URL = "https://m.weibo.cn/api/container/getIndex"
WEB_TIMELINE_URL = "https://weibo.com/ajax/statuses/mymblog"
EXTEND_URL = "https://m.weibo.cn/statuses/extend"
QR_SIGNIN_URL = "https://passport.weibo.com/sso/signin"
QR_IMAGE_URL = "https://passport.weibo.com/sso/v2/qrcode/image"
QR_CHECK_URL = "https://passport.weibo.com/sso/v2/qrcode/check"
LOGIN_CHECK_URL = "https://weibo.com/ajax/log/action"
QR_REFERER = "https://passport.weibo.com/sso/signin?entry=miniblog&source=miniblog&disp=popup&url=https%3A%2F%2Fweibo.com%2F"

DEFAULT_RAW_OUT = "data/weibo_raw.txt"
DEFAULT_JSON_OUT = "data/weibo_parsed.json"
DEFAULT_QR_IMAGE = "data/weibo_qr.png"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"https://weibo.com/u/{UID_NANJING_METRO}",
}

MOBILE_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
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


def strip_html(text: str) -> str:
    text = text.replace("<br />", "\n").replace("<br>", "\n")
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()

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

def apply_cookie_headers(session: requests.Session, cookie_str: str) -> None:
    session.headers.update({"Cookie": cookie_str})
    cookie_map = parse_cookie_value(cookie_str)
    xsrf = cookie_map.get("XSRF-TOKEN") or cookie_map.get("XSRF-TOKEN".lower())
    if xsrf:
        session.headers.update({"X-XSRF-TOKEN": xsrf})


def cookiejar_to_string(session: requests.Session) -> str:
    parts = []
    for cookie in session.cookies:
        if cookie.name and cookie.value:
            parts.append(f"{cookie.name}={cookie.value}")
    return "; ".join(parts)


def login_by_qr(session: requests.Session, qr_out: str) -> None:
    params = {
        "entry": "miniblog",
        "source": "miniblog",
        "disp": "popup",
        "url": "https://weibo.com/newlogin?tabtype=weibo&gid=102803&openLoginLayer=0&url=https%3A%2F%2Fweibo.com%2F",
    }
    resp = session.get(QR_SIGNIN_URL, params=params, timeout=20)
    if resp.status_code != 200:
        raise FetchError(f"qr signin request failed: {resp.status_code}")

    xsrf = session.cookies.get("XSRF-TOKEN") or session.cookies.get("XSRF-TOKEN".lower())
    headers = {"Referer": QR_REFERER}
    if xsrf:
        headers["X-CSRF-TOKEN"] = xsrf
    else:
        print("Warning: XSRF-TOKEN not found after signin, continuing without it.")
    resp = session.get(
        QR_IMAGE_URL,
        params={"entry": "miniblog", "size": "180"},
        headers=headers,
        timeout=20,
    )
    if resp.status_code != 200:
        raise FetchError(f"qr image request failed: {resp.status_code}")
    payload = resp.json()
    if payload.get("retcode") != 20000000:
        raise FetchError(f"qr image retcode error: {payload.get('retcode')}")

    qrid = payload["data"]["qrid"]
    image_url = payload["data"]["image"]

    img_resp = session.get(image_url, headers={"Referer": QR_REFERER}, timeout=20)
    if img_resp.status_code != 200:
        raise FetchError(f"qr image download failed: {img_resp.status_code}")
    os.makedirs(os.path.dirname(qr_out) or ".", exist_ok=True)
    with open(qr_out, "wb") as f:
        f.write(img_resp.content)

    print(f"QR code saved to: {qr_out}", flush=True)
    print("请用微博App扫码并确认登录，然后保持此脚本运行。", flush=True)

    for _ in range(60):
        check_headers = {"Referer": QR_REFERER}
        if xsrf:
            check_headers["X-CSRF-TOKEN"] = xsrf
        check_resp = session.get(
            QR_CHECK_URL,
            params={
                "entry": "miniblog",
                "source": "miniblog",
                "url": "https://weibo.com/newlogin?tabtype=weibo&gid=102803&openLoginLayer=0&url=https%3A%2F%2Fweibo.com%2F",
                "qrid": qrid,
                "disp": "popup",
            },
            headers=check_headers,
            timeout=20,
        )
        if check_resp.status_code != 200:
            raise FetchError(f"qr check request failed: {check_resp.status_code}")
        data = check_resp.json()
        if data.get("retcode") == 20000000 and data.get("data", {}).get("url"):
            login_url = data["data"]["url"]
            session.get(login_url, allow_redirects=True, timeout=20)
            verify = session.get(LOGIN_CHECK_URL, timeout=20)
            if verify.headers.get("X-Log-Uid"):
                return
        import time

        time.sleep(2)

    raise FetchError("qr login timeout")


def fetch_timeline(session: requests.Session, pages: int) -> List[Dict]:
    cards = []
    for page in range(1, pages + 1):
        params = {
            "type": "uid",
            "value": UID_NANJING_METRO,
            "containerid": f"107603{UID_NANJING_METRO}",
            "page": page,
        }
        resp = session.get(TIMELINE_URL, params=params, headers=MOBILE_HEADERS, timeout=20)
        if resp.status_code != 200:
            raise FetchError(f"timeline request failed: {resp.status_code}")
        payload = resp.json()
        if payload.get("ok") == -100:
            raise FetchError("m.weibo.cn requires login (ok=-100)")
        cards.extend(payload.get("data", {}).get("cards", []))
    return cards


def fetch_long_text(session: requests.Session, mid: str) -> Optional[str]:
    resp = session.get(EXTEND_URL, params={"id": mid}, timeout=20)
    if resp.status_code != 200:
        return None
    payload = resp.json()
    return payload.get("data", {}).get("longTextContent")


def find_yesterday_text(cards: List[Dict], session: requests.Session) -> Tuple[str, str]:
    for card in cards:
        mblog = card.get("mblog") or card.get("card_group", [{}])[0].get("mblog")
        if not mblog:
            continue
        text = mblog.get("text", "")
        if "#昨日客流#" not in text and "昨日客流" not in text:
            continue
        mid = str(mblog.get("id"))
        if mblog.get("isLongText"):
            long_text = fetch_long_text(session, mid)
            if long_text:
                text = long_text
        clean = strip_html(text)
        return clean, mid
    raise FetchError("no #昨日客流# post found in fetched pages")


def fetch_web_timeline(session: requests.Session, pages: int) -> List[Dict]:
    posts = []
    for page in range(1, pages + 1):
        params = {"uid": UID_NANJING_METRO, "page": page, "feature": 0, "count": 20}
        resp = session.get(
            WEB_TIMELINE_URL,
            params=params,
            headers=HEADERS,
            timeout=20,
        )
        if resp.status_code != 200:
            raise FetchError(f"web timeline request failed: {resp.status_code}")
        payload = resp.json()
        data = payload.get("data", {})
        posts.extend(data.get("list", []) or [])
    return posts


def find_yesterday_text_web(posts: List[Dict]) -> Tuple[str, str]:
    for post in posts:
        text = post.get("text_raw") or post.get("text") or ""
        if "#昨日客流#" not in text and "昨日客流" not in text:
            continue
        mid = str(post.get("id") or post.get("mid") or "")
        clean = strip_html(text)
        return clean, mid
    raise FetchError("no #昨日客流# post found in web timeline")


def infer_year(month: int, day: int) -> int:
    today = date.today()
    year = today.year
    try_date = date(year, month, day)
    # If date is more than 7 days in the future, assume last year (year rollover).
    if (try_date - today).days > 7:
        return year - 1
    return year


def parse_metro_text(text: str) -> Dict:
    pattern = r"(?:#昨日客流#)?南京地铁(\d{1,2})月(\d{1,2})日客运量(\d+(?:\.\d+)?)[^，]*，(.+?)（以上单位: 万）"
    match = re.search(pattern, text)
    if not match:
        raise FetchError("text does not match expected pattern")

    month = int(match.group(1))
    day = int(match.group(2))
    total = float(match.group(3))
    lines_data = match.group(4)

    year = infer_year(month, day)
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


def write_outputs(raw_text: str, parsed: Dict, raw_out: str, json_out: str) -> None:
    os.makedirs(os.path.dirname(raw_out) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(json_out) or ".", exist_ok=True)

    with open(raw_out, "w", encoding="utf-8") as f:
        f.write(raw_text)

    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(parsed, f, ensure_ascii=False, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch #昨日客流# weibo text and parse it into JSON")
    parser.add_argument("--pages", type=int, default=3, help="number of timeline pages to scan (default: 3)")
    parser.add_argument("--cookie-file", type=str, default=None, help="path to cookie file")
    parser.add_argument("--raw-out", type=str, default=DEFAULT_RAW_OUT, help="output path for raw text")
    parser.add_argument("--json-out", type=str, default=DEFAULT_JSON_OUT, help="output path for parsed JSON")
    parser.add_argument("--debug-list", action="store_true", help="print brief info for fetched posts")
    parser.add_argument("--from-raw", type=str, default=None, help="parse from a raw text file without fetching")
    parser.add_argument("--login-qr", action="store_true", help="use QR code login to obtain cookies")
    parser.add_argument("--cookie-out", type=str, default="weibo_cookie.txt", help="path to save cookies after login")
    parser.add_argument("--qr-out", type=str, default=DEFAULT_QR_IMAGE, help="path to save QR image")
    args = parser.parse_args()

    if args.from_raw:
        with open(args.from_raw, "r", encoding="utf-8") as f:
            raw_text = f.read().strip()
        parsed = parse_metro_text(raw_text)
        write_outputs(raw_text, parsed, args.raw_out, args.json_out)
        print(f"Raw text loaded from: {args.from_raw}")
        print(f"Raw text saved to: {args.raw_out}")
        print(f"Parsed JSON saved to: {args.json_out}")
        return 0

    cookie = load_cookie(args.cookie_file)

    session = requests.Session()
    session.headers.update(HEADERS)
    if cookie:
        apply_cookie_headers(session, cookie)
    elif not args.login_qr:
        print("Missing cookie. Set WEIBO_COOKIE or provide --cookie-file (or weibo_cookie.txt).", file=sys.stderr)
        return 2

    if args.login_qr:
        try:
            login_by_qr(session, args.qr_out)
            cookie_str = cookiejar_to_string(session)
            if cookie_str:
                with open(args.cookie_out, "w", encoding="utf-8") as f:
                    f.write(cookie_str)
                print(f"Cookie saved to: {args.cookie_out}")
                apply_cookie_headers(session, cookie_str)
        except FetchError as e:
            print(f"QR login failed: {e}", file=sys.stderr)
            return 2

    try:
        posts = fetch_web_timeline(session, args.pages)
        if args.debug_list:
            print(f"web timeline posts: {len(posts)}")
            for p in posts[:5]:
                txt = (p.get("text_raw") or p.get("text") or "")[:120]
                print(f"- {strip_html(txt)}")
        raw_text, mid = find_yesterday_text_web(posts)
    except FetchError:
        cards = fetch_timeline(session, args.pages)
        if args.debug_list:
            print(f"mobile timeline cards: {len(cards)}")
            shown = 0
            for c in cards:
                mblog = c.get("mblog") or c.get("card_group", [{}])[0].get("mblog")
                if not mblog:
                    continue
                user = mblog.get("user") or {}
                uid = user.get("id") or ""
                name = user.get("screen_name") or ""
                txt = (mblog.get("text") or "")[:160]
                print(f"- [{uid} {name}] {strip_html(txt)}")
                shown += 1
                if shown >= 5:
                    break
        raw_text, mid = find_yesterday_text(cards, session)
    parsed = parse_metro_text(raw_text)

    write_outputs(raw_text, parsed, args.raw_out, args.json_out)

    print(f"Fetched MID: {mid}")
    print(f"Raw text saved to: {args.raw_out}")
    print(f"Parsed JSON saved to: {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
