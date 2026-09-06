"""Score a deck of commands against the policy-deck rule table and a published error budget.

The normal path (``rules=None``) classifies every row with ``policy_deck.classifier.classify``,
so day-to-day scoring runs the real, shipped algorithm and nothing else. The one exception is
the injection seam ``rules`` on ``score_rows``: the planted-regression test
(``tests/test_budget_regression.py``) needs to prove the budget gate can actually fail, and it
does that by building a *widened* or a *shortened* copy of the rule tuple in memory -- never by
editing a file. ``classifier.classify`` has no way to accept a substitute rule table (it always
scores against the module-level ``policy.RULES``), so this module carries a small private
re-implementation of the winner-selection step, ``_classify_against``, used only when ``rules``
is not None. It mirrors ``classify`` step for step: the same malformed check, the same
normalize, the same per-rule haystack (so ``DENY-001`` sees quoted spans masked here exactly as
it does on the normal path), the same highest-severity winner with table-order tie-break, the
same approval-token downgrade. Nothing about the matching *policy* is reinvented here, only the
ability to swap the table it runs against.

The haystack step is called out because it was **missing** until this version, and its absence
was invisible: the injected path scored a quoted risky phrase inside a commit message as a
``DENY``, so the fitted deck read ``fp=24`` under injection and ``fp=8`` on the normal path, for
the same rule table. Any measurement taken through the seam was inflated by the deck's own
quoted-prose near-misses. A re-implementation that claims in its docstring to mirror another
function is a claim a test has to hold up: ``tests/test_injection_seam_parity.py`` now scores
every shipped deck both ways and asserts the two paths return the identical verdict for every
row.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .classifier import Decision, _haystack_for, classify, is_malformed, normalize
from .deck import DeckError, DeckRow, deck_sha256, load_deck
from .policy import SEVERITY, Family, Rule, RULES_BY_ID, Verdict

EXIT_PASS: int = 0
EXIT_BUDGET_MISSED: int = 1
EXIT_OPERATIONAL: int = 2

_MAX_FAILURES_LISTED: int = 25
_MALFORMED_RULE_ID: str = "MALFORMED-001"


@dataclass(frozen=True)
class Budget:
    deck: str
    deck_sha256: str
    generator_seed: int
    rows: int
    fp_budget: int
    fn_budget: int
    misroute_budget: int
    hard_cases: str
    hard_case_mismatch_budget: int
    # The holdout deck is scored separately, against its own bars, and is optional: a budget file
    # without these keys still loads, and `score --holdout` then reports an operational error
    # rather than silently scoring nothing.
    holdout: str = ""
    holdout_sha256: str = ""
    holdout_rows: int = 0
    holdout_fp_budget: int = 0
    holdout_fn_budget: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "deck": self.deck,
            "deck_sha256": self.deck_sha256,
            "generator_seed": self.generator_seed,
            "rows": self.rows,
            "fp_budget": self.fp_budget,
            "fn_budget": self.fn_budget,
            "misroute_budget": self.misroute_budget,
            "hard_cases": self.hard_cases,
            "hard_case_mismatch_budget": self.hard_case_mismatch_budget,
            "holdout": self.holdout,
            "holdout_sha256": self.holdout_sha256,
            "holdout_rows": self.holdout_rows,
            "holdout_fp_budget": self.holdout_fp_budget,
            "holdout_fn_budget": self.holdout_fn_budget,
        }


class BudgetError(ValueError):
    """Raised when budget.json is missing a key, has a wrong type, or cannot be read."""


_BUDGET_STR_FIELDS: tuple[str, ...] = ("deck", "deck_sha256", "hard_cases")
_BUDGET_INT_FIELDS: tuple[str, ...] = (
    "generator_seed",
    "rows",
    "fp_budget",
    "fn_budget",
    "misroute_budget",
    "hard_case_mismatch_budget",
)
# Optional, additive: a budget file written before the holdout deck existed still loads.
_BUDGET_OPTIONAL_STR_FIELDS: tuple[str, ...] = ("holdout", "holdout_sha256")
_BUDGET_OPTIONAL_INT_FIELDS: tuple[str, ...] = (
    "holdout_rows",
    "holdout_fp_budget",
    "holdout_fn_budget",
)


def load_budget(path: Path) -> Budget:
    """Read and validate budget.json. Raise BudgetError on any problem, never a bare exception."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BudgetError(f"cannot read budget file {path}: {exc}") from exc
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BudgetError(f"budget file {path} is not valid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise BudgetError(f"budget file {path} must contain a JSON object")
    missing = [k for k in (_BUDGET_STR_FIELDS + _BUDGET_INT_FIELDS) if k not in obj]
    if missing:
        raise BudgetError(f"budget file {path} is missing keys: {', '.join(sorted(missing))}")
    for key in _BUDGET_STR_FIELDS:
        if not isinstance(obj[key], str):
            raise BudgetError(f"budget field {key!r} must be a string")
    for key in _BUDGET_INT_FIELDS:
        value = obj[key]
        if not isinstance(value, int) or isinstance(value, bool):
            raise BudgetError(f"budget field {key!r} must be an integer")
    optional: dict[str, object] = {}
    for key in _BUDGET_OPTIONAL_STR_FIELDS:
        if key in obj:
            if not isinstance(obj[key], str):
                raise BudgetError(f"budget field {key!r} must be a string")
            optional[key] = obj[key]
    for key in _BUDGET_OPTIONAL_INT_FIELDS:
        if key in obj:
            value = obj[key]
            if not isinstance(value, int) or isinstance(value, bool):
                raise BudgetError(f"budget field {key!r} must be an integer")
            optional[key] = value
    return Budget(
        **optional,  # type: ignore[arg-type]
        deck=obj["deck"],
        deck_sha256=obj["deck_sha256"],
        generator_seed=obj["generator_seed"],
        rows=obj["rows"],
        fp_budget=obj["fp_budget"],
        fn_budget=obj["fn_budget"],
        misroute_budget=obj["misroute_budget"],
        hard_cases=obj["hard_cases"],
        hard_case_mismatch_budget=obj["hard_case_mismatch_budget"],
    )


@dataclass(frozen=True)
class Score:
    rows: int
    tp: int
    tn: int
    fp: int
    fn: int
    misroute: int
    rule_mismatch: int
    precision: float
    recall: float
    per_class: dict[str, dict[str, int]]
    per_rule: dict[str, dict[str, int]]
    failures: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "rows": self.rows,
            "tp": self.tp,
            "tn": self.tn,
            "fp": self.fp,
            "fn": self.fn,
            "misroute": self.misroute,
            "rule_mismatch": self.rule_mismatch,
            "precision": self.precision,
            "recall": self.recall,
            "per_class": self.per_class,
            "per_rule": self.per_rule,
            "failures": list(self.failures),
        }


