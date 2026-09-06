"""DENY-001 is independent of the order of the short flags in a `git clean` cluster.

Every DENY row below is a real command a developer types, and the pre-fix pattern -- which looked
for the literal substring `-f` -- returned ALLOW for `-df` and `-xfd`. A guardrail whose most
advertised rule is defeated by reordering two characters is not a guardrail, so the flag cluster
is now matched as a token containing `f`, not as a fixed substring.

The ALLOW rows are the other half of the same fix: widening a flag matcher is only safe if it
still refuses to read a pathspec or a long option as a force flag.
"""

from __future__ import annotations

import pytest

from policy_deck import Verdict, classify

_FORCE_CLUSTERS_IN_EVERY_ORDER = [
    "git clean -f",
    "git clean -fd",
    "git clean -df",
    "git clean -xfd",
    "git clean -fdx",
    "git clean -dfx",
    "git clean -fx",
    "git clean --force",
    "git clean --force -d",
    "git clean -d --force",
    "git clean -d -f",
    "git clean -f -d -x",
]

_NO_FORCE_FLAG_STAYS_ALLOW = [
    "git clean -n",
    "git clean --dry-run",
    "git clean -nd",
    "git clean -n -- some-file.txt",
    "git clean --dry-run -x",
]


@pytest.mark.parametrize("command", _FORCE_CLUSTERS_IN_EVERY_ORDER)
def test_force_flag_in_any_order_is_denied(command: str) -> None:
    decision = classify(command)
    assert decision.verdict == Verdict.DENY
    assert decision.rule_id == "DENY-001"


@pytest.mark.parametrize("command", _NO_FORCE_FLAG_STAYS_ALLOW)
def test_no_force_flag_stays_allow(command: str) -> None:
    """A dry run deletes nothing; a pathspec containing a hyphen is not a flag cluster."""
    assert classify(command).verdict == Verdict.ALLOW


def test_uppercase_and_extra_whitespace_do_not_defeat_the_cluster() -> None:
    assert classify("GIT   CLEAN   -DF").verdict == Verdict.DENY


def test_a_force_flag_in_a_later_clause_does_not_reach_back_to_clean() -> None:
    """The lookahead is clause-scoped: a force flag belonging to a different command after a
    separator must not make an otherwise harmless `git clean -n` read as a discard."""
    assert classify("git clean -n ; grep -f patterns.txt access.log").verdict == Verdict.ALLOW
