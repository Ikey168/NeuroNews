import pytest

from neuronews.ml.validation.input_validator import InputValidator, ValidationError


def test_validate_success():
    v = InputValidator()
    va = v.validate("Title", "Some content long enough")
    assert va.title == "Title"
    assert va.content.startswith("Some content")


@pytest.mark.parametrize(
    "title,content",
    [
        (None, "content"),
        ("Ti", "Proper content body"),  # too short title
        ("Title", "shrt"),  # too short content
    ],
)
def test_validate_failures(title, content):
    v = InputValidator()
    with pytest.raises(ValidationError):
        v.validate(title, content)


def test_truncation():
    v = InputValidator(max_total_len=20)
    content = "x" * 100
    va = v.validate("Title", content)
    assert len(va.content) + len(va.title) <= 20
