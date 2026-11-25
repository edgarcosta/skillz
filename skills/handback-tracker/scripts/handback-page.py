#!/usr/bin/env python3
"""Render a handback state, convert jury replies, or read page responses.

Exit codes: 0 success; 2 invalid arguments, invalid state, or input/output failure.
"""

import argparse
import hashlib
import html
import json
import os
import re
import sys
import tempfile
import unicodedata
from pathlib import Path
from urllib.parse import quote


REPO = r"[A-Za-z0-9][A-Za-z0-9-]*/(?!\.{1,2}(?:#|$))[A-Za-z0-9_.][A-Za-z0-9_.-]*"
LINK = re.compile(
    r"\[(?P<label>[^\]\n]*)\]\((?P<target>(?:[^\s<>()]|\([^\s<>()]*\))+)\)"
    r"|<(?P<autolink>https?://[^\s<>]+)>"
    r"|(?P<url>https?://[^\s<>\"'\x60]+)"
    r"|(?<![\w./#&=?%+-])(?:(?P<repo>" + REPO + r"))?#(?P<number>[0-9]+)(?![\w])")


class Usage(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, "handback-page: " + message + "\n")


def load(path):
    try:
        return json.loads(read_source(path))
    except ValueError as error:
        raise Usage("invalid JSON in %s: %s" % (path, error)) from error


def read_source(path):
    try:
        with Path(path).open(encoding="utf-8", newline="") as source:
            return source.read()
    except (OSError, UnicodeError) as error:
        raise Usage("cannot read %s: %s" % (path, error)) from error


def command_hash(command):
    # Hash the exact text, whitespace included: any edit to a command must void its earlier tick.
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
            if key == "jury" and isinstance(item, dict):
                prose(item.get("agreement", ""), path + ".jury.agreement")
                for row in item["lines"]:
                    for field in ("juror", "model"):
                        prose(row[field], path + ".jury." + field)
            elif key == "appendix" and isinstance(item, list):
                for source in item:
                    prose(source["title"], path + ".appendix.title")
            elif key not in ("command", "notes", "question") and not (key == "label" and value.get("proposed") is True):
                prose(item, path + "." + key)


def source_value(line, prefix, label=None):
    label_pattern = re.escape(label) if label is not None else r"[^\s]+?"
    match = re.fullmatch(r"[ \t]*" + prefix + r"(?:[ \t]+(" + label_pattern + r"))?:([^\r\n]*)", line)
    if match:
        return match[1], match[2].strip()
    return source_value(line, prefix) if label is not None else None


def jury_label(step):
    return step["jury"].get("label", step["id"])


def doc_id(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_~:@+.-]{1,200}", value) is not None and value not in (".", "..")


