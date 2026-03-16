#!/bin/bash
cd /Users/zhuzhiwei/nanjing-metro-dashboard

python3 << 'PYEOF'
import requests
import json
from datetime import datetime, timedelta

# 中国节假日（2025-2026年）
holidays = {
    "2025-01-01": "元旦",
    "2025-01-28": "春节",
    "2025-01-29": "春节",
    "2025-01-30": "春节",
    "2025-01-31": "春节",
    "2025-02-01": "春节",
    "2025-02-02": "春节",
    "2025-02-03": "春节",
    "2025-02-04": "春节",
    "2025-04-04": "清明节",
    "2025-04-05": "清明节",
    "2025-04-06": "清明节",
    "2025-05-01": "劳动节",
    "2025-05-02": "劳动节",
    "2025-05-03": "劳动节",
    "2025-05-04": "劳动节",
    "2025-05-05": "劳动节",
    "2025-06-09": "端午节",
    "2025-06-10": "端午节",
    "2025-09-15": "中秋节",
    "2025-09-16": "中秋节",
    "2025-09-17": "中秋节",
    "2025-10-01": "国庆节",
    "2025-10-02": "国庆节",
    "2025-10-03": "国庆节",
    "2025-10-04": "国庆节",
    "2025-10-05": "国庆节",
    "2025-10-06": "国庆节",
    "2025-10-07": "国庆节",
    "2026-01-01": "元旦",
    "2026-01-28": "春节",
    "2026-01-29": "春节",
    "2026-01-30": "春节",
    "2026-01-31": "春节",
    "2026-02-01": "春节",
    "2026-02-02": "春节",
    "2026-02-03": "春节",
    "2026-02-04": "春节",
    "2026-04-04": "清明节",
    "2026-04-05": "清明节",
    "2026-04-06": "清明节",
    "2026-05-01": "劳动节",
    "2026-05-02": "劳动节",
    "2026-05-03": "劳动节",
    "2026-05-04": "劳动节",
    "2026-05-05": "劳动节",
}

# 判断节假日前一天
def is_holiday_eve(date_str, holidays):
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    tomorrow = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
    return tomorrow in holidays

# 获取天气预报
url = "https://api.open-meteo.com/v1/forecast"
params = {
    "latitude": 32.06,
    "longitude": 118.79,
    "daily": "weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum",
    "timezone": "Asia/Shanghai",
    "forecast_days": 2
}

resp = requests.get(url, params=params)
data = resp.json()

dates = data["daily"]["time"]
codes = data["daily"]["weathercode"]
max_temps = data["daily"]["temperature_2m_max"]
min_temps = data["daily"]["temperature_2m_min"]
precip = data["daily"]["precipitation_sum"]

def get_weather(code):
    if code == 0: return "晴"
    elif code <= 3: return "多云"
    elif code <= 48: return "雾"
    elif code <= 67: return "雨"
    elif code <= 77: return "雪"
    else: return "雷暴"

# 读取现有数据
with open('data/weather.json', 'r', encoding='utf-8') as f:
    weather = json.load(f)

existing_dates = {w['date'] for w in weather}

# 添加或更新
for i in range(2):
    date = dates[i]
    is_holiday = date in holidays
    is_eve = is_holiday_eve(date, holidays)
    
    w = {
        "date": date,
        "temp_max": max_temps[i],
        "temp_min": min_temps[i],
        "weather": get_weather(codes[i]),
        "precipitation": precip[i],
        "weather_code": codes[i],
        "wind": "未知",
        "aqi": 0,
        "is_rainy": codes[i] >= 51,
        "is_heavy_rain": codes[i] >= 61,
        "is_snow": codes[i] >= 71,
        "is_holiday": is_holiday,
        "is_holiday_eve": is_eve
    }
    
    if date not in existing_dates:
        weather.append(w)
    else:
        for j, old in enumerate(weather):
            if old['date'] == date:
                weather[j] = w
                break

with open('data/weather.json', 'w', encoding='utf-8') as f:
    json.dump(weather, f, ensure_ascii=False, indent=2)

print(f"已更新天气数据: {dates}")
print(f"添加节假日字段完成")
PYEOF
