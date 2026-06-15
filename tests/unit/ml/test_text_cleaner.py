"""Tests for src/ml/preprocessing/text_cleaner.py."""

import os
import sys

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from ml.preprocessing.text_cleaner import clean  # noqa: E402


def test_collapses_whitespace():
    title, content = clean("Hello    World", "foo\n\nbar\t baz")
    assert title == "Hello World"
    assert content == "foo bar baz"


def test_strips_edges():
    title, content = clean("  padded  ", "  text  ")
    assert title == "padded"
    assert content == "text"


def test_handles_none():
    assert clean(None, None) == ("", "")


def test_handles_empty():
    assert clean("", "") == ("", "")


def test_mixed_none_and_value():
    title, content = clean(None, "  a  b  ")
    assert title == ""
    assert content == "a b"
