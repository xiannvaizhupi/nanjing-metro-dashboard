#!/usr/bin/env python3
"""Lightweight checks for the Nanjing Metro passenger-flow fetcher."""

import json
import ssl
import tempfile
from datetime import date
from pathlib import Path
from urllib.error import URLError

import fetch_data
from fetch_data import infer_entry_year, parse_passenger_flow, parse_weibo_flow


JULY_BACKFILL_TEXT = (
    "#昨日客流#南京地铁7月15日客运量347.99，其中1号线74.06，2号线61.98，"
    "3号线62.86，4号线17.68，5号线39.86，7号线30.28，10号线19.09，"
    "S1号线10.05，S2号线3.99，S3号线9.41，S6号线5.25，S7号线1.41，"
    "S8号线10.25，S9号线1.81（以上单位: 万） "
    "#昨日客流#南京地铁7月16日客运量343.01，其中1号线72.49，2号线61.18，"
    "3号线62.55，4号线17.5，5号线40.09，7号线29.6，10号线18.67，"
    "S1号线9.67，S2号线3.83，S3号线9.33，S6号线5.07，S7号线1.4，"
    "S8号线9.98，S9号线1.66（以上单位: 万） "
    "南京地铁7月17日客运量362.28，其中：1号线77.92，2号线63.94，3号线66.65，"
    "4号线17.86，5号线41.45，7号线30.37，10号线20.62，S1号线10.32，"
    "S2号线3.97，S3号线10.18，S6号线5.18，S7号线1.47，S8号线10.50，"
    "S9号线1.86（以上单位：万） "
    "南京地铁7月18日客运量311.47，其中：1号线67.25，2号线57.87，3号线56.65，"
    "4号线14.69，5号线38.37，7号线23.93，10号线14.59，S1号线8.95，"
    "S2号线4.60，S3号线8.04，S6号线4.76，S7号线1.27，S8号线8.83，"
    "S9号线1.69（以上单位：万） "
    "#昨日客流#南京地铁7月19日客运量254.21，其中1号线55.49，2号线45.75，"
    "3号线47.19，4号线10.54，5号线30.67，7号线18.94，10号线11.5，"
    "S1号线8.33，S2号线3.99，S3号线7.12，S6号线3.98，S7号线1.19，"
    "S8号线7.81，S9号线1.72（以上单位: 万）"
)


def assert_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def test_parse_with_explicit_short_year():
    html = (
        "26-6-23#昨日客流#南京地铁6月23日客运量331.51，"
        "其中1号线70.24，2号线58.57，3号线60.03，4号线16.95，"
        "5号线36.60，7号线29.62，10号线18.64，S1号线9.42，"
        "S2号线3.43，S3号线9.33，S6号线5.09，S7号线1.28，"
        "S8号线10.30，S9号线2.01（以上单位: 万）"
    )
    entries = parse_weibo_flow(html)

    assert_equal(len(entries), 1, "entry count")
    assert_equal(entries[0]["date"], "2026-06-23", "date")
    assert_equal(entries[0]["total"], 331.51, "total")
    assert_equal(entries[0]["lines"]["L10"], 18.64, "line 10")
    assert_equal(entries[0]["lines"]["S9"], 2.01, "line S9")


def test_infer_year_around_new_year():
    assert_equal(
        infer_entry_year(12, 31, reference_date=date(2027, 1, 1)),
        2026,
        "Dec 31 should resolve to previous year after New Year",
    )
    assert_equal(
        infer_entry_year(1, 1, reference_date=date(2026, 12, 31)),
        2027,
        "Jan 1 should resolve to next year before New Year",
    )


def test_official_homepage_api_response():
    response = '{"articleTitle":"337.91","articleContent":""}'
    assert_equal(fetch_data.parse_official_total(response), 337.91, "official total")


def test_wrapped_ssl_verification_error_is_detected():
    wrapped = URLError(ssl.SSLCertVerificationError(1, "certificate verify failed"))
    assert_equal(fetch_data.is_ssl_verification_error(wrapped), True, "wrapped SSL error")


