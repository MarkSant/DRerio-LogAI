"""Unit tests for the scanner's unaccented ("word") heuristic.

The accent heuristic that carried the first three migration phases is blind to
Portuguese written without accents, and the ratchet built on top of it inherited
that blindness: ``coordinators/`` sat inside the ratchet while publishing
"Aguardando sinal externo..." as status text. These tests pin the second pass
that closes it, and -- just as important -- pin the exemptions that keep it
quiet enough to stay switched on.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from i18n_scan import (  # noqa: E402
    PORTUGUESE_WORDS,
    classify,
    is_allowlisted,
    portuguese_words_in,
    scan_file,
)

# --- the word pass finds what the accent pass cannot ------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Salvar projeto",
        "Nenhum video encontrado",
        "Gravando",
        "Aguardando sinal externo",
        "Carregando detector...",
        "Iniciando captura...",
        "Falha ao abrir a pasta",
        "Selecione o Dia:",
        "camera_index deve ser <= 10 (limite de dispositivos)",
    ],
)
def test_unaccented_portuguese_is_detected(text: str) -> None:
    assert classify(text) == "word", f"{text!r} slipped through the word pass"


def test_accented_portuguese_still_reports_as_accent() -> None:
    """The original pass keeps priority, so existing findings do not change kind."""
    assert classify("Não foi possível") == "accent"


# --- and stays quiet on English ---------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Save project",
        "No video found",
        "Recording",
        "Waiting for external signal",
        "Failed to open the folder",
        # Words deliberately excluded from PORTUGUESE_WORDS because English uses
        # them too. Each of these was a real false positive during the sweep.
        "CPU: 8 cores (12.5% used)",
        "OpenVINO uses all logical cores",
        "The anterior region of the larva",
        "Compare taxa across the dataset",
        "She ate the whole sample",
        "Use the index to look it up",
        "Total: 10",
    ],
)
def test_english_is_not_flagged(text: str) -> None:
    assert classify(text) is None, f"false positive on {text!r}"


def test_wordlist_holds_no_english_words() -> None:
    """A word that is also English would make the pass fire on English copy."""
    english = {
        "ate",
        "anterior",
        "area",
        "data",
        "taxa",
        "um",
        "no",
        "do",
        "use",
        "ignore",
        "continue",
        "pause",
        "cores",
        "total",
        "normal",
        "final",
        "index",
        "video",
        "camera",
        "so",
        "sim",
    }
    assert not (PORTUGUESE_WORDS & english), (
        "these are English as well as Portuguese and would cause false positives: "
        f"{sorted(PORTUGUESE_WORDS & english)}"
    )


# --- identifier exemption ----------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "tempo_no_{}_s",
        "distancia_no_{}_cm",
        "duracao_total_congelamento_no_{}_s",
        "grupo_id",
        "test_project/group1_cobaia1",
        "data_transformer.geotaxis_rename.error",
    ],
)
def test_identifiers_are_not_interface_text(text: str) -> None:
    """Column templates, dict keys, paths and structlog events are not copy."""
    assert portuguese_words_in(text) == ()


def test_identifier_exemption_does_not_reach_the_accent_pass() -> None:
    """A lowercase accented literal must still be reported.

    The exemption is a word-pass concession; widening it to the accent pass
    could let a real string back in while the ratchet stayed green.
    """
    assert classify("configuração") == "accent"


# --- line-level pragma -------------------------------------------------------


def test_line_marker_exempts_only_its_own_line(tmp_path: Path) -> None:
    source = tmp_path / "sample.py"
    source.write_text(
        "def f(value):\n"
        '    if value == "sem dia":  # i18n: not-ui — stored spelling\n'
        '        return "Nenhum video"\n',
        encoding="utf-8",
    )

    findings = scan_file(source, ())
    texts = [f.text for f in findings]

    assert "sem dia" not in texts, "the marked comparison should be exempt"
    assert "Nenhum video" in texts, "the next line must still be reported"


# --- allowlist exact matching ------------------------------------------------


def test_exact_pattern_matches_only_the_whole_literal() -> None:
    allowlist = ("=grupo",)
    assert is_allowlisted("grupo", allowlist)
    assert not is_allowlisted("Selecione o grupo experimental", allowlist)


def test_substring_pattern_still_matches_a_prefix() -> None:
    allowlist = ("Grupo_",)
    assert is_allowlisted("Grupo_{group}", allowlist)
    assert is_allowlisted("Grupo_Sem_Grupo", allowlist)


def test_repo_allowlist_keeps_common_words_exact() -> None:
    """Regression guard for the blind spot this sweep uncovered.

    As a substring, ``grupo`` exempted every sentence containing the word and
    hid seven real Portuguese strings -- two of them multi-paragraph wizard
    tooltips -- while ``i18n_scan.py`` reported ``TOTAL: 0``.
    """
    from i18n_scan import load_allowlist

    patterns = load_allowlist()
    for word in ("grupo", "resumo"):
        assert f"={word}" in patterns, f"{word!r} must be an exact-match pattern"
        assert word not in patterns, f"{word!r} must not be a bare substring pattern"
