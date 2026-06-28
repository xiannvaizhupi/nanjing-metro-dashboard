#!/usr/bin/env python3
"""Lightweight parser checks for the Nanjing Metro passenger-flow fetcher."""

from datetime import date

from fetch_data import infer_entry_year, parse_passenger_flow, parse_weibo_flow


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


def test_parse_official_homepage_text_without_hashtag():
    html = """
    <div class="notice">
      南京地铁2026年6月27日客运量：359.88万，其中：
      1号线：73.12，2号线：58.45，3号线：64.30，4号线：17.01，
      5号线：43.22，7号线：29.80，10号线：18.70，S1号线：9.60，
      S2号线：3.51，S3号线：9.75，S6号线：5.42，S7号线：1.33，
      S8号线：11.31，S9号线：2.39（以上单位：万）
    </div>
    """
    entries = parse_passenger_flow(html, source_name="南京地铁官网首页")

    assert_equal(len(entries), 1, "official entry count")
    assert_equal(entries[0]["date"], "2026-06-27", "official date")
    assert_equal(entries[0]["total"], 359.88, "official total")
    assert_equal(entries[0]["lines"]["L1"], 73.12, "official line 1")
    assert_equal(entries[0]["lines"]["S9"], 2.39, "official line S9")


if __name__ == "__main__":
    test_parse_with_explicit_short_year()
    test_infer_year_around_new_year()
    test_parse_official_homepage_text_without_hashtag()
    print("fetch_data parser checks passed.")
