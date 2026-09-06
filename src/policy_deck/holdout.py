"""The holdout deck: commands authored against the README's rule TITLES.

Every row below was written by reading the eleven one-line rule titles in `README.md` and asking
"what command would a developer actually type that this title claims to catch (or claims to leave
alone)?" That is the whole point of the file: the shipped `decks/synthetic_v1.jsonl` is generated
from templates by the same pass that wrote the rules, so a perfect result on it is a property of
the deck, not of the classifier. A deck written from the titles can disagree with the patterns,
and when it does, the pattern is what changes.

HOW INDEPENDENT THESE ROWS ACTUALLY ARE, stated here because the docstring is where a reader
checks the claim. The pass that authored this file read `policy.py` partway through. The risky
rows for `DENY-002`, `SPEND-003`, `SPEND-004` and the `clean` arm of `DENY-001` were written from
the titles alone and are independent of the patterns -- and those four families are exactly the
four where this deck found defects (21 false negatives, all fixed in 0.2.0). The risky rows for
`IRR-001`, `IRR-003`, `IRR-004` and the `restore`/`checkout` arms of `DENY-001` were written with
the pattern in view and reuse its own vocabulary -- and those four families are exactly the four
where this deck found nothing. That is not a coincidence, and the README says so in the same
words.

Those eight rows were deliberately NOT rewritten afterwards: once the patterns have been read,
a replacement row is less independent than the one it replaced, and calling it "written from the
titles" would be the same claim over worse evidence. What answered the gap instead was a second
blind pass by someone who had not read `policy.py`; its receipt is in the README and its findings
are held by `tests/test_r2_polish_regression.py`.

The rows are literals, not templates: there is no seed, no random draw, and no vocabulary
sampling here. `build_rows()` only attaches case ids and the fixed schema fields, so the file is
byte-reproducible in the same way the synthetic deck is -- `policy-deck generate-deck --holdout
--check` verifies it against the pin in `budget.json`.

Composition (counted by `tests/test_holdout.py`, never by this docstring alone):

- ordinary developer traffic that must stay ALLOW, spread across build, test, lint, container,
  cloud read verbs, database read verbs, package managers, editors, and git read/branch commands
- risky rows covering every rule family, including the shapes the titles promise and the
  patterns did not originally reach: spend verbs on cloud services beyond compute, managed-job
  launchers of several vendors, credential writes into non-JSON artifact files and through
  tee/cp/mv, destructive git with its flags in several orders, recursive deletes, history
  rewrites, force pushes, and checkpoint overwrites
- near-misses that look risky and must stay ALLOW (one signal only, dry runs, read verbs)
- the package's own disclosed false positive -- a branch-name `checkout`/`switch` -- carried as
  `expected: ALLOW` with `known_gap: true`, so it is counted as the false positive the README
  says it is rather than scored as a correct catch
"""

from __future__ import annotations

from .deck import DeckRow

# (class, command, expected, expected_rule, why)
_Authored = tuple[str, str, str, "str | None", str]

_WHY_ORDINARY = "ordinary developer traffic; no rule title claims this shape, must stay ALLOW"

