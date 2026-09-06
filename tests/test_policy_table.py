"""The rule table itself: shape invariants, and that README.md's table cannot drift from it."""

from __future__ import annotations

import re
from pathlib import Path

from policy_deck import APPROVAL_TOKENS, RULES, SEVERITY, Family, Verdict

_REPO_ROOT = Path(__file__).resolve().parent.parent
_MARKER_START = "<!-- RULES_TABLE -->"
_MARKER_END = "<!-- /RULES_TABLE -->"


def test_eleven_rules() -> None:
    assert len(RULES) == 11


def test_rule_ids_unique() -> None:
    ids = [r.id for r in RULES]
    assert len(ids) == len(set(ids))


def test_every_rule_has_a_title_and_a_safe_correction() -> None:
    for r in RULES:
        assert r.title.strip() != ""
        assert len(r.title) <= 90
        assert r.safe_correction.strip() != ""


def test_verdict_matches_family() -> None:
    expected = {
        Family.SPEND: Verdict.ASK_MONEY,
        Family.IRREVERSIBLE: Verdict.ASK_IRREVERSIBLE,
        Family.DESTRUCTIVE: Verdict.DENY,
        Family.LEAK: Verdict.DENY,
        Family.INPUT: Verdict.DENY,
    }
    for r in RULES:
        assert r.verdict == expected[r.family]


def test_ask_families_have_a_token_deny_families_have_none() -> None:
    for r in RULES:
        assert r.approval_token == APPROVAL_TOKENS.get(r.family)
        if r.family in (Family.SPEND, Family.IRREVERSIBLE):
            assert r.approval_token is not None
        else:
            assert r.approval_token is None


def test_severity_is_strictly_ordered_across_verdicts() -> None:
    assert SEVERITY[Verdict.ALLOW] < SEVERITY[Verdict.ASK_MONEY]
    assert SEVERITY[Verdict.ASK_MONEY] < SEVERITY[Verdict.ASK_IRREVERSIBLE]
    assert SEVERITY[Verdict.ASK_IRREVERSIBLE] < SEVERITY[Verdict.DENY]


def _parse_markdown_table(block: str) -> list[tuple[str, str, str, str]]:
    """Parse a `| id | family | verdict | title |` pipe table into (id, family, verdict, title)."""
    rows: list[tuple[str, str, str, str]] = []
    lines = [line.strip() for line in block.splitlines() if line.strip().startswith("|")]
    # First line is the header, second is the `---` separator; data starts at index 2.
    for line in lines[2:]:
        cells = [re.sub(r"^`|`$", "", c.strip()) for c in line.strip("|").split("|")]
        assert len(cells) == 4, f"expected 4 columns, got {len(cells)}: {line!r}"
        rows.append((cells[0], cells[1], cells[2], cells[3]))
    return rows


def test_readme_rules_table_matches_the_code_exactly() -> None:
    readme_path = _REPO_ROOT / "README.md"
    assert readme_path.exists(), "README.md must exist at the repo root"
    text = readme_path.read_text(encoding="utf-8")

    start = text.find(_MARKER_START)
    end = text.find(_MARKER_END)
    assert start != -1, f"missing marker {_MARKER_START!r} in README.md"
    assert end != -1, f"missing marker {_MARKER_END!r} in README.md"
    assert start < end, "RULES_TABLE start marker must precede the end marker"

    block = text[start + len(_MARKER_START) : end]
    parsed = _parse_markdown_table(block)

    expected = [(r.id, r.family.value, r.verdict.value, r.title) for r in RULES]
    assert parsed == expected


def test_pyproject_version_matches_dunder_version() -> None:
    # Avoid tomllib (stdlib only from 3.11) so this test still collects and runs on 3.10, per
    # the project's stated Python floor -- a plain regex over `version = "..."` is enough here.
    from policy_deck import __version__

    pyproject_path = _REPO_ROOT / "pyproject.toml"
    assert pyproject_path.exists(), "pyproject.toml must exist at the repo root"
    text = pyproject_path.read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    assert match is not None, "pyproject.toml must declare a top-level version = \"...\""
    assert match.group(1) == __version__
