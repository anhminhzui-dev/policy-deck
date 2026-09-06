"""SPEND-003 and SPEND-004 reach what their titles claim, and nothing wider.

SPEND-003 was three compute namespaces (`aws ec2`, `gcloud compute`, `az vm`) under a title that
said "cloud provider CLI"; storage, managed databases, serverless functions and managed clusters
all bill and all walked through. SPEND-004 was a filename convention (`*_job.py`) plus one
literal (`custom-jobs`) under a title that said "managed training/batch job submitted to a paid
backend"; every real launcher walked through.

The read-verb half of SPEND-003 is the reason this rule can be widened at all: the service token
is only one of the two signals, and a list/describe/show command carries no mutating verb, so the
same widened service list stays quiet on the traffic that fills a real terminal.
"""

from __future__ import annotations

import pytest

from policy_deck import Verdict, classify

_SPEND_003_MUTATING = [
    "aws s3 rb s3://prod-artifacts --force",
    "aws s3 sync build/ s3://prod-artifacts",
    "aws rds delete-db-instance --db-instance-identifier reporting",
    "aws lambda invoke --function-name nightly-batch payload.bin",
    "aws eks create-cluster --name analytics",
    "aws ecs update-service --service api --desired-count 4",
    "gcloud sql instances create reporting-db --tier db-f1-micro",
    "gcloud storage buckets create bucket-name",
    "gcloud compute instances create demo-vm --zone us-central1-a",
    "az storage account create --name reportsstore --sku Standard_LRS",
    "az aks scale --name cluster --node-count 6",
    "az vm create --name demo-vm --resource-group demo-rg",
]

_SPEND_003_READ_VERBS_STAY_ALLOW = [
    "aws s3 ls s3://reports-bucket",
    "aws s3api list-buckets",
    "aws ec2 describe-instances --max-items 5",
    "aws rds describe-db-instances",
    "aws lambda list-functions",
    "aws eks list-clusters",
    "gcloud compute instances list",
    "gcloud sql instances list",
    "gcloud storage buckets list",
    "az storage account list",
    "az vm list --output table",
    "az aks list --output table",
]

_SPEND_004_LAUNCHERS = [
    "modal run train_pipeline.py",
    "modal deploy serving_app.py",
    "sky launch -c trainer cluster.yaml",
    "anyscale job submit -- python train.py",
    "ray job submit --working-dir . -- python train.py",
    "beam deploy app.py",
    "dstack run trainer",
    "aws sagemaker create-training-job --training-job-name nightly",
    "gcloud ai custom-jobs create --config trainer.yaml",
    "az ml job create --file trainer.yaml",
    "azureml job create --file trainer.yaml",
    "together fine-tuning create --model base-7b --training-file corpus.jsonl",
    "python train_job.py --mode submit",
    "python eval_job.py --mode=submit",
]

_SPEND_004_LOCAL_OR_READ_STAYS_ALLOW = [
    "python train_job.py --mode dry-run",
    "python train.py --local",
    "modal token new",
    "modal app list",
    "sky status",
    "ray status",
    "gcloud ai custom-jobs list",
    "az ml job list",
]


@pytest.mark.parametrize("command", _SPEND_003_MUTATING)
def test_cloud_cli_mutating_verb_asks_for_money(command: str) -> None:
    decision = classify(command)
    assert decision.verdict == Verdict.ASK_MONEY
    assert decision.rule_id == "SPEND-003"


@pytest.mark.parametrize("command", _SPEND_003_READ_VERBS_STAY_ALLOW)
def test_cloud_cli_read_verb_stays_allow(command: str) -> None:
    assert classify(command).verdict == Verdict.ALLOW


@pytest.mark.parametrize("command", _SPEND_004_LAUNCHERS)
def test_managed_job_launcher_asks_for_money(command: str) -> None:
    decision = classify(command)
    assert decision.verdict == Verdict.ASK_MONEY
    assert decision.family is not None
    assert decision.family.value == "SPEND"


@pytest.mark.parametrize("command", _SPEND_004_LOCAL_OR_READ_STAYS_ALLOW)
def test_local_run_or_read_verb_on_a_launcher_stays_allow(command: str) -> None:
    assert classify(command).verdict == Verdict.ALLOW


def test_managed_job_namespaces_do_not_collide_with_the_cloud_rule() -> None:
    """`aws sagemaker`, `gcloud ai` and `az ml` belong to SPEND-004; keeping them out of
    SPEND-003's service list is what stops one command from being claimed by both rules."""
    for command in (
        "aws sagemaker create-training-job --training-job-name nightly",
        "gcloud ai custom-jobs create --config trainer.yaml",
        "az ml job create --file trainer.yaml",
    ):
        assert classify(command).rule_id == "SPEND-004", command


def test_an_approval_token_still_clears_the_widened_rules() -> None:
    for command in (
        "aws s3 rb s3://prod-artifacts --force --approve-spend",
        "modal run train_pipeline.py --approve-spend",
    ):
        decision = classify(command)
        assert decision.verdict == Verdict.ALLOW, command
        assert decision.approved_by == "--approve-spend"
