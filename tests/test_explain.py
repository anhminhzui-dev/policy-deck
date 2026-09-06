"""explain(): a full per-rule trace, plus the JSON and text renderings built on top of it."""

from __future__ import annotations

from policy_deck import RULES, Verdict, explain, explanation_to_dict, format_explanation


def test_trace_has_one_entry_per_rule_in_table_order() -> None:
    explanation = explain("git status")
    assert len(explanation.traces) == 11
    assert [t.rule_id for t in explanation.traces] == [r.id for r in RULES]


def test_malformed_rule_trace_present_but_unevaluated() -> None:
    explanation = explain("git push --force origin main")
    malformed_trace = next(t for t in explanation.traces if t.rule_id == "MALFORMED-001")
    assert malformed_trace.matched is False
    assert malformed_trace.guard_matched is None


def test_winning_rule_has_a_matched_span() -> None:
    explanation = explain("git push --force origin main")
    assert explanation.decision.rule_id == "IRR-002"
    winner_trace = next(t for t in explanation.traces if t.rule_id == "IRR-002")
    assert winner_trace.matched is True
    assert winner_trace.matched_text is not None


def test_near_miss_shows_which_signal_failed() -> None:
    """rg api_key src/ matches DENY-002's field guard but not its sink pattern."""
    explanation = explain("rg api_key src/")
    leak_trace = next(t for t in explanation.traces if t.rule_id == "DENY-002")
    assert leak_trace.matched is False
    assert explanation.decision.verdict == Verdict.ALLOW


def test_explanation_to_dict_shape() -> None:
    explanation = explain("git push --force origin main")
    payload = explanation_to_dict(explanation)
    assert set(payload.keys()) == {
        "command", "normalized", "verdict", "rule_id", "family", "reason",
        "safe_correction", "matched_text", "approved_by", "would_clear_with", "traces",
    }
    assert payload["verdict"] == "ASK_IRREVERSIBLE"
    assert payload["rule_id"] == "IRR-002"
    assert payload["would_clear_with"] == "--approve-irreversible"
    assert len(payload["traces"]) == 11
    assert set(payload["traces"][0].keys()) == {
        "rule_id", "matched", "guard_matched", "matched_text",
    }


def test_would_clear_with_is_null_on_allow() -> None:
    explanation = explain("git status")
    payload = explanation_to_dict(explanation)
    assert payload["would_clear_with"] is None
    assert payload["verdict"] == "ALLOW"


def test_would_clear_with_is_null_on_a_deny_family_rule() -> None:
    explanation = explain("git stash")
    payload = explanation_to_dict(explanation)
    assert payload["verdict"] == "DENY"
    assert payload["would_clear_with"] is None


def test_format_explanation_first_line_is_verdict_and_rule() -> None:
    explanation = explain("git push --force origin main")
    text = format_explanation(explanation)
    lines = text.splitlines()
    assert lines[0] == "ASK_IRREVERSIBLE  IRR-002"
    assert any(line.startswith("clears with:") for line in lines)


def test_format_explanation_on_allow_has_no_clears_with_line() -> None:
    explanation = explain("git status")
    text = format_explanation(explanation)
    assert text.startswith("ALLOW  -")
    assert "clears with:" not in text
