"""The four fixed misses, planted back in memory, must fail the holdout again.

This is `test_budget_regression.py`'s idiom pointed at the holdout: the pre-fix pattern for each
of the four rules is rebuilt here as a literal, injected through `score_rows(rules=...)`, and the
holdout is scored against it. Nothing on disk changes. If a future edit quietly narrows one of
these four patterns back, the corresponding assertion below stops holding and this test fails.

The last test in the file is the point of the whole exercise: the *fitted* deck scores fn=0
against the pre-fix table too. The deck that shipped with the package could not see any of these
four misses, because it was generated from the same shapes the patterns were written for. That is
what a holdout is for, stated as an assertion rather than as a paragraph.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from policy_deck.deck import DeckRow, load_deck
from policy_deck.policy import RULES, Rule
from policy_deck.score import score_rows

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HOLDOUT_PATH = _REPO_ROOT / "decks" / "holdout_v1.jsonl"
_DECK_PATH = _REPO_ROOT / "decks" / "synthetic_v1.jsonl"

# --- the four patterns exactly as they shipped before this fix ----------------------------------
_PRE_FIX_DENY_001 = re.compile(
    r"""
    \bgit\ stash\b(?!\ (?:list|show))
    |
    \bgit\ reset\ --hard\b
    |
    \bgit\ clean\b(?=[^|;&]*(?:-f|--force))
    |
    \bgit\ (?:checkout|switch)\b(?!\ --\ )
    |
    \bgit\ restore\b(?!\ \S)
    """,
    re.VERBOSE,
)
_PRE_FIX_DENY_002 = re.compile(
    r"\b(?:set-content|cp|mv|tee)\b.*\.json\b|--output\s+\S+\.json\b|>\s*\S*\.json\b"
)
_PRE_FIX_SPEND_003 = re.compile(r"\baws\s+ec2\b|\bgcloud\s+compute\b|\baz\s+vm\b")
_PRE_FIX_SPEND_003_GUARD = re.compile(r"\b(?:create|apply|scale|delete|run-instances)\b")
_PRE_FIX_SPEND_004 = re.compile(r"\b\w*_job\.py\b|\bcustom-jobs\b")
_PRE_FIX_SPEND_004_GUARD = re.compile(r"--mode[=\s]+submit\b|\bcreate\b")

_PRE_FIX: dict[str, tuple[re.Pattern[str], "re.Pattern[str] | None"]] = {
    "DENY-001": (_PRE_FIX_DENY_001, None),
    "DENY-002": (_PRE_FIX_DENY_002, None),  # guard unchanged; filled in below
    "SPEND-003": (_PRE_FIX_SPEND_003, _PRE_FIX_SPEND_003_GUARD),
    "SPEND-004": (_PRE_FIX_SPEND_004, _PRE_FIX_SPEND_004_GUARD),
}

# The false negatives each pre-fix pattern let through, counted on the holdout deck.
_EXPECTED_PRE_FIX_MISSES: dict[str, int] = {
    "DENY-001": 2,
    "DENY-002": 6,
    "SPEND-003": 6,
    "SPEND-004": 7,
}


def _rules_with_pre_fix(rule_id: str) -> tuple[Rule, ...]:
    pattern, guard = _PRE_FIX[rule_id]
    out: list[Rule] = []
    for shipped in RULES:
        if shipped.id != rule_id:
            out.append(shipped)
            continue
        # DENY-002's guard (the credential field signal) never changed; only its sink did.
        replacement_guard = shipped.guard if rule_id == "DENY-002" else guard
        out.append(dataclasses.replace(shipped, pattern=pattern, guard=replacement_guard))
    return tuple(out)


@pytest.fixture(scope="module")
def holdout_rows() -> list[DeckRow]:
    return load_deck(_HOLDOUT_PATH)


def test_the_shipped_table_has_no_false_negatives_on_the_holdout(
    holdout_rows: list[DeckRow],
) -> None:
    score = score_rows(holdout_rows)
    assert score.fn == 0, score.failures
    assert score.misroute == 0


@pytest.mark.parametrize("rule_id", sorted(_EXPECTED_PRE_FIX_MISSES))
def test_each_pre_fix_pattern_misses_what_the_fix_now_catches(
    rule_id: str, holdout_rows: list[DeckRow]
) -> None:
    score = score_rows(holdout_rows, rules=_rules_with_pre_fix(rule_id))
    assert score.fn == _EXPECTED_PRE_FIX_MISSES[rule_id], score.failures
    assert score.per_rule[rule_id]["fn"] == _EXPECTED_PRE_FIX_MISSES[rule_id]


def test_all_four_pre_fix_patterns_together_miss_twenty_one_rows(
    holdout_rows: list[DeckRow],
) -> None:
    rules = RULES
    for rule_id in _PRE_FIX:
        pattern, guard = _PRE_FIX[rule_id]
        rules = tuple(
            dataclasses.replace(
                r,
                pattern=pattern,
                guard=r.guard if rule_id == "DENY-002" else guard,
            )
            if r.id == rule_id
            else r
            for r in rules
        )
    score = score_rows(holdout_rows, rules=rules)
    assert score.fn == sum(_EXPECTED_PRE_FIX_MISSES.values()) == 21


@pytest.mark.parametrize("rule_id", sorted(_EXPECTED_PRE_FIX_MISSES))
def test_the_fitted_deck_cannot_see_any_of_the_four_misses(rule_id: str) -> None:
    """The whole argument for a holdout, as an assertion: put the broken pattern back and the
    shipped deck still reports zero false negatives, because it was generated from the same
    shapes the pattern was written for."""
    deck_rows = load_deck(_DECK_PATH)
    score = score_rows(deck_rows, rules=_rules_with_pre_fix(rule_id))
    assert score.fn == 0
