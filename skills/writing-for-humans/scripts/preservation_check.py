#!/usr/bin/env python3
"""Compare an original text and its revision for changes to formulas, citation
keys, labels, references, and qualifier words. Report "a" or "an" swapped with
"the" inside changed lines. Every listed item is a question to check, not an error.

Usage: preservation_check.py ORIGINAL REVISED
Output: one line per difference, then one summary line, for example
  formula removed (original line 4): $p > 3$
  qualifier added (revised line 7): only
  article changed (original line 9, revised line 9): an odd -> the odd
Each category is compared as a multiset, so an item that only moved is not listed.
Exit codes: 0 when the comparison ran, whatever it found; 2 for unreadable
input or bad arguments.

Adapted, with permission, from preservation_check.py in Samuel Grushevsky's WriteBetter skill.
"""
import argparse
import bisect
import difflib
import re
import sys
from collections import Counter

QUALIFIERS = [
    "every", "all", "some", "any", "unique", "generic", "generically", "general",
    "nonzero", "non-zero", "nonempty", "non-empty", "finite", "smooth", "proper",
    "only", "unless", "if", "assume", "assuming", "provided", "not", "never",
    "characteristic", "conditional", "precisely", "therefore", "canonical",
    "natural", "uniquely", "necessarily", "always", "exactly",
]
CATEGORIES = ["formula", "citation key", "label", "reference", "qualifier", "article"]

MATH_ENVS = r"(?:equation|align|alignat|flalign|gather|multline|eqnarray)\*?|displaymath|math|aligned|split"
# One alternation, so math nested in other math (aligned inside $$) counts once.
# Inline $...$ may not cross a blank line, so a stray dollar sign in prose
# cannot swallow the paragraphs after it.
FORMULA_RE = re.compile(
    r"\\begin\{(" + MATH_ENVS + r")\}.*?\\end\{\1\}"
    r"|(?<!\\)\$\$.*?(?<!\\)\$\$"
    r"|(?<!\\)\$(?!\$)(?:(?!\n[ \t]*\n).)+?(?<!\\)\$"
    r"|(?<!\\)\\\[.*?\\\]|(?<!\\)\\\(.*?\\\)",
    re.S,
)


def key_re(names, args=1):
    return re.compile(r"(?<!\\)\\(?:%s)\*?(?:\s*\[[^\]]*\])*" % names + r"\s*\{([^{}]*)\}" * args)


# (category, command, whether the braces may hold a comma-separated list)
KEY_COMMANDS = [
    ("citation key", key_re(r"[A-Za-z]*[Cc]ite[A-Za-z]*"), True),
    ("label", key_re("label"), False),
    ("reference", key_re("ref|eqref|autoref|cref|Cref|pageref|nameref"), True),
    ("reference", key_re("crefrange|Crefrange", 2), False),
]
# A % after an odd run of backslashes is escaped, as in \%. After an even
# run, such as the row break \\, it starts a comment. Group 1 is the comment
# alone, so blanking it keeps the row break.
COMMENT_RE = re.compile(r"(?<!\\)(?:\\\\)*(%.*)")
QUALIFIER_RE = re.compile(r"(?<!\\)\b(?:%s)\b" % "|".join(map(re.escape, QUALIFIERS)), re.I)


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def blank(text, spans):
    chars = list(text)
    for start, end in spans:
        chars[start:end] = re.sub(r"[^\n]", " ", text[start:end])
    return "".join(chars)