def test_parse_official_homepage_text_without_hashtag():
    html = """
    <div class="notice">
      南京地铁2026年6月27日客运量：347.91万，其中：
      1号线：73.12，2号线：58.45，3号线：64.30，4号线：17.01，
      5号线：43.22，7号线：29.80，10号线：18.70，S1号线：9.60，
      S2号线：3.51，S3号线：9.75，S6号线：5.42，S7号线：1.33，
      S8号线：11.31，S9号线：2.39（以上单位：万）
    </div>
    """
    entries = parse_passenger_flow(html, source_name="南京地铁官网首页")

    assert_equal(len(entries), 1, "official entry count")
    assert_equal(entries[0]["date"], "2026-06-27", "official date")
    assert_equal(entries[0]["total"], 347.91, "official total")
    assert_equal(entries[0]["lines"]["L1"], 73.12, "official line 1")
    assert_equal(entries[0]["lines"]["S9"], 2.39, "official line S9")


def test_incomplete_line_data_is_rejected():
    html = (
        "南京地铁2026年7月12日客运量68.82万，其中："
        "1号线12.07，2号线12.80，3号线15.42，4号线4.44，"
        "5号线10.62，7号线8.59，10号线2.81，S3号线2.06（以上单位：万）"
    )
    entries = parse_passenger_flow(html, source_name="南京地铁官网首页")
    assert_equal(entries, [], "incomplete line data should be rejected")


def test_large_total_line_difference_is_rejected():
    html = (
        "南京地铁2026年7月12日客运量300万，其中："
        "1号线10，2号线10，3号线10，4号线10，5号线10，7号线10，"
        "10号线10，S1号线10，S2号线10，S3号线10，S6号线10，"
        "S7号线10，S8号线10，S9号线10（以上单位：万）"
    )
    entries = parse_passenger_flow(html, source_name="南京地铁官网首页")
    assert_equal(entries, [], "large total-line mismatch should be rejected")


def test_parse_backfill_text_with_mixed_formats():
    entries = parse_passenger_flow(JULY_BACKFILL_TEXT, source_name="人工核验补录")
    assert_equal(len(entries), 5, "backfill entry count")
    assert_equal([item["date"] for item in entries], [
        "2026-07-15", "2026-07-16", "2026-07-17", "2026-07-18", "2026-07-19"
    ], "backfill dates")
    assert_equal(entries[-1]["lines"]["S9"], 1.72, "backfill final line")


def test_unparseable_sources_are_not_reported_as_successful():
    original_fetch_url = fetch_data.fetch_url
    try:
        fetch_data.fetch_url = lambda *args, **kwargs: "<html>unexpected response</html>"
        entries, source_name, successful_sources = fetch_data.fetch_passenger_flow_entries(
            reference_date=date(2026, 7, 24)
        )
        assert_equal(entries, [], "unparseable entries")
        assert_equal(source_name, None, "unparseable source")
        assert_equal(successful_sources, [], "unparseable sources should fail")
    finally:
        fetch_data.fetch_url = original_fetch_url


def test_corrected_entry_triggers_follow_up_processing():
    original_path = fetch_data.METRO_DATA_PATH
    try:
        with tempfile.TemporaryDirectory() as temporary_directory:
            metro_path = Path(temporary_directory) / "metro_data.json"
            metro_path.write_text(json.dumps({
                "metadata": {},
                "daily_data": [{
                    "date": "2026-07-01",
                    "total": 300.0,
                    "is_weekend": False,
                    "note": "",
                    "lines": {},
                }],
            }), encoding="utf-8")
            fetch_data.METRO_DATA_PATH = str(metro_path)
            updated_dates = fetch_data.update_metro_data([{
                "date": "2026-07-01",
                "total": 301.0,
                "is_weekend": False,
                "note": "",
                "lines": {},
            }])
            assert_equal(updated_dates, ["2026-07-01"], "corrected date should be returned")
    finally:
        fetch_data.METRO_DATA_PATH = original_path


if __name__ == "__main__":
    test_parse_with_explicit_short_year()
    test_infer_year_around_new_year()
    test_official_homepage_api_response()
    test_wrapped_ssl_verification_error_is_detected()
    test_parse_official_homepage_text_without_hashtag()
    test_incomplete_line_data_is_rejected()
    test_large_total_line_difference_is_rejected()
    test_parse_backfill_text_with_mixed_formats()
    test_unparseable_sources_are_not_reported_as_successful()
    test_corrected_entry_triggers_follow_up_processing()
    print("fetch_data parser checks passed.")
