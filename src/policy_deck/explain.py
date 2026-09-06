"""A human-readable trace of a classification: which rule won, and how every other rule did.

`classify()` only reports the winning rule. `explain()` reports all eleven -- matched or not,
and for the two-signal rules, whether each of the two signals fired independently -- so a
reviewer can see *why* a near-miss stayed ALLOW (one signal hit, the other did not) instead of
just trusting the final verdict.
"""

from __future__ import annotations

from dataclasses import dataclass

from .classifier import Decision, _haystack_for, classify
from .policy import RULES, RULES_BY_ID, Verdict

_MALFORMED_ID = "MALFORMED-001"


@dataclass(frozen=True)
class RuleTrace:
    rule_id: str
    matched: bool
    guard_matched: bool | None       # None when the rule has no guard
    matched_text: str | None


@dataclass(frozen=True)
class Explanation:
    command: str
    normalized: str
    decision: Decision
    traces: tuple[RuleTrace, ...]    # one entry per rule in RULES, table order, always 11


def explain(command: str, *, approvals: frozenset[str] | None = None) -> Explanation:
    decision = classify(command, approvals=approvals)
    normalized = decision.normalized
    traces: list[RuleTrace] = []

    for candidate in RULES:
        if candidate.id == _MALFORMED_ID:
            # Decided by is_malformed() before any pattern runs; never evaluated here.
            traces.append(
                RuleTrace(rule_id=candidate.id, matched=False, guard_matched=None,
                           matched_text=None)
            )
            continue

        haystack = _haystack_for(candidate, normalized)
        match = candidate.pattern.search(haystack)
        matched = match is not None
        guard_matched = None
        if candidate.guard is not None:
            guard_matched = candidate.guard.search(haystack) is not None
        matched_text = normalized[match.start():match.end()] if match is not None else None

        traces.append(
            RuleTrace(
                rule_id=candidate.id,
                matched=matched,
                guard_matched=guard_matched,
                matched_text=matched_text,
            )
        )

    return Explanation(
        command=command,
        normalized=normalized,
        decision=decision,
        traces=tuple(traces),
    )


def _would_clear_with(decision: Decision) -> str | None:
    """The approval token that would clear this block, else None. Nothing to clear on an
    already-ALLOW decision, and DENY-family rules carry no token at all."""
    if decision.verdict is Verdict.ALLOW:
        return None
    if decision.rule_id is None:
        return None
    matched_rule = RULES_BY_ID.get(decision.rule_id)
    return matched_rule.approval_token if matched_rule is not None else None


def explanation_to_dict(explanation: Explanation) -> dict[str, object]:
    """JSON-safe. Top-level keys exactly:
    command, normalized, verdict, rule_id, family, reason, safe_correction, matched_text,
    approved_by, would_clear_with, traces
    - verdict/family are the string values of the enums (or null)
    - would_clear_with: the approval token that WOULD clear this block, else null
    - traces: list of {rule_id, matched, guard_matched, matched_text}
    """
    decision = explanation.decision
    return {
        "command": explanation.command,
        "normalized": explanation.normalized,
        "verdict": decision.verdict.value,
        "rule_id": decision.rule_id,
        "family": decision.family.value if decision.family is not None else None,
        "reason": decision.reason,
        "safe_correction": decision.safe_correction,
        "matched_text": decision.matched_text,
        "approved_by": decision.approved_by,
        "would_clear_with": _would_clear_with(decision),
        "traces": [
            {
                "rule_id": trace.rule_id,
                "matched": trace.matched,
                "guard_matched": trace.guard_matched,
                "matched_text": trace.matched_text,
            }
            for trace in explanation.traces
        ],
    }


def format_explanation(explanation: Explanation) -> str:
    """Plain text for a terminal. First line is `<VERDICT>  <rule_id or '-'>`. Then the reason,
    the matched text, the safe correction, and -- for a block that an approval token would clear
    -- the line `clears with: <token>`. No colour, no unicode box drawing.

    An ALLOW that no rule matched still gets a reason line naming how many rules were evaluated.
    A package whose pitch is explainability cannot leave its most common verdict unexplained: an
    empty allow path reads as "nothing ran" rather than "everything ran and nothing fired"."""
    decision = explanation.decision
    lines = [f"{decision.verdict.value}  {decision.rule_id or '-'}"]
    if decision.reason:
        lines.append(f"reason: {decision.reason}")
    elif decision.rule_id is None:
        lines.append(f"reason: no rule matched ({len(explanation.traces)} rules evaluated)")
    if decision.matched_text:
        lines.append(f"matched: {decision.matched_text!r}")
    if decision.safe_correction:
        lines.append(f"safe correction: {decision.safe_correction}")
    token = _would_clear_with(decision)
    if token:
        lines.append(f"clears with: {token}")
    return "\n".join(lines)
