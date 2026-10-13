"""Pipeline CLI tests — cycle 3 (t_553af028): ugc/cli.py.

Contract (this cycle's decision log):
- Subcommands: families / build / validate / plan / report.
- Exit codes: 0 success; 1 build/plan refused (invalid graph);
  2 usage error (unknown family, unknown backend, bad JSON, missing file);
  3 lower() itself raised an unexpected exception (programmer bug, not a
  property of the graph).
- JSON on stdout for --json; human text otherwise. The validate/plan/report
  JSON payloads embed the exact library to_dict() objects — no renames, no
  re-shapes — so a CLI consumer sees the same wire shapes as the API.
- build --scale: positive finite float; scale <= 0 or non-numeric is a
  usage error (build_garment raises ValueError).
- Determinism: same input bytes on stdout across runs; no silent state.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_cli(args, cwd=REPO):
    proc = subprocess.run(
        [sys.executable, "-m", "ugc.cli"] + args, cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode, proc.stdout.decode("utf-8"), \
        proc.stderr.decode("utf-8")


def _json_run(args, cwd=REPO):
    """Run the CLI; parse stdout as JSON. Usage errors (rc 2) must have
    empty stdout — an unexpected rc fails the test with stderr attached."""
    rc, out, err = _run_cli(args, cwd=cwd)
    if rc not in (0, 1):
        raise AssertionError(
            "unexpected exit %d for %r\nstderr: %s" % (rc, args, err))
    return rc, json.loads(out), err


def _invalid_graph_dict():
    """Constructible but invalid: two disjoint tubes. from_dict() accepts
    it (params are well-formed); the catalog rejects it (I-GRAPH
    root_count/unreachable, I-SEAL floating_rim) — the exit-1 flavor."""
    return {
        "version": 2,
        "primitives": [
            {"id": "a", "kind": "tube",
             "params": {"r1": 50, "r2": 45, "l": 200},
             "origin": [0, 0, 0], "axis": [0, 1, 0]},
            {"id": "b", "kind": "tube",
             "params": {"r1": 30, "r2": 30, "l": 80},
             "origin": [0, -400, 0], "axis": [0, 1, 0]},
        ],
    }


# ---------------------------------------------------------------------------
# families
# ---------------------------------------------------------------------------
class TestFamiliesSubcommand(unittest.TestCase):
    def test_text_lists_all_nine_families(self):
        rc, out, err = _run_cli(["families"])
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        for fam in ("hat", "sock", "glove", "skirt", "dress",
                    "trousers", "shorts", "shirt", "hoodie"):
            self.assertIn(fam, out)

    def test_json_is_exact_family_tuple(self):
        rc, payload, _ = _json_run(["families", "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(
            payload,
            ["dress", "glove", "hat", "hoodie", "shirt", "shorts",
             "skirt", "sock", "trousers"])


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------
class TestBuildSubcommand(unittest.TestCase):
    def test_build_sock_json_counts(self):
        rc, payload, err = _json_run(["build", "sock", "--json"])
        self.assertEqual(rc, 0, err)
        self.assertEqual(payload["family"], "sock")
        self.assertEqual(payload["scale"], 1.0)
        self.assertEqual(payload["graph"]["version"], 2)
        prim_ids = [p["id"] for p in payload["graph"]["primitives"]]
        self.assertEqual(prim_ids, ["sock_leg", "sock_foot", "sock_toe"])
        self.assertEqual(
            len(payload["graph"]["joints"]["terminus_continuations"]), 2)
        # real params, not placeholders: sock leg is a tube with positive
        # radii in mm
        leg = [p for p in payload["graph"]["primitives"]
               if p["id"] == "sock_leg"][0]
        self.assertGreater(leg["params"]["r1"], 0)

    def test_build_sock_text_is_human_readable(self):
        rc, out, err = _run_cli(["build", "sock"])
        self.assertEqual(rc, 0)
        self.assertIn("sock", out)
        self.assertIn("3", out)          # piece count
        self.assertIn("mm", out)         # units are honest

    def test_build_sock_scale_applies_to_linear_params(self):
        rc, payload, _ = _json_run(["build", "sock", "--scale", "2.5",
                                    "--json"])
        self.assertEqual(rc, 0)
        leg = [p for p in payload["graph"]["primitives"]
               if p["id"] == "sock_leg"][0]
        base = [p for p in
                _json_run(["build", "sock", "--json"])[1]["graph"]
                ["primitives"] if p["id"] == "sock_leg"][0]
        self.assertAlmostEqual(leg["params"]["l"],
                               base["params"]["l"] * 2.5)
        self.assertAlmostEqual(leg["params"]["r1"],
                               base["params"]["r1"] * 2.5)

    def test_build_nonpositive_scale_is_usage_error(self):
        for bad in ("0", "-2", "abc"):
            rc, out, err = _run_cli(["build", "sock", "--scale", bad])
            self.assertEqual(rc, 2, "scale=%r rc=%d err=%s" % (bad, rc, err))
            self.assertIn("scale", err.lower())
            self.assertEqual(out, "")

    def test_build_unknown_family_is_usage_error(self):
        rc, out, err = _run_cli(["build", "corset"])
        self.assertEqual(rc, 2)
        self.assertIn("corset", err)
        self.assertEqual(out, "")

    def test_build_deterministic_bytes(self):
        _, a, _ = _run_cli(["build", "sock", "--json"])
        _, b, _ = _run_cli(["build", "sock", "--json"])
        self.assertEqual(a, b)


# ---------------------------------------------------------------------------
# validate (file/graph-json input)
# ---------------------------------------------------------------------------
class TestValidateSubcommand(unittest.TestCase):
    def test_validate_sock_graph_file_ok(self):
        # a real graph from the sock builder, written to a temp file
        rc, payload, err = _json_run(["build", "sock", "--json"])
        self.assertEqual(rc, 0, err)
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as fh:
            json.dump(payload["graph"], fh)
            path = fh.name
        try:
            rc, payload, err = _json_run(["validate", "--graph", path])
            self.assertEqual(rc, 0, err)
            self.assertTrue(payload["ok"])
            self.assertFalse(payload["fatal"])
            self.assertEqual(payload["errors"], [])
            # 11 v2 classes + 4 v3 topological classes = 15
            self.assertEqual(len(payload["findings"]), 15)
        finally:
            os.unlink(path)

    def test_validate_invalid_graph_exit_1_with_catalog_errors(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as fh:
            json.dump(_invalid_graph_dict(), fh)
            path = fh.name
        try:
            rc, payload, err = _json_run(["validate", "--graph", path])
            self.assertEqual(rc, 1)
            self.assertFalse(payload["ok"])
            codes = {e["code"] for e in payload["errors"]}
            self.assertIn("I-GRAPH", codes)
            kinds = {e["kind"] for e in payload["errors"]}
            self.assertIn("unreachable", kinds)
        finally:
            os.unlink(path)

    def test_validate_inline_json(self):
        blob = json.dumps(build_sock_like_valid_graph())
        rc, payload, err = _json_run(["validate", "--graph-json", blob])
        self.assertEqual(rc, 0, err)
        self.assertTrue(payload["ok"])

    def test_validate_missing_file_is_usage_error(self):
        rc, out, err = _run_cli(["validate", "--graph",
                                 "/nonexistent/nope.json"])
        self.assertEqual(rc, 2)
        self.assertIn("nope.json", err)
        self.assertEqual(out, "")

    def test_validate_bad_json_is_usage_error(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as fh:
            fh.write("{not json")
            path = fh.name
        try:
            rc, out, err = _run_cli(["validate", "--graph", path])
            self.assertEqual(rc, 2)
            self.assertIn("json", err.lower())
        finally:
            os.unlink(path)

    def test_validate_wrong_version_is_usage_error(self):
        bad = _invalid_graph_dict()
        bad["version"] = 99
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as fh:
            json.dump(bad, fh)
            path = fh.name
        try:
            rc, out, err = _run_cli(["validate", "--graph", path])
            self.assertEqual(rc, 2)
            self.assertIn("version", err.lower())
        finally:
            os.unlink(path)

    def test_validate_requires_input(self):
        rc, out, err = _run_cli(["validate"])
        self.assertEqual(rc, 2)
        self.assertIn("graph", err.lower())


def build_sock_like_valid_graph():
    """Real valid graph via the library (kept in this module so tests stay
    self-contained); also used by plan/report classes."""
    from ugc.garments import build_garment
    return build_garment("sock", 1.0).to_dict()


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------
class TestPlanSubcommand(unittest.TestCase):
    def test_plan_sock_text_shows_reference_ops(self):
        rc, out, err = _run_cli(["plan", "sock"])
        self.assertEqual(rc, 0)
        for verb in ("CAST_ON", "PICK_UP", "KNIT", "GRAFT"):
            self.assertIn(verb, out)
        self.assertIn("UNSIMULATED", out)   # honest verdict with no gauge

    def test_plan_sock_json_shape(self):
        rc, payload, err = _json_run(["plan", "sock", "--json"])
        self.assertEqual(rc, 0, err)
        self.assertEqual(payload["backend"], "default_knit")
        self.assertEqual(payload["machine_ops"],
                         ["CAST_ON", "PICK_UP", "KNIT", "GRAFT"])
        self.assertEqual(payload["stats"]["piece_count"], 3)
        self.assertEqual(payload["stats"]["machine_verdict"],
                         "UNSIMULATED")
        self.assertEqual(payload["open_boundaries"], [])

    def test_plan_json_matches_library_bytes(self):
        """CLI plan --json equals lowered_to_json(lower(build_garment(f)))."""
        import ugc
        expected = ugc.lowered_to_json(
            ugc.lower(ugc.build_garment("sock", 1.0)))
        _, out, _ = _run_cli(["plan", "sock", "--json"])
        self.assertEqual(out.strip(), expected.strip())

    def test_plan_gloved_family_json_roundtrip(self):
        rc, payload, err = _json_run(["plan", "glove", "--json"])
        self.assertEqual(rc, 0, err)
        # envelope version + payload shape survives lowered_from_json
        import ugc
        payload2 = ugc.lowered_from_json(
            ugc.lowered_to_json(
                ugc.lower(ugc.build_garment("glove", 1.0))))
        self.assertEqual(payload["machine_ops"],
                         list(payload2["machine_ops"]))

    def test_plan_graph_refuses_invalid_exit_1(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as fh:
            json.dump(_invalid_graph_dict(), fh)
            path = fh.name
        try:
            rc, payload, err = _json_run(["plan", "--graph", path])
            self.assertEqual(rc, 1)
            self.assertIsNone(payload["plan"])
            codes = {e["code"] for e in payload["errors"]}
            self.assertIn("I-GRAPH", codes)
        finally:
            os.unlink(path)

    def test_plan_unknown_backend_is_usage_error(self):
        rc, out, err = _run_cli(["plan", "sock", "--backend", "shima"])
        self.assertEqual(rc, 2)
        self.assertIn("shima", err)
        self.assertEqual(out, "")


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------
class TestReportSubcommand(unittest.TestCase):
    def test_report_sock_text_shows_per_class(self):
        rc, out, err = _run_cli(["report", "sock"])
        self.assertEqual(rc, 0)
        for cls in ("I-DEGENERATE", "I-SCHEMA", "I-LOOP", "I-JOINT"):
            self.assertIn(cls, out)
        self.assertIn("PASS", out)
        self.assertIn("UNVERIFIED", out)

    def test_report_sock_json_per_class(self):
        rc, payload, err = _json_run(["report", "sock", "--json"])
        self.assertEqual(rc, 0, err)
        self.assertEqual(payload["backend"], "default_knit")
        self.assertEqual(payload["geometric_validity"], "PASS")
        self.assertEqual(payload["per_class"]["I-LOOP"], "UNVERIFIED")
        self.assertEqual(payload["per_class"]["I-DEGENERATE"], "PASS")
        self.assertIn("note", payload)

    def test_report_graph_refuses_invalid_exit_1(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as fh:
            json.dump(_invalid_graph_dict(), fh)
            path = fh.name
        try:
            rc, payload, err = _json_run(["report", "--graph", path])
            self.assertEqual(rc, 1)
            self.assertIsNone(payload["report"])
            self.assertFalse(payload["ok"])
        finally:
            os.unlink(path)

    def test_report_graph_valid_full_payload(self):
        blob = json.dumps(build_sock_like_valid_graph())
        rc, payload, err = _json_run(["report", "--graph-json", blob,
                                      "--json"])
        self.assertEqual(rc, 0, err)
        self.assertEqual(payload["geometric_validity"], "PASS")
        self.assertIsNone(payload["report"])   # no lowering requested
        # 11 v2 classes + 4 v3 topological classes = 15
        self.assertEqual(len(payload["findings"]), 15)

    def test_report_exit_1_payload_mirrors_validate(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as fh:
            json.dump(_invalid_graph_dict(), fh)
            path = fh.name
        try:
            _, va, _ = _json_run(["validate", "--graph", path])
            _, ra, _ = _json_run(["report", "--graph", path])
            self.assertEqual(va["errors"], ra["errors"])
            self.assertEqual(va["findings"], ra["findings"])
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# cross-cutting
# ---------------------------------------------------------------------------
class TestCliCrossCutting(unittest.TestCase):
    def test_no_subcommand_shows_usage_exit_2(self):
        rc, out, err = _run_cli([])
        self.assertEqual(rc, 2)
        self.assertIn("usage", err.lower())
        self.assertIn("families", err)      # subcommands listed

    def test_unknown_subcommand_exit_2(self):
        rc, out, err = _run_cli(["frobnicate"])
        self.assertEqual(rc, 2)
        self.assertIn("frobnicate", err)

    def test_help_flags(self):
        for flag in ("-h", "--help"):
            rc, out, err = _run_cli([flag])
            self.assertEqual(rc, 0, err)
            self.assertIn("usage", out.lower())

    def test_per_subcommand_help(self):
        for sub in ("families", "build", "validate", "plan", "report"):
            rc, out, err = _run_cli([sub, "--help"])
            self.assertEqual(rc, 0, err)

    def test_uppercase_family_accepted_via_lowering(self):
        """CLI normalizes family case; 'SOCK' behaves like 'sock'."""
        rc, out, err = _run_cli(["build", "SOCK", "--json"])
        self.assertEqual(rc, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["family"], "sock")

    def test_unexpected_library_failure_exits_3(self):
        """Exit 3 = programmer bug path: the library raises something the
        CLI doesn't classify. Nothing partial on stdout."""
        import io
        from unittest import mock
        import ugc.cli as cli_mod
        buf = io.StringIO()
        with mock.patch.object(cli_mod, "validate",
                               side_effect=ZeroDivisionError("boom")):
            with mock.patch("sys.stderr", new=buf):
                rc = cli_mod.main(["validate", "--graph-json",
                                   json.dumps(build_sock_like_valid_graph())])
        self.assertEqual(rc, 3)
        self.assertIn("ZeroDivisionError", buf.getvalue())


