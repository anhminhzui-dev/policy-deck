"""Command-line interface for policy-deck: score, generate-deck, explain.

All default paths resolve relative to the current working directory, not the package -- the
CLI is meant to be run from the repo root, same as any dev tool. `main(argv)` never touches
`sys.argv` itself so tests can call it in-process with an explicit argument list.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .deck import DEFAULT_ROWS, DEFAULT_SEED, deck_sha256, generate, serialize, write_deck
from .explain import explain, explanation_to_dict, format_explanation
from .holdout import build_rows as build_holdout_rows
from .policy import Verdict
from .score import (
    BudgetError,
    EXIT_BUDGET_MISSED,
    EXIT_OPERATIONAL,
    EXIT_PASS,
    evaluate,
    evaluate_holdout,
    load_budget,
)

_DEFAULT_DECK = Path("decks/synthetic_v1.jsonl")
_DEFAULT_BUDGET = Path("budget.json")
_DEFAULT_HARD_CASES = Path("decks/hard_cases.jsonl")
_DEFAULT_HOLDOUT = Path("decks/holdout_v1.jsonl")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="policy-deck",
        description=(
            "A small, readable shell-command policy classifier: score it against a published "
            "budget, explain one verdict, or regenerate its deterministic test deck."
        ),
    )
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    sub = parser.add_subparsers(dest="command")

    score_p = sub.add_parser("score", help="score a deck against the published error budget")
    score_p.add_argument("--deck", type=Path, default=_DEFAULT_DECK)
    score_p.add_argument("--budget", type=Path, default=_DEFAULT_BUDGET)
    score_p.add_argument("--hard-cases", type=Path, default=_DEFAULT_HARD_CASES)
    score_p.add_argument("--receipt", type=Path, default=None)
    score_p.add_argument("--json", action="store_true", help="print the receipt as JSON")
    score_p.add_argument(
        "--holdout",
        action="store_true",
        help=(
            "score the holdout deck (written against the rule titles, not the patterns) "
            "against its own bars instead of the fitted deck"
        ),
    )

    gen_p = sub.add_parser(
        "generate-deck", help="deterministically (re)generate the synthetic deck"
    )
    gen_p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    gen_p.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    gen_p.add_argument("--out", type=Path, default=None)
    gen_p.add_argument("--budget", type=Path, default=_DEFAULT_BUDGET, help="pin to check against")
    gen_p.add_argument(
        "--check", action="store_true", help="verify against the budget's pinned sha"
    )
    gen_p.add_argument(
        "--holdout",
        action="store_true",
        help="rebuild the authored holdout deck instead of the seeded synthetic deck",
    )

    exp_p = sub.add_parser("explain", help="explain the verdict for one command")
    exp_p.add_argument("command_text", nargs="?", metavar="COMMAND")
    exp_p.add_argument("--stdin", action="store_true", help="read the command from stdin")
    exp_p.add_argument("--json", action="store_true")
    exp_p.add_argument("--approve-spend", action="store_true")
    exp_p.add_argument("--approve-irreversible", action="store_true")

    return parser


def _cmd_score(args: argparse.Namespace) -> int:
    if args.holdout:
        exit_code, rcpt, message = evaluate_holdout(args.budget)
    else:
        exit_code, rcpt, message = evaluate(
            args.deck, args.budget, args.hard_cases, rules=None
        )
    if rcpt is None:
        print(message)
        return exit_code
    if args.receipt is not None:
        args.receipt.write_text(
            json.dumps(rcpt, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    if args.json:
        print(json.dumps(rcpt, sort_keys=True, ensure_ascii=False))
    else:
        print(message)
    return exit_code


def _cmd_generate_deck(args: argparse.Namespace) -> int:
    if args.holdout:
        rows = build_holdout_rows()
    else:
        rows = generate(seed=args.seed, rows=args.rows)
    text = serialize(rows)
    sha = deck_sha256(text)

    if args.check:
        try:
            budget = load_budget(args.budget)
        except BudgetError as exc:
            print(f"operational error: {exc}")
            return EXIT_OPERATIONAL
        pinned = budget.holdout_sha256 if args.holdout else budget.deck_sha256
        label = "holdout" if args.holdout else "deck"
        if not pinned:
            print(f"operational error: this budget file declares no {label} sha to check against")
            return EXIT_OPERATIONAL
        if sha != pinned:
            print(f"{label} drift detected: rebuilding no longer reproduces the pinned sha")
            print(f"  pinned:      {pinned}")
            print(f"  regenerated: {sha}")
            return EXIT_BUDGET_MISSED
        print(f"{label} matches pinned sha256: {sha}")
        return EXIT_PASS

    default_out = _DEFAULT_HOLDOUT if args.holdout else _DEFAULT_DECK
    out_path = args.out if args.out is not None else default_out
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_deck(rows, out_path)
    except OSError as exc:
        print(f"operational error: cannot write deck to {out_path}: {exc}")
        return EXIT_OPERATIONAL
    print(sha)
    return EXIT_PASS


def _cmd_explain(args: argparse.Namespace) -> int:
    if args.stdin:
        command = sys.stdin.read()
    elif args.command_text is not None:
        command = args.command_text
    else:
        print("explain requires COMMAND or --stdin", file=sys.stderr)
        return 2

    approvals: set[str] = set()
    if args.approve_spend:
        approvals.add("--approve-spend")
    if args.approve_irreversible:
        approvals.add("--approve-irreversible")

    explanation = explain(command, approvals=frozenset(approvals) if approvals else None)
    if args.json:
        print(json.dumps(explanation_to_dict(explanation), sort_keys=True, ensure_ascii=False))
    else:
        print(format_explanation(explanation))
    return 0 if explanation.decision.verdict == Verdict.ALLOW else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(__version__)
        return 0

    if args.command == "score":
        return _cmd_score(args)
    if args.command == "generate-deck":
        return _cmd_generate_deck(args)
    if args.command == "explain":
        return _cmd_explain(args)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
