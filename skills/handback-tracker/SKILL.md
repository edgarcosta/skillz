---
name: handback-tracker
description: Use when a handback goes on a tracker (page or Markdown form) under the Handbacks rules in your global instructions; to resume a tracker recorded on a bead; or when the user says check or done about a tracker.
---

# Handback tracker

A handback is something the user must do because the session cannot: a command on their machine,
an action behind their credentials, or a decision. This skill covers both tracker forms: a
page and a Markdown file.

## State and commands

Keep the source JSON and generated files in the worktree's scratch directory, such as
`docs/superpowers/handback/`. In commands below, replace `STATE.json`, `PAGE.html`, `PAGE.md`
and `DBDIR` with absolute paths there. The script lives beside this skill under `scripts/`;
the commands write this skill's directory as `<this directory>`.

Use the writing-for-humans skill for page prose. For each command, Where names the machine
and shell. Why explains its effect and whether it changes anything. Success says what proves
it worked and who checks. Follow the Handbacks rules in your global instructions for runnable
commands and readable `tee` logs. Keep secret values off the hosted page.

The JSON fields are:

- `title` (two to four words), `goal`, `now` (whose move and one next action), `updated`;
  `steps`, `after`, `sessions`, `done`, `side_notes` (lists); `url` once published.
- Each step: stable `id` and positive integer `num`, `kind` (`command` or `decision`),
  `status` (`open` or `done`), `title`.
- Open command: `where`, `why`, `success`, `command`; optional `time` when over a minute.
  Finished command: `result`.
- Open decision: `recommendation` first, with the alternative in one sentence;
  `options` as objects with `id` and `label`; `replies` maps note ids to your answers.
  Optional `notes` maps the same ids to the user's note text for Markdown quotations.
  Finished decision: `answer`. Queue later decisions in `after` with owner `You`.
- `after`: objects with `num`, `owner` (`You`, `Me`, `You, maybe`), `title`, and optional
  `id` to preserve the number on promotion to a step. Commands wait until their inputs exist.
- `sessions`: objects with `session`, `owns`, `state`; shown when there is more than one.
  `done` and `side_notes`: text lists.

Run these for the command contract and argument help:

```bash
python3 -B <this directory>/scripts/handback-page.py --help
python3 -B <this directory>/scripts/handback-page.py render --help
python3 -B <this directory>/scripts/handback-page.py read --help
```

Each command exits **0** on success, including help. Exit **2** means invalid arguments,
invalid state, or input/output failure. On 2, correct the reported problem before publishing.

## Publish and read back

The session that owns the tracker, page or Markdown form, renders, publishes and reads back
its responses itself; reading `tee` logs may go to a worker.

1. When the repo has `.beads/`, read the bead with `bd show BEAD`.
   Reuse its recorded tracker and state file. With the Artifact tool, read an existing
   tracker with action `read` before republishing.
   If the state or numbers file is lost, rebuild it from the artifact read, keeping the
   page's `data-step` ids and `data-num` numbers. The numbers file maps number strings to
   ids, or `null` for after items without an id.
   For a Markdown tracker, recover from its `.md` file and the state path recorded on the
   bead. A rebuilt numbers file cannot restore reservations for removed steps.
2. Before changing an existing state, read the responses as described below. Write
   `STATE.json` using the fields above. Edit only the source JSON; render the page with:

   ```bash
   python3 -B <this directory>/scripts/handback-page.py render STATE.json -o PAGE.html
   ```

   Render checks and saves `<state stem>.numbers.json` beside the state file automatically.
   Keep this sidecar with the state across sessions; it reserves numbers even for removed steps.
3. Publish `PAGE.html` with the Artifact tool, explicitly declaring `capabilities: {db:{}}`.
   Keep the page private. On every republish, pass the `url` saved in state; omit `url` only
   on the first publish. If publishing is refused because the page changed, re-read the
   tracker, source state and responses. Render again and republish with the saved `url`;
   never merge the HTML.
   After the first publish, save its URL in state and record the URL and absolute state path
   once on the bead with `bd update BEAD --append-notes "Handback: URL; state: ABSOLUTE_PATH"`.
   In a repo without `.beads/`, give the user the URL and absolute state path in the reply.
   Hand the user the page link and the one next action.
4. Read responses when the user sends a word in chat, such as "check", "done" or "answered",
   and before every republish. **Never watch or poll the page.** Use ArtifactData action
   `list` (older harnesses: Artifact action `read_db` with `db_op: "list"`).
   Use a fresh `DBDIR` for each readback. Make these three calls, replacing `URL` with the
   saved artifact URL and `DBDIR` with the absolute directory path:

   ```json
   {"action":"list","url":"URL","collection":"ticks","out_dir":"DBDIR","query":{"limit":1000}}
   {"action":"list","url":"URL","collection":"picks","out_dir":"DBDIR","query":{"limit":1000}}
   {"action":"list","url":"URL","collection":"notes","out_dir":"DBDIR","query":{"limit":1000}}
   ```

   When a collection returns `next_cursor`, repeat its call with that cursor until no
   `next_cursor` remains. The files are `DBDIR/<collection>/<doc-id>.json`, each holding
   the document body; a missing collection directory is empty. Then run:

   ```bash
   python3 -B <this directory>/scripts/handback-page.py read STATE.json DBDIR
   ```

   Act on this report of current ticks, decision picks and unanswered notes. A tick confirms
   the current command was run; read its `tee` log to judge success before marking it done.
   Read both before asking the user anything; they never need to paste output.
   Command failures and surprises belong in chat.
   To ask for a re-run of an unchanged command, delete its `ticks` document with ArtifactData:

   ```json
   {"action":"delete","url":"URL","collection":"ticks","doc_id":"STEP_ID","if_version":VERSION}
   ```

   Replace `VERSION` with the tick's version from the ticks `list` result.
   With `out_dir`, that result reports each document's id and version. Drop `if_version` only if the tool
   says it is not accepted in this session. Older harnesses use Artifact:

   ```json
   {"action":"write_db","db_op":"delete","url":"URL","collection":"ticks","doc_id":"STEP_ID","if_version":VERSION}
   ```
5. Answer a decision note through `replies[note-id]`, leaving the decision open until the user
   picks an option or confirms your reading of their note. Record a settled answer and mark
   the step done. Republish the same artifact at every state change: a step finished, a new
   step ready, a decision answered, or a session idle. Update `now` and `updated` each time;
   repeat the response check and render steps. At completion, `now` reads
   "Done, nothing left for you"; keep side notes.

## Without the Artifact tool

Steps 1, 2 and 5 still apply. The user's chat messages are the responses in steps 2 and 5.
Key each reply by a short id you choose: put their quoted note in `notes[id]` and your answer
in `replies[id]`. The Markdown form shows the note above its reply.
In step 2, render the same state as Markdown:

```bash
python3 -B <this directory>/scripts/handback-page.py render --md STATE.json -o PAGE.md
```

In place of step 3, record the absolute Markdown and state paths once, when first written, with
`bd update BEAD --append-notes "Handback: ABSOLUTE_MD_PATH; state: ABSOLUTE_STATE_PATH"`.
Without `.beads/`, give the user both paths in the reply. Link the Markdown file by its absolute
path. Chat replaces step 4: the user replies with the command step number or their decision, note
or question. Read command logs, update state and render again at every state change.