def _classify_against(
    command: str, rules: tuple[Rule, ...], approvals: frozenset[str] | None
) -> Decision:
    """Reimplementation of classify() parameterized on an injected rule table.

    Used only when the caller supplies a substitute ``rules`` tuple (the budget-regression
    test). Step order matches ``classifier.classify`` exactly; see the module docstring.
    """
    if is_malformed(command):
        malformed = RULES_BY_ID.get(_MALFORMED_RULE_ID)
        title = malformed.title if malformed is not None else "malformed input"
        correction = (
            malformed.safe_correction if malformed is not None else "provide a well-formed command"
        )
        return Decision(
            verdict=Verdict.DENY,
            rule_id=_MALFORMED_RULE_ID,
            family=Family.INPUT,
            reason=title,
            safe_correction=correction,
            matched_text=None,
            approved_by=None,
            normalized="",
        )
    normalized = normalize(command)
    # `_haystack_for` is the same per-rule text selector the normal path uses: DENY-001 is
    # matched against a quote-masked copy so a risky phrase quoted as data is not read as a
    # command; every other rule sees the real text. Calling it here is what keeps the two paths
    # in agreement -- see the module docstring for what its absence cost.
    matches = [
        r
        for r in rules
        if r.id != _MALFORMED_RULE_ID
        and r.pattern.search(_haystack_for(r, normalized))
        and (r.guard is None or r.guard.search(_haystack_for(r, normalized)))
    ]
    if not matches:
        return Decision(
            verdict=Verdict.ALLOW,
            rule_id=None,
            family=None,
            reason="",
            safe_correction="",
            matched_text=None,
            approved_by=None,
            normalized=normalized,
        )
    # max() keeps the first element on a tie, and `matches` preserves table order, so this
    # is the required "highest severity wins, ties break by table order" rule.
    winner = max(matches, key=lambda r: SEVERITY[r.verdict])
    span = winner.pattern.search(_haystack_for(winner, normalized))
    matched_text = normalized[span.start():span.end()] if span is not None else None
    verdict = winner.verdict
    approved_by: str | None = None
    if winner.approval_token is not None:
        tokens = set(normalized.split())
        has_token = winner.approval_token in tokens or (
            approvals is not None and winner.approval_token in approvals
        )
        if has_token:
            verdict = Verdict.ALLOW
            approved_by = winner.approval_token
    return Decision(
        verdict=verdict,
        rule_id=winner.id,
        family=winner.family,
        reason=winner.title,
        safe_correction=winner.safe_correction if verdict != Verdict.ALLOW else "",
        matched_text=matched_text,
        approved_by=approved_by,
        normalized=normalized,
    )


