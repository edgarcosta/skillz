---
name: bead-orchestration
description: >-
  Use when driving a multi-step goal through beads, orchestrating workers without
  managing them, asked to "orchestrate this", or resuming a goal from its bead.
---

# Bead orchestration

Keep one conversation with the user. Beads hold the plan and context.

## 1. Write or resume the tree

The orchestrator is the user's session: it keeps context for decisions, never implements.
Workers are one-shot: one child bead, one dispatch, then end. Use no long-lived or
coordinating agents, daemon, automatic retry, scaling, or reconciliation.

Make the goal a parent bead. If exploration is needed, dispatch a short-lived worker
to write the tree, at the tier that exploration demands; otherwise write it as
orchestrator. Each small child needs a done-condition a third party can check (a command
and expected result, or an observable fact), one tier label with a one-line reason, and
explicit dependencies. Choose the tier by the hardest judgement the work demands:
`cheap` for lookups, searches, recording known facts, renames, formatting or polling,
even when the result lands in a plan file; `mid` for code or prose written to a settled
design; `top` only for novel design or correctness-critical verification. Split a child
whose parts demand different tiers. Use
`bd create --parent <goal> --acceptance '<condition>' --labels tier:<tier> --description 'Tier: <tier>, because <reason>. ...'`
and `bd dep add <child> <prerequisite>`.

Specs too long for a bead field go in an excluded working directory. The child's
description names the file and part; keep its done-condition, tier, and notes in the bead.
At every state change, update the parent's notes: done, in flight, next.
To resume, read `bd show <goal>`, list `bd list --parent <goal> --all --limit 0`,
and read its children. These records suffice without conversation history.

## 2. Dispatch ready children

Before dispatch, check every work child has a done-condition and exactly one tier
label, `tier:cheap`, `tier:mid` or `tier:top`, whose reason opens its description.
When the reason contradicts section 1's tier rule, correct the label and note why.
Use `bd ready --parent <goal>` as the dispatch queue; never dispatch decision beads.
Read [local.md](local.md), or section 7 when it does not exist; dispatch what the
binding returns for the child's tier. Stop and report failed dispatches or exhausted
picks; never route around them.

Every child runs on the goal branch, one at a time, in dependency order.

Keep the worker prompt to a few lines: child id, worktree, and standing rules.
Tell it to read the child and goal, do only this child, append evidence for each
done-condition clause to its notes, commit on the branch, and leave the bead open.
It states whether the done-condition holds, with evidence. The bead names the spec.
Include this rule in the worker prompt: when the bead, goal, code, and repo conventions
leave more than one defensible answer, do not decide. Append options to the bead's notes
and end with `DECISION: <the question in one sentence>`. Make small calls with a
conventional default and note them in the bead.

## 3. Check and review each return

A worker return ending on a `DECISION` line goes to section 4 alone, not a failed
done-condition check or a review round. Otherwise, the orchestrator checks the
done-condition itself before closing a child; a worker's "tests pass" is a claim to check.
Give each intermediate child one reviewer: `math-review` for a mathematical change,
otherwise `review` from a different model family than the worker's, subject to
[local.md](local.md). Use the same brief shape, read-only, ending on one `VERDICT: clean`
or `VERDICT: fix` line. Define clean as nothing at medium severity or above.
For `VERDICT: fix`, triage every finding: evident fix to the next fix worker; not worth
fixing to the child's notes as an open item; more than one defensible fix to section 4.
At most four review rounds per child. A failed done-condition check counts as a fix round
like `VERDICT: fix`, not a retry. Each intervening fix gets a fresh one-shot worker at the
child's tier. Close when the done-condition holds and the latest review leaves nothing
to fix: `VERDICT: clean`, all findings triaged as open items, or the four-round cap met.
Record remaining items in the child's notes; do not loop on them.
When a child closes, refresh at once what it built in every structured decision record
it depended on, with complete branch/PR/issue links. Use current ruling data and the binding's
stored-source record form; local.md covers decisions without a structured record.
If the done-condition check still fails after round four, stop and report to the user
with the child's notes; leave the child open.

## 4. Record decisions and proceed

Decisions may come from a worker's `DECISION` line, a review finding, or the orchestrator's triage.
Before preparing the question, create one `--type decision` bead under the goal for the run.
Cover every source label or one bare question in that run's single question file.
Add `bd dep add <child> <decision>` for every affected child, across all labels.
Then the orchestrator runs the `jury` skill itself. Decision beads need neither a tier
nor a work done-condition.
This is a standing grant to apply the jury result. Follow `jury` for authority, provisional rulings,
recording, review labels and closure; its local binding owns the record recipes.
Append the recorded ruling to every affected child's notes, and dispatch ready work as fresh one-shot workers.
A decision the user makes without a jury run receives the binding's direct-user marker;
a ruling in chat on a recorded jury card is a human ruling, recorded as in section 6.

## 5. Review the whole branch and hand back

When every child is closed, run one final multi-model review on the whole branch
before the PR: run `review-loop`. Its first round is the `audit-changes` pass;
it ends there when nothing needs fixing.
The orchestrator still never implements: dispatch each fix the loop calls for as a
one-shot worker picked for `tier:mid`; triage stays with the loop's judge. The loop owns
its bounded follow-up reviews; do not repeat the final review per child.
Record any jury at the loop's cap through section 4, with dependencies for affected work.
Refresh its built text through the stored-source form once the loop's fix lands.
List every open item in the children's notes at handback, whatever recorded it.
After the audit, put each item it did not raise again in the PR body's limitations.
Keep these items out of audit-changes lane prompts, which forbid orchestrator prose.
Hand back under the repo's push/PR rules. The parent stays open until the user merges.

## 6. Review decisions and approve corrections

Follow `jury` for page feedback, current-record checks and correction-scope approval.
Ruled cards join the task conversation's page through `handback-tracker`.
For reviews of earlier rulings, follow handback-tracker's rule for a review of earlier rulings (the one second page) and jury's collection binding.
Resume the page owned by this conversation; keep the task's `Handback:` pointer and the review's `Decision review:` pointer distinct.
Keep completed children's built descriptions current as in section 3.

For an overturn of a recorded jury decision, record the replacement human ruling as jury directs,
then `bd reopen <decision>` to block open dependents across all labels.
Read affected work from blocking work-bead `dependents` in `bd show <decision> --json`.
Before reopening work or creating correction children, show each affected bead, what it built,
complete branch/PR/issue links and the proposed correction; ask for scope approval.
Record the proposal and pending approval in the decision's notes. Keep closed work and any
closed goal closed until approval; pause affected dispatch, including ambiguous dependencies.
For handed-back work with a task tracker, set its `now` to say its commands wait for approval
of the correction, then republish through handback-tracker step 5. After an inline handback,
say in chat that those commands wait for approval of the correction. Preserve its branch meanwhile.
After approval, record it and append the replacement ruling to every unstarted affected child's
notes before closing the decision. Then reopen only agreed work and goal, or create approved
correction children.
Unaffected work may proceed under jury's correction rule.
Mark the review card done with 'Overturned X; now Y; see <link>'; record approval and later
correction links in the bead and update the row. This settles the ruling, not the correction.
For older cards, review their prose explicitly; record chat rulings and clear the label through
local.md without creating a structured record.

## 7. Without local.md

With no local.md next to this file, there is no binding. Dispatch through your harness's
agent tool: a worker at the child's tier, a `review` reviewer at mid tier, a `math-review`
reviewer at top tier. With no other model family in reach, review in the same family and
record "reviewed in the same family" as an open item on the child. Where a step uses the
binding's record form, marker or label, write the same facts to the decision bead's notes.
