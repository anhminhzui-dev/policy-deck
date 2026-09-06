"""An ALLOW explains itself too.

`explain` used to print the bare line `ALLOW  -` and stop. For a package whose pitch is that a
guardrail should say which rule decided and what to do instead, the most common verdict of all
explained nothing: a reader could not tell "every rule ran and none matched" from "nothing ran".
One line closes it, and it names the number of rules that were evaluated so the count is checkable
against the table.
"""

from __future__ import annotations

import pytest

from policy_deck import RULES, explain, format_explanation
from policy_deck.cli import main

_ALLOW_COMMANDS = [
    "git status --short --branch",
    "npm run build",
    "grep -rn api_key src/",
    "aws s3 ls s3://reports-bucket",
    "git clean -n",
]


@pytest.mark.parametrize("command", _ALLOW_COMMANDS)
def test_allow_prints_a_reason_line_naming_the_rule_count(command: str) -> None:
    text = format_explanation(explain(command))
    lines = text.splitlines()
    assert lines[0] == "ALLOW  -"
    assert lines[1] == f"reason: no rule matched ({len(RULES)} rules evaluated)"


def test_the_rule_count_in_the_line_matches_the_trace_length() -> None:
    explanation = explain("git status")
    assert len(explanation.traces) == len(RULES)
    assert f"({len(explanation.traces)} rules evaluated)" in format_explanation(explanation)


def test_a_blocked_command_still_prints_its_rule_reason_not_the_allow_line() -> None:
    text = format_explanation(explain("git push --force origin main"))
    assert "no rule matched" not in text
    assert text.splitlines()[1].startswith("reason: git push with --force")


def test_an_approved_command_prints_the_rule_that_was_cleared() -> None:
    """An ASK downgraded by its approval token is an ALLOW *with* a rule, so it keeps the rule's
    own reason rather than claiming nothing matched."""
    text = format_explanation(explain("git push --force origin main --approve-irreversible"))
    assert text.startswith("ALLOW  IRR-002")
    assert "no rule matched" not in text


def test_cli_allow_output_carries_the_reason_line(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["explain", "git status"])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "reason: no rule matched (11 rules evaluated)" in out
