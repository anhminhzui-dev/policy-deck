"""SPEND-001..004: three positives and one near-miss negative per rule."""

from __future__ import annotations

import pytest

from policy_deck import Verdict, classify

_SPEND_001_POSITIVE = [
    "python run.py --provider openai --mode invoke",
    "curl -X POST https://api.exampleprovider.com/v1/responses -d @payload.json",
    "python client.py --provider anthropic --submit",
]
_SPEND_001_NEGATIVE = [
    "cat notes/openai-pricing.md",
    "rg openai src/",
]

_SPEND_002_POSITIVE = [
    "vastai create instance --gpu a100",
    "runpodctl rent --gpu h100",
    "paperspace launch --preset training",
]
_SPEND_002_NEGATIVE = [
    "vastai list",
    "runpodctl --help",
]

_SPEND_003_POSITIVE = [
    "aws ec2 run-instances --image-id ami-0123456789abcdef0 --count 2",
    "gcloud compute instances create demo-vm --zone us-central1-a",
    "az vm create --name demo-vm --resource-group demo-rg",
]
_SPEND_003_NEGATIVE = [
    "aws s3 ls",
    "gcloud config list",
    "kubectl get pods",
]

_SPEND_004_POSITIVE = [
    "python train_job.py --mode submit",
    "python eval_job.py --mode=submit",
    "gcloud ai custom-jobs create --config job.yaml",
]
_SPEND_004_NEGATIVE = [
    "python train_job.py --mode dry-run",
    "python train.py --local",
]


@pytest.mark.parametrize("command", _SPEND_001_POSITIVE)
def test_spend_001_positive(command: str) -> None:
    decision = classify(command)
    assert decision.verdict == Verdict.ASK_MONEY
    assert decision.rule_id == "SPEND-001"


@pytest.mark.parametrize("command", _SPEND_001_NEGATIVE)
def test_spend_001_near_miss_stays_allow(command: str) -> None:
    decision = classify(command)
    assert decision.verdict == Verdict.ALLOW


@pytest.mark.parametrize("command", _SPEND_002_POSITIVE)
def test_spend_002_positive(command: str) -> None:
    decision = classify(command)
    assert decision.verdict == Verdict.ASK_MONEY
    assert decision.rule_id == "SPEND-002"


@pytest.mark.parametrize("command", _SPEND_002_NEGATIVE)
def test_spend_002_near_miss_stays_allow(command: str) -> None:
    decision = classify(command)
    assert decision.verdict == Verdict.ALLOW


@pytest.mark.parametrize("command", _SPEND_003_POSITIVE)
def test_spend_003_positive(command: str) -> None:
    decision = classify(command)
    assert decision.verdict == Verdict.ASK_MONEY
    assert decision.rule_id == "SPEND-003"


@pytest.mark.parametrize("command", _SPEND_003_NEGATIVE)
def test_spend_003_near_miss_stays_allow(command: str) -> None:
    decision = classify(command)
    assert decision.verdict == Verdict.ALLOW


@pytest.mark.parametrize("command", _SPEND_004_POSITIVE)
def test_spend_004_positive(command: str) -> None:
    decision = classify(command)
    assert decision.verdict == Verdict.ASK_MONEY
    assert decision.rule_id == "SPEND-004"


@pytest.mark.parametrize("command", _SPEND_004_NEGATIVE)
def test_spend_004_near_miss_stays_allow(command: str) -> None:
    decision = classify(command)
    assert decision.verdict == Verdict.ALLOW
