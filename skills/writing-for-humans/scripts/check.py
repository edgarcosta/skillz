#!/usr/bin/env python3
"""
Deterministic pre-send checker for a draft PR body, review comment, issue,
or tracker comment. Reports prose problems the house style forbids so the
sending agent can fix them before sending; it never blocks the send itself.
Usage: check.py [--max-words N] [--spelling] FILE [FILE...]
       check.py [-]   (also: no args at all) reads stdin as one document
"""
import argparse, bisect, os, re, shutil, subprocess, sys, tempfile, unicodedata
from itertools import accumulate
# house rule: no hedging qualifiers in prose (check: hedge)
HEDGE = ["perhaps", "a bit", "fairly", "somewhat", "quite", "rather", "arguably", "seemingly", "potentially", "might possibly", "could possibly", "sort of", "kind of", "more or less", "to some extent", "in some sense"]
# house rule: no throat-clearing filler words (check: filler)
FILLER = ["basically", "essentially", "actually", "really", "very", "just", "simply", "in order to", "it is worth noting", "it's worth noting", "worth noting", "note that", "it should be noted", "importantly", "notably", "overall", "additionally", "furthermore", "moreover", "in summary", "in conclusion", "as mentioned", "as you can see", "needless to say", "of course", "obviously", "clearly"]
# house rule: no corporate-speak idioms (check: idiom)
IDIOM = ["circle back", "low-hanging fruit", "on the same page", "moving forward", "going forward", "at the end of the day", "touch base", "deep dive", "boil the ocean", "move the needle", "get the ball rolling", "hit the ground running", "think outside the box", "take a step back", "double-edged sword", "the elephant in the room", "silver bullet", "no-brainer"]
# house rule: no words that read as LLM-generated boilerplate (check: llm-tell)
LLM_TELL = ["delve", "leverage", "robust", "seamlessly", "seamless", "comprehensive", "streamline", "crucial", "pivotal", "landscape", "tapestry", "testament", "underscore", "it's important to note", "it is important to note", "in today's", "ever-evolving", "game-changer", "navigate the", "unlock"]
CATEGORIES = [("hedge", HEDGE), ("filler", FILLER), ("idiom", IDIOM), ("llm-tell", LLM_TELL)]
PREAMBLE = ["this pr", "this pull request", "this change", "this commit", "this patch", "this issue", "i wanted to", "just a", "opening this", "in this pr", "here is", "here's", "sure", "great question"]
CLOSER = ["let me know", "hope this helps", "feel free", "happy to", "thanks for reading", "don't hesitate", "any questions"]
TRAILERS = ["Generated with", "Co-Authored-By", "Claude-Session", "claude.ai/code/session"]
FENCE_RE, INLINE_CODE_RE = re.compile(r"^\s*```"), re.compile(r"`[^`\n]+`")
SENT_END_RE = re.compile(r"[.!?](?=\s|$)|:(?=\n|$)|\n(?=\s*(?:[|#>]|[-*+] |\d+\. |\n|$))")
ABBR_ENDINGS = ("e.g.", "i.e.", "vs.")
def mask_lines(lines):
    out, in_fence = [], False
    for line in lines:
        if FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(" " * len(line))
        elif in_fence or line.lstrip().startswith("|"):  # table rows are data, not prose
            out.append(" " * len(line))
        else:
            out.append(INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), line))
    return out

# masked whole-doc text + each line's start offset; shared by sentence/keyword checks
def masked_text(lines):
    masked = mask_lines(lines)
    text = "\n".join(masked)
    return text, [0] + list(accumulate(len(l) + 1 for l in masked))

# house rule: ASCII only, no em-dashes/curly quotes/smart punctuation (check: non-ascii)
def check_non_ascii(lines):
    found = []
    for ln, line in enumerate(lines, 1):
        for col, ch in enumerate(line, 1):
            if ch == "\t" or 0x20 <= ord(ch) <= 0x7E or unicodedata.category(ch).startswith("L"):
                continue
            esc = ch.encode("unicode_escape").decode("ascii")
            found.append((ln, "non-ascii", "U+%04X '%s' at column %d" % (ord(ch), esc, col)))
    return found

# house rule: no agent attribution trailer of any kind (check: trailer)
def check_trailer(lines):
    return [(ln, "trailer", "contains '%s'" % t) for ln, line in enumerate(lines, 1)
            for t in TRAILERS if t in line]

# house rule: keep sentences short enough to read in one breath (check: long-sentence)
def check_long_sentence(lines, max_words):
    text, starts = masked_text(lines)
    def flag(found, s, e):
        words = text[s:e].split()
        if len(words) > max_words:
            ln = bisect.bisect_right(starts, s)
            found.append((ln, "long-sentence", "%d words: %s" % (len(words), " ".join(words[:8]))))
    found, start = [], 0
    for m in SENT_END_RE.finditer(text):
        p = m.start()
        if text[:p + 1].lower().endswith(ABBR_ENDINGS):
            continue
        flag(found, start, p + 1)
        start = p + 1
    if text[start:].strip():  # final sentence may lack terminal punctuation, even at EOF
        flag(found, start, len(text))
    return found

