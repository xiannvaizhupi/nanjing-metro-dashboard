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

MODEL_NAME = "adaptive-time-series-ensemble"
MODEL_VERSION = "2.0.0"
RIDGE_ALPHAS = (0.1, 1.0, 10.0, 50.0, 100.0, 300.0, 500.0, 1000.0)
ENSEMBLE_BASELINE_WEIGHTS = tuple(index / 10 for index in range(11))
TRAINING_WINDOWS = (180, 365, None)
MEAN_WEEKDAY_BASELINE = "same-weekday-mean-4"
WEIGHTED_WEEKDAY_BASELINE = "recency-weighted-same-weekday-4"
BASELINE_NAMES = (MEAN_WEEKDAY_BASELINE, WEIGHTED_WEEKDAY_BASELINE)
MIN_TRAINING_ROWS = 60
SERVICE_DISRUPTION_MARKERS = ("停运", "运营中断")


@dataclass
class TrainingRow:
    date: str
    features: list[float]
    target: float
    seasonal_baseline: float
    weighted_seasonal_baseline: float


@dataclass
class ModelSelection:
    alpha: float | None
    baseline_weight: float
    baseline_name: str
    training_window_days: int | None
    strategy: str
    validation: dict[str, Any]


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


def weighted_weekday_baseline(target: date, totals: dict[str, float], fallback: float) -> float:
    """Weight the most recent same-weekday observations more heavily."""
    weighted_values: list[tuple[float, float]] = []
    for weeks_back, weight in enumerate((0.4, 0.3, 0.2, 0.1), start=1):
        value = totals.get(format_date(target - timedelta(days=7 * weeks_back)))
        if value is not None:
            weighted_values.append((value, weight))
    if not weighted_values:
        return fallback
    weight_sum = sum(weight for _, weight in weighted_values)
    return sum(value * weight for value, weight in weighted_values) / weight_sum


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
    daily_data: Iterable[dict[str, Any]],
    weather_map: dict[str, dict[str, Any]],
    line_id: str | None = None,
) -> list[TrainingRow]:
    sorted_data = sorted(daily_data, key=lambda row: row["date"])
    if line_id is None:
        series_data = [row for row in sorted_data if row.get("total") is not None]
        totals = {row["date"]: as_number(row["total"]) for row in series_data}
    else:
        series_data = [row for row in sorted_data if line_id in row.get("lines", {})]
        totals = {row["date"]: as_number(row["lines"][line_id]) for row in series_data}

    rows: list[TrainingRow] = []
    for item in series_data:
        note = str(item.get("note", ""))
        target_value = as_number(item["total"] if line_id is None else item["lines"][line_id])
        has_disruption = any(marker in note for marker in SERVICE_DISRUPTION_MARKERS)
        if line_id is None and has_disruption:
            continue
        if line_id is not None and (target_value <= 0 or (has_disruption and line_id in note)):
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
            target_value,
            seasonal[0],
            weighted_weekday_baseline(target, totals, seasonal[0]),
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


def rows_in_window(
    rows: list[TrainingRow], window_days: int | None, end_date: date
) -> list[TrainingRow]:
    if window_days is None:
        return rows
    cutoff = end_date - timedelta(days=window_days)
    return [row for row in rows if parse_date(row.date) >= cutoff]


def strategy_name(baseline_name: str, baseline_weight: float) -> str:
    if baseline_weight == 0:
        return "ridge-regression"
    if baseline_weight == 1:
        return baseline_name
    return f"ridge-{baseline_name}-ensemble"


def validation_metrics(
    validation_rows: list[TrainingRow],
    predictions: list[float],
    folds: int,
    candidate_count: int,
) -> dict[str, Any]:
    actual = [row.target for row in validation_rows]
    residuals = [actual_value - predicted for actual_value, predicted in zip(actual, predictions)]
    percentage_errors = [
        abs(actual_value - predicted) / actual_value * 100
        for actual_value, predicted in zip(actual, predictions)
        if actual_value > 0
    ]
    return {
        "rows": len(validation_rows),
        "start_date": validation_rows[0].date,
        "end_date": validation_rows[-1].date,
        "folds": folds,
        "candidate_count": candidate_count,
        "mae": round(mean_absolute_error(actual, predictions), 2),
        "rmse": round(root_mean_squared_error(actual, predictions), 2),
        "mape": round(mean(percentage_errors), 2) if percentage_errors else None,
        "interval_radius": round(quantile([abs(value) for value in residuals], 0.9), 2),
    }


