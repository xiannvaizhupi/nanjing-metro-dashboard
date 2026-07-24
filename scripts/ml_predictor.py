#!/usr/bin/env python3
"""Train and publish a standalone Nanjing Metro passenger-flow ML forecast.

The module intentionally uses only the Python standard library so the same
training and forecasting path works on a laptop and in GitHub Actions.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
DEFAULT_METRO_DATA_PATH = REPO_DIR / "data" / "metro_data.json"
DEFAULT_WEATHER_DATA_PATH = REPO_DIR / "data" / "weather.json"
DEFAULT_OUTPUT_PATH = REPO_DIR / "data" / "ml_predictions.json"

MODEL_NAME = "ridge-regression"
MODEL_VERSION = "1.2.0"
RIDGE_ALPHAS = (0.1, 1.0, 10.0, 50.0, 100.0, 300.0, 500.0, 1000.0)
ENSEMBLE_BASELINE_WEIGHTS = (0.0, 0.1, 0.2, 0.25, 0.3, 0.4, 0.5)
MIN_TRAINING_ROWS = 60
SERVICE_DISRUPTION_MARKERS = ("停运", "运营中断")


@dataclass
class TrainingRow:
    date: str
    features: list[float]
    target: float
    seasonal_baseline: float


class RidgeRegressor:
    """Small ridge-regression implementation with feature standardization."""

    def __init__(self, alpha: float) -> None:
        self.alpha = alpha
        self.means: list[float] = []
        self.scales: list[float] = []
        self.weights: list[float] = []

    def fit(self, rows: list[TrainingRow]) -> "RidgeRegressor":
        if len(rows) < 2:
            raise ValueError("训练数据不足，至少需要 2 条样本")

        feature_count = len(rows[0].features)
        if any(len(row.features) != feature_count for row in rows):
            raise ValueError("训练特征长度不一致")

        self.means = [0.0] * feature_count
        self.scales = [1.0] * feature_count
        for column in range(1, feature_count):
            values = [row.features[column] for row in rows]
            mean = sum(values) / len(values)
            variance = sum((value - mean) ** 2 for value in values) / len(values)
            self.means[column] = mean
            self.scales[column] = math.sqrt(variance) or 1.0

        standardized = [self._standardize(row.features) for row in rows]
        normal = [[0.0] * feature_count for _ in range(feature_count)]
        target_vector = [0.0] * feature_count
        for row, target_row in zip(standardized, rows):
            for i in range(feature_count):
                target_vector[i] += row[i] * target_row.target
                for j in range(feature_count):
                    normal[i][j] += row[i] * row[j]

        # Keep the intercept unpenalized while regularizing all other terms.
        for index in range(1, feature_count):
            normal[index][index] += self.alpha

        self.weights = solve_linear_system(normal, target_vector)
        return self

    def predict(self, features: list[float]) -> float:
        if not self.weights:
            raise RuntimeError("模型尚未训练")
        standardized = self._standardize(features)
        return sum(weight * value for weight, value in zip(self.weights, standardized))

    def _standardize(self, features: list[float]) -> list[float]:
        if not self.means:
            return features[:]
        return [
            value if index == 0 else (value - self.means[index]) / self.scales[index]
            for index, value in enumerate(features)
        ]


def solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Solve a linear system using partial-pivot Gaussian elimination."""
    size = len(vector)
    augmented = [row[:] + [vector[index]] for index, row in enumerate(matrix)]

    for column in range(size):
        pivot_row = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        pivot = augmented[pivot_row][column]
        if abs(pivot) < 1e-12:
            raise ValueError("训练矩阵不可逆，请检查数据覆盖范围")
        if pivot_row != column:
            augmented[column], augmented[pivot_row] = augmented[pivot_row], augmented[column]

        inverse_pivot = 1.0 / augmented[column][column]
        for index in range(column, size + 1):
            augmented[column][index] *= inverse_pivot

        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor == 0:
                continue
            for index in range(column, size + 1):
                augmented[row][index] -= factor * augmented[column][index]

    return [augmented[row][size] for row in range(size)]


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def format_date(value: date) -> str:
    return value.isoformat()


