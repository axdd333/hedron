"""Backend lowering tests — cycle 2 (t_c97edfbf): statistical judgment
ledger (garment_stats), package exports, and the ugc CLI.

garment_stats contract (§8.1, "in plain english"):
- exact key set; counts tie to the lowered program, never recomputed
  by feelings: sum(ops_by_kind.values()) == len(ops),
  sum(machine_ops_by_verb.values()) == len(machine_ops);
- machine_verdict: "SIMULATED" only with a complete gauge (both wale_mm
  and course_mm), else "UNSIMULATED" — a partial gauge is not a
  simulation;
- the JSON envelope embeds the same stats dict.
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

import ugc
from ugc.primitives import UGPGraph
from ugc.garments import GARMENT_FAMILIES, build_garment
from ugc.backend import (lower, lowered_to_json, lower_ops, garment_stats)


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_cli(args):
    proc = subprocess.run(
        [sys.executable, "-m", "ugc"] + args, cwd=REPO,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode, proc.stdout.decode("utf-8"), \
        proc.stderr.decode("utf-8")


# --- garment_stats --------------------------------------------------------------
class TestGarmentStats(unittest.TestCase):
    STATS_KEYS = {"piece_count", "joint_count", "ops_by_kind",
                  "machine_ops_by_verb", "open_boundaries", "gauge",
                  "machine_verdict", "notes"}

    def test_sock_stats_shape(self):
        g = build_garment("sock")
        res = lower(g)
        s = res.stats
        self.assertEqual(set(s.keys()), self.STATS_KEYS)
        self.assertEqual(s["piece_count"], 3)
        self.assertEqual(s["joint_count"], 2)
        self.assertEqual(s["open_boundaries"], [])
        self.assertIsNone(s["gauge"])
        self.assertEqual(s["machine_verdict"], "UNSIMULATED")
        self.assertTrue(s["notes"])

    def test_ops_by_kind_sock(self):
        s = lower(build_garment("sock")).stats
        self.assertEqual(s["ops_by_kind"],
                         {"cast_on": 1, "graft": 1, "pick_up": 1})

    def test_machine_ops_by_verb_sock(self):
        s = lower(build_garment("sock")).stats
        self.assertEqual(s["machine_ops_by_verb"],
                         {"CAST_ON": 1, "GRAFT": 1, "KNIT": 1, "PICK_UP": 1})

    def test_stats_tie_to_program_all_families(self):
        for family in GARMENT_FAMILIES:
            g = build_garment(family)
            res = lower(g)
            s = res.stats
            self.assertEqual(sum(s["ops_by_kind"].values()), len(res.ops),
                             family)
            self.assertEqual(sum(s["machine_ops_by_verb"].values()),
                             len(res.machine_ops), family)
            self.assertEqual(s["open_boundaries"],
                             list(res.open_boundaries), family)
            self.assertTrue(s["notes"], family)

    def test_machine_verdict_simulated_with_gauge(self):
        g = build_garment("sock")
        g.gauge = {"wale_mm": 2.5, "course_mm": 1.6}
        s = lower(g).stats
        self.assertEqual(s["machine_verdict"], "SIMULATED")
        self.assertEqual(s["gauge"], {"wale_mm": 2.5, "course_mm": 1.6})

    def test_partial_gauge_is_not_a_simulation(self):
        g = build_garment("skirt")
        g.gauge = {"wale_mm": 2.5}
        s = lower(g).stats
        self.assertEqual(s["machine_verdict"], "UNSIMULATED")

    def test_standalone_garment_stats_matches_result(self):
        g = build_garment("dress")
        res = lower(g)
        self.assertEqual(garment_stats(g, lower(g)), res.stats)
        self.assertEqual(garment_stats(g, res), res.stats)

    def test_stats_in_json_envelope(self):
        data = json.loads(lowered_to_json(lower(build_garment("sock"))))
        self.assertEqual(data["stats"]["piece_count"], 3)
        self.assertEqual(data["stats"]["machine_verdict"], "UNSIMULATED")


# --- package exports --------------------------------------------------------------
class TestPackageExports(unittest.TestCase):
    def test_ugc_exports_backend_api(self):
        for name in ("lower", "LoweringResult", "BackendNotApplicable",
                     "garment_stats", "lower_ops", "lowered_to_json"):
            self.assertTrue(hasattr(ugc, name), name)

    def test_ugc_exports_garment_and_validation_api(self):
        for name in ("GARMENT_FAMILIES", "build_garment", "validate",
                     "validate_strict", "UGPGraph", "Primitive", "KnitOp",
                     "Joint"):
            self.assertTrue(hasattr(ugc, name), name)

    def test_ugc_all_declared_and_resolvable(self):
        self.assertTrue(ugc.__all__)
        self.assertEqual(sorted(ugc.__all__), sorted(set(ugc.__all__)))
        for name in ugc.__all__:
            self.assertTrue(hasattr(ugc, name), name)


# --- CLI ---------------------------------------------------------------------------
class TestCLI(unittest.TestCase):
    def test_cli_family_exits_zero_with_envelope(self):
        rc, out, err = _run_cli(["sock"])
        self.assertEqual(rc, 0, err)
        data = json.loads(out)
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["backend"], "default_knit")
        for key in ("primitives", "joints", "ops"):
            self.assertIn(key, data["graph"])
        self.assertEqual(data["stats"]["piece_count"], 3)
        self.assertTrue(data["machine_ops"])

    def test_cli_family_deterministic_bytes(self):
        rc1, out1, _ = _run_cli(["sock"])
        rc2, out2, _ = _run_cli(["sock"])
        self.assertEqual((rc1, rc2), (0, 0))
        self.assertEqual(out1, out2)

    def test_cli_stats_flag(self):
        rc, out, err = _run_cli(["dress", "--stats"])
        self.assertEqual(rc, 0, err)
        self.assertIn("ops_by_kind", out)
        self.assertIn("machine_verdict", out)
        # --stats: stats ledger only, no program envelope
        self.assertNotIn("machine_ops", json.loads(out))

    def test_cli_all_flag(self):
        rc, out, err = _run_cli(["--all"])
        self.assertEqual(rc, 0, err)
        entries = json.loads(out)
        self.assertEqual([e["family"] for e in entries],
                         sorted(GARMENT_FAMILIES))
        for e in entries:
            self.assertEqual(e["result"]["backend"], "default_knit")
            self.assertIn("stats", e["result"])

    def test_cli_lower_graph_flag(self):
        g = build_garment("hat")
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as fh:
            fh.write(g.to_json())
            path = fh.name
        try:
            rc, out, err = _run_cli(["lower", "--graph", path])
            self.assertEqual(rc, 0, err)
            data = json.loads(out)
            self.assertEqual(data["machine_ops"], ["CAST_ON", "GRAFT"])
            self.assertEqual(data["stats"]["piece_count"], 2)
        finally:
            os.unlink(path)

    def test_cli_rejects_broken_graph_exit_2(self):
        # hat + a severed island: validation must gate the CLI too
        g = build_garment("hat")
        g.add(ugc.Primitive(id="island", kind="tube",
                            params={"r1": 40, "r2": 40, "l": 60},
                            origin=(0, 0, 0)))
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as fh:
            fh.write(g.to_json())
            path = fh.name
        try:
            rc, out, err = _run_cli(["lower", "--graph", path])
            self.assertEqual(rc, 2)
            self.assertIn("BackendNotApplicable", err)
            self.assertIn("I-GRAPH", err)
            self.assertEqual(out, "")
        finally:
            os.unlink(path)

    def test_cli_bogus_family_exits_2_with_families(self):
        rc, out, err = _run_cli(["sockk"])
        self.assertEqual(rc, 2)
        self.assertEqual(out, "")
        for family in GARMENT_FAMILIES:
            self.assertIn(family, err)

    def test_cli_no_args_exits_2(self):
        rc, out, err = _run_cli([])
        self.assertEqual(rc, 2)
        self.assertEqual(out, "")

    def test_cli_unknown_backend_exits_2(self):
        rc, out, err = _run_cli(["hat", "--backend", "brother_knit"])
        self.assertEqual(rc, 2)
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
