"""Backend lowering tests — ugc.backend (t_c97edfbf), cycle 1.

Contract under test:
- validation gates lowering: every broken graph raises
  BackendNotApplicable carrying the specific catalog codes (code x kind);
- the six default_knit op instances lower to reference machine ops,
  one LoweredOp per op instance;
- the op program order is (BFS index of the acted-on primitive, graph op
  id) — insertion-order independent, byte-identical across re-lowerings;
- canonical JSON export with a version guard and a faithful roundtrip.

Machine-op mapping under test (reference verbs, NOT a machine format):
  cast_on -> ("CAST_ON",)          pick_up -> ("PICK_UP", "KNIT")
  bind_off -> ("BIND_OFF",)        short_row_close -> ("SHORT_ROW_CLOSE",)
  graft -> ("GRAFT",)              selvedge_seam -> ("SELVEDGE_SEAM",)
"""
import json
import math
import os
import unittest

from ugc.primitives import (Joint, JointError, KnitOp, OpError, Primitive,
                            PrimitiveError, RegistryError, UGPGraph)
from ugc.validation import validate
from ugc.garments import GARMENT_FAMILIES, build_garment
from ugc.backend import (BackendNotApplicable, LoweredOp, LoweringResult,
                         lower, lowered_from_json, lowered_to_json, lower_ops)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- helpers -----------------------------------------------------------------
def _errs(exc):
    """Cataloged errors off a BackendNotApplicable."""
    return exc.result.errors


def _tube(pid, r1, r2, l, origin=(0, 0, 0), axis=(0, 1, 0)):
    return Primitive(id=pid, kind="tube",
                     params={"r1": r1, "r2": r2, "l": l},
                     origin=origin, axis=axis)


def _cast_on(g, pid, oid):
    g.add_op(KnitOp(id=oid, op="cast_on", consumes=[],
                    produces="%s/rim_start" % pid))


def _bypass_prim(pid, kind, params, origin=(0, 0, 0), axis=(0, 1, 0)):
    """A Primitive that skipped ingest validation (forged-graph simulation)."""
    p = Primitive.__new__(Primitive)
    p.id, p.kind, p.params = pid, kind, dict(params)
    p.origin, p.axis = tuple(origin), tuple(axis)
    p.disposition, p.disposition_state = {}, {}
    return p


def _norm_t(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)


def _grafted_pair(r2=45.0, wale=0.1):
    """Two tubes grafted rim-to-rim; T_RIM widened so I-RIMMATCH stays quiet.
    Default r2=45 makes rim lengths differ ~11% so I-LOOP fires under the
    tiny gauge; pass r2=50 for a grafted pair that lowers clean."""
    g = UGPGraph(tolerances={"T_RIM": 40.0})
    g.add(_tube("ga", 50, 50, 100))
    g.add(_tube("gb", r2, r2, 100))
    _cast_on(g, "ga", "ga_cast_on")
    g.add_op(KnitOp(id="gr_1", op="graft",
                    consumes=["ga/rim_end", "gb/rim_start"]))
    g.open_boundaries = ["gb/rim_end"]
    g.add_joint(Joint(id="j_graft", joint="rim_joint", child="gb",
                      child_boundary="rim_start", parent="ga",
                      parent_boundary="rim_end", construction="grafted",
                      anchor={"feature": "rim", "boundary": "rim_end",
                              "point": (50.0, 100.0, 0.0)},
                      realized_by=["gr_1"]))
    g.gauge = {"wale_mm": wale, "course_mm": 0.1}
    return g


def _knitted_pair_no_cast_on():
    """knitted_in rim joint with no cast_on anywhere -> a/rim_start floats."""
    g = UGPGraph()
    g.add(_tube("ka", 50, 50, 100))
    g.add(_tube("kb", 50, 50, 100))
    g.add_op(KnitOp(id="kp_1", op="pick_up", consumes=["ka/rim_end"],
                    produces="kb/rim_start"))
    g.open_boundaries = ["kb/rim_end"]
    g.add_joint(Joint(id="j_knit", joint="rim_joint", child="kb",
                      child_boundary="rim_start", parent="ka",
                      parent_boundary="rim_end", construction="knitted_in",
                      anchor={"feature": "rim", "boundary": "rim_end",
                              "point": (50.0, 100.0, 0.0)},
                      realized_by=["kp_1"]))
    return g


