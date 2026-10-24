---
name: writing-for-humans
description: Use when drafting or revising something the user will send, post, file, or keep: a PR body, a review, an issue, a status update, a summary, an email, a message to a colleague. Ordinary replies in this conversation keep their usual style.
---

# Writing for humans

This shapes text another person will read on their own, without you there to explain it. That reader is busy, does not know what you were doing, and reads the first line and maybe the last. Work out what they need to understand, decide, or do, and write for that.

Short is not the goal. Cut the story of how you got here; keep every fact the reader needs to act, including the fix, the condition it depends on, and any real uncertainty. Use only facts you were given or verified. A path, a line number, an error string, or a test result you did not see is a guess: label it as one or leave it out.

## 1. The point goes in the first line

Start with the conclusion: what changed, what is broken, or what you want. Write it as a full sentence. If you can set the title, the point goes there and the first line of the body gives the strongest fact behind it; with a fixed or generic title, the point goes in the opening sentence.

| kind | setup | point |
|---|---|---|
| PR body | "This PR addresses an issue in the config parser." | "A blank line in config.ini made the parser drop every key after it." |
| Issue | "I've been seeing some strange behaviour lately." | "chezmoi apply exits 1 on any machine with Safari open." |
| Status update | "Quick update on where things are." | "The import is blocked on the TZ bug; the fix is in review as #212." |

## 2. One purpose per text

Organise the text around what was asked. If the request had three questions, answer all three here. A separate problem you notice while writing, one that needs its own owner or resolution, becomes its own message or issue. Link to it from this one. Draft it; do not file it unless asked. Something you noticed but are not addressing here still gets one line saying so, so the reader knows you saw it. Something that blocks the main point stays in, because it is part of the answer.

## 3. Specific over general

Use the most specific verified details you have: names, dates, quantities, commands, versions, exact error text. When you do not know something, say what you checked and what you did not.

Weak: "Fails sometimes under load."
Better: "Fails about 1 run in 5 at worker.py:212 with RuntimeError: dictionary changed size during iteration. Reproduced with pytest -n 8 tests/test_pool.py."

## 4. For a failure: the cost first, then what you know

One sentence on what broke and what it costs the reader. Then only the parts you have: the cause, the fix, the evidence that the fix works. Parts you do not have stay missing; say so.

Cause known: "The migration drops users.last_seen before the backfill reads it, so every row lands NULL. Fix: move the backfill ahead of the DROP (migrations/0042.sql:18). Verified on a restored snapshot: 12,904 rows populated, 0 NULL."

Cause unknown: what breaks, the smallest way to reproduce it, and what you ruled out. Name the boundary you found ("works at p = 2^31 - 1, crashes at p = 2^61 - 1"). No guess at the mechanism.

## 5. Number steps only when order matters

Steps to reproduce, migrate, or deploy: numbered, one action each. Use bullets for unordered items, unless numbers are needed so people can refer to items by number.

## 6. When someone else wrote the work, open with what is right and what is wrong together

This rule applies only when a person other than you wrote the thing you are commenting on. The first line names a strength the work shows and the main problem, in one sentence or two adjacent ones. Neither part is required: with no real strength, one clause thanking them for the work is enough; with no problem, say so. Do not invent either.

Better: "Thanks, the retry loop is the right fix. One thing: this drops the error when n == 0."

## 7. End on the one action you want, if there is one

If the reader must do something, the last line names that one thing: approve, confirm the reproduction, answer a named question. The ask goes last, not first. If nothing is needed, stop when the answer is complete; do not add "let me know what you think".

## Before sending

Run the checker on the draft:

    python3 <this directory>/scripts/check.py DRAFT.md

It lists sentences over 25 words, hedges, filler words, idioms, preamble and closing pleasantries, non-ASCII characters, attribution trailers, and grammar when harper-cli is installed. Each hit is a question, not an order. Fix hits that are padding or vagueness. Keep hits that carry real uncertainty or technical meaning. Never edit text inside a quote, a command, or a code block, even when it is flagged. The report is for you; keep it out of your reply.

## Scope

These rules shape the artifact you will post. The chat reply that hands it over keeps its usual style; if the person reading your reply is the one deciding, the reply is the artifact.

Repository instructions (AGENTS.md, CLAUDE.md) decide structure and formatting: length limits, one bullet per file, ASCII only, no trailers. They win over anything here. This skill sets no limit on list length.

For the layout of a full pull request review or an issue triage reply, read reviewing.md next to this file. When another skill produced the findings (for example audit-changes), that skill owns what is true; this one only orders and words it.
