"""The CLI, invoked in-process via main(argv) -- never a subprocess, never a shell."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from policy_deck import __version__
from policy_deck.cli import main

_REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _run_from_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI's default paths (decks/..., budget.json) are relative to the repo root."""
    monkeypatch.chdir(_REPO_ROOT)


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--version"])
    out = capsys.readouterr().out.strip()
    assert exit_code == 0
    assert out == __version__


def test_no_subcommand_prints_help_and_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([])
    out = capsys.readouterr().out
    assert exit_code == 2
    assert "usage" in out.lower()


def test_score_exits_zero_on_the_shipped_deck(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["score"])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "PASS" in out


def test_score_json_prints_a_parseable_receipt(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["score", "--json"])
    out = capsys.readouterr().out.strip()
    assert exit_code == 0
    payload = json.loads(out)
    assert payload["schema"] == "policy-deck/parity/1"
    assert payload["passed"] is True


def test_score_writes_a_receipt_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    receipt_path = tmp_path / "parity.json"
    exit_code = main(["score", "--receipt", str(receipt_path)])
    capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert payload["schema"] == "policy-deck/parity/1"
    assert receipt_path.read_text(encoding="utf-8").endswith("\n")


def test_generate_deck_check_passes_on_the_pinned_seed(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["generate-deck", "--check"])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "matches pinned sha256" in out


def test_generate_deck_check_fails_on_a_different_seed(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["generate-deck", "--seed", "1", "--check"])
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "drift" in out.lower()


def test_generate_deck_writes_a_file_and_prints_its_sha(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_path = tmp_path / "regenerated.jsonl"
    exit_code = main(["generate-deck", "--out", str(out_path)])
    out = capsys.readouterr().out.strip()
    assert exit_code == 0
    assert len(out) == 64  # a bare sha256 hex digest
    assert out_path.exists()


def test_explain_text_output_for_a_blocked_command(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["explain", "git push --force origin main"])
    out = capsys.readouterr().out
    assert exit_code == 1
    assert out.startswith("ASK_IRREVERSIBLE  IRR-002")


def test_explain_text_output_for_an_allowed_command(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["explain", "git status"])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert out.startswith("ALLOW")


def test_explain_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["explain", "git push --force origin main", "--json"])
    out = capsys.readouterr().out.strip()
    assert exit_code == 1
    payload = json.loads(out)
    assert payload["rule_id"] == "IRR-002"


def test_explain_approve_irreversible_flag_clears_the_block(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(
        ["explain", "git push --force origin main", "--approve-irreversible"]
    )
    out = capsys.readouterr().out
    assert exit_code == 0
    assert out.startswith("ALLOW")


def test_explain_stdin_reads_one_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("git status"))
    exit_code = main(["explain", "--stdin"])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert out.startswith("ALLOW")


def test_explain_requires_command_or_stdin(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["explain"])
    err = capsys.readouterr().err
    assert exit_code == 2
    assert "COMMAND" in err or "stdin" in err