def validate(state, render=False):
    if not isinstance(state, dict):
        raise Usage("state must be an object")
    for field in ("title", "goal", "now", "updated"):
        if not isinstance(state.get(field), str) or not state[field].strip():
            raise Usage("missing " + field)
    if not 2 <= len(state["title"].split()) <= 4:
        raise Usage("title must have two to four words")
    for field in ("steps", "after", "sessions", "done", "side_notes", "appendix", "groups"):
        if not isinstance(state.get(field, []), list) or (field not in state and field not in ("appendix", "groups")):
            raise Usage(field + " must be a list")
    if "repo" in state and (not isinstance(state["repo"], str) or not re.fullmatch(REPO, state["repo"])):
        raise Usage("repo must be owner/name")
    ids, numbers = set(), set()
    for item in state["steps"] + state["after"]:
        if not isinstance(item, dict):
            raise Usage("step must be an object")
        if item.get("id") is not None:
            sid = item["id"]
            if not doc_id(sid):
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
    for step in state["steps"]:
        sid = step.get("id")
        if sid is None:
            raise Usage("step id must be a db document id")
        if "priority" in step and (type(step["priority"]) is not int or step["priority"] < 1):
            raise Usage("step priority must be a positive integer: " + sid)
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
            continue
        if "context" in step and not isinstance(step["context"], str):
            raise Usage("decision context must be text: " + sid)
        for field in ("question", "ruling"):
            if field in step and not isinstance(step[field], str):
                raise Usage("decision %s must be text: %s" % (field, sid))
        if "built" in step and (not isinstance(step["built"], list) or
                               any(not isinstance(text, str) for text in step["built"])):
            raise Usage("decision built must be a list of text: " + sid)
        if "jury" in step and not step.get("options"):
            raise Usage("jury decision needs options: " + sid)
        if step["status"] == "open":
            if not isinstance(step.get("recommendation"), str) or not step["recommendation"].strip() or not step.get("options"):
                raise Usage("open decision needs a recommendation and options: " + sid)
        if "options" in step:
            if not isinstance(step["options"], list):
                raise Usage("decision options must be a list: " + sid)
            option_ids = set()
            for option in step["options"]:
                if not isinstance(option, dict) or not isinstance(option.get("id"), str) or not option["id"].strip():
                    raise Usage("decision option id must be a non-empty string: " + sid)
                if not isinstance(option.get("label"), str) or not option["label"].strip() or option["id"] in option_ids:
                    raise Usage("decision options need distinct ids and labels: " + sid)
                if "proposed" in option and type(option["proposed"]) is not bool:
                    raise Usage("option proposed must be a boolean: " + sid)
                option_ids.add(option["id"])
        if "jury" in step:
            jury = step["jury"]
            if not isinstance(jury, dict) or not isinstance(jury.get("lines"), list) or not jury["lines"]:
                raise Usage("jury lines must be a nonempty list: " + sid)
            label = jury_label(step)
            if label is not None and not doc_id(label):
                raise Usage("jury label must be a source label or null: " + sid)
            if "agreement" in jury and (not isinstance(jury["agreement"], str) or len(jury["agreement"].splitlines()) > 1):
                raise Usage("jury agreement must be one line: " + sid)
            jurors = set()
            for row in jury["lines"]:
                if not isinstance(row, dict):
                    raise Usage("juror must be an object: " + sid)
                for field in ("juror", "model"):
                    if not isinstance(row.get(field), str) or not row[field].strip():
                        raise Usage("juror needs nonempty " + field + ": " + sid)
                if row["juror"] in jurors:
                    raise Usage("duplicate juror: " + row["juror"])
                jurors.add(row["juror"])
                for field in ("pick", "reason"):
                    if field not in row:
                        continue
                    parsed = source_value(row[field], field.upper(), label) if isinstance(row[field], str) else None
                    if parsed is None:
                        raise Usage("invalid %s source line for %s: %s" % (field, row["juror"], sid))
                    if step["status"] == "open" and parsed[0] != label and (parsed[0] is not None or "label" in jury):
                        raise Usage("cross-labelled %s for %s: %s" % (field, row["juror"], sid))
                if "status" in row:
                    status = row["status"]
                    if not isinstance(status, str) or (status not in ("truncated", "no pick line; no reason line") and
                                                       not status.startswith("no reply, exit ")):
                        raise Usage("invalid jury status for " + row["juror"])
                    if status == "truncated" and ("pick" in row or "reason" in row):
                        raise Usage("truncated juror cannot hold evidence: " + row["juror"])
                if render and not any(field in row for field in ("pick", "reason", "status")):
                    raise Usage("jury decision %s is not converted yet" % sid)
    for item in state.get("appendix", []):
        if not isinstance(item, dict) or not isinstance(item.get("title"), str) or not item["title"].strip() or not isinstance(item.get("text"), str):
            raise Usage("appendix items need a nonempty title and source text")
    step_ids = {step["id"] for step in state["steps"]}
    positions = {step["id"]: index for index, step in enumerate(ordered_steps(state, "open"))}
    grouped = set()
    for group in state.get("groups", []):
        if not isinstance(group, dict) or not isinstance(group.get("title"), str) or not group["title"].strip():
            raise Usage("group needs a nonempty title")
        members = group.get("steps")
        if not isinstance(members, list) or not members:
            raise Usage("group steps must be a nonempty list")
        for sid in members:
            if not isinstance(sid, str) or sid not in step_ids or sid in grouped:
                raise Usage("missing or repeated group step: " + str(sid))
            grouped.add(sid)
        indices = sorted(positions[sid] for sid in members if sid in positions)
        if indices and indices[-1] - indices[0] + 1 != len(indices):
            raise Usage("open group steps must be adjacent in display order: " + group["title"])
    prose(state)


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


def linked_text(value, repo, markdown=False):
    text = md_text if markdown else esc
    value = str(value)
    parts, end = [], 0
    for match in LINK.finditer(value):
        parts.append(text(value[end:match.start()]))
        label = match["label"]
        url = match["target"] or match["autolink"] or match["url"]
        tail = ""
        if match["url"]:
            while True:
                previous = url
                url = url.rstrip(".,;:!?*]")
                while url.endswith(")") and url.count(")") > url.count("("):
                    url = url[:-1]
                if url == previous:
                    break
            tail = match[0][len(url):]
        if match["target"] and not url.startswith(("http://", "https://")):
            reference = re.fullmatch(r"(?:(?P<repo>" + REPO + r"))?#(?P<number>[0-9]+)", url)
            if not reference or not (reference["repo"] or repo):
                parts.append(text(match[0]))
                end = match.end()
                continue
            url = "https://github.com/%s/issues/%s" % (reference["repo"] or repo, reference["number"])
        if not url:
            target_repo = match["repo"] or repo
            if not target_repo:
                parts.append(text(match[0]))
                end = match.end()
                continue
            url = "https://github.com/%s/issues/%s" % (target_repo, match["number"])
        if label is None:
            label = match["autolink"] or (url if match["url"] else match[0])
        url = quote(url, safe="/:?#[]@!$&'*+,;=%-._~")
        parts.append(("[%s](%s)" % (text(label), url) if markdown else
                      '<a href="%s">%s</a>' % (esc(url), text(label))) + text(tail))
        end = match.end()
    parts.append(text(value[end:]))
    return "".join(parts)


