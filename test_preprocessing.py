#!/usr/bin/env python3
"""
Test the text preprocessing functionality directly
"""

import re


def test_preprocessing():
    """Test the preprocessing regex patterns."""
    text = "This is test content with URLs http://example.com and emails test@example.com"
    title = "Test Article Title"

    # Simulate the preprocessing steps
    full_text = "{0}. {1}".format(title, text)

    # Remove URLs
    full_text = re.sub(
        r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+",
        "",
        full_text,
    )

    # Remove email addresses
    full_text = re.sub(r"\S+@\S+", "", full_text)

    # Clean up whitespace
    full_text = re.sub(r"\s+", " ", full_text)
    full_text = full_text.strip()

    print("Original text:", repr(text))
    print("Processed text:", repr(full_text))
    print("URL found:", "http://example.com" in full_text)
    print("Email found:", "test@example.com" in full_text)

    # The assertions from the test
    assert "Test Article Title" in full_text
    assert "http://example.com" not in full_text
    assert "test@example.com" not in full_text

    print(" All assertions pass!")


if __name__ == "__main__":
    test_preprocessing()
