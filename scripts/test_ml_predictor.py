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
        lines = {
            "L1": round(total * 0.24 + current.weekday() * 0.15, 2),
        }
        if offset >= 28:
            lines["S2"] = round(2.4 + (offset - 28) * 0.018 + current.weekday() * 0.05, 2)
        note = ""
        if offset == 50:
            lines["S2"] = 0.0
            note = "停运线路：S2"
        daily_data.append({
            "date": current.isoformat(),
            "total": round(total, 2),
            "is_weekend": current.weekday() >= 5,
            "note": note,
            "lines": lines,
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
    metro_path.write_text(json.dumps({
        "metadata": {
            "lines": [
                {"id": "L1", "name": "1号线"},
                {"id": "S2", "name": "S2号线"},
            ],
        },
        "daily_data": daily_data,
    }), encoding="utf-8")
    weather_path.write_text(json.dumps(weather_data), encoding="utf-8")
    return metro_path, weather_path, (start + timedelta(days=108)).isoformat()


def test_prediction_file_generation():
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        metro_path, weather_path, expected_start = build_fixture(root)
        output_path = root / "ml_predictions.json"
        payload = generate_prediction_file(metro_path, weather_path, output_path, forecast_days=2)

        assert_true(output_path.exists(), "prediction file should be written")
        assert_true(payload["schema_version"] == 2, "hierarchical prediction schema")
        assert_true(
            payload["model"]["name"] == "adaptive-time-series-ensemble",
            "model name should be recorded",
        )
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
        assert_true(set(payload["line_models"]) == {"L1", "S2"}, "each line should have a model")
        assert_true(
            payload["line_models"]["L1"]["training_rows"]
            > payload["line_models"]["S2"]["training_rows"],
            "new lines should use their own shorter history",
        )
        assert_true(
            payload["line_models"]["S2"]["excluded_service_disruption_rows"] == 1,
            "line-specific disruption should be excluded",
        )
        first_forecast = payload["forecasts"][0]
        assert_true(
            set(first_forecast["line_forecasts"]) == {"L1", "S2"},
            "each line should receive a forecast",
        )
        assert_true(
            first_forecast["line_forecast_sum"] == first_forecast["predicted_total"],
            "reconciled lines should sum to network total",
        )
        assert_true(
            all(
                "model_strategy" in forecast
                and forecast["lower_bound"] <= forecast["predicted_flow"] <= forecast["upper_bound"]
                for forecast in first_forecast["line_forecasts"].values()
            ),
            "line forecasts should expose strategy and valid intervals",
        )


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
