"""RED — loc_accounting contract (t_ce16ab48 deliverable, audited by t_94195dde).

The benchmark card requires programmatic (ast) LOC accounting of the
shared representation vs per-family builders, plus a count of the
negative-path tests. These tests pin that tool before it exists.
"""
import json
import os
import tempfile
import unittest

from benchmark.loc_accounting import (ast_code_lines, negative_path_tests,
                                      repo_counts)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestAstCodeLines(unittest.TestCase):
    def test_counts_statement_lines_not_comments_or_blanks(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "snippet.py")
            with open(p, "w") as fh:
                fh.write("x = 1\n"
                         "# a comment\n"
                         "\n"
                         "y = 2\n")
            self.assertEqual(ast_code_lines(p), 2)

    def test_multiline_statement_is_one_span_of_lines(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "snippet.py")
            with open(p, "w") as fh:
                fh.write("t = (\n"
                         "    1,\n"
                         "    2,\n"
                         ")\n")
            self.assertEqual(ast_code_lines(p), 4)


class TestRepoCounts(unittest.TestCase):
    def test_shared_vs_per_family_measured_and_strong(self):
        counts = repo_counts(REPO)
        for key in ("shared_total", "shared_code", "per_family_total",
                    "per_family_code"):
            self.assertIsInstance(counts[key], int, key)
        self.assertIsInstance(counts["ratio_code"], float, "ratio_code")
        self.assertEqual(counts["shared_files"],
                         ["ugc/primitives.py", "ugc/validation.py",
                          "ugc/backend.py"])
        self.assertEqual(counts["per_family_file"], "ugc/garments.py")
        # the headline claim: shared representation is > 2x the builders
        self.assertGreater(counts["ratio_code"], 2)

    def test_json_shape_is_stable(self):
        blob = json.dumps(repo_counts(REPO), sort_keys=True)
        self.assertIn('"ratio_code"', blob)


class TestNegativePathCount(unittest.TestCase):
    def test_counts_negative_path_tests_across_the_suite(self):
        n = negative_path_tests(REPO)
        self.assertIsInstance(n, int)
        # the deliberate-broken catalog: every must-reject case (DESIGN §7)
        # is exercised; audited at 42 — pin a floor, not an exact number,
        # so adding valid-path tests never breaks this.
        self.assertGreaterEqual(n, 40)


if __name__ == "__main__":
    unittest.main()
