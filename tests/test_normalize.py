"""normalize(), strip_heredoc_bodies(), and is_malformed() as pure functions."""

from __future__ import annotations

from policy_deck import normalize
from policy_deck.classifier import is_malformed, strip_heredoc_bodies


def test_whitespace_collapses_to_single_spaces() -> None:
    assert normalize("git   push    --force   origin   main") == "git push --force origin main"


def test_case_folds_to_lowercase() -> None:
    assert normalize("GIT PUSH --FORCE") == "git push --force"


def test_newlines_collapse_like_any_other_whitespace() -> None:
    assert normalize("echo hi\ngit stash") == "echo hi git stash"


def test_leading_and_trailing_whitespace_is_stripped() -> None:
    assert normalize("   git status   ") == "git status"


def test_heredoc_body_elided_into_non_executing_sink() -> None:
    command = "cat <<EOF > notes.md\nsome sensitive-looking content here\nEOF"
    stripped = strip_heredoc_bodies(command)
    assert "sensitive-looking" not in stripped
    assert "__heredoc_body_elided__" in stripped


def test_heredoc_body_kept_when_piped_into_an_interpreter() -> None:
    command = "bash <<EOF\necho this body must stay visible\nEOF"
    stripped = strip_heredoc_bodies(command)
    assert "this body must stay visible" in stripped
    assert "__heredoc_body_elided__" not in stripped


def test_heredoc_elision_runs_before_whitespace_collapse() -> None:
    """Collapsing whitespace before eliding would fuse the body into the surrounding command."""
    command = "cat <<EOF > notes.md\ngit push --force origin main\nEOF"
    normalized = normalize(command)
    assert "--force" not in normalized


def test_is_malformed_empty_string() -> None:
    assert is_malformed("") is True


def test_is_malformed_whitespace_only() -> None:
    assert is_malformed("   ") is True


def test_is_malformed_non_string() -> None:
    assert is_malformed(None) is True
    assert is_malformed(12345) is True


def test_is_malformed_contains_nul() -> None:
    assert is_malformed("echo hi\x00bye") is True


def test_is_malformed_over_length() -> None:
    from policy_deck import MAX_COMMAND_CHARS

    assert is_malformed("a" * (MAX_COMMAND_CHARS + 1)) is True


def test_is_malformed_well_formed_command() -> None:
    assert is_malformed("git status") is False
