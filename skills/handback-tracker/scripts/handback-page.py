#!/usr/bin/env python3
"""Render a handback state as HTML or Markdown, or read its page responses.

Exit codes: 0 success; 2 invalid arguments, invalid state, or input/output failure.
"""

import argparse
import hashlib
import html
import json
import re
import sys
import unicodedata
from pathlib import Path


class Usage(Exception):
    pass


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def command_hash(command):
    return hashlib.sha256(command.encode("utf-8")).hexdigest()


def prose(value, path="state"):
    if isinstance(value, str):
        for char in value:
            if ord(char) > 127 and unicodedata.category(char)[0] in "PSZC":
                raise Usage("non-ASCII punctuation or spacing in " + path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            prose(item, "%s[%d]" % (path, index))
    elif isinstance(value, dict):
        for key, item in value.items():
            if key not in ("command", "notes"):
                prose(item, path + "." + key)


def validate(state):
    if not isinstance(state, dict):
        raise Usage("state must be an object")
    prose(state)
    for field in ("title", "goal", "now", "updated"):
        if not isinstance(state.get(field), str) or not state[field].strip():
            raise Usage("missing " + field)
    if not 2 <= len(state["title"].split()) <= 4:
        raise Usage("title must have two to four words")
    for field in ("steps", "after", "sessions", "done", "side_notes"):
        if not isinstance(state.get(field), list):
            raise Usage(field + " must be a list")
    ids, numbers = set(), set()
    for item in state["steps"] + state["after"]:
        if item.get("id") is not None:
            sid = item["id"]
            if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9_~:@+.-]{1,200}", sid) or sid in (".", ".."):
                raise Usage("step id must be a db document id")
            if sid in ids:
                raise Usage("duplicate step id: " + sid)
            ids.add(sid)
        num = item.get("num")
        if type(num) is not int or num < 1:
            raise Usage("step number must be a positive integer")
        if num in numbers:
            raise Usage("duplicate step number: %d" % num)
        numbers.add(num)
    decisions = 0
    for step in state["steps"]:
        sid = step.get("id")
        if sid is None:
            raise Usage("step id must be a db document id")
        if step.get("kind") not in ("command", "decision") or step.get("status") not in ("open", "done"):
            raise Usage("invalid kind or status for " + sid)
        if not isinstance(step.get("title"), str) or not step["title"].strip():
            raise Usage("missing title for " + sid)
        if step["status"] == "done":
            field = "result" if step["kind"] == "command" else "answer"
            if not isinstance(step.get(field), str) or not step[field].strip():
                raise Usage("done %s %s missing %s" % (step["kind"], sid, field))
        if step["kind"] == "command":
            if step["status"] == "open":
                for field in ("where", "why", "success", "command"):
                    if not isinstance(step.get(field), str) or not step[field].strip():
                        raise Usage("open command %s missing %s" % (sid, field))
        elif step["status"] == "open":
            decisions += 1
            if not step.get("recommendation") or not step.get("options"):
                raise Usage("open decision needs a recommendation and options: " + sid)
            option_ids = set()
            for option in step["options"]:
                if not isinstance(option.get("id"), str) or not option["id"].strip():
                    raise Usage("decision option id must be a non-empty string: " + sid)
                if not option.get("label") or option["id"] in option_ids:
                    raise Usage("decision options need distinct ids and labels: " + sid)
                option_ids.add(option["id"])
    if decisions > 1:
        raise Usage("more than one open decision")


def step_numbers(state, previous):
    if not isinstance(previous, dict):
        raise Usage("number snapshot must be an object")
    old_ids = {}
    for num, sid in previous.items():
        if not re.fullmatch(r"[1-9][0-9]*", num) or (sid is not None and
                (not isinstance(sid, str) or not sid or sid in old_ids)):
            raise Usage("invalid number snapshot")
        if sid is not None:
            old_ids[sid] = num
    numbers = previous.copy()
    for item in state["steps"] + state["after"]:
        num, sid = str(item["num"]), item.get("id")
        if sid in old_ids and old_ids[sid] != num:
            raise Usage("step number changed for " + sid)
        if num in numbers and numbers[num] is not None and numbers[num] != sid:
            raise Usage("step number %s belongs to %s" % (num, numbers[num]))
        if num not in numbers or numbers[num] is None:
            numbers[num] = sid
    return numbers


def esc(value):
    return html.escape(str(value), quote=True)


def ordered_steps(state, status):
    return sorted((s for s in state["steps"] if s["status"] == status), key=lambda s: s["num"])


def replies_html(step):
    return "".join('<div class="reply" data-note="%s"><div class="viewer-note" hidden>'
                   '<p>Your note:</p><p class="note-text"></p></div>'
                   '<p>Reply: %s</p></div>' % (esc(nid), esc(answer))
                   for nid, answer in step.get("replies", {}).items())


