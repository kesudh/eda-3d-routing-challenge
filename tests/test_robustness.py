"""Robustness of submission loading, scoring and leaderboard rendering.

Malformed or unusual participant files must be reported as illegal (or ignored,
for optional metadata), never crash the toolkit or silently pass.
"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from m3d.checker import check
from m3d.cli import _load_manifest, _load_runtimes, _render_leaderboard_md
from m3d.model import Instance, Submission, SubmissionFormatError
from m3d.scorer import pareto_frontier, score_submission_set

INTRO = "benchmarks"
HARD = "benchmarks_hard"
REF01 = os.path.join(INTRO, "reference", "case_01.sol.json")
CASE01 = os.path.join(INTRO, "case_01.json")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ref_doc():
    with open(REF01, encoding="utf-8") as fh:
        return json.load(fh)


class TestSubmissionFormat(unittest.TestCase):
    def _mutate(self, fn):
        d = _ref_doc()
        fn(d)
        return d

    def test_malformed_documents_raise_format_error(self):
        bad = {
            "four coordinates": lambda d: d["routes"][0]["edges"][0][0].append(0),
            "two coordinates": lambda d: d["routes"][0]["edges"][0][0].pop(),
            "null coordinate": lambda d: d["routes"][0]["edges"][0][0].__setitem__(0, None),
            "string coordinate": lambda d: d["routes"][0]["edges"][0][0].__setitem__(0, "9"),
            "edge with three vertices": lambda d: d["routes"][0]["edges"][0].append([0, 0, 0]),
            "edge not a list": lambda d: d["routes"][0]["edges"].__setitem__(0, 7),
            "missing edges": lambda d: d["routes"][0].pop("edges"),
            "missing net": lambda d: d["routes"][0].pop("net"),
            "routes null": lambda d: d.__setitem__("routes", None),
        }
        for label, fn in bad.items():
            with self.subTest(label):
                with self.assertRaises(SubmissionFormatError):
                    Submission.from_dict(self._mutate(fn))
        with self.assertRaises(SubmissionFormatError):
            Submission.from_dict([])  # top-level JSON array

    def test_non_integer_coordinates_are_rejected_not_truncated(self):
        # int() used to truncate floats, so an out-of-grid x = -0.9 became 0
        for value in (9.0, 9.5, -0.9, True, float("nan"), float("inf")):
            with self.subTest(value=value):
                d = _ref_doc()
                d["routes"][0]["edges"][0][0][0] = value
                with self.assertRaises(SubmissionFormatError):
                    Submission.from_dict(d)

    def test_float_net_id_is_rejected(self):
        d = _ref_doc()
        d["routes"][0]["net"] = 0.7
        with self.assertRaises(SubmissionFormatError):
            Submission.from_dict(d)

    def test_valid_reference_still_loads_and_is_legal(self):
        res = check(Instance.load(CASE01), Submission.load(REF01))
        self.assertTrue(res.legal)

    def test_utf8_bom_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "case_01.sol.json")
            with open(path, "w", encoding="utf-8-sig") as fh:
                json.dump(_ref_doc(), fh)
            res = check(Instance.load(CASE01), Submission.load(path))
            self.assertTrue(res.legal)


class TestScoringRobustness(unittest.TestCase):
    def test_malformed_case_is_scored_illegal_not_crash(self):
        man = _load_manifest(INTRO)
        with tempfile.TemporaryDirectory() as tmp:
            for c in man["cases"]:
                shutil.copy(os.path.join(INTRO, "reference", f"{c['name']}.sol.json"), tmp)
            bad = _ref_doc()
            bad["routes"][0]["edges"][0][0].append(0)
            with open(os.path.join(tmp, "case_01.sol.json"), "w", encoding="utf-8") as fh:
                json.dump(bad, fh)
            s = score_submission_set(man, INTRO, tmp, "x", {})
            self.assertFalse(s.complete)
            self.assertEqual(s.n_legal, len(man["cases"]) - 1)
            case01 = [c for c in s.cases if c.case == "case_01"][0]
            self.assertTrue(any("unreadable" in r for r in case01.reasons))

    def test_partial_runtime_does_not_count_toward_pareto(self):
        man = _load_manifest(HARD)
        d = os.path.join("submissions", "hard", "negotiated")
        full = score_submission_set(man, HARD, d, "full", _load_runtimes(d))
        partial = score_submission_set(man, HARD, d, "partial", {"case_01": 0.5})
        self.assertIsNotNone(full.total_runtime)
        self.assertIsNone(partial.total_runtime)
        self.assertNotIn("partial", pareto_frontier([full, partial]))

    def test_runtime_total_is_independent_of_python_version(self):
        # plain float sum() rounds differently on 3.12+ (these values sum to
        # 0.9999999999999999 before, 1.0 after); the total must match everywhere
        man = _load_manifest(HARD)
        d = os.path.join("submissions", "hard", "negotiated")
        rts = {c["name"]: 0.1 for c in man["cases"]}
        rts["case_01"] = 0.1 * 2
        s = score_submission_set(man, HARD, d, "x", rts)
        self.assertEqual(s.total_runtime, math.fsum(rts.values()))

    def test_invalid_runtime_values_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "runtime.json"), "w", encoding="utf-8") as fh:
                fh.write('{"a": 1.5, "b": -3, "c": NaN, "d": Infinity, "e": true, '
                         '"f": "2", "g": null, "h": 0}')
            self.assertEqual(_load_runtimes(tmp), {"a": 1.5, "h": 0.0})
            with open(os.path.join(tmp, "runtime.json"), "w", encoding="utf-8") as fh:
                fh.write("[1, 2, 3]")
            self.assertEqual(_load_runtimes(tmp), {})


class TestLeaderboardRendering(unittest.TestCase):
    def _root_with_entries(self, tmp, metas):
        hard = os.path.join(tmp, "hard")
        for name, meta in metas.items():
            shutil.copytree(os.path.join("submissions", "hard", "negotiated"),
                            os.path.join(hard, name))
            with open(os.path.join(hard, name, "meta.json"), "w", encoding="utf-8") as fh:
                fh.write(meta)
        return tmp

    def test_bad_meta_does_not_crash_and_cells_are_escaped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root_with_entries(tmp, {
                "list_meta": "[]",
                "string_meta": '"Jane Doe"',
                "pipe_author": '{"author": "Jane | Doe\\nSmith"}',
            })
            md = _render_leaderboard_md(root)
            rows = [l for l in md.splitlines() if l.startswith("| ") and "rank" not in l]
            self.assertEqual(len(rows), 3)
            for row in rows:
                # 9 columns -> 10 unescaped pipes per row
                unescaped = row.replace("\\|", "")
                self.assertEqual(unescaped.count("|"), 10, row)
            self.assertIn("Jane \\| Doe Smith", md)


class TestVerifyScript(unittest.TestCase):
    def test_reports_per_net_reasons_and_runs_from_any_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = os.path.join(tmp, "intro", "broken")
            os.makedirs(entry)
            bad = _ref_doc()
            bad["routes"][0]["edges"].pop()  # disconnect a pin of net 0
            with open(os.path.join(entry, "case_01.sol.json"), "w", encoding="utf-8") as fh:
                json.dump(bad, fh)
            p = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "verify_submissions.py"), tmp],
                               cwd=tmp, capture_output=True, text=True)
            self.assertEqual(p.returncode, 1)
            self.assertNotIn("unknown tier", p.stdout)
            self.assertIn("net 0:", p.stdout)


if __name__ == "__main__":
    unittest.main()
