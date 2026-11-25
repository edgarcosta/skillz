import copy
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("handback-page.py")


class OptionLines(HTMLParser):
    def __init__(self, output):
        super().__init__()
        self.depth = 0
        self.options = None
        self.lines = []
        self.parts = []
        self.feed(output)

    def handle_starttag(self, tag, attrs):
        if tag in ("meta", "input"):
            return
        self.depth += 1
        if ("class", "options") in attrs:
            self.options = self.depth

    def handle_endtag(self, tag):
        if self.options is not None:
            if self.depth == self.options + 1:
                self.lines.append("".join(self.parts).strip())
                self.parts = []
            elif self.depth == self.options:
                self.options = None
        self.depth -= 1

    def handle_data(self, data):
        if self.options is not None:
            self.parts.append(data)


class FinishedCardsTest(unittest.TestCase):
    def test_jury_recommendation_accepts_its_display_label(self):
        step = {
            "id": "choice", "num": 1, "kind": "decision", "status": "done",
            "title": "Choose a path", "answer": "Confirmed B",
            "options": [{"id": "B", "label": "Second path"}],
            "jury": {
                "lines": [{"juror": "amber", "model": "reviewer", "pick": "PICK choice: B",
                           "reason": "REASON choice: Keep the bounded search."}],
                "support": [{"juror": "amber", "option": "B", "conditional": False, "outcome": ""}],
            },
        }
        for prefix, marker in (("Mine:", "recommended"), ("Mine (no vote):", "Mine")):
            step["recommendation"] = prefix + " B: Keep the bounded search."
            for markdown in (False, True):
                with self.subTest(prefix=prefix, markdown=markdown):
                    output = self.render(step, markdown)
                    options = ([line[2:] for line in output.splitlines() if line.startswith("- ")]
                               if markdown else OptionLines(output).lines)
                    self.assertIn(marker, options[0])
                    self.assertEqual(output.count("Mine (no vote):"), int(marker == "Mine"))
                    self.assertEqual(output.count("B: Keep the bounded search."), 1)

    def test_options_show_stored_support_and_keep_full_evidence_below(self):
        step = {
            "id": "choice", "num": 1, "kind": "decision", "status": "open",
            "title": "Choose a path", "recommendation": "Use B: Keep the bounded search.",
            "options": [{"id": oid, "label": label} for oid, label in
                        [("A", "First path"), ("B", "Second path"), ("C", "Third path")]],
            "jury": {
                "lines": [
                    {"juror": "amber", "model": "reviewer", "pick": "PICK choice: A",
                     "reason": "REASON choice: Retain the public API."},
                    {"juror": "blue", "model": "reviewer",
                     "pick": "PICK choice: B if cost < 5 & results match",
                     "reason": "REASON choice: Bound the search cost."},
                    {"juror": "coral", "model": "reviewer", "pick": "PICK choice: A or B",
                     "reason": "REASON choice: This source has no resolved support."},
                    {"juror": "denim", "model": "reviewer", "pick": "PICK choice: A",
                     "reason": "REASON choice: Keep existing callers working."},
                ],
                "support": [
                    {"juror": "amber", "option": "A", "conditional": False, "outcome": ""},
                    {"juror": "blue", "option": "B", "conditional": True, "outcome": ""},
                    {"juror": "coral", "option": None, "conditional": False,
                     "outcome": "unmatched pick"},
                    {"juror": "denim", "option": "A", "conditional": False, "outcome": ""},
                ],
            },
        }
        for status in ("open", "done"):
            step.update(status=status, answer="Confirmed B")
            for markdown in (False, True):
                with self.subTest(status=status, markdown=markdown):
                    output = self.render(step, markdown)
                    options = ([line[2:] for line in output.splitlines() if line.startswith("- ")]
                               if markdown else OptionLines(output).lines)
                    self.assertEqual(len(options), 3)
                    self.assertIn("Amber", options[0])
                    self.assertIn("Denim", options[0])
                    self.assertNotIn("coral", " ".join(options))
                    self.assertIn("Blue (if ...", options[1])
                    self.assertIn("recommended", options[1])
                    self.assertNotIn("Mine", options[0])
                    self.assertEqual(options[2], "C: Third path")
                    self.assertIn("cost < 5 & results match" if markdown else
                                  "cost &lt; 5 &amp; results match", output)
                    self.assertEqual(output.count(step["recommendation"]), 1)
                    self.assertLess(output.index("Third path"), output.index(step["recommendation"]))
                    self.assertLess(output.index(step["recommendation"]), output.index("Juror advice"))
                    evidence = output.split("Juror advice", 1)[1]
                    for row in step["jury"]["lines"]:
                        for field in ("pick", "reason"):
                            self.assertIn(row[field] if markdown else escape(row[field]), evidence)

    def test_recommendation_markers_belong_to_the_named_option(self):
        step = {
            "id": "choice", "num": 1, "kind": "decision", "status": "open",
            "title": "Choose a path",
            "options": [{"id": "A", "label": "First path"}, {"id": "B", "label": "Second path"}],
        }
        for status in ("open", "done"):
            step.update(status=status, answer="Confirmed B")
            for recommendation, option, detail in [
                ("B", "B", False), ("Use B", "B", False),
                ("B: Keep the bounded search.", "B", True),
                ("Provisional B; keep A available.", "B", True),
                ("Panel majority: B, 3 of 4", "B", True),
                ("Panel majority: none, 2 for A and 2 for B", None, True),
                ("Leave a note about A or B.", None, True),
            ]:
                step["recommendation"] = recommendation
                for markdown in (False, True):
                    with self.subTest(status=status, markdown=markdown, recommendation=recommendation):
                        output = self.render(step, markdown)
                        options = ([line[2:] for line in output.splitlines() if line.startswith("- ")]
                                   if markdown else OptionLines(output).lines)
                        self.assertEqual(len(options), 2)
                        self.assertEqual(options[0], "A: First path")
                        self.assertEqual(("panel majority" if recommendation.startswith("Panel majority:") else "recommended") in options[1], option == "B")
                        self.assertNotIn("Backed by", " ".join(options))
                        self.assertNotIn("Mine", " ".join(options))
                        if detail:
                            self.assertEqual(output.count(recommendation), 1)
                            self.assertLess(output.index("Second path"), output.index(recommendation))
                        else:
                            self.assertNotIn("Recommendation:", output)

    def test_jury_options_recover_punctuated_picks_and_conditions(self):
        step = {
            "id": "choice", "num": 1, "kind": "decision", "status": "open",
            "title": "Choose a path", "recommendation": "Panel majority: C, 4 of 4",
            "options": [{"id": "A", "label": "First path"}, {"id": "C", "label": "Third path"}],
            "jury": {"label": None, "lines": [
                {"juror": juror, "model": "reviewer", "pick": "PICK: " + pick,
                 "reason": "REASON: Keep a recoverable public table."}
                for juror, pick in [
                    ("Sol", "C, provided the public downloads work."),
                    ("Astra", "C, publishing once public downloads are verified."),
                    ("Fable", "C, conditioned on a verified public download."),
                    ("Opus", "C: publish a pinned table.")]],
            },
        }
        for status in ("open", "done"):
            step.update(status=status, answer="Confirmed C")
            for stored in (False, True):
                if stored:
                    step["jury"]["support"] = [
                        {"juror": row["juror"], "option": None, "conditional": False,
                         "outcome": "unmatched pick"} for row in step["jury"]["lines"]]
                else:
                    step["jury"].pop("support", None)
                for markdown in (False, True):
                    with self.subTest(status=status, stored=stored, markdown=markdown):
                        output = self.render(step, markdown)
                        options = ([line[2:] for line in output.splitlines() if line.startswith("- ")]
                                   if markdown else OptionLines(output).lines)
                        self.assertEqual(options[0], "A: First path")
                        for juror in ("Sol", "Astra", "Fable"):
                            self.assertIn(juror + " (if ...", options[1])
                        self.assertIn("Opus", options[1])
                        self.assertIn(" -- ", options[1])
                        self.assertIn("panel majority", options[1])
                        self.assertNotIn("Mine", output)
                        self.assertNotIn("unmatched pick", output)

    def test_converter_retains_conditions_on_punctuated_picks(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            directory = Path(directory)
            step = {
                "id": "choice", "num": 1, "kind": "decision", "status": "open",
                "title": "Choose a path", "recommendation": "A",
                "options": [{"id": "A", "label": "First path"}],
                "jury": {"label": None, "lines": [{"juror": "Sol", "model": "reviewer"}]},
            }
            state = {"title": "Decision tracker", "goal": "Pick a path", "now": "Review choices",
                     "updated": "2026-11-15", "steps": [step], "after": [], "sessions": [],
                     "done": [], "side_notes": []}
            source, question, reply, output = [directory / name for name in
                                              ("state.json", "question.txt", "reply.txt", "out.json")]
            source.write_text(json.dumps(state))
            question.write_text("Choose a recoverable home.")
            picks = ("A if downloads work", "A, provided downloads work", "A, on condition that downloads work",
                         "A, with ownership confirmed before transfer", "A, conditional on downloads working",
                         "A - use the public table, subject to proving access",
                         "A: recommend stopping only after acceptance",
                         "A; reopen as B when a model-lookup caller appears")
            for pick, fence in [(pick, "") for pick in picks] + [("A", "```"), ("A", "```text")]:
                with self.subTest(pick=pick, fence=fence):
                    block = "PICK: " + pick + "\nREASON: Keep the table recoverable.\n"
                    if fence:
                        block = fence + "\n" + block + "```\nPICK: A\nREASON: Ignore later evidence.\n"
                    reply.write_text(block + "END\n")
                    result = subprocess.run([sys.executable, "-B", str(SCRIPT), "jury", str(source),
                        "--question", str(question), "--sentinel", "END", "--reply", "Sol=" + str(reply),
                        "-o", str(output)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    support = json.loads(output.read_text())["steps"][0]["jury"]["support"]
                    self.assertEqual(support, [{"juror": "Sol", "option": "A",
                        "conditional": pick != "A" and not pick.startswith("A:"), "outcome": ""}])

    def test_proposed_option_names_its_endorser_once(self):
        step = {
            "id": "choice", "num": 1, "kind": "decision", "status": "done",
            "title": "Choose a path", "recommendation": "B", "answer": "Confirmed B",
            "options": [{"id": "A", "label": "First path"},
                        {"id": "B", "label": "Second path", "proposed": True}],
            "jury": {"lines": [{"juror": "Opus", "model": "reviewer",
                "pick": "PICK choice: new: Second path", "reason": "REASON choice: Keep it recoverable."}]},
        }
        for markdown in (False, True):
            with self.subTest(markdown=markdown):
                output = self.render(step, markdown)
                options = ([line[2:] for line in output.splitlines() if line.startswith("- ")]
                           if markdown else OptionLines(output).lines)
                self.assertEqual(options[1].count("Opus"), 1)
                self.assertIn("Proposed by: Opus; recommended", options[1])

    def test_finished_cards_keep_their_content_collapsed(self):
        decision = {
            "id": "choice", "num": 1, "kind": "decision", "status": "done",
            "title": "Choose a path", "answer": "Confirmed A", "context": "Choice context",
            "recommendation": "Use A", "options": [{"id": "A", "label": "First path"}],
            "question": "Which path?", "ruling": "Use the first path",
            "built": ["First path implemented"], "notes": {"n": "My note"},
            "replies": {"n": "Note answered"},
        }
        jury = copy.deepcopy(decision)
        jury["jury"] = {"lines": [{
            "juror": "amber", "model": "reviewer", "pick": "PICK choice: A",
            "reason": "REASON choice: Shortest path",
        }]}
        command = {
            "id": "run", "num": 1, "kind": "command", "status": "done",
            "title": "Run a command", "result": "Output checked", "where": "Local shell",
            "why": "Produce output", "success": "Output exists", "command": "echo output",
        }
        cases = [
            (command, ["Output checked", "Local shell", "Produce output", "Output exists", "echo output"]),
            ({k: command[k] for k in ("id", "num", "kind", "status", "title", "result")}, ["Output checked"]),
            (decision, ["Confirmed A", "Choice context", "Which path?", "recommended", "First path",
                        "Use the first path", "First path implemented", "My note", "Note answered"]),
            ({k: decision[k] for k in ("id", "num", "kind", "status", "title", "answer")}, ["Confirmed A"]),
            (jury, ["Confirmed A", "Which path?", "Amber; recommended", "PICK choice: A", "REASON choice: Shortest path",
                    "Use the first path", "First path implemented", "My note", "Note answered"]),
        ]
        for markdown in (False, True):
            for step, expected in cases:
                with self.subTest(markdown=markdown, kind=step["kind"], fields=sorted(step)):
                    output = self.render(step, markdown)
                    done = output.split("## Done so far" if markdown else '<div id="done-steps">', 1)[1]
                    self.assertIn("<details", done)
                    self.assertNotIn("<details open", done)
                    summary, body = done.split("</summary>", 1)
                    self.assertIn("1. " + step["title"], summary)
                    for value in expected:
                        self.assertNotIn(value, summary)
                        self.assertIn(value, body)
                    self.assertNotIn("<button", body)
                    self.assertNotIn("<form", body)

    def test_open_cards_stay_expanded(self):
        step = {
            "id": "pending", "num": 1, "kind": "decision", "status": "open",
            "title": "Choose a path", "recommendation": "Use A",
            "options": [{"id": "A", "label": "First path"}],
        }
        self.assertIn('<details open class="step"', self.render(step, False))
        self.assertIn("Reply in chat with the step number", self.render(step, True))

    def render(self, step, markdown):
        state = {
            "title": "Release tracker", "goal": "Finish release", "now": "Review steps",
            "updated": "2026-11-12", "steps": [step], "after": [], "sessions": [],
            "done": [], "side_notes": [],
        }
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            source = Path(directory) / "state.json"
            output = Path(directory) / ("page.md" if markdown else "page.html")
            source.write_text(json.dumps(state), encoding="utf-8")
            command = [sys.executable, "-B", str(SCRIPT), "render", str(source), "-o", str(output)]
            if markdown:
                command.append("--md")
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return output.read_text(encoding="utf-8")


class ReadResponsesTest(unittest.TestCase):
    def test_read_matches_exported_filenames_to_tilde_ids(self):
        state = {
            "title": "Decision tracker", "goal": "Read decisions", "now": "Review picks",
            "updated": "2026-11-15", "after": [], "sessions": [], "done": [], "side_notes": [],
            "steps": [
                {"id": sid, "num": num, "kind": "decision", "status": "open",
                 "title": "Choose a path", "recommendation": "Use B",
                 "options": [{"id": "B", "label": "Second path"},
                             {"id": "C", "label": "Third path"}]}
                for num, sid in [(71, "census-2qt.93.7~Q"), (72, "census-co0.38.14~Q"),
                                 (73, "census-ohe.8~Q"), (74, "ordinary")]
            ],
        }
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            source = Path(directory) / "state.json"
            source.write_text(json.dumps(state), encoding="utf-8")
            db = Path(directory) / "db"
            picks = db / "picks"
            picks.mkdir(parents=True)
            for filename, option in [("census-2qt.93.7@Q.json", "B"),
                                     ("census-co0.38.14@Q.json", "B"),
                                     ("census-ohe.8@Q.json", "C"), ("ordinary.json", "B")]:
                (picks / filename).write_text(json.dumps({"option": option}), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), "read", str(source), str(db)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "71. census-2qt.93.7~Q: pick B\n"
                             "72. census-co0.38.14~Q: pick B\n"
                             "73. census-ohe.8~Q: pick C\n"
                             "74. ordinary: pick B\n")


if __name__ == "__main__":
    unittest.main()