def extract(text):
    """Return the items in text as (category, item, line), and the text with
    every comment, formula and keyed command blanked out, which leaves the prose."""
    # Blank comments before matching anything: a delimiter, formula or key
    # inside a comment is not part of the text LaTeX reads.
    text = blank(text, [m.span(1) for m in COMMENT_RE.finditer(text)])
    starts = [0] + [m.end() for m in re.finditer(r"\n", text)]
    found, spans = [], []

    def add(category, item, offset):
        item = " ".join(item.split())
        if item:
            found.append((category, item, bisect.bisect_right(starts, offset)))

    for m in FORMULA_RE.finditer(text):
        add("formula", m.group(0), m.start())
        spans.append(m.span())
    for category, pattern, is_list in KEY_COMMANDS:
        for m in pattern.finditer(text):
            for group in m.groups():
                for key in group.split(",") if is_list else [group]:
                    add(category, key, m.start())
            spans.append(m.span())
    prose = blank(text, spans)
    for m in QUALIFIER_RE.finditer(prose):
        add("qualifier", m.group(0).lower().replace("-", ""), m.start())
    return found, prose


def unmatched(mine, theirs, changed):
    """Match items as multisets, taking surplus items from changed lines first.
    This locates repeated items where they were edited."""
    surplus = Counter(i[:2] for i in mine) - Counter(i[:2] for i in theirs)
    out = []
    for category, item, line in sorted(mine, key=lambda i: (i[2] not in changed, i[2])):
        if surplus[category, item] > 0:
            surplus[category, item] -= 1
            out.append((category, item, line))
    return out


def words(lines, first, last):
    return [(re.sub(r"^\W+|\W+$", "", m.group(0)).lower(), m.group(0), n + 1)
            for n in range(first, last) for m in re.finditer(r"[^\s~]+", lines[n])]


def phrase(ws, n):
    return " ".join(w[1] for w in ws[n:n + 2])


def article_changes(old_lines, new_lines, blocks):
    out = []
    for tag, i, j, k, l in blocks:
        if tag != "replace":
            continue
        old, new = words(old_lines, i, j), words(new_lines, k, l)
        # Align articles together even when adjacent words were also revised.
        old_keys, new_keys = [[None if w[0] in {"a", "an", "the"} else w[0] for w in ws]
                              for ws in (old, new)]
        matcher = difflib.SequenceMatcher(None, old_keys, new_keys, autojunk=False)
        for a, b, size in matcher.get_matching_blocks():
            for offset in range(size):
                x, y = a + offset, b + offset
                if {old[x][0], new[y][0]} in ({"a", "the"}, {"an", "the"}):
                    out.append((old[x][2], new[y][2], "%s -> %s" % (phrase(old, x), phrase(new, y))))
    return out


def report(original, revised):
    old_items, old_prose = extract(original)
    new_items, new_prose = extract(revised)
    blocks = difflib.SequenceMatcher(
        None, original.split("\n"), revised.split("\n"), autojunk=False).get_opcodes()
    old_changed = {n + 1 for tag, i, j, _, _ in blocks if tag != "equal" for n in range(i, j)}
    new_changed = {n + 1 for tag, _, _, k, l in blocks if tag != "equal" for n in range(k, l)}
    rows = [(c, line, 0, "%s removed (original line %d): %s" % (c, line, item))
            for c, item, line in unmatched(old_items, new_items, old_changed)]
    rows += [(c, line, 1, "%s added (revised line %d): %s" % (c, line, item))
             for c, item, line in unmatched(new_items, old_items, new_changed)]
    rows += [("article", a, 2, "article changed (original line %d, revised line %d): %s" % (a, b, text))
             for a, b, text in article_changes(old_prose.split("\n"), new_prose.split("\n"), blocks)]
    rows.sort(key=lambda r: (CATEGORIES.index(r[0]),) + r[1:])
    return [r[3] for r in rows]


def main(argv=None):
    parser = argparse.ArgumentParser(
        usage=argparse.SUPPRESS, description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("original", help="the text before revision")
    parser.add_argument("revised", help="the text after revision")
    args = parser.parse_args(argv)
    try:
        original, revised = read(args.original), read(args.revised)
    except OSError as exc:
        print("preservation_check.py: %s" % exc, file=sys.stderr)
        return 2
    rows = report(original, revised)
    for row in rows:
        print(row)
    if not rows:
        print("no differences")
    else:
        print("%d difference%s" % (len(rows), "" if len(rows) == 1 else "s"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