def text_blocks(value):
    if "\n" not in value:
        return [(False, [value])]
    blocks = []
    current = None
    for line in value.splitlines():
        if not line.strip():
            current = None
            continue
        bullet = line.startswith("- ")
        if current is None or bullet != current[0]:
            current = (bullet, [])
            blocks.append(current)
        current[1].append(line[2:] if bullet else line)
    return blocks


def prose_html(value, text, label="", class_name=""):
    parts = []
    prefix = '<strong>%s:</strong> ' % esc(label) if label else ""
    for bullet, lines in text_blocks(value):
        if bullet:
            if prefix:
                parts.append('<p>%s</p>' % prefix.rstrip())
            parts.append('<ul>' + ''.join('<li>%s</li>' % text(line) for line in lines) + '</ul>')
        else:
            parts.append('<p>%s%s</p>' % (prefix, text("\n".join(lines))))
        prefix = ""
    body = ''.join(parts)
    if class_name:
        if len(parts) == 1 and body.startswith('<p>'):
            return '<p class="%s">%s' % (esc(class_name), body[3:])
        return '<div class="%s">%s</div>' % (esc(class_name), body)
    return body


def prose_md(value, text, label=""):
    parts = []
    prefix = label + ": " if label else ""
    for bullet, lines in text_blocks(value):
        if bullet:
            if prefix:
                parts.append(prefix.rstrip())
            parts.append("\n".join("- " + text(line) for line in lines))
        else:
            parts.append(prefix + text("\n".join(lines)))
        prefix = ""
    return "\n\n".join(parts)


def ordered_steps(state, status):
    steps = sorted((s for s in state["steps"] if s["status"] == status), key=lambda s: s["num"])
    if status == "open":
        steps.sort(key=lambda s: s.get("priority", float("inf")))
    return steps


def jury_rows(step):
    rows = []
    label = jury_label(step)
    for row in sorted(step["jury"]["lines"], key=lambda row: row["juror"]):
        option, conditional, outcome = None, False, ""
        if "status" in row:
            outcome = "no reply" if row["status"].startswith("no reply, exit ") else row["status"]
        elif "pick" not in row:
            outcome = "no pick line" + ("; no reason line" if "reason" not in row else "")
        elif "reason" not in row or not source_value(row["reason"], "REASON", label)[1]:
            outcome = "no reason line"
        else:
            pick = source_value(row["pick"], "PICK", label)[1]
            authored = [candidate for candidate in step["options"] if not candidate.get("proposed")]
            exact = next((candidate for candidate in authored if candidate["id"] == pick), None)
            if exact is not None:
                option = exact["id"]
            elif pick.startswith("new:") and pick[4:].strip():
                option = next((candidate["id"] for candidate in step["options"]
                               if candidate["label"] == pick[4:].strip()), None)
            else:
                for candidate in authored:
                    oid = candidate["id"]
                    match = re.fullmatch(re.escape(oid) + r"(?: if |[:,;]\s*| - )(.+)", pick)
                    if match:
                        option = oid
                        conditional = bool(re.search(
                            r"\b(?:if|provided|condition(?:ed|al) on|on condition|once|when|subject to)\b"
                            r"|\bwith\b.*\b(?:confirmed|verified)\b", match[1], re.I))
                        conditional = conditional or pick.startswith(oid + " if ")
                        break
            if option is None:
                outcome = "abstained" if pick == "none" and not any(o["id"] == "none" for o in step["options"]) else "unmatched pick"
        rows.append((row, option, conditional, outcome))
    return rows


def jury_support(step):
    support = {entry["juror"]: entry for entry in step["jury"].get("support", [])}
    rows = []
    for row, option, conditional, outcome in jury_rows(step):
        entry = support.get(row["juror"])
        if entry is not None and entry.get("outcome") != "unmatched pick":
            option, conditional, outcome = entry["option"], entry["conditional"], entry["outcome"]
        rows.append((row, option, conditional, outcome))
    return rows


def recommendation_parts(step):
    value = step.get("recommendation", "").strip()
    value = re.sub(r"^Mine(?: \(no vote\))?:\s*", "", value, count=1, flags=re.I)
    choice = re.sub(r"^(?:I recommend|Recommend|Recommended|Recommendation:|Use|Pick|Choose|"
                    r"Option|Provisional|Panel majority:)\s+", "", value, count=1, flags=re.I)
    for option in step.get("options", []):
        match = re.match(re.escape(option["id"]) + r"(?=$|[\s:;,.-])", choice)
        if match:
            detail = value if choice[match.end():].strip(" \t\r\n:;,.-") else ""
            return option["id"], detail
    return None, value


