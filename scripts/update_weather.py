#!/usr/bin/env python3
"""Update Nanjing weather data and regenerate the published ML forecast."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
DEFAULT_WEATHER_PATH = REPO_DIR / "data" / "weather.json"
DEFAULT_METRO_PATH = REPO_DIR / "data" / "metro_data.json"
DEFAULT_PREDICTION_PATH = REPO_DIR / "data" / "ml_predictions.json"
ML_PREDICTOR_PATH = SCRIPT_DIR / "ml_predictor.py"

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
NANJING_LATITUDE = 32.06
NANJING_LONGITUDE = 118.79
TIMEZONE = "Asia/Shanghai"
DEFAULT_PAST_DAYS = 14
DEFAULT_FORECAST_DAYS = 7
RETRY_DELAYS = (5, 15)

EXIT_SUCCESS = 0
EXIT_SOURCE_UNAVAILABLE = 2
EXIT_DATA_INVALID = 4

DAILY_FIELDS = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "snowfall_sum",
    "wind_speed_10m_max",
)

# Official State Council holiday periods. Update this table when a new annual
# holiday notice is published; unknown years remain unmarked rather than guessed.
HOLIDAY_PERIODS = (
    ("2025-01-01", "2025-01-01", "元旦"),
    ("2025-01-28", "2025-02-04", "春节"),
    ("2025-04-04", "2025-04-06", "清明节"),
    ("2025-05-01", "2025-05-05", "劳动节"),
    ("2025-05-31", "2025-06-02", "端午节"),
    ("2025-10-01", "2025-10-08", "国庆节、中秋节"),
    ("2026-01-01", "2026-01-03", "元旦"),
    ("2026-02-15", "2026-02-23", "春节"),
    ("2026-04-04", "2026-04-06", "清明节"),
    ("2026-05-01", "2026-05-05", "劳动节"),
    ("2026-06-19", "2026-06-21", "端午节"),
    ("2026-09-25", "2026-09-27", "中秋节"),
    ("2026-10-01", "2026-10-07", "国庆节"),
)
KNOWN_CALENDAR_YEARS = {2025, 2026}

RAIN_CODES = {
    51, 53, 55, 56, 57,
    61, 63, 65, 66, 67,
    80, 81, 82,
    95, 96, 99,
}
HEAVY_RAIN_CODES = {55, 57, 65, 67, 82, 96, 99}
SNOW_CODES = {71, 73, 75, 77, 85, 86}


class WeatherSourceError(RuntimeError):
    """The remote weather source could not be reached."""


class WeatherDataError(ValueError):
    """The weather response or local dataset is structurally invalid."""


def date_strings(start: str, end: str) -> list[str]:
    current = date.fromisoformat(start)
    final = date.fromisoformat(end)
    values = []
    while current <= final:
        values.append(current.isoformat())
        current += timedelta(days=1)
    return values


HOLIDAY_NAMES = {
    value: name
    for start, end, name in HOLIDAY_PERIODS
    for value in date_strings(start, end)
}
HOLIDAY_STARTS = {start for start, _, _ in HOLIDAY_PERIODS}


def calendar_flags(date_string: str) -> tuple[bool, bool]:
    """Return official holiday and holiday-eve flags for known calendar years."""
    current = date.fromisoformat(date_string)
    is_holiday = date_string in HOLIDAY_NAMES
    tomorrow = (current + timedelta(days=1)).isoformat()
    is_holiday_eve = not is_holiday and tomorrow in HOLIDAY_STARTS
    return is_holiday, is_holiday_eve


def weather_label(code: int) -> str:
    if code == 0:
        return "晴"
    if code in {1, 2, 3}:
        return "多云"
    if code in {45, 48}:
        return "雾"
    if code in {51, 53, 55}:
        return "毛毛雨"
    if code in {56, 57, 66, 67}:
        return "冻雨"
    if code in {61, 63, 65}:
        return "雨"
    if code in {71, 73, 75, 77}:
        return "雪"
    if code in {80, 81, 82}:
        return "阵雨"
    if code in {85, 86}:
        return "阵雪"
    if code in {95, 96, 99}:
        return "雷暴"
    return "未知"


def as_float(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise WeatherDataError(f"{field} 不是有效数字: {value!r}") from error
    if not math.isfinite(number):
        raise WeatherDataError(f"{field} 不是有限数字: {value!r}")
    return number


def as_weather_code(value: Any) -> int:
    number = as_float(value, "weather_code")
    if not number.is_integer():
        raise WeatherDataError(f"weather_code 必须是整数: {value!r}")
    code = int(number)
    if not 0 <= code <= 99:
        raise WeatherDataError(f"weather_code 超出合理范围: {code}")
    return code


def build_api_url(past_days: int, forecast_days: int) -> str:
    params = {
        "latitude": NANJING_LATITUDE,
        "longitude": NANJING_LONGITUDE,
        "daily": ",".join(DAILY_FIELDS),
        "timezone": TIMEZONE,
        "past_days": past_days,
        "forecast_days": forecast_days,
    }
    return f"{OPEN_METEO_URL}?{urlencode(params)}"


def fetch_forecast(past_days: int, forecast_days: int, attempts: int = 3) -> dict[str, Any]:
    url = build_api_url(past_days, forecast_days)
    max_attempts = max(1, attempts)
    for attempt in range(1, max_attempts + 1):
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "nanjing-metro-dashboard/1.0",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise WeatherDataError("Open-Meteo 返回值不是 JSON 对象")
            if payload.get("error"):
                raise WeatherDataError(f"Open-Meteo 拒绝请求: {payload.get('reason', '未知原因')}")
            return payload
        except WeatherDataError:
            raise
        except Exception as error:
            if attempt >= max_attempts:
                raise WeatherSourceError(f"Open-Meteo 请求失败: {error}") from error
            delay = RETRY_DELAYS[min(attempt - 1, len(RETRY_DELAYS) - 1)]
            print(f"Open-Meteo 第 {attempt}/{max_attempts} 次请求失败，{delay} 秒后重试: {error}")
            time.sleep(delay)
    raise WeatherSourceError("Open-Meteo 请求失败")


def parse_forecast(
    payload: dict[str, Any], required_tail: int | None = None
) -> list[dict[str, Any]]:
    daily = payload.get("daily")
    if not isinstance(daily, dict):
        raise WeatherDataError("Open-Meteo 响应缺少 daily 对象")

    required = ("time",) + DAILY_FIELDS
    arrays = {}
    for field in required:
        values = daily.get(field)
        if not isinstance(values, list):
            raise WeatherDataError(f"Open-Meteo 响应缺少 {field} 数组")
        arrays[field] = values

    lengths = {len(values) for values in arrays.values()}
    if len(lengths) != 1 or not lengths or next(iter(lengths)) == 0:
        raise WeatherDataError("Open-Meteo 日数据数组长度不一致或为空")

    record_count = next(iter(lengths))
    if required_tail is not None and not 1 <= required_tail <= record_count:
        raise WeatherDataError("必须完整保留的预报天数超出接口返回范围")

    records = []
    skipped_dates = []
    for index, date_string in enumerate(arrays["time"]):
        try:
            date.fromisoformat(date_string)
        except (TypeError, ValueError) as error:
            raise WeatherDataError(f"Open-Meteo 返回无效日期: {date_string!r}") from error

        try:
            code = as_weather_code(arrays["weather_code"][index])
            temp_max = as_float(arrays["temperature_2m_max"][index], "temperature_2m_max")
            temp_min = as_float(arrays["temperature_2m_min"][index], "temperature_2m_min")
            precipitation = max(
                0.0,
                as_float(arrays["precipitation_sum"][index], "precipitation_sum"),
            )
            snowfall = max(0.0, as_float(arrays["snowfall_sum"][index], "snowfall_sum"))
            wind_speed = max(
                0.0,
                as_float(arrays["wind_speed_10m_max"][index], "wind_speed_10m_max"),
            )
        except WeatherDataError:
            is_required_forecast = (
                required_tail is None or index >= record_count - required_tail
            )
            if is_required_forecast:
                raise
            skipped_dates.append(date_string)
            continue
        if not -80 <= temp_min <= temp_max <= 60:
            raise WeatherDataError(
                f"{date_string} 温度超出合理范围或高低温倒置: {temp_min} 至 {temp_max}"
            )

        is_holiday, is_holiday_eve = calendar_flags(date_string)
        is_rainy = code in RAIN_CODES
        records.append({
            "date": date_string,
            "temp_max": round(temp_max, 1),
            "temp_min": round(temp_min, 1),
            "weather": weather_label(code),
            "precipitation": round(precipitation, 1),
            "weather_code": code,
            "wind": f"{wind_speed:.1f} km/h",
            "wind_speed_max": round(wind_speed, 1),
            "aqi": 0,
            "is_rainy": is_rainy,
            "is_heavy_rain": is_rainy and (
                code in HEAVY_RAIN_CODES or precipitation >= 15.0
            ),
            "is_snow": code in SNOW_CODES or snowfall > 0,
            "is_holiday": is_holiday,
            "is_holiday_eve": is_holiday_eve,
        })
    if skipped_dates:
        print(f"跳过 {len(skipped_dates)} 个不完整历史天气日: {', '.join(skipped_dates)}")
    if not records:
        raise WeatherDataError("Open-Meteo 没有返回可用日数据")
    return records


def load_weather(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        raise WeatherDataError(f"无法读取 {path}: {error}") from error
    if not isinstance(payload, list):
        raise WeatherDataError(f"{path} 必须是数组")
    return payload


def merge_weather(
    existing: list[dict[str, Any]], incoming: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    records: dict[str, dict[str, Any]] = {}
    for item in existing:
        if not isinstance(item, dict) or not isinstance(item.get("date"), str):
            raise WeatherDataError("现有天气数据包含无效记录")
        date.fromisoformat(item["date"])
        if item["date"] in records:
            raise WeatherDataError(f"现有天气数据日期重复: {item['date']}")
        records[item["date"]] = dict(item)

    before = {key: dict(value) for key, value in records.items()}
    for item in incoming:
        date_string = item["date"]
        records[date_string] = {**records.get(date_string, {}), **item}

    # Repair deterministic fields written by earlier updater versions.
    for date_string, item in records.items():
        code_value = item.get("weather_code")
        if code_value is not None:
            code = as_weather_code(code_value)
            precipitation = as_float(item.get("precipitation", 0), "precipitation")
            item["weather"] = weather_label(code)
            item["is_rainy"] = code in RAIN_CODES
            item["is_heavy_rain"] = item["is_rainy"] and (
                code in HEAVY_RAIN_CODES or precipitation >= 15.0
            )
            item["is_snow"] = code in SNOW_CODES
        if date.fromisoformat(date_string).year not in KNOWN_CALENDAR_YEARS:
            continue
        item["is_holiday"], item["is_holiday_eve"] = calendar_flags(date_string)

    changed_dates = sorted(
        date_string
        for date_string in set(before) | set(records)
        if before.get(date_string) != records.get(date_string)
    )
    return [records[key] for key in sorted(records)], changed_dates


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            temporary_path = Path(handle.name)
        temporary_path.replace(path)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def latest_metro_date(path: Path) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload["daily_data"]
        return max(item["date"] for item in rows)
    except Exception as error:
        raise WeatherDataError(f"无法确定最新客流日期: {error}") from error


def predictions_need_refresh(
    prediction_path: Path, metro_path: Path, weather_dates: set[str]
) -> bool:
    if not prediction_path.exists():
        return True
    try:
        payload = json.loads(prediction_path.read_text(encoding="utf-8"))
        if payload.get("forecast_base_date") != latest_metro_date(metro_path):
            return True
        forecasts = payload["forecasts"]
        if not forecasts:
            return True
        return any(
            forecast.get("date") in weather_dates
            and forecast.get("inputs", {}).get("weather_source") != "weather_file"
            for forecast in forecasts
        )
    except Exception:
        return True


def regenerate_predictions(weather_path: Path, metro_path: Path, output_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ML_PREDICTOR_PATH),
            "--weather-data",
            str(weather_path),
            "--metro-data",
            str(metro_path),
            "--output",
            str(output_path),
        ],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout.strip())
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr.strip())
        raise WeatherDataError("天气更新后重新训练预测模型失败")


def validate_predictions(
    prediction_path: Path, metro_path: Path, weather_dates: set[str]
) -> None:
    try:
        payload = json.loads(prediction_path.read_text(encoding="utf-8"))
        forecasts = payload["forecasts"]
    except Exception as error:
        raise WeatherDataError(f"无法读取预测文件: {error}") from error
    if payload.get("forecast_base_date") != latest_metro_date(metro_path):
        raise WeatherDataError("预测基准日与最新客流日期不一致")
    if not isinstance(forecasts, list) or not forecasts:
        raise WeatherDataError("预测文件没有未来预测")
    for forecast in forecasts:
        if forecast.get("date") not in weather_dates:
            raise WeatherDataError(f"{forecast.get('date')} 缺少精确天气预报")
        if forecast.get("inputs", {}).get("weather_source") != "weather_file":
            raise WeatherDataError(f"{forecast.get('date')} 未使用精确天气预报")
        if round(float(forecast["predicted_total"]), 2) != round(
            float(forecast["line_forecast_sum"]), 2
        ):
            raise WeatherDataError(f"{forecast.get('date')} 线路预测合计不一致")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="更新南京天气并重新生成客流预测")
    parser.add_argument("--weather-data", type=Path, default=DEFAULT_WEATHER_PATH)
    parser.add_argument("--metro-data", type=Path, default=DEFAULT_METRO_PATH)
    parser.add_argument("--prediction-output", type=Path, default=DEFAULT_PREDICTION_PATH)
    parser.add_argument("--past-days", type=int, default=DEFAULT_PAST_DAYS)
    parser.add_argument("--forecast-days", type=int, default=DEFAULT_FORECAST_DAYS)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--skip-prediction", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    if not 0 <= args.past_days <= 92:
        print("past-days 必须在 0 至 92 之间")
        return EXIT_DATA_INVALID
    if not 1 <= args.forecast_days <= 16:
        print("forecast-days 必须在 1 至 16 之间")
        return EXIT_DATA_INVALID
    if not 1 <= args.attempts <= 5:
        print("attempts 必须在 1 至 5 之间")
        return EXIT_DATA_INVALID

    try:
        payload = fetch_forecast(args.past_days, args.forecast_days, args.attempts)
        incoming = parse_forecast(payload, required_tail=args.forecast_days)
        existing = load_weather(args.weather_data)
        merged, changed_dates = merge_weather(existing, incoming)
        weather_dates = {item["date"] for item in merged}
        if args.dry_run:
            print(
                f"天气数据检查通过: 接口返回 {len(incoming)} 天，"
                f"将变更 {len(changed_dates)} 天，范围 {incoming[0]['date']} 至 {incoming[-1]['date']}"
            )
            return EXIT_SUCCESS

        if changed_dates:
            write_json_atomic(args.weather_data, merged)
            print(
                f"天气数据已更新: {len(changed_dates)} 天发生变化，"
                f"当前范围 {merged[0]['date']} 至 {merged[-1]['date']}"
            )
        else:
            print("天气数据已是最新，无字段变化")

        needs_prediction = changed_dates or predictions_need_refresh(
            args.prediction_output, args.metro_data, weather_dates
        )
        if needs_prediction and not args.skip_prediction:
            regenerate_predictions(args.weather_data, args.metro_data, args.prediction_output)
            validate_predictions(args.prediction_output, args.metro_data, weather_dates)
            print("天气驱动的机器学习预测已重新生成并通过校验")
        elif args.skip_prediction:
            print("已设置 --skip-prediction，跳过机器学习预测更新")
        else:
            print("机器学习预测已使用最新天气，无需重新生成")
        return EXIT_SUCCESS
    except WeatherSourceError as error:
        print(error)
        return EXIT_SOURCE_UNAVAILABLE
    except WeatherDataError as error:
        print(f"天气更新失败: {error}")
        return EXIT_DATA_INVALID
    except Exception as error:
        print(f"天气更新出现未预期错误: {error}")
        return EXIT_DATA_INVALID


if __name__ == "__main__":
    raise SystemExit(main())
