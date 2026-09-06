"""Turn one command string into one typed Decision.

The shape is: fail closed on unusable input, normalize, scan every rule, keep every match, hand
the highest-severity match to an approval check, and return a Decision that always names which
rule decided and what to do instead. A rule that says "no" without saying which rule and what to
do instead is not a usable guardrail.

Normalization is deliberately dumb: collapse whitespace (including newlines, so a risky verb
hiding after a line break is still visible to an unanchored pattern) and lowercase, after eliding
any heredoc body that flows into a file rather than an interpreter. Collapsing whitespace before
eliding heredocs would fuse a document's *content* into the command text as if it were code; the
elision has to run first and has to be conditional, because a document that is actually piped
into an interpreter is executed and must stay in scope.

Quote-awareness is scoped narrowly, not applied everywhere: only the whole-tree git-discard rule
(``DENY-001``) is evaluated against a version of the command with quoted spans blanked out, so a
risky phrase inside a commit message or a quoted argument cannot be misread as a command. Every
other rule -- including the credential-leak rule, whose field signal is routinely quoted JSON --
is evaluated against the real, unmasked text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .policy import MAX_COMMAND_CHARS, RULES, RULES_BY_ID, SEVERITY, Family, Rule, Verdict

INTERPRETERS: tuple[str, ...] = (
    "bash", "sh", "zsh", "ksh", "dash", "python", "node", "deno", "perl", "ruby",
    "php", "powershell", "pwsh", "eval", "source", "xargs",
)

_MALFORMED_ID = "MALFORMED-001"
_QUOTE_MASKED_ID = "DENY-001"


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    rule_id: str | None          # None only when verdict is ALLOW and nothing matched
    family: Family | None
    reason: str                  # human sentence: the rule title, or "" when nothing matched
    safe_correction: str         # "" when ALLOW
    matched_text: str | None     # the substring the winning pattern matched, or None
    approved_by: str | None      # the approval token that downgraded a block to ALLOW
    normalized: str              # the normalized command the rules were run against


_HEREDOC_START = re.compile(
    r"<<-?\s*(?:'([A-Za-z_]\w*)'|\"([A-Za-z_]\w*)\"|([A-Za-z_]\w*))"
)
_HEREDOC_PLACEHOLDER = "__heredoc_body_elided__"


def strip_heredoc_bodies(text: str) -> str:
    """Elide a heredoc body when it flows into a NON-executing sink, keep it when the same line
    invokes an interpreter. `cat > notes.md <<EOF ... EOF` -> body replaced by a placeholder;
    `bash <<EOF ... EOF` -> body untouched."""
    out_parts: list[str] = []
    pos = 0
    for match in _HEREDOC_START.finditer(text):
        if match.start() < pos:
            continue  # inside a body we already consumed for an earlier heredoc
        delimiter = match.group(1) or match.group(2) or match.group(3)
        if not delimiter:
            continue
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_prefix = text[line_start:match.start()]
        invokes_interpreter = any(
            re.search(rf"\b{re.escape(name)}\b", line_prefix) for name in INTERPRETERS
        )
        newline_after_marker = text.find("\n", match.end())
        if newline_after_marker == -1:
            break  # no body follows on its own line; nothing left to elide
        body_start = newline_after_marker + 1
        end_pattern = re.compile(rf"^[ \t]*{re.escape(delimiter)}[ \t]*$", re.MULTILINE)
        end_match = end_pattern.search(text, body_start)
        if end_match is None:
            break  # unterminated heredoc; leave the rest of the text as-is
        body_end = end_match.start()
        out_parts.append(text[pos:body_start])
        if invokes_interpreter:
            out_parts.append(text[body_start:body_end])
        else:
            out_parts.append(_HEREDOC_PLACEHOLDER)
        pos = body_end
    out_parts.append(text[pos:])
    return "".join(out_parts)


def normalize(command: str) -> str:
    """strip_heredoc_bodies, then collapse every run of whitespace (including newlines) to one
    space, strip, and lowercase. Pure; no side effects."""
    text = strip_heredoc_bodies(command)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def is_malformed(command: object) -> bool:
    """True when the input is not a non-empty string, contains a NUL, or exceeds
    MAX_COMMAND_CHARS (measured on the raw input, before normalization)."""
    if not isinstance(command, str):
        return True
    if command.strip() == "":
        return True
    if "\x00" in command:
        return True
    if len(command) > MAX_COMMAND_CHARS:
        return True
    return False


_QUOTED_RUN = re.compile(r"'[^']*'|\"[^\"]*\"")


def _mask_quoted_spans(text: str) -> str:
    """Blank the interior of every single- or double-quoted run, keeping the quote characters
    and the overall length so span offsets still line up with the unmasked text. Used only for
    DENY-001: a risky phrase quoted as data (a commit message, a quoted argument) is not a
    command and must not be read as one."""

    def _blank(match: re.Match[str]) -> str:
        span = match.group(0)
        return span[0] + " " * (len(span) - 2) + span[-1]

    return _QUOTED_RUN.sub(_blank, text)


def _haystack_for(rule_obj: Rule, normalized: str) -> str:
    """The text a rule's pattern/guard actually run against: quote-masked for DENY-001 only."""
    if rule_obj.id == _QUOTE_MASKED_ID:
        return _mask_quoted_spans(normalized)
    return normalized