def recommendation_marker(step):
    value = step.get("recommendation", "").strip()
    if re.match(r"^Mine \(no vote\):", value, re.I):
        return "Mine"
    if re.match(r"^Panel majority:", value, re.I):
        return "panel majority"
    return "recommended"


def juror_name(row):
    name = row["juror"]
    return name.capitalize() if name.islower() else name


def backing_text(step, option, rows, text, conditional_text):
    backers = [(row, conditional) for row, oid, conditional, outcome in rows if oid == option["id"]]
    captions = []
    if option.get("proposed") and backers:
        captions.append("Proposed by: " + ", ".join(text(juror_name(row)) for row, conditional in backers))
    elif backers:
        captions.append(", ".join(conditional_text(row) if conditional else text(juror_name(row))
                        for row, conditional in backers))
    if recommendation_parts(step)[0] == option["id"]:
        captions.append(recommendation_marker(step))
    return "; ".join(captions)


def no_backing(rows, text):
    outcomes = [text(row["juror"]) + ": " + text(outcome) for row, oid, conditional, outcome in rows if oid is None]
    return "No option backed: " + "; ".join(outcomes) if outcomes else ""


def majority_caption(rows):
    replying = sum(outcome != "no reply" for row, oid, conditional, outcome in rows)
    counts = {}
    for row, oid, conditional, outcome in rows:
        if oid is not None and not conditional:
            counts[oid] = counts.get(oid, 0) + 1
    for oid, count in counts.items():
        if count > replying / 2:
            return "Majority: %s, %d of %d replying" % (oid, count, replying)
    return ""


RULING_GUIDANCE = ("Pick the ruled option to confirm, another option to replace it, or send a note; "
                   "then say check in the conversation that owns this page.")


def options_html(step, text, rows=()):
    body = '<div class="options">'
    for option in step.get("options", []):
        caption = backing_text(step, option, rows, text,
            lambda row: '<span title="%s">%s (if ...)</span>' % (esc(row["pick"]), text(juror_name(row))))
        label_text = text if step["status"] == "done" else esc
        label = "%s: %s" % (esc(option["id"]), label_text(option["label"]))
        body += '<div>' + (label if step["status"] == "done" else
            '<button type="button" disabled data-option="%s" aria-pressed="false">%s</button>' % (esc(option["id"]), label))
        if caption:
            body += '<span class="backing"> -- %s</span>' % caption
        body += '</div>'
    body += '</div>'
    detail = recommendation_parts(step)[1]
    if detail:
        body += prose_html(detail, text, "Mine (no vote)" if recommendation_marker(step) == "Mine" else "Recommendation")
    return body


def jury_html(step, text):
    rows = jury_support(step)
    body = options_html(step, text, rows)
    if majority_caption(rows):
        body += '<p>%s</p>' % esc(majority_caption(rows))
    if no_backing(rows, text):
        body += '<p>%s</p>' % no_backing(rows, text)
    body += '<h4>Juror advice</h4>'
    for row, oid, conditional, outcome in rows:
        body += '<div class="jury-line"><p>%s (%s)</p>' % (text(row["juror"]), text(row["model"]))
        for field in ("pick", "reason", "status"):
            if field in row:
                body += '<pre>\n%s</pre>' % esc(row[field])
        if outcome:
            body += '<p>%s</p>' % esc(outcome)
        body += '</div>'
    if step["jury"].get("agreement"):
        body += '<p><strong>Agreement:</strong> %s</p>' % text(step["jury"]["agreement"])
    return body


def open_entries(state):
    steps = ordered_steps(state, "open")
    groups = {sid: index for index, group in enumerate(state.get("groups", [])) for sid in group["steps"]}
    visible = any(step["id"] in groups for step in steps)
    numbers = {step["id"]: step["num"] for step in state["steps"]}
    previous = object()
    for step in steps:
        group = groups.get(step["id"])
        if visible and group != previous:
            if group is None:
                yield "Other steps", step["num"], None
            else:
                title = state["groups"][group]["title"]
                num = min(numbers[sid] for sid in state["groups"][group]["steps"])
                yield title, num, None
        yield None, step["num"], step
        previous = group


def fence_for(text, minimum=3):
    return "`" * max(minimum, max((len(m[0]) + 1 for m in re.finditer(r"`+", text)), default=0))


def fenced(text, language="text"):
    fence = fence_for(text)
    return [fence + language, text + ("" if text.endswith("\n") else "\n") + fence, ""]


def md_code(text):
    delimiter = fence_for(text, 1)
    return delimiter + " " + text + " " + delimiter if text.startswith(("`", " ")) or text.endswith(("`", " ")) else delimiter + text + delimiter