def _decide(command: str, rules: tuple[Rule, ...] | None) -> Decision:
    if rules is None:
        return classify(command)
    return _classify_against(command, rules, None)


def score_rows(rows: Sequence[DeckRow], *, rules: tuple[Rule, ...] | None = None) -> Score:
    """Classify every row and tally fp/fn/misroute/rule_mismatch per the metric definitions.

    `rules` is the injection seam for the planted-regression test: None means the shipped table.
    """
    per_class: dict[str, dict[str, int]] = {}
    per_rule: dict[str, dict[str, int]] = {}
    tp = tn = fp = fn = misroute = rule_mismatch = 0
    failures: list[dict[str, str]] = []

    for row in rows:
        decision = _decide(row.command, rules)
        actual_blocked = decision.verdict != Verdict.ALLOW
        expected_verdict = Verdict(row.expected)
        expected_blocked = expected_verdict != Verdict.ALLOW

        cls_bucket = per_class.setdefault(row.cls, {"total": 0, "fp": 0, "fn": 0, "misroute": 0})
        cls_bucket["total"] += 1

        kind: str | None = None
        if expected_blocked and actual_blocked:
            tp += 1
            expected_rule = RULES_BY_ID.get(row.expected_rule) if row.expected_rule else None
            expected_family = expected_rule.family if expected_rule is not None else None
            if expected_family is not None and decision.family != expected_family:
                misroute += 1
                cls_bucket["misroute"] += 1
                kind = "misroute"
            elif row.expected_rule is not None and decision.rule_id != row.expected_rule:
                rule_mismatch += 1
        elif not expected_blocked and not actual_blocked:
            tn += 1
        elif not expected_blocked and actual_blocked:
            fp += 1
            cls_bucket["fp"] += 1
            kind = "fp"
        else:  # expected_blocked and not actual_blocked
            fn += 1
            cls_bucket["fn"] += 1
            kind = "fn"

        if row.expected_rule is not None:
            rule_bucket = per_rule.setdefault(
                row.expected_rule, {"total": 0, "fn": 0, "misroute": 0}
            )
            rule_bucket["total"] += 1
            if kind == "fn":
                rule_bucket["fn"] += 1
            elif kind == "misroute":
                rule_bucket["misroute"] += 1

        if kind is not None and len(failures) < _MAX_FAILURES_LISTED:
            failures.append(
                {
                    "case_id": row.case_id,
                    "kind": kind,
                    "expected": row.expected,
                    "actual": decision.verdict.value,
                    "command": row.command,
                }
            )

    precision = round(tp / (tp + fp), 6) if (tp + fp) else 0.0
    recall = round(tp / (tp + fn), 6) if (tp + fn) else 0.0
    return Score(
        rows=len(rows),
        tp=tp,
        tn=tn,
        fp=fp,
        fn=fn,
        misroute=misroute,
        rule_mismatch=rule_mismatch,
        precision=precision,
        recall=recall,
        per_class=per_class,
        per_rule=per_rule,
        failures=tuple(failures),
    )


def check_budget(score: Score, budget: Budget, hard: Score | None = None) -> list[str]:
    """Return one plain sentence per missed bar, each naming the metric and both numbers."""
    reasons: list[str] = []
    if score.fp > budget.fp_budget:
        reasons.append(f"fp {score.fp} exceeds budget {budget.fp_budget}")
    if score.fn > budget.fn_budget:
        reasons.append(f"fn {score.fn} exceeds budget {budget.fn_budget}")
    if score.misroute > budget.misroute_budget:
        reasons.append(f"misroute {score.misroute} exceeds budget {budget.misroute_budget}")
    if hard is not None:
        hard_mismatch = hard.fp + hard.fn + hard.misroute
        if hard_mismatch > budget.hard_case_mismatch_budget:
            reasons.append(
                f"hard_case_mismatch {hard_mismatch} exceeds budget "
                f"{budget.hard_case_mismatch_budget}"
            )
    return reasons