def _seamed_pair():
    """Two panels joined by a sewn seam; exercises selvedge_seam lowering."""
    g = UGPGraph()
    g.add(_tube("pane_a", 50, 50, 100))
    g.add(_tube("pane_b", 50, 50, 100))
    _cast_on(g, "pane_a", "co_a")
    _cast_on(g, "pane_b", "co_b")
    g.add_op(KnitOp(id="seam_1", op="selvedge_seam",
                    consumes=["pane_a/rim_end", "pane_b/rim_end"]))
    g.add_joint(Joint(id="j_seam", joint="rim_joint", child="pane_b",
                      child_boundary="rim_end", parent="pane_a",
                      parent_boundary="rim_end", construction="selvedge_seam",
                      anchor={"feature": "rim", "boundary": "rim_end",
                              "point": (50.0, 100.0, 0.0)},
                      realized_by=["seam_1"]))
    return g


def _single(op):
    """One tube whose rim_end is sealed by `op` (bind_off/short_row_close)."""
    g = UGPGraph()
    g.add(_tube("solo", 30, 30, 80))
    _cast_on(g, "solo", "solo_cast_on")
    g.add_op(KnitOp(id="seal_1", op=op, consumes=["solo/rim_end"]))
    return g


# --- family lowering ----------------------------------------------------------
FAMILY_MACHINE = {
    "hat": ["CAST_ON", "GRAFT"],
    "sock": ["CAST_ON", "PICK_UP", "KNIT", "GRAFT"],
    "glove": ["CAST_ON", "GRAFT"],
    "skirt": ["CAST_ON"],
    "dress": ["CAST_ON", "PICK_UP", "KNIT"],
    "trousers": ["CAST_ON", "CAST_ON", "CAST_ON"],
    "shorts": ["CAST_ON", "CAST_ON", "CAST_ON"],
    "shirt": ["CAST_ON", "CAST_ON", "CAST_ON"],
    # hood is a root annulus: cast on at the face opening, graft the
    # far rim to the torso neck (AUDIT_HOODIE_CHI.md)
    "hoodie": ["CAST_ON", "CAST_ON", "GRAFT", "CAST_ON", "CAST_ON"],
}