def options_md(step, text, rows=()):
    lines = []
    for option in step.get("options", []):
        caption = backing_text(step, option, rows, text,
            lambda row: text(juror_name(row)) + " (if ...: " + md_code(row["pick"]) + ")")
        lines.append("- %s: %s%s" % (text(option["id"]), text(option["label"]), " -- **" + caption + "**" if caption else ""))
    lines += [""]
    detail = recommendation_parts(step)[1]
    if detail:
        lines += [prose_md(detail, text, "Mine (no vote)" if recommendation_marker(step) == "Mine" else "Recommendation"), ""]
    return lines


def jury_md(step, text):
    rows = jury_support(step)
    lines = options_md(step, text, rows)
    if majority_caption(rows):
        lines += [md_text(majority_caption(rows)), ""]
    if no_backing(rows, text):
        lines += [no_backing(rows, text), ""]
    lines += ["**Juror advice**", ""]
    for row, oid, conditional, outcome in rows:
        lines += ["%s (%s)" % (text(row["juror"]), text(row["model"])), ""]
        for field in ("pick", "reason", "status"):
            if field in row:
                lines += fenced(row[field])
        if outcome:
            lines += [text(outcome), ""]
    if step["jury"].get("agreement"):
        lines += ["Agreement: " + text(step["jury"]["agreement"]), ""]
    return lines


def replies_html(step, text):
    return "".join('<div class="reply" data-note="%s"><div class="viewer-note"%s>'
                   '<p>Your note:</p><p class="note-text" data-source="%s">%s</p></div>'
                   '<p>Reply: %s</p></div>' % (esc(nid), "" if nid in step.get("notes", {}) else " hidden",
                                              esc(step.get("notes", {}).get(nid, "")),
                                              text(step.get("notes", {}).get(nid, "")), text(answer))
                   for nid, answer in step.get("replies", {}).items())


def step_html(step, text):
    sid = esc(step["id"])
    title = "%d. %s" % (step["num"], text(step["title"]))
    finished = step["status"] == "done"
    head = '<details open class="step" data-step="%s" data-num="%d"><summary>%s<span class="ran" hidden> - Ran; output awaits review.</span></summary>' % (
        sid, step["num"], title)
    if finished:
        head = '<details class="finished" data-step="%s" data-num="%d"><summary>%s</summary>' % (
            sid, step["num"], title)
    if step["kind"] == "command":
        body = "".join(prose_html(step[field], text, label) if field in ("why", "success") else
                       '<p><strong>%s:</strong> %s</p>' % (label, text(step[field]))
                       for field, label in (("where", "Where"), ("why", "Why"), ("success", "Success")) if step.get(field))
        if step.get("time"):
            body += '<p><strong>Time:</strong> %s</p>' % text(step["time"])
        if step.get("command"):
            copy = '' if finished else '<button type="button" class="copy">Copy command</button>'
            body += '<div class="command">%s<pre>\n%s</pre></div>' % (copy, esc(step["command"]))
        if not finished:
            body += '<label class="tick" hidden><input type="checkbox" disabled data-cmd="%s"> I ran this</label>' % command_hash(step["command"])
    else:
        body = prose_html(step["context"], text) if step.get("context") else ""
        if "question" in step:
            body += '<details class="appendix"><summary>Question sent to the jury</summary><pre>\n%s</pre></details>' % esc(step["question"])
        if "jury" in step:
            body += jury_html(step, text)
        else:
            body += options_html(step, text)
        if step.get("ruling"):
            body += '<p><strong>Ruling:</strong> %s</p>' % text(step["ruling"])
        if step.get("built"):
            body += '<p><strong>Built:</strong></p><ul>' + ''.join('<li>%s</li>' % text(value)
                    for value in step["built"]) + '</ul>'
        if not finished:
            if "jury" in step and step.get("ruling"):
                body += '<p>%s</p>' % esc(RULING_GUIDANCE)
            body += '<p class="pick" aria-live="polite">No option picked.</p><div class="notes"></div>'
        body += replies_html(step, text)
        if not finished:
            body += '<form><label>Note or question<textarea disabled></textarea></label><button disabled type="button">Send note</button></form>'
    if finished:
        result = step["result"] if step["kind"] == "command" else step["answer"]
        body = '<p>%s</p>' % text(result) + body
    return head + '<div class="step-body">' + body + '</div></details>'


