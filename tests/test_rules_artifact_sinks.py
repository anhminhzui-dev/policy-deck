"""DENY-002 reaches every artifact-file extension its title names, through every sink it names.

Before the fix the rule's sink was `.json` and nothing else, while the title and the README both
said "artifact file". A credential redirected into a `.yaml`, copied as a `.env`, moved as a
`.toml` or teed into an `.ini` walked straight through. These rows are the fix, expressed as the
behaviour a reader of the title would expect.

The negatives matter just as much: widening the sink list cannot be allowed to turn ordinary
config-file handling into a refusal, so a sink with no credential field, and a credential field
with no sink, both still stay ALLOW.
"""

from __future__ import annotations

import pytest

from policy_deck import Verdict, classify

_CREDENTIAL_INTO_AN_ARTIFACT_FILE = [
    # redirects, both forms
    "echo 'api_key: REDACTED' > shared/config.yaml",
    "echo 'api_key: REDACTED' >> shared/config.yaml",
    "echo 'client_secret=REDACTED' > env/staging.env",
    "echo 'password=REDACTED' >> deploy/settings.ini",
    "echo 'auth_token=REDACTED' > notes/handoff.md",
    "echo 'access_key=REDACTED' > out/keys.txt",
    "echo 'private_key=REDACTED' > build/app.cfg",
    "echo 'token=REDACTED' > config/app.yml",
    # copy and move
    "cp secrets.env build/out/secrets.env",
    "mv service_token.toml dist/service_token.toml",
    "cp deploy/password.ini backup/password.ini",
    # tee
    "printf 'password=REDACTED' | tee deploy/credentials.ini",
    "printf 'secret=REDACTED' | tee shared/values.yaml",
    # --output, both spellings
    "python emit.py --output handoff/access_key.txt --field access_key",
    "python emit.py --output=handoff/api_key.toml --field api_key",
    # the original .json shape must keep working
    "cp secrets_dump.json shared/worker_input.json",
]

_SINK_WITHOUT_A_CREDENTIAL_FIELD_STAYS_ALLOW = [
    "cp settings.toml backup_settings.toml",
    "mv release_notes.md docs/release_notes.md",
    "echo 'debug: true' > config/app.yaml",
    "printf 'ok' | tee build/status.txt",
    "python emit.py --output reports/summary.md --section overview",
]

_CREDENTIAL_FIELD_WITHOUT_A_SINK_STAYS_ALLOW = [
    "grep -rn api_key src/",
    "cat config.yaml | grep -i token",
    "rg --hidden client_secret .",
    "diff -u secrets.env secrets.env.example",
]


@pytest.mark.parametrize("command", _CREDENTIAL_INTO_AN_ARTIFACT_FILE)
def test_credential_written_into_an_artifact_file_is_denied(command: str) -> None:
    decision = classify(command)
    assert decision.verdict == Verdict.DENY
    assert decision.rule_id == "DENY-002"


@pytest.mark.parametrize("command", _SINK_WITHOUT_A_CREDENTIAL_FIELD_STAYS_ALLOW)
def test_sink_alone_still_stays_allow(command: str) -> None:
    assert classify(command).verdict == Verdict.ALLOW


@pytest.mark.parametrize("command", _CREDENTIAL_FIELD_WITHOUT_A_SINK_STAYS_ALLOW)
def test_field_alone_still_stays_allow(command: str) -> None:
    assert classify(command).verdict == Verdict.ALLOW


def test_the_title_names_every_extension_the_pattern_matches() -> None:
    """The title cannot outrun the pattern, and the pattern cannot outrun the title."""
    from policy_deck.policy import _ARTIFACT_EXTENSIONS, RULES_BY_ID

    title = RULES_BY_ID["DENY-002"].title
    for extension in _ARTIFACT_EXTENSIONS:
        assert extension in title, extension
    named_in_title = [w for w in title.replace("/", " ").split() if w in _ARTIFACT_EXTENSIONS]
    assert len(named_in_title) == len(_ARTIFACT_EXTENSIONS)


def test_an_unlisted_extension_is_not_a_sink() -> None:
    """A log file and a binary are not the artifact files this rule is about; if that ever needs
    to change, the extension list and the title change together."""
    assert classify("echo 'token=REDACTED' > build/run.log").verdict == Verdict.ALLOW
    assert classify("cp api_key.bin vendor/api_key.bin").verdict == Verdict.ALLOW
