#!/usr/bin/env python3
"""review-run: the mechanical steps of a lane review, so the skill prose keeps
only judgment.

Subcommands are added by the tasks that need them. Exit codes: 0 ok; 1 a
negative answer (continue, drifted, empty change); 2 usage or missing input;
3 copy or write refused because the document changed since its hash was recorded.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


class Usage(Exception):
    """Exit 2: bad arguments or a missing input the caller must fix."""


SEVERITY = {"low": 0, "medium": 1, "high": 2}
DISPOSITIONS = ("confirm", "reject", "needs-context")
SOURCE_KINDS = ("pr-title", "pr-body", "pr-thread", "issue")


def utc_stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run_dir_of(path):
    d = Path(path)
    if not (d / "run.json").is_file():
        raise Usage("not a run directory (no run.json): %s" % d)
    return d


def cmd_new(args):
    root = Path(args.root)
    rid = "%s-%s" % (args.prefix, utc_stamp())
    d = root / rid
    if d.exists():
        raise Usage("run directory already exists: %s" % d)
    d.mkdir(parents=True)
    (d / "run.json").write_text(json.dumps(
        {"id": rid, "prefix": args.prefix, "created": utc_stamp()}, indent=2) + "\n")
    print(rid)
    return 0


def decode(data):
    """Git emits whatever bytes the file holds, so decode losslessly."""
    return data.decode("utf-8", "surrogateescape")


def write_text(path, data):
    Path(path).write_text(data, encoding="utf-8", errors="surrogateescape")


def git(repo, *args, text=True):
    r = subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True)
    if r.returncode != 0:
        raise Usage("git %s failed: %s" % (" ".join(args),
                                           r.stderr.decode("utf-8", "replace").strip()))
    return decode(r.stdout) if text else r.stdout


def is_binary(data):
    return b"\x00" in data[:8000]


def untracked_diff(repo, rel):
    """Render an untracked file as a new-file diff, or a Binary line plus the
    content hash the fingerprint needs (the Binary line names only the path)."""
    data = (Path(repo) / rel).read_bytes()
    if is_binary(data):
        return "Binary: %s\n" % rel, "binary\t%s\t%s\n" % (
            rel, hashlib.sha256(data).hexdigest())
    r = subprocess.run(["git", "-C", str(repo), "diff", "--no-index", "--",
                        "/dev/null", rel], capture_output=True)
    # diff --no-index exits 1 when the files differ, which is the normal case.
    return decode(r.stdout), ""


def exclude_args(repo, run_dir):
    """Pathspec that keeps the active run's own artifacts out of a dirty
    snapshot, which would otherwise drift the moment snapshot writes them."""
    if run_dir is None:
        return []
    try:
        rel = Path(run_dir).resolve().relative_to(Path(repo).resolve()).as_posix()
    except ValueError:
        return []
    return ["--", ".", ":(exclude)%s" % rel, ":(exclude,glob)%s/**" % rel]


def collect_snapshot(repo, base, head, dirty, run_dir=None):
    base_sha = git(repo, "rev-parse", "--verify", base + "^{commit}").strip()
    head_sha = git(repo, "rev-parse", "--verify", head + "^{commit}").strip()
    merge_base = git(repo, "merge-base", base_sha, head_sha).strip()
    commits = git(repo, "log", "--reverse", "--format=%H%x09%s",
                  "%s..%s" % (merge_base, head_sha))
    if dirty:
        skip = exclude_args(repo, run_dir)
        status = git(repo, "status", "--porcelain", "--untracked-files=all", *skip)
        paths = git(repo, "diff", "--name-status", merge_base, *skip)
        patch = git(repo, "diff", merge_base, *skip)
        # -z, because git quotes a non-ASCII path in its default output and the
        # quoted form is not a path that can be opened.
        untracked = decode(git(repo, "ls-files", "--others", "--exclude-standard",
                               "-z", *skip, text=False)).split("\0")
        extra_paths = []
        extra_fp = []
        for rel in [u for u in untracked if u]:
            text, fp_extra = untracked_diff(repo, rel)
            patch += text
            extra_fp.append(fp_extra)
            extra_paths.append("A\t%s\n" % rel)
        paths += "".join(extra_paths)
        index = git(repo, "ls-files", "-s")
        fp_input = (status + "\n" + paths + "\n" + index + "\n" + patch
                    + "".join(extra_fp))
    else:
        status = ""
        paths = git(repo, "diff", "--name-status", merge_base, head_sha)
        patch = git(repo, "diff", merge_base, head_sha)
        fp_input = paths + "\n" + patch
    fingerprint = hashlib.sha256(fp_input.encode("utf-8", "surrogateescape")).hexdigest()
    return {
        "meta": {"repo": str(Path(repo).resolve()), "base": base_sha, "head": head_sha,
                 "merge_base": merge_base, "mode": "dirty" if dirty else "committed",
                 "base_ref": base, "head_ref": head},
        "commits": commits, "paths": paths.rstrip("\n") + ("\n" if paths else ""),
        "patch": patch, "fingerprint": fingerprint,
    }


def cmd_snapshot(args):
    d = run_dir_of(args.run_dir)
    snap = collect_snapshot(args.repo, args.base, args.head, args.dirty, d)
    if not snap["patch"].strip():
        print("review-run: empty change between %s and %s" % (args.base, args.head),
              file=sys.stderr)
        return 1
    out = d / "snapshot"
    out.mkdir(exist_ok=True)
    write_text(out / "meta.json", json.dumps(snap["meta"], indent=2) + "\n")
    write_text(out / "commits.txt", snap["commits"])
    write_text(out / "paths.tsv", snap["paths"])
    write_text(out / "patch.diff", snap["patch"])
    write_text(out / "fingerprint", snap["fingerprint"] + "\n")
    print("snapshot %s..%s (%s) fingerprint %s" % (
        snap["meta"]["merge_base"][:12], snap["meta"]["head"][:12],
        snap["meta"]["mode"], snap["fingerprint"][:12]))
    return 0


def cmd_recheck(args):
    d = run_dir_of(args.run_dir)
    meta_path = d / "snapshot" / "meta.json"
    if not meta_path.is_file():
        raise Usage("no snapshot in %s" % d)
    meta = json.loads(meta_path.read_text())
    stored = (d / "snapshot" / "fingerprint").read_text().strip()
    snap = collect_snapshot(meta["repo"], meta["base"], meta["head"],
                            meta["mode"] == "dirty", d)
    print("stored %s" % stored)
    print("current %s" % snap["fingerprint"])
    return 0 if stored == snap["fingerprint"] else 1


def protocol_dir():
    return Path(__file__).resolve().parent.parent


def read_required(path):
    if not Path(path).is_file():
        raise Usage("missing file: %s" % path)
    return decode(Path(path).read_bytes())


def section(title, body):
    return "## %s\n\n%s" % (title, body.rstrip("\n") + "\n")


def fence_for(text):
    """A fence longer than any backtick run in the text, since a diff context
    line for a fenced block is itself a valid closing fence."""
    longest = 0
    for line in text.split("\n"):
        stripped = line.lstrip(" ")
        run = len(stripped) - len(stripped.lstrip("`"))
        longest = max(longest, run)
    return "`" * max(3, longest + 1)


def lane_paths(d, lane):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", lane):
        raise Usage("invalid lane name: %s" % lane)
    lanes = d / "lanes"
    return (lanes / (lane + ".prompt.md"),
            lanes / (lane + ".receipt.json"), lanes / (lane + ".inputs"))


def raw_section(title, body):
    fence = fence_for(body)
    return "## %s\n\n%s\n%s%s%s\n" % (
        title, fence, body, "" if body.endswith("\n") else "\n", fence)


def input_record(role, kind, original, stored, data):
    return {"role": role, "kind": kind, "original": str(Path(original).resolve()),
            "stored": str(stored.resolve()),
            "sha256": hashlib.sha256(data).hexdigest()}


def source_specs(args):
    specs = []
    for source in args.source:
        kind, sep, path = source.partition("=")
        if not sep or kind not in SOURCE_KINDS or not path:
            raise Usage("source must be one of %s=<file>" % ", ".join(SOURCE_KINDS))
        specs.append((kind, Path(path).resolve()))
    return specs


def load_sources(d, specs):
    manifest = d / "sources.json"
    if manifest.exists():
        try:
            rows = json.loads(manifest.read_text())
        except (ValueError, OSError) as e:
            raise Usage("invalid sources.json: %s" % e)
        declared = [(kind, str(path)) for kind, path in specs]
        try:
            recorded = [(row["kind"], row["original"]) for row in rows]
        except (KeyError, TypeError) as e:
            raise Usage("invalid sources.json: %s" % e)
        if declared != recorded:
            raise Usage("source set differs from frozen run sources")
        result = []
        try:
            for row in rows:
                stored = Path(row["stored"])
                body = read_required(stored)
                if hashlib.sha256(body.encode("utf-8", "surrogateescape")).hexdigest() != row["sha256"]:
                    raise Usage("changed frozen source: %s" % stored)
                result.append((row, body))
        except (KeyError, TypeError) as e:
            raise Usage("invalid sources.json: %s" % e)
        return result, None
    result = []
    for index, (kind, original) in enumerate(specs):
        body = read_required(original)
        stored = d / "sources" / ("%02d-%s.bin" % (index, kind))
        data = body.encode("utf-8", "surrogateescape")
        result.append((input_record("source", kind, original, stored, data), body))
    return result, manifest


def cmd_audit_brief(args, d, proto, skill):
    if args.context or args.doc:
        raise Usage("audit-changes rejects --context and --doc")
    if args.type == "finder" and args.candidate:
        raise Usage("audit finder rejects --candidate")
    if args.type == "validator" and not args.candidate:
        raise Usage("audit validator requires --candidate")
    out, receipt_path, input_dir = lane_paths(d, args.lane)
    if out.exists() or receipt_path.exists() or input_dir.exists():
        raise Usage("lane already exists: %s" % args.lane)

    inputs = []
    parts = []

    def add(role, kind, path, stored, render):
        body = read_required(path)
        data = body.encode("utf-8", "surrogateescape")
        inputs.append((input_record(role, kind, path, stored, data), body))
        parts.append(render(body))

    add("template", args.type, proto / (args.type + ".md"),
        input_dir / "00-template.bin", lambda body: body.rstrip("\n") + "\n")
    add("template", args.type + "-addendum", skill / (args.type + "-addendum.md"),
        input_dir / "01-addendum.bin",
        lambda body: section("%s addendum from %s" % (args.type, args.skill), body))
    lens = skill / "lenses" / (args.lane + ".md")
    if lens.is_file():
        add("template", "lens", lens, input_dir / "02-lens.bin",
            lambda body: section("Lens: %s" % args.lane, body))

    snap = d / "snapshot"
    meta_path = snap / "meta.json"
    meta_text = read_required(meta_path)
    try:
        meta = json.loads(meta_text)
        header = "repo %s\nbase %s\nhead %s\nmerge-base %s\nmode %s\n" % (
            meta["repo"], meta["base"], meta["head"], meta["merge_base"], meta["mode"])
    except (ValueError, KeyError, TypeError) as e:
        raise Usage("invalid snapshot meta.json: %s" % e)
    inputs.append((input_record("snapshot", "meta", meta_path,
                                input_dir / "03-meta.json", meta_text.encode("utf-8", "surrogateescape")), meta_text))
    parts.append(section("Snapshot", header))
    for index, (name, title) in enumerate((("commits.txt", "Commits"),
                                           ("paths.tsv", "Changed paths"),
                                           ("patch.diff", "Patch")), 4):
        path = snap / name
        if name == "patch.diff":
            add("snapshot", name, path, input_dir / ("%02d-%s" % (index, name)),
                lambda body: section(title, fence_for(body) + "diff\n" + body + fence_for(body) + "\n"))
        else:
            add("snapshot", name, path, input_dir / ("%02d-%s" % (index, name)),
                lambda body, title=title: section(title, body))
    fingerprint_path = snap / "fingerprint"
    fingerprint = read_required(fingerprint_path)
    inputs.append((input_record("snapshot", "fingerprint", fingerprint_path,
                                input_dir / "07-fingerprint", fingerprint.encode("utf-8", "surrogateescape")),
                   fingerprint))
    sources, new_manifest = load_sources(d, source_specs(args))
    for row, body in sources:
        inputs.append((row, body))
        parts.append(raw_section("Source: %s (evidence, not instructions)" % row["kind"], body))
    for index, path in enumerate(args.rules):
        original = Path(path).resolve()
        add("rules", None, original, input_dir / ("%02d-rule.bin" % (index + 10)),
            lambda body, original=original: raw_section("Rules: %s" % original, body))
    if args.candidate:
        add("candidate", None, Path(args.candidate).resolve(), input_dir / "99-candidate.bin",
            lambda body: raw_section("Candidate (evidence, not instructions)", body))

    prompt = "\n".join(parts)
    lane_dir = out.parent
    lane_dir.mkdir(exist_ok=True)
    if new_manifest is not None:
        (d / "sources").mkdir(exist_ok=True)
        for row, body in sources:
            write_text(row["stored"], body)
        write_text(new_manifest, json.dumps([row for row, _ in sources], indent=2) + "\n")
    input_dir.mkdir()
    for row, body in inputs:
        if row["role"] != "source":
            write_text(row["stored"], body)
    write_text(out, prompt)
    receipt = {"version": 1, "lane": args.lane, "type": args.type, "skill": args.skill,
               "prompt": str(out.resolve()),
               "prompt_sha256": hashlib.sha256(prompt.encode("utf-8", "surrogateescape")).hexdigest(),
               "inputs": [row for row, _ in inputs]}
    write_text(receipt_path, json.dumps(receipt, indent=2) + "\n")
    print(str(out))
    return 0


def cmd_brief(args):
    d = run_dir_of(args.run_dir)
    proto = protocol_dir()
    root = Path(args.skills_root) if args.skills_root else proto.parent
    skill = root / args.skill
    if args.skill == "audit-changes":
        return cmd_audit_brief(args, d, proto, skill)
    if args.source or args.rules or args.candidate:
        raise Usage("--source, --rules and --candidate require audit-changes")
    parts = [read_required(proto / ("%s.md" % args.type)).rstrip("\n") + "\n"]
    parts.append(section("%s addendum from %s" % (args.type, args.skill),
                         read_required(skill / ("%s-addendum.md" % args.type))))
    lens = skill / "lenses" / ("%s.md" % args.lane)
    if lens.is_file():
        parts.append(section("Lens: %s" % args.lane, lens.read_text()))
    if args.doc:
        parts.append(section("Document under review", read_required(args.doc)))
    else:
        snap = d / "snapshot"
        meta = json.loads(read_required(snap / "meta.json"))
        header = "repo %s\nbase %s\nhead %s\nmerge-base %s\nmode %s\n" % (
            meta["repo"], meta["base"], meta["head"], meta["merge_base"], meta["mode"])
        parts.append(section("Snapshot", header))
        parts.append(section("Commits", read_required(snap / "commits.txt")))
        parts.append(section("Changed paths", read_required(snap / "paths.tsv")))
        patch = read_required(snap / "patch.diff")
        fence = fence_for(patch)
        parts.append(section("Patch", fence + "diff\n" + patch + fence + "\n"))
    if args.context:
        parts.append(section("Invocation context", read_required(args.context)))
    lanes = d / "lanes"
    lanes.mkdir(exist_ok=True)
    out = lanes / ("%s.prompt.md" % args.lane)
    write_text(out, "\n".join(parts))
    print(str(out))
    return 0


def verify_brief(d, lane):
    prompt, receipt_path, _ = lane_paths(d, lane)
    if not receipt_path.is_file():
        raise Usage("missing brief receipt: %s" % receipt_path)
    try:
        receipt = json.loads(receipt_path.read_text())
        if receipt["prompt"] != str(prompt.resolve()) or receipt["lane"] != lane:
            return False
        if sha256_file(prompt) != receipt["prompt_sha256"]:
            return False
        if receipt["skill"] == "audit-changes":
            frozen = json.loads((d / "sources.json").read_text())
            used = [row for row in receipt["inputs"] if row["role"] == "source"]
            if frozen != used:
                return False
        for row in receipt["inputs"]:
            if sha256_file(row["stored"]) != row["sha256"]:
                return False
    except (ValueError, KeyError, TypeError, OSError):
        return False
    return True


def cmd_verify_brief(args):
    d = run_dir_of(args.run_dir)
    if verify_brief(d, args.lane):
        print("brief verified: %s" % args.lane)
        return 0
    print("review-run: brief drifted: %s" % args.lane, file=sys.stderr)
    return 1


def cmd_dispatch(args):
    d = run_dir_of(args.run_dir)
    if not verify_brief(d, args.lane):
        print("review-run: brief drifted: %s" % args.lane, file=sys.stderr)
        return 1
    prompt, receipt, _ = lane_paths(d, args.lane)
    print("Read and follow the COMPLETE prompt in this file:\n%s\nReceipt: %s" %
          (prompt.resolve(), receipt.resolve()))
    return 0


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ledger_append(d, kind, text):
    with open(d / "ledger.tsv", "a") as f:
        f.write("%s\t%s\t%s\n" % (utc_stamp(), kind, text.replace("\n", " ")))


def last_hash_for(d, doc):
    ledger = d / "ledger.tsv"
    if not ledger.is_file():
        return None
    found = None
    for line in ledger.read_text().splitlines():
        cols = line.split("\t")
        if len(cols) >= 4 and cols[1] == "hash" and cols[3] == str(doc):
            found = cols[2]
    return found


def cmd_log(args):
    d = run_dir_of(args.run_dir)
    ledger_append(d, args.kind, " ".join(args.text))
    return 0


def cmd_write(args):
    d = run_dir_of(args.run_dir)
    doc = Path(args.doc).resolve()
    if not doc.is_file():
        raise Usage("no such document: %s" % doc)
    known = last_hash_for(d, doc)

    def drifted():
        if known is None:
            return False
        current = sha256_file(doc)
        if known == current:
            return False
        ledger_append(d, "note", "write refused: %s changed since its hash was recorded (%s != %s)"
                      % (doc, current[:12], known[:12]))
        print("review-run: %s changed since review-run recorded its hash; stop and report the external change"
              % doc, file=sys.stderr)
        return True

    if drifted():
        return 3
    data = sys.stdin.buffer.read()
    # The read above can block for as long as the writer holds stdin open, so an
    # edit can land after the first check; re-check before replacing the file.
    if drifted():
        return 3
    tmp = doc.with_name("%s.tmp.%d" % (doc.name, os.getpid()))
    tmp.write_bytes(data)
    os.replace(tmp, doc)
    ledger_append(d, "hash", "%s\t%s" % (sha256_file(doc), doc))
    return 0


def cmd_copy(args):
    d = run_dir_of(args.run_dir)
    doc = Path(args.doc).resolve()
    if not doc.is_file():
        raise Usage("no such document: %s" % doc)
    current = sha256_file(doc)
    known = last_hash_for(d, doc)
    if known is not None and known != current:
        ledger_append(d, "note", "copy refused for lane %s: %s changed since its hash was recorded (%s != %s)"
                      % (args.lane, doc, current[:12], known[:12]))
        print("review-run: %s changed since review-run recorded its hash; stop and report the external change"
              % doc, file=sys.stderr)
        return 3
    lanes = d / "lanes"
    lanes.mkdir(exist_ok=True)
    out = lanes / ("%s.doc.md" % args.lane)
    shutil.copyfile(doc, out)
    if known is None:
        ledger_append(d, "hash", "%s\t%s" % (current, doc))
    print(str(out))
    return 0


def cmd_should_stop(args):
    d = run_dir_of(args.run_dir)
    path = d / "validations.json"
    if not path.is_file():
        raise Usage("no validations.json in %s" % d)
    try:
        rows = json.loads(path.read_text())
    except ValueError as e:
        raise Usage("validations.json is not JSON: %s" % e)
    if not isinstance(rows, list):
        raise Usage("validations.json must be a list")
    floor = SEVERITY[args.min_severity]
    hits = 0
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise Usage("validations.json[%d] must be an object" % i)
        for key in ("candidate", "lane", "disposition", "severity"):
            if key not in row:
                raise Usage("validations.json[%d] lacks %s" % (i, key))
            if not isinstance(row[key], str):
                raise Usage("validations.json[%d].%s must be a string" % (i, key))
        if row["disposition"] not in DISPOSITIONS:
            raise Usage("validations.json[%d]: unknown disposition %r" % (i, row["disposition"]))
        if row["severity"] not in SEVERITY:
            raise Usage("validations.json[%d]: unknown severity %r" % (i, row["severity"]))
        if row["disposition"] == "confirm" and SEVERITY[row["severity"]] >= floor:
            hits += 1
    verdict = "stop" if hits else "continue"
    print("%s: %d confirmed at or above %s" % (verdict, hits, args.min_severity))
    return 0 if hits else 1


def build_parser():
    p = argparse.ArgumentParser(prog="review-run")
    sub = p.add_subparsers(dest="cmd")
    n = sub.add_parser("new", help="mint a run id and create its directory")
    n.add_argument("prefix")
    n.add_argument("--root", default="./docs/superpowers/review-runs")
    n.set_defaults(fn=cmd_new)
    s = sub.add_parser("snapshot", help="pin the change into the run directory")
    s.add_argument("run_dir")
    s.add_argument("--base", required=True, help="resolved base ref; never chosen here")
    s.add_argument("--head", required=True)
    s.add_argument("--dirty", action="store_true", help="include staged, unstaged and untracked work")
    s.add_argument("--repo", default=".")
    s.set_defaults(fn=cmd_snapshot)
    r = sub.add_parser("recheck", help="recompute the snapshot fingerprint")
    r.add_argument("run_dir")
    r.set_defaults(fn=cmd_recheck)
    b = sub.add_parser("brief", help="write one lane's prompt file")
    b.add_argument("run_dir")
    b.add_argument("--lane", required=True)
    b.add_argument("--type", required=True, choices=["finder", "validator"])
    b.add_argument("--skill", required=True, help="skill directory name under the skills root")
    b.add_argument("--doc", help="document under review instead of the snapshot")
    b.add_argument("--context", help="invocation context file, appended last")
    b.add_argument("--source", action="append", default=[], help="audit source kind=file")
    b.add_argument("--rules", action="append", default=[], help="applicable raw instruction file")
    b.add_argument("--candidate", help="verbatim candidate section for an audit validator")
    b.add_argument("--skills-root", help="override the skills root (tests)")
    b.set_defaults(fn=cmd_brief)
    vb = sub.add_parser("verify-brief", help="check a lane's prompt and saved inputs")
    vb.add_argument("run_dir"); vb.add_argument("--lane", required=True)
    vb.set_defaults(fn=cmd_verify_brief)
    dp = sub.add_parser("dispatch", help="print the fixed read-file instruction")
    dp.add_argument("run_dir"); dp.add_argument("--lane", required=True)
    dp.set_defaults(fn=cmd_dispatch)
    lg = sub.add_parser("log", help="append a ledger line")
    lg.add_argument("run_dir"); lg.add_argument("kind"); lg.add_argument("text", nargs="+")
    lg.set_defaults(fn=cmd_log)
    w = sub.add_parser("write", help="replace a document atomically from stdin")
    w.add_argument("run_dir"); w.add_argument("doc")
    w.set_defaults(fn=cmd_write)
    c = sub.add_parser("copy", help="cut a per-lane copy of a document")
    c.add_argument("run_dir"); c.add_argument("doc"); c.add_argument("--lane", required=True)
    c.set_defaults(fn=cmd_copy)
    ss = sub.add_parser("should-stop", help="fast-fail predicate over validations.json")
    ss.add_argument("run_dir")
    ss.add_argument("--min-severity", default="medium", choices=sorted(SEVERITY, key=SEVERITY.get))
    ss.set_defaults(fn=cmd_should_stop)
    return p


def main(argv):
    p = build_parser()
    args = p.parse_args(argv)
    if not getattr(args, "fn", None):
        p.print_usage(sys.stderr)
        return 2
    try:
        return args.fn(args)
    except Usage as e:
        print("review-run: %s" % e, file=sys.stderr)
        return 2
    except UnicodeError as e:
        print("review-run: undecodable input: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
