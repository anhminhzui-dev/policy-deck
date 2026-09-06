"""score_rows() and check_budget() against a tiny, hand-computed in-memory deck.

Six rows, one of each outcome kind (tn, plain tp, fn, fp, misroute, rule_mismatch), chosen so the
answer can be worked out by hand rather than trusted from the implementation under test:

  A  "git status"                        expected ALLOW                       -> tn
  B  "git push --force origin main"      expected ASK_IRREVERSIBLE / IRR-002  -> tp (clean)
  C  "git status"                        expected DENY / DENY-001             -> fn
  D  "rm -rf data"                       expected ALLOW                       -> fp
  E  "git push --force origin main"      expected ASK_MONEY / SPEND-001       -> tp + misroute
  F  "git push --force origin main"      expected ASK_IRREVERSIBLE / IRR-001  -> tp + rule_mismatch

tp = 3 (B, E, F) / tn = 1 (A) / fp = 1 (D) / fn = 1 (C) / misroute = 1 (E) / rule_mismatch = 1 (F)
precision = 3/(3+1) = 0.75, recall = 3/(3+1) = 0.75
"""

from __future__ import annotations

from pathlib import Path

from policy_deck.deck import DeckRow
from policy_deck.score import Budget, check_budget, score_rows

_ROW_A = DeckRow("t-a", "git status", "ALLOW", None, "t", "h", "handwritten", "", False)
_ROW_B = DeckRow(
    "t-b", "git push --force origin main", "ASK_IRREVERSIBLE", "IRR-002", "t", "h",
    "handwritten", "", False,
)
_ROW_C = DeckRow("t-c", "git status", "DENY", "DENY-001", "t", "h", "handwritten", "", False)
_ROW_D = DeckRow("t-d", "rm -rf data", "ALLOW", None, "t", "h", "handwritten", "", False)
_ROW_E = DeckRow(
    "t-e", "git push --force origin main", "ASK_MONEY", "SPEND-001", "t", "h",
    "handwritten", "", False,
)
_ROW_F = DeckRow(
    "t-f", "git push --force origin main", "ASK_IRREVERSIBLE", "IRR-001", "t", "h",
    "handwritten", "", False,
)
_TINY_DECK = [_ROW_A, _ROW_B, _ROW_C, _ROW_D, _ROW_E, _ROW_F]


def _budget(**overrides: int) -> Budget:
    base = dict(
        deck="decks/synthetic_v1.jsonl",
        deck_sha256="0" * 64,
        generator_seed=20260906,
        rows=6,
        fp_budget=0,
        fn_budget=0,
        misroute_budget=0,
        hard_cases="decks/hard_cases.jsonl",
        hard_case_mismatch_budget=0,
    )
    base.update(overrides)
    return Budget(**base)


def test_hand_computed_tallies() -> None:
    result = score_rows(_TINY_DECK)
    assert result.rows == 6
    assert result.tp == 3
    assert result.tn == 1
    assert result.fp == 1
    assert result.fn == 1
    assert result.misroute == 1
    assert result.rule_mismatch == 1


def test_hand_computed_precision_and_recall() -> None:
    result = score_rows(_TINY_DECK)
    assert result.precision == 0.75
    assert result.recall == 0.75


def test_precision_and_recall_are_zero_when_denominator_is_zero() -> None:
    only_allow = [_ROW_A]
    result = score_rows(only_allow)
    assert result.tp == 0
    assert result.fp == 0
    assert result.fn == 0
    assert result.precision == 0.0
    assert result.recall == 0.0


def test_per_class_bucket_matches_the_tally() -> None:
    result = score_rows(_TINY_DECK)
    bucket = result.per_class["t"]
    assert bucket["total"] == 6
    assert bucket["fp"] == 1
    assert bucket["fn"] == 1
    assert bucket["misroute"] == 1


def test_per_rule_bucket_tracks_fn_and_misroute() -> None:
    result = score_rows(_TINY_DECK)
    assert result.per_rule["DENY-001"]["fn"] == 1
    assert result.per_rule["SPEND-001"]["misroute"] == 1
    assert result.per_rule["IRR-002"]["fn"] == 0
    assert result.per_rule["IRR-002"]["misroute"] == 0


def test_failures_list_names_case_id_kind_and_command() -> None:
    result = score_rows(_TINY_DECK)
    kinds = {f["case_id"]: f["kind"] for f in result.failures}
    assert kinds["t-c"] == "fn"
    assert kinds["t-d"] == "fp"
    assert kinds["t-e"] == "misroute"
    assert "t-a" not in kinds
    assert "t-b" not in kinds
    assert "t-f" not in kinds  # rule_mismatch is reported, not a scored failure kind


def test_check_budget_returns_empty_when_every_bar_is_met() -> None:
    result = score_rows(_TINY_DECK)
    reasons = check_budget(result, _budget(fp_budget=1, fn_budget=1, misroute_budget=1))
    assert reasons == []


def test_check_budget_names_every_missed_metric() -> None:
    result = score_rows(_TINY_DECK)
    reasons = check_budget(result, _budget(fp_budget=0, fn_budget=0, misroute_budget=0))
    joined = " | ".join(reasons)
    assert "fp 1 exceeds budget 0" in joined
    assert "fn 1 exceeds budget 0" in joined
    assert "misroute 1 exceeds budget 0" in joined


def test_check_budget_includes_hard_case_mismatch_when_given() -> None:
    clean = score_rows([_ROW_A])
    hard_with_a_miss = score_rows([_ROW_C])  # one fn
    reasons = check_budget(
        clean, _budget(hard_case_mismatch_budget=0), hard=hard_with_a_miss
    )
    assert any("hard_case_mismatch" in r for r in reasons)


def test_load_budget_round_trips_the_shipped_budget_file(tmp_path: Path) -> None:
    from policy_deck.score import load_budget

    repo_root = Path(__file__).resolve().parent.parent
    budget = load_budget(repo_root / "budget.json")
    assert budget.rows == 1260
    assert budget.fn_budget == 0
    assert len(budget.deck_sha256) == 64
