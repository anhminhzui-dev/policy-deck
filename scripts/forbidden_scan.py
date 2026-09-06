"""Scan a tree of text files for the strings this package must never ship.

The word-based patterns below are assembled at runtime from short fragments (see `_frag` and the
module-level `_W_*` constants) so that no guarded word appears anywhere in this file's own source
text, neither in a string literal nor in an identifier. The constants are named for what they
*hold*, never for the word itself, because a constant named after a guarded word puts that word
back into the file the scan is supposed to keep clean. `tests/test_forbidden_scan.py` asserts this
property directly against this file's bytes, so the paragraph you are reading is checked, not
claimed.

The fragmented half holds only ORDINARY vocabulary -- the label and claim words that make a
measurement leak recognisable. It holds no private name of any kind, and that is deliberate: two
string literals joined by `_frag` are readable to anyone who reads the line, so fragmenting is
concealment from a grep and from nothing else. Every private name lives in the hashed half below
instead, where it cannot be read back out at all.

That is not stylistic: this scanner is itself scanned by CI on every run, and a scanner that
could not survive its own scan would prove nothing about anything else. There is no
self-exemption and no allowlist; if this file ever needed to print one of the assembled words in
its own prose, that would be a defect in this file, not a case for an exception.

A second half of the guard is HASHED_DENY: sha256 hexes of forbidden *names* -- an examination
name, a rights holder, an internal codename, a private storage directory, an institution used in
a private demonstration, an outreach contact. Those names are never written in this file at all,
not even split into fragments; only their one-way hexes are compared, and a hit prints the hex
prefix rather than the line that produced it, because printing the line would republish the very
name the guard exists to keep out. The set is generated with --hash-tokens from a word list kept
OUTSIDE this repository. An empty set is announced in the output rather than passing quietly.

Why two halves and not one: fragments are readable to a determined reader and cannot cover a name
whose leak would matter most, while hexes cannot be reviewed at all. The fragmented half covers
the words this package legitimately discusses; the hashed half covers the words it must never
print.

One private string is deliberately NOT hashed: the owner's personal mailbox handle, because the
same handle is the local part of the public no-reply contact address this package's metadata is
entitled to carry. Denying the handle would deny the address that replaces it. A shape rule
covers it instead -- a mailbox at a consumer mail provider -- which names no person.

The scan also reports how many files it walked and exits 2 when that count is zero. A scan of an
empty or wrong root is not a clean tree -- it is a broken instrument, and the two must not print
the same result.

Finally the scan refuses an unfilled licence placeholder, under its own exit code 3. An unfilled
holder is not a leak -- it is a repository that is not ready to be published -- and folding the
two into one number would let a reader confuse "nothing private got out" with "this is ready to
go out".
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections.abc import Sequence
from pathlib import Path

_SKIP_DIR_NAMES = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", "venv", ".venv"}
_MAX_LINE_CHARS = 120


def _frag(*parts: str) -> str:
    return "".join(parts)


# Each guarded word is split across two or more literal fragments so the whole word never appears
# as a contiguous run of characters in this file's own text. The names below say what each
# constant is FOR, never what it contains: naming a constant after the word it holds would put
# that word back in this file, which is exactly what the fragmenting is here to prevent.
#
# Only ordinary vocabulary is fragmented. Private names -- codenames, an examination name, rights
# holders, an outreach contact, an institution used in a private demonstration, a private storage
# directory -- are NOT here in any form: fragments are trivially rejoined by eye, so a fragmented
# private name is a published private name with an extra step. Those live in HASHED_DENY.
_W_GRADE_1 = _frag("ba", "nd")
_W_GRADE_2 = _frag("M", "ET")
_W_GRADE_3 = _frag("UN", _W_GRADE_2)
_W_GRADE_4 = _frag("sco", "re")
_W_METRIC_1 = _frag("accur", "acy")
_W_METRIC_2 = _frag("M", "AE")
_W_CLAIM_1 = _frag("preve", "nted")
_W_CLAIM_2 = _frag("incide", "nts")
_W_CLAIM_3 = _frag("doll", "ars")
_W_CLAIM_4 = _frag("sa", "ved")
_HOME_PREFIX = _frag("/", "home", "/")

# The licence placeholder, assembled like every other guarded string rather than written whole --
# not because it is private, but because this file is walked by its own scan and a whole literal
# here would report this script as an unfilled licence. Assembling it keeps the "no self-exemption
# and no allowlist" claim above literally true: there is no skip rule for this file anywhere.
LICENCE_PLACEHOLDER = _frag("<copy", "right_holder>")

# Generated with --hash-tokens from a one-word-per-line list kept OUTSIDE this repository and
# never copied into it. Only these one-way hexes are committed; the words behind them cannot be
# read back out of this file. Regenerate with:
#     python scripts/forbidden_scan.py --hash-tokens <path to the local word list>
# and paste the block it prints over this one.
HASHED_DENY: frozenset[str] = frozenset(
    {
        "032cab5ebbc988153d81c3df611c39093b5fc531696753725173be03be0d8f18",
        "0661652820890613176da180316c4cdbe82aecc68cb8426f983d2c846d3f498e",
        "09cf980b5ff304ac11b7f6d2c5c263da2a867425798ef5cc5d2ebcf55c4fcd23",
        "0c1eeccce6f114bf627c03a403d7c6e52e5b201ff1be893410a507066c9cc16b",
        "165f5e0d1d4cc3ea1e281af001e1a5998bd3f5eda2c27b913d7889c907c28306",
        "196fd26067ba4e39c19644034adcbcff5bed3b0960336a7dade607fe834d2f97",
        "2ae1dbc2d0e91a0902a10a39d8fb49d54258656cf2cecefae2234a2ea0ca7e76",
        "3ec41ddd6bfe23f613abf2889f24edda7241f0b620046b5bae8a26868380efee",
        "426e4d5cf1a4ace95793879f973338a900560f4fe2f06fa17589e5b749bd7a4e",
        "546f729f98eb03a0486f48ed2044711dfc9da79e1031a7c883c333bfb6d4e874",
        "57b003b3a857ddc804c7a66c5a27306ad653918cde9bd401251518ace61efee0",
        "5d2c13d6f9fa421125a9f55e56fd0e4df9319ef30087f8f4675cd6f05135f397",
        "656359bc1e55ae213165faf18fac5caa211123778c8695d15328b8d6de431c75",
        "659ab32d3107888aed862da1ad715088fed272e1ba4545fd6f89e0ce2624874a",
        "6d04f542b426bec69aee1f34b01588a14958749d34a1db894cc0f200f74ddf68",
        "6ff43db5339fb6aaee5417eac4a10c728799a9bf00d57901932a98b93bd87792",
        "7969bf2d3a9ceff9f774531d05be1923d0719b2b75db0e145e8af7b149aaf71f",
        "7dca25d4dd938eda65ef14a6b5a04669d440da25fe185c86ed524d7260f755a2",
        "810dc03c4810c8a4f8e7684ff5e78c4bc5266dc809aa8663b8c8f2066de4a092",
        "8367cd66fdd136bba8ba23f8805bb050dd6289401c8ec3b0be44a3c233eef90d",
        "96cad2ff6e6e60a498323095e88ae16c36fa4c5be8a19e073d804bd66e64a0ba",
        "9bcd6d530324efd4c018d3ed5425ab2896e0b9e7f2d97710a47c31c92f9ce680",
        "9d9b78271c6f54cc3107774d65c7793ee42d5935dd2a205a120c46269af6319d",
        "b2908eb1ec9c11d0d47374b0ae0b22a5dab85ea61e46ac2510993d9a281565e5",
        "b6c4ac412ac8822355239dd717c11ca5b07373e4db550d0423c1b6aeceef8493",
        "b796b6acc1242a75189ffb38e0f1c051848f28cba25af3f165772f08e43c337f",
        "d972c62454deefd5d7cb8a0c39f5015daa6d4729ba5488a3d62236a5b9c06ade",
        "e15da43055a1b48f2e9370cf9ebf22c63ff41f4c50802a952af86243688f1f4b",
        "ea6c857a49a023ae5b36782ac18860305073eac6cc84fffa2fd80521f9ddbe8e",
        "eb2f62cd01d16c0aef15953fef2cf186b76a2f42535c426cfdd13dccb8d4c296",
        "ef68e7cb2f7463ef6e071792614149c1b228699ef09cd2b52956f10c4149f251",
        "ef7d74898c22a4bf0be437d30987bc945310dcdf1ddb48a6bce085f376b302ae",
        "fbe96c8edfbfe0d97d9b4074fb1d8aec7bcd4c13c44f5291d7db0c7b637730eb",
    }
)

# Tokenisers for the hashed half. Two shapes are emitted per line because a private directory name
# carrying an underscore must be deniable whole without denying either ordinary English half of it
# on its own.
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_IDENT_RE = re.compile(r"[a-z0-9_]+")

# Every assembled word, for the self-check in tests/test_forbidden_scan.py. Kept next to the
# constants so a new fragment cannot be added without landing in the check.
ASSEMBLED_WORDS: tuple[str, ...] = (
    _W_GRADE_1, _W_GRADE_2, _W_GRADE_3, _W_GRADE_4, _W_METRIC_1, _W_METRIC_2,
    _W_CLAIM_1, _W_CLAIM_2, _W_CLAIM_3, _W_CLAIM_4,
)


def build_patterns() -> list[tuple[str, re.Pattern[str]]]:
    """(label, pattern) pairs, assembled at runtime from fragments so that no forbidden word
    exists anywhere in this file. No self-exemption and no allowlist is permitted.
    """
    patterns: list[tuple[str, re.Pattern[str]]] = []

    # No codename or party-name pattern lives here any more; both moved to HASHED_DENY, which
    # denies the same words without writing any of them down. What remains is shape and
    # vocabulary: paths, credentials, and value-carrying labels.
    patterns.append(("drive_letter", re.compile(r"\b[A-Za-z]:[\\/]")))
    patterns.append(("home_dir", re.compile(r"[\\/]Users[\\/][^\s\\/]+", re.IGNORECASE)))
    patterns.append(("home_dir", re.compile(_HOME_PREFIX + r"[^\s/]+")))
    patterns.append(("unc_path", re.compile(r"\\\\[A-Za-z0-9_.$-]+\\[A-Za-z0-9_.$-]+")))

    # A mailbox at a consumer mail provider, as a SHAPE. It names no person, and a no-reply
    # address on a code host is not a consumer mail provider, so the public contact address this
    # package is entitled to carry passes while a personal one does not.
    patterns.append(
        (
            "personal_mail_address",
            re.compile(
                r"[A-Za-z0-9._%+-]+@(?:gmail|googlemail|outlook|hotmail|live|yahoo|ymail|"
                r"icloud|aol|proton|protonmail|gmx|yandex|zoho|qq)\.[A-Za-z]{2,}"
                r"(?:\.[A-Za-z]{2,})?",
                re.IGNORECASE,
            ),
        )
    )

    patterns.append(("session_id", re.compile(r"\bs\d{3}\b")))
    patterns.append(("session_id", re.compile(r"\bsession_[0-9A-Za-z]{16,}\b")))

    patterns.append(("credential_literal", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")))
    patterns.append(("credential_literal", re.compile(r"\bAKIA[0-9A-Z]{16}\b")))
    patterns.append(
        (
            "credential_literal",
            re.compile(
                r"(?:api[_-]?key|secret|token|password|private[_-]?key)\s*[:=]\s*"
                r"['\"][A-Za-z0-9/+_=\-]{20,}['\"]",
                re.IGNORECASE,
            ),
        )
    )

    patterns.append(
        ("grade_claim", re.compile(re.escape(_W_GRADE_1) + r"\s*[:=]\s*[0-9]", re.IGNORECASE))
    )
    patterns.append(
        (
            "grade_claim",
            re.compile(
                r"\b(?:" + re.escape(_W_GRADE_3) + "|" + re.escape(_W_GRADE_2) + r")\s*[:=]\s*\S+",
                re.IGNORECASE,
            ),
        )
    )
    patterns.append(
        ("grade_claim", re.compile(re.escape(_W_GRADE_4) + r"\s*[:=]\s*[0-9]", re.IGNORECASE))
    )

    patterns.append(
        (
            "accuracy_claim",
            re.compile(re.escape(_W_METRIC_1) + r"\s*(?:of|is)?\s*[:=]?\s*\d", re.IGNORECASE),
        )
    )
    patterns.append(
        ("accuracy_claim", re.compile(r"\b" + re.escape(_W_METRIC_2) + r"\b\s*[:=]?\s*[0-9]"))
    )
    patterns.append(
        (
            "accuracy_claim",
            re.compile(
                r"\d{1,3}(?:\.\d+)?\s*%\s*(?:" + re.escape(_W_METRIC_1) + r"|precision|recall)",
                re.IGNORECASE,
            ),
        )
    )

    patterns.append(
        (
            "incident_claim",
            re.compile(
                re.escape(_W_CLAIM_1) + r"\s+\d+\s+" + re.escape(_W_CLAIM_2), re.IGNORECASE
            ),
        )
    )
    patterns.append(
        (
            "incident_claim",
            re.compile(r"\$\s?[\d,]+(?:\.\d+)?\s*" + re.escape(_W_CLAIM_4), re.IGNORECASE),
        )
    )
    patterns.append(
        (
            "incident_claim",
            re.compile(re.escape(_W_CLAIM_3) + r"\s+" + re.escape(_W_CLAIM_4), re.IGNORECASE),
        )
    )

    return patterns


def word_tokens(text: str) -> set[str]:
    """Lower-case tokens in two shapes: bare alphanumeric runs, and runs that keep underscores."""
    lowered = text.lower()
    return set(_TOKEN_RE.findall(lowered)) | set(_IDENT_RE.findall(lowered))


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_tokens_file(path: Path) -> list[str]:
    """sha256 hex of every non-blank, non-comment line of a local word list. Sorted, so the same
    list regenerates a byte-identical block and a diff shows only what actually changed.
    """
    hexes: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        word = raw.strip().lower()
        if not word or word.startswith("#"):
            continue
        hexes.add(hash_token(word))
    return sorted(hexes)


def hashed_deny_block(hexes: list[str]) -> str:
    """The exact text block that belongs inside HASHED_DENY above."""
    return "\n".join(f'        "{h}",' for h in hexes)


def unfilled_placeholder_files(root: Path) -> list[Path]:
    """Files still carrying the unfilled licence placeholder. Not a leak: a not-ready repository."""
    found: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if LICENCE_PLACEHOLDER in text.lower():
            found.append(path)
    return found


def scan_tree_with_count(root: Path) -> tuple[list[tuple[Path, int, str, str]], int]:
    """Walk every text file under root, skipping .git and __pycache__ and any file that is not
    utf-8 decodable. Return (hits, files_scanned), where each hit is (path, 1-based line number,
    label, the offending line truncated to 120 chars).

    The file count is returned, not merely logged, because zero files scanned and zero hits found
    are completely different facts that otherwise print identically.
    """
    patterns = build_patterns()
    hits: list[tuple[Path, int, str, str]] = []
    files_scanned = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        files_scanned += 1
        for lineno, line in enumerate(text.splitlines(), start=1):
            for label, pattern in patterns:
                if pattern.search(line):
                    hits.append((path, lineno, label, line.strip()[:_MAX_LINE_CHARS]))
            if HASHED_DENY:
                for token in word_tokens(line):
                    digest = hash_token(token)
                    if digest in HASHED_DENY:
                        # The hex prefix, never the line: the line holds the forbidden name, and a
                        # report that prints it has published exactly what it was guarding.
                        hits.append((path, lineno, "hashed_name", f"sha256:{digest[:12]}"))
    return hits, files_scanned


def scan_tree(root: Path) -> list[tuple[Path, int, str, str]]:
    """The hits alone, for callers that do not need the file count."""
    hits, _files_scanned = scan_tree_with_count(root)
    return hits


def main(argv: Sequence[str] | None = None) -> int:
    """`--root PATH` (default "."). Print one line per hit as `path:line: label`, then a summary
    line `scanned N files, H hits`.

    `--hash-tokens PATH` prints the HASHED_DENY block for a local word list and exits without
    scanning; the list itself is never read into the repository.

    Exit 0 when the tree was walked, is clean, and carries no unfilled licence placeholder. Exit 1
    when there is at least one hit. Exit 2 when no file was scanned at all -- an empty or wrong
    root is a broken instrument, not a clean tree, and a CI step run from the wrong working
    directory must not read as a pass. Exit 3 when the tree is clean but the licence still names
    no copyright holder: nothing private got out, and this is still not ready to be published.
    """
    parser = argparse.ArgumentParser(prog="forbidden_scan")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--hash-tokens",
        type=Path,
        default=None,
        help="path to a local, out-of-repository, one-word-per-line list; print the HASHED_DENY "
        "block for it and exit without scanning",
    )
    args = parser.parse_args(argv)

    if args.hash_tokens is not None:
        if not args.hash_tokens.is_file():
            print(f"operational error: word list not found: {args.hash_tokens}")
            return 2
        hexes = hash_tokens_file(args.hash_tokens)
        print("HASHED_DENY: frozenset[str] = frozenset(")
        print("    {")
        print(hashed_deny_block(hexes))
        print("    }")
        print(")")
        return 0

    hits, files_scanned = scan_tree_with_count(args.root)
    for path, lineno, label, _line in hits:
        print(f"{path}:{lineno}: {label}")
    print(f"scanned {files_scanned} files, {len(hits)} hits")
    if not HASHED_DENY:
        print(
            "NOTE: HASHED_DENY is empty -- the hashed half of this guard is INACTIVE. "
            "Generate it with --hash-tokens before reading a clean result as complete."
        )
    if files_scanned == 0:
        print(f"operational error: no files scanned under {args.root}")
        return 2
    if hits:
        return 1
    placeholder_files = unfilled_placeholder_files(args.root)
    if placeholder_files:
        for path in placeholder_files:
            print(f"{path}: licence placeholder is unfilled")
        print(
            f"publication blocker: {LICENCE_PLACEHOLDER} still stands in "
            f"{len(placeholder_files)} file(s); fill in the copyright holder before publishing"
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