def receipt(
    score: Score,
    budget: Budget,
    deck_sha: str,
    hard: Score | None,
    version: str,
) -> dict[str, object]:
    """Byte-reproducible parity receipt. No timestamp, no host, no path outside the repo."""
    reasons = check_budget(score, budget, hard)
    return {
        "schema": "policy-deck/parity/1",
        "version": version,
        "deck": budget.deck,
        "deck_sha256": deck_sha,
        "rows": score.rows,
        "fp": score.fp,
        "fn": score.fn,
        "misroute": score.misroute,
        "rule_mismatch": score.rule_mismatch,
        "precision": score.precision,
        "recall": score.recall,
        "per_class": score.per_class,
        "per_rule": score.per_rule,
        "hard_cases": hard.to_dict() if hard is not None else None,
        "budget": budget.to_dict(),
        "passed": len(reasons) == 0,
        "reasons": reasons,
    }


def _format_summary(score: Score, hard: Score | None, budget: Budget, reasons: list[str]) -> str:
    lines = [
        f"rows: {score.rows}  tp={score.tp} tn={score.tn} fp={score.fp} fn={score.fn} "
        f"misroute={score.misroute} rule_mismatch={score.rule_mismatch}",
        f"precision={score.precision:.6f} recall={score.recall:.6f}",
        f"budget: fp<={budget.fp_budget} fn<={budget.fn_budget} "
        f"misroute<={budget.misroute_budget}",
    ]
    if hard is not None:
        hard_mismatch = hard.fp + hard.fn + hard.misroute
        lines.append(
            f"hard cases: rows={hard.rows} mismatch={hard_mismatch} "
            f"budget<={budget.hard_case_mismatch_budget}"
        )
    if reasons:
        lines.append("FAIL")
        lines.extend(f"  - {r}" for r in reasons)
    else:
        lines.append("PASS")
    return "\n".join(lines)


def evaluate(
    deck_path: Path,
    budget_path: Path,
    hard_path: Path | None = None,
    *,
    rules: tuple[Rule, ...] | None = None,
) -> tuple[int, dict[str, object] | None, str]:
    """Load, score, and build the receipt without printing or writing anything.

    Returns (exit_code, receipt_dict_or_None, message). `receipt_dict` is None only on an
    operational error, in which case `message` names the problem. This is the shared core
    behind both `run()` (prints a text summary, optionally writes the receipt file) and the
    CLI's `score` subcommand (which additionally supports `--json`).
    """
    try:
        budget = load_budget(budget_path)
    except BudgetError as exc:
        return EXIT_OPERATIONAL, None, f"operational error: {exc}"

    try:
        deck_text = deck_path.read_text(encoding="utf-8")
    except OSError as exc:
        return EXIT_OPERATIONAL, None, f"operational error: cannot read deck {deck_path}: {exc}"

    actual_sha = deck_sha256(deck_text)
    if actual_sha != budget.deck_sha256:
        message = (
            "operational error: deck sha mismatch\n"
            f"  pinned:  {budget.deck_sha256}\n"
            f"  actual:  {actual_sha}\n"
            "the deck is frozen; regenerate it with the pinned seed before scoring"
        )
        return EXIT_OPERATIONAL, None, message

    try:
        rows = load_deck(deck_path)
    except DeckError as exc:
        return EXIT_OPERATIONAL, None, f"operational error: {exc}"

    score = score_rows(rows, rules=rules)

    hard_score: Score | None = None
    if hard_path is not None:
        try:
            hard_rows = load_deck(hard_path)
        except DeckError as exc:
            return EXIT_OPERATIONAL, None, f"operational error: {exc}"
        hard_score = score_rows(hard_rows, rules=rules)

    reasons = check_budget(score, budget, hard_score)
    rcpt = receipt(score, budget, actual_sha, hard_score, __version__)
    exit_code = EXIT_PASS if not reasons else EXIT_BUDGET_MISSED
    summary = _format_summary(score, hard_score, budget, reasons)
    return exit_code, rcpt, summary


def _format_holdout_summary(score: Score, budget: Budget, reasons: list[str]) -> str:
    lines = [
        f"holdout rows: {score.rows}  tp={score.tp} tn={score.tn} fp={score.fp} fn={score.fn} "
        f"misroute={score.misroute} rule_mismatch={score.rule_mismatch}",
        f"precision={score.precision:.6f} recall={score.recall:.6f}",
        f"holdout budget: fp<={budget.holdout_fp_budget} fn<={budget.holdout_fn_budget} "
        f"misroute<={budget.misroute_budget}",
    ]
    if reasons:
        lines.append("FAIL")
        lines.extend(f"  - {r}" for r in reasons)
    else:
        lines.append("PASS")
    return "\n".join(lines)


