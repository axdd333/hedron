"""Benchmark tests — benchmark/benchmark.py (t_ce16ab48).

Contract under test:
- the benchmark measures what the engine actually does: every number in a
  report comes from ugc.primitives / ugc.validation / ugc.backend calls —
  no recomputed geometry, no invented verdicts;
- all nine U-01 families report: graph facts (primitives with boundary
  lengths in mm, joints with construction, declared open boundaries) and
  per-backend buildability + lowered program (op counts, machine verbs);
- honesty is structural: without a gauge loop counts are null and the
  I-LOOP class reads UNVERIFIED / machine_verdict UNSIMULATED; with a
  complete gauge the engine's own loop conversion (Boundary.loops_for)
  appears and the verdict becomes SIMULATED;
- unsupported constructions (glove fingers, trousers legs, shirt sleeves)
  surface verbatim as construction="unsupported" — documented, not hidden;
- a graph that fails validation is a recorded refusal with catalog codes
  (BackendNotApplicable result), never a crash and never a partial report;
- canonical JSON: sorted keys, versioned envelope, byte-identical for
  repeated runs (determinism contract).
"""
import json
import math
import os
import tempfile
import unittest

from ugc.primitives import (INARIANT_CLASSES, Primitive, UGPGraph, KnitOp,
                            RegistryError, buildability_report)
from ugc.validation import validate as V_validate
from ugc.garments import GARMENT_FAMILIES, build_garment
from ugc.backend import lower, BackendNotApplicable

import benchmark.benchmark as bench

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _broken_graph():
    """A graph with an unresolved open-boundary ref (I-SCHEMA) — refuses
    to lower but is a legitimate benchmark datapoint."""
    g = build_garment("skirt", 1.0)
    g.open_boundaries = ["skirt_body/nonexistent"]
    return g


class TestGraphFacts(unittest.TestCase):
    def test_all_nine_families_report(self):
        report = bench.run_benchmark()
        self.assertEqual(sorted(report["families"]), sorted(GARMENT_FAMILIES))
        for fam in GARMENT_FAMILIES:
            facts = report["families"][fam]["graph"]
            g = build_garment(fam, 1.0)
            self.assertEqual(facts["piece_count"], len(list(g)))
            self.assertEqual(facts["joint_count"], len(list(g.joints())))
            self.assertEqual(len(facts["primitives"]), len(list(g)))

    def test_boundary_lengths_come_from_engine(self):
        # every length must equal the engine Boundary value, not a recompute
        report = bench.benchmark_family("hat")
        facts = report["graph"]
        g = build_garment("hat", 1.0)
        by_id = {p.id: p for p in g}
        for pfact in facts["primitives"]:
            p = by_id[pfact["id"]]
            engine = {b.boundary: b.length_mm for b in p.boundaries}
            for bfact in pfact["boundaries"]:
                self.assertEqual(bfact["length_mm"], engine[bfact["boundary"]])
        # spot-check one real number: crown rim_end = 2*pi*r2
        crown = [p for p in facts["primitives"]
                 if p["id"] == "hat_crown"][0]
        rim_end = [b for b in crown["boundaries"]
                   if b["boundary"] == "rim_end"][0]
        self.assertAlmostEqual(rim_end["length_mm"],
                               2.0 * math.pi * 90.0, places=3)

    def test_open_boundaries_passthrough(self):
        self.assertEqual(bench.benchmark_family("skirt")["graph"]
                         ["open_boundaries"], ["skirt_body/rim_end"])
        self.assertEqual(
            bench.benchmark_family("trousers")["graph"]["open_boundaries"],
            ["trousers_hips/rim_end", "trousers_leg_l/rim_end",
             "trousers_leg_r/rim_end"])

    def test_unsupported_construction_surfaced(self):
        # glove fingers / trousers legs are surface_branch with construction
        # "unsupported" — the benchmark reports what the graph declares
        glove = bench.benchmark_family("glove")["graph"]
        finger = [j for j in glove["joints"]
                  if j["child"].startswith("finger_")][0]
        self.assertEqual(finger["joint"], "surface_branch")
        self.assertEqual(finger["construction"], "unsupported")
        self.assertEqual(finger["realized_by"], [])
        trous = bench.benchmark_family("trousers")["graph"]
        legs = [j for j in trous["joints"] if j["child"].endswith("_leg_l")]
        self.assertEqual(legs[0]["construction"], "unsupported")
        # and the finger disks' rims are inert (render caps, §1)
        finger_disk = [p for p in glove["primitives"]
                       if p["id"] == "finger_1"][0]
        self.assertEqual(finger_disk["boundaries"][0]["kind"], "inert")

    def test_joint_constructions_supported_flows(self):
        # supported joints carry their real construction + realizing op
        sock = bench.benchmark_family("sock")["graph"]
        heel = [j for j in sock["joints"] if j["id"] == "sock_j_heel"][0]
        self.assertEqual(heel["joint"], "terminus_continuation")
        self.assertEqual(heel["construction"], "knitted_in")
        self.assertEqual(heel["realized_by"], ["sock_foot_pick_up"])
        toe = [j for j in sock["joints"] if j["id"] == "sock_j_toe"][0]
        self.assertEqual(toe["construction"], "grafted")