def find_matches(normalized: str) -> list[Rule]:
    """Every rule whose pattern matches and whose guard (if any) also matches, in table order.
    Never includes MALFORMED-001, which is decided before matching."""
    matches: list[Rule] = []
    for candidate in RULES:
        if candidate.id == _MALFORMED_ID:
            continue
        haystack = _haystack_for(candidate, normalized)
        if candidate.pattern.search(haystack) is None:
            continue
        if candidate.guard is not None and candidate.guard.search(haystack) is None:
            continue
        matches.append(candidate)
    return matches


def _matched_text(rule_obj: Rule, normalized: str) -> str | None:
    haystack = _haystack_for(rule_obj, normalized)
    match = rule_obj.pattern.search(haystack)
    if match is None:
        return None
    return normalized[match.start():match.end()]


def classify(command: str, *, approvals: frozenset[str] | None = None) -> Decision:
    """Classify one command.

    1. is_malformed -> Decision(DENY, "MALFORMED-001", ...) immediately.
    2. normalized = normalize(command).
    3. winner = highest SEVERITY among find_matches(normalized); ties break by table order.
    4. No winner -> Decision(ALLOW, None, None, "", "", None, None, normalized).
    5. Winner has an approval_token, and that token is present -- as a whole token in
       `normalized`, or a member of `approvals` -- -> verdict becomes ALLOW and approved_by is
       the token; rule_id, family and matched_text are still reported.
    6. Otherwise the winner's verdict is returned.

    A rule with approval_token None can never be downgraded.
    """
    if is_malformed(command):
        normalized = normalize(command) if isinstance(command, str) else ""
        malformed_rule = RULES_BY_ID[_MALFORMED_ID]
        return Decision(
            verdict=Verdict.DENY,
            rule_id=malformed_rule.id,
            family=malformed_rule.family,
            reason=malformed_rule.title,
            safe_correction=malformed_rule.safe_correction,
            matched_text=None,
            approved_by=None,
            normalized=normalized,
        )

    normalized = normalize(command)
    matches = find_matches(normalized)
    if not matches:
        return Decision(Verdict.ALLOW, None, None, "", "", None, None, normalized)

    winner = max(matches, key=lambda r: SEVERITY[r.verdict])
    matched_text = _matched_text(winner, normalized)
    verdict = winner.verdict
    approved_by: str | None = None

    if winner.approval_token is not None:
        tokens = normalized.split()
        token_present = winner.approval_token in tokens
        approvals_present = approvals is not None and winner.approval_token in approvals
        if token_present or approvals_present:
            verdict = Verdict.ALLOW
            approved_by = winner.approval_token

    return Decision(
        verdict=verdict,
        rule_id=winner.id,
        family=winner.family,
        reason=winner.title,
        safe_correction=winner.safe_correction,
        matched_text=matched_text,
        approved_by=approved_by,
        normalized=normalized,
    )


def is_blocked(decision: Decision) -> bool:
    """decision.verdict is not Verdict.ALLOW."""
    return decision.verdict is not Verdict.ALLOW
