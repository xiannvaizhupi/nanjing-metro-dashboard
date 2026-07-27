#!/usr/bin/env python3
"""
南京地铁客流数据自动抓取脚本
从南京地铁官网首页优先获取昨日客流数据，微博组件作为兜底
"""

import json
import re
import os
import math
import ssl
import sys
import subprocess
import tempfile
import time
from html import unescape
from datetime import datetime, date, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
METRO_DATA_PATH = os.path.join(REPO_DIR, 'data', 'metro_data.json')
PREDICTION_LOG_PATH = os.path.join(REPO_DIR, 'data', 'prediction_log.json')
ML_PREDICTIONS_PATH = os.path.join(REPO_DIR, 'data', 'ml_predictions.json')
ML_PREDICTOR_PATH = os.path.join(SCRIPT_DIR, 'ml_predictor.py')

EXIT_SUCCESS = 0
EXIT_SOURCE_UNAVAILABLE = 2
EXIT_DATA_PENDING = 3
EXIT_DATA_INVALID = 4

PUSH_RETRY_DELAYS = (5, 15)

OFFICIAL_HOMEPAGE_URL = "https://www.njmetro.com.cn/njdtweb/gx/dtmain.jsp"
OFFICIAL_FLOW_API_URL = "https://www.njmetro.com.cn/njdtweb/portal/get-lineIntro.do"
OFFICIAL_FLOW_ROW_ID = "8a80800766e1aa290166e7e5c60d0003"
WEIBO_WIDGET_URL = "https://widget.weibo.com/weiboshow/index.php?language=&width=0&height=430&fansRow=1&ptype=1&speed=0&skin=1&isTitle=1&noborder=1&isWeibo=1&isFans=0&uid=2638276292&verifier=138e3b0a&dpc=1"

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

LINE_PATTERNS = [
    (r'(?<![A-Za-z])1号线[：:]?(\d+\.?\d*)', 'L1'),
    (r'(?<![A-Za-z])2号线[：:]?(\d+\.?\d*)', 'L2'),
    (r'(?<![A-Za-z])3号线[：:]?(\d+\.?\d*)', 'L3'),
    (r'(?<![A-Za-z])4号线[：:]?(\d+\.?\d*)', 'L4'),
    (r'(?<![A-Za-z])5号线[：:]?(\d+\.?\d*)', 'L5'),
    (r'(?<![A-Za-z])7号线[：:]?(\d+\.?\d*)', 'L7'),
    (r'(?<![A-Za-z])10号线[：:]?(\d+\.?\d*)', 'L10'),
    (r'S1号线[：:]?(\d+\.?\d*)', 'S1'),
    (r'S2号线[：:]?(\d+\.?\d*)', 'S2'),
    (r'S3号线[：:]?(\d+\.?\d*)', 'S3'),
    (r'S6号线[：:]?(\d+\.?\d*)', 'S6'),
    (r'S7号线[：:]?(\d+\.?\d*)', 'S7'),
    (r'S8号线[：:]?(\d+\.?\d*)', 'S8'),
    (r'S9号线[：:]?(\d+\.?\d*)', 'S9'),
]

# 停运线路仍属于完整公告，将其客流记为 0 并保留状态说明。
SUSPENDED_LINE_PATTERNS = [
    (r'(?<![A-Za-z])1号线[：:]?(?:全天)?停运', 'L1'),
    (r'(?<![A-Za-z])2号线[：:]?(?:全天)?停运', 'L2'),
    (r'(?<![A-Za-z])3号线[：:]?(?:全天)?停运', 'L3'),
    (r'(?<![A-Za-z])4号线[：:]?(?:全天)?停运', 'L4'),
    (r'(?<![A-Za-z])5号线[：:]?(?:全天)?停运', 'L5'),
    (r'(?<![A-Za-z])7号线[：:]?(?:全天)?停运', 'L7'),
    (r'(?<![A-Za-z])10号线[：:]?(?:全天)?停运', 'L10'),
    (r'S1号线[：:]?(?:全天)?停运', 'S1'),
    (r'S2号线[：:]?(?:全天)?停运', 'S2'),
    (r'S3号线[：:]?(?:全天)?停运', 'S3'),
    (r'S6号线[：:]?(?:全天)?停运', 'S6'),
    (r'S7号线[：:]?(?:全天)?停运', 'S7'),
    (r'S8号线[：:]?(?:全天)?停运', 'S8'),
    (r'S9号线[：:]?(?:全天)?停运', 'S9'),
]

# 当前公告正常会覆盖 12 至 14 条线路状态；低于 10 条通常是页面内容截断。
MINIMUM_COMPLETE_LINE_COUNT = 10
MAXIMUM_TOTAL_LINE_DIFFERENCE = 5.0

