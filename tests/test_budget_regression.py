"""The scorer must be able to fail: a widened rule and a dropped rule each miss the budget.

Both plants build a modified rule tuple in memory (`dataclasses.replace` / a filtered tuple) and
pass it through `score.evaluate`'s injection seam (`rules=`) -- nothing on disk is ever edited.
Without the clean-table control this proves nothing; without the two plants the control passing
proves nothing either.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from policy_deck import RULES
from policy_deck.score import EXIT_BUDGET_MISSED, EXIT_PASS, evaluate

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DECK_PATH = _REPO_ROOT / "decks" / "synthetic_v1.jsonl"
_BUDGET_PATH = _REPO_ROOT / "budget.json"
_HARD_PATH = _REPO_ROOT / "decks" / "hard_cases.jsonl"


def _widen_rule_to_match_everything(rule_id: str) -> tuple:
    """Replace one rule's pattern with `.*` and drop its guard -- it now fires on every row."""
    return tuple(
        dataclasses.replace(r, pattern=re.compile(r".*"), guard=None) if r.id == rule_id else r
        for r in RULES
    )


def _drop_rule(rule_id: str) -> tuple:
    """A rule table missing one rule -- whatever it used to catch now slips through."""
    return tuple(r for r in RULES if r.id != rule_id)


def test_shipped_table_passes_the_budget() -> None:
    exit_code, receipt, _message = evaluate(_DECK_PATH, _BUDGET_PATH, _HARD_PATH, rules=None)
    assert exit_code == EXIT_PASS
    assert receipt is not None
    assert receipt["passed"] is True
    assert receipt["reasons"] == []


def test_over_broad_rule_pushes_fp_past_budget() -> None:
    widened = _widen_rule_to_match_everything("SPEND-001")
    exit_code, receipt, message = evaluate(_DECK_PATH, _BUDGET_PATH, _HARD_PATH, rules=widened)
    assert exit_code == EXIT_BUDGET_MISSED
    assert receipt is not None
    assert receipt["passed"] is False
    assert any("fp" in reason for reason in receipt["reasons"])
    assert receipt["fp"] > 36
    assert "fp" in message.lower() or "FAIL" in message


def test_dropped_rule_pushes_fn_past_budget() -> None:
    without_deny_001 = _drop_rule("DENY-001")
    exit_code, receipt, message = evaluate(
        _DECK_PATH, _BUDGET_PATH, _HARD_PATH, rules=without_deny_001
    )
    assert exit_code == EXIT_BUDGET_MISSED
    assert receipt is not None
    assert receipt["passed"] is False
    assert any("fn" in reason for reason in receipt["reasons"])
    assert receipt["fn"] > 0
    assert "fn" in message.lower() or "FAIL" in message


def test_dropped_rule_specifically_loses_the_destructive_git_class() -> None:
    """The eight destructive_git rows are exactly what DENY-001 exists to catch."""
    without_deny_001 = _drop_rule("DENY-001")
    _exit_code, receipt, _message = evaluate(
        _DECK_PATH, _BUDGET_PATH, _HARD_PATH, rules=without_deny_001
    )
    assert receipt is not None
    assert receipt["per_class"]["destructive_git"]["fn"] == 8