def step_html(step):
    sid = esc(step["id"])
    title = "%d. %s" % (step["num"], esc(step["title"]))
    if step["status"] == "done":
        result = step.get("result", "") if step["kind"] == "command" else step.get("answer", "")
        return '<div class="finished" data-step="%s" data-num="%d"><span>%s</span>: %s</div>' % (
            sid, step["num"], title, esc(result))
    head = '<details open class="step" data-step="%s" data-num="%d"><summary>%s<span class="ran" hidden> - Ran; output awaits review.</span></summary>' % (
        sid, step["num"], title)
    if step["kind"] == "command":
        body = "".join('<p><strong>%s:</strong> %s</p>' % (label, esc(step[field]))
                       for field, label in (("where", "Where"), ("why", "Why"), ("success", "Success")))
        if step.get("time"):
            body += '<p><strong>Time:</strong> %s</p>' % esc(step["time"])
        body += '<div class="command"><button type="button" class="copy">Copy command</button><pre>\n%s</pre></div>' % esc(step["command"])
        body += '<label class="tick" hidden><input type="checkbox" disabled data-cmd="%s"> I ran this</label>' % command_hash(step["command"])
    else:
        body = '<p><strong>Recommendation:</strong> %s</p>' % esc(step["recommendation"])
        body += '<div class="options">' + "".join(
            '<button type="button" disabled data-option="%s" aria-pressed="false">%s</button>' % (esc(o["id"]), esc(o["label"]))
            for o in step["options"]) + '</div><p class="pick" aria-live="polite">No option picked.</p>'
        body += '<div class="notes"></div>' + replies_html(step)
        body += '<form><label>Note or question<textarea disabled></textarea></label><button disabled type="button">Send note</button></form>'
    return head + '<div class="step-body">' + body + '</div></details>'


def render_html(state):
    after = "".join('<li value="%d" data-num="%d"%s><strong>%s:</strong> %s</li>' %
                    (item["num"], item["num"], ' data-step="%s"' % esc(item["id"]) if item.get("id") is not None else "",
                     esc(item["owner"]), esc(item["title"])) for item in state["after"])
    sessions = ""
    if len(state["sessions"]) > 1:
        sessions = '<section><h2>Sessions</h2><table><thead><tr><th>Session</th><th>Owns</th><th>State</th></tr></thead><tbody>'
        for row in state["sessions"]:
            sessions += '<tr>' + "".join('<td>%s</td>' % esc(row[key]) for key in ("session", "owns", "state")) + '</tr>'
        sessions += '</tbody></table></section>'
    values = {
        "TITLE": esc(state["title"]), "GOAL": esc(state["goal"]),
        "NOW": esc(state["now"]), "UPDATED": esc(state["updated"]),
        "OPEN": "".join(step_html(s) for s in ordered_steps(state, "open")),
        "AFTER": after, "SESSIONS": sessions,
        "DONE": "".join(step_html(s) for s in ordered_steps(state, "done")) +
                "".join('<p>%s</p>' % esc(text) for text in state["done"]),
        "SIDE_NOTES": "".join('<li>%s</li>' % esc(text) for text in state["side_notes"]),
    }
    template = (Path(__file__).resolve().parent.parent / "template.html").read_text(encoding="utf-8")
    return re.sub(r"@@([A-Z_]+)@@", lambda m: values[m[1]], template)


def md_text(value):
    text = re.sub(r"([\\`*_\[\]|<>~])", r"\\\1", str(value))
    text = re.sub(r"(?m)^([ \t]*)(#{1,6}|[-+])(?=[ \t]|$)", r"\1\\\2", text)
    text = re.sub(r"(?m)^([ \t]*\d+)([.)])(?=[ \t]|$)", r"\1\\\2", text)
    return re.sub(r"(?m)^([ \t]*)(-+|=+)([ \t]*)$", r"\1\\\2\3", text)


def render_md(state):
    lines = ["# " + md_text(state["title"]), "", md_text(state["goal"]), "",
             "Now: " + md_text(state["now"]), "", "Updated: " + md_text(state["updated"]), "", "## Your turn", ""]
    for step in ordered_steps(state, "open"):
        lines += ["### %d. %s" % (step["num"], md_text(step["title"])), ""]
        if step["kind"] == "command":
            for field, label in (("where", "Where"), ("why", "Why"), ("success", "Success"), ("time", "Time")):
                if step.get(field):
                    lines += [label + ": " + md_text(step[field]), ""]
            command = step["command"]
            fence = "`" * max(3, max((len(m[0]) + 1 for m in re.finditer(r"`+", command)), default=0))
            lines += [fence + "bash", command + ("" if command.endswith("\n") else "\n") + fence, ""]
            lines += ["Reply in chat with the step number.", ""]
        else:
            lines += ["Recommendation: " + md_text(step["recommendation"]), ""]
            lines += ["- %s: %s" % (md_text(o["id"]), md_text(o["label"])) for o in step["options"]]
            lines += ["", "Reply in chat with your choice, note or question.", ""]
            for nid, answer in step.get("replies", {}).items():
                if nid in step.get("notes", {}):
                    lines += ["> " + md_text(step["notes"][nid]).replace("\n", "\n> "), ""]
                lines += ["Reply: " + md_text(answer), ""]
    lines += ["## After that", ""]
    for item in state["after"]:
        lines += ["- Step %d: %s: %s" % (item["num"], md_text(item["owner"]), md_text(item["title"]))]
    lines += [""]
    if len(state["sessions"]) > 1:
        lines += ["## Sessions", "", "| Session | Owns | State |", "| --- | --- | --- |"]
        for row in state["sessions"]:
            lines += ["| " + " | ".join(md_text(row[k]).replace("\n", " ") for k in ("session", "owns", "state")) + " |"]
        lines += [""]
    lines += ["## Done so far", ""]
    for step in ordered_steps(state, "done"):
        result = step.get("result", "") if step["kind"] == "command" else step.get("answer", "")
        lines += ["- %d. %s: %s" % (step["num"], md_text(step["title"]), md_text(result))]
    lines += ["- " + md_text(text) for text in state["done"]]
    lines += ["", "## Side notes", ""] + ["- " + md_text(text) for text in state["side_notes"]]
    return "\n".join(lines) + "\n"


