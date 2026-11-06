from __future__ import annotations

from autoclip.tiktok_report import parse_content_rows, summarize


def test_parse_rows():
    rows = parse_content_rows(
        "01:00\nCaption satu\nNov 13, 8:00 PM\nEveryone\n0\n10\n2\n"
    )
    assert rows == [{"when": "Nov 13, 8:00 PM", "caption": "Caption satu", "views": 0}]


def test_parse_rows_multiple_and_noise():
    text = (
        "Upload\n"
        "00:34\n"
        "opah nya seram\n"
        "Nov 12, 9:00 PM\n"
        "Everyone\n"
        "1,234\n"
        "12\n"
        "3\n"
        "00:41\n"
        "Nov 11, 7:00 PM\n"
        "Everyone\n"
        "87\n"
        "0\n"
        "0\n"
    )
    rows = parse_content_rows(text)
    assert [(r["caption"], r["views"]) for r in rows] == [
        ("opah nya seram", 1234),
        ("", 87),
    ]


def test_summarize_median():
    rows = [{"caption": "a", "when": "x", "views": 10},
            {"caption": "b", "when": "y", "views": 100},
            {"caption": "c", "when": "z", "views": 30}]
    stats = summarize(rows)
    assert stats == {"n": 3, "median": 30, "max": 100}
