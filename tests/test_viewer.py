"""Viewer smoke test (t_bb76d3b7): serve the real out/ + viewer/ and
verify the data contract end to end over http — no browser, no vision.

Runs the same engine the card requires the page to honor: 9 bundles on
the wire, 200s, parseable, and the unsupported-construction facts the
viewer must surface verbatim (glove fingers, shirt sleeves, trouser legs).
"""
import json
import os
import re
import subprocess
import sys
import unittest
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAMILIES = ("dress", "glove", "hat", "hoodie", "shirt", "shorts",
            "skirt", "sock", "trousers")


class ViewerDataSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proc = subprocess.Popen(
            [sys.executable, "-m", "ugc.cli", "serve", "--port", "0"],
            cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if cls.proc.stdout is None:
            raise RuntimeError("serve subprocess has no captured stdout")
        line = cls.proc.stdout.readline().decode("utf-8")
        m = re.search(r"http://127\.0\.0\.1:(\d+)", line)
        if m is None:
            raise RuntimeError("no ready line from serve: %r" % line)
        cls.base = "http://127.0.0.1:%s" % m.group(1)

    @staticmethod
    def _stop(proc):
        proc.terminate()
        proc.wait(timeout=10)
        for stream in (proc.stdout, proc.stderr):
            if stream is not None:
                stream.close()

    @classmethod
    def tearDownClass(cls):
        cls._stop(cls.proc)

    def _fetch(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as resp:
            return resp.status, resp.read()

    def _bundle(self, fam):
        status, body = self._fetch("/out/%s.json" % fam)
        self.assertEqual(status, 200, fam)
        return json.loads(body.decode("utf-8"))

    def test_index_served_and_references_app(self):
        status, body = self._fetch("/viewer/index.html")
        self.assertEqual(status, 200)
        text = body.decode("utf-8")
        self.assertIn("app.js", text)
        self.assertIn("out/", text)

    def test_app_js_served(self):
        status, body = self._fetch("/viewer/app.js")
        self.assertEqual(status, 200)
        self.assertGreater(len(body), 1000)

    def test_all_nine_family_bundles_parse(self):
        for fam in FAMILIES:
            status, body = self._fetch("/out/%s.json" % fam)
            self.assertEqual(status, 200, fam)
            bundle = json.loads(body.decode("utf-8"))
            self.assertEqual(bundle["family"], fam)
            self.assertEqual(bundle["graph"]["version"], 2)
            self.assertTrue(bundle["validation"]["ok"], fam)
            self.assertIn("default_knit", bundle["buildability"])
            self.assertIsNotNone(bundle["plan"], fam)

    def test_unsupported_constructions_surface_verbatim(self):
        """The page's data must carry the unsupported flags it has to show."""
        glove = self._bundle("glove")
        branches = glove["graph"]["joints"]["surface_branches"]
        self.assertEqual(len(branches), 5)
        self.assertTrue(all(j["construction"] == "unsupported"
                            for j in branches))
        shirt = self._bundle("shirt")
        self.assertEqual(
            len(shirt["graph"]["joints"]["surface_branches"]), 2)
        trous = self._bundle("trousers")
        self.assertEqual(
            len(trous["graph"]["joints"]["surface_branches"]), 2)

    def test_glove_plan_records_the_refusal_data(self):
        glove = self._bundle("glove")
        self.assertEqual(glove["plan"]["stats"]["piece_count"], 7)
        self.assertEqual(glove["plan"]["stats"]["machine_verdict"],
                         "UNSIMULATED")
        self.assertIn("I-LOOP", glove["plan"]["notes"][0])

    def test_out_dir_is_gittignore_clean(self):
        gitignore = os.path.join(REPO, ".gitignore")
        if not os.path.isfile(gitignore):
            self.skipTest("no .gitignore")
        with open(gitignore, "r", encoding="utf-8") as fh:
            rules = fh.read().splitlines()
        self.assertTrue(any(r.strip() == "out/" for r in rules),
                        "out/ not gitignored")


if __name__ == "__main__":
    unittest.main()