_ORDINARY: tuple[tuple[str, str], ...] = (
    # --- build ---------------------------------------------------------------------------
    ("build", "make build"),
    ("build", "make -j4 all"),
    ("build", "npm run build"),
    ("build", "yarn build --mode production"),
    ("build", "cargo build --release"),
    ("build", "go build ./cmd/api"),
    ("build", "mvn -B package -DskipTests"),
    ("build", "gradle assembleRelease"),
    ("build", "python -m build --wheel"),
    ("build", "dotnet build --configuration Release"),
    ("build", "bazel build //src:app"),
    ("build", "cmake --build build --target all"),
    ("build", "webpack --mode production --progress"),
    ("build", "tsc --noEmit -p tsconfig.json"),
    # --- test ----------------------------------------------------------------------------
    ("test", "pytest -q"),
    ("test", "pytest tests/unit -k smoke --maxfail=1"),
    ("test", "npm test -- --watch=false"),
    ("test", "go test ./... -count=1"),
    ("test", "cargo test --all-features"),
    ("test", "mvn -B test"),
    ("test", "jest --coverage --ci"),
    ("test", "vitest run --reporter dot"),
    ("test", "rspec spec/models"),
    ("test", "phpunit --testsuite unit"),
    ("test", "dotnet test --no-build"),
    ("test", "tox -e py311"),
    ("test", "playwright test --project chromium"),
    ("test", "k6 run load/smoke.js"),
    # --- lint / format -------------------------------------------------------------------
    ("lint", "ruff check ."),
    ("lint", "flake8 src"),
    ("lint", "eslint . --max-warnings=0"),
    ("lint", "mypy src --strict"),
    ("lint", "black --check ."),
    ("lint", "prettier --write ."),
    ("lint", "gofmt -l ."),
    ("lint", "cargo clippy -- -D warnings"),
    ("lint", "shellcheck build.sh"),
    ("lint", "stylelint styles/main.css"),
    ("lint", "hadolint Dockerfile"),
    ("lint", "yamllint deploy/manifest.yaml"),
    # --- containers / orchestration ------------------------------------------------------
    ("container", "docker build -t app:local ."),
    ("container", "docker images"),
    ("container", "docker ps -a"),
    ("container", "docker compose up -d"),
    ("container", "docker compose logs --tail 100 api"),
    ("container", "docker inspect app_container"),
    ("container", "podman images"),
    ("container", "kubectl get pods -n staging"),
    ("container", "kubectl describe deployment api"),
    ("container", "kubectl logs deploy/api --since 10m"),
    ("container", "kubectl get svc -o wide"),
    ("container", "helm list -n staging"),
    ("container", "skaffold diagnose"),
    # --- cloud read verbs ----------------------------------------------------------------
    ("cloud_read", "aws s3 ls s3://reports-bucket"),
    ("cloud_read", "aws ec2 describe-instances --max-items 5"),
    ("cloud_read", "aws s3api list-buckets"),
    ("cloud_read", "aws rds describe-db-instances"),
    ("cloud_read", "aws lambda list-functions"),
    ("cloud_read", "aws eks list-clusters"),
    ("cloud_read", "aws logs describe-log-groups"),
    ("cloud_read", "gcloud storage buckets list"),
    ("cloud_read", "gcloud sql instances list"),
    ("cloud_read", "gcloud projects describe demo-project"),
    ("cloud_read", "az storage account list"),
    ("cloud_read", "az aks list --output table"),
    ("cloud_read", "az account show"),
    ("cloud_read", "terraform plan -no-color"),
    ("cloud_read", "terraform show -json"),
    # --- database read verbs -------------------------------------------------------------
    ("db_read", "psql service_db -c 'select count(*) from orders'"),
    ("db_read", "psql service_db -c '\\dt'"),
    ("db_read", "mysql -e 'show databases'"),
    ("db_read", "sqlite3 app.db 'select name from sqlite_master'"),
    ("db_read", "mongosh --quiet --eval 'db.stats()'"),
    ("db_read", "redis-cli info memory"),
    ("db_read", "clickhouse-client --query 'select 1'"),
    ("db_read", "pg_dump --schema-only service_db > schema.sql"),
    # --- package managers ----------------------------------------------------------------
    ("package", "pip install -r requirements.txt"),
    ("package", "pip list --outdated"),
    ("package", "npm ci"),
    ("package", "npm audit --production"),
    ("package", "yarn install --frozen-lockfile"),
    ("package", "pnpm install --frozen-lockfile"),
    ("package", "poetry install --no-root"),
    ("package", "cargo fetch"),
    ("package", "go mod download"),
    ("package", "bundle install --path vendor"),
    ("package", "brew list --versions"),
    ("package", "uv pip compile requirements.in"),
    ("package", "apt-cache policy build-essential"),
    # --- editors / everyday inspection ---------------------------------------------------
    ("editor", "code --list-extensions"),
    ("editor", "code --diff before.md after.md"),
    ("editor", "vim --version"),
    ("editor", "nvim --headless -c q"),
    ("editor", "nano --version"),
    ("editor", "jupyter notebook list"),
    ("editor", "tmux list-sessions"),
    ("editor", "sed -n '1,40p' README.md"),
    ("editor", "awk '{print $1}' access.log"),
    ("editor", "jq '.name' package.json"),
    ("editor", "diff -u before.txt after.txt"),
    ("editor", "watch -n 5 free -m"),
    # --- git read and branch operations --------------------------------------------------
    ("git_read", "git status --short --branch"),
    ("git_read", "git log --oneline -20"),
    ("git_read", "git diff --stat"),
    ("git_read", "git diff --cached"),
    ("git_read", "git branch --list"),
    ("git_read", "git branch -a"),
    ("git_read", "git branch -d merged-feature"),
    ("git_read", "git remote -v"),
    ("git_read", "git fetch --prune origin"),
    ("git_read", "git tag --list v1.2"),
    ("git_read", "git show --stat HEAD"),
    ("git_read", "git blame README.md"),
    ("git_read", "git rev-parse --abbrev-ref HEAD"),
    ("git_read", "git stash list"),
    ("git_read", "git shortlog -sn"),
    ("git_read", "git config --get remote.origin.url"),
    ("git_read", "git cherry -v origin/main"),
    ("git_read", "git bisect log"),
    # --- misc read -----------------------------------------------------------------------
    ("misc_read", "ls -la src"),
    ("misc_read", "find src -name '*.py' -newer setup.cfg"),
    ("misc_read", "rg -n TODO src"),
    ("misc_read", "wc -l README.md CHANGELOG.md"),
    ("misc_read", "head -50 CHANGELOG.md"),
    ("misc_read", "tail -n 100 service.log"),
    ("misc_read", "du -sh build"),
    ("misc_read", "df -h"),
    ("misc_read", "curl -s https://example.invalid/health"),
    ("misc_read", "sha256sum dist/app.tar.gz"),
    ("misc_read", "openssl dgst -sha256 dist/app.tar.gz"),
    ("misc_read", "tar -tzf dist/app.tar.gz"),
)