class TestLowerAllFamilies(unittest.TestCase):
    def test_all_nine_families_lower(self):
        for family in GARMENT_FAMILIES:
            g = build_garment(family)
            res = lower(g)
            self.assertIsInstance(res, LoweringResult)
            self.assertIs(res.graph, g)
            self.assertEqual(res.backend, "default_knit")
            self.assertEqual(res.machine_ops, tuple(FAMILY_MACHINE[family]),
                             "family %s machine ops" % family)
            # one LoweredOp per graph op instance — always exactly 1:1
            self.assertEqual(len(res.ops), len(g.ops), family)
            self.assertEqual(res.geometric_validity, "PASS")
            # no gauge anywhere -> I-LOOP is honestly UNVERIFIED, never guessed
            self.assertTrue(any(n.startswith("I-LOOP UNVERIFIED")
                                for n in res.notes), family)
            # per-class report: nothing FAIL, I-LOOP UNVERIFIED
            self.assertEqual(set(res.report["per_class"].values()),
                             {"PASS", "UNVERIFIED"}, family)
            self.assertEqual(res.report["backend"], "default_knit")

    def test_sock_op_program_details(self):
        res = lower(build_garment("sock"))
        self.assertEqual(
            [(lo.graph_op, lo.op, lo.machine_ops, lo.consumes, lo.produces)
             for lo in res.ops],
            [("sock_cast_on", "cast_on", ("CAST_ON",), (),
              "sock_leg/rim_start"),
             ("sock_foot_pick_up", "pick_up", ("PICK_UP", "KNIT"),
              ("sock_leg/rim_end",), "sock_foot/rim_start"),
             ("sock_toe_graft", "graft", ("GRAFT",),
              ("sock_foot/rim_end", "sock_toe/rim"), None)])

    def test_hoodie_order_hood_cast_on_graft_then_sleeves(self):
        # hood is a root annulus cast on at the face opening; its far
        # rim is grafted to the torso neck. bfs index 1 (torso 0, hood
        # 1); op-id tiebreak puts hood_graft before the sleeve cast_ons
        # in the same group.
        res = lower(build_garment("hoodie"))
        self.assertEqual([lo.graph_op for lo in res.ops],
                         ["shirt_cast_on", "hood_cast_on", "hood_graft",
                          "shirt_sleeve_l_cast_on", "shirt_sleeve_r_cast_on"])

    def test_all_six_ops_lowered_somewhere(self):
        seen = set()
        for lo in lower(build_garment("sock")).ops:
            seen.add(lo.op)
        seen.add(lower(_single("bind_off")).ops[1].op)
        seen.add(lower(_single("short_row_close")).ops[1].op)
        seen.add(lower(_seamed_pair()).ops[2].op)
        seen.add(lower(_grafted_pair(r2=50.0)).ops[1].op)
        self.assertEqual(seen, {"cast_on", "bind_off", "short_row_close",
                                "graft", "selvedge_seam", "pick_up"})

    def test_bind_off_and_short_row_machine_ops(self):
        self.assertEqual(lower(_single("bind_off")).machine_ops,
                         ("CAST_ON", "BIND_OFF"))
        self.assertEqual(lower(_single("short_row_close")).machine_ops,
                         ("CAST_ON", "SHORT_ROW_CLOSE"))

    def test_selvedge_seam_machine_ops(self):
        self.assertEqual(lower(_seamed_pair()).machine_ops,
                         ("CAST_ON", "CAST_ON", "SELVEDGE_SEAM"))

    def test_determinism_same_graph_byte_identical(self):
        g = build_garment("sock")
        self.assertEqual(lowered_to_json(lower(g)), lowered_to_json(lower(g)))

    def test_insertion_order_independence(self):
        """Same sock content, hostile insertion order (ops first, prims
        reversed) -> identical lowering JSON to the builder's order."""
        leg = _tube("sock_leg", 55, 50, 250)
        foot = _tube("sock_foot", 50, 45, 180, axis=(1, 0, 0))
        toe = Primitive(id="sock_toe", kind="hemisphere",
                        params={"r": 45}, origin=(180, 0, 0))
        g = UGPGraph()
        g.add_op(KnitOp(id="sock_toe_graft", op="graft",
                        consumes=["sock_foot/rim_end", "sock_toe/rim"]))
        g.add_op(KnitOp(id="sock_foot_pick_up", op="pick_up",
                        consumes=["sock_leg/rim_end"],
                        produces="sock_foot/rim_start"))
        g.add_op(KnitOp(id="sock_cast_on", op="cast_on", consumes=[],
                        produces="sock_leg/rim_start"))
        g.add(toe)
        g.add(foot)
        g.add(leg)
        g.add_joint(Joint(id="sock_j_heel", joint="terminus_continuation",
                          child="sock_foot", child_boundary="rim_start",
                          parent="sock_leg", parent_boundary="rim_end",
                          construction="knitted_in",
                          anchor={"feature": "terminus",
                                  "boundary": "rim_end",
                                  "point": (0.0, 250.0, 0.0)},
                          realized_by=["sock_foot_pick_up"]))
        g.add_joint(Joint(id="sock_j_toe", joint="terminus_continuation",
                          child="sock_toe", child_boundary="rim",
                          parent="sock_foot", parent_boundary="rim_end",
                          construction="grafted",
                          anchor={"feature": "terminus",
                                  "boundary": "rim_end",
                                  "point": (180.0, 0.0, 0.0)},
                          realized_by=["sock_toe_graft"]))
        self.assertEqual(lowered_to_json(lower(g)),
                         lowered_to_json(lower(build_garment("sock"))))

    def test_graph_json_roundtrip_lowering_stable(self):
        g = build_garment("dress")
        g2 = UGPGraph.from_json(g.to_json())
        self.assertEqual(lowered_to_json(lower(g2)), lowered_to_json(lower(g)))

    def test_gauge_silences_loop_note_on_sock(self):
        g = build_garment("sock")
        g.gauge = {"wale_mm": 2.5, "course_mm": 1.6}
        res = lower(g)
        self.assertEqual(res.notes, ())
        self.assertEqual(res.report["per_class"]["I-LOOP"], "PASS")


