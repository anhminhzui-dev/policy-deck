"""The policy table: eleven rules, four verdicts, no prose.

A guardrail is a classifier, and a classifier should be a table you can read start to finish,
not a pile of regular expressions nobody has ever counted. Every rule below names the one risk
it exists to catch, in one sentence, next to the pattern that catches it.

Two of the four verdicts route to a human because a machine cannot make that call alone:
spending money (``ASK_MONEY``) and doing something that cannot be undone (``ASK_IRREVERSIBLE``).
The other two are absolute: ``ALLOW`` (nothing here needs a human) and ``DENY`` (no approval
token clears this, ever -- either the action is destructive with no scope check available to
make it safe, or a credential is already written into a shared file, and asking permission after
the fact is pointless).

Design note on rule 8 (``IRR-004``, checkpoint overwrite). The rule blocks when a
checkpoint-shaped path is written **and** either ``--overwrite`` is present or the destination
file's stem carries **no digit at all**. That last clause is the whole heuristic, stated plainly:
*a name with no digit in it cannot name a version or a step*, so writing to it is an overwrite of
whatever was there. ``model.pt``, ``latest.ckpt`` and ``production.safetensors`` are all caught;
``step_4000.pt``, ``run-973.bin``, ``model-v14.pt`` and ``epoch12.ckpt`` are read as new files and
allowed.

The heuristic is deliberately crude in one direction and honest about it: a genuinely versioned
name that uses no digits (``checkpoints/model-alpha.pt``) is refused, and that is a false positive
this rule accepts rather than guess at every versioning convention in use. The earlier version of
this rule matched a fixed four-name list (``final``/``best``/``latest``/``last``) under a title
that said "a non-versioned name" -- so an ordinary ``checkpoints/model.pt`` walked straight
through (r2 blind-holdout miss ``r2-risk-10``). A title that outruns its pattern is the failure
this package exists to criticise elsewhere; the title now names the heuristic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Verdict(str, Enum):
    ALLOW = "ALLOW"
    ASK_MONEY = "ASK_MONEY"
    ASK_IRREVERSIBLE = "ASK_IRREVERSIBLE"
    DENY = "DENY"


class Family(str, Enum):
    SPEND = "SPEND"
    IRREVERSIBLE = "IRREVERSIBLE"
    DESTRUCTIVE = "DESTRUCTIVE"
    LEAK = "LEAK"
    INPUT = "INPUT"


SEVERITY: dict[Verdict, int] = {
    Verdict.ALLOW: 0,
    Verdict.ASK_MONEY: 1,
    Verdict.ASK_IRREVERSIBLE: 2,
    Verdict.DENY: 3,
}

FAMILY_VERDICT: dict[Family, Verdict] = {
    Family.SPEND: Verdict.ASK_MONEY,
    Family.IRREVERSIBLE: Verdict.ASK_IRREVERSIBLE,
    Family.DESTRUCTIVE: Verdict.DENY,
    Family.LEAK: Verdict.DENY,
    Family.INPUT: Verdict.DENY,
}

APPROVAL_TOKENS: dict[Family, str] = {
    Family.SPEND: "--approve-spend",
    Family.IRREVERSIBLE: "--approve-irreversible",
}

MAX_COMMAND_CHARS: int = 8192


@dataclass(frozen=True)
class Rule:
    id: str
    family: Family
    verdict: Verdict
    title: str                       # one line, <= 90 chars, README table cell
    pattern: re.Pattern[str]         # primary signal, matched against the normalized command
    guard: re.Pattern[str] | None    # second signal that must ALSO match, or None
    safe_correction: str             # what to do instead, one sentence
    approval_token: str | None       # None for every DENY-verdict rule


# ---------------------------------------------------------------------------------------------
# Rule 1 -- SPEND-001: a paid provider is called with a request-shaped verb.
# Risk: a single command silently bills a paid API. Naming a provider is not enough on its own
# (reading a pricing page, grepping source for a provider name) -- it must be paired with a verb
# that actually places a call.
# ---------------------------------------------------------------------------------------------
_SPEND_001_PATTERN = re.compile(
    r"\b(?:openai|anthropic|cohere|mistral|gemini|vertexai|bedrock|azure-openai|together|"
    r"replicate|perplexity|elevenlabs)\b|https?://api\."
)
_SPEND_001_GUARD = re.compile(r"\b(?:api|invoke|submit|completions|responses)\b")

# ---------------------------------------------------------------------------------------------
# Rule 2 -- SPEND-002: a GPU/compute rental CLI creates or launches a billed resource.
# Risk: renting a GPU box bills by the hour from the moment it launches. A read-only verb
# (list/--help) on the same CLI is harmless and must stay ALLOW.
# ---------------------------------------------------------------------------------------------
_SPEND_002_PATTERN = re.compile(r"\b(?:vastai|runpodctl|paperspace|coreweave-cli|tensordock)\b")
_SPEND_002_GUARD = re.compile(r"\b(?:create|rent|launch|deploy)\b")

# ---------------------------------------------------------------------------------------------
# Rule 3 -- SPEND-003: a cloud provider CLI performs a mutating (spend-incurring) verb on a
# billed service.
# Risk: the same cloud CLI that lists resources for free also creates them for money. Gate the
# verb, not the tool. The service list is deliberately not compute-only -- storage, managed
# databases, serverless functions and managed clusters all bill, and a rule titled "cloud
# provider CLI" has to reach them (holdout misses hold-spend_cloud-001..006). Managed *job*
# submission stays with SPEND-004: the namespaces that rule owns (`aws sagemaker`, `gcloud ai`,
# `az ml`) are absent from the list below, so the two rules cannot collide.
# The guard is a whole-command verb signal -- the same disclosed trade-off DENY-002's field guard
# makes: a mutating verb anywhere in the line pairs with the service token to fire the rule. A
# read verb (list/get/describe/show) carries no member of the guard list, so it stays ALLOW.
# ---------------------------------------------------------------------------------------------
_SPEND_003_PATTERN = re.compile(
    r"\baws\s+(?:ec2|s3|s3api|rds|lambda|eks|ecs|emr|redshift|elasticache)\b"
    r"|\bgcloud\s+(?:compute|sql|container|storage|dataproc)\b"
    r"|\baz\s+(?:vm|storage|aks|sql|disk)\b"
)
_SPEND_003_GUARD = re.compile(
    r"\b(?:create|apply|scale|delete|terminate|run-instances|start-instances|rb|mb|rm|sync|"
    r"invoke|update|deploy|launch|modify|reboot|put-object|delete-object)\b"
)

# ---------------------------------------------------------------------------------------------
# Rule 4 -- SPEND-004: a managed job is handed to a metered backend by a launcher verb.
# Risk: "submit", "create", "run", "deploy" and "launch" hand a job to a scheduler that bills for
# it; a local or dry-run invocation of the very same script must stay ALLOW.
# The original pattern was a *filename convention* (`*_job.py`) plus one literal (`custom-jobs`),
# which every real launcher walked straight through (holdout misses hold-spend_job-001..008). The
# pattern below names the launcher CLIs and binds each one to its own submitting verb, so the
# rule catches what its title claims and nothing wider: `modal token new` and
# `python train_job.py --mode dry-run` carry no launcher verb and stay ALLOW.
# The verb is inside the pattern (each vendor names its own), so this rule needs no separate
# guard; the `*_job.py` arm keeps its second signal as a lookahead in the same clause.
# ---------------------------------------------------------------------------------------------
_SPEND_004_PATTERN = re.compile(
    r"\bmodal\s+(?:run|deploy|launch)\b"
    r"|\bsky\s+(?:launch|exec|jobs\s+launch)\b"
    r"|\banyscale\s+job\s+submit\b"
    r"|\bray\s+job\s+submit\b"
    r"|\bbeam\s+(?:run|deploy)\b"
    r"|\bdstack\s+(?:run|apply)\b"
    r"|\brunpodctl\s+(?:create|start)\b"
    r"|\bvastai\s+(?:create|launch)\b"
    r"|\bsagemaker\s+create-training-job\b"
    r"|\baws\s+sagemaker\s+create-\S+"
    r"|\bcustom-jobs\s+create\b"
    r"|\baz(?:ure)?ml\s+job\s+create\b"
    r"|\baz\s+ml\s+job\s+create\b"
    r"|\btogether\s+fine-tun(?:ing|es?)\s+create\b"
    r"|\b\w*_job\.py\b(?=[^|;&]*(?:--mode[=\s]+submit\b|--submit\b|\bsubmit\b|\bcreate\b))"
)
_SPEND_004_GUARD = None

# ---------------------------------------------------------------------------------------------
# Rule 5 -- IRR-001: a write/copy/move verb targets a system, runtime, or version-control
# directory, or a directory named to say it must not be written to.
# Risk: writing into an operating-system tree, an interpreter's installed-package tree, or a
# repository's own metadata directory changes something outside the project, and reverting the
# project does not undo it. A read of the same path is harmless.
#
# The pattern was `\b(?:locked|protected|immutable)/` -- three literal directory *names* -- under
# a title that said "a protected path segment", which any reader takes to mean a real system
# path. A copy into a system config directory, a tee into an interpreter's package directory and
# a write into a repository's own version-control directory were all ALLOW (r2 blind-holdout miss
# `r2-risk-07`). The four arms below are that title spelled out: an absolute Unix system tree, a
# runtime/dependency/version-control directory segment, a Windows system directory, and the three
# original by-name markers. Every path arm requires a token boundary in front of it, so a path
# that is only a substring of a longer word does not fire.
# ---------------------------------------------------------------------------------------------
_IRR_001_PATTERN = re.compile(
    # a real Unix system/config/runtime tree, named absolutely
    r"(?:^|[\s=\"'(])/(?:etc|usr|bin|sbin|lib|lib64|boot|opt|var|sys|proc|dev)/"
    # an interpreter's installed-package tree, a dependency tree, or repository metadata
    r"|(?:^|[\s=\"'(/])(?:site-packages|dist-packages|node_modules|\.git|\.svn|\.hg)/"
    # a Windows system directory. Keyed on the directory NAME, not on a drive letter: the name is
    # the distinctive token, and the leading-separator class means a drive-qualified path, a
    # drive-relative path and a UNC path all match the same arm. Keying it this way also keeps
    # this repository free of drive-letter literals, which `scripts/forbidden_scan.py` refuses
    # tree-wide and grants no exemption from -- not to a comment, and not to a test fixture.
    r"|(?:^|[\s=\"'(\\/])(?:windows[\\/]system32|program files(?: \(x86\))?[\\/]|programdata[\\/])"
    # a directory whose own name says it must not be written to silently
    r"|\b(?:locked|protected|immutable)/"
)
# The write verbs. `install`/`rsync` join the POSIX three because both routinely write into a
# system tree; `copy`/`xcopy`/`robocopy`/`move` are the Windows spellings of the same act. Every
# one of them still needs the path arm above to match first, so a bare `move` is not a signal.
_IRR_001_GUARD = re.compile(
    r"\b(?:cp|mv|tee|install|rsync|copy|xcopy|robocopy|move)\b|>"
)

# ---------------------------------------------------------------------------------------------
# Rule 6 -- IRR-002: a force-push rewrites shared history.
# Risk: --force, -f, --force-with-lease, and --mirror all discard commits a collaborator may
# already depend on. An ordinary push, or a --dry-run, is not this.
# ---------------------------------------------------------------------------------------------
_IRR_002_PATTERN = re.compile(
    r"\bgit push\b.*(?:--force(?:-with-lease)?\b|-f\b|--mirror\b)"
)

# ---------------------------------------------------------------------------------------------
# Rule 7 -- IRR-003: a recursive force-delete targets a data-shaped directory.
# Risk: -rf/-fr/-r -f (in either order) plus `find -delete` remove a whole tree with no
# confirmation and no trash. A single named file, or a non-data directory (build/, node_modules),
# is not this.
# ---------------------------------------------------------------------------------------------
_IRR_003_PATTERN = re.compile(
    r"\brm\s+(?:-rf\b|-fr\b|-r\s+-f\b|-f\s+-r\b)|\bfind\b.*-delete\b"
)
_IRR_003_GUARD = re.compile(r"\b(?:data|datasets?|checkpoints?|artifacts?)\b")

# ---------------------------------------------------------------------------------------------
# Rule 8 -- IRR-004: a checkpoint-shaped file is written under a name carrying no version or
# step digits, or with --overwrite.
# Risk: writing a checkpoint to a name that cannot identify which run or step produced it
# destroys the only copy under that name, silently. Writing a new, distinctly-versioned file is
# not this -- see the module docstring for the heuristic and why it replaced a four-name list.
# ---------------------------------------------------------------------------------------------
_IRR_004_PATTERN = re.compile(
    r"\b(?:cp|mv)\b.*\bcheckpoints?/[\w.\-]+\.(?:bin|pt|pth|ckpt|safetensors)\b"
)
# The stem character class carries no digit on purpose: THE HEURISTIC IS "a name with no digit in
# it cannot name a version or a step". `model.pt`, `latest.ckpt`, `production.safetensors` all
# fire; `step_4000.pt`, `run-973.bin`, `model-v14.pt`, `epoch12.ckpt` do not.
_IRR_004_GUARD = re.compile(
    r"--overwrite\b|/[a-z_.\-]+\.(?:bin|pt|pth|ckpt|safetensors)\b"
)

# ---------------------------------------------------------------------------------------------
# Rule 9 -- DENY-001: a whole-tree git discard, with no scope engine to make it safer.
# Risk: git stash/reset --hard/checkout/switch/restore/clean can each erase uncommitted or
# committed work across the whole tree. Without a way to check "is this branch name actually a
# safe pathspec", this rule refuses `git checkout <anything>` and `git switch <anything>` except
# the explicitly scoped `checkout -- <path>` form -- an intentional, disclosed over-refusal.
# A risky phrase quoted inside a commit message is data, not a command, and must not trigger this
# rule; the classifier masks quoted spans before this one pattern runs (see classifier.py).
#
# Two arms below exist because the earlier version of this rule refused a harmless branch switch
# while permitting a whole-tree discard -- and pointed the caller at the permitted shape in its
# own safe correction:
#   * `restore` was matched bare only (`(?!\ \S)`), so `restore .`, `restore --worktree .` and
#     `restore --source=HEAD .` -- every one of them a whole-tree discard -- were ALLOW
#     (r2 blind-holdout miss `r2-risk-12`).
#   * the scoped-checkout exemption `(?!\ --\ )` exempted `checkout -- <anything>` INCLUDING
#     `checkout -- .`, which discards the entire working tree.
# The dot pathspec is therefore its own arm and applies to both verbs: `.` is not a scope, it is
# the whole tree wearing a scope's clothes.
# ---------------------------------------------------------------------------------------------
_DENY_001_PATTERN = re.compile(
    r"""
    \bgit\ stash\b(?!\ (?:list|show))          # any stash op except list/show discards work
    |
    \bgit\ reset\ --hard\b                     # --hard discards tracked changes
    |
    # clean with a force flag in the same clause, in ANY flag order: --force, or a short-flag
    # cluster containing f (-f, -fd, -df, -xfd, -fdx). The cluster has to start its own token
    # (the lookbehind), so a pathspec such as "some-file" is not read as a flag.
    \bgit\ clean\b(?=[^|;&]*(?:--force\b|(?<![\w-])-[a-z]*f[a-z]*\b))
    |
    \bgit\ (?:checkout|switch)\b(?!\ --\ )     # whole-tree op unless explicitly scoped with --
    |
    # the dot pathspec IS the whole tree: `checkout -- .` and `restore .` are not scoped ops.
    # The lookbehind keeps a dot inside a filename (`src/app.py`) from matching; the lookahead
    # requires the dot to end its own token.
    \bgit\ (?:checkout|restore)\b[^|;&]*(?<![\w.\-/])\.(?=\s|$)
    |
    \bgit\ restore\b(?!\ \S)                   # bare restore: no target path named
    |
    # a restore that names the working tree, or replays from a source, is whole-tree by nature
    \bgit\ restore\b[^|;&]*(?:--worktree\b|--source\b|--source=)
    """,
    re.VERBOSE,
)

# ---------------------------------------------------------------------------------------------
# Rule 10 -- DENY-002: a credential field is written into a shared artifact file.
# Risk: two signals, both required. A sink alone (writing a plain config file) is routine. A
# credential field name alone (grepping for one) is inspection, not a leak. Both together mean a
# secret value is about to land on disk where something else can read it -- already leaked, so
# this is DENY, never an ask. The field guard matches as a substring (not a whole word) on
# purpose: it catches compound and pluralized names such as "secrets_dump.json" at the cost of
# also matching inside an unrelated word such as "tokenizer" -- a disclosed, accepted trade-off.
# The sink was originally `.json` only, while the title and the README both said "artifact file":
# a redirect into a .yaml or a copy of a .env file walked through (holdout misses
# hold-leak-001..006). The extension list below is now the title, spelled out, and both the rule
# title and the README name the same nine extensions.
# ---------------------------------------------------------------------------------------------
_ARTIFACT_EXTENSIONS: tuple[str, ...] = (
    "json", "yaml", "yml", "env", "toml", "ini", "txt", "md", "cfg",
)
_ARTIFACT_SUFFIX = r"\.(?:" + "|".join(_ARTIFACT_EXTENSIONS) + r")\b"
_DENY_002_PATTERN = re.compile(
    r"\b(?:set-content|cp|mv|tee)\b[^|;&]*" + _ARTIFACT_SUFFIX
    + r"|--output[=\s]+\S*" + _ARTIFACT_SUFFIX
    + r"|>>?\s*\S*" + _ARTIFACT_SUFFIX
)
_DENY_002_GUARD = re.compile(
    r"api_key|password|passwd|secret|token|private_key|access_key|client_secret|"
    r"auth_token|credential"
)

# ---------------------------------------------------------------------------------------------
# Rule 11 -- MALFORMED-001: the input itself cannot be classified.
# Risk: an empty, blank, non-string, NUL-carrying, or over-length command is not safe to reason
# about, so it fails closed. This pattern intentionally never matches anything -- malformed input
# is decided by `is_malformed()` before any pattern runs (see classifier.py); this rule keeps a
# table entry only so it has a title, a safe correction, and a place in the trace list `explain()`
# returns.
# ---------------------------------------------------------------------------------------------
_MALFORMED_001_PATTERN = re.compile(r"(?!)")


RULES: tuple[Rule, ...] = (
    Rule(
        id="SPEND-001",
        family=Family.SPEND,
        verdict=Verdict.ASK_MONEY,
        title="Paid model/API provider call (endpoint + request verb)",
        pattern=_SPEND_001_PATTERN,
        guard=_SPEND_001_GUARD,
        safe_correction=(
            "Confirm the spend, then add --approve-spend, or run a local/free path instead."
        ),
        approval_token=APPROVAL_TOKENS[Family.SPEND],
    ),
    Rule(
        id="SPEND-002",
        family=Family.SPEND,
        verdict=Verdict.ASK_MONEY,
        title="GPU/compute rental CLI creating or launching a paid resource",
        pattern=_SPEND_002_PATTERN,
        guard=_SPEND_002_GUARD,
        safe_correction=(
            "Confirm the rental cost, then add --approve-spend, or list/--help first."
        ),
        approval_token=APPROVAL_TOKENS[Family.SPEND],
    ),
    Rule(
        id="SPEND-003",
        family=Family.SPEND,
        verdict=Verdict.ASK_MONEY,
        title="Cloud provider CLI performing a mutating (spend-incurring) verb",
        pattern=_SPEND_003_PATTERN,
        guard=_SPEND_003_GUARD,
        safe_correction=(
            "Confirm the cloud spend, then add --approve-spend, or use a read-only verb "
            "(list/get/describe) first."
        ),
        approval_token=APPROVAL_TOKENS[Family.SPEND],
    ),
    Rule(
        id="SPEND-004",
        family=Family.SPEND,
        verdict=Verdict.ASK_MONEY,
        title=(
            "Managed-job launcher verb (modal/sky/sagemaker/custom-jobs/az ml) or *_job.py submit"
        ),
        pattern=_SPEND_004_PATTERN,
        guard=_SPEND_004_GUARD,
        safe_correction=(
            "Confirm the job cost, then add --approve-spend, or run with a local/dry-run "
            "mode first."
        ),
        approval_token=APPROVAL_TOKENS[Family.SPEND],
    ),
    Rule(
        id="IRR-001",
        family=Family.IRREVERSIBLE,
        verdict=Verdict.ASK_IRREVERSIBLE,
        title="Write/copy/move into a system, runtime, package, or version-control directory",
        pattern=_IRR_001_PATTERN,
        guard=_IRR_001_GUARD,
        safe_correction=(
            "Confirm the change is intended, then add --approve-irreversible, or write "
            "into the project tree instead of the system, runtime, or version-control one."
        ),
        approval_token=APPROVAL_TOKENS[Family.IRREVERSIBLE],
    ),
    Rule(
        id="IRR-002",
        family=Family.IRREVERSIBLE,
        verdict=Verdict.ASK_IRREVERSIBLE,
        title="git push with --force, -f, --force-with-lease, or --mirror",
        pattern=_IRR_002_PATTERN,
        guard=None,
        safe_correction=(
            "Confirm the history rewrite, then add --approve-irreversible, or push "
            "without --force."
        ),
        approval_token=APPROVAL_TOKENS[Family.IRREVERSIBLE],
    ),
    Rule(
        id="IRR-003",
        family=Family.IRREVERSIBLE,
        verdict=Verdict.ASK_IRREVERSIBLE,
        title="Recursive force-delete of a data-shaped target",
        pattern=_IRR_003_PATTERN,
        guard=_IRR_003_GUARD,
        safe_correction=(
            "Confirm the deletion, then add --approve-irreversible, or delete a single "
            "named file instead."
        ),
        approval_token=APPROVAL_TOKENS[Family.IRREVERSIBLE],
    ),
    Rule(
        id="IRR-004",
        family=Family.IRREVERSIBLE,
        verdict=Verdict.ASK_IRREVERSIBLE,
        title="Checkpoint write to a name carrying no version/step digits, or --overwrite",
        pattern=_IRR_004_PATTERN,
        guard=_IRR_004_GUARD,
        safe_correction=(
            "Confirm the overwrite, then add --approve-irreversible, or write to a new "
            "versioned filename."
        ),
        approval_token=APPROVAL_TOKENS[Family.IRREVERSIBLE],
    ),
    Rule(
        id="DENY-001",
        family=Family.DESTRUCTIVE,
        verdict=Verdict.DENY,
        title="Whole-tree git discard (stash/reset --hard/checkout/switch/restore/clean)",
        pattern=_DENY_001_PATTERN,
        guard=None,
        safe_correction=(
            'Re-run with an explicit pathspec naming a real file (e.g. '
            '"git checkout -- src/app.py"); "." is the whole tree, not a scope. Or run '
            '"git stash list" first.'
        ),
        approval_token=None,
    ),
    Rule(
        id="DENY-002",
        family=Family.LEAK,
        verdict=Verdict.DENY,
        title="Credential field written into a json/yaml/yml/env/toml/ini/txt/md/cfg file",
        pattern=_DENY_002_PATTERN,
        guard=_DENY_002_GUARD,
        safe_correction=(
            "Remove the credential value before writing; never place a secret in a "
            "shared artifact file."
        ),
        approval_token=None,
    ),
    Rule(
        id="MALFORMED-001",
        family=Family.INPUT,
        verdict=Verdict.DENY,
        title="Command input is empty, blank, non-string, oversize, or contains NUL",
        pattern=_MALFORMED_001_PATTERN,
        guard=None,
        safe_correction=(
            "Resend a single non-empty command string under the length limit, with no "
            "NUL bytes."
        ),
        approval_token=None,
    ),
)

RULES_BY_ID: dict[str, Rule] = {r.id: r for r in RULES}


def rule(rule_id: str) -> Rule:
    """Return the rule with this id. Raise KeyError if unknown."""
    return RULES_BY_ID[rule_id]


def rules_for_family(family: Family) -> tuple[Rule, ...]:
    """Rules of one family, in table order."""
    return tuple(r for r in RULES if r.family is family)
