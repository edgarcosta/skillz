# Reviewing

Layout for two kinds of text: a pull request review and an issue triage reply. The rules in SKILL.md apply; this file only says where each part goes.

## When the findings come from another skill or person

If audit-changes, another tool, or the reviewer supplied the findings, they own what is true: each finding's severity, location, evidence, and confidence, and the verdict. You may reorder findings, group ones that share a cause, label them, and shorten their wording. You may not add a finding, drop one, change a severity, soften or strengthen a claim, or remove a location, snapshot, or link. If something you need is missing, such as a verdict or a severity, say it is missing and ask; do not fill it in. "No issues found" is not "approve" unless the reviewer says so.

## Pull request review

A review is one summary plus inline comments. Evidence and fixes go in the inline comments; the summary says what they add up to and links to the blocking ones.

- First line of the summary: the verdict and its one reason. "Request changes: is_squarefree(0) returns True where the old code raised." Something the author got right (rule 6) follows the verdict on the same line, never before it.
- Then, only the parts that exist: blocking items, one line each pointing at its inline comment; non-blocking items (nits, questions) labelled as such; what was checked and only that (ran the tests, tried the reproduction, or read the diff), and what was not.
- Each inline comment is one finding: the problem, the fix if there is one, then one word for severity: blocking, nit, or question.
- Last line of the summary (rule 7): the action that gets it approved, when the reviewer set one; when approving, the evidence approved on.
- A small unrelated change already in the diff gets one bullet marked unrelated. A problem outside the diff with no issue yet gets one line, so the author knows it was seen.

## Issue triage reply

- First line: the disposition the triager decided: confirmed, cannot reproduce, not a bug, duplicate of #N, or needs information.
- Then, by disposition. Confirmed: where the problem is if known (rule 4) and what happens next. Cannot reproduce: exactly what was run, on which version, and what was seen instead. Needs information: the one or two details that decide it, not a checklist. Not a bug, or duplicate: the reason in one line and the link, plus what the reporter can do instead.
- Last line (rule 7): what is needed from the reporter, or "nothing needed, will update here". Say who takes the next step; if that is unsettled, say so and ask.
