# Changelog

**Note on this file's history:** earlier drafts of this changelog described four separate dated
releases (0.1.0 through 0.3.1), each with its own version heading. The actual git history for this
repository is **one commit** (`2fcc025`, "Initial release: source-available, evaluation-only.",
2026-09-06) and no tags — so those four version headings never corresponded to four real releases.
This file now has one release section, matching the one shipped commit and the version in
`pyproject.toml`, plus a "Development notes" section that keeps every fact from the original four
sections — the bugs found, the blind-test receipts, the fixes — as a chronological record of the
single development session that produced that commit, not as release history.

## [0.3.1] - 2026-09-06

The one shipped commit (`2fcc025`). What the package contains: an 11-rule shell-command policy
classifier (`ALLOW` / `ASK_MONEY` / `ASK_IRREVERSIBLE` / `DENY`) with a per-command `explain`
trace, a deterministic sha-pinned synthetic command deck plus a separately authored holdout deck,
an fp/fn/precision/recall scorer against a published error budget, a CLI (`score`, `generate-deck`,
`explain`, `--version`), CI on `ubuntu-latest` and `windows-latest` across three Python versions, a
source-available Evaluation-Only Licence, and a two-part forbidden-string scanner (a plain word
list plus a hashed name list) with a planted-token check. See "Development notes" below for how
each piece was built and debugged during the single session that produced it.

## Development notes (pre-release, single session 2026-09-06)

The passes below happened in this order during the one development session that produced the
single commit above. They were originally written as four dated version sections (0.1.0, 0.2.0,
0.3.0, 0.3.1); there are no commits or tags behind those version numbers, so they are kept here as
development notes instead, with every fact from the original sections — the bugs found, the
blind-test receipts, the fixes — unchanged.

### Pass 1 (originally labelled "0.1.0")

#### Added

- Initial release: an 11-rule shell-command policy classifier (`policy_deck.policy`,
  `policy_deck.classifier`) with four verdicts: `ALLOW`, `ASK_MONEY`, `ASK_IRREVERSIBLE`, `DENY`.
- `policy_deck.explain` — a per-command trace naming every rule considered, which one won, the
  safe correction, and (when applicable) which approval token would clear a block.
- `policy_deck.deck` — a deterministic, seeded, sha-pinned synthetic command-deck generator, plus
  a small hand-written hard-cases file covering obfuscations and flag flips.
- `policy_deck.score` — an fp / fn / precision / recall scorer against a published error budget,
  with a fail-closed sha precondition and a distinct exit code for an operational error versus a
  missed budget.
- `policy-deck` CLI: `score [--json] [--receipt PATH]`, `generate-deck [--seed] [--rows] [--check]`,
  `explain COMMAND [--json] [--approve-spend] [--approve-irreversible]`, `--version`.
- CI on `ubuntu-latest` and `windows-latest`, Python 3.10 / 3.11 / 3.12: the test suite, a
  deck-drift check, the budget gate, and a forbidden-string scan — all four must pass.

#### Known limitations

- This is a policy classifier over command **text**, not a sandbox. Indirection defeats it by
  construction: an interpreter reading a variable (`eval "$RISKY"`), an aliased command
  (`g=git; $g push --force`), an encoded payload, or a command substitution as the target
  (`rm -rf $(cat targets.txt)`) are documented, tested blind spots — see
  `decks/hard_cases.jsonl` (`known_gap: true`) and the README section "What it does not do", not
  a silent gap discovered later.
- `git checkout <branch>` and `git switch <branch>` are refused deliberately. Without a
  project-scope lookup this package cannot tell a branch name from a pathspec, so it over-refuses
  rather than under-refuses on that one ambiguity. It is a named false positive, priced into the
  false-positive budget, not an accident.
- "Is this the right thing to be working on" is not detectable from a command string at all, so
  scope and direction is out of scope for this package by design — see the README section
  "What it does not do".

### Pass 2 (originally labelled "0.2.0")

A holdout deck written against the rule **titles** — deliberately not against the patterns — found
four rules doing materially less than they claimed. All four are fixed, and both receipts are now
printed in the README instead of a placeholder.

#### The four misses, before and after

The holdout is 190 rows: 131 ordinary developer commands, 45 risky ones spread across every rule
family, 12 near-misses, and 2 rows of the package's own disclosed over-refusal. Scored against the
rule table as it stood, it returned **fn=21 against a published budget of fn<=0**.

