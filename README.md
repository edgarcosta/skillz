# skillz

Agent skills for auditing code changes, hardening plans, asking several models to rule on a
decision, and writing text that people will read. They work in Claude Code and Codex.

## Skills

- **audit-changes**: High-signal, independently validated audit of a proposed code change. Use for changes in the current or another worktree, a branch or fixed-point diff, a supplied patch or gh pr view/gh pr diff output, or an existing pull request number or URL, including work not yet opened as a pull request. Prefer code-review instead when the user explicitly wants separate Standards and Spec reports.
- **harden-plan**: Iterate a plan or design document to a reviewed fixed point through tiered multi-model review, revising the file in place. Use when the user wants a plan, design doc, spec, RFC, or implementation plan reviewed, stress-tested, hardened, or iterated before execution, including phrases like 'review my plan', 'harden this design', 'is this plan ready', and before executing an implementation plan. Prefer audit-changes for code diffs, patches, and pull requests; prefer grilling when the user wants to be interrogated about their own thinking rather than have a document revised.
- **jury**: Use when a decision has more than one defensible answer and one model's judgement is not enough: "ask the jury", "get a second opinion from several models", a design choice between two workable options, or a skill that reaches a question it cannot settle on its own. Convenes independent blind jurors on one self-contained question and reports them as a decision card for the user to rule on.
- **review-loop**: Bound an audit-and-fix loop on a code change to a few rounds and end it, calling audit-changes for the finding half. Use when the user wants a branch, patch, or pull request reviewed and fixed, iterated until it is ready, or wants such a loop bounded, including "review this PR and fix what matters", "audit and fix this branch", and "once it lands, review it". Prefer audit-changes alone when the request is to audit, inspect, or report with no fixing.
- **review-protocol**: Shared lane brief and run script for audit-changes and harden-plan. Not invoked directly.
- **writing-for-humans**: Use when drafting or revising something the user will send, post, file, or keep: a PR body, a review, an issue, a status update, a summary, an email, a message to a colleague. Ordinary replies in this conversation keep their usual style.

`audit-changes`, `harden-plan` and `review-loop` read their reviewer briefs and run script
from `review-protocol`, so copy it alongside them. The audits send work to other agents
through your harness's own subagent tool.

## Install

Claude Code:

```
/plugin marketplace add edgarcosta/skillz
/plugin install skillz@skillz
```

Codex:

```
codex plugin marketplace add edgarcosta/skillz
codex plugin add skillz@skillz
```

Or copy folders from `skills/` into `~/.claude/skills/` or `~/.agents/skills/`.

## Contributing

Issues and pull requests are welcome. This repository is generated from my dotfiles, so I
apply an accepted change there and it comes back here with the next sync.

## License

MIT