def collection(db, name):
    folder = db / name
    if not folder.exists():
        return {}
    if not folder.is_dir():
        raise Usage(str(folder) + " must be a collection directory")
    fields = {"ticks": {"done": bool, "cmd": str}, "picks": {"option": str},
              "notes": {"step": str, "text": str}}[name]
    rows = {}
    for path in sorted(folder.glob("*.json")):
        body = load(path)
        if not isinstance(body, dict):
            raise Usage(str(path) + ": body must be an object")
        for field, kind in fields.items():
            if field not in body:
                raise Usage(str(path) + ": missing " + field)
            if type(body[field]) is not kind:
                raise Usage(str(path) + ": invalid " + field)
        rows[path.stem] = body
    return rows


def read_responses(state, db):
    if not db.is_dir():
        raise Usage(str(db) + " must be a response directory")
    ticks, picks, notes = (collection(db, name) for name in ("ticks", "picks", "notes"))
    lines = []
    for step in sorted(state["steps"], key=lambda s: s["num"]):
        sid = step["id"]
        if step["kind"] == "command":
            if step["status"] == "done":
                lines.append("%d. %s: done" % (step["num"], sid))
                continue
            tick = ticks.get(sid, {})
            current = tick.get("cmd") == command_hash(step.get("command", ""))
            ticked = tick.get("done") is True and current
            lines.append("%d. %s: %s%s" % (step["num"], sid, "ticked" if ticked else "not ticked",
                                         " (stale command hash)" if tick and not current else ""))
        else:
            if step["status"] == "done":
                lines.append("%d. %s: answer %s" % (step["num"], sid, step["answer"].replace("\n", "\n    ")))
            else:
                pick = picks.get(sid, {}).get("option")
                current = any(option["id"] == pick for option in step.get("options", []))
                answer = str(pick) if current else "none"
                if pick is not None and not current:
                    answer += " (stale option %s)" % pick
                lines.append("%d. %s: pick %s" % (step["num"], sid, answer))
            for nid, note in sorted(notes.items(), key=lambda item: item[1].get("at", "")):
                if note.get("step") == sid and nid not in step.get("replies", {}):
                    lines.append("  Unanswered note %s: %s" % (nid, note.get("text", "").replace("\n", "\n    ")))
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        'Publish HTML with capabilities {"db":{}}. Read takes DBDIR from ArtifactData list out_dir: '
        'ticks/, picks/ and notes/ hold doc-id.json bodies; a missing collection is empty. '
        'Ticks need bool done and string cmd, picks string option, notes string step and text. '
        'State after items have num/owner/title and an optional id to keep their number when promoted to steps. '
        'Sessions have session/owns/state; '
        'done and side_notes are lists of text. Decision replies map note ids to answers; '
        'optional notes map the same ids to quoted text for Markdown.'))
    subs = parser.add_subparsers(dest="action", required=True)
    render = subs.add_parser("render", help="render HTML, or Markdown with --md", description=(
        'Check stable ids and numbers against <state stem>.numbers.json beside the state, '
        'then save cumulative number reservations there after a successful render.'))
    render.add_argument("state")
    render.add_argument("-o", "--output", required=True)
    render.add_argument("--md", action="store_true")
    read = subs.add_parser("read", help="report done commands, current ticks, decision picks and unanswered notes")
    read.add_argument("state")
    read.add_argument("dbdir", metavar="DBDIR")
    args = parser.parse_args()
    try:
        state = load(args.state)
        validate(state)
        if args.action == "read":
            print(read_responses(state, Path(args.dbdir)), end="")
        else:
            snapshot = Path(args.state).with_suffix(".numbers.json")
            numbers = step_numbers(state, load(snapshot) if snapshot.exists() else {})
            content = render_md(state) if args.md else render_html(state)
            Path(args.output).write_text(content, encoding="utf-8")
            snapshot.write_text(json.dumps(numbers, indent=2) + "\n", encoding="utf-8")
    except (Usage, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print("handback-page: " + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