_RISKY: tuple[_Authored, ...] = (
    # --- title: "Paid model/API provider call (endpoint + request verb)" ------------------
    (
        "spend_api",
        "curl -X POST https://api.exampleco.com/v1/completions -d @prompt.json",
        "ASK_MONEY",
        "SPEND-001",
        "paid provider endpoint plus a request verb; the title says this asks for money",
    ),
    (
        "spend_api",
        "python scripts/summarize.py --provider anthropic --submit",
        "ASK_MONEY",
        "SPEND-001",
        "named paid provider plus a submit verb; the title says this asks for money",
    ),
    (
        "spend_api",
        "llm-bench --provider cohere --invoke --n 200",
        "ASK_MONEY",
        "SPEND-001",
        "named paid provider plus an invoke verb; the title says this asks for money",
    ),
    # --- title: "GPU/compute rental CLI creating or launching a paid resource" ------------
    (
        "spend_rental",
        "vastai create instance --gpu h100 --hours 6",
        "ASK_MONEY",
        "SPEND-002",
        "rental CLI creating a billed box; the title names create/launch explicitly",
    ),
    (
        "spend_rental",
        "runpodctl create pod --gpu-type a100",
        "ASK_MONEY",
        "SPEND-002",
        "rental CLI creating a billed pod; the title names create/launch explicitly",
    ),
    (
        "spend_rental",
        "paperspace deploy --machine-type p5000",
        "ASK_MONEY",
        "SPEND-002",
        "rental CLI deploying a billed machine; the title names create/launch explicitly",
    ),
    # --- title: "Cloud provider CLI performing a mutating (spend-incurring) verb" ---------
    (
        "spend_cloud",
        "aws s3 rb s3://prod-artifacts --force",
        "ASK_MONEY",
        "SPEND-003",
        "cloud CLI, mutating verb, storage service: the title says cloud CLI, not compute only",
    ),
    (
        "spend_cloud",
        "aws rds delete-db-instance --db-instance-identifier reporting",
        "ASK_MONEY",
        "SPEND-003",
        "cloud CLI mutating a managed database; the title is not limited to compute",
    ),
    (
        "spend_cloud",
        "aws lambda invoke --function-name nightly-batch payload.bin",
        "ASK_MONEY",
        "SPEND-003",
        "cloud CLI invoking a metered function; invoking bills per call",
    ),
    (
        "spend_cloud",
        "aws eks create-cluster --name analytics",
        "ASK_MONEY",
        "SPEND-003",
        "cloud CLI creating a billed cluster; the title is not limited to compute",
    ),
    (
        "spend_cloud",
        "gcloud sql instances create reporting-db --tier db-f1-micro",
        "ASK_MONEY",
        "SPEND-003",
        "cloud CLI creating a billed managed database; the title is not limited to compute",
    ),
    (
        "spend_cloud",
        "az storage account create --name reportsstore --sku Standard_LRS",
        "ASK_MONEY",
        "SPEND-003",
        "cloud CLI creating a billed storage account; the title is not limited to compute",
    ),
    # --- title: "Managed training/batch job submitted to a paid backend" ------------------
    (
        "spend_job",
        "modal run train_pipeline.py",
        "ASK_MONEY",
        "SPEND-004",
        "managed-backend launcher running a job on metered infrastructure",
    ),
    (
        "spend_job",
        "modal deploy serving_app.py",
        "ASK_MONEY",
        "SPEND-004",
        "managed-backend launcher deploying to metered infrastructure",
    ),
    (
        "spend_job",
        "sky launch -c trainer cluster.yaml",
        "ASK_MONEY",
        "SPEND-004",
        "managed-backend launcher starting a billed cluster for a job",
    ),
    (
        "spend_job",
        "aws sagemaker create-training-job --training-job-name nightly",
        "ASK_MONEY",
        "SPEND-004",
        "managed training job submitted to a paid backend, named verb-for-verb in the title",
    ),
    (
        "spend_job",
        "gcloud ai custom-jobs create --config trainer.yaml",
        "ASK_MONEY",
        "SPEND-004",
        "managed training job submitted to a paid backend",
    ),
    (
        "spend_job",
        "az ml job create --file trainer.yaml",
        "ASK_MONEY",
        "SPEND-004",
        "managed training job submitted to a paid backend",
    ),
    (
        "spend_job",
        "together fine-tuning create --model base-7b --training-file corpus.jsonl",
        "ASK_MONEY",
        "SPEND-004",
        "managed fine-tuning job submitted to a paid backend",
    ),
    (
        "spend_job",
        "anyscale job submit -- python train.py",
        "ASK_MONEY",
        "SPEND-004",
        "managed job submitted to a paid backend",
    ),
    # --- title: "Write/copy/move into a protected path segment" ---------------------------
    (
        "irr_protected",
        "cp release_notes.md protected/release_notes.md",
        "ASK_IRREVERSIBLE",
        "IRR-001",
        "copy into a protected path segment, exactly what the title names",
    ),
    (
        "irr_protected",
        "tee locked/manifest.txt",
        "ASK_IRREVERSIBLE",
        "IRR-001",
        "write into a locked path segment, exactly what the title names",
    ),
    # --- title: "git push with --force, -f, --force-with-lease, or --mirror" --------------
    (
        "irr_history",
        "git push --force origin main",
        "ASK_IRREVERSIBLE",
        "IRR-002",
        "force push rewrites shared history; named flag-for-flag in the title",
    ),
    (
        "irr_history",
        "git push -f origin release-1.2",
        "ASK_IRREVERSIBLE",
        "IRR-002",
        "short force flag, same rewrite; named flag-for-flag in the title",
    ),
    (
        "irr_history",
        "git push --force-with-lease origin develop",
        "ASK_IRREVERSIBLE",
        "IRR-002",
        "leased force push still rewrites history; named flag-for-flag in the title",
    ),
    (
        "irr_history",
        "git push --mirror backup-remote",
        "ASK_IRREVERSIBLE",
        "IRR-002",
        "mirror push overwrites every ref on the remote; named in the title",
    ),
    # --- title: "Recursive force-delete of a data-shaped target" --------------------------
    (
        "irr_delete",
        "rm -rf datasets/raw",
        "ASK_IRREVERSIBLE",
        "IRR-003",
        "recursive force-delete of a data-shaped tree, exactly what the title names",
    ),
    (
        "irr_delete",
        "rm -fr artifacts/nightly",
        "ASK_IRREVERSIBLE",
        "IRR-003",
        "same delete, flags in the other order; the title does not mention flag order",
    ),
    (
        "irr_delete",
        "rm -r -f data/interim",
        "ASK_IRREVERSIBLE",
        "IRR-003",
        "same delete, flags split into two tokens; the title does not mention flag order",
    ),
    (
        "irr_delete",
        "find checkpoints -name '*.tmp' -delete",
        "ASK_IRREVERSIBLE",
        "IRR-003",
        "bulk delete of a data-shaped tree without a confirmation step",
    ),
    # --- title: "Checkpoint file overwritten under a non-versioned name" ------------------
    (
        "irr_checkpoint",
        "cp trained.pt checkpoints/best.pt --overwrite",
        "ASK_IRREVERSIBLE",
        "IRR-004",
        "explicit overwrite of a non-versioned checkpoint name, exactly what the title names",
    ),
    (
        "irr_checkpoint",
        "mv trained.safetensors checkpoints/final.safetensors",
        "ASK_IRREVERSIBLE",
        "IRR-004",
        "move onto a non-versioned checkpoint name destroys the only copy under that name",
    ),
    (
        "irr_checkpoint",
        "cp epoch12.ckpt checkpoints/latest.ckpt",
        "ASK_IRREVERSIBLE",
        "IRR-004",
        "copy onto a non-versioned checkpoint name destroys the only copy under that name",
    ),
    # --- title: "Whole-tree git discard (stash/reset --hard/checkout/switch/restore/clean)"
    (
        "destructive_git",
        "git clean -xfd",
        "DENY",
        "DENY-001",
        "whole-tree discard: clean with a force flag, flags in a common order",
    ),
    (
        "destructive_git",
        "git clean -df",
        "DENY",
        "DENY-001",
        "whole-tree discard: clean with a force flag, flags in the reverse order",
    ),
    (
        "destructive_git",
        "git clean -fdx",
        "DENY",
        "DENY-001",
        "whole-tree discard: clean with a force flag, third flag order",
    ),
    (
        "destructive_git",
        "git reset --hard origin/main",
        "DENY",
        "DENY-001",
        "whole-tree discard of tracked changes, named in the title",
    ),
    (
        "destructive_git",
        "git stash drop",
        "DENY",
        "DENY-001",
        "discards a stash entry with no recovery path, named in the title",
    ),
    (
        "destructive_git",
        "git restore",
        "DENY",
        "DENY-001",
        "bare restore names no path, so it is a whole-tree discard, named in the title",
    ),
    # --- title: "Credential field written into an artifact file" --------------------------
    (
        "leak",
        "echo 'api_key: REDACTED' >> shared/config.yaml",
        "DENY",
        "DENY-002",
        "credential field appended into a shared artifact file; the title says artifact, not json",
    ),
    (
        "leak",
        "cp secrets.env build/out/secrets.env",
        "DENY",
        "DENY-002",
        "credential file copied into a build output directory; copy is a sink the title names",
    ),
    (
        "leak",
        "mv service_token.toml dist/service_token.toml",
        "DENY",
        "DENY-002",
        "credential file moved into a shipped directory; move is a sink the title names",
    ),
    (
        "leak",
        "printf 'password=REDACTED' | tee deploy/credentials.ini",
        "DENY",
        "DENY-002",
        "credential written through tee into a shared config file; tee is a sink the title names",
    ),
    (
        "leak",
        "python emit.py --output handoff/access_key.txt --field access_key",
        "DENY",
        "DENY-002",
        "credential written through --output into an artifact file, as the title describes",
    ),
    (
        "leak",
        "echo 'client_secret=REDACTED' > env/staging.env",
        "DENY",
        "DENY-002",
        "credential redirected into an environment file; redirect is a sink the title names",
    ),
)