NEXT_ENTRY_PATTERN = (
    r'(?:(?:\d{2,4})[-/.年](?:\d{1,2})[-/.月](?:\d{1,2})[日号]?)?'
    r'(?:#?昨日客流#?.{0,80}?)?'
    r'南京地铁(?:\d{2,4}年)?\d{1,2}月\d{1,2}日(?:线网)?客运量'
)

FLOW_ENTRY_PATTERN = re.compile(
    r'(?:(\d{2,4})[-/.年](\d{1,2})[-/.月](\d{1,2})[日号]?)?'
    r'(?:#?昨日客流#?.{0,80}?)?'
    r'南京地铁(?:(\d{2,4})年)?(?:(\d{1,2})月)?(\d{1,2})日(?:线网)?客运量(?:为)?[：:]?(\d+\.?\d*)万?'
    r'[，,；;。]?(.+?)(?:[（(]?以上单位[:：]?万?[）)]?|(?=' + NEXT_ENTRY_PATTERN + r')|$)',
    re.S
)


def decode_response(response):
    """按响应头和常见中文编码解码网页。"""
    raw = response.read()
    charset = response.headers.get_content_charset()
    encodings = [charset, 'utf-8', 'gb18030', 'gbk']

    for encoding in dict.fromkeys(e for e in encodings if e):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue

    return raw.decode('utf-8', errors='replace')


def is_ssl_verification_error(error):
    """识别直接或经 URLError 包装的证书校验错误。"""
    reason = getattr(error, 'reason', None)
    return (
        isinstance(error, ssl.SSLError)
        or isinstance(reason, ssl.SSLError)
        or 'CERTIFICATE_VERIFY_FAILED' in str(error)
    )


def cache_busted_url(url, nonce=None):
    """为容易返回旧页面的组件请求追加防缓存参数。"""
    separator = '&' if '?' in url else '?'
    value = nonce if nonce is not None else int(datetime.now().timestamp() * 1000)
    return f"{url}{separator}_={value}"


def fetch_url(source_name, url, form_data=None, extra_headers=None):
    """抓取指定来源；南京地铁旧证书失败时自动使用未验证连接重试。"""
    payload = urlencode(form_data).encode('utf-8') if form_data else None
    request_headers = dict(HTTP_HEADERS)
    request_headers.update(extra_headers or {})

    def request(context=None):
        req = Request(url, data=payload, headers=request_headers)
        response = urlopen(req, timeout=30, context=context)
        return decode_response(response)

    try:
        return request()
    except Exception as error:
        if not is_ssl_verification_error(error):
            print(f"获取{source_name}失败: {error}")
            return None

        print(f"  [SSL] {source_name} 证书校验失败，使用兼容模式重试: {error}")
        try:
            return request(ssl._create_unverified_context())
        except Exception as retry_error:
            print(f"获取{source_name}失败: {retry_error}")
            return None


def fetch_weibo_data():
    """从南京地铁官方微博组件获取数据。保留给旧测试或手动调用。"""
    return fetch_url(
        "南京地铁官方微博组件",
        cache_busted_url(WEIBO_WIDGET_URL),
        extra_headers={
            'Referer': OFFICIAL_HOMEPAGE_URL,
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        },
    )


def parse_official_total(response_text):
    """解析官网首页 AJAX 接口返回的昨日总客流。"""
    payload = json.loads(response_text)
    value = float(payload['articleTitle'])
    if not 0 < value < 1000:
        raise ValueError(f"官网客流数值超出合理范围: {value}")
    return value


def fetch_official_total():
    """调用官网首页 JavaScript 实际使用的 POST 接口。"""
    response_text = fetch_url(
        "南京地铁官网客流接口",
        OFFICIAL_FLOW_API_URL,
        form_data={'rowId': OFFICIAL_FLOW_ROW_ID},
    )
    if response_text is None:
        return None, False
    try:
        total = parse_official_total(response_text)
    except Exception as error:
        print(f"南京地铁官网客流接口解析失败: {error}")
        return None, True
    print(f"官网首页昨日客流: {total}万")
    return total, True


def build_official_total_entry(total, target_date):
    """明细暂不可用时，仍使用官网总量维持总客流连续更新。"""
    return {
        'date': target_date.isoformat(),
        'total': total,
        'is_weekend': target_date.weekday() >= 5,
        'note': '官网总量；线路明细待补',
        'lines': {},
    }