# --- rejects -------------------------------------------------------------------
class TestLowerRejects(unittest.TestCase):
    def test_severed_sleeve_unreachable(self):
        g = UGPGraph()
        g.add(_tube("torso", 110, 120, 300))
        g.add(_tube("severed_sleeve", 55, 45, 250))
        _cast_on(g, "torso", "t_co")
        _cast_on(g, "severed_sleeve", "s_co")
        with self.assertRaises(BackendNotApplicable) as ctx:
            lower(g)
        codes = [e.as_tuple()[:2] for e in _errs(ctx.exception)]
        self.assertIn(("I-GRAPH", "unreachable"), codes)
        graph_ids = set()
        for e in _errs(ctx.exception):
            graph_ids.update(e.ids)
        self.assertTrue({"torso", "severed_sleeve"} <= graph_ids)

    def test_disconnected_island_lists_orphan(self):
        g = build_garment("hat")
        g.add(_tube("island", 40, 40, 60))
        with self.assertRaises(BackendNotApplicable) as ctx:
            lower(g)
        unreach = [e for e in _errs(ctx.exception)
                   if (e.code, e.kind) == ("I-GRAPH", "unreachable")]
        self.assertEqual(len(unreach), 1)
        self.assertEqual(unreach[0].ids, ("island",))

    def test_radius_cliff_at_continuation(self):
        g = build_garment("sock")
        g.get("sock_foot").params["r1"] = 60.0
        with self.assertRaises(BackendNotApplicable) as ctx:
            lower(g)
        kinds = [(e.code, e.kind) for e in _errs(ctx.exception)]
        self.assertIn(("I-CONT", "radius_step"), kinds)
        step = [e for e in _errs(ctx.exception)
                if (e.code, e.kind) == ("I-CONT", "radius_step")][0]
        self.assertEqual(step.expected, 1.0)
        self.assertEqual(step.actual, 10.0)
        # the rim mismatch is co-reported (same 10 mm shows in lengths)
        self.assertIn(("I-RIMMATCH", "rim_length_mismatch"), kinds)

    def test_boundary_mismatch_beyond_tolerance(self):
        g = build_garment("hat")
        g.get("hat_dome").params["r"] = 100.0
        with self.assertRaises(BackendNotApplicable) as ctx:
            lower(g)
        mismatch = [e for e in _errs(ctx.exception)
                    if (e.code, e.kind) == ("I-RIMMATCH",
                                            "rim_length_mismatch")]
        self.assertEqual(len(mismatch), 1)
        self.assertEqual(mismatch[0].expected, 1.0)
        self.assertAlmostEqual(mismatch[0].actual, 2 * math.pi * 10.0,
                               places=2)

    def test_kinked_continuation_beyond_max_turn(self):
        g = build_garment("sock")
        g.get("sock_foot").axis = _norm_t((1.0, -0.2, 0.0))
        with self.assertRaises(BackendNotApplicable) as ctx:
            lower(g)
        kinds = [(e.code, e.kind) for e in _errs(ctx.exception)]
        self.assertIn(("I-CONT", "axis_turn"), kinds)
        turn = [e for e in _errs(ctx.exception)
                if (e.code, e.kind) == ("I-CONT", "axis_turn")][0]
        self.assertEqual(turn.expected, 90.0)
        self.assertGreater(turn.actual, 90.0)

    def test_nan_param_rejected_fatal(self):
        g = build_garment("skirt")
        g.add(_bypass_prim("fraud", "tube",
                           {"r1": 30, "r2": 30, "l": float("nan")}))
        with self.assertRaises(BackendNotApplicable) as ctx:
            lower(g)
        self.assertTrue(ctx.exception.result.fatal)
        self.assertIn(("I-DEGENERATE", "param_nonfinite"),
                      [e.as_tuple()[:2] for e in _errs(ctx.exception)])

    def test_floating_rim(self):
        with self.assertRaises(BackendNotApplicable) as ctx:
            lower(_knitted_pair_no_cast_on())
        self.assertIn(("I-SEAL", "floating_rim"),
                      [e.as_tuple()[:2] for e in _errs(ctx.exception)])

    def test_loop_mismatch_beyond_t_loops(self):
        with self.assertRaises(BackendNotApplicable) as ctx:
            lower(_grafted_pair())
        loop = [e for e in _errs(ctx.exception)
                if (e.code, e.kind) == ("I-LOOP", "loop_mismatch")]
        self.assertEqual(len(loop), 1)
        self.assertEqual(loop[0].expected, 2.0)
        self.assertGreater(loop[0].actual, 2.0)

    def test_empty_graph_no_root(self):
        with self.assertRaises(BackendNotApplicable) as ctx:
            lower(UGPGraph())
        self.assertIn(("I-GRAPH", "root_count"),
                      [e.as_tuple()[:2] for e in _errs(ctx.exception)])

    def test_non_graph_type_error(self):
        with self.assertRaises(TypeError):
            lower({"primitives": []})
        with self.assertRaises(TypeError):
            lower(None)

    def test_unknown_backend_registry_error(self):
        g = build_garment("hat")
        with self.assertRaises(RegistryError):
            lower(g, backend="nope")

    def test_construction_time_enum_errors_unreachable_to_backend(self):
        with self.assertRaises(JointError):
            Joint(id="j", joint="weld", child="a", child_boundary="rim_start",
                  parent="b", parent_boundary="rim_end",
                  construction="knitted_in",
                  anchor={"feature": "rim", "boundary": "rim_end",
                          "point": (0, 0, 0)})
        with self.assertRaises(OpError):
            KnitOp(id="o", op="crochet", consumes=[])
        with self.assertRaises(PrimitiveError):
            _tube("t", 0, 10, 10)


