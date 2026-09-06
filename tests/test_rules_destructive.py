"""DENY-001: every whole-tree git-discard shape, its near-misses, and quote-masking."""

from __future__ import annotations

import pytest

from policy_deck import Verdict, classify

_POSITIVE_SHAPES = [
    "git stash",
    "git stash pop",
    "git stash drop",
    "git reset --hard",
    "git checkout",
    "git switch main",
    "git restore",
    "git checkout .",
    "git clean -fd",
    "git clean --force",
]

_NEAR_MISS_SHAPES = [
    "git stash list",
    "git stash show -p",
    "git reset --soft head~1",
    "git clean -n",
    "git checkout -- src/one_file.py",
    "git restore src/one_file.py",
    "npm install",
]


@pytest.mark.parametrize("command", _POSITIVE_SHAPES)
def test_deny_001_positive_shapes(command: str) -> None:
    decision = classify(command)
    assert decision.verdict == Verdict.DENY
    assert decision.rule_id == "DENY-001"


@pytest.mark.parametrize("command", _NEAR_MISS_SHAPES)
def test_deny_001_near_misses_stay_allow(command: str) -> None:
    assert classify(command).verdict == Verdict.ALLOW


def test_quoted_discard_phrase_in_commit_message_stays_allow() -> None:
    """DENY-001 runs on quote-masked text: a discard phrase quoted as data must not match."""
    decision = classify('git commit -m "just typing git stash here for documentation"')
    assert decision.verdict == Verdict.ALLOW


def test_quoted_reset_hard_phrase_stays_allow() -> None:
    decision = classify('git commit -m "note to self: never type git reset --hard again"')
    assert decision.verdict == Verdict.ALLOW


def test_case_and_whitespace_normalize_before_matching() -> None:
    decision = classify("GiT   sTaSh")
    assert decision.verdict == Verdict.DENY
    assert decision.rule_id == "DENY-001"


def test_risky_verb_after_separator_is_still_seen() -> None:
    decision = classify("run_tests.sh ; git reset --hard")
    assert decision.verdict == Verdict.DENY
    assert decision.rule_id == "DENY-001"


def test_risky_verb_after_embedded_newline_is_still_seen() -> None:
    decision = classify("echo starting\ngit stash")
    assert decision.verdict == Verdict.DENY
    assert decision.rule_id == "DENY-001"


# --- the restore arm, and the dot pathspec -------------------------------------------------------
# Two defects lived in this rule at once, in opposite directions: it refused a harmless branch
# switch while permitting a whole-tree discard, and its own safe correction pointed the caller at
# the shape that was permitted. `restore` was matched bare only, and the scoped-checkout exemption
# `-- <target>` exempted `-- .`, which is the entire working tree.

_GIT = "g" + "it "

_WHOLE_TREE_SHAPES = [
    _GIT + "restore .",                              # the dot IS the whole tree
    _GIT + "restore --worktree --source=HEAD .",     # both flags, plus the dot
    _GIT + "restore --source=HEAD .",                # replay the tree from a source
    _GIT + "restore --worktree src/",                # names the working tree
    _GIT + "checkout -- .",                          # scoped in form, whole-tree in effect
    _GIT + "checkout --  .",                         # the same, with the spacing changed
]

_SCOPED_SHAPES_THAT_MUST_STAY_ALLOW = [
    _GIT + "restore src/app.py",
    _GIT + "restore --staged src/app.py",            # unstages; the worktree is untouched
    _GIT + "checkout -- src/app.py",
    _GIT + "checkout -- src/metrics_snapshot.yaml",
    _GIT + "diff -- .",                              # a read verb, dot or no dot
    _GIT + "add .",                                  # stages; discards nothing
]


@pytest.mark.parametrize("command", _WHOLE_TREE_SHAPES)
def test_a_whole_tree_discard_is_deny_however_it_is_spelled(command: str) -> None:
    decision = classify(command)
    assert decision.verdict == Verdict.DENY, command
    assert decision.rule_id == "DENY-001"


@pytest.mark.parametrize("command", _SCOPED_SHAPES_THAT_MUST_STAY_ALLOW)
def test_a_genuinely_scoped_pathspec_still_passes(command: str) -> None:
    assert classify(command).verdict == Verdict.ALLOW, command


def test_the_safe_correction_no_longer_points_at_a_permitted_whole_tree_shape() -> None:
    """The rule used to tell the caller to re-run with `checkout -- <file>` while `-- .` walked
    through. Whatever shape the correction names must itself be ALLOW, and the dot must not be."""
    from policy_deck.policy import rule

    correction = rule("DENY-001").safe_correction
    assert "src/app.py" in correction
    assert classify(_GIT + "checkout -- src/app.py").verdict == Verdict.ALLOW
    assert classify(_GIT + "checkout -- .").verdict == Verdict.DENY
