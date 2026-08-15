"""Tests for reading ON/OFF intent out of a firmware ACK line."""

from __future__ import annotations

import pytest

from zebtrack.core.services.arduino_ack_semantics import (
    classify_ack,
    describe_inversion,
    edge_ack_is_inverted,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Exact ACK strings emitted by the reference sketch.
        ("Red LED 1 ON", "on"),
        ("Red LED 1 OFF", "off"),
        ("Blue LED ON", "on"),
        ("Blue LED OFF", "off"),
        ("Green LED ON", "on"),
        ("Green LED OFF", "off"),
        ("Red LED 2 ON", "on"),
        ("Red LED 2 OFF", "off"),
        # Portuguese firmwares.
        ("LED verde ligado", "on"),
        ("LED verde desligado", "off"),
        ("Rele acionado, luz acesa", "on"),
        ("Luz apagada", "off"),
    ],
)
def test_classify_ack_reads_reference_firmware(text, expected):
    assert classify_ack(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "   ",
        "Unknown command",  # the sketch's default branch — no ON/OFF claim
        "Arduino is ready.",
        "42",
        "ON OFF",  # ambiguous: both readings present
    ],
)
def test_classify_ack_returns_none_when_not_confident(text):
    assert classify_ack(text) is None


def test_off_inside_word_does_not_false_positive():
    """'ON' must not be read out of the middle of an unrelated word."""
    assert classify_ack("COMMAND ACCEPTED") is None
    assert classify_ack("Monitoring") is None


@pytest.mark.parametrize("text", ["Acesso negado", "Acessando porta", "acessos: 3"])
def test_acesso_is_not_read_as_acesa(text):
    """'ACESSO'/'ACESSANDO' are whole words but mean access, not "lit"."""
    assert classify_ack(text) is None


@pytest.mark.parametrize("text", ["Luz acesa", "LED aceso", "Luzes acesas"])
def test_acesa_variants_still_read_as_on(text):
    assert classify_ack(text) == "on"


def test_desligado_is_not_read_as_ligado():
    """'DESLIGADO' contains 'LIGADO' — the word boundary must keep them apart."""
    assert classify_ack("desligado") == "off"


def test_enter_answered_with_off_is_inverted():
    """Regression: the 2026-08-04 session where Z4 enter answered 'Blue LED OFF'."""
    assert edge_ack_is_inverted("enter", "Blue LED OFF") is True


def test_exit_answered_with_on_is_inverted():
    assert edge_ack_is_inverted("exit", "Green LED ON") is True


@pytest.mark.parametrize(
    ("edge", "ack"),
    [
        ("enter", "Red LED 1 ON"),
        ("exit", "Red LED 1 OFF"),
        ("enter", "Blue LED ON"),
        ("exit", "Blue LED OFF"),
    ],
)
def test_correct_pairing_is_not_flagged(edge, ack):
    """The canonical layout verified live on 2026-08-04 must stay silent."""
    assert edge_ack_is_inverted(edge, ack) is False


@pytest.mark.parametrize("ack", [None, "", "Unknown command", "Arduino is ready."])
def test_unclassifiable_ack_never_flags(ack):
    assert edge_ack_is_inverted("enter", ack) is False
    assert edge_ack_is_inverted("exit", ack) is False


def test_unknown_edge_never_flags():
    assert edge_ack_is_inverted(None, "Blue LED OFF") is False
    assert edge_ack_is_inverted("sideways", "Blue LED OFF") is False


def test_describe_inversion_names_roi_edge_and_token():
    text = describe_inversion("Z4", "enter", 4, "Blue LED OFF")
    assert "Z4" in text
    assert "4" in text
    assert "Blue LED OFF" in text
    assert "switch it ON" in text
