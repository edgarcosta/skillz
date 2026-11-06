---
name: jury
description: Use when a decision has more than one defensible answer and one model's judgement is not enough: "ask the jury", "get a second opinion from several models", a design choice between two workable options, or a skill that reaches a question it cannot settle on its own, or to review rulings taken earlier. Convenes independent blind jurors on one self-contained question.
---

# Jury

A jury is several models answering one question independently, none of them seeing another's answer. It is for a decision where more than one answer is defensible and one model's blind spot would be expensive. You write the question and cast no vote. Delegated authority follows the rules below; advisory use leaves the ruling with the user.

## When to convene one

- A design decision with more than one defensible answer: a target, a layout, a check method, a trade-off between two costs.
- A review or revision loop that reached its round cap with a question still open. The calling skill says what to ask.
- Any question the user sends to the jury by name.

A question with one right answer gets no jury. A fact, a measurement, or something the code or the documentation settles is looked up, not voted on.

## The panel

Jurors are independent and blind to each other. Each runs in its own process, sees the question and nothing else, and never sees another juror's reply. The panel spans more than one model family, by default two jurors from each of two families, so a question gets two reads per family and a disagreement between families is visible rather than averaged away.

If `local.md` exists next to this file, it names the jurors and the command that dispatches them, and is authoritative. If it does not, take the roster from the user; with no roster, use the dispatching-agents skill to reach the top tier of two families. With no binding, no roster and no second family in reach, report the missing capability and stop, because one model answering alone is not a jury.

## The question file

Write the question to a file before dispatching anything. That file is the whole prompt a juror sees. A juror has no chat context, no tracker access and no memory of the work so far, so anything the question leaves out is not available to it.

It states:

- the decision to make;
- the facts gathered so far, each with the file path, command or measurement it came from;
- the options as they stand, lettered A, B, C;
- what a good answer must cover.

Carry no recommendation or claim of prior approval in the question. Give each option its strongest case in parallel form at similar length. State relevant constraints as facts, with their evidence.

Define every symbol, name and abbreviation on first use. Ask for a bounded answer that opens with two lines,

    PICK: <option letter, "none", or "new: <the option in one sentence>">
    REASON: <the deciding reason, one sentence of at most 20 words>

and then argues the pick within a word limit, ending with a fixed sentinel line you choose, so a truncated run is detectable. A pick that depends on something carries its condition in the PICK line: "A if the release build passes". A question file that asks several questions, or one question about several items such as each open finding, labels each one (Q1, Q2 or F1, F2) and asks for one PICK and REASON pair per label: "PICK F1: FIX", "REASON F1: ...".

## Check the framing

Before each panel dispatch, obtain a fresh blind neutrality read from a different model family than the question's author. The reader is separate from the voting panel. Use the helper beside this skill:

```text
python3 -B <this directory>/scripts/jury-question.py brief QUESTION [--label LABEL ...] -o PROMPT
python3 -B <this directory>/scripts/jury-question.py record QUESTION --author-family FAMILY --reader-family FAMILY [--label LABEL ...] --reply REPLY -o CHECK.json
python3 -B <this directory>/scripts/jury-question.py verify QUESTION CHECK.json
```

Supply every source label exactly once with `--label`, covering the whole file and matching the labels the cards will use. Omit labels for a single unlabelled question. `brief` needs no family arguments; it writes only the checking instruction, label inventory and exact question text.

The reader sees only that prompt, without conversation history, decision records, recommendations or juror replies. Request another family from the dispatcher; `local.md`, when present, binds the command and family metadata. If no second family is available or the reader command fails, record the blocker and leave the panel undispatched. Capture stdout alone as REPLY, with stderr and harness banners separate. Take the reader's family from dispatch metadata, never from its reply, and give the author's family in the same vocabulary.

Create a new output directory for every read, preserving all earlier output. Run `brief` again for every read. Write that read's PROMPT and CHECK.json inside its directory. `record` stores the raw reply, labels, results, normalized families and exact question digest. Exit 0 records an all-label pass; exit 1 records a lean. Revise a leaning question and submit the whole revised file to a fresh read until every label passes, with no iteration cap. Keep each reader's output unchanged as evidence.

Exit 2 means invalid input or I/O failure and leaves an existing record unchanged. For a malformed reply on either an initial or revised question, obtain one fresh read. If that read is also malformed, record the blocker and leave the panel undispatched. Correct other input or I/O errors before retrying.

Run `verify` immediately before dispatching the panel on those exact question bytes. Exit 0 permits dispatch; exit 1 means failed, stale or otherwise unusable evidence; exit 2 means malformed input or I/O failure. Editing any question invalidates the whole-file pass. Keep the sent question and its check with the run; a later read cannot certify an earlier dispatch.

