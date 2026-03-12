#!/bin/bash
# 南京地铁每日数据更新脚本
# 每天早上10点执行

# 设置工作目录
PROJECT_DIR="/Users/zhuzhiwei/项目/nanjing-metro-dashboard"
cd "$PROJECT_DIR"

# 检查虚拟环境或直接执行
if [ -f "venv/bin/python" ]; then
    PYTHON_CMD="venv/bin/python"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    echo "未找到Python解释器"
    exit 1
fi

# 执行数据更新脚本
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始执行南京地铁数据更新"

# 抓取昨日客流原文并解析
if [ -f "weibo_cookie.txt" ]; then
    $PYTHON_CMD weibo_yesterday_fetcher.py --cookie-file weibo_cookie.txt
    # 将解析结果写入 metro_data.json（同时更新 data / daily_data / last_updated）
    $PYTHON_CMD - <<'PY'
import json
from weibo_yesterday_fetcher import parse_metro_text

raw_path = "data/weibo_raw.txt"
metro_path = "data/metro_data.json"

with open(raw_path, "r", encoding="utf-8") as f:
    raw = f.read().strip()

parsed = parse_metro_text(raw)

with open(metro_path, "r", encoding="utf-8") as f:
    data = json.load(f)

def upsert(lst, item):
    for i, it in enumerate(lst):
        if it.get("date") == item.get("date"):
            lst[i] = item
            return
    lst.insert(0, item)

data.setdefault("data", [])
data.setdefault("daily_data", [])

upsert(data["data"], parsed)
upsert(data["daily_data"], parsed)

data.setdefault("metadata", {})
data["metadata"]["last_updated"] = parsed["date"]
data["metadata"]["fetched_at"] = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")

with open(metro_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
PY
else
    echo "未找到 weibo_cookie.txt，跳过微博原文抓取"
fi

$PYTHON_CMD enhanced_auto_update.py

if [ $? -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 数据更新完成"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 数据更新失败"
fi
