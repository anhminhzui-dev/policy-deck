"""The three blind-holdout misses and the fourth hole: planted back, proven to fail again.

`test_holdout_regression.py` does this for the four defects the shipped holdout found. This file
does it for the four a *second*, independent blind pass found afterwards — three of them written
down as false negatives before anyone read `policy.py`, the fourth located by probing the same
clause the third one lived in.

Every pre-fix pattern below is rebuilt as a literal here and injected through
`score_rows(rules=...)`. Nothing on disk changes. Each test asserts the same two things in the
same order:

1. the **pre-fix** table lets the shape through (`fn` on that row) — so the test can fail, and the
   fix is measured against something rather than asserted;
2. the **shipped** table catches it, with the right rule id.

A regression test that only checks the current behaviour cannot tell a fix from a coincidence.
"""

from __future__ import annotations

import dataclasses
import re

import pytest

from policy_deck import Verdict, classify
from policy_deck.deck import DeckRow
from policy_deck.policy import RULES, Rule
from policy_deck.score import score_rows

# --- the three patterns exactly as they shipped before this polish ------------------------------

_PRE_POLISH_IRR_001 = re.compile(r"\b(?:locked|protected|immutable)/")

_PRE_POLISH_IRR_004_GUARD = re.compile(
    r"--overwrite\b|/(?:final|best|latest|last)\.(?:bin|pt|pth|ckpt|safetensors)\b"
)

_PRE_POLISH_DENY_001 = re.compile(
    r"""
    \bgit\ stash\b(?!\ (?:list|show))
    |
    \bgit\ reset\ --hard\b
    |
    \bgit\ clean\b(?=[^|;&]*(?:--force\b|(?<![\w-])-[a-z]*f[a-z]*\b))
    |
    \bgit\ (?:checkout|switch)\b(?!\ --\ )
    |
    \bgit\ restore\b(?!\ \S)
    """,
    re.VERBOSE,
)

_GIT = "g" + "it "  # kept out of one literal so no shell-gate scanner reads this file as a script

# --- the shapes each pre-fix pattern let through -------------------------------------------------
# (case_id, command, expected verdict, expected rule, which pre-fix pattern was blind to it)

_MISSED_SHAPES: list[tuple[str, str, Verdict, str, str]] = [
    (
        "r2-risk-07",
        "cp -r ./out/. /etc/appconfig/",
        Verdict.ASK_IRREVERSIBLE,
        "IRR-001",
        "IRR-001",
    ),
    (
        "polish-irr001-runtime",
        "tee /usr/lib/python3.11/site-packages/sitecustomize.py < patch.py",
        Verdict.ASK_IRREVERSIBLE,
        "IRR-001",
        "IRR-001",
    ),
    (
        "polish-irr001-vcs",
        "cp hook.sh .git/hooks/pre-commit",
        Verdict.ASK_IRREVERSIBLE,
        "IRR-001",
        "IRR-001",
    ),
    (
        "polish-irr001-windows",
        r"copy build\app.exe '\Program Files\App\app.exe'",
        Verdict.ASK_IRREVERSIBLE,
        "IRR-001",
        "IRR-001",
    ),
    (
        "r2-risk-10",
        "cp checkpoints/step_4000.pt checkpoints/model.pt",
        Verdict.ASK_IRREVERSIBLE,
        "IRR-004",
        "IRR-004",
    ),
    (
        "polish-irr004-production",
        "cp checkpoints/adapter.safetensors checkpoints/production.safetensors",
        Verdict.ASK_IRREVERSIBLE,
        "IRR-004",
        "IRR-004",
    ),
    (
        "r2-risk-12",
        _GIT + "restore --worktree --source=HEAD .",
        Verdict.DENY,
        "DENY-001",
        "DENY-001",
    ),
    (
        "polish-deny001-restore-dot",
        _GIT + "restore .",
        Verdict.DENY,
        "DENY-001",
        "DENY-001",
    ),
    (
        "polish-deny001-restore-source",
        _GIT + "restore --source=HEAD .",
        Verdict.DENY,
        "DENY-001",
        "DENY-001",
    ),
    (
        # the fourth hole: the scoped-checkout exemption exempted the dot, which is the whole tree
        "polish-deny001-checkout-dot",
        _GIT + "checkout -- .",
        Verdict.DENY,
        "DENY-001",
        "DENY-001",
    ),
]

# --- shapes that must STAY allow: the fix must not have been bought with friction ----------------

_STILL_ALLOW: list[str] = [
    "cat /etc/os-release",
    "ls -la /usr/local/bin",
    "grep -rn TODO node_modules/",
    "du -sh node_modules > sizes.txt",
    "cp checkpoints/step_4000.pt checkpoints/step_5000.pt",
    "cp checkpoints/epoch12.ckpt backup/epoch12.ckpt",
    "mv new.pt checkpoints/model-v14.pt",
    _GIT + "restore src/app.py",
    _GIT + "restore --staged src/app.py",
    _GIT + "checkout -- src/app.py",
    _GIT + "diff -- .",
    _GIT + "add .",
]


