"""The disclosed over-refusal is labelled ALLOW and counted as a false positive.

The README says a branch-name `checkout`/`switch` is a known false positive "priced into the
false-positive budget". Before this change the deck labelled those same commands `DENY`, which
scored the package's own admitted over-refusal as a correct catch and produced fp=0. A deck that
relabels a disclosed defect into a success is not a measurement.

So: the rows stay in the deck, the label becomes ALLOW, the fitted receipt reports a non-zero fp
under budget, and the README sentence is now literally true. The classifier's behaviour is
unchanged -- it still refuses these commands, on purpose, for the reason the README gives.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from policy_deck import Verdict, classify
from policy_deck.deck import (
    CLASS_PLAN,
    DESTRUCTIVE_SHAPES,
    KNOWN_FALSE_POSITIVE_SHAPES,
    load_deck,
)
from policy_deck.score import evaluate, load_budget

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DECK_PATH = _REPO_ROOT / "decks" / "synthetic_v1.jsonl"
_BUDGET_PATH = _REPO_ROOT / "budget.json"
_HARD_PATH = _REPO_ROOT / "decks" / "hard_cases.jsonl"


def test_the_deck_carries_a_known_false_positive_class_expecting_allow() -> None:
    plan = {cls: (count, expected) for cls, count, expected in CLASS_PLAN}
    assert plan["known_false_positive"] == (8, "ALLOW")


def test_branch_operations_are_labelled_allow_in_the_deck() -> None:
    rows = [r for r in load_deck(_DECK_PATH) if r.cls == "known_false_positive"]
    assert len(rows) == 8
    for row in rows:
        assert row.expected == "ALLOW", row.case_id
        assert row.expected_rule is None
        assert row.known_gap is True
        assert "false positive" in row.why


def test_no_destructive_git_row_is_a_bare_branch_operation() -> None:
    """The DENY side of the deck must contain only shapes that really do discard work."""
    for shape in DESTRUCTIVE_SHAPES:
        assert not shape.startswith("git switch"), shape
        assert shape != "git checkout", shape
    rows = load_deck(_DECK_PATH)
    for row in rows:
        if row.cls != "destructive_git":
            continue
        assert not row.command.startswith("git switch"), row.command
        assert row.command != "git checkout", row.command


@pytest.mark.parametrize("command", KNOWN_FALSE_POSITIVE_SHAPES)
def test_the_classifier_still_refuses_them_which_is_why_they_are_false_positives(
    command: str,
) -> None:
    decision = classify(command)
    assert decision.verdict == Verdict.DENY
    assert decision.rule_id == "DENY-001"


def test_the_fitted_receipt_reports_a_non_zero_fp_under_budget() -> None:
    exit_code, receipt, message = evaluate(_DECK_PATH, _BUDGET_PATH, _HARD_PATH)
    assert receipt is not None, message
    budget = load_budget(_BUDGET_PATH)
    assert receipt["fp"] > 0, "fp=0 on a self-authored deck is the finding, not the result"
    assert receipt["fp"] <= budget.fp_budget
    assert receipt["fn"] == 0
    assert exit_code == 0
    per_class = receipt["per_class"]
    assert isinstance(per_class, dict)
    assert per_class["known_false_positive"]["fp"] == receipt["fp"]


def test_the_readme_sentence_about_pricing_it_into_the_budget_is_true() -> None:
    """The README claims the over-refusal is priced into the false-positive budget. That is only
    true if the deck actually charges it there, which is what this asserts."""
    import re

    readme = re.sub(r"\s+", " ", (_REPO_ROOT / "README.md").read_text(encoding="utf-8"))
    assert "priced into the false-positive budget" in readme
    budget = json.loads(_BUDGET_PATH.read_text(encoding="utf-8"))
    _exit_code, receipt, _message = evaluate(_DECK_PATH, _BUDGET_PATH, _HARD_PATH)
    assert receipt is not None
    charged = receipt["per_class"]["known_false_positive"]["fp"]
    assert charged == 8
    assert charged < budget["fp_budget"]
