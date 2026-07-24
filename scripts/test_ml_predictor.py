#!/usr/bin/env python3
"""Checks for the standalone machine-learning forecast module."""

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

from ml_predictor import generate_prediction_file


def assert_true(value, label):
    if not value:
        raise AssertionError(label)


def build_fixture(root):
    start = date(2025, 1, 1)
    daily_data = []
    weather_data = []
    for offset in range(108):
        current = start + timedelta(days=offset)
        rainy = offset % 11 == 0
        total = 290 + current.weekday() * 8 + offset * 0.16 - (12 if rainy else 0)
        daily_data.append({
            "date": current.isoformat(),
            "total": round(total, 2),
            "is_weekend": current.weekday() >= 5,
            "note": "停运线路：S1" if offset == 50 else "",
            "lines": {},
        })
        weather_data.append({
            "date": current.isoformat(),
            "temp_max": 18 + offset % 9,
            "temp_min": 6 + offset % 6,
            "precipitation": 4.0 if rainy else 0.0,
            "is_rainy": rainy,
            "is_heavy_rain": False,
            "is_holiday": False,
            "is_holiday_eve": False,
        })

    # Include exact forecast weather so the prediction path can verify it is used.
    for offset in range(108, 110):
        current = start + timedelta(days=offset)
        weather_data.append({
            "date": current.isoformat(),
            "temp_max": 25,
            "temp_min": 15,
            "precipitation": 0.0,
            "is_rainy": False,
            "is_heavy_rain": False,
            "is_holiday": False,
            "is_holiday_eve": False,
        })

    metro_path = root / "metro_data.json"
    weather_path = root / "weather.json"
    metro_path.write_text(json.dumps({"daily_data": daily_data}), encoding="utf-8")
    weather_path.write_text(json.dumps(weather_data), encoding="utf-8")
    return metro_path, weather_path, (start + timedelta(days=108)).isoformat()


def test_prediction_file_generation():
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        metro_path, weather_path, expected_start = build_fixture(root)
        output_path = root / "ml_predictions.json"
        payload = generate_prediction_file(metro_path, weather_path, output_path, forecast_days=2)

        assert_true(output_path.exists(), "prediction file should be written")
        assert_true(payload["model"]["name"] == "ridge-regression", "model name should be recorded")
        assert_true("ensemble" in payload["model"], "ensemble configuration should be recorded")
        assert_true(payload["model"]["training_rows"] >= 90, "training rows should exclude only lag warm-up")
        assert_true(
            payload["model"]["excluded_service_disruption_rows"] == 1,
            "service disruption targets should be excluded",
        )
        assert_true(payload["model"]["validation"]["rows"] >= 28, "temporal validation should run")
        assert_true(len(payload["forecasts"]) == 2, "two forecasts should be generated")
        assert_true(payload["forecasts"][0]["date"] == expected_start, "forecast should start after latest actual")
        assert_true(payload["forecasts"][0]["inputs"]["weather_source"] == "weather_file", "exact weather should be used")
        assert_true(payload["forecasts"][0]["upper_bound"] >= payload["forecasts"][0]["predicted_total"], "interval upper bound")


def test_prediction_with_recent_data_gaps():
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        metro_path, weather_path, expected_start = build_fixture(root)
        payload = json.loads(metro_path.read_text(encoding="utf-8"))
        start = date(2025, 1, 1)
        missing_dates = {
            (start + timedelta(days=101)).isoformat(),
            (start + timedelta(days=103)).isoformat(),
            (start + timedelta(days=104)).isoformat(),
        }
        payload["daily_data"] = [
            item for item in payload["daily_data"] if item["date"] not in missing_dates
        ]
        metro_path.write_text(json.dumps(payload), encoding="utf-8")

        result = generate_prediction_file(
            metro_path,
            weather_path,
            root / "ml_predictions_with_gaps.json",
            forecast_days=2,
        )
        assert_true(result["forecasts"][0]["date"] == expected_start, "gapped forecast start")
        assert_true(result["forecasts"][0]["predicted_total"] > 0, "gapped forecast value")


if __name__ == "__main__":
    test_prediction_file_generation()
    test_prediction_with_recent_data_gaps()
    print("ml_predictor checks passed.")
