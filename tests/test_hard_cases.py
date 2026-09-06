"""Every hard-case row classifies to its asserted label -- including the five documented gaps."""

from __future__ import annotations

from pathlib import Path

import pytest

from policy_deck import classify
from policy_deck.deck import DeckRow, load_deck

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HARD_CASES_PATH = _REPO_ROOT / "decks" / "hard_cases.jsonl"


def _load_rows() -> list[DeckRow]:
    assert _HARD_CASES_PATH.exists(), "decks/hard_cases.jsonl must be committed"
    return load_deck(_HARD_CASES_PATH)


_ROWS = _load_rows()


def test_hard_cases_file_has_the_expected_row_count() -> None:
    assert 36 <= len(_ROWS) <= 48


def test_hard_cases_cover_every_required_class() -> None:
    required = {
        "obfuscation", "separator", "quoting", "heredoc",
        "flag_flip", "approval", "malformed", "known_gap",
    }
    seen = {row.cls for row in _ROWS}
    assert required <= seen


def test_every_row_is_handwritten_and_sourced_correctly() -> None:
    for row in _ROWS:
        assert row.source == "handwritten"
        assert row.template_id == "handwritten"


def test_every_row_has_a_non_empty_why() -> None:
    for row in _ROWS:
        assert row.why.strip() != "", row.case_id


def test_exactly_five_known_gap_rows() -> None:
    known_gap_rows = [r for r in _ROWS if r.known_gap]
    assert len(known_gap_rows) == 5


@pytest.mark.parametrize("row", [r for r in _ROWS if not r.known_gap], ids=lambda r: r.case_id)
def test_non_known_gap_row_matches_its_asserted_label(row: DeckRow) -> None:
    decision = classify(row.command)
    assert decision.verdict.value == row.expected, row.case_id
    if row.expected_rule is not None:
        assert decision.rule_id == row.expected_rule, row.case_id


@pytest.mark.parametrize("row", [r for r in _ROWS if r.known_gap], ids=lambda r: r.case_id)
def test_known_gap_row_matches_its_documented_current_behaviour(row: DeckRow) -> None:
    """A known_gap row asserts today's behaviour so a future change is caught, not silent."""
    decision = classify(row.command)
    assert decision.verdict.value == row.expected, row.case_id