class TestHonesty(unittest.TestCase):
    def test_no_gauge_loops_null_and_unverified(self):
        rep = bench.benchmark_family("sock")
        self.assertFalse(rep["graph"]["loop_counts_available"])
        for p in rep["graph"]["primitives"]:
            for b in p["boundaries"]:
                self.assertIsNone(b["loops"])
        self.assertIsNone(rep["graph"]["gauge"])
        self.assertEqual(rep["backends"]["default_knit"]["program"]
                         ["machine_verdict"], "UNSIMULATED")
        self.assertEqual(rep["backends"]["default_knit"]["buildability"]
                         ["per_class"]["I-LOOP"], "UNVERIFIED")

    def test_gauge_scenario_uses_engine_loop_conversion(self):
        gauge = {"wale_mm": 2.5, "course_mm": 3.0}
        rep = bench.benchmark_family("sock", gauge=gauge)
        self.assertTrue(rep["graph"]["loop_counts_available"])
        g = build_garment("sock", 1.0)
        g.gauge = gauge
        engine = g.get("sock_leg").boundary("rim_end").loops_for(gauge)
        leg = [p for p in rep["graph"]["primitives"]
               if p["id"] == "sock_leg"][0]
        rim_end = [b for b in leg["boundaries"]
                   if b["boundary"] == "rim_end"][0]
        self.assertEqual(rim_end["loops"], engine)
        self.assertEqual(rep["backends"]["default_knit"]["buildability"]
                         ["per_class"]["I-LOOP"], "PASS")
        self.assertEqual(rep["backends"]["default_knit"]["program"]
                         ["machine_verdict"], "SIMULATED")

    def test_bad_gauge_rejected(self):
        for bad in ({"wale_mm": -1, "course_mm": 3.0},
                    {"wale_mm": 2.5},
                    {"wale_mm": "x", "course_mm": 3.0},
                    "nope", 42):
            with self.assertRaises(ValueError):
                bench.benchmark_family("hat", gauge=bad)