def render_html(state):
    text = lambda value: linked_text(value, state.get("repo"))
    after = "".join('<li value="%d" data-num="%d"%s><strong>%s:</strong> %s</li>' %
                    (item["num"], item["num"], ' data-step="%s"' % esc(item["id"]) if item.get("id") is not None else "",
                     text(item["owner"]), text(item["title"])) for item in state["after"])
    sessions = ""
    if len(state["sessions"]) > 1:
        sessions = '<section><h2>Sessions</h2><table><thead><tr><th>Session</th><th>Owns</th><th>State</th></tr></thead><tbody>'
        for row in state["sessions"]:
            sessions += '<tr>' + "".join('<td>%s</td>' % text(row[key]) for key in ("session", "owns", "state")) + '</tr>'
        sessions += '</tbody></table></section>'
    values = {
        "DOCUMENT_TITLE": esc(state["title"]), "TITLE": text(state["title"]), "GOAL": prose_html(state["goal"], text),
        "NOW": prose_html(state["now"], text, "Now", "now"), "UPDATED": text(state["updated"]),
        "OPEN": "".join('<h3 data-num="%d">%s</h3>' % (num, text(title)) if step is None else step_html(step, text)
                        for title, num, step in open_entries(state)),
        "AFTER": after, "SESSIONS": sessions,
        "DONE": "".join(step_html(s, text) for s in ordered_steps(state, "done")) +
                "".join('<p>%s</p>' % text(value) for value in state["done"]),
        "SIDE_NOTES": "".join('<li>%s</li>' % text(value) for value in state["side_notes"]),
        "APPENDIX": ('<section class="appendix"><h2>Appendix</h2>' + "".join(
            '<details><summary>%s</summary><pre>\n%s</pre></details>' % (text(item["title"]), esc(item["text"]))
            for item in state["appendix"]) + '</section>') if state.get("appendix") else "",
    }
    template = (Path(__file__).resolve().parent.parent / "template.html").read_text(encoding="utf-8")
    template = template.replace('<p>@@GOAL@@</p>', '@@GOAL@@').replace(
        '<p class="now"><strong>Now:</strong> @@NOW@@</p>', '@@NOW@@')
    return re.sub(r"@@([A-Z_]+)@@", lambda m: values[m[1]], template)


def md_text(value):
    text = re.sub(r"([\\`*_\[\]|<>~])", r"\\\1", str(value))
    text = re.sub(r"(?m)^([ \t]*)(#{1,6}|[-+])(?=[ \t]|$)", r"\1\\\2", text)
    text = re.sub(r"(?m)^([ \t]*\d+)([.)])(?=[ \t]|$)", r"\1\\\2", text)
    return re.sub(r"(?m)^([ \t]*)(-+|=+)([ \t]*)$", r"\1\\\2\3", text)


def decision_md(step, text):
    lines = []
    if step.get("context"):
        lines += [prose_md(step["context"], text), ""]
    if "question" in step:
        lines += ["Question sent to the jury:", ""] + fenced(step["question"])
    if "jury" in step:
        lines += jury_md(step, text)
    else:
        lines += options_md(step, text)
    if step.get("ruling"):
        if lines and lines[-1] != "":
            lines += [""]
        lines += ["Ruling: " + text(step["ruling"]), ""]
    if step.get("built"):
        if lines and lines[-1] != "":
            lines += [""]
        lines += ["Built:", ""] + ["- " + text(value) for value in step["built"]]
    if step["status"] == "open":
        if "jury" in step and step.get("ruling"):
            guidance = ("Reply in chat with the step number and the ruled option to confirm it, "
                        "another option to replace it, or a note.")
        else:
            guidance = "Reply in chat with the step number and your choice, note or question."
        lines += ["", guidance, ""]
    for nid, answer in step.get("replies", {}).items():
        if lines and lines[-1] != "":
            lines += [""]
        if nid in step.get("notes", {}):
            lines += ["Your note:", "", "> " + text(step["notes"][nid]).replace("\n", "\n> "), ""]
        lines += ["Reply: " + text(answer), ""]
    return lines


