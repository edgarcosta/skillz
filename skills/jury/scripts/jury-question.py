#!/usr/bin/env python3
"""Prepare and verify a blind neutrality read. Exit 0: pass; 1: lean/unusable; 2: invalid input or I/O."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile


INSTRUCTION = """Read only the question below. Assess whether its framing favors an option.
Use no tools and read no other file.
Check the context, assumptions, selection criteria, option descriptions and
requested answer. Each option should receive its strongest case in parallel
form at similar length. Do not answer the underlying decision.
For a labelled file, reply with one line for every source label, using:
<label>: no lean
or
<label>: leans to <option or position> because <quote the phrase causing the lean>
For an unlabelled file, reply with one bare line using:
no lean
or
leans to <option or position> because <quote the phrase causing the lean>
"""


def labels_checked(labels):
    if (any(not re.fullmatch(r"[A-Za-z0-9_~:@+.-]{1,200}", label) or label in (".", "..")
            for label in labels) or len(set(labels)) != len(labels)):
        raise ValueError("labels must be unique, 1-200 characters from A-Z a-z 0-9 _ ~ : @ + . -, and not . or ..")
    return labels


def family(value):
    if not isinstance(value, str) or not value.strip() or len(value.strip().splitlines()) != 1:
        raise ValueError("family must be a nonempty identifier")
    return value.strip().casefold()


def results(raw, labels):
    parsed = {}
    for line in raw.rstrip().splitlines():
        label, verdict = None, line.rstrip()
        if labels:
            match = re.fullmatch(r"([A-Za-z0-9_~:@+.-]+): (.+)", verdict)
            if not match:
                raise ValueError("reply needs one labelled verdict per source label")
            label, verdict = match.groups()
        if label not in (labels or [None]) or label in parsed:
            raise ValueError("reply has an unexpected or duplicate label")
        if verdict != "no lean" and not re.fullmatch(r"leans to \S(?:.*\S)? because \S(?:.*\S)?", verdict):
            raise ValueError("reply must use 'no lean' or 'leans to ... because ...' without extra prose")
        parsed[label] = verdict
    if len(parsed) != len(labels or [None]):
        raise ValueError("reply is missing a verdict")
    return [{"label": label, "verdict": parsed[label]} for label in (labels or [None])]


def atomic_write(path, text):
    output = Path(path)
    if not output.parent.is_dir():
        raise ValueError("output directory does not exist: " + str(output.parent))
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=output.parent,
                                         prefix="." + output.name + ".", suffix=".tmp", delete=False) as draft:
            temporary = Path(draft.name)
            draft.write(text)
        os.replace(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def verify(question, check):
    if not isinstance(check, dict) or type(check.get("version")) is not int or check["version"] != 1:
        raise ValueError("check must be a version-1 record")
    author, reader = family(check.get("author_family")), family(check.get("reader_family"))
    return 0 if (check.get("passed") is True and author != reader and
                 check.get("question_sha256") == hashlib.sha256(question).hexdigest()) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("brief", "record", "verify"):
        command = commands.add_parser(name)
        command.add_argument("question", type=Path)
        if name == "verify":
            command.add_argument("check", type=Path)
        else:
            command.add_argument("--label", action="append", default=[], help="source label; repeat for every question")
            command.add_argument("-o", "--output", required=True, type=Path)
        if name == "record":
            command.add_argument("--author-family", required=True)
            command.add_argument("--reader-family", required=True)
            command.add_argument("--reply", required=True, type=Path, help="reader stdout only")
    args = parser.parse_args()
    try:
        question = args.question.read_bytes()
        text = question.decode("utf-8")
        if args.command == "verify":
            return verify(question, json.loads(args.check.read_bytes().decode("utf-8")))
        labels = labels_checked(args.label)
        if args.command == "brief":
            atomic_write(args.output, INSTRUCTION + "\nLabels: " +
                         (", ".join(labels) if labels else "(unlabelled)") + "\n\n" + text)
            return 0
        author, reader = family(args.author_family), family(args.reader_family)
        if author == reader:
            raise ValueError("author and reader must come from different model families")
        raw = args.reply.read_bytes().decode("utf-8")
        parsed = results(raw, labels)
        passed = all(row["verdict"] == "no lean" for row in parsed)
        check = dict(version=1, question_sha256=hashlib.sha256(question).hexdigest(),
                     labels=labels, raw_reply=raw, results=parsed, author_family=author,
                     reader_family=reader, passed=passed)
        atomic_write(args.output, json.dumps(check, indent=2, ensure_ascii=False) + "\n")
        return 0 if passed else 1
    except (OSError, ValueError) as error:
        print("jury-question: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