# house rule: no throat-clearing preamble before the point (check: preamble)
def check_preamble(lines):
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        low = s.lower()
        hit = next((p for p in PREAMBLE if low.startswith(p)), None)
        return [(i + 1, "preamble", "starts with '%s'" % hit)] if hit else []
    return []

# house rule: no sign-off closer tacked onto the end (check: closer)
def check_closer(lines):
    for i in range(len(lines) - 1, -1, -1):
        s = lines[i].strip()
        if not s:
            continue
        low = s.lower()
        hit = next((c for c in CLOSER if c in low), None)
        return [(i + 1, "closer", "contains '%s'" % hit)] if hit else []
    return []

def check_keywords(lines):
    text, starts = masked_text(lines)
    # \s+ between words matches a line-wrapped or multi-spaced phrase too
    patterns = [(kind, re.compile(r"\b(?:%s)\b" % "|".join(
                r"\s+".join(re.escape(p) for p in w.split())
                for w in sorted(words, key=len, reverse=True)), re.IGNORECASE))
                for kind, words in CATEGORIES]
    found, claimed = [], []
    for kind, pat in patterns:
        for m in pat.finditer(text):
            a, b = m.span()
            if any(x < b and a < y for x, y in claimed):
                continue
            claimed.append((a, b))
            ln = bisect.bisect_right(starts, a)
            found.append((ln, kind, m.group(0)))
    return found

# house rule: run Harper's grammar pass when the binary is available (check: harper)
def run_harper(path, ignore, dialect):
    cmd = (["harper-cli", "lint", "--no-color", "--quiet", "--format", "compact", "--ignore", ignore]
           + (["--dialect", dialect] if dialect else []) + [path])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as e:
        print("harper-cli failed to run: %s" % e, file=sys.stderr)
        return []
    # a title may open with an identifier or a Conventional Commits type, so line 1 skips the capitalization rule
    found = [(int(m.group(1)), "harper", m.group(2)) for line in proc.stdout.splitlines()
             for m in [re.match(r"^[^:]*:(\d+):\d+:\s*(.*)$", line)] if m
             and not (m.group(1) == "1" and "SentenceCapitalization" in m.group(2))]
    return list(dict.fromkeys(found))
def process(label, text, real_path, max_words, harper_ok, ignore, dialect):
    lines = text.splitlines()
    findings = (check_non_ascii(lines) + check_trailer(lines) + check_long_sentence(lines, max_words)
                + check_preamble(lines) + check_closer(lines) + check_keywords(lines))
    if harper_ok:
        path = real_path
        if path is None:
            fd, path = tempfile.mkstemp(suffix=".md")
            with os.fdopen(fd, "w") as f:
                f.write(text)
        findings += run_harper(path, ignore, dialect)
        if real_path is None:
            os.unlink(path)
    return [(label, ln, kind, detail) for ln, kind, detail in findings]
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", default=["-"])
    ap.add_argument("--max-words", type=int, default=25)
    ap.add_argument("--spelling", action="store_true")
    args = ap.parse_args()
    harper_ok = shutil.which("harper-cli") is not None
    if not harper_ok:
        print("harper-cli not found; grammar pass skipped", file=sys.stderr)
    noise = "UseTitleCase,ExpandAlgorithm,ExpandAlloc,ExpandArgument,ExpandBecause,ExpandConfiguration,ExpandControl,ExpandCoordinate,ExpandDecl,ExpandDependencies,ExpandDereference,ExpandDirectory,ExpandForward,ExpandGovt,ExpandMemoryShorthands,ExpandMinimum,ExpandNotification,ExpandParameter,ExpandPeople,ExpandPerformance,ExpandPointer,ExpandPreference,ExpandPrevious,ExpandStandardInputAndOutput,ExpandThough,ExpandThrough,ExpandTimeShorthands,ExpandVulnerability,ExpandWith,ExpandWithout,SplitWords,DisjointPrefixes,Dashes"  # abbreviation expanders fire on config/repo/env; the rest fire on math compounds and forbidden en dashes
    ignore = noise if args.spelling else "SpellCheck," + noise
    dialect = os.environ.get("HARPER_DIALECT", "")
    all_findings = []
    for path in args.files:
        real_path = None if path == "-" else path
        label = "<stdin>" if path == "-" else path
        if path == "-":
            text = sys.stdin.read()
        else:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        all_findings += process(label, text, real_path, args.max_words, harper_ok, ignore, dialect)
    all_findings.sort(key=lambda t: (t[0], t[1]))
    for label, ln, kind, detail in all_findings:
        print("%s:%d: %s: %s" % (label, ln, kind, detail))
    print("clean" if not all_findings else "%d findings" % len(all_findings))
if __name__ == "__main__":
    main()