| receipt | rows | fp | fn | verdict |
|---|---|---|---|---|
| holdout, rule table **before** the fix | 190 | 2 | **21** | **FAIL** (fn budget is 0) |
| holdout, rule table **after** the fix | 190 | 2 | **0** | PASS |
| fitted deck, **before** | 1,260 | 0 | 0 | PASS — and blind to all four defects |
| fitted deck, **after** (relabelled, see below) | 1,260 | 8 | 0 | PASS |

Per rule, the false negatives the old pattern let through and the smallest change that closed it:

| rule | fn before | fn after | change |
|---|---|---|---|
| `DENY-001` | 2 | 0 | the force-flag lookahead matched the literal `-f`, so `-df` and `-xfd` passed. It now matches a short-flag cluster containing `f`, anchored to the start of its own token so a pathspec with a hyphen is still not a flag. |
| `DENY-002` | 6 | 0 | the sink matched `.json` only, under a title that said "artifact file". The extension list is now `json/yaml/yml/env/toml/ini/txt/md/cfg` through `>`, `>>`, `tee`, `cp`, `mv` and `--output`, and the rule title names that list exactly. |
| `SPEND-003` | 6 | 0 | the pattern covered `aws ec2`, `gcloud compute` and `az vm` only. It now covers storage, managed databases, serverless functions and managed clusters across the three providers. The mutating-verb guard is unchanged in kind and still lets every read verb through. |
| `SPEND-004` | 7 | 0 | the pattern was a filename convention plus one literal. It is now the launcher verbs themselves (`modal run/deploy`, `sky launch`, `aws sagemaker create-*`, `custom-jobs create`, `az ml job create`, `together fine-tuning create`, `anyscale`/`ray job submit`, `runpodctl`/`vastai` create, `beam`, `dstack`), with the `*_job.py` arm keeping its submit/create second signal. |

`tests/test_holdout_regression.py` plants each pre-fix pattern back in memory and asserts the
holdout fails again — and that the **fitted deck reports fn=0 against every one of those broken
patterns**, which is the whole argument for keeping a holdout, written as an assertion.

#### Added

- `decks/holdout_v1.jsonl` and `src/policy_deck/holdout.py` — an authored holdout deck, sha-pinned
  in `budget.json` and rebuildable byte-for-byte with `policy-deck generate-deck --holdout --check`.
- `policy-deck score --holdout` — scores the holdout against its own bars
  (`holdout_fp_budget`, `holdout_fn_budget`), with its own receipt schema
  `policy-deck/holdout/1`. The two decks are never merged into one number.
- `budget.json` gains the optional keys `holdout`, `holdout_sha256`, `holdout_rows`,
  `holdout_fp_budget`, `holdout_fn_budget`. The addition is backward compatible: a budget file
  without them still loads, and `score --holdout` then reports an operational error rather than
  silently scoring nothing.
- `explain` on an ALLOW now prints `reason: no rule matched (11 rules evaluated)` instead of a
  bare verdict line.
- `scripts/forbidden_scan.py` prints `scanned N files, H hits` and exits `2` when `N == 0`; an
  empty or wrong root is a broken instrument, not a clean tree.

#### Changed

- **The deck no longer scores the package's own disclosed false positive as a correct catch.**
  Branch-name `git checkout` / `git switch` rows moved out of the `destructive_git` class into a
  new `known_false_positive` class of 8 rows labelled `expected: ALLOW`, `known_gap: true`. The
  fitted receipt now reports **fp=8 against a budget of 36** instead of fp=0, and the README
  sentence "priced into the false-positive budget" is literally true for the first time. The
  classifier's behaviour is unchanged: it still refuses those commands, on purpose, for the
  reason the README gives.
- `read_traffic` drops from 690 to 682 rows so the deck stays at 1,260 with the same
  1,220 ALLOW / 40 blocked split.
- The deck sha is re-pinned (both the relabel and the new class change the bytes).
- Rule titles for `DENY-002` and `SPEND-004` now describe exactly what their patterns match. A
  title that outruns its pattern is the failure this package exists to criticise elsewhere.
- The README prints the real measurement — both receipts with their deck shas, the budgets, and
  PASS/FAIL — instead of `<n>` placeholders.
- `scripts/forbidden_scan.py`'s split-word constants are renamed to neutral names
  (`_W_CODENAME_1`…), so its docstring's claim that no forbidden word appears in its own source is
  true of identifiers as well as string literals, and a test asserts it against the file's bytes.