def render_md(state):
    text = lambda value: linked_text(value, state.get("repo"), markdown=True)
    lines = ["# " + text(state["title"]), "", prose_md(state["goal"], text), "",
             prose_md(state["now"], text, "Now"), "", "Updated: " + text(state["updated"]), "", "## Your turn", ""]
    entries = list(open_entries(state))
    heading = "####" if any(step is None for title, num, step in entries) else "###"
    for title, num, step in entries:
        if step is None:
            lines += ["### " + text(title), ""]
            continue
        lines += ["%s %d. %s" % (heading, step["num"], text(step["title"])), ""]
        if step["kind"] == "command":
            for field, label in (("where", "Where"), ("why", "Why"), ("success", "Success"), ("time", "Time")):
                if step.get(field):
                    lines += [prose_md(step[field], text, label) if field in ("why", "success") else
                              label + ": " + text(step[field]), ""]
            lines += fenced(step["command"], "bash")
            lines += ["Reply in chat with the step number.", ""]
        else:
            lines += decision_md(step, text)
    lines += ["## After that", ""]
    for item in state["after"]:
        lines += ["- Step %d: %s: %s" % (item["num"], text(item["owner"]), text(item["title"]))]
    lines += [""]
    if len(state["sessions"]) > 1:
        lines += ["## Sessions", "", "| Session | Owns | State |", "| --- | --- | --- |"]
        for row in state["sessions"]:
            lines += ["| " + " | ".join(text(row[k]).replace("\n", " ") for k in ("session", "owns", "state")) + " |"]
        lines += [""]
    lines += ["## Done so far", ""]
    for step in ordered_steps(state, "done"):
        result = step.get("result", "") if step["kind"] == "command" else step.get("answer", "")
        summary = "%d. %s" % (step["num"], step["title"])
        lines += ["<details>", "<summary>" + linked_text(summary, state.get("repo")) + "</summary>", "", text(result), ""]
        if step["kind"] == "decision":
            lines += decision_md(step, text)
        else:
            for field, label in (("where", "Where"), ("why", "Why"), ("success", "Success"), ("time", "Time")):
                if step.get(field):
                    lines += [prose_md(step[field], text, label) if field in ("why", "success") else
                              label + ": " + text(step[field]), ""]
            if step.get("command"):
                lines += fenced(step["command"], "bash")
        lines += ["</details>", ""]
    lines += ["- " + text(value) for value in state["done"]]
    lines += ["", "## Side notes", ""] + ["- " + text(value) for value in state["side_notes"]]
    if state.get("appendix"):
        lines += ["", "## Appendix", ""]
        for item in state["appendix"]:
            lines += ["### " + text(item["title"]), ""] + fenced(item["text"])
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
        # ArtifactData out_dir writes '~' in document ids as '@' in filenames.
        rows[path.stem.replace("@", "~")] = body
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
                pick = picks.get(sid, {}).get("option") or None
                current = any(option["id"] == pick for option in step.get("options", []))
                answer = str(pick) if current else "none"
                if pick is not None and not current:
                    answer += " (stale option %s)" % pick
                lines.append("%d. %s: pick %s" % (step["num"], sid, answer))
            for nid, note in sorted(notes.items(), key=lambda item: item[1].get("at", "")):
                if note.get("step") == sid and nid not in step.get("replies", {}):
                    lines.append("  Unanswered note %s: %s" % (nid, note.get("text", "").replace("\n", "\n    ")))
    return "\n".join(lines) + "\n"