class TestBackends(unittest.TestCase):
    def test_both_canonical_backends_reported(self):
        rep = bench.benchmark_family("hat")
        self.assertEqual(sorted(rep["backends"]),
                         ["default_knit", "default_sim"])

    def test_buildability_matches_engine_verbatim(self):
        rep = bench.benchmark_family("hat")
        engine = buildability_report(build_garment("hat", 1.0),
                                     "default_knit")
        got = rep["backends"]["default_knit"]["buildability"]
        self.assertEqual(got, engine)

    def test_program_matches_lower(self):
        rep = bench.benchmark_family("hat")
        program = rep["backends"]["default_knit"]["program"]
        res = lower(build_garment("hat", 1.0), "default_knit")
        self.assertEqual(program["op_count"], len(res.ops))
        self.assertEqual([o["graph_op"] for o in program["ops"]],
                         [o.graph_op for o in res.ops])
        self.assertEqual(program["ops_by_kind"],
                         res.stats["ops_by_kind"])
        self.assertEqual(program["machine_ops_by_verb"],
                         res.stats["machine_ops_by_verb"])
        self.assertEqual(program["open_boundaries"],
                         list(res.open_boundaries))

    def test_unknown_backend_fails_fast(self):
        with self.assertRaises(RegistryError):
            bench.benchmark_family("hat", backends=("nonexistent",))


class TestRefusal(unittest.TestCase):
    def test_broken_graph_recorded_not_raised(self):
        facts = bench.benchmark_graph(_broken_graph(), "skirt")
        self.assertFalse(facts["graph"]["validation"]["ok"])
        codes = {e["code"]
                 for e in facts["graph"]["validation"]["errors"]}
        self.assertIn("I-SCHEMA", codes)
        for backend in ("default_knit", "default_sim"):
            entry = facts["backends"][backend]
            self.assertFalse(entry["lowerable"])
            self.assertIn("refusal", entry)
            self.assertNotIn("program", entry)
        # the engine's buildability section still runs and says FAIL
        self.assertEqual(facts["backends"]["default_knit"]["buildability"]
                         ["geometric_validity"], "FAIL")

    def test_refusal_matches_backendnotapplicable(self):
        facts = bench.benchmark_graph(_broken_graph(), "skirt")
        broken = _broken_graph()
        with self.assertRaises(BackendNotApplicable) as ctx:
            lower(broken, "default_knit")
        self.assertEqual(
            facts["backends"]["default_knit"]["refusal"]["error_count"],
            len(ctx.exception.result.errors))
        self.assertEqual(
            facts["backends"]["default_knit"]["refusal"]["message"],
            str(ctx.exception))


class TestReport(unittest.TestCase):
    def test_determinism_bytes(self):
        a = bench.report_to_json(bench.run_benchmark())
        b = bench.report_to_json(bench.run_benchmark())
        self.assertEqual(a, b)
        # and across a full rebuild from the same function calls
        c = bench.report_to_json(bench.run_benchmark())
        self.assertEqual(a, c)

    def test_json_envelope_shape(self):
        blob = bench.report_to_json(bench.run_benchmark())
        data = json.loads(blob)
        self.assertEqual(data["schema_version"], bench.BENCHMARK_VERSION)
        self.assertEqual(data["kind"], "ugc-benchmark")
        self.assertEqual(sorted(data["families"]), sorted(GARMENT_FAMILIES))
        self.assertEqual(sorted(data["backends"]),
                         ["default_knit", "default_sim"])
        # machine_verdict_counts aggregates the families' own verdicts
        verdicts = {}
        for fam in data["families"].values():
            v = fam["backends"]["default_knit"]["program"]["machine_verdict"]
            verdicts[v] = verdicts.get(v, 0) + 1
        self.assertEqual(data["machine_verdict_counts"]["default_knit"],
                         verdicts)

    def test_machine_verdict_counts_all_simulated_with_gauge(self):
        data = json.loads(bench.report_to_json(bench.run_benchmark(
            gauge={"wale_mm": 2.5, "course_mm": 3.0})))
        self.assertEqual(
            data["machine_verdict_counts"]["default_knit"],
            {"SIMULATED": len(GARMENT_FAMILIES)})

    def test_write_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.json")
            out = bench.write_report(path)
            self.assertEqual(out, os.path.abspath(path))
            with open(out) as fh:
                data = json.load(fh)
            self.assertEqual(data["kind"], "ugc-benchmark")


if __name__ == "__main__":
    unittest.main()