def evaluate_holdout(
    budget_path: Path, holdout_path: Path | None = None
) -> tuple[int, dict[str, object] | None, str]:
    """Score the holdout deck against its own bars, and never against the fitted deck's.

    The holdout is a separate measurement, so it gets a separate receipt and a separate budget:
    the two are printed side by side in the README precisely because they are not the same exam.
    A missed holdout bar is EXIT_BUDGET_MISSED; a missing declaration, an unreadable file, or a
    sha that does not match the pin is EXIT_OPERATIONAL, same as everywhere else in this module.
    """
    try:
        budget = load_budget(budget_path)
    except BudgetError as exc:
        return EXIT_OPERATIONAL, None, f"operational error: {exc}"

    if not budget.holdout or not budget.holdout_sha256:
        return (
            EXIT_OPERATIONAL,
            None,
            "operational error: this budget file declares no holdout deck "
            "(keys 'holdout' and 'holdout_sha256')",
        )

    path = holdout_path if holdout_path is not None else Path(budget.holdout)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return EXIT_OPERATIONAL, None, f"operational error: cannot read holdout {path}: {exc}"

    actual_sha = deck_sha256(text)
    if actual_sha != budget.holdout_sha256:
        message = (
            "operational error: holdout sha mismatch\n"
            f"  pinned:  {budget.holdout_sha256}\n"
            f"  actual:  {actual_sha}\n"
            "the holdout is frozen; rebuild it from policy_deck.holdout before scoring"
        )
        return EXIT_OPERATIONAL, None, message

    try:
        rows = load_deck(path)
    except DeckError as exc:
        return EXIT_OPERATIONAL, None, f"operational error: {exc}"

    score = score_rows(rows)
    reasons: list[str] = []
    if score.fp > budget.holdout_fp_budget:
        reasons.append(f"holdout fp {score.fp} exceeds budget {budget.holdout_fp_budget}")
    if score.fn > budget.holdout_fn_budget:
        reasons.append(f"holdout fn {score.fn} exceeds budget {budget.holdout_fn_budget}")
    if score.misroute > budget.misroute_budget:
        reasons.append(
            f"holdout misroute {score.misroute} exceeds budget {budget.misroute_budget}"
        )

    rcpt: dict[str, object] = {
        "schema": "policy-deck/holdout/1",
        "version": __version__,
        "deck": budget.holdout,
        "deck_sha256": actual_sha,
        "rows": score.rows,
        "fp": score.fp,
        "fn": score.fn,
        "misroute": score.misroute,
        "rule_mismatch": score.rule_mismatch,
        "precision": score.precision,
        "recall": score.recall,
        "per_class": score.per_class,
        "per_rule": score.per_rule,
        "budget": {
            "holdout_rows": budget.holdout_rows,
            "holdout_fp_budget": budget.holdout_fp_budget,
            "holdout_fn_budget": budget.holdout_fn_budget,
            "misroute_budget": budget.misroute_budget,
        },
        "failures": list(score.failures),
        "passed": len(reasons) == 0,
        "reasons": reasons,
    }
    exit_code = EXIT_PASS if not reasons else EXIT_BUDGET_MISSED
    return exit_code, rcpt, _format_holdout_summary(score, budget, reasons)


def run(
    deck_path: Path,
    budget_path: Path,
    hard_path: Path | None = None,
    receipt_path: Path | None = None,
    *,
    rules: tuple[Rule, ...] | None = None,
) -> int:
    """Load the budget, load the deck, recompute its sha and compare to budget.deck_sha256,
    score, optionally score the hard cases, optionally write the receipt, print a one-screen
    summary, return EXIT_PASS / EXIT_BUDGET_MISSED / EXIT_OPERATIONAL.

    EXIT_OPERATIONAL covers: missing or unreadable budget or deck, DeckError, BudgetError, and a
    deck sha that does not match the pin. A sha mismatch prints both hashes and the sentence that
    the deck is frozen and must be regenerated with the pinned seed.
    """
    exit_code, rcpt, message = evaluate(deck_path, budget_path, hard_path, rules=rules)
    if rcpt is None:
        print(message)
        return exit_code
    if receipt_path is not None:
        receipt_path.write_text(
            json.dumps(rcpt, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(message)
    return exit_code