def convert_jury(state, args):
    validate(state)
    targets = [step for step in sorted(state["steps"], key=lambda step: step["num"])
               if step["kind"] == "decision" and "jury" in step and
               all(not any(field in row for field in ("pick", "reason", "status"))
                   for row in step["jury"]["lines"])]
    if not targets:
        raise Usage("no target decisions; start from a roster-only scaffold")
    roster = {row["juror"]: row["model"] for row in targets[0]["jury"]["lines"]}
    for step in targets:
        if {row["juror"]: row["model"] for row in step["jury"]["lines"]} != roster:
            raise Usage("inconsistent jury roster for " + step["id"])
        if not any(not option.get("proposed") for option in step.get("options", [])):
            raise Usage("target %s needs at least one authored option" % step["id"])
    sources = {}
    for field in ("reply", "failed"):
        for argument in getattr(args, field):
            juror, sep, path = argument.partition("=")
            if not sep or not juror or not path or not Path(path).is_absolute():
                raise Usage("--%s needs juror=path with an absolute file path: %s" % (field, argument))
            if juror not in roster:
                raise Usage("unknown juror: " + juror)
            if juror in sources:
                raise Usage("duplicate source for juror: " + juror)
            sources[juror] = (field, path, read_source(path))
    missing = sorted(set(roster) - set(sources))
    if missing:
        raise Usage("missing reply or failure file for juror: " + ", ".join(missing))
    if not args.sentinel.strip() or len(args.sentinel.splitlines()) != 1:
        raise Usage("sentinel must be one nonblank line")
    labels = [jury_label(step) for step in targets]
    if None in labels and len(targets) != 1:
        raise Usage("bare prefixes require a single target decision")
    if len(set(labels)) != len(labels):
        label = next(label for label in labels if labels.count(label) > 1)
        ids = ", ".join(step["id"] for step in targets if jury_label(step) == label)
        raise Usage("duplicate source label %s in target decisions: %s" % (label, ids))
    label_pattern = "|".join([re.escape(label) for label in sorted(
        (label for label in labels if label is not None), key=lambda label: (-len(label), label))] + [r"[^\s]+?"])
    evidence = {}
    for juror in sorted(roster):
        field, path, text = sources[juror]
        lines = text.splitlines()
        if field == "failed":
            if not lines or not re.fullmatch(r"no reply, exit -?[0-9]+", lines[0]):
                raise Usage("failure file for juror %s must start with no reply, exit <integer>: %s" % (juror, path))
            evidence[juror] = {sid: {"status": text} for sid in labels}
            continue
        end = len(lines) - 1
        while end >= 0 and not lines[end].strip():
            end -= 1
        if end < 0 or lines[end].strip() != args.sentinel:
            evidence[juror] = {sid: {"status": "truncated"} for sid in labels}
            continue
        extracted = {sid: {} for sid in labels}
        opening = True
        for line in lines[:end]:
            if not line.strip():
                continue
            if opening and re.fullmatch(r"[ \t]*```[^`]*", line):
                opening = False
                continue
            opening = False
            match = re.fullmatch(r"[ \t]*(PICK|REASON)(?: (" + label_pattern + r"))?:([^\r\n]*)", line)
            if match is None:
                break
            prefix, sid = match[1], match[2]
            if sid is None and None not in labels:
                raise Usage("unlabelled %s from juror %s in %s; set jury.label to null for one bare target" % (prefix, juror, path))
            if sid not in labels:
                if any("jury" in step and jury_label(step) == sid for step in state["steps"]):
                    raise Usage("label %s from juror %s in %s names a decision that is not a roster-only target" %
                                (sid, juror, path))
                raise Usage("unknown target label %s from juror %s in %s" % (sid, juror, path))
            key = prefix.lower()
            if key in extracted[sid]:
                raise Usage("duplicate %s for %s from juror %s in %s" % (prefix, sid, juror, path))
            extracted[sid][key] = line
        evidence[juror] = {sid: fields or {"status": "no pick line; no reason line"}
                           for sid, fields in extracted.items()}
    for step in targets:
        sid = step["id"]
        label = jury_label(step)
        step["jury"]["lines"] = [dict(juror=juror, model=roster[juror], **evidence[juror][label])
                                  for juror in sorted(roster)]
        for row in step["jury"]["lines"]:
            if "pick" not in row or "reason" not in row or not source_value(row["reason"], "REASON", label)[1]:
                continue
            pick = source_value(row["pick"], "PICK", label)[1]
            proposal = pick[4:].strip() if pick.startswith("new:") else ""
            if not proposal or any(option["label"] == proposal for option in step["options"]):
                continue
            oid = next((letter for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                        if not any(option["id"] == letter for option in step["options"])), None)
            if oid is None:
                raise Usage("no unused option letter for %s from juror %s" % (sid, row["juror"]))
            step["options"].append({"id": oid, "label": proposal, "proposed": True})
        step["jury"]["support"] = [dict(juror=row["juror"], option=option, conditional=conditional, outcome=outcome)
                                   for row, option, conditional, outcome in jury_rows(step)]
    named = any("label" in step["jury"] for step in targets)

    def caption(step):
        if not named:
            return step["id"]
        label = jury_label(step)
        return "%s (%s)" % (step["title"], "single question" if label is None else label)

    label_range = caption(targets[0])
    if len(targets) > 1:
        label_range += " to " + caption(targets[-1])
    question = read_source(args.question)
    for step in targets:
        step["question"] = question
    appendix = state.setdefault("appendix", [])
    for juror in sorted(roster):
        if sources[juror][0] == "reply":
            appendix.append({"title": "Reply from %s (%s) for %s" % (juror, roster[juror], label_range),
                             "text": sources[juror][2]})
    validate(state, render=True)
    output = Path(args.output)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                         prefix="." + output.name + ".", suffix=".tmp", delete=False) as draft:
            temporary = Path(draft.name)
            draft.write(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
        os.replace(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main():
    parser = Parser(description=__doc__, epilog=(
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
    jury = subs.add_parser("jury", help="convert jury replies into a draft state", description=(
        'Populate roster-only decisions from the opening PICK/REASON block. '
        'Use jury.label for source labels, or null for one bare question. '
        'Put the exact question on each card and full replies in the appendix; render separately.'))
    jury.add_argument("state", metavar="CARD.json")
    jury.add_argument("--question", required=True, metavar="QUESTION.txt")
    jury.add_argument("--sentinel", required=True, help="required last nonblank line of a complete reply")
    jury.add_argument("--reply", action="append", default=[], metavar="juror=/absolute/path/reply.txt",
                      help="repeat once per roster juror that replied")
    jury.add_argument("--failed", action="append", default=[], metavar="juror=/absolute/path/failure.txt",
                      help="repeat once per roster juror whose command failed")
    jury.add_argument("-o", "--output", required=True, metavar="STATE.json")
    args = parser.parse_args()
    try:
        state = load(args.state)
        if args.action == "jury":
            convert_jury(state, args)
            return 0
        validate(state, render=args.action == "render")
        if args.action == "read":
            print(read_responses(state, Path(args.dbdir)), end="")
        else:
            snapshot = Path(args.state).with_suffix(".numbers.json")
            numbers = step_numbers(state, load(snapshot) if snapshot.exists() else {})
            completion = re.fullmatch(r"Work done; (\d+) rulings? open for optional review", state["now"])
            if completion:
                count = int(completion[1])
                state["now"] = "Work done; %d %s open for optional review" % (count, "ruling" if count == 1 else "rulings")
            content = render_md(state) if args.md else render_html(state)
            Path(args.output).write_text(content, encoding="utf-8")
            snapshot.write_text(json.dumps(numbers, indent=2) + "\n", encoding="utf-8")
    except (Usage, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print("handback-page: " + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