### Pass 3 (originally labelled "0.3.0")

A **second** blind pass authored 60 rows from the rule titles alone, before opening the shipped
holdout or `policy.py`, and scored them cold. It returned `fn=3` against a budget of zero — and
all three misses landed in the four rule families the shipped holdout had written with a pattern
in view. Probing the third one's clause found a fourth hole with no row against it. A fifth defect
turned up in the scorer itself while the probe was running.

#### The receipt, before and after, on the same 60 rows

| receipt | rows | tp | tn | fp | fn | precision | recall |
|---|---|---|---|---|---|---|---|
| blind 60, rule table **before** this version | 60 | 12 | 45 | 0 | **3** | 1.000000 | 0.800000 |
| blind 60, rule table **after** this version | 60 | 15 | 45 | 0 | **0** | 1.000000 | 1.000000 |

The two shipped decks did not move: the fitted deck still reports `fp=8 fn=0` against a budget of
36/0, the holdout still reports `fp=2 fn=0` against 8/0, `hard_cases` still reports `mismatch=0`,
and all three deck shas are unchanged — no deck was regenerated to accommodate a fix.

#### The four rule defects, and the smallest change that closed each

| rule | what walked through | the fix |
|---|---|---|
| `IRR-001` | a copy into a system config directory, a `tee` into an interpreter's installed-package directory, a write into a repository's own version-control directory. The pattern was three literal directory *names* (`locked`/`protected`/`immutable`) under a title that said "a protected path segment". | the pattern is the title spelled out — absolute system trees (`/etc`, `/usr`, `/var`, …), installed-package and dependency trees (`site-packages`, `node_modules`, …), version-control metadata (`.git`, `.svn`, `.hg`), Windows system directories, plus the three original markers. The guard gains `install`, `rsync` and the Windows write verbs. The title now names the classes. |
| `IRR-004` | `cp checkpoints/step_4000.pt checkpoints/model.pt` — an ordinary unversioned name. The guard was a fixed four-name list (`final`/`best`/`latest`/`last`) under a title that said "a non-versioned name". | the guard is a **stated heuristic**: a destination stem carrying no digit at all cannot name a version or a step. `model.pt`, `latest.ckpt`, `production.safetensors` fire; `step_4000.pt`, `run-973.bin`, `model-v14.pt` do not. The title now says "no version/step digits", so it no longer outruns the pattern. |
| `DENY-001`, restore arm | `restore .`, `restore --worktree .`, `restore --source=HEAD .` — every one a whole-tree discard. The arm matched the **bare** verb only. | `restore` with `--worktree`, with `--source`, or with the `.` pathspec is `DENY`. `restore src/app.py` and `restore --staged src/app.py` still pass. |
| `DENY-001`, checkout arm | `checkout -- .`, which discards the entire working tree. The scoped exemption `-- <target>` exempted the dot. **The rule refused a harmless branch switch while permitting a whole-tree discard, and its own safe correction pointed the caller at the permitted shape.** | the `.` pathspec is its own arm covering both `checkout` and `restore`: a dot is not a scope. `checkout -- src/app.py` still passes, and the safe-correction text now names a real file and says so. |

`tests/test_r2_polish_regression.py` holds all four in place: each pre-fix pattern is planted back
in memory, asserted to miss its shapes again, and the shipped table is asserted to catch every one
with the right rule id. Twelve neighbouring shapes are asserted to stay `ALLOW`, so the catch
cannot be bought with friction. And, as with the first holdout: **both shipped decks still report
`fn=0` against all three broken patterns** — neither could see any of this.

#### The fifth defect: the measuring instrument, not the rules

`score.py::_classify_against` is a small re-implementation of `classify`, used only when a test
injects a substitute rule table. Its docstring claimed to mirror `classify` step for step. It did
not: it skipped the per-rule haystack selection, so `DENY-001` ran against raw text instead of the
quote-masked copy, and a risky phrase quoted inside a commit message scored as `DENY`. The fitted
deck therefore read **`fp=24` through the injection seam and `fp=8` on the normal path, for the
identical rule table**. Every number ever taken through that seam was inflated by the deck's own
quoted-prose near-misses.

`tests/test_injection_seam_parity.py` closes it by comparison rather than assertion: all three
shipped decks are scored both ways and the two paths must return the same verdict and the same
rule id for every row. A re-implementation that claims in prose to mirror another function is a
claim a test has to hold up.

#### Changed

