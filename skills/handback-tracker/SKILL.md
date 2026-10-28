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

Use the writing-for-humans skill for all authored prose in either tracker form, including jury cards;
keep quoted juror lines and source text verbatim.
For each command, Where names the machine and shell. Why explains its effect and whether it changes
anything. Success says what proves
it worked and who checks. Follow the Handbacks rules in your global instructions for runnable
commands and readable `tee` logs. Keep secret values off the hosted page.

The JSON fields are:

- `title` (two to four words), `goal`, `now` (whose move and one next action), `updated`;
  `steps`, `after`, `sessions`, `done`, `side_notes` (lists); `url` once published.
- Each step: stable `id` and positive integer `num`, `kind` (`command` or `decision`),
  `status` (`open` or `done`), `title`.
- Open command: `where`, `why`, `success`, `command`; optional `time` when over a minute.
  Finished command: `result`.
- Open decision: `recommendation`, with the alternative in one sentence;
  `options` as objects with `id` and `label`; `replies` maps note ids to your answers.
  Optional `context` explains the choice without chat context.
  Optional `notes` maps the same ids to the user's note text for Markdown quotations.
  Optional `question` keeps the exact source text on the card, after Context and before Options.
  Optional `ruling` records the decision taken; `built` is a list describing what used it, with complete URLs.
  Both appear before the response controls. A provisional ruling leaves the user's choice unselected.
  Finished decision: `answer`. Queue later decisions in `after` with owner `You`.
- Optional decision `jury`: nonempty `lines` of juror objects and optional `agreement`,
  one authored line with its count. Each juror has nonempty `juror` and `model` display strings;
  juror names are unique within a decision. Optional `pick` and `reason` keep complete PICK and
  REASON source lines.
  Optional `label` is the source label. A string requires matching labelled prefixes;
  null permits bare prefixes for one conversion target. Each run requires distinct source labels.
  An absent `label` uses the decision's id; render also accepts bare prefixes
  on such a decision, as older states have them.
  Converter diagnostics use optional `status`; render rejects roster-only lines.
  Backing is derived from complete evidence pairs and the decision's current options.
  Options added from proposals carry `proposed: true`; proposer names are derived too.
  Conversion writes derived `support` entries with `juror`, resolved `option` or null,
  `conditional` and `outcome`, using the same interpretation as rendering.
- Optional `appendix`: objects with nonempty `title` and source `text`, shown after Side notes.
  HTML keeps each source in a closed disclosure; Markdown uses text fences.
- Optional `groups`: objects with nonempty `title` and nonempty `steps` lists of step ids.
  Members are adjacent in numeric order, including done steps, and occur in only one group.
  Only groups with open members have headings; other open runs read Other steps.
- `after`: objects with `num`, `owner` (`You`, `Me`, `You, maybe`), `title`, and optional
  `id` to preserve the number on promotion to a step. Commands wait until their inputs exist.
- `sessions`: objects with `session`, `owns`, `state`; shown when there is more than one.
  `done` and `side_notes`: text lists.

Ordinary decisions put the recommendation first; jury decisions put Mine after the juror lines,
with one decision step per label.

Run these for the command contract and argument help:

```bash
python3 -B <this directory>/scripts/handback-page.py --help
python3 -B <this directory>/scripts/handback-page.py render --help
python3 -B <this directory>/scripts/handback-page.py read --help
python3 -B <this directory>/scripts/handback-page.py jury --help
```

Each command exits **0** on success, including help. Exit **2** means invalid arguments,
invalid state, or input/output failure. On 2, correct the reported problem before publishing.

### Convert jury replies

Before dispatching the jury, give each labelled question a source label such as F5.
Ask jurors to open with every PICK and REASON pair, labelled unless the question is bare, before any argument.
Set `jury.label` when the page id differs from the source label, or to null for a bare single question;
separate runs may reuse a source label with distinct page ids.
Add jury decisions to the state only when every reply or failure file is ready, then convert at once.
Author each decision's title, context, recommendation, options, and stable number from the question file.
Each jury decision to convert (a target) needs at least one authored option.
For a label answered only by `none` or `new:`, author an option with id `none`.
Each target's `jury.lines` supplies the same juror/model roster, with no `pick`, `reason` or `status` yet.
Check the authored fields against the exact question sent to the panel before conversion.

```bash
python3 -B <this directory>/scripts/handback-page.py jury CARD.json \
  --question QUESTION.txt --sentinel END-OF-JURY-REPLY \
  --reply amber=/absolute/path/reply-a.txt --reply blue=/absolute/path/reply-b.txt -o STATE.json
```

Supply every roster juror exactly once through `--reply juror=/absolute/path/reply.txt`
or `--failed juror=/absolute/path/failure.txt`.
A failure file starts with `no reply, exit <integer>`, followed by the command and last error line.
The converter copies it as a diagnostic; it runs no command.
Reply filenames carry no meaning. Labels in `PICK F5:` and `REASON F5:` name source labels.
Only the opening block of PICK, REASON, and blank lines supplies evidence; argument text stays quoted.
Labels and prefixes are case sensitive. The last nonblank reply line must match the chosen sentinel.
Missing lines, truncation, and unmatched picks remain visible, with no inferred vote.
Complete `new:` proposals reuse an identical option label or receive the first unused letter from A to Z.

Conversion preserves other steps and existing appendix sources, puts the exact question on every target card,
and appends the full replies to the appendix. Source-labelled appendix titles name the decisions and their source labels.
Exit 0 means the draft was written, including incomplete replies; exit 2 leaves an existing output unchanged.
A redo starts from the roster-only scaffold; an already converted state has no targets.
To add a run, copy the tracker state to a new `CARD.json`, add the roster-only decisions there,
and pass the tracker state path to `-o`; a redo reuses that `CARD.json`.
Conversion leaves page responses and number reservations to the usual read and render commands.

After conversion, read the replies, then write each decision's `agreement` and revise its
`recommendation` in the output state before rendering. Omit agreement unless every replying juror makes that point.
When the diagnostic names a reply, leave the reply unchanged and show the user the diagnostic with that reply.

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
   the current command was run. Judge success from its `tee` log, or the live remote state
   for push or PR steps, before marking it done.
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
path. Chat replaces step 4: the user replies with the step number and, for a decision, their
choice, note or question. Read command logs, update state and render again at every state change.
