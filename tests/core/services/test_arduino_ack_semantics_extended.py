"""
Extended unit tests for arduino_ack_semantics.
"""

from __future__ import annotations

import pytest

from zebtrack.core.services.arduino_ack_semantics import (
    classify_ack,
    describe_inversion,
    edge_ack_is_inverted,
)


@pytest.mark.parametrize(
    "ack_text,expected",
    [
        ("Green LED ON", "on"),
        ("LED 1 LIGADO", "on"),
        ("Luz ACESA", "on"),
        ("Blue LED OFF", "off"),
        ("LED 1 DESLIGADO", "off"),
        ("Luz APAGADA", "off"),
        (None, None),
        ("", None),
        ("OK", None),
        ("Turned ON and OFF simultaneously", None),  # ambiguous
    ],
)
def test_classify_ack(ack_text: str | None, expected: str | None):
    assert classify_ack(ack_text) == expected


@pytest.mark.parametrize(
    "edge,ack_text,expected_inverted",
    [
        ("enter", "LED ON", False),
        ("enter", "LED OFF", True),
        ("exit", "LED OFF", False),
        ("exit", "LED ON", True),
        ("enter", "OK", False),
        ("exit", "OK", False),
        ("invalid_edge", "LED OFF", False),
        (None, "LED OFF", False),
    ],
)
def test_edge_ack_is_inverted(edge: str | None, ack_text: str | None, expected_inverted: bool):
    assert edge_ack_is_inverted(edge, ack_text) is expected_inverted


def test_describe_inversion():
    desc_enter = describe_inversion("ROI_1", "enter", 1, "LED OFF")
    assert "ROI_1" in desc_enter
    assert "token 1" in desc_enter
    assert "LED OFF" in desc_enter
    assert "ON" in desc_enter

    desc_exit = describe_inversion("ROI_1", "exit", 2, "LED ON")
    assert "ROI_1" in desc_exit
    assert "token 2" in desc_exit
    assert "LED ON" in desc_exit
    assert "OFF" in desc_exit