def fetch_passenger_flow_entries(reference_date=None):
    """组合官网总量与官网首页嵌入的官方微博线路明细。"""
    ref = reference_date or date.today()
    expected_date = ref - timedelta(days=1)
    successful_sources = []
    reached_sources = []

    official_total, official_reached = fetch_official_total()
    if official_reached:
        reached_sources.append('南京地铁官网客流接口')
    if official_total is not None:
        successful_sources.append('南京地铁官网客流接口')

    detailed_entries = []
    widget_html = fetch_url(
        "南京地铁官网嵌入的官方微博组件",
        cache_busted_url(WEIBO_WIDGET_URL),
        extra_headers={
            'Referer': OFFICIAL_HOMEPAGE_URL,
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        },
    )
    if widget_html is not None:
        reached_sources.append('南京地铁官方微博组件')
        try:
            detailed_entries = parse_passenger_flow(widget_html, source_name='南京地铁官方微博组件')
        except Exception as error:
            print(f"南京地铁官方微博组件解析异常: {error}")
        if detailed_entries:
            successful_sources.append('南京地铁官方微博组件')

    if official_total is not None:
        expected_key = expected_date.isoformat()
        expected_entry = next((item for item in detailed_entries if item['date'] == expected_key), None)
        if expected_entry:
            if abs(expected_entry['total'] - official_total) > 0.01:
                print(
                    f"[校验] 无日期的官网总量 {official_total} 与日期明确的线路公告总量 "
                    f"{expected_entry['total']} 不一致，以线路公告为准。"
                )
        else:
            matching_detail = any(abs(item['total'] - official_total) <= 0.01 for item in detailed_entries)
            metro_map = load_metro_data()
            latest_existing = max(metro_map.values(), key=lambda item: item['date']) if metro_map else None
            matching_existing = bool(
                latest_existing
                and abs(float(latest_existing.get('total', 0)) - official_total) <= 0.01
            )
            if not matching_detail and not matching_existing:
                print(f"微博明细尚未发布，使用官网总量更新 {expected_key}。")
                detailed_entries.append(build_official_total_entry(official_total, expected_date))

    if detailed_entries:
        detailed_entries.sort(key=lambda item: item['date'])
        source_name = (
            '南京地铁官网首页（官方微博线路明细）'
            if official_total is not None
            else '南京地铁官方微博组件'
        )
        print(f"使用数据源: {source_name}")
        return detailed_entries, source_name, successful_sources, reached_sources

    return [], None, successful_sources, reached_sources


def infer_entry_year(month, day, explicit_year=None, reference_date=None):
    """根据微博日期推断年份，避免跨年后仍写死到旧年份。"""
    if explicit_year:
        year = int(explicit_year)
        return 2000 + year if year < 100 else year

    ref = reference_date or date.today()
    candidates = []
    # 当 month 为 None 时（如微博只写"27日客运量"），用 ref 的月份作为回退
    months_to_try = [month] if month is not None else [ref.month, ref.month - 1 if ref.month > 1 else 12]
    days_to_try = [day]

    for m in months_to_try:
        for d in days_to_try:
            for year in range(ref.year - 1, ref.year + 2):
                try:
                    candidate = date(year, m, d)
                except ValueError:
                    continue
                # 官网/微博可能在前一天晚间提前给出次日日期，允许一周内的近未来日期。
                if candidate > ref + timedelta(days=7):
                    continue
                candidates.append((abs((candidate - ref).days), year, m, d))

    if not candidates:
        raise ValueError(f"无法推断日期年份: {month}-{day}")

    # 优先选离 ref 最近的；多条同距离时选月份最大的（更可能是同月）
    candidates.sort(key=lambda x: (x[0], -x[2]))
    return min(candidates)[1]


def normalize_flow_text(html):
    """把官网/微博 HTML 归一为便于正则提取的连续文本。"""
    normalized = unescape(html)
    normalized = re.sub(
        r'\\u([0-9a-fA-F]{4})',
        lambda match: chr(int(match.group(1), 16)),
        normalized,
    )
    normalized = re.sub(r'<[^>]+>', '', normalized)
    normalized = re.sub(r'[\u200b\ufeff\xa0]', '', normalized)
    normalized = re.sub(r'\s+', '', normalized)
    return normalized


