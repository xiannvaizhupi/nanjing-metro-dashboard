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
from html import unescape
from datetime import datetime, date, timedelta
from urllib.request import Request, urlopen

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
METRO_DATA_PATH = os.path.join(REPO_DIR, 'data', 'metro_data.json')
PREDICTION_LOG_PATH = os.path.join(REPO_DIR, 'data', 'prediction_log.json')

OFFICIAL_HOMEPAGE_URL = "https://www.njmetro.com.cn/njdtweb/gx/dtmain.jsp"
OFFICIAL_ROOT_URL = "https://www.njmetro.com.cn/"
WEIBO_WIDGET_URL = "https://widget.weibo.com/weiboshow/index.php?language=&width=0&height=430&fansRow=1&ptype=1&speed=0&skin=1&isTitle=1&noborder=1&isWeibo=1&isFans=0&uid=2638276292&verifier=138e3b0a&dpc=1"

FETCH_SOURCES = [
    ("南京地铁官网首页", OFFICIAL_HOMEPAGE_URL),
    ("南京地铁官网根页", OFFICIAL_ROOT_URL),
    ("南京地铁官方微博组件", WEIBO_WIDGET_URL),
]

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

NEXT_ENTRY_PATTERN = (
    r'(?:(?:\d{2,4})[-/.年](?:\d{1,2})[-/.月](?:\d{1,2})[日号]?)?'
    r'(?:#?昨日客流#?.{0,80}?)?'
    r'南京地铁(?:\d{2,4}年)?\d{1,2}月\d{1,2}日客运量'
)

