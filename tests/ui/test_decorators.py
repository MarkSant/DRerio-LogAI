"""Tests for UI decorators."""

from zebtrack.ui.decorators import deprecated, public_api


def test_public_api_marks_wrapper():
    @public_api
    def sample(x):
        return x + 1

    assert getattr(sample, "__public_api__", False) is True
    assert sample(1) == 2
    assert sample.__name__ == "sample"


def test_deprecated_marks_wrapper_and_info():
    @deprecated(reason="legacy", version="v1.0", alternative="new")
    def old():
        return "ok"

    assert getattr(old, "__deprecated__", False) is True
    info = getattr(old, "__deprecation_info__", {})
    assert info["reason"] == "legacy"
    assert info["version"] == "v1.0"
    assert info["alternative"] == "new"
    assert old() == "ok"