## Dispatch and collect

Every juror gets the same file. Dispatch them in parallel, each in its own process.

Check every reply for the sentinel line. A reply without it was truncated: report it as truncated rather than reading the fragment as an opinion. A juror whose command fails is reported to the user with the command and its output, and is never rerouted to another account or model, because swapping a juror changes the panel the ruling rests on.

## Authority and provisional rulings

An instruction to let the jury decide grants authority for the stated decision or workflow.
A calling skill's standing grant also delegates authority.
Report-only use and "I will rule" keep the ruling with the user.
Independent approval boundaries still apply, including memory-review's explicit accept/apply step.

With delegated authority, an option picked by more than half of the replying jurors is the provisional ruling.
Otherwise, choose the most-picked option cheapest to undo and record why.
Count a conditional pick only after checking its condition; with no eligible pick, report the blocker.
The session applies the panel result without casting a vote: record it before acting, then proceed.

## Relay and record

Send cards with multiple decisions through handback-tracker's jury converter, with one step per source label. Keep source labels unchanged and use distinct tracker step ids when combining runs. Put every PICK and REASON pair before any argument.

Report each decision as a self-contained card for ruling or later review, in this order:

1. **Heading**: the decision in one line. When one message walks through several decisions, number them: "Decision 5 of 12: ...".
2. **Context**: one paragraph a reader with no memory of the session can follow: what the thing is, what changed, and which constraint forces the choice. Take it from the question file, define every name on first use, and cite pull requests and issues by number.
3. **Question**: the exact sent question text, on every card, after Context and before Options.
4. **Options**: the lettered options, one line each. A juror's "new" pick joins the list under the next letter, marked with the juror who proposed it.
5. **Jury**: one line per juror, in alphabetical order: its name, then its PICK and REASON lines copied word for word. Every juror keeps its line: a reply with no PICK line reads "no pick line", a truncated reply "truncated", a failed command "no reply, exit <code>" followed by the command and the last line of its error output. Then at most one agreement line, for a point every juror who replied makes in its own text, with the count: "All four keep the uninstall cleanup, so D is out."
6. **Mine**: optionally your own recommendation, last, as "Mine (no vote): ...".
7. **Full replies**: the complete replies in an appendix or disclosure. Keep the run directory as the working copy.

The juror lines preserve the evidence for the ruling and its later review. A missing PICK line stays missing: a pick inferred from the body is your reading. A question file with several labels gets one Options and Jury block per label.

With delegated authority and a beads store, record one decision bead per jury run under the goal, or a root decision bead with no goal.
Before acting, save the exact question, options, card, full replies, neutrality evidence and provisional ruling through [local.md](local.md)'s first-record recipe.
Paste sources into the record: a worktree file may be gone when the decision is read elsewhere.
Attach affected work dependencies when they exist; otherwise record the owning task, worktree/branch and correction destination in notes and built descriptions.
Initially state that no work has used the ruling; update built work and complete links as it uses it.
Close the decision after its structured record or size-exit fallback is saved, retaining any review label.
The record command owns the review-label predicate: only a matching neutrality pass and unanimous unconditional support from replying jurors on every unreviewed card exempt the run.
The commissioning session owns later updates; jury workers have no later turn.

In advisory use, record the question, card, full replies and the user's ruling wherever the decision is tracked once the user rules.

Add ruled cards to the session's page through `handback-tracker`; use its add-a-run recipe and response-reading rules.
For requests to review earlier rulings, read [local.md](local.md)'s collection and page-pointer recipes, then publish through `handback-tracker`.
Without a project beads store, follow local.md's initialization approval and held-run recovery recipe; rulings remain on the page meanwhile.
Without local.md, save the same sources and ruling wherever the decision is tracked before acting, and keep the card on the session's page.

## Feedback and correction approval

Before acting on a page pick, read the decision's current record if one exists.
If another page recorded a different human ruling, ask on the page before applying it.
Record a confirmation or replacement human ruling through the stored-source form, preserving the provisional ruling, then settle the card on the receiving page.
Answer notes on that page; record changed rulings or added constraints in the human ruling's `text` field or decision notes.

An overturn pauses affected work. Show what used the ruling with complete links, and ask for correction scope before changing it.
Put that scope question on the session's page as `handback-tracker` describes.
Keep closed work closed pending approval; merged work receives new work on a new branch/PR.
Bead-orchestration owns its graph-specific reopen, dependent inspection and approved correction-child procedure.
Settling a ruling does not establish that corrections are complete.
