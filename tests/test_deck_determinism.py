"""Two generations of the same seed are byte-identical, and the shipped sha is the pinned one."""

from __future__ import annotations

import json
from pathlib import Path

from policy_deck.deck import (
    CLASS_PLAN,
    DEFAULT_ROWS,
    DEFAULT_SEED,
    deck_sha256,
    generate,
    serialize,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_two_generations_are_byte_identical() -> None:
    first = serialize(generate(seed=DEFAULT_SEED))
    second = serialize(generate(seed=DEFAULT_SEED))
    assert first == second


def test_different_seed_changes_the_output() -> None:
    default_text = serialize(generate(seed=DEFAULT_SEED))
    other_text = serialize(generate(seed=DEFAULT_SEED + 1))
    assert default_text != other_text


def test_generated_row_count_matches_class_plan_at_default_rows() -> None:
    rows = generate(seed=DEFAULT_SEED, rows=DEFAULT_ROWS)
    assert len(rows) == DEFAULT_ROWS
    assert len(rows) == sum(count for _, count, _ in CLASS_PLAN)


def test_generated_deck_honours_class_plan_exactly() -> None:
    rows = generate()
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.cls] = counts.get(row.cls, 0) + 1
    for cls, expected_count, expected_verdict in CLASS_PLAN:
        assert counts.get(cls) == expected_count, cls
        class_rows = [r for r in rows if r.cls == cls]
        assert all(r.expected == expected_verdict for r in class_rows), cls


def test_case_ids_are_unique() -> None:
    rows = generate()
    ids = [r.case_id for r in rows]
    assert len(ids) == len(set(ids))


def test_output_is_sorted_by_case_id() -> None:
    rows = generate()
    ids = [r.case_id for r in rows]
    assert ids == sorted(ids)


def test_every_rule_id_appears_at_least_once_among_blocked_rows() -> None:
    expected_rule_ids = {
        "SPEND-001", "SPEND-002", "SPEND-003", "SPEND-004",
        "IRR-001", "IRR-002", "IRR-003", "IRR-004",
        "DENY-001", "DENY-002",
    }
    rows = generate()
    seen = {r.expected_rule for r in rows if r.expected_rule is not None}
    assert expected_rule_ids <= seen


def test_verdict_mix_matches_the_published_shape() -> None:
    rows = generate()
    allow = sum(1 for r in rows if r.expected == "ALLOW")
    blocked = sum(1 for r in rows if r.expected != "ALLOW")
    assert allow == 1220
    assert blocked == 40


def test_serialized_bytes_use_lf_and_end_with_one_trailing_newline() -> None:
    text = serialize(generate())
    assert "\r" not in text
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def test_each_line_is_compact_sorted_key_json() -> None:
    """Structural separators are compact (no space after ',' or ':'); prose fields may contain
    either character freely -- the check is round-tripping through the exact dumps() call the
    contract specifies, not a naive substring search that a "why" sentence could trip."""
    text = serialize(generate(seed=DEFAULT_SEED, rows=20))
    for line in text.rstrip("\n").split("\n"):
        obj = json.loads(line)
        assert list(obj.keys()) == sorted(obj.keys())
        expected = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        assert line == expected


def test_shipped_deck_sha_matches_the_pinned_budget() -> None:
    deck_path = _REPO_ROOT / "decks" / "synthetic_v1.jsonl"
    budget_path = _REPO_ROOT / "budget.json"
    assert deck_path.exists(), "decks/synthetic_v1.jsonl must be committed"
    assert budget_path.exists(), "budget.json must be committed"

    deck_text = deck_path.read_text(encoding="utf-8")
    actual_sha = deck_sha256(deck_text)
    budget = json.loads(budget_path.read_text(encoding="utf-8"))
    assert actual_sha == budget["deck_sha256"]


def test_shipped_deck_regenerates_byte_for_byte_from_the_pinned_seed() -> None:
    """The buyer's own kill test: 'regenerate and re-run' must reproduce the shipped file."""
    deck_path = _REPO_ROOT / "decks" / "synthetic_v1.jsonl"
    on_disk = deck_path.read_text(encoding="utf-8")
    regenerated = serialize(generate(seed=DEFAULT_SEED, rows=DEFAULT_ROWS))
    assert regenerated == on_disk