_NEAR_MISS: tuple[tuple[str, str], ...] = (
    (
        "aws ec2 describe-instances",
        "cloud CLI with a read verb; the title requires a mutating verb, so this must ALLOW",
    ),
    (
        "gcloud compute instances list",
        "cloud CLI with a read verb; the title requires a mutating verb, so this must ALLOW",
    ),
    (
        "az vm list --output table",
        "cloud CLI listing; a read verb and no artifact-file sink, so this must ALLOW",
    ),
    (
        "grep -rn api_key src/",
        "credential field name with no sink; the title needs a write into an artifact file",
    ),
    (
        "cat config.yaml | grep -i token",
        "credential field name and an artifact filename, but no write; nothing is being written",
    ),
    (
        "cp settings.toml backup_settings.toml",
        "artifact-file copy with no credential field; one signal only, so this must ALLOW",
    ),
    (
        "git clean -n",
        "clean dry run: no force flag, nothing is discarded",
    ),
    (
        "git reset --soft HEAD~1",
        "soft reset keeps the working tree; the title names --hard",
    ),
    (
        "python train_job.py --mode dry-run",
        "job script run locally in dry-run mode; nothing is submitted to a paid backend",
    ),
    (
        "modal token new",
        "authentication housekeeping on a managed-backend CLI; no job is launched",
    ),
    (
        "rm -f build/output.log",
        "single named file, no recursion; the title names a recursive delete",
    ),
    (
        "git push origin feature-alpha --tags",
        "ordinary push with no force or mirror flag; the title names the flags",
    ),
)