def parse_passenger_flow(html, source_name=''):
    """解析官网首页或微博组件中的客流数据。"""
    if not html:
        return []

    results = []
    seen_dates = set()
    normalized = normalize_flow_text(html)

    for match in FLOW_ENTRY_PATTERN.finditer(normalized):
        explicit_year = match.group(1) or match.group(4)
        month_raw = match.group(5)
        month = int(month_raw) if month_raw else None
        day = int(match.group(6))
        total = float(match.group(7))
        lines_str = match.group(8)

        year = infer_entry_year(month, day, explicit_year=explicit_year)
        # month 可能为 None（微博里只写"27日客运量"），用当前月份兜底
        if month is None:
            month = datetime.now().month
        date_str = f"{year}-{month:02d}-{day:02d}"
        if date_str in seen_dates:
            continue

        # 解析各线路
        lines = {}
        for line_pattern, line_id in LINE_PATTERNS:
            line_match = re.search(line_pattern, lines_str)
            if line_match:
                lines[line_id] = float(line_match.group(1))

        suspended_lines = []
        for line_pattern, line_id in SUSPENDED_LINE_PATTERNS:
            if line_id not in lines and re.search(line_pattern, lines_str):
                lines[line_id] = 0.0
                suspended_lines.append(line_id)

        if len(lines) < MINIMUM_COMPLETE_LINE_COUNT:
            print(f"跳过疑似不完整数据: {date_str}，仅解析到 {len(lines)} 条线路")
            continue

        line_total_difference = round(total - sum(lines.values()), 2)
        if abs(line_total_difference) > MAXIMUM_TOTAL_LINE_DIFFERENCE:
            print(
                f"跳过总量校验失败数据: {date_str}，官网总量与线路合计相差 "
                f"{line_total_difference}万"
            )
            continue
        if abs(line_total_difference) > 0.5:
            print(
                f"[校验] {date_str} 官网总量与线路合计相差 "
                f"{line_total_difference}万，保留官方原始值。"
            )

        d = date(year, month, day)
        is_weekend = d.weekday() >= 5

        results.append({
            'date': date_str,
            'total': total,
            'is_weekend': is_weekend,
            'note': f"停运线路：{'、'.join(suspended_lines)}" if suspended_lines else '',
            'lines': lines
        })
        seen_dates.add(date_str)

        source_label = f"[{source_name}]" if source_name else ""
        print(f"解析{source_label}: {date_str} - {total}万")

    return results


def parse_weibo_flow(html):
    """兼容旧调用名：解析微博或官网客流文本。"""
    return parse_passenger_flow(html, source_name='南京地铁官方微博组件')