# --- machine-op vocabulary -----------------------------------------------------
class TestMachineOpVocabulary(unittest.TestCase):
    def test_lower_ops_default_knit(self):
        self.assertEqual(
            lower_ops("default_knit"),
            ("BIND_OFF", "CAST_ON", "GRAFT", "KNIT", "PICK_UP",
             "SELVEDGE_SEAM", "SHORT_ROW_CLOSE"))

    def test_lower_ops_default_sim_same_reference(self):
        self.assertEqual(lower_ops("default_sim"), lower_ops("default_knit"))

    def test_lower_ops_unknown_backend(self):
        with self.assertRaises(RegistryError):
            lower_ops("nope")


# --- JSON contract ---------------------------------------------------------------
class TestLoweringJson(unittest.TestCase):
    def test_roundtrip(self):
        res = lower(build_garment("sock"))
        blob = lowered_to_json(res)
        back = lowered_from_json(blob)
        self.assertEqual(back, res.to_dict())
        data = json.loads(blob)
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["backend"], "default_knit")
        self.assertEqual(data["machine_ops"],
                         ["CAST_ON", "PICK_UP", "KNIT", "GRAFT"])

    def test_version_guard(self):
        with self.assertRaises(ValueError):
            lowered_from_json(json.dumps({"version": 99}))

    def test_open_boundaries_serialized_sorted(self):
        g = build_garment("trousers")
        data = json.loads(lowered_to_json(lower(g)))
        self.assertEqual(data["open_boundaries"],
                         sorted(g.open_boundaries))

    def test_loweredop_shape(self):
        lo = lower(build_garment("hat")).ops[0]
        self.assertIsInstance(lo, LoweredOp)
        self.assertEqual(lo.op, "cast_on")
        self.assertEqual(lo.to_dict(),
                         {"graph_op": "hat_cast_on", "op": "cast_on",
                          "machine_ops": ["CAST_ON"], "consumes": [],
                          "produces": "hat_crown/rim_start"})


if __name__ == "__main__":
    unittest.main()