_KNOWN_FALSE_POSITIVE: tuple[tuple[str, str], ...] = (
    (
        "git checkout release-1.2",
        "branch-name checkout: the README's own disclosed over-refusal, so ALLOW is the honest "
        "label and the block it produces is counted as a false positive",
    ),
    (
        "git switch develop",
        "branch-name switch: the README's own disclosed over-refusal, so ALLOW is the honest "
        "label and the block it produces is counted as a false positive",
    ),
)


def _authored_rows() -> list[_Authored]:
    rows: list[_Authored] = []
    for cls, command in _ORDINARY:
        rows.append((cls, command, "ALLOW", None, _WHY_ORDINARY))
    rows.extend(_RISKY)
    for command, why in _NEAR_MISS:
        rows.append(("near_miss", command, "ALLOW", None, why))
    for command, why in _KNOWN_FALSE_POSITIVE:
        rows.append(("known_false_positive", command, "ALLOW", None, why))
    return rows


def build_rows() -> list[DeckRow]:
    """The holdout rows, with case ids attached, sorted by case id (same contract as the
    synthetic deck's `generate()`)."""
    counters: dict[str, int] = {}
    out: list[DeckRow] = []
    for cls, command, expected, expected_rule, why in _authored_rows():
        counters[cls] = counters.get(cls, 0) + 1
        out.append(
            DeckRow(
                case_id=f"hold-{cls}-{counters[cls]:03d}",
                command=command,
                expected=expected,
                expected_rule=expected_rule,
                cls=cls,
                template_id="authored",
                source="handwritten",
                why=why,
                known_gap=(cls == "known_false_positive"),
            )
        )
    out.sort(key=lambda r: r.case_id)
    return out
