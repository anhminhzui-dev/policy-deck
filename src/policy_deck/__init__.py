"""policy-deck: a small, readable shell-command policy, plus the machinery to grade it."""

from __future__ import annotations

from .classifier import Decision, classify, is_blocked, normalize, strip_heredoc_bodies
from .explain import Explanation, RuleTrace, explain, explanation_to_dict, format_explanation
from .policy import (
    APPROVAL_TOKENS,
    MAX_COMMAND_CHARS,
    RULES,
    RULES_BY_ID,
    SEVERITY,
    Family,
    Rule,
    Verdict,
)

__version__: str = "0.3.1"
__all__ = [
    "Verdict", "Family", "Rule", "RULES", "RULES_BY_ID", "SEVERITY", "APPROVAL_TOKENS",
    "MAX_COMMAND_CHARS", "Decision", "classify", "is_blocked", "normalize",
    "strip_heredoc_bodies", "Explanation", "RuleTrace", "explain", "explanation_to_dict",
    "format_explanation",
]