def as_number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_flag(value: Any) -> float:
    return 1.0 if value else 0.0


def weekday_label(value: date) -> str:
    return ("周一", "周二", "周三", "周四", "周五", "周六", "周日")[value.weekday()]


def feature_names() -> list[str]:
    return [
        "intercept",
        "weekday_mon",
        "weekday_tue",
        "weekday_wed",
        "weekday_thu",
        "weekday_fri",
        "weekday_sat",
        "weekday_sun",
        "annual_sin",
        "annual_cos",
        "is_holiday",
        "is_holiday_eve",
        "is_rainy",
        "is_heavy_rain",
        "temperature_mean",
        "precipitation",
        "lag_1",
        "lag_7",
        "rolling_7",
        "same_weekday_4",
        "same_weekday_8",
        "year_ago_same_weekday",
        "has_year_ago",
    ]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_daily_data(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    rows = payload.get("daily_data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError(f"{path} 缺少 daily_data 数组")

    cleaned = [row for row in rows if isinstance(row, dict) and row.get("date") and row.get("total") is not None]
    cleaned.sort(key=lambda row: row["date"])
    if not cleaned:
        raise ValueError("客流数据为空")
    return cleaned


def load_weather_data(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    payload = load_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"{path} 必须是天气记录数组")
    return {
        row["date"]: row
        for row in payload
        if isinstance(row, dict) and isinstance(row.get("date"), str)
    }


def weather_values(weather: dict[str, Any]) -> dict[str, float]:
    max_temp = as_number(weather.get("temp_max"))
    min_temp = as_number(weather.get("temp_min"))
    return {
        "temp_mean": (max_temp + min_temp) / 2,
        "precipitation": max(0.0, as_number(weather.get("precipitation"))),
        "is_holiday": as_flag(weather.get("is_holiday")),
        "is_holiday_eve": as_flag(weather.get("is_holiday_eve")),
        "is_rainy": as_flag(weather.get("is_rainy")),
        "is_heavy_rain": as_flag(weather.get("is_heavy_rain")),
    }


def resolve_weather(target: date, weather_map: dict[str, dict[str, Any]]) -> tuple[dict[str, float], str]:
    """Use the exact day weather when available, otherwise a recent seven-day average."""
    target_key = format_date(target)
    exact = weather_map.get(target_key)
    if exact is not None:
        return weather_values(exact), "weather_file"

    recent: list[dict[str, float]] = []
    for days_back in range(1, 31):
        previous = weather_map.get(format_date(target - timedelta(days=days_back)))
        if previous is not None:
            recent.append(weather_values(previous))
        if len(recent) == 7:
            break

    if not recent:
        return {
            "temp_mean": 15.0,
            "precipitation": 0.0,
            "is_holiday": 0.0,
            "is_holiday_eve": 0.0,
            "is_rainy": 0.0,
            "is_heavy_rain": 0.0,
        }, "default_climate"

    fields = recent[0].keys()
    averaged = {field: sum(entry[field] for entry in recent) / len(recent) for field in fields}
    # Holiday flags must remain false when a date is not explicitly tagged.
    averaged["is_holiday"] = 0.0
    averaged["is_holiday_eve"] = 0.0
    averaged["is_rainy"] = 1.0 if averaged["is_rainy"] >= 0.5 else 0.0
    averaged["is_heavy_rain"] = 1.0 if averaged["is_heavy_rain"] >= 0.5 else 0.0
    return averaged, "recent_7_day_average"


def lag_features(target: date, totals: dict[str, float]) -> tuple[float, float, float] | None:
    recent_values: list[float] = []
    for days_back in range(1, 61):
        value = totals.get(format_date(target - timedelta(days=days_back)))
        if value is not None:
            recent_values.append(value)
        if len(recent_values) == 7:
            break

    if len(recent_values) < 5:
        return None

    lag_1 = totals.get(format_date(target - timedelta(days=1)), recent_values[0])
    lag_7 = totals.get(format_date(target - timedelta(days=7)))
    if lag_7 is None:
        lag_7 = next(
            (
                totals[format_date(target - timedelta(days=7 * weeks_back))]
                for weeks_back in range(2, 9)
                if format_date(target - timedelta(days=7 * weeks_back)) in totals
            ),
            recent_values[0],
        )
    return lag_1, lag_7, sum(recent_values) / len(recent_values)


def mean(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        raise ValueError("无法计算空序列均值")
    return sum(values) / len(values)


def seasonal_signals(target: date, totals: dict[str, float], fallback: float) -> tuple[float, float, float, float]:
    """Build short-term and year-over-year signals that preserve weekday alignment."""
    same_weekday = [
        totals.get(format_date(target - timedelta(days=7 * weeks_back)))
        for weeks_back in range(1, 9)
    ]
    available = [value for value in same_weekday if value is not None]
    recent_four = mean(available[:4]) if available else fallback
    recent_eight = mean(available) if available else fallback

    # 364 days equals 52 weeks, so it compares the same weekday across years.
    year_ago_key = format_date(target - timedelta(days=364))
    year_ago_value = totals.get(year_ago_key, recent_four)
    has_year_ago = 1.0 if year_ago_key in totals else 0.0
    return recent_four, recent_eight, year_ago_value, has_year_ago


def build_features(
    target: date,
    weather: dict[str, float],
    lags: tuple[float, float, float],
    seasonal: tuple[float, float, float, float],
) -> list[float]:
    day_of_year = target.timetuple().tm_yday
    annual_angle = 2 * math.pi * day_of_year / 365.25
    return [
        1.0,
        *[1.0 if target.weekday() == weekday else 0.0 for weekday in range(7)],
        math.sin(annual_angle),
        math.cos(annual_angle),
        weather["is_holiday"],
        weather["is_holiday_eve"],
        weather["is_rainy"],
        weather["is_heavy_rain"],
        weather["temp_mean"],
        weather["precipitation"],
        *lags,
        *seasonal,
    ]


def build_training_rows(
    daily_data: Iterable[dict[str, Any]], weather_map: dict[str, dict[str, Any]]
) -> list[TrainingRow]:
    sorted_data = sorted(daily_data, key=lambda row: row["date"])
    totals = {row["date"]: as_number(row["total"]) for row in sorted_data}
    rows: list[TrainingRow] = []
    for item in sorted_data:
        note = str(item.get("note", ""))
        if any(marker in note for marker in SERVICE_DISRUPTION_MARKERS):
            continue
        target = parse_date(item["date"])
        lags = lag_features(target, totals)
        if lags is None:
            continue
        weather, _ = resolve_weather(target, weather_map)
        seasonal = seasonal_signals(target, totals, lags[1])
        rows.append(TrainingRow(
            item["date"],
            build_features(target, weather, lags, seasonal),
            as_number(item["total"]),
            seasonal[0],
        ))
    return rows


def mean_absolute_error(actual: list[float], predicted: list[float]) -> float:
    return sum(abs(left - right) for left, right in zip(actual, predicted)) / len(actual)


def root_mean_squared_error(actual: list[float], predicted: list[float]) -> float:
    return math.sqrt(sum((left - right) ** 2 for left, right in zip(actual, predicted)) / len(actual))


def quantile(values: list[float], probability: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    return sorted_values[lower] + (position - lower) * (sorted_values[upper] - sorted_values[lower])


def select_alpha(rows: list[TrainingRow]) -> tuple[float, float, dict[str, Any]]:
    if len(rows) < MIN_TRAINING_ROWS:
        raise ValueError(f"有效训练样本只有 {len(rows)} 条，至少需要 {MIN_TRAINING_ROWS} 条")

    validation_size = min(28, max(14, len(rows) // 8))
    fold_count = min(3, max(1, (len(rows) - MIN_TRAINING_ROWS) // validation_size))
    first_validation_index = len(rows) - fold_count * validation_size
    if first_validation_index < MIN_TRAINING_ROWS:
        raise ValueError("训练集不足，无法保留时间验证集")

    validation_folds = [
        (rows[:start_index], rows[start_index:start_index + validation_size])
        for start_index in range(len(rows) - fold_count * validation_size, len(rows), validation_size)
    ]

    scored: list[tuple[float, float, float, list[float]]] = []
    for alpha in RIDGE_ALPHAS:
        for baseline_weight in ENSEMBLE_BASELINE_WEIGHTS:
            actual: list[float] = []
            predictions: list[float] = []
            for train_rows, validation_rows in validation_folds:
                model = RidgeRegressor(alpha).fit(train_rows)
                ridge_predictions = [model.predict(row.features) for row in validation_rows]
                actual.extend(row.target for row in validation_rows)
                predictions.extend(
                    (1 - baseline_weight) * ridge_prediction + baseline_weight * row.seasonal_baseline
                    for ridge_prediction, row in zip(ridge_predictions, validation_rows)
                )
            scored.append((mean_absolute_error(actual, predictions), alpha, baseline_weight, predictions))

    validation_mae, alpha, baseline_weight, predictions = min(scored, key=lambda item: item[0])
    validation_rows = [row for _, fold in validation_folds for row in fold]
    actual = [row.target for row in validation_rows]
    residuals = [actual_value - predicted_value for actual_value, predicted_value in zip(actual, predictions)]
    nonzero_actual = [
        abs(actual_value - predicted_value) / actual_value * 100
        for actual_value, predicted_value in zip(actual, predictions)
        if actual_value > 0
    ]
    metrics = {
        "rows": len(validation_rows),
        "start_date": validation_rows[0].date,
        "end_date": validation_rows[-1].date,
        "folds": fold_count,
        "mae": round(validation_mae, 2),
        "rmse": round(root_mean_squared_error(actual, predictions), 2),
        "mape": round(sum(nonzero_actual) / len(nonzero_actual), 2) if nonzero_actual else None,
        "interval_radius": round(quantile([abs(value) for value in residuals], 0.9), 2),
    }
    return alpha, baseline_weight, metrics


def forecast(
    model: RidgeRegressor,
    totals: dict[str, float],
    weather_map: dict[str, dict[str, Any]],
    start: date,
    days: int,
    interval_radius: float,
    baseline_weight: float,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    recursive_totals = totals.copy()
    for offset in range(days):
        target = start + timedelta(days=offset)
        lags = lag_features(target, recursive_totals)
        if lags is None:
            raise ValueError(f"{format_date(target)} 缺少构建预测所需的滞后客流数据")
        weather, weather_source = resolve_weather(target, weather_map)
        seasonal = seasonal_signals(target, recursive_totals, lags[1])
        ridge_prediction = model.predict(build_features(target, weather, lags, seasonal))
        prediction = max(0.0, (1 - baseline_weight) * ridge_prediction + baseline_weight * seasonal[0])
        target_key = format_date(target)
        recursive_totals[target_key] = prediction
        results.append({
            "date": target_key,
            "predicted_total": round(prediction, 2),
            "lower_bound": round(max(0.0, prediction - interval_radius), 2),
            "upper_bound": round(prediction + interval_radius, 2),
            "model_components": {
                "ridge_prediction": round(ridge_prediction, 2),
                "same_weekday_baseline": round(seasonal[0], 2),
            },
            "inputs": {
                "weekday": weekday_label(target),
                "is_weekend": target.weekday() >= 5,
                "is_holiday": bool(weather["is_holiday"]),
                "is_holiday_eve": bool(weather["is_holiday_eve"]),
                "temperature_mean": round(weather["temp_mean"], 1),
                "precipitation": round(weather["precipitation"], 1),
                "is_rainy": bool(weather["is_rainy"]),
                "is_heavy_rain": bool(weather["is_heavy_rain"]),
                "lag_1": round(lags[0], 2),
                "lag_7": round(lags[1], 2),
                "rolling_7": round(lags[2], 2),
                "weather_source": weather_source,
            },
        })
    return results


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary_path = Path(handle.name)
    temporary_path.replace(path)


def generate_prediction_file(
    metro_data_path: Path = DEFAULT_METRO_DATA_PATH,
    weather_data_path: Path = DEFAULT_WEATHER_DATA_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    forecast_days: int = 2,
    start_date: str | None = None,
) -> dict[str, Any]:
    if forecast_days < 1:
        raise ValueError("forecast_days 必须大于 0")

    daily_data = load_daily_data(metro_data_path)
    weather_map = load_weather_data(weather_data_path)
    rows = build_training_rows(daily_data, weather_map)
    alpha, baseline_weight, validation = select_alpha(rows)
    model = RidgeRegressor(alpha).fit(rows)

    latest_actual = parse_date(daily_data[-1]["date"])
    start = parse_date(start_date) if start_date else latest_actual + timedelta(days=1)
    if start <= latest_actual:
        raise ValueError("预测起始日期必须晚于最新实际客流日期")

    totals = {row["date"]: as_number(row["total"]) for row in daily_data}
    forecasts = forecast(
        model,
        totals,
        weather_map,
        start,
        forecast_days,
        validation["interval_radius"],
        baseline_weight,
    )
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S%z"),
        "model": {
            "name": MODEL_NAME,
            "version": MODEL_VERSION,
            "algorithm": "时间顺序验证的岭回归与同星期季节基线融合",
            "alpha": alpha,
            "ensemble": {
                "ridge_weight": round(1 - baseline_weight, 2),
                "same_weekday_baseline_weight": round(baseline_weight, 2),
                "baseline": "最近 4 个同星期客流均值",
            },
            "training_rows": len(rows),
            "excluded_service_disruption_rows": sum(
                1
                for item in daily_data
                if any(marker in str(item.get("note", "")) for marker in SERVICE_DISRUPTION_MARKERS)
            ),
            "training_start_date": rows[0].date,
            "training_end_date": rows[-1].date,
            "feature_names": feature_names(),
            "feature_means": [round(value, 8) for value in model.means],
            "feature_scales": [round(value, 8) for value in model.scales],
            "weights": [round(value, 8) for value in model.weights],
            "validation": validation,
        },
        "forecast_base_date": format_date(latest_actual),
        "forecasts": forecasts,
    }
    write_json(output_path, payload)
    return payload


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="训练南京地铁客流岭回归模型并生成预测数据")
    parser.add_argument("--metro-data", type=Path, default=DEFAULT_METRO_DATA_PATH)
    parser.add_argument("--weather-data", type=Path, default=DEFAULT_WEATHER_DATA_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--forecast-days", type=int, default=2)
    parser.add_argument("--start-date", help="预测起始日期，格式 YYYY-MM-DD；默认取最新实际客流的下一天")
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    try:
        payload = generate_prediction_file(
            metro_data_path=args.metro_data,
            weather_data_path=args.weather_data,
            output_path=args.output,
            forecast_days=args.forecast_days,
            start_date=args.start_date,
        )
    except Exception as error:
        print(f"机器学习预测模块失败: {error}")
        return 1

    validation = payload["model"]["validation"]
    forecasts = payload["forecasts"]
    print(
        "机器学习预测已生成: "
        f"训练样本={payload['model']['training_rows']}，"
        f"验证 MAE={validation['mae']}万，"
        f"预测={forecasts[0]['date']} 至 {forecasts[-1]['date']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