def select_strategy(rows: list[TrainingRow]) -> ModelSelection:
    """Select each series' window, ridge penalty, and seasonal blending independently."""
    if len(rows) < MIN_TRAINING_ROWS + 14:
        validation_rows = rows[-min(14, len(rows)):]
        if not validation_rows:
            raise ValueError("没有可用的线路训练样本")
        predictions = [row.weighted_seasonal_baseline for row in validation_rows]
        return ModelSelection(
            alpha=None,
            baseline_weight=1.0,
            baseline_name=WEIGHTED_WEEKDAY_BASELINE,
            training_window_days=None,
            strategy=WEIGHTED_WEEKDAY_BASELINE,
            validation=validation_metrics(validation_rows, predictions, 1, 1),
        )

    validation_size = min(28, max(14, len(rows) // 8))
    fold_count = min(3, max(1, (len(rows) - MIN_TRAINING_ROWS) // validation_size))
    first_validation_index = len(rows) - fold_count * validation_size
    if first_validation_index < MIN_TRAINING_ROWS:
        raise ValueError("训练集不足，无法保留时间验证集")

    validation_folds = [
        (rows[:start_index], rows[start_index:start_index + validation_size])
        for start_index in range(first_validation_index, len(rows), validation_size)
    ]
    validation_rows = [row for _, fold in validation_folds for row in fold]
    scored: list[dict[str, Any]] = []

    for window_days in TRAINING_WINDOWS:
        for alpha in RIDGE_ALPHAS:
            actual: list[float] = []
            ridge_predictions: list[float] = []
            mean_baselines: list[float] = []
            weighted_baselines: list[float] = []
            valid_candidate = True
            for preceding_rows, fold_rows in validation_folds:
                train_rows = rows_in_window(preceding_rows, window_days, parse_date(fold_rows[0].date))
                if len(train_rows) < MIN_TRAINING_ROWS:
                    valid_candidate = False
                    break
                model = RidgeRegressor(alpha).fit(train_rows)
                actual.extend(row.target for row in fold_rows)
                ridge_predictions.extend(model.predict(row.features) for row in fold_rows)
                mean_baselines.extend(row.seasonal_baseline for row in fold_rows)
                weighted_baselines.extend(row.weighted_seasonal_baseline for row in fold_rows)
            if not valid_candidate:
                continue

            for baseline_name in BASELINE_NAMES:
                baselines = (
                    weighted_baselines
                    if baseline_name == WEIGHTED_WEEKDAY_BASELINE
                    else mean_baselines
                )
                for baseline_weight in ENSEMBLE_BASELINE_WEIGHTS:
                    if baseline_weight == 0 and baseline_name != MEAN_WEEKDAY_BASELINE:
                        continue
                    predictions = [
                        (1 - baseline_weight) * ridge_prediction + baseline_weight * baseline
                        for ridge_prediction, baseline in zip(ridge_predictions, baselines)
                    ]
                    scored.append({
                        "mae": mean_absolute_error(actual, predictions),
                        "alpha": alpha,
                        "baseline_weight": baseline_weight,
                        "baseline_name": baseline_name,
                        "window_days": window_days,
                        "predictions": predictions,
                    })

    if not scored:
        raise ValueError("没有模型配置满足最小训练样本要求")
    best = min(scored, key=lambda candidate: candidate["mae"])
    return ModelSelection(
        alpha=best["alpha"],
        baseline_weight=best["baseline_weight"],
        baseline_name=best["baseline_name"],
        training_window_days=best["window_days"],
        strategy=strategy_name(best["baseline_name"], best["baseline_weight"]),
        validation=validation_metrics(
            validation_rows,
            best["predictions"],
            fold_count,
            len(scored),
        ),
    )


def select_alpha(rows: list[TrainingRow]) -> tuple[float, float, dict[str, Any]]:
    """Backward-compatible selector for callers that only need ridge settings."""
    selection = select_strategy(rows)
    if selection.alpha is None:
        raise ValueError("训练样本不足，当前策略不包含岭回归")
    return selection.alpha, selection.baseline_weight, selection.validation


def train_series_model(rows: list[TrainingRow]) -> tuple[RidgeRegressor | None, ModelSelection, list[TrainingRow]]:
    selection = select_strategy(rows)
    final_rows = rows_in_window(
        rows,
        selection.training_window_days,
        parse_date(rows[-1].date) + timedelta(days=1),
    )
    model = None
    if selection.baseline_weight < 1:
        if selection.alpha is None:
            raise ValueError("岭回归策略缺少 alpha")
        model = RidgeRegressor(selection.alpha).fit(final_rows)
    return model, selection, final_rows


def selected_baseline(
    selection: ModelSelection,
    target: date,
    values: dict[str, float],
    seasonal: tuple[float, float, float, float],
) -> float:
    if selection.baseline_name == WEIGHTED_WEEKDAY_BASELINE:
        return weighted_weekday_baseline(target, values, seasonal[0])
    return seasonal[0]


def predict_series_day(
    model: RidgeRegressor | None,
    selection: ModelSelection,
    values: dict[str, float],
    weather_map: dict[str, dict[str, Any]],
    target: date,
) -> dict[str, Any]:
    lags = lag_features(target, values)
    if lags is None:
        raise ValueError(f"{format_date(target)} 缺少构建预测所需的滞后客流数据")
    weather, weather_source = resolve_weather(target, weather_map)
    seasonal = seasonal_signals(target, values, lags[1])
    baseline = selected_baseline(selection, target, values, seasonal)
    ridge_prediction = model.predict(build_features(target, weather, lags, seasonal)) if model else None
    ridge_component = ridge_prediction if ridge_prediction is not None else baseline
    prediction = max(
        0.0,
        (1 - selection.baseline_weight) * ridge_component
        + selection.baseline_weight * baseline,
    )
    radius = selection.validation["interval_radius"]
    return {
        "prediction": prediction,
        "lower_bound": max(0.0, prediction - radius),
        "upper_bound": prediction + radius,
        "components": {
            "ridge_prediction": ridge_prediction,
            "selected_weekday_baseline": baseline,
            "baseline_name": selection.baseline_name,
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
    }


def reconcile_line_predictions(
    total_prediction: float,
    raw_predictions: dict[str, dict[str, Any]],
) -> dict[str, dict[str, float]]:
    raw_sum = sum(result["prediction"] for result in raw_predictions.values())
    if raw_sum <= 0:
        raise ValueError("线路预测合计无效，无法执行线网校准")
    factor = total_prediction / raw_sum
    reconciled: dict[str, dict[str, float]] = {}
    for line_id, result in raw_predictions.items():
        predicted = round(result["prediction"] * factor, 2)
        reconciled[line_id] = {
            "predicted_flow": predicted,
            "raw_prediction": round(result["prediction"], 2),
            "lower_bound": round(max(0.0, result["lower_bound"] * factor), 2),
            "upper_bound": round(result["upper_bound"] * factor, 2),
            "reconciliation_factor": round(factor, 6),
        }

    rounded_total = round(total_prediction, 2)
    rounding_gap = round(rounded_total - sum(item["predicted_flow"] for item in reconciled.values()), 2)
    if rounding_gap:
        adjustment_line = max(reconciled, key=lambda line_id: reconciled[line_id]["predicted_flow"])
        reconciled[adjustment_line]["predicted_flow"] = round(
            reconciled[adjustment_line]["predicted_flow"] + rounding_gap,
            2,
        )
    for item in reconciled.values():
        item["lower_bound"] = min(item["lower_bound"], item["predicted_flow"])
        item["upper_bound"] = max(item["upper_bound"], item["predicted_flow"])
    return reconciled


def load_line_catalog(path: Path, daily_data: list[dict[str, Any]]) -> list[dict[str, str]]:
    payload = load_json(path)
    configured = payload.get("metadata", {}).get("lines", []) if isinstance(payload, dict) else []
    catalog = [
        {"id": item["id"], "name": item.get("name", item["id"])}
        for item in configured
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]
    known_ids = {item["id"] for item in catalog}
    observed_ids = {
        line_id
        for row in daily_data
        for line_id in row.get("lines", {})
        if isinstance(line_id, str)
    }
    catalog.extend({"id": line_id, "name": line_id} for line_id in sorted(observed_ids - known_ids))
    return catalog


def algorithm_description(selection: ModelSelection) -> str:
    if selection.strategy == "ridge-regression":
        return "带正则化的多特征岭回归"
    if selection.baseline_weight == 1:
        return "近期同星期客流季节基线"
    return "多特征岭回归与近期同星期季节基线融合"


def model_metadata(
    model: RidgeRegressor | None,
    selection: ModelSelection,
    training_rows: list[TrainingRow],
    excluded_rows: int,
) -> dict[str, Any]:
    baseline_label = (
        "最近 4 个同星期加权均值"
        if selection.baseline_name == WEIGHTED_WEEKDAY_BASELINE
        else "最近 4 个同星期算术均值"
    )
    return {
        "strategy": selection.strategy,
        "algorithm": algorithm_description(selection),
        "alpha": selection.alpha,
        "training_window_days": selection.training_window_days,
        "ensemble": {
            "ridge_weight": round(1 - selection.baseline_weight, 2),
            "same_weekday_baseline_weight": round(selection.baseline_weight, 2),
            "baseline": baseline_label,
        },
        "training_rows": len(training_rows),
        "excluded_service_disruption_rows": excluded_rows,
        "training_start_date": training_rows[0].date,
        "training_end_date": training_rows[-1].date,
        "feature_names": feature_names(),
        "feature_means": [round(value, 8) for value in model.means] if model else [],
        "feature_scales": [round(value, 8) for value in model.scales] if model else [],
        "weights": [round(value, 8) for value in model.weights] if model else [],
        "validation": selection.validation,
    }


def rounded_components(components: dict[str, Any]) -> dict[str, Any]:
    return {
        key: round(value, 2) if isinstance(value, (int, float)) else value
        for key, value in components.items()
    }


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
    total_rows = build_training_rows(daily_data, weather_map)
    total_model, total_selection, total_training_rows = train_series_model(total_rows)

    latest_actual = parse_date(daily_data[-1]["date"])
    start = parse_date(start_date) if start_date else latest_actual + timedelta(days=1)
    if start <= latest_actual:
        raise ValueError("预测起始日期必须晚于最新实际客流日期")

    line_catalog = load_line_catalog(metro_data_path, daily_data)
    if not line_catalog:
        raise ValueError("客流数据中没有可预测的线路")

    line_models: dict[str, dict[str, Any]] = {}
    line_bundles: dict[str, tuple[RidgeRegressor | None, ModelSelection]] = {}
    recursive_lines: dict[str, dict[str, float]] = {}
    for line in line_catalog:
        line_id = line["id"]
        observed = [row for row in daily_data if line_id in row.get("lines", {})]
        if len(observed) < 7:
            raise ValueError(f"{line['name']} 只有 {len(observed)} 条数据，无法建立独立预测")
        line_rows = build_training_rows(daily_data, weather_map, line_id=line_id)
        line_model, line_selection, line_training_rows = train_series_model(line_rows)
        excluded_rows = sum(
            1
            for item in observed
            if as_number(item["lines"][line_id]) <= 0
            or (
                any(marker in str(item.get("note", "")) for marker in SERVICE_DISRUPTION_MARKERS)
                and line_id in str(item.get("note", ""))
            )
        )
        line_models[line_id] = {
            "line_name": line["name"],
            **model_metadata(line_model, line_selection, line_training_rows, excluded_rows),
        }
        line_bundles[line_id] = (line_model, line_selection)
        recursive_lines[line_id] = {
            item["date"]: as_number(item["lines"][line_id])
            for item in observed
        }

    recursive_totals = {row["date"]: as_number(row["total"]) for row in daily_data}
    forecasts: list[dict[str, Any]] = []
    for offset in range(forecast_days):
        target = start + timedelta(days=offset)
        target_key = format_date(target)
        total_result = predict_series_day(
            total_model,
            total_selection,
            recursive_totals,
            weather_map,
            target,
        )
        raw_line_results = {
            line_id: predict_series_day(
                line_bundles[line_id][0],
                line_bundles[line_id][1],
                recursive_lines[line_id],
                weather_map,
                target,
            )
            for line_id in line_bundles
        }
        total_prediction = round(total_result["prediction"], 2)
        reconciled = reconcile_line_predictions(total_prediction, raw_line_results)
        line_forecasts: dict[str, dict[str, Any]] = {}
        for line in line_catalog:
            line_id = line["id"]
            values = reconciled[line_id]
            line_forecasts[line_id] = {
                "line_name": line["name"],
                **values,
                "model_strategy": line_bundles[line_id][1].strategy,
            }
            recursive_lines[line_id][target_key] = values["predicted_flow"]
        recursive_totals[target_key] = total_prediction
        forecasts.append({
            "date": target_key,
            "predicted_total": total_prediction,
            "lower_bound": round(total_result["lower_bound"], 2),
            "upper_bound": round(total_result["upper_bound"], 2),
            "model_components": rounded_components(total_result["components"]),
            "inputs": total_result["inputs"],
            "line_forecasts": line_forecasts,
            "line_forecast_sum": round(
                sum(item["predicted_flow"] for item in line_forecasts.values()),
                2,
            ),
        })

    total_excluded_rows = sum(
        1
        for item in daily_data
        if any(marker in str(item.get("note", "")) for marker in SERVICE_DISRUPTION_MARKERS)
    )
    payload = {
        "schema_version": 2,
        "generated_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S%z"),
        "model": {
            "name": MODEL_NAME,
            "version": MODEL_VERSION,
            **model_metadata(
                total_model,
                total_selection,
                total_training_rows,
                total_excluded_rows,
            ),
        },
        "line_modeling": {
            "method": "各线路独立时间验证选模，预测后按线网总量进行分层校准",
            "candidate_training_windows_days": [180, 365, "all"],
            "candidate_baselines": list(BASELINE_NAMES),
            "minimum_training_rows": MIN_TRAINING_ROWS,
            "line_count": len(line_models),
        },
        "line_models": line_models,
        "forecast_base_date": format_date(latest_actual),
        "forecasts": forecasts,
    }
    write_json(output_path, payload)
    return payload


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="训练南京地铁线网及各线路独立客流模型并生成预测数据")
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
        f"线路模型={len(payload['line_models'])}个，"
        f"预测={forecasts[0]['date']} 至 {forecasts[-1]['date']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
