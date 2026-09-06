"""load_deck(): accepts a well-formed deck, rejects every named malformation with DeckError."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from policy_deck.deck import DeckError, DeckRow, load_deck, serialize, write_deck

_GOOD_ROW = DeckRow(
    case_id="syn-read_traffic-0001",
    command="cat reports/summary.txt",
    expected="ALLOW",
    expected_rule=None,
    cls="read_traffic",
    template_id="read_cat",
    source="synthetic",
    why="ordinary read traffic",
    known_gap=False,
)


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "deck.jsonl"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def test_load_deck_accepts_a_well_formed_deck(tmp_path: Path) -> None:
    target = tmp_path / "deck.jsonl"
    write_deck([_GOOD_ROW], target)
    rows = load_deck(target)
    assert len(rows) == 1
    assert rows[0].case_id == "syn-read_traffic-0001"


def test_load_deck_rejects_empty_file(tmp_path: Path) -> None:
    path = _write(tmp_path, "")
    with pytest.raises(DeckError):
        load_deck(path)


def test_load_deck_rejects_blank_line(tmp_path: Path) -> None:
    good_line = serialize([_GOOD_ROW]).rstrip("\n")
    path = _write(tmp_path, good_line + "\n\n" + good_line.replace("0001", "0002") + "\n")
    with pytest.raises(DeckError, match="blank line"):
        load_deck(path)


def test_load_deck_rejects_invalid_json(tmp_path: Path) -> None:
    path = _write(tmp_path, "{not valid json\n")
    with pytest.raises(DeckError):
        load_deck(path)


def test_load_deck_rejects_missing_key(tmp_path: Path) -> None:
    obj = _GOOD_ROW.to_json_obj()
    del obj["why"]
    path = _write(tmp_path, json.dumps(obj, sort_keys=True) + "\n")
    with pytest.raises(DeckError, match="missing key"):
        load_deck(path)


def test_load_deck_rejects_unknown_key(tmp_path: Path) -> None:
    obj = _GOOD_ROW.to_json_obj()
    obj["extra_field"] = "not part of the schema"
    path = _write(tmp_path, json.dumps(obj, sort_keys=True) + "\n")
    with pytest.raises(DeckError, match="unknown key"):
        load_deck(path)


def test_load_deck_rejects_bad_verdict(tmp_path: Path) -> None:
    obj = _GOOD_ROW.to_json_obj()
    obj["expected"] = "MAYBE"
    path = _write(tmp_path, json.dumps(obj, sort_keys=True) + "\n")
    with pytest.raises(DeckError):
        load_deck(path)


def test_load_deck_rejects_duplicate_case_id(tmp_path: Path) -> None:
    line = serialize([_GOOD_ROW]).rstrip("\n")
    path = _write(tmp_path, line + "\n" + line + "\n")
    with pytest.raises(DeckError, match="duplicate"):
        load_deck(path)


def test_load_deck_rejects_wrong_type_for_known_gap(tmp_path: Path) -> None:
    obj = _GOOD_ROW.to_json_obj()
    obj["known_gap"] = "false"  # string, not bool
    path = _write(tmp_path, json.dumps(obj, sort_keys=True) + "\n")
    with pytest.raises(DeckError):
        load_deck(path)


def test_load_deck_rejects_row_that_is_not_an_object(tmp_path: Path) -> None:
    path = _write(tmp_path, "[1, 2, 3]\n")
    with pytest.raises(DeckError):
        load_deck(path)


def test_error_message_names_the_line_number(tmp_path: Path) -> None:
    good_line = serialize([_GOOD_ROW]).rstrip("\n")
    path = _write(tmp_path, good_line + "\n" + "{bad json\n")
    with pytest.raises(DeckError, match="line 2"):
        load_deck(path)


def test_write_deck_returns_the_sha_of_what_it_wrote(tmp_path: Path) -> None:
    target = tmp_path / "deck.jsonl"
    sha = write_deck([_GOOD_ROW], target)
    on_disk = target.read_text(encoding="utf-8")
    from policy_deck.deck import deck_sha256

    assert sha == deck_sha256(on_disk)
