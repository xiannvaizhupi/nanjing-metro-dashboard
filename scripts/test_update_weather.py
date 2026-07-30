#!/usr/bin/env python3
"""Checks for the standalone weather updater."""

import json
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import update_weather


def assert_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def fixture_payload():
    return {
        "daily": {
            "time": ["2026-02-14", "2026-02-15", "2026-02-16"],
            "weather_code": [75, 96, 3],
            "temperature_2m_max": [2.0, 8.0, 10.0],
            "temperature_2m_min": [-2.0, 2.0, 3.0],
            "precipitation_sum": [4.0, 20.0, 0.0],
            "snowfall_sum": [3.0, 0.0, 0.0],
            "wind_speed_10m_max": [12.0, 18.0, 8.0],
        }
    }


def test_api_url_uses_current_open_meteo_fields():
    query = parse_qs(urlparse(update_weather.build_api_url(14, 7)).query)
    assert_equal(query["timezone"], ["Asia/Shanghai"], "timezone")
    assert_equal(query["past_days"], ["14"], "past days")
    assert_equal(query["forecast_days"], ["7"], "forecast days")
    assert_equal("weather_code" in query["daily"][0], True, "current weather code field")


def test_weather_categories_and_official_calendar():
    records = update_weather.parse_forecast(fixture_payload())
    assert_equal(records[0]["is_snow"], True, "snow code")
    assert_equal(records[0]["is_rainy"], False, "snow is not rain")
    assert_equal(records[0]["is_heavy_rain"], False, "snow is not heavy rain")
    assert_equal(records[1]["weather"], "雷暴", "thunderstorm label")
    assert_equal(records[1]["is_snow"], False, "thunderstorm is not snow")
    assert_equal(records[1]["is_heavy_rain"], True, "heavy thunderstorm")
    assert_equal(records[0]["is_holiday_eve"], True, "Spring Festival eve")
    assert_equal(records[1]["is_holiday"], True, "Spring Festival start")
    assert_equal(records[2]["is_holiday_eve"], False, "holiday is not holiday eve")
    assert_equal(update_weather.calendar_flags("2026-01-28"), (False, False), "old wrong date")
    assert_equal(update_weather.calendar_flags("2026-06-19"), (True, False), "Dragon Boat")


def test_merge_updates_dates_and_repairs_legacy_calendar():
    existing = [
        {
            "date": "2026-01-10",
            "temp_max": 9.0,
            "temp_min": 1.0,
            "weather_code": 95,
            "precipitation": 0.5,
            "weather": "雷暴",
            "is_rainy": True,
            "is_heavy_rain": False,
            "is_snow": True,
            "is_holiday": False,
            "is_holiday_eve": False,
        },
        {
            "date": "2026-01-28",
            "temp_max": 9.0,
            "temp_min": 1.0,
            "is_holiday": True,
            "is_holiday_eve": True,
        },
        {
            "date": "2026-02-15",
            "temp_max": 7.0,
            "temp_min": 1.0,
            "weather_code": 96,
            "precipitation": 20.0,
            "weather": "雷暴",
            "is_rainy": True,
            "is_heavy_rain": True,
            "is_snow": True,
            "is_holiday": False,
            "is_holiday_eve": False,
        },
    ]
    incoming = update_weather.parse_forecast(fixture_payload())
    merged, changed = update_weather.merge_weather(existing, incoming)
    by_date = {item["date"]: item for item in merged}
    assert_equal([item["date"] for item in merged], sorted(by_date), "sorted dates")
    assert_equal(by_date["2026-01-10"]["is_snow"], False, "repair legacy thunder")
    assert_equal(by_date["2026-01-28"]["is_holiday"], False, "repair old holiday")
    assert_equal(by_date["2026-02-15"]["temp_max"], 8.0, "replace forecast")
    assert_equal("2026-01-28" in changed, True, "calendar repair tracked")
    assert_equal("2026-02-16" in changed, True, "new date tracked")


def test_invalid_parallel_arrays_are_rejected():
    payload = fixture_payload()
    payload["daily"]["precipitation_sum"] = [1.0]
    try:
        update_weather.parse_forecast(payload)
    except update_weather.WeatherDataError:
        return
    raise AssertionError("mismatched daily arrays should be rejected")


def test_invalid_numeric_values_are_rejected():
    payload = fixture_payload()
    payload["daily"]["temperature_2m_max"][0] = "nan"
    try:
        update_weather.parse_forecast(payload)
    except update_weather.WeatherDataError:
        return
    raise AssertionError("non-finite weather values should be rejected")


def test_incomplete_history_is_skipped_but_forecast_is_required():
    payload = fixture_payload()
    payload["daily"]["weather_code"][0] = None
    records = update_weather.parse_forecast(payload, required_tail=2)
    assert_equal([record["date"] for record in records], ["2026-02-15", "2026-02-16"], "history skip")

    payload = fixture_payload()
    payload["daily"]["weather_code"][-1] = None
    try:
        update_weather.parse_forecast(payload, required_tail=2)
    except update_weather.WeatherDataError:
        return
    raise AssertionError("incomplete forecast days should be rejected")


def test_atomic_json_write():
    with tempfile.TemporaryDirectory() as temporary_directory:
        path = Path(temporary_directory) / "weather.json"
        payload = update_weather.parse_forecast(fixture_payload())
        update_weather.write_json_atomic(path, payload)
        assert_equal(json.loads(path.read_text(encoding="utf-8")), payload, "atomic JSON")


if __name__ == "__main__":
    test_api_url_uses_current_open_meteo_fields()
    test_weather_categories_and_official_calendar()
    test_merge_updates_dates_and_repairs_legacy_calendar()
    test_invalid_parallel_arrays_are_rejected()
    test_invalid_numeric_values_are_rejected()
    test_incomplete_history_is_skipped_but_forecast_is_required()
    test_atomic_json_write()
    print("weather updater checks passed.")
