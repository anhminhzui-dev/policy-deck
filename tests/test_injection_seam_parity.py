"""The injection seam must agree with the shipped classifier, row for row.

`score.py` carries `_classify_against`, a small re-implementation of `classifier.classify` that
exists only so a test can swap the rule table in memory. Its docstring claims it "mirrors
`classify` step for step". That claim went untested and was false: it skipped the per-rule
haystack selection, so `DENY-001` was matched against the raw text instead of the quote-masked
copy. A risky phrase quoted inside a commit message therefore scored as `DENY` through the seam
and as `ALLOW` on the normal path — the fitted deck read `fp=24` one way and `fp=8` the other,
for the identical rule table.

That is worse than an ordinary bug, because every number produced through the seam — including
the planted-regression counts this package publishes — was measured on a classifier the package
does not ship. The tests below close it by comparison rather than by assertion: score every
shipped deck both ways and require the two paths to return the same verdict and the same rule id
for every row.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from policy_deck import classify
from policy_deck.deck import DeckRow, load_deck
from policy_deck.policy import RULES
from policy_deck.score import _classify_against, score_rows

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DECK_NAMES = ("synthetic_v1.jsonl", "holdout_v1.jsonl", "hard_cases.jsonl")


def _rows(deck_name: str) -> list[DeckRow]:
    return load_deck(_REPO_ROOT / "decks" / deck_name)


@pytest.mark.parametrize("deck_name", _DECK_NAMES)
def test_every_row_gets_the_same_verdict_through_both_paths(deck_name: str) -> None:
    disagreements: list[tuple[str, str, str, str]] = []
    for row in _rows(deck_name):
        shipped = classify(row.command)
        injected = _classify_against(row.command, RULES, None)
        if (shipped.verdict, shipped.rule_id) != (injected.verdict, injected.rule_id):
            disagreements.append(
                (
                    row.case_id,
                    row.command,
                    f"{shipped.verdict.value}/{shipped.rule_id}",
                    f"{injected.verdict.value}/{injected.rule_id}",
                )
            )
    assert disagreements == [], disagreements


@pytest.mark.parametrize("deck_name", _DECK_NAMES)
def test_the_seam_and_the_normal_path_produce_the_same_receipt(deck_name: str) -> None:
    rows = _rows(deck_name)
    normal = score_rows(rows)
    injected = score_rows(rows, rules=RULES)
    assert (normal.tp, normal.tn, normal.fp, normal.fn, normal.misroute) == (
        injected.tp,
        injected.tn,
        injected.fp,
        injected.fn,
        injected.misroute,
    )


def test_the_quoted_phrase_that_exposed_the_defect_is_allow_on_both_paths() -> None:
    """The exact shape that used to disagree, named as its own case so a regression is legible."""
    command = 'git commit -m "note to self: never type git reset --hard again"'
    assert classify(command).verdict.value == "ALLOW"
    assert _classify_against(command, RULES, None).verdict.value == "ALLOW"


def test_the_seam_still_reports_the_matched_text_from_the_unmasked_command() -> None:
    """Masking is a matching device, not a reporting one: the operator sees the real bytes."""
    command = "g" + "it stash drop"
    injected = _classify_against(command, RULES, None)
    assert injected.rule_id == "DENY-001"
    assert injected.matched_text is not None
    assert injected.matched_text in command.lower()
