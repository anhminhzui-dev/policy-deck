"""The publication gate: a planted hit fails the scan, a clean tree passes.

`scripts/` is not a package, so the module is loaded by file path (per CONTRACT.md's own
instruction), and every planted string below is assembled from separate fragments joined at
runtime -- never written as one contiguous literal in this file's own source -- for the same
reason `forbidden_scan.py` builds its own patterns that way: this file is itself walked by the
real scan over the whole tree, and a literal trigger string sitting in a *test* fixture would be
a false self-inflicted hit on every real run, not a demonstration of anything.
"""

from __future__ import annotations

import importlib.util
import types
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "forbidden_scan.py"


def _load_forbidden_scan() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("forbidden_scan", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_forbidden_scan = _load_forbidden_scan()


def test_clean_tree_reports_no_hits(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text(
        "an ordinary file about reading and searching, nothing sensitive here.\n",
        encoding="utf-8",
    )
    (tmp_path / "code.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    hits = _forbidden_scan.scan_tree(tmp_path)
    assert hits == []
    assert _forbidden_scan.main(["--root", str(tmp_path)]) == 0


# An invented word. It is not private, it is not in the shipped deny set, and it appears in no
# other file: the tests below put its hash into the deny set themselves for the length of one test.
# That is the whole trick -- proving the hashed guard works needs a word the set contains, not a
# word that matters, and writing a real forbidden name here would put back exactly what the guard
# was built to keep out.
_INVENTED_WORD = "qzrivenholt"


def test_a_planted_hashed_name_is_caught(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """One planted leak, caught -- and the report of it must not repeat the word.

    The word is invented and its hash is injected here, so this test proves the mechanism without
    the suite carrying a private name in any form, fragmented or whole. The assertion that matters
    is the last one: the hit carries a hex prefix, never the word that produced it.
    """
    monkeypatch.setattr(
        _forbidden_scan, "HASHED_DENY", frozenset({_forbidden_scan.hash_token(_INVENTED_WORD)})
    )
    target = tmp_path / "leaky.md"
    target.write_text(f"internal project codename: {_INVENTED_WORD} lives here\n", encoding="utf-8")

    hits = _forbidden_scan.scan_tree(tmp_path)
    assert len(hits) == 1
    path, lineno, label, line = hits[0]
    assert path == target
    assert lineno == 1
    assert label == "hashed_name"
    assert line.startswith("sha256:")
    assert _INVENTED_WORD not in line.lower()

    assert _forbidden_scan.main(["--root", str(tmp_path)]) == 1


def test_planted_drive_letter_path_is_caught(tmp_path: Path) -> None:
    drive_path = "C" + ":" + "\\" + "fake" + "\\" + "path" + "\\" + "file.txt"
    (tmp_path / "config.md").write_text(f"the file lives at {drive_path}\n", encoding="utf-8")

    hits = _forbidden_scan.scan_tree(tmp_path)
    labels = [h[2] for h in hits]
    assert "drive_letter" in labels


def test_planted_grade_claim_is_caught(tmp_path: Path) -> None:
    # The assembled word + "=6" is never written as one contiguous run in this file's own text,
    # including in this comment -- the whole point of the exercise is that grep-for-the-literal
    # would find nothing here, yet the runtime string built below still trips the real scanner.
    grade_line = "ba" + "nd" + "=" + "6"
    (tmp_path / "report.md").write_text(f"result: {grade_line}\n", encoding="utf-8")

    hits = _forbidden_scan.scan_tree(tmp_path)
    labels = [h[2] for h in hits]
    assert "grade_claim" in labels


def test_hit_line_is_truncated_to_120_chars(tmp_path: Path) -> None:
    # Any hit whose payload is the offending line will do, so this uses the value-carrying label
    # pattern rather than a name: the truncation is a property of the report, not of the rule.
    grade_line = "ba" + "nd" + "=" + "6"
    long_line = grade_line + " " + ("x" * 300)
    (tmp_path / "long.md").write_text(long_line + "\n", encoding="utf-8")

    hits = _forbidden_scan.scan_tree(tmp_path)
    assert len(hits[0][3]) <= 120


def test_non_utf8_file_is_skipped_not_crashed_on(tmp_path: Path) -> None:
    (tmp_path / "binary.dat").write_bytes(b"\xff\xfe\x00\x01not utf-8 at all")
    hits = _forbidden_scan.scan_tree(tmp_path)
    assert hits == []


def test_pycache_and_git_directories_are_skipped(tmp_path: Path) -> None:
    grade_line = "ba" + "nd" + "=" + "6"
    skip_dir = tmp_path / "__pycache__"
    skip_dir.mkdir()
    (skip_dir / "cached.md").write_text(grade_line, encoding="utf-8")
    hits = _forbidden_scan.scan_tree(tmp_path)
    assert hits == []


def test_the_shipped_repo_tree_is_itself_clean() -> None:
    """The actual publication gate: the real repo, as built, must carry zero hits."""
    hits = _forbidden_scan.scan_tree(_REPO_ROOT)
    assert hits == [], hits
