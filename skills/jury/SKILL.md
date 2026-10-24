---
name: jury
description: Use when a decision has more than one defensible answer and one model's judgement is not enough: "ask the jury", "get a second opinion from several models", a design choice between two workable options, or a skill that reaches a question it cannot settle on its own. Convenes independent blind jurors on one self-contained question and reports them as a decision card for the user to rule on.
---

# Jury

A jury is several models answering one question independently, none of them seeing another's answer. It is for a decision where more than one answer is defensible and one model's blind spot would be expensive. The user rules. You write the question and cast no vote.

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

Define every symbol, name and abbreviation on first use. Ask for a bounded answer that opens with two lines,

    PICK: <option letter, "none", or "new: <the option in one sentence>">
    REASON: <the deciding reason, one sentence of at most 20 words>

and then argues the pick within a word limit, ending with a fixed sentinel line you choose, so a truncated run is detectable. A pick that depends on something carries its condition in the PICK line: "A if the release build passes". A question file that asks several questions, or one question about several items such as each open finding, labels each one (Q1, Q2 or F1, F2) and asks for one PICK and REASON pair per label: "PICK F1: FIX", "REASON F1: ...".

## Dispatch and collect

Every juror gets the same file. Dispatch them in parallel, each in its own process.

Check every reply for the sentinel line. A reply without it was truncated: report it as truncated rather than reading the fragment as an opinion. A juror whose command fails is reported to the user with the command and its output, and is never rerouted to another account or model, because swapping a juror changes the panel the user is about to rule on.

## Relay and record

Report the decision as a card the user can rule from alone, in this order:

1. **Heading**: the decision in one line. When one message walks through several decisions, number them: "Decision 5 of 12: ...".
2. **Context**: one paragraph a reader with no memory of the session can follow: what the thing is, what changed, and which constraint forces the choice. Take it from the question file, define every name on first use, and cite pull requests and issues by number.
3. **Options**: the lettered options, one line each. A juror's "new" pick joins the list under the next letter, marked with the juror who proposed it.
4. **Jury**: one line per juror, in alphabetical order: its name, then its PICK and REASON lines copied word for word. Every juror keeps its line: a reply with no PICK line reads "no pick line", a truncated reply "truncated", a failed command "no reply, exit <code>" followed by the command and the last line of its error output. Then at most one agreement line, for a point every juror who replied makes in its own text, with the count: "All four keep the uninstall cleanup, so D is out."
5. **Mine**: optionally your own recommendation, last, as "Mine (no vote): ...".
6. **Full replies**: the run directory that holds them.

The juror lines are the jurors' own words, so the user rules on what the jurors said rather than on your reading of it. A missing PICK line stays missing: a pick inferred from the body is your reading. A question file with several labels gets one Options and Jury block per label.

Record the question, the card, the full replies pasted in, and the ruling wherever that decision is tracked, as soon as the user rules. Paste rather than link, because a worktree file is gone when the record is read somewhere else.
