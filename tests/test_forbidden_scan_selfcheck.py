"""Two things a reviewer checks in the first five minutes, asserted instead of claimed.

1. The scanner's docstring says no forbidden word appears in its own source text. Before this
   change that was false in a way anyone would find immediately: the constants were *named* after
   the words they held (`_W_<codename>`), so grepping the scanner for a codename returned hits in
   the scanner itself. The code was right -- `_` is a word character, so the `\\b` anchors never
   fired on an identifier -- but the sentence was not, and an overstated sentence in a file whose
   whole job is not overstating things is worth more than the two minutes it costs to fix.

2. A scan of an empty or wrong root exited 0 with no output, which in CI is indistinguishable
   from a clean tree. It now prints the file count and exits 2 when nothing was scanned.
"""

from __future__ import annotations

import importlib.util
import re
import types
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "forbidden_scan.py"


def _load_forbidden_scan() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("forbidden_scan_selfcheck", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_forbidden_scan = _load_forbidden_scan()


def test_no_assembled_word_appears_in_the_scanner_source() -> None:
    """The docstring's claim, checked against the file's own bytes -- identifiers included."""
    source = _SCRIPT_PATH.read_text(encoding="utf-8")
    for word in _forbidden_scan.ASSEMBLED_WORDS:
        pattern = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
        assert pattern.search(source) is None, word


def test_every_assembled_word_is_short_enough_to_be_a_word_not_a_sentence() -> None:
    """A guard on the check above: if ASSEMBLED_WORDS ever went empty or filled with junk, the
    test above would pass vacuously. The floor is 9 rather than 15 because the eight private NAMES
    that used to be fragmented here were moved into the hashed set, where they cannot be read back
    out; what is left is ordinary label and claim vocabulary."""
    assert len(_forbidden_scan.ASSEMBLED_WORDS) >= 9
    for word in _forbidden_scan.ASSEMBLED_WORDS:
        assert 2 <= len(word) <= 30, word


def test_the_self_check_can_fail(tmp_path: Path) -> None:
    """The negative case for the check above: a copy of the scanner with one assembled word
    written into it as a plain literal must be caught."""
    source = _SCRIPT_PATH.read_text(encoding="utf-8")
    planted = source + "\n# " + _forbidden_scan.ASSEMBLED_WORDS[0] + "\n"
    copy = tmp_path / "planted_scan.py"
    copy.write_text(planted, encoding="utf-8")
    pattern = re.compile(
        r"\b" + re.escape(_forbidden_scan.ASSEMBLED_WORDS[0]) + r"\b", re.IGNORECASE
    )
    assert pattern.search(copy.read_text(encoding="utf-8")) is not None


def test_scan_prints_the_file_count_on_a_clean_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.md").write_text("ordinary notes\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    exit_code = _forbidden_scan.main(["--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "scanned 2 files, 0 hits" in out


def test_scan_counts_hits_in_the_summary_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    grade_line = "ba" + "nd" + "=" + "6"
    (tmp_path / "leaky.md").write_text(f"{grade_line}\n", encoding="utf-8")
    exit_code = _forbidden_scan.main(["--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "scanned 1 files, 1 hits" in out


def test_empty_root_exits_two_not_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A wrong working directory in CI must not read as a pass."""
    empty = tmp_path / "nothing_here"
    empty.mkdir()
    exit_code = _forbidden_scan.main(["--root", str(empty)])
    out = capsys.readouterr().out
    assert exit_code == 2
    assert "scanned 0 files, 0 hits" in out
    assert "operational error" in out


def test_a_root_of_only_skipped_directories_also_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "x.md").write_text("anything\n", encoding="utf-8")
    exit_code = _forbidden_scan.main(["--root", str(tmp_path)])
    assert exit_code == 2
    assert "scanned 0 files" in capsys.readouterr().out


def test_scan_tree_with_count_returns_both_halves(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("ordinary\n", encoding="utf-8")
    hits, files_scanned = _forbidden_scan.scan_tree_with_count(tmp_path)
    assert hits == []
    assert files_scanned == 1


def test_the_shipped_tree_is_clean_and_non_empty() -> None:
    hits, files_scanned = _forbidden_scan.scan_tree_with_count(_REPO_ROOT)
    assert files_scanned > 0
    assert hits == [], hits