- The README's holdout section no longer claims every row was written from the titles. It now
  prints a family-by-family table saying which four families are independent of the patterns and
  which four are pattern-shaped — and states plainly that the four independent families are
  exactly the four that found defects. The rows were **not** rewritten: the patterns had been read
  by then, so a replacement row would be less independent than the one it replaced, and calling it
  "written from the titles" would be the same claim over worse evidence. The second blind pass is
  the answer to that gap, and its receipt is printed instead.
- The README no longer derives percentages from a measurement that is not published here. The public
  false-positive budget is stated on its own terms (36, 3.0% of the deck's must-pass rows, set
  tight because a template-generated must-pass mass is less adversarial than real command
  history). The one-sentence statement of where the package came from is unchanged.
- The licence is **source-available, evaluation only** — read it, run it to evaluate the author's
  work; no reuse, redistribution, derivative works, commercial use, or use as training data. It is
  not open source, and the previous MIT text no longer applies.
- Test count: 442, up from 364.

### Pass 4 (originally labelled "0.3.1")

A leak audit read every shipped file and asked one question of each line: does this describe the
private system this package was extracted from? Three kinds of answer came back, and this release
is what happened to them.

#### Removed

- **A measurement that is not published here is gone from the README.** The opening paragraph used to quote
  the private guardrail's own measurement — its deck size, its error counts and its published
  budget. Those are numbers about a system that is not published and cannot be checked by anyone
  reading this, and a portfolio piece does not need them: every number in this README is now
  measured on a deck that ships in this repository and that you can regenerate byte-for-byte. The
  origin sentence stays, because where an idea came from is not a secret; the measurement does
  not, because it is somebody's operating data.

#### Licence

- The licence is an **Evaluation-Only Licence**: source-available, not open source. Read it, run
  it, evaluate the author's work — no redistribution, no derivative works, no commercial use, no
  use as training data, all rights reserved.
- PolyForm Strict 1.0.0 was checked first and rejected on its own text: it grants "any
  noncommercial purpose" and a patent licence, both broader than evaluation. A standard licence
  that says more than is meant is worse than a short one that says exactly it.
- The copyright holder is a placeholder, and `scripts/forbidden_scan.py` now **refuses to pass a
  tree that still carries it** — under its own exit code `3`, distinct from a leak (`1`) and from
  a broken instrument (`2`). Nothing private got out and this is not ready to be published are
  different facts and no longer print the same number.

#### Changed

- `pyproject.toml` carries an author with the same placeholder name and a code-host no-reply
  contact address. No personal mailbox appears anywhere in this repository, and the scanner now
  denies the *shape* of one — a mailbox at any of thirteen consumer mail providers — which names
  no person and leaves the no-reply address alone.
- `scripts/forbidden_scan.py` gains a **hashed** half. The fragmented word list it already carried
  covers words this package legitimately discusses; the hashed set covers names it must never
  print at all — an examination name, a rights holder, internal codenames, a private storage
  directory, an institution used in a private demonstration, outreach contacts. Only one-way
  sha256 hexes are committed, the word list is kept outside the repository, `--hash-tokens`
  regenerates the block from it, and a hit prints the hex prefix rather than the offending line,
  because a report that prints the line has published exactly what it was guarding. An empty set
  announces itself instead of reading as a clean tree.
- The licence placeholder is assembled from fragments inside the scanner rather than written whole,
  so the scanner does not report itself and the file keeps its "no self-exemption, no allowlist"
  property literally true.

#### Removed, and this one was the audit's own finding

- **Every private name is out of the scanner's fragmented half.** Eight of the words it denied
  were written into it as `_frag("Ab", "cde")` pairs -- codenames and an outreach contact -- on the
  reasoning that a split word survives a grep. It does, and that is all it survives: anyone reading
  the line reads the word. A guard whose only claim is "these names appear nowhere in this
  repository" cannot itself be where they appear. All eight moved into the hashed set, which denies
  the same words without writing any of them down, and the fragmented half now holds only ordinary
  label and claim vocabulary, which reveals nothing whether it is split or not.
- **The test suite carried the same word in six places**, which is the same leak in a different
  file, and a test suite ships. It carries none now: where a test needs a denied word it invents
  one and injects that word's hash into the deny set for the length of the test, which proves the
  mechanism without the repository holding a real name in any form.
- A planted-token check runs every word of the out-of-repository list through the scan one at a
  time and requires both that it is caught and that the report withholds it: 33 of 33 caught, the
  word printed zero times.

