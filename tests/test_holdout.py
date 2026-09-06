"""The holdout deck: composition, pin, and the bars it is scored against.

These tests check the properties that make the holdout worth printing beside the fitted receipt:
it is large enough and mixed enough to be traffic rather than a demo, it reaches every blocking
rule, it rebuilds byte-for-byte from `policy_deck.holdout`, and it is scored against its own
budget rather than the fitted deck's.

What no test can check is the one thing that matters most -- that the rows were written from the
rule titles rather than from the patterns. That is a claim about how the file was made, stated in
the README and in `holdout.py`'s own docstring, and the reader's evidence for it is the receipt:
a deck written from the patterns does not produce 21 false negatives on first contact.
"""

from __future__ import annotations

import json
from pathlib import Path

from policy_deck.deck import deck_sha256, load_deck, serialize
from policy_deck.holdout import build_rows
from policy_deck.score import EXIT_PASS, evaluate_holdout, load_budget

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HOLDOUT_PATH = _REPO_ROOT / "decks" / "holdout_v1.jsonl"
_BUDGET_PATH = _REPO_ROOT / "budget.json"
_DECK_PATH = _REPO_ROOT / "decks" / "synthetic_v1.jsonl"

_ORDINARY_CLASSES = frozenset(
    {
        "build", "test", "lint", "container", "cloud_read", "db_read", "package", "editor",
        "git_read", "misc_read",
    }
)


def test_holdout_file_is_committed_and_parses() -> None:
    assert _HOLDOUT_PATH.exists(), "decks/holdout_v1.jsonl must be committed"
    rows = load_deck(_HOLDOUT_PATH)
    assert 150 <= len(rows) <= 200


def test_holdout_rebuilds_byte_for_byte_from_the_module() -> None:
    on_disk = _HOLDOUT_PATH.read_text(encoding="utf-8")
    assert serialize(build_rows()) == on_disk


def test_holdout_sha_matches_the_pin() -> None:
    budget = json.loads(_BUDGET_PATH.read_text(encoding="utf-8"))
    assert deck_sha256(_HOLDOUT_PATH.read_text(encoding="utf-8")) == budget["holdout_sha256"]
    assert budget["holdout_rows"] == len(load_deck(_HOLDOUT_PATH))


def test_composition_meets_the_stated_shape() -> None:
    rows = load_deck(_HOLDOUT_PATH)
    ordinary = [r for r in rows if r.cls in _ORDINARY_CLASSES]
    risky = [r for r in rows if r.expected != "ALLOW"]
    near_miss = [r for r in rows if r.cls == "near_miss"]
    known_fp = [r for r in rows if r.cls == "known_false_positive"]

    assert len(ordinary) >= 120
    assert len(risky) >= 30
    assert len(near_miss) >= 10
    assert len(known_fp) == 2
    assert all(r.expected == "ALLOW" for r in ordinary + near_miss + known_fp)
    assert len(ordinary) + len(risky) + len(near_miss) + len(known_fp) == len(rows)


def test_ordinary_traffic_spans_many_tool_families() -> None:
    rows = load_deck(_HOLDOUT_PATH)
    families = {r.cls for r in rows if r.cls in _ORDINARY_CLASSES}
    assert families == _ORDINARY_CLASSES
    for family in _ORDINARY_CLASSES:
        assert sum(1 for r in rows if r.cls == family) >= 8, family


def test_every_blocking_rule_is_exercised_by_a_risky_row() -> None:
    rows = load_deck(_HOLDOUT_PATH)
    seen = {r.expected_rule for r in rows if r.expected != "ALLOW"}
    assert {
        "SPEND-001", "SPEND-002", "SPEND-003", "SPEND-004",
        "IRR-001", "IRR-002", "IRR-003", "IRR-004",
        "DENY-001", "DENY-002",
    } <= seen


def test_every_row_carries_a_class_a_verdict_and_a_why() -> None:
    for row in load_deck(_HOLDOUT_PATH):
        assert row.cls.strip() != ""
        assert row.expected in {"ALLOW", "ASK_MONEY", "ASK_IRREVERSIBLE", "DENY"}
        assert len(row.why.strip()) >= 20, row.case_id
        assert row.source == "handwritten"


def test_case_ids_are_unique_and_sorted() -> None:
    rows = load_deck(_HOLDOUT_PATH)
    ids = [r.case_id for r in rows]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))


def test_commands_are_not_duplicated_within_the_holdout() -> None:
    rows = load_deck(_HOLDOUT_PATH)
    assert len({r.command for r in rows}) == len(rows)


def test_overlap_with_the_fitted_deck_is_bounded_and_small() -> None:
    """Zero overlap is not claimed and would not be honest: a few commands (`git status --short
    --branch`, `git stash list`, `git clean -n`) are canonical enough that any independent author
    writes them. What matters is that the holdout is not a re-run of the fitted deck."""
    fitted = {r.command.strip().lower() for r in load_deck(_DECK_PATH)}
    holdout = load_deck(_HOLDOUT_PATH)
    overlap = [r for r in holdout if r.command.strip().lower() in fitted]
    assert len(overlap) <= 10
    assert len(overlap) < len(holdout) // 10


def test_holdout_scores_against_its_own_budget_and_passes() -> None:
    exit_code, receipt, message = evaluate_holdout(_BUDGET_PATH, _HOLDOUT_PATH)
    assert receipt is not None, message
    assert receipt["schema"] == "policy-deck/holdout/1"
    assert exit_code == EXIT_PASS, message
    assert receipt["fn"] == 0
    budget = load_budget(_BUDGET_PATH)
    assert receipt["fp"] <= budget.holdout_fp_budget
    assert receipt["passed"] is True


def test_holdout_false_positives_are_exactly_the_disclosed_over_refusal() -> None:
    _exit_code, receipt, _message = evaluate_holdout(_BUDGET_PATH, _HOLDOUT_PATH)
    assert receipt is not None
    per_class = receipt["per_class"]
    assert isinstance(per_class, dict)
    assert per_class["known_false_positive"]["fp"] == 2
    assert receipt["fp"] == 2


def test_a_budget_without_holdout_keys_reports_an_operational_error(tmp_path: Path) -> None:
    """A missing declaration must not read as a clean holdout run."""
    budget = json.loads(_BUDGET_PATH.read_text(encoding="utf-8"))
    for key in ("holdout", "holdout_sha256"):
        budget.pop(key, None)
    path = tmp_path / "budget.json"
    path.write_text(json.dumps(budget), encoding="utf-8")
    exit_code, receipt, message = evaluate_holdout(path)
    assert exit_code == 2
    assert receipt is None
    assert "no holdout deck" in message
