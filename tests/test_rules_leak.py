"""DENY-002: the two-signal conjunction (sink shape AND credential field), both directions."""

from __future__ import annotations

import pytest

from policy_deck import Verdict, classify

_BOTH_SIGNALS_POSITIVE = [
    'set-content shared/agent_payload.json \'{"api_key": "REDACTED"}\'',
    "cp secrets_dump.json shared/worker_input.json",
    "python emit.py --output shared/task.json --field password",
    'echo "token=REDACTED" > shared/handoff.json',
]

_SINK_ALONE_NEGATIVE = [
    'set-content shared/agent_payload.json \'{"status": "ok"}\'',
    "cp status.json out/status.json",
]

_FIELD_ALONE_NEGATIVE = [
    "rg api_key src/",
    "grep -r password src/",
]

_NEITHER_NEGATIVE = [
    "cat shared/agent_payload.json",
]


@pytest.mark.parametrize("command", _BOTH_SIGNALS_POSITIVE)
def test_deny_002_fires_when_both_signals_present(command: str) -> None:
    decision = classify(command)
    assert decision.verdict == Verdict.DENY
    assert decision.rule_id == "DENY-002"


@pytest.mark.parametrize("command", _SINK_ALONE_NEGATIVE)
def test_sink_alone_stays_allow(command: str) -> None:
    assert classify(command).verdict == Verdict.ALLOW


@pytest.mark.parametrize("command", _FIELD_ALONE_NEGATIVE)
def test_field_alone_stays_allow(command: str) -> None:
    assert classify(command).verdict == Verdict.ALLOW


@pytest.mark.parametrize("command", _NEITHER_NEGATIVE)
def test_neither_signal_stays_allow(command: str) -> None:
    assert classify(command).verdict == Verdict.ALLOW


def test_deny_002_has_no_approval_token() -> None:
    """A DENY-family rule can never be downgraded, even if the request carries an ASK token."""
    decision = classify(
        'set-content shared/agent_payload.json \'{"api_key": "x"}\' --approve-irreversible'
    )
    assert decision.verdict == Verdict.DENY
    assert decision.rule_id == "DENY-002"
