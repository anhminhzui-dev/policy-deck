"""Approval-token downgrade: own-family clears, wrong-family does not, DENY never clears."""

from __future__ import annotations

from policy_deck import Verdict, classify


def test_correct_token_in_command_text_clears_spend() -> None:
    decision = classify("python run.py --provider openai --mode invoke --approve-spend")
    assert decision.verdict == Verdict.ALLOW
    assert decision.rule_id == "SPEND-001"
    assert decision.approved_by == "--approve-spend"


def test_correct_token_in_command_text_clears_irreversible() -> None:
    decision = classify("git push --force origin main --approve-irreversible")
    assert decision.verdict == Verdict.ALLOW
    assert decision.rule_id == "IRR-002"
    assert decision.approved_by == "--approve-irreversible"


def test_wrong_family_token_does_not_clear_spend() -> None:
    decision = classify("python run.py --provider openai --mode invoke --approve-irreversible")
    assert decision.verdict == Verdict.ASK_MONEY
    assert decision.rule_id == "SPEND-001"
    assert decision.approved_by is None


def test_wrong_family_token_does_not_clear_irreversible() -> None:
    decision = classify("git push --force origin main --approve-spend")
    assert decision.verdict == Verdict.ASK_IRREVERSIBLE
    assert decision.rule_id == "IRR-002"
    assert decision.approved_by is None


def test_no_token_clears_a_deny() -> None:
    decision = classify("git stash --approve-irreversible")
    assert decision.verdict == Verdict.DENY
    assert decision.rule_id == "DENY-001"
    assert decision.approved_by is None


def test_approvals_parameter_clears_without_editing_the_command() -> None:
    decision = classify(
        "git push --force origin main", approvals=frozenset({"--approve-irreversible"})
    )
    assert decision.verdict == Verdict.ALLOW
    assert decision.approved_by == "--approve-irreversible"


def test_approvals_parameter_with_wrong_token_does_not_clear() -> None:
    decision = classify(
        "git push --force origin main", approvals=frozenset({"--approve-spend"})
    )
    assert decision.verdict == Verdict.ASK_IRREVERSIBLE
    assert decision.approved_by is None


def test_prefix_token_does_not_count_as_the_real_token() -> None:
    """--approve-spending is a different whole token from --approve-spend."""
    decision = classify("python run.py --provider openai --mode invoke --approve-spending")
    assert decision.verdict == Verdict.ASK_MONEY
    assert decision.approved_by is None