def write_json_atomic(path, payload):
    """先写临时文件再替换，避免任务中断留下半截 JSON。"""
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            'w',
            encoding='utf-8',
            dir=os.path.dirname(path),
            delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
            temporary_path = handle.name
        os.replace(temporary_path, path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def update_metro_data(new_entries, source_name=None):
    """更新metro_data.json，返回是否有新数据被添加"""
    try:
        with open(METRO_DATA_PATH, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("metro_data.json 不存在")
        return False

    existing_dates = {item['date'] for item in data['daily_data']}
    has_new = False
    updated_dates = []

    for entry in new_entries:
        entry_date = entry['date']
        if entry_date in existing_dates:
            for i, item in enumerate(data['daily_data']):
                if item['date'] == entry_date:
                    has_total_change = item['total'] != entry['total']
                    has_better_details = len(entry.get('lines', {})) > len(item.get('lines', {}))
                    if has_total_change or has_better_details:
                        data['daily_data'][i] = entry
                        if has_total_change:
                            print(f"数据有变，更新: {entry_date} ({item['total']} → {entry['total']})")
                        else:
                            print(f"线路明细已补齐: {entry_date}")
                        has_new = True
                        updated_dates.append(entry_date)
                    break
        else:
            data['daily_data'].append(entry)
            print(f"添加新数据: {entry_date} - {entry['total']}万")
            has_new = True
            updated_dates.append(entry_date)

    if has_new:
        data['daily_data'].sort(key=lambda x: x['date'])
        data['metadata']['last_updated'] = datetime.now().strftime('%Y-%m-%d')
        data['metadata']['fetched_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if source_name:
            data['metadata']['data_source'] = source_name

        write_json_atomic(METRO_DATA_PATH, data)

        print(f"数据已保存到 metro_data.json")
        return updated_dates
    else:
        print("数据源尚未更新，暂无新数据")
        return []


def load_metro_data():
    """加载 metro_data.json"""
    try:
        with open(METRO_DATA_PATH, 'r') as f:
            data = json.load(f)
        return {item['date']: item for item in data['daily_data']}
    except Exception as e:
        print(f"加载 metro_data.json 失败: {e}")
        return {}


def validate_metro_dataset(path=METRO_DATA_PATH, reference_date=None):
    """发布前验证日期、总量、线路完整性和线路合计。"""
    errors = []
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            payload = json.load(handle)
    except Exception as error:
        print(f"[数据校验失败] 无法读取 {path}: {error}")
        return False

    rows = payload.get('daily_data') if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        print("[数据校验失败] daily_data 为空或格式错误")
        return False

    dates = []
    seen_dates = set()
    today = reference_date or date.today()
    for index, item in enumerate(rows):
        if not isinstance(item, dict):
            errors.append(f"第 {index + 1} 条记录不是对象")
            continue

        date_string = item.get('date')
        try:
            item_date = datetime.strptime(date_string, '%Y-%m-%d').date()
        except (TypeError, ValueError):
            errors.append(f"第 {index + 1} 条日期无效: {date_string!r}")
            continue

        dates.append(date_string)
        if date_string in seen_dates:
            errors.append(f"日期重复: {date_string}")
        seen_dates.add(date_string)
        if item_date > today:
            errors.append(f"存在未来日期: {date_string}")

        try:
            total = float(item.get('total'))
        except (TypeError, ValueError):
            errors.append(f"{date_string} 总客流不是数字")
            continue
        if not 0 < total < 1000:
            errors.append(f"{date_string} 总客流超出合理范围: {total}")

        lines = item.get('lines')
        if not isinstance(lines, dict):
            errors.append(f"{date_string} 线路数据格式错误")
            continue
        pending_details = '线路明细待补' in str(item.get('note', ''))
        if not lines and pending_details:
            continue
        if len(lines) < MINIMUM_COMPLETE_LINE_COUNT:
            errors.append(f"{date_string} 仅有 {len(lines)} 条线路状态")
            continue
        try:
            line_total = sum(float(value) for value in lines.values())
        except (TypeError, ValueError):
            errors.append(f"{date_string} 包含非数字线路客流")
            continue
        difference = round(total - line_total, 2)
        if abs(difference) > MAXIMUM_TOTAL_LINE_DIFFERENCE:
            errors.append(f"{date_string} 总量与线路合计相差 {difference}万")

    if dates != sorted(dates):
        errors.append("daily_data 未按日期升序排列")

    if errors:
        for error in errors[:20]:
            print(f"[数据校验失败] {error}")
        if len(errors) > 20:
            print(f"[数据校验失败] 另有 {len(errors) - 20} 个错误未显示")
        return False

    print(f"[数据校验] {len(rows)} 条记录通过，最新日期 {dates[-1]}")
    return True


def required_data_date(reference_date=None):
    """读取 CI 要求的数据日期；本地默认不强制昨日必须发布。"""
    explicit_date = os.environ.get('METRO_EXPECT_DATE')
    if explicit_date:
        return datetime.strptime(explicit_date, '%Y-%m-%d').date()
    require_yesterday = os.environ.get('METRO_REQUIRE_YESTERDAY', '').lower()
    if require_yesterday in {'1', 'true', 'yes'}:
        return (reference_date or date.today()) - timedelta(days=1)
    return None


def load_prediction_log():
    """加载 prediction_log.json"""
    try:
        with open(PREDICTION_LOG_PATH, 'r') as f:
            log = json.load(f)
    except FileNotFoundError:
        log = {}

    if not isinstance(log, dict):
        log = {}

    # 旧版文件将 predictions 初始化为数组；统一迁移为以日期为键的字典。
    if not isinstance(log.get('predictions'), dict):
        log['predictions'] = {}
    if not isinstance(log.get('comparison'), list):
        log['comparison'] = []
    if not isinstance(log.get('stats'), dict):
        log['stats'] = {}
    log['stats'].setdefault('total_comparisons', 0)
    log['stats'].setdefault('mean_absolute_error', None)
    log['stats'].setdefault('mean_bias', None)
    log['stats'].setdefault('last_updated', None)
    return log


def save_prediction_log(log):
    """保存 prediction_log.json"""
    write_json_atomic(PREDICTION_LOG_PATH, log)


def load_ml_forecasts():
    """读取独立机器学习模块上一轮写入的预测结果。"""
    try:
        with open(ML_PREDICTIONS_PATH, 'r') as f:
            payload = json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"读取机器学习预测失败: {e}")
        return {}

    forecasts = payload.get('forecasts', []) if isinstance(payload, dict) else []
    return {
        item['date']: item
        for item in forecasts
        if isinstance(item, dict) and item.get('date') and item.get('predicted_total') is not None
    }


def regenerate_ml_predictions():
    """训练独立模型并发布最新两天预测；失败时阻止发布不完整的数据。"""
    result = subprocess.run(
        [sys.executable, ML_PREDICTOR_PATH],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout.strip())
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr.strip())
        raise RuntimeError('机器学习预测模块执行失败，已停止发布此次数据更新')


def ml_predictions_need_refresh():
    """判断预测基准日是否落后于最新实际客流。"""
    metro_map = load_metro_data()
    if not metro_map:
        return False
    latest_date = max(metro_map)
    try:
        with open(ML_PREDICTIONS_PATH, 'r') as f:
            payload = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return True
    return payload.get('forecast_base_date') != latest_date


def validate_ml_predictions(path=ML_PREDICTIONS_PATH):
    """确认预测基准日与最新实际数据一致，且预测值有效。"""
    metro_map = load_metro_data()
    if not metro_map:
        print("[预测校验失败] 无法读取客流数据")
        return False
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            payload = json.load(handle)
    except Exception as error:
        print(f"[预测校验失败] 无法读取 {path}: {error}")
        return False

    latest_date = max(metro_map)
    if payload.get('forecast_base_date') != latest_date:
        print(
            f"[预测校验失败] 基准日 {payload.get('forecast_base_date')} "
            f"与最新数据 {latest_date} 不一致"
        )
        return False

    forecasts = payload.get('forecasts')
    if not isinstance(forecasts, list) or not forecasts:
        print("[预测校验失败] forecasts 为空或格式错误")
        return False
    line_models = payload.get('line_models', {})
    try:
        requires_line_forecasts = int(payload.get('schema_version', 1)) >= 2
    except (TypeError, ValueError):
        print("[预测校验失败] schema_version 格式错误")
        return False
    if requires_line_forecasts and (not isinstance(line_models, dict) or not line_models):
        print("[预测校验失败] schema v2 缺少线路模型")
        return False

    for forecast in forecasts:
        try:
            forecast_date = datetime.strptime(forecast['date'], '%Y-%m-%d').date()
            predicted_total = float(forecast['predicted_total'])
        except (KeyError, TypeError, ValueError) as error:
            print(f"[预测校验失败] 预测记录格式错误: {error}")
            return False
        if forecast_date <= datetime.strptime(latest_date, '%Y-%m-%d').date():
            print(f"[预测校验失败] 预测日期未晚于基准日: {forecast['date']}")
            return False
        if not 0 < predicted_total < 1000:
            print(f"[预测校验失败] 预测值超出合理范围: {predicted_total}")
            return False
        if requires_line_forecasts:
            line_forecasts = forecast.get('line_forecasts')
            if not isinstance(line_forecasts, dict) or set(line_forecasts) != set(line_models):
                print(f"[预测校验失败] {forecast['date']} 线路预测与线路模型不匹配")
                return False
            try:
                line_values = [float(item['predicted_flow']) for item in line_forecasts.values()]
                valid_intervals = all(
                    float(item['lower_bound']) <= float(item['predicted_flow']) <= float(item['upper_bound'])
                    for item in line_forecasts.values()
                )
            except (KeyError, TypeError, ValueError):
                print(f"[预测校验失败] {forecast['date']} 线路预测格式错误")
                return False
            if any(value < 0 or value >= 500 for value in line_values):
                print(f"[预测校验失败] {forecast['date']} 存在线路预测值超出合理范围")
                return False
            if not valid_intervals:
                print(f"[预测校验失败] {forecast['date']} 存在线路预测区间不包含预测值")
                return False
            line_sum = round(sum(line_values), 2)
            if abs(line_sum - round(predicted_total, 2)) > 0.01:
                print(
                    f"[预测校验失败] {forecast['date']} 线路合计 {line_sum} "
                    f"与线网预测 {predicted_total} 不一致"
                )
                return False

    line_summary = f"，{len(line_models)} 条线路独立模型" if requires_line_forecasts else ""
    print(f"[预测校验] 基准日 {latest_date}，共 {len(forecasts)} 条预测{line_summary}")
    return True


def date_str_to_weekday(date_str):
    """返回星期几（0=周一，6=周日）"""
    d = datetime.strptime(date_str, '%Y-%m-%d')
    return d.weekday()


# ============================================================
# 节假日感知预测模型 (v2)
# 基于历史同星期数据 × 节假日系数
# ============================================================

# 节假日定义: (开始日期, 结束日期, 类型, {星期:系数,...})
# 星期: 0=周一 ... 6=周六, 系数 = 实际客流 / 历史同星期均值
_HOLIDAY_DEFS = [
    # 清明前周末 (人们提前出行踏青)
    ('2026-03-28', '2026-03-29', '清明前周末', {5: 1.31, 6: 1.28}),
    # 春假 (中小学春假期间，出行增加)
    ('2026-04-01', '2026-04-02', '春假',      {0: 1.28, 1: 1.29, 2: 1.27, 3: 1.29, 4: 1.20}),
    # 清明假期 (三天法定假，高速公路免费，出行高峰)
    ('2026-04-03', '2026-04-06', '清明假期',  {0: 1.14, 4: 1.27, 5: 1.49, 6: 1.50}),
    # 清明后调休 (假期结束，部分人返程或继续出游，Sat/Sun 略低)
    ('2026-04-07', '2026-04-12', '清明后周末', {0: 1.11, 4: 1.07, 5: 1.06, 6: 0.98}),
]

# 单独标记的特例日期 (不在上述范围内但有明确历史记录)
_SPECIAL_DATE_FACTORS = {
    '2026-03-21': {5: 1.30, 6: 1.25},  # 清明前周六/日
    '2026-04-02': {3: 1.29},            # 春假周四 (4/2是春假不是普通周四)
}


def _get_holiday_factor(date_str):
    """返回指定日期的节假日系数（相对历史同星期均值）"""
    # 特例日期优先
    if date_str in _SPECIAL_DATE_FACTORS:
        factors = _SPECIAL_DATE_FACTORS[date_str]
        wd = datetime.strptime(date_str, '%Y-%m-%d').weekday()
        return factors.get(wd, 1.0)
    
    dt = datetime.strptime(date_str, '%Y-%m-%d').date()
    for start_str, end_str, name, factors in _HOLIDAY_DEFS:
        start = datetime.strptime(start_str, '%Y-%m-%d').date()
        end = datetime.strptime(end_str, '%Y-%m-%d').date()
        if start <= dt <= end:
            wd = dt.weekday()
            return factors.get(wd, 1.0)
    return 1.0


def _get_same_weekday_history(date_str, metro_map, count=8):
    """获取过去 N 周同星期的历史数据（去尾均值）"""
    values = []
    d = datetime.strptime(date_str, '%Y-%m-%d')
    target_weekday = d.weekday()

    cursor = d
    guard = 0
    while len(values) < count and guard < 365:
        cursor = cursor - timedelta(days=1)
        if cursor.weekday() == target_weekday:
            ds = cursor.strftime('%Y-%m-%d')
            if ds in metro_map:
                values.append(metro_map[ds]['total'])
        guard += 1

    return values


def baseline_predict(date_str, metro_map):
    """
    节假日感知预测：过去8周同星期去尾均值 × 节假日系数
    - 节假日期间人们出行增加，清明/春假期间客流显著高于平日
    - 节假日后首个周末通常略低于历史均值（部分人尚未返程）
    """
    history = _get_same_weekday_history(date_str, metro_map, count=8)
    if not history:
        return None
    
    # 去尾均值：去掉最高和最低，减少异常值影响
    if len(history) >= 4:
        sorted_h = sorted(history)
        middle = sorted_h[1:-1] if len(sorted_h) > 2 else sorted_h
        base = sum(middle) / len(middle)
    else:
        base = sum(history) / len(history)
    
    holiday_factor = _get_holiday_factor(date_str)
    return base * holiday_factor


def compare_and_log(newly_added_dates):
    """对比新到数据与预测，记录误差"""
    if not newly_added_dates:
        return

    metro_map = load_metro_data()
    log = load_prediction_log()
    ml_forecasts = load_ml_forecasts()

    for date_str in sorted(newly_added_dates):
        actual = metro_map.get(date_str)
        if not actual:
            continue
        actual_total = actual['total']

        # 获取预测值：优先用持久化的机器学习预测，缺失时回退到旧基线。
        predicted = None
        prediction_source = 'baseline-v2'
        if date_str in log['predictions']:
            predicted = log['predictions'][date_str].get('predicted_total')
            prediction_source = log['predictions'][date_str].get('model', prediction_source)
        elif date_str in ml_forecasts:
            forecast = ml_forecasts[date_str]
            predicted = forecast.get('predicted_total')
            prediction_source = 'ridge-regression-v1'
            log['predictions'][date_str] = {
                'predicted_total': predicted,
                'lower_bound': forecast.get('lower_bound'),
                'upper_bound': forecast.get('upper_bound'),
                'model': prediction_source,
                'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        else:
            predicted = baseline_predict(date_str, metro_map)

        if predicted is None:
            print(f"[对比] {date_str}: 无预测值，跳过")
            continue

        error = actual_total - predicted
        abs_error = abs(error)
        pct_error = error / predicted * 100 if predicted != 0 else 0

        entry = {
            'date': date_str,
            'actual': round(actual_total, 2),
            'predicted': round(predicted, 2),
            'error': round(error, 2),
            'abs_error': round(abs_error, 2),
            'pct_error': round(pct_error, 2),
            'weekday': date_str_to_weekday(date_str),
            'is_weekend': actual.get('is_weekend', False),
            'model': prediction_source,
            'compared_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        # 若官网修正同一天的数据，用新值覆盖旧评估，避免统计重复。
        log['comparison'] = [item for item in log['comparison'] if item.get('date') != date_str]
        log['comparison'].append(entry)

        # 更新统计
        errors = [c['error'] for c in log['comparison']]
        abs_errors = [c['abs_error'] for c in log['comparison']]
        n = len(errors)
        log['stats']['total_comparisons'] = n
        log['stats']['mean_absolute_error'] = round(sum(abs_errors) / n, 2)
        log['stats']['mean_bias'] = round(sum(errors) / n, 2)
        log['stats']['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        print(f"[对比] {date_str}: 实际={actual_total} | 预测={predicted:.1f} | 误差={error:+.1f} ({pct_error:+.1f}%)")

    save_prediction_log(log)

    # 输出统计摘要
    n = log['stats']['total_comparisons']
    mae = log['stats']['mean_absolute_error']
    bias = log['stats']['mean_bias']
    print(f"\n[预测评估] 共 {n} 条记录 | MAE={mae}万 | 平均偏差={bias:+.2f}万")

    # 检查是否需要模型重训练（MAE 超过阈值时提示）
    # v2节假日模型在正常日期MAE约10-20万，节假日期间可能达20-30万
    if n >= 7 and mae is not None and mae > 25:
        print(f"[警告] 连续 {n} 天 MAE={mae}万 偏高，建议重新训练模型")
        print(f"[提示] 在仪表盘刷新页面即可重新训练模型")
    elif n >= 7:
        print(f"[预测评估] 模型误差正常，无需特殊处理")


def is_transient_push_error(message):
    """判断 Git 推送失败是否属于值得重试的网络故障。"""
    normalized = message.lower()
    transient_markers = (
        'timed out',
        'operation timeout',
        'failed to connect',
        'could not resolve host',
        'connection reset',
        'recv failure',
        'remote end hung up',
        'http/2 stream',
        'tls connection',
    )
    return any(marker in normalized for marker in transient_markers)


def push_remote(remote, label, retry_delays=PUSH_RETRY_DELAYS):
    """推送单个远端；瞬时网络错误会有限重试。"""
    max_attempts = len(retry_delays) + 1
    for attempt in range(1, max_attempts + 1):
        result = subprocess.run(
            ['git', 'push', remote, 'main'],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            suffix = f"（第 {attempt} 次尝试）" if attempt > 1 else ""
            print(f"{label} 推送成功!{suffix}")
            return True

        error_message = (result.stderr or result.stdout).strip()
        can_retry = attempt < max_attempts and is_transient_push_error(error_message)
        if not can_retry:
            print(f"{label} 推送失败: {error_message}")
            return False

        delay = retry_delays[attempt - 1]
        print(
            f"{label} 推送第 {attempt}/{max_attempts} 次失败，"
            f"{delay} 秒后重试: {error_message}"
        )
        time.sleep(delay)

    return False


def commit_and_push_updates():
    """提交本地更新并同步 GitHub、Gitee。"""
    try:
        commit_msg = f"Auto update metro data - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        subprocess.run([
            'git', 'add',
            METRO_DATA_PATH,
            PREDICTION_LOG_PATH,
            ML_PREDICTIONS_PATH,
        ], cwd=REPO_DIR, check=True)
        subprocess.run(['git', 'commit', '-m', commit_msg], cwd=REPO_DIR, check=True)
    except Exception as error:
        print(f"Git 提交失败: {error}")
        return False

    push_succeeded = True
    for remote, label in [('origin', 'GitHub'), ('gitee', 'Gitee')]:
        if not push_remote(remote, label):
            push_succeeded = False
    return push_succeeded


def main():
    print(f"=== 南京地铁客流数据抓取 ===")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    expected_date = required_data_date()
    if expected_date:
        print(f"本次期望数据日期: {expected_date.isoformat()}")

    entries, source_name, successful_sources, reached_sources = fetch_passenger_flow_entries()
    widget_source = '南京地铁官方微博组件'
    if widget_source in reached_sources and widget_source not in successful_sources:
        print("官方微博组件已连接但未解析到任何完整客流记录，疑似页面格式变化。")
        return EXIT_DATA_INVALID
    if not successful_sources:
        if reached_sources:
            print(f"数据源已连接但内容无法解析: {', '.join(reached_sources)}")
            return EXIT_DATA_INVALID
        print("所有客流数据源均暂时无法访问。")
        return EXIT_SOURCE_UNAVAILABLE

    updated_dates = update_metro_data(entries, source_name=source_name) if entries else []
    if updated_dates:
        print("\n有新数据，更新预测与评估...")
        compare_and_log(updated_dates)
    else:
        print("官网已访问，当前没有新的客流明细。")

    if not validate_metro_dataset():
        return EXIT_DATA_INVALID

    prediction_refreshed = False
    if updated_dates or ml_predictions_need_refresh():
        try:
            regenerate_ml_predictions()
        except RuntimeError as error:
            print(error)
            return EXIT_DATA_INVALID
        prediction_refreshed = True

    if not validate_ml_predictions():
        return EXIT_DATA_INVALID

    expected_pending = bool(
        expected_date
        and expected_date.isoformat() not in load_metro_data()
    )
    if expected_pending:
        print(f"官网尚未发布 {expected_date.isoformat()} 客流，等待下一次重试。")

    if not updated_dates and not prediction_refreshed:
        print("数据和预测均为最新，无需发布。")
        return EXIT_DATA_PENDING if expected_pending else EXIT_SUCCESS

    if os.environ.get('METRO_SKIP_GIT') == '1':
        print("已设置 METRO_SKIP_GIT=1，跳过脚本内 Git 提交/推送。")
        return EXIT_DATA_PENDING if expected_pending else EXIT_SUCCESS

    if not commit_and_push_updates():
        return 1
    return EXIT_DATA_PENDING if expected_pending else EXIT_SUCCESS


if __name__ == '__main__':
    raise SystemExit(main())