# ---------------------------------------------------------------------------
# build --out (t_bb76d3b7)
# ---------------------------------------------------------------------------
class TestBuildOutFlag(unittest.TestCase):
    def test_build_out_writes_json_payload_file(self):
        out_path = os.path.join(tempfile.mkdtemp(), "sock.json")
        rc, out, err = _run_cli(["build", "sock", "--out", out_path])
        self.assertEqual(rc, 0, err)
        self.assertTrue(os.path.isfile(out_path))
        with open(out_path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        self.assertEqual(payload["family"], "sock")
        self.assertEqual(payload["scale"], 1.0)
        self.assertEqual(payload["graph"]["version"], 2)

    def test_build_out_bytes_match_json_stdout(self):
        out_path = os.path.join(tempfile.mkdtemp(), "spec.json")
        rc, _, err = _run_cli(["build", "sock", "--out", out_path])
        self.assertEqual(rc, 0, err)
        with open(out_path, "r", encoding="utf-8") as fh:
            file_bytes = fh.read()
        _, stdout, _ = _run_cli(["build", "sock", "--json"])
        self.assertEqual(file_bytes, stdout)

    def test_build_out_creates_missing_directories(self):
        base = tempfile.mkdtemp()
        out_path = os.path.join(base, "nested", "dir", "shirt.json")
        rc, out, err = _run_cli(["build", "shirt", "--out", out_path])
        self.assertEqual(rc, 0, err)
        self.assertTrue(os.path.isfile(out_path))

    def test_build_out_names_the_file_on_stdout(self):
        out_path = os.path.join(tempfile.mkdtemp(), "hat.json")
        rc, out, err = _run_cli(["build", "hat", "--out", out_path])
        self.assertEqual(rc, 0, err)
        self.assertIn(out_path, out)


# ---------------------------------------------------------------------------
# serve (t_bb76d3b7)
# ---------------------------------------------------------------------------
class TestServeSubcommand(unittest.TestCase):
    def _start(self, *extra):
        proc = subprocess.Popen(
            [sys.executable, "-m", "ugc.cli", "serve"] + list(extra),
            cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.stdout is None:
            self.fail("serve subprocess has no captured stdout")
        return proc

    @staticmethod
    def _stop(proc):
        proc.terminate()
        proc.wait(timeout=10)
        for stream in (proc.stdout, proc.stderr):
            if stream is not None:
                stream.close()

    def _ready_url(self, proc):
        """Read the serve ready line and return the printed base URL."""
        line = proc.stdout.readline().decode("utf-8")
        m = re.search(r"http://127\.0\.0\.1:(\d+)", line)
        if m is None:
            self.fail("no ready URL on stdout: %r" % line)
        return "http://127.0.0.1:%s" % m.group(1)

    def test_serve_starts_serves_spec_file_and_shuts_down(self):
        root = tempfile.mkdtemp()
        outdir = os.path.join(root, "out")
        os.makedirs(outdir)
        spec = {"family": "sock", "scale": 1.0, "graph": {"version": 2}}
        with open(os.path.join(outdir, "sock.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(spec, fh)
        proc = self._start("--port", "0", "--root", root)
        try:
            url = self._ready_url(proc) + "/out/sock.json"
            with urllib.request.urlopen(url, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                self.assertEqual(json.load(resp), spec)
        finally:
            self._stop(proc)
            self.assertIsNotNone(proc.returncode)

    def test_serve_default_root_is_repo_root_with_viewer(self):
        proc = self._start("--port", "0")
        try:
            base = self._ready_url(proc)
            with urllib.request.urlopen(base + "/viewer/index.html",
                                        timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                self.assertIn(b"app.js", resp.read())
            with urllib.request.urlopen(base + "/out/sock.json",
                                        timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                self.assertEqual(json.load(resp)["family"], "sock")
        finally:
            self._stop(proc)
            self.assertIsNotNone(proc.returncode)


if __name__ == "__main__":
    unittest.main()
