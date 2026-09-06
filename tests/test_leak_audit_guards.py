"""The guards added by the leak audit, each with the negative case that makes it worth having.

Three things are asserted here, and each one exists because the claim it holds up is the kind a
reader has no way to check by eye:

1. The hashed half of `forbidden_scan` actually denies something, and a hit from it never prints
   the word that produced it. A guard whose whole justification is "the forbidden names are not
   written anywhere in this repository" is worthless if its own output writes them.
2. A personal mailbox at a consumer mail provider is refused, while the code-host no-reply address
   this package's metadata carries is not. Those two are one character class apart and a rule that
   cannot tell them apart is either useless or unusable.
3. An unfilled licence placeholder stops the tree from reading as publishable, under its own exit
   code -- and a filled one does not.

This file is itself walked by the real scan on every run, so it carries no private word at all.
Where a test needs one, it invents a word and injects that word's hash into the deny set for the
length of the test. Fragmenting a real name across two literals was the earlier answer here and it
was the wrong one: a split word hides from a grep and from nothing else.
"""

from __future__ import annotations

import importlib.util
import types
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "forbidden_scan.py"


def _load_forbidden_scan() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("forbidden_scan_leak_audit", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_scan = _load_forbidden_scan()

# An invented word, private to nobody, in the shipped deny set of nothing. Tests that need a denied
# word inject its hash themselves rather than writing a real one into a file that ships.
_INVENTED_WORD = "qzrivenholt"


# --- 1. the hashed half ---------------------------------------------------------------


def test_the_hashed_deny_set_is_not_empty() -> None:
    """An empty set would make every test below pass vacuously and every real run read clean."""
    assert len(_scan.HASHED_DENY) >= 20
    for digest in _scan.HASHED_DENY:
        assert len(digest) == 64
        assert all(ch in "0123456789abcdef" for ch in digest)


def test_a_hashed_name_is_caught_and_its_hit_never_carries_the_word(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative case, built without any real forbidden word: invent one, put its hash in the
    deny set for the length of this test, plant it, and require both that it is caught and that the
    report withholds it. Using a real private name here would reintroduce the leak the hashed set
    exists to prevent -- the suite is shipped too."""
    monkeypatch.setattr(_scan, "HASHED_DENY", frozenset({_scan.hash_token(_INVENTED_WORD)}))

    (tmp_path / "leaky.md").write_text(f"the {_INVENTED_WORD} directory\n", encoding="utf-8")
    hits = _scan.scan_tree(tmp_path)
    hashed = [h for h in hits if h[2] == "hashed_name"]
    assert len(hashed) == 1
    assert hashed[0][3].startswith("sha256:")
    assert _INVENTED_WORD not in hashed[0][3].lower()


def test_an_ordinary_word_is_not_denied(tmp_path: Path) -> None:
    """The other direction: the hashed half must not fire on ordinary prose, or nobody can ship."""
    (tmp_path / "ok.md").write_text(
        "an ordinary paragraph about reading files, searching them, and printing a summary.\n",
        encoding="utf-8",
    )
    assert _scan.scan_tree(tmp_path) == []


def test_hash_tokens_file_round_trips_and_is_sorted(tmp_path: Path) -> None:
    """`--hash-tokens` is how the set is regenerated; the same list must produce the same block."""
    word_list = tmp_path / "words.txt"
    word_list.write_text("# a comment\n\nAlpha\nbravo\nALPHA\n", encoding="utf-8")
    hexes = _scan.hash_tokens_file(word_list)
    assert hexes == sorted(hexes)
    assert len(hexes) == 2, "case-folded and de-duplicated"
    assert _scan.hash_token("alpha") in hexes
    assert _scan.hash_token("bravo") in hexes
    block = _scan.hashed_deny_block(hexes)
    for digest in hexes:
        assert f'"{digest}",' in block


def test_hash_tokens_on_a_missing_list_is_an_operational_error(tmp_path: Path) -> None:
    assert _scan.main(["--hash-tokens", str(tmp_path / "nope.txt")]) == 2


# --- 2. the mailbox shape rule --------------------------------------------------------


def test_a_consumer_mailbox_is_refused(tmp_path: Path) -> None:
    address = "someone" + "@" + "gm" + "ail" + ".com"
    (tmp_path / "contact.md").write_text(f"write to {address}\n", encoding="utf-8")
    labels = {h[2] for h in _scan.scan_tree(tmp_path)}
    assert "personal_mail_address" in labels


def test_the_code_host_no_reply_address_is_allowed(tmp_path: Path) -> None:
    """The rule has to leave this one alone: it is the address that replaces the personal one."""
    address = "someone-dev" + "@" + "users.norep" + "ly.github.com"
    (tmp_path / "meta.toml").write_text(f'email = "{address}"\n', encoding="utf-8")
    assert _scan.scan_tree(tmp_path) == []


def test_the_shipped_metadata_carries_no_consumer_mailbox() -> None:
    """The real check, on the real tree, rather than on a fixture."""
    hits, files_scanned = _scan.scan_tree_with_count(_REPO_ROOT)
    assert files_scanned > 0
    assert [h for h in hits if h[2] == "personal_mail_address"] == []


# --- 3. the licence placeholder gate --------------------------------------------------


def test_an_unfilled_placeholder_exits_three_not_zero(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text(
        "Copyright (c) 2026 " + _scan.LICENCE_PLACEHOLDER.upper() + ". All rights reserved.\n",
        encoding="utf-8",
    )
    assert _scan.main(["--root", str(tmp_path)]) == 3


def test_a_filled_licence_exits_zero(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text(
        "Copyright (c) 2026 A Real Name. All rights reserved.\n", encoding="utf-8"
    )
    assert _scan.main(["--root", str(tmp_path)]) == 0


def test_a_leak_outranks_an_unfilled_placeholder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both wrong at once must report the leak: exit 1 is the more urgent of the two."""
    monkeypatch.setattr(_scan, "HASHED_DENY", frozenset({_scan.hash_token(_INVENTED_WORD)}))
    (tmp_path / "LICENSE").write_text(_scan.LICENCE_PLACEHOLDER + "\n", encoding="utf-8")
    (tmp_path / "leaky.md").write_text(_INVENTED_WORD + "\n", encoding="utf-8")
    assert _scan.main(["--root", str(tmp_path)]) == 1


def test_the_scanner_does_not_report_itself_as_an_unfilled_licence() -> None:
    """The placeholder is assembled from fragments inside the scanner for exactly this reason, so
    that the file defining it needs no skip rule and the "no self-exemption" claim stays true."""
    source = _SCRIPT_PATH.read_text(encoding="utf-8")
    assert _scan.LICENCE_PLACEHOLDER not in source.lower()
    assert _SCRIPT_PATH not in _scan.unfilled_placeholder_files(_REPO_ROOT)


def test_the_shipped_tree_carries_no_unfilled_placeholder() -> None:
    """The holder was filled in by the owner at publication, so the shipped tree must report no
    unfilled placeholder anywhere, and the licence must name a holder on its copyright line. The
    guard's ability to catch an unfilled placeholder is proven on throwaway trees above, never on
    the shipped one."""
    flagged = {p.name for p in _scan.unfilled_placeholder_files(_REPO_ROOT)}
    assert flagged == set(), flagged
    licence = (_REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Copyright (c) 2026 " in licence
    assert _scan.LICENCE_PLACEHOLDER not in licence.lower()