FLOW_ENTRY_PATTERN = re.compile(
    r'(?:(\d{2,4})[-/.年](\d{1,2})[-/.月](\d{1,2})[日号]?)?'
    r'(?:#?昨日客流#?.{0,80}?)?'
    r'南京地铁(?:(\d{2,4})年)?(?:(\d{1,2})月)?(\d{1,2})日客运量(?:为)?[：:]?(\d+\.?\d*)万?'
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


def fetch_url(source_name, url):
    """抓取指定来源页面。SSL 失败时自动降级到未验证模式（macOS Python 常见证书问题）。"""
    try:
        req = Request(url, headers=HTTP_HEADERS)
        response = urlopen(req, timeout=30)
        return decode_response(response)
    except ssl.SSLError as e:
        # 兜底：跳过证书验证（南京地铁官网 + 部分内网环境常见）
        print(f"  [SSL] {source_name} 证书校验失败，降级到未验证模式: {e}")
        try:
            ctx = ssl._create_unverified_context()
            req = Request(url, headers=HTTP_HEADERS)
            response = urlopen(req, timeout=30, context=ctx)
            return decode_response(response)
        except Exception as e2:
            print(f"获取{source_name}失败: {e2}")
            return None
    except Exception as e:
        print(f"获取{source_name}失败: {e}")
        return None


def fetch_weibo_data():
    """从南京地铁官方微博组件获取数据。保留给旧测试或手动调用。"""
    return fetch_url("南京地铁官方微博组件", WEIBO_WIDGET_URL)


def fetch_passenger_flow_entries():
    """按优先级抓取并解析客流数据。任一来源出错不影响其他来源继续尝试。"""
    for source_name, url in FETCH_SOURCES:
        try:
            html = fetch_url(source_name, url)
        except Exception as e:
            print(f"获取{source_name}异常: {e}")
            continue

        if not html:
            continue

        try:
            entries = parse_passenger_flow(html, source_name=source_name)
        except Exception as e:
            print(f"{source_name} 解析异常: {e}")
            continue

        if entries:
            print(f"使用数据源: {source_name}")
            return entries, source_name

        print(f"{source_name}未解析到客流数据，尝试下一个来源。")

    return [], None


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
                # 拒绝未来日期（> ref）
                if candidate > ref:
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

        if len(lines) < 8:
            print(f"跳过疑似不完整数据: {date_str}，仅解析到 {len(lines)} 条线路")
            continue

        d = date(year, month, day)
        is_weekend = d.weekday() >= 5

        results.append({
            'date': date_str,
            'total': total,
            'is_weekend': is_weekend,
            'note': '',
            'lines': lines
        })
        seen_dates.add(date_str)

        source_label = f"[{source_name}]" if source_name else ""
        print(f"解析{source_label}: {date_str} - {total}万")

    return results


def parse_weibo_flow(html):
    """兼容旧调用名：解析微博或官网客流文本。"""
    return parse_passenger_flow(html, source_name='南京地铁官方微博组件')


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
    newly_added_dates = []

    for entry in new_entries:
        entry_date = entry['date']
        if entry_date in existing_dates:
            for i, item in enumerate(data['daily_data']):
                if item['date'] == entry_date:
                    if item['total'] != entry['total']:
                        data['daily_data'][i] = entry
                        print(f"数据有变，更新: {entry_date} ({item['total']} → {entry['total']})")
                        has_new = True
                    break
        else:
            data['daily_data'].append(entry)
            print(f"添加新数据: {entry_date} - {entry['total']}万")
            has_new = True
            newly_added_dates.append(entry_date)

    if has_new:
        data['daily_data'].sort(key=lambda x: x['date'])
        data['metadata']['last_updated'] = datetime.now().strftime('%Y-%m-%d')
        data['metadata']['fetched_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if source_name:
            data['metadata']['data_source'] = source_name

        with open(METRO_DATA_PATH, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"数据已保存到 metro_data.json")
        return newly_added_dates
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


def load_prediction_log():
    """加载 prediction_log.json"""
    try:
        with open(PREDICTION_LOG_PATH, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            'predictions': {},
            'comparison': [],
            'stats': {
                'total_comparisons': 0,
                'mean_absolute_error': None,
                'mean_bias': None,
                'last_updated': None
            }
        }


def save_prediction_log(log):
    """保存 prediction_log.json"""
    with open(PREDICTION_LOG_PATH, 'w') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


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

    for date_str in sorted(newly_added_dates):
        actual = metro_map.get(date_str)
        if not actual:
            continue
        actual_total = actual['total']

        # 获取预测值（优先用记录的预测，否则用基线）
        predicted = None
        if date_str in log['predictions']:
            predicted = log['predictions'][date_str].get('predicted_total')
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
            'compared_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

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


def main():
    import subprocess

    print(f"=== 南京地铁客流数据抓取 ===")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    entries, source_name = fetch_passenger_flow_entries()

    if entries:
        newly_added = update_metro_data(entries, source_name=source_name)

        if newly_added:
            print("\n有新数据，准备推送...")

            # 预测对比
            compare_and_log(newly_added)

            if os.environ.get('METRO_SKIP_GIT') == '1':
                print("已设置 METRO_SKIP_GIT=1，跳过脚本内 Git 提交/推送。")
                return

            # Git 推送（同时推送到 GitHub 和 Gitee）
            try:
                commit_msg = f"Auto update metro data - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

                subprocess.run(['git', 'add', '.'], cwd=REPO_DIR, check=True)
                subprocess.run(['git', 'commit', '-m', commit_msg], cwd=REPO_DIR, check=True)
                
                # 推送到 GitHub
                result_origin = subprocess.run(['git', 'push', 'origin', 'main'], cwd=REPO_DIR, capture_output=True, text=True)
                if result_origin.returncode == 0:
                    print("GitHub 推送成功!")
                else:
                    print(f"GitHub 推送失败: {result_origin.stderr}")
                
                # 推送到 Gitee（Gitee Pages 用）
                result_gitee = subprocess.run(['git', 'push', 'gitee', 'main'], cwd=REPO_DIR, capture_output=True, text=True)
                if result_gitee.returncode == 0:
                    print("Gitee 推送成功!")
                else:
                    print(f"Gitee 推送失败: {result_gitee.stderr}")
            except Exception as e:
                print(f"Git 操作失败: {e}")
        else:
            print("无新数据，退出。")
    else:
        print("未解析到客流数据，退出。可稍后手动重试或等待 GitHub Actions 云端任务。")


if __name__ == '__main__':
    main()
