---
name: harden-plan
description: Iterate a plan or design document to a reviewed fixed point through tiered multi-model review, revising the file in place. Use when the user wants a plan, design doc, spec, RFC, or implementation plan reviewed, stress-tested, hardened, or iterated before execution, including phrases like 'review my plan', 'harden this design', 'is this plan ready', and before executing an implementation plan. Prefer audit-changes for code diffs, patches, and pull requests; prefer grilling when the user wants to be interrogated about their own thinking rather than have a document revised.
---

# Harden Plan

Revise a plan document in place until it survives review. This is the sibling of audit-changes: audit-changes is a read-only audit of code diffs; harden-plan revises prose plans. Reviewers asked to find issues never return empty, so "reviewer finds nothing" is not a reachable fixed point. The fixed point is zero accepted findings: a judge triages every finding against a written rubric before any revision happens. Three mechanisms keep iterate-on-critique from bloating the plan into an overengineered mess: the triage gate, a persistent rejection ledger fed back to reviewers, and a scope anchor (Goals and Non-Goals sections in the doc itself).

Paths below are relative to the skills root, the directory that contains this skill's directory. The run script is `python3 review-protocol/scripts/review-run.py`, written as `review-run` from here on.

The main session does only the four steps below. The whole loop (rounds, lanes, triage rubric, revision discipline) lives in [`agents/sub-orchestrator.md`](agents/sub-orchestrator.md); that file is the subagent's brief, so read it yourself only when the user asks how the loop works or a run needs debugging.

## 1. Resolve the target

The target is one plan, design doc, spec, or RFC file in the current worktree, resolved from the user's request; ask only when two candidates are in genuine contention. Accept only files: save pasted text to a file first, and redirect code diffs, patches, and pull requests to audit-changes.

## 2. Snapshot the before state

Run `review-run new harden`; it prints the run id and creates the run directory at `docs/superpowers/review-runs/<id>`. Run `review-run copy <run-dir> <doc> --lane initial` to record the live document's hash, then copy `<run-dir>/lanes/initial.doc.md` to `<name>.pre-review.md` beside the document with `cp` before anything else touches it. The doc is often untracked under an excluded directory, so git cannot supply the before state; this copy is what the final diff is measured against, and the recorded hash prevents a later `write` from overwriting an external edit.

## 3. Dispatch the sub-orchestrator

If `dispatching-agents/local.md` exists, pick the sub-orchestrator with `fleet-pick --lane harden.judge --json --wave <id>`, where the id is the run id from step 2, and dispatch it through that wrapper's CLI in the dispatching-agents command shape with the returned args; if it does not exist, dispatch it through your harness's agent tool at the top tier. Exit 3 from the picker, or a failed dispatch, is a coverage gap on the one lane that runs everything else: log it with `review-run log <run-dir> gap harden.judge: <command and output>` and stop without retry or rerouting. For a CLI dispatch, run it as a detached process that writes to its own log file beside the doc, because the loop outruns a shell tool's timeout. For a native dispatch, use the harness agent lifecycle instead and wait for its returned final report; no detached shell log exists in that path. Its brief is `agents/sub-orchestrator.md`; pass it the doc path, the before-copy path, the run directory, the run id, and any user-supplied context about goals or constraints. The whole review loop runs inside that process or native agent so the main session's context stays clean; run no reviewer lanes and no triage yourself.

Lane grant: this skill authorizes lanes harden.judge, harden.flash, harden.gpt and harden.claude as fleet-pick resolves them, under the dispatching-agents rule that the wrapper choice is the user's. State the grant in the dispatch so the sub-orchestrator proceeds without asking which wrapper to use.

## 4. Relay the result

When the CLI log carries the sub-orchestrator's final report, or the native agent lifecycle returns it, relay to the user:

- whether Goals and Non-Goals were inferred by the harness rather than written by the user, since dispositions may hinge on inferred scope;
- the per-round trace and the ledger summary;
- where the before-copy, the run directory and its `ledger.tsv` are;
- non-convergence, stated plainly with the residual findings, whenever a round cap was hit. Never present a capped run as success.
