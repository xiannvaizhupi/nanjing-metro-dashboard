#!/usr/bin/env python3
"""Lightweight parser checks for the Nanjing Metro passenger-flow fetcher."""

from datetime import date

from fetch_data import infer_entry_year, parse_weibo_flow


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


if __name__ == "__main__":
    test_parse_with_explicit_short_year()
    test_infer_year_around_new_year()
    print("fetch_data parser checks passed.")