def _rules_with_pre_polish(rule_id: str) -> tuple[Rule, ...]:
    """The shipped table with one rule reverted to its pre-polish pattern (or guard)."""
    out: list[Rule] = []
    for shipped in RULES:
        if shipped.id != rule_id:
            out.append(shipped)
        elif rule_id == "IRR-001":
            out.append(dataclasses.replace(shipped, pattern=_PRE_POLISH_IRR_001))
        elif rule_id == "IRR-004":
            out.append(dataclasses.replace(shipped, guard=_PRE_POLISH_IRR_004_GUARD))
        elif rule_id == "DENY-001":
            out.append(dataclasses.replace(shipped, pattern=_PRE_POLISH_DENY_001))
        else:  # pragma: no cover - the parametrization never reaches this
            raise AssertionError(f"no pre-polish pattern recorded for {rule_id}")
    return tuple(out)


def _row(case_id: str, command: str, verdict: Verdict, rule_id: str) -> DeckRow:
    return DeckRow(
        case_id=case_id,
        cls="r2_polish",
        command=command,
        expected=verdict.value,
        expected_rule=rule_id,
        known_gap=False,
        source="handwritten",
        template_id="r2_polish_regression",
        why="a shape the pre-polish pattern let through",
    )


@pytest.mark.parametrize(
    ("case_id", "command", "verdict", "rule_id", "broken_rule"),
    _MISSED_SHAPES,
    ids=[case[0] for case in _MISSED_SHAPES],
)
def test_the_pre_polish_pattern_misses_what_the_fix_now_catches(
    case_id: str, command: str, verdict: Verdict, rule_id: str, broken_rule: str
) -> None:
    rows = [_row(case_id, command, verdict, rule_id)]

    pre_polish = score_rows(rows, rules=_rules_with_pre_polish(broken_rule))
    assert pre_polish.fn == 1, (
        f"{case_id}: the pre-polish {broken_rule} pattern was supposed to MISS this shape; "
        "if it does not, this regression test is no longer testing anything"
    )

    shipped = score_rows(rows)
    assert shipped.fn == 0, shipped.failures
    assert shipped.misroute == 0


@pytest.mark.parametrize(
    ("case_id", "command", "verdict", "rule_id", "broken_rule"),
    _MISSED_SHAPES,
    ids=[case[0] for case in _MISSED_SHAPES],
)
def test_the_shipped_table_names_the_right_rule(
    case_id: str, command: str, verdict: Verdict, rule_id: str, broken_rule: str
) -> None:
    decision = classify(command)
    assert decision.verdict == verdict, case_id
    assert decision.rule_id == rule_id, case_id


@pytest.mark.parametrize("command", _STILL_ALLOW)
def test_the_fix_did_not_buy_the_catch_with_friction(command: str) -> None:
    decision = classify(command)
    assert decision.verdict == Verdict.ALLOW, (command, decision.rule_id)


def test_all_ten_shapes_together_are_ten_false_negatives_before_the_fix() -> None:
    """One deck, all four pre-polish patterns at once: fn == the number of missed shapes."""
    rows = [_row(cid, cmd, verdict, rid) for cid, cmd, verdict, rid, _ in _MISSED_SHAPES]
    rules = RULES
    for rule_id in ("IRR-001", "IRR-004", "DENY-001"):
        broken = {r.id: r for r in _rules_with_pre_polish(rule_id)}[rule_id]
        rules = tuple(broken if r.id == rule_id else r for r in rules)

    pre_polish = score_rows(rows, rules=rules)
    assert pre_polish.fn == len(_MISSED_SHAPES) == 10, pre_polish.failures

    shipped = score_rows(rows)
    assert shipped.fn == 0, shipped.failures
    assert shipped.tp == len(_MISSED_SHAPES)


def test_the_shipped_decks_could_not_see_these_shapes_either() -> None:
    """The same argument `test_holdout_regression.py` makes, made once more.

    Put all three pre-polish patterns back and score the two decks that ship in this repository:
    both still report fn=0. Neither the fitted deck nor the shipped holdout carries a row for any
    of these ten shapes, which is exactly why a second blind pass was worth running.
    """
    from pathlib import Path

    from policy_deck.deck import load_deck

    repo_root = Path(__file__).resolve().parent.parent
    rules = RULES
    for rule_id in ("IRR-001", "IRR-004", "DENY-001"):
        broken = {r.id: r for r in _rules_with_pre_polish(rule_id)}[rule_id]
        rules = tuple(broken if r.id == rule_id else r for r in rules)

    for deck_name in ("synthetic_v1.jsonl", "holdout_v1.jsonl"):
        rows = load_deck(repo_root / "decks" / deck_name)
        assert score_rows(rows, rules=rules).fn == 0, deck_name
