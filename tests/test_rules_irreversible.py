"""IRR-001..004: three positives and one near-miss negative per rule."""

from __future__ import annotations

import pytest

from policy_deck import Verdict, classify

_IRR_001_POSITIVE = [
    "cp out.parquet data/locked/train.parquet",
    "mv summary.json protected/summary.json",
    "tee immutable/notes.txt",
]
_IRR_001_NEGATIVE = [
    "cat data/locked/train.parquet",
    "ls data/locked",
]

_IRR_002_POSITIVE = [
    "git push --force origin main",
    "git push -f origin main",
    "git push --force-with-lease origin main",
]
_IRR_002_NEGATIVE = [
    "git push origin main",
    "git push --dry-run",
]

_IRR_003_POSITIVE = [
    "rm -rf data",
    "rm -fr datasets/train",
    "rm -r -f checkpoints",
]
_IRR_003_NEGATIVE = [
    "rm -f data/one_file.txt",
    "rm -rf build",
]

_IRR_004_POSITIVE = [
    "cp model.bin checkpoints/final.bin --overwrite",
    "mv new.pt checkpoints/best.pt",
    "cp run.ckpt checkpoints/latest.ckpt",
]
_IRR_004_NEGATIVE = [
    "cp model.bin checkpoints/model-v12.bin",
    "mv new.pt checkpoints/step00050.pt",
]


@pytest.mark.parametrize("command", _IRR_001_POSITIVE)
def test_irr_001_positive(command: str) -> None:
    decision = classify(command)
    assert decision.verdict == Verdict.ASK_IRREVERSIBLE
    assert decision.rule_id == "IRR-001"


@pytest.mark.parametrize("command", _IRR_001_NEGATIVE)
def test_irr_001_near_miss_stays_allow(command: str) -> None:
    assert classify(command).verdict == Verdict.ALLOW


@pytest.mark.parametrize("command", _IRR_002_POSITIVE)
def test_irr_002_positive(command: str) -> None:
    decision = classify(command)
    assert decision.verdict == Verdict.ASK_IRREVERSIBLE
    assert decision.rule_id == "IRR-002"


@pytest.mark.parametrize("command", _IRR_002_NEGATIVE)
def test_irr_002_near_miss_stays_allow(command: str) -> None:
    assert classify(command).verdict == Verdict.ALLOW


@pytest.mark.parametrize("command", _IRR_003_POSITIVE)
def test_irr_003_positive(command: str) -> None:
    decision = classify(command)
    assert decision.verdict == Verdict.ASK_IRREVERSIBLE
    assert decision.rule_id == "IRR-003"


@pytest.mark.parametrize("command", _IRR_003_NEGATIVE)
def test_irr_003_near_miss_stays_allow(command: str) -> None:
    assert classify(command).verdict == Verdict.ALLOW


@pytest.mark.parametrize("command", _IRR_004_POSITIVE)
def test_irr_004_positive(command: str) -> None:
    decision = classify(command)
    assert decision.verdict == Verdict.ASK_IRREVERSIBLE
    assert decision.rule_id == "IRR-004"


@pytest.mark.parametrize("command", _IRR_004_NEGATIVE)
def test_irr_004_near_miss_stays_allow(command: str) -> None:
    assert classify(command).verdict == Verdict.ALLOW


def test_irr_002_force_flag_variant_mirror() -> None:
    decision = classify("git push --mirror origin")
    assert decision.verdict == Verdict.ASK_IRREVERSIBLE
    assert decision.rule_id == "IRR-002"


def test_irr_003_find_delete_variant() -> None:
    decision = classify("find data -delete")
    assert decision.verdict == Verdict.ASK_IRREVERSIBLE
    assert decision.rule_id == "IRR-003"


# --- IRR-001, widened from three directory NAMES to real system/runtime/VCS directories ---------
# The title said "a protected path segment"; the pattern matched a directory literally named
# locked/protected/immutable. These are the shapes a reader of the title expects it to catch.

_IRR_001_SYSTEM_POSITIVE = [
    "cp -r ./out/. /etc/appconfig/",                                    # system config tree
    "cp build/plugin.so /usr/lib/myapp/plugin.so",                      # system library tree
    "tee /usr/lib/python3.11/site-packages/sitecustomize.py < patch.py",  # installed packages
    "cp hook.sh .git/hooks/pre-commit",                                 # repository metadata
    r"copy build\app.exe '\Program Files\App\app.exe'",              # Windows system directory
    r"copy drv.sys \Windows\System32\drivers\drv.sys",               # Windows runtime directory
    "cp -r vendor/. node_modules/left-pad/",                            # dependency tree
    "rsync -a build/ /opt/myapp/",                                      # optional-software tree
    "install -m 755 myapp /usr/local/bin/myapp",                        # install(1) as the verb
]

_IRR_001_SYSTEM_NEGATIVE = [
    "cat /etc/os-release",                     # a read of a system path
    "ls -la /usr/local/bin",                   # a listing
    "grep -rn TODO node_modules/",             # a search
    "du -sh node_modules > sizes.txt",         # the redirect writes OUTSIDE the protected tree
    "python -m pytest tests/",                 # nothing protected at all
]


@pytest.mark.parametrize("command", _IRR_001_SYSTEM_POSITIVE)
def test_irr_001_reaches_real_system_and_runtime_directories(command: str) -> None:
    decision = classify(command)
    assert decision.verdict == Verdict.ASK_IRREVERSIBLE
    assert decision.rule_id == "IRR-001"


@pytest.mark.parametrize("command", _IRR_001_SYSTEM_NEGATIVE)
def test_irr_001_leaves_reads_and_outside_writes_alone(command: str) -> None:
    assert classify(command).verdict == Verdict.ALLOW


# --- IRR-004, from a four-name list to the stated heuristic --------------------------------------
# THE HEURISTIC, stated in the rule title and the module docstring: a destination stem carrying no
# digit cannot name a version or a step, so writing to it overwrites whatever was there.

_IRR_004_NO_DIGIT_POSITIVE = [
    "cp checkpoints/step_4000.pt checkpoints/model.pt",
    "cp checkpoints/adapter.safetensors checkpoints/production.safetensors",
    "mv checkpoints/run-42.bin checkpoints/release.bin",
    "cp train.ckpt checkpoints/converged.ckpt",
]

_IRR_004_VERSIONED_NEGATIVE = [
    "cp checkpoints/step_4000.pt checkpoints/step_5000.pt",
    "cp checkpoints/epoch12.ckpt backup/epoch12.ckpt",
    "mv new.pt checkpoints/model-v14.pt",
    "cp out.bin checkpoints/run-973.bin",
]


@pytest.mark.parametrize("command", _IRR_004_NO_DIGIT_POSITIVE)
def test_irr_004_catches_any_stem_with_no_version_or_step_digits(command: str) -> None:
    decision = classify(command)
    assert decision.verdict == Verdict.ASK_IRREVERSIBLE
    assert decision.rule_id == "IRR-004"


@pytest.mark.parametrize("command", _IRR_004_VERSIONED_NEGATIVE)
def test_irr_004_reads_a_digit_bearing_stem_as_a_new_file(command: str) -> None:
    assert classify(command).verdict == Verdict.ALLOW


def test_irr_004_title_names_the_heuristic_it_implements() -> None:
    """The defect this rule was carrying was a title that outran its pattern. The title now has
    to say what the pattern does, and this test is what stops it drifting back."""
    from policy_deck.policy import rule

    title = rule("IRR-004").title.lower()
    assert "version" in title or "step" in title
    assert "digit" in title
