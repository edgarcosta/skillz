---
name: review-loop
description: Bound an audit-and-fix loop on a code change to a few rounds and end it, calling audit-changes for the finding half. Use when the user wants a branch, patch, or pull request reviewed and fixed, iterated until it is ready, or wants such a loop bounded, including "review this PR and fix what matters", "audit and fix this branch", and "once it lands, review it". Prefer audit-changes alone when the request is to audit, inspect, or report with no fixing.
---

# Review Loop

Audit one pinned change, fix only what is worth fixing, and stop. audit-changes finds; this skill decides which findings earn a fix, applies them, bounds the rounds, and hands back what was decided.

The boundary with audit-changes runs both ways. A request to audit, inspect, or report on a change, with nothing to be changed, is audit-changes on its own: run that skill and do not open a loop. A request to review and fix, to iterate on a change until it is ready, or to bound such a loop, is this skill, which calls audit-changes inside every round. A loop never substitutes its own reading of the diff for that audit.

Paths below are relative to the skills root, the directory that contains this skill's directory. The run script is `python3 review-protocol/scripts/review-run.py`, written as `review-run` from here on.

## Terms

- **Round**: one pass over the pinned change: finders, then validators, then triage, then one fix pass.
- **Finder** and **validator**: audit-changes' lanes. A validator is a fresh agent of a different model from the finder and answers confirm, reject, or needs-context for one candidate.
- **Triage**: a proportionality judgement on each confirmed finding, made by one top-tier judge dispatched for it, separate from the finders and from whoever applies the fixes. It returns one verdict per finding: **FIX** in the smallest shape, **SIMPLIFY** to a named smaller version of a fix an earlier round already made, or **DECLINE** with a one-line reason the maintainer can paste into a review thread.
- **Accepted limit**: a declined finding.
- **Mutation gap**: a test-strength gap found by breaking a check on purpose, where the suite still passes although the property it names broke.

## 1. Open the run

Resolve the target and its base exactly as audit-changes step 1 does; that skill owns target resolution and the snapshot. Then run `review-run new loop`, which prints the run id and creates `docs/superpowers/review-runs/<id>`. That id is the loop's wave id for every pick, and its `ledger.tsv` is the loop's record. Each round's audit mints its own run directory; this one is the loop's and outlives them.

## 2. Each round

1. Run a new audit-changes pass over the whole change. The base is fixed for the loop and the head moves with each fix pass, so a round snapshots the current head against that base and audits all of it, including code outside the last fixes, because cross-file interactions surface there. Narrowing a later round to the lines the last fix pass touched is not an option. Each audit run shares its frozen source copies and applicable rule files across lanes; a later round captures current source text again.
2. Keep earlier declines and rulings in the loop ledger for orchestrator triage. They do not enter later finder or validator prompts; fresh reviewers make independent judgments on the current snapshot.
3. Triage every confirmed finding, and the fixes earlier rounds already made along with them. A SIMPLIFY or revert verdict on an earlier fix is applied in this round's fix pass.
4. Give the fixer only the FIX and SIMPLIFY items, in the shape triage named. Record each DECLINE with `review-run log <run-dir> limit <finding> / <one-line reason>`.
5. Decide whether the loop stops.

## 3. The proportionality bar

A fix earns its place when a realistic trigger in the documented workflow produces a wrong result that matters: a broken or unsafe artifact shipped, a record that lies, a check that passes what it exists to catch. The fix must also be small relative to that harm. Weigh against it:

- triggers that need a hostile or unusual actor on the maintainer's own machine, or inputs the pipeline never produces; these are declined;
- lines of code and test fixture added, new branches, engine- or platform-specific paths;
- prose added to READMEs and commit messages.

Preference order: decline with a reason; a one-line comment or README sentence stating the limit; the smallest code change; anything bigger only when the harm is real and likely.

## 4. Severity

Severity is audit-changes' one scale: high for security, data loss or corruption, or a wrong result; medium for incorrect behaviour on a reachable input the change did not intend, with bounded impact; low for correct but misleading or fragile. Do not introduce a second scale.

A mutation gap is medium only when the pull request body or the test itself claims the property that broke. Otherwise it is low.

## 5. When the loop stops

**Normal stop.** The loop ends after the first round in which no confirmed finding of medium severity or above survives triage as FIX. Decide that with the script rather than by hand. After triage, write the round's post-triage view to `<run-dir>/validations.json` as a list of objects with the keys `candidate`, `lane`, `disposition` and `severity`, recording a FIX as `confirm` at the finding's severity and a DECLINE or a SIMPLIFY as `reject`, then run `review-run should-stop <run-dir> --min-severity medium`. The validators' own file stays in the audit's run directory and is not edited.

Read that command's exit status, not the word it prints: `should-stop` is named for audit-changes' fast-fail, where a confirmed finding stops the fan-out, so its words read backwards here. Exit 1, printed as `continue`, means nothing medium or above survived, so this round's fix pass is the last one and the loop ends. Exit 0, printed as `stop`, means one did, so run another round. Exit 2 means a bad or missing file: stop and report it.

**Cap.** At most 3 rounds. When round 3 still leaves a medium-or-higher FIX open, convene the jury once, apply one fix pass directed by its answers with focused verification, and end the loop. Never run a fourth round, and never present a capped loop as a converged one: say that it hit the cap and what remains open.

**Blocker.** When a correctness or security blocker remains after that pass, pause the lane and hand it to the maintainer rather than fixing on.

## 6. The jury at the cap

Convene the four-juror panel once, through the `jury` skill. Its question file asks exactly:

1. For each open confirmed finding: FIX at the smallest adequate scope, or DECLINE as an accepted limit?
2. Does any earlier DECLINE or SIMPLIFY now look unsafe, given the accumulated changes?
3. After those fixes, is the pull request ready?

Convene it at the cap and nowhere else.

## 7. End of the lane

Hand the maintainer one list: every remaining low finding, and every DECLINE with its one-line reason. That list is where a misjudged severity gets caught, so it is complete: no entry is summarized away and no count stands in for the entries. Report alongside it how many rounds ran, whether the loop stopped normally or at the cap, what the fix passes changed, the run directory and its `ledger.tsv`, and every coverage gap the rounds' audits recorded.

## Failure handling

After the dispatching-agents retry step, a failed dispatch and a picker exit 3 are the same thing: a coverage gap. Log it with `review-run log <run-dir> gap <lane>: <command and its output>`, continue with the remaining lanes, and never retry, reroute, or substitute a different venue, account, vendor or model. A round whose finder lanes all failed is not a round that found nothing: report it, and do not count it toward the cap or read it as a normal stop.
