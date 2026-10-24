---
name: review-protocol
description: Shared lane brief and run script for audit-changes and harden-plan. Not invoked directly.
disable-model-invocation: true
disable-slash-command: true
---

# Review Protocol

Finders get `finder.md` and validators get `validator.md`, assembled into a lane prompt by `python3 <this directory>/scripts/review-run.py brief <run-dir> --lane <name> --type finder|validator --skill <skill>`. The order is shared brief, skill addendum, optional lens, snapshot or document copy, then declared source files, applicable raw rule files, and the candidate file for validators. Audit callers use repeated `--source <kind>=<file>`, repeated `--rules <file>`, and validator-only `--candidate <file>`. Source kinds are `pr-title`, `pr-body`, `pr-thread`, and `issue`. The first lane brief copies source bytes unchanged under `<run-dir>/sources/` and records their original paths, kinds, hashes, and stored paths in `<run-dir>/sources.json`. Each lane receipt at `lanes/<lane>.receipt.json` references its inputs and records their hashes, stored-copy paths, template and snapshot evidence, and the final prompt hash. Repeat the same `--source` arguments for each lane: the script compares source kinds and original paths, then reuses the frozen run copies. Do not pass the stored-copy paths. The orchestrator records URL or issue linkage and capture time separately with `review-run log`; source files remain untouched. Candidate files contain one verbatim candidate section from the original finder output; retain the full finder output separately. Normalization and deduplication are routing bookkeeping only.

For audit prompts, `--context` and `--doc` are rejected. Finders reject `--candidate`; validators require it. `verify-brief <run-dir> --lane <name>` checks copied inputs and the prompt against the lane receipt. Exit 1 from `verify-brief` or `dispatch` means integrity verification failed: discard the lane result and log a coverage gap. Exit 2 from `brief` means an input is missing or invalid. `dispatch <run-dir> --lane <name>` verifies the prompt and prints a fixed, short instruction to read and follow the complete prompt at its absolute path. That generated instruction is the entire worker task. Dispatch it unchanged; prompt contents and extra context do not belong in argv or a wrapper. Each finder and validator starts in a fresh context with no inherited conversation and may inspect repository evidence required by its lens. Verify after the worker returns and before counting its result. Local hashes prove recorded bytes and assembly integrity; they do not prove remote authenticity or describe other harness context.

`--context` and `--doc` remain available to callers such as harden-plan. Audit callers use the declared source, rule, and candidate inputs instead.

A skill that uses this protocol keeps its own `finder-addendum.md` beside its `SKILL.md`, a `validator-addendum.md` when it runs validator lanes, and one file per lens under `lenses/`. The addendum carries the skill's target-specific rejects and candidate fields; the brief carries what every lane shares.

The script's other subcommands are `new`, `snapshot`, `recheck`, `copy`, `write`, `log`, `verify-brief`, `dispatch` and `should-stop`; each skill names the ones it uses. `copy` and `write` exit 3 without overwriting the document when its current hash differs from the last recorded hash. Exit 2 from any subcommand means a missing file or bad input, named on stderr: the calling skill stops and reports it rather than assembling a prompt by hand.
