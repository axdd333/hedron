"""UGC-01 constraint checker tests: ugc.validation (t_ff7ea486).

Test-first against DESIGN.md spec v2 §6/§7 and the card contract:
validate(graph) -> ValidationResult(.ok, .errors[]) with a stable
error-code catalog (code = spec I-* class, kind = catalog slug), expected
vs actual numbers, deterministic ordering, no LLM anywhere.

Cycles (TDD, RED+GREEN per cycle):
  C1  API shape, clean sweep (fixture + 9 garment families), determinism,
      degenerate pre-scan (fatal-first), schema refs, axis, connectivity
  C2  rim/cont/branch/loop/seal/joint mapping, numeric expected/actual,
      tolerance override, catalog completeness
"""
import math
import unittest

import ugc.primitives as P
import ugc.validation as V
from ugc.garments import build_garment, GARMENT_FAMILIES


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
def _tube(pid, r1=10, r2=10, l=100, origin=(0, 0, 0), axis=(0, 1, 0)):
    return P.Primitive(id=pid, kind="tube",
                       params={"r1": r1, "r2": r2, "l": l},
                       origin=origin, axis=axis)


def _cast_on(g, pid, op_id):
    g.add_op(P.KnitOp(id=op_id, op="cast_on", consumes=[],
                      produces="%s/rim_start" % pid))


def _pick_up(g, op_id, parent, child):
    g.add_op(P.KnitOp(id=op_id, op="pick_up",
                      consumes=["%s/rim_end" % parent],
                      produces="%s/rim_start" % child))


def _cont_joint(gid, child, parent, point, realized_by):
    return P.Joint(id=gid, joint="terminus_continuation", child=child,
                   child_boundary="rim_start", parent=parent,
                   parent_boundary="rim_end", construction="knitted_in",
                   anchor={"feature": "terminus", "boundary": "rim_end",
                           "point": point},
                   realized_by=realized_by)


def _rim_joint(gid, child, parent, point, realized_by,
               child_boundary="rim_start", construction="knitted_in",
               feature="rim"):
    return P.Joint(id=gid, joint="rim_joint", child=child,
                   child_boundary=child_boundary, parent=parent,
                   parent_boundary="rim_end", construction=construction,
                   anchor={"feature": feature, "boundary": "rim_end",
                           "point": point},
                   realized_by=realized_by)


def _cont_graph(child_r2=10):
    """Root tube a + knitted-in continuation b at the terminus (clean)."""
    a = _tube("a")
    b = _tube("b", r1=child_r2, r2=child_r2, l=50, origin=(0, 100, 0))
    g = P.UGPGraph(primitives=[a, b], open_boundaries=["b/rim_end"])
    _cast_on(g, "a", "cast_on_1")
    _pick_up(g, "pick_up_1", "a", "b")
    g.add_joint(_cont_joint("j1", "b", "a", (0, 100, 0), ["pick_up_1"]))
    return g


def _kinds(result):
    return [(e.code, e.kind) for e in result.errors]


def _by_kind(result, kind):
    return [e for e in result.errors if e.kind == kind]


# ---------------------------------------------------------------------------
# C1 — API shape
# ---------------------------------------------------------------------------
class TestValidationAPI(unittest.TestCase):
    def test_validate_returns_result_not_exception(self):
        r = V.validate(_cont_graph())
        self.assertIsInstance(r, V.ValidationResult)
        self.assertTrue(r.ok)
        self.assertEqual(r.errors, [])
        self.assertEqual(len(r.findings), len(P.INARIANT_CLASSES))

    def test_clean_graph_has_every_class_pass(self):
        r = V.validate(_cont_graph())
        statuses = {f.invariant: f.status for f in r.findings}
        for inv in P.INARIANT_CLASSES:
            self.assertNotEqual(statuses.get(inv), "FAIL", inv)

    def test_clean_graph_engine_verdict_pass_or_unverified(self):
        # I-LOOP is UNVERIFIED for default_knit graphs (no loop accounting
        # in the checker itself); the engine must never FAIL a clean graph
        r = V.validate(_cont_graph())
        loop = [f for f in r.findings if f.invariant == "I-LOOP"][0]
        self.assertIn(loop.status, ("PASS", "UNVERIFIED"))

    def test_all_nine_garment_families_validate_clean(self):
        for fam in GARMENT_FAMILIES:
            r = V.validate(build_garment(fam))
            self.assertTrue(r.ok, "%s: %s" % (fam, _kinds(r)))
            self.assertEqual(r.errors, [], fam)

    def test_error_record_shape(self):
        g = _cont_graph()
        g.get("a").params["r1"] = 0          # mutation: constructor forbids
        r = V.validate(g)
        self.assertFalse(r.ok)
        e = r.errors[0]
        for attr in ("code", "kind", "ids", "message", "expected", "actual"):
            self.assertTrue(hasattr(e, attr), attr)
        self.assertIsInstance(e.ids, tuple)
        self.assertIsInstance(e.message, str)

    def test_determinism_same_graph_same_errors_same_order(self):
        g1 = _cont_graph(child_r2=20)
        g2 = _cont_graph(child_r2=20)
        r1 = V.validate(g1)
        r2 = V.validate(g2)
        self.assertEqual([e.as_tuple() for e in r1.errors],
                         [e.as_tuple() for e in r2.errors])
        self.assertFalse(r1.ok)


# ---------------------------------------------------------------------------
# C1 — degenerate rejection (fatal pre-scan, card class 5)
# ---------------------------------------------------------------------------
class TestDegeneratePreScan(unittest.TestCase):
    def _mutated(self, mutator):
        g = _cont_graph()
        mutator(g)
        return V.validate(g)

    def test_r_zero_mutation(self):
        r = self._mutated(lambda g: g.get("a").params.__setitem__("r1", 0))
        self.assertFalse(r.ok)
        self.assertIn(("I-DEGENERATE", "param_nonpositive"), _kinds(r))
        self.assertEqual(_by_kind(r, "param_nonpositive")[0].ids, ("a",))

    def test_negative_length_mutation(self):
        r = self._mutated(lambda g: g.get("a").params.__setitem__("l", -3))
        self.assertFalse(r.ok)
        self.assertIn(("I-DEGENERATE", "param_nonpositive"), _kinds(r))

    def test_nan_param(self):
        r = self._mutated(lambda g: g.get("a").params.__setitem__("r2",
                                                                  float("nan")))
        self.assertIn(("I-DEGENERATE", "param_nonfinite"), _kinds(r))

    def test_inf_param(self):
        r = self._mutated(lambda g: g.get("a").params.__setitem__("r2",
                                                                  float("inf")))
        self.assertIn(("I-DEGENERATE", "param_nonfinite"), _kinds(r))

    def test_non_numeric_param(self):
        r = self._mutated(lambda g: g.get("a").params.__setitem__("r2", "10"))
        self.assertIn(("I-DEGENERATE", "param_nonfinite"), _kinds(r))

    def test_inf_origin(self):
        r = self._mutated(lambda g: setattr(g.get("a"), "origin",
                                            (0.0, float("inf"), 0.0)))
        self.assertIn(("I-DEGENERATE", "coord_nonfinite"), _kinds(r))

    def test_nan_axis(self):
        r = self._mutated(lambda g: setattr(g.get("a"), "axis",
                                            (0.0, float("nan"), 0.0)))
        self.assertIn(("I-DEGENERATE", "axis_nonfinite"), _kinds(r))

    def test_zero_axis(self):
        r = self._mutated(lambda g: setattr(g.get("a"), "axis",
                                            (0.0, 0.0, 0.0)))
        self.assertIn(("I-DEGENERATE", "axis_zero"), _kinds(r))
        self.assertEqual(_by_kind(r, "axis_zero")[0].ids, ("a",))

    def test_unknown_kind(self):
        r = self._mutated(lambda g: setattr(g.get("b"), "kind",
                                            "octahedron"))
        self.assertIn(("I-DEGENERATE", "kind_unknown"), _kinds(r))

    def test_unknown_joint_type(self):
        # engine-blind (probe): a mutated joint type must still be rejected
        def mut(g):
            g.terminus_continuations[0].joint = "seam"
        r = self._mutated(mut)
        self.assertIn(("I-DEGENERATE", "joint_type_unknown"), _kinds(r))

    def test_unknown_construction(self):
        def mut(g):
            g.terminus_continuations[0].construction = "velcro"
        r = self._mutated(mut)
        self.assertIn(("I-DEGENERATE", "construction_unknown"), _kinds(r))

    def test_duplicate_prim_id_defensive(self):
        g = _cont_graph()
        g._prims.append(_tube("a"))          # unconstructible via add()
        r = V.validate(g)
        self.assertIn(("I-DEGENERATE", "duplicate_prim_id"), _kinds(r))

    def test_fatal_degenerate_short_circuits_engine(self):
        # §7 hard errors: a degenerate graph reports degenerate verdicts only
        g = _cont_graph()
        g.get("a").params["r1"] = 0
        r = V.validate(g)
        for f in r.findings:
            self.assertEqual(f.invariant, "I-DEGENERATE", f)
        self.assertFalse(any(e.code != "I-DEGENERATE" for e in r.errors))


# ---------------------------------------------------------------------------
# C1 — schema refs and duplicate ids (engine I-SCHEMA mapping)
# ---------------------------------------------------------------------------
class TestSchema(unittest.TestCase):
    def test_duplicate_joint_id(self):
        g = _cont_graph()
        c = _tube("c", l=30, origin=(0, 150, 0))
        g.add(c)
        _pick_up(g, "pick_up_2", "b", "c")
        g.add_joint(_cont_joint("j1", "c", "b", (0, 150, 0), ["pick_up_2"]))
        r = V.validate(g)
        self.assertIn(("I-SCHEMA", "duplicate_joint_id"), _kinds(r))

    def test_duplicate_op_id_defensive(self):
        g = _cont_graph()
        g.ops.append(P.KnitOp(id="cast_on_1", op="cast_on", consumes=[],
                              produces="a/rim_start"))
        r = V.validate(g)
        self.assertIn(("I-SCHEMA", "duplicate_op_id"), _kinds(r))

    def test_unresolved_child_boundary(self):
        g = _cont_graph()
        j = g.terminus_continuations[0]
        g.terminus_continuations[0] = P.Joint(
            id=j.id, joint=j.joint, child=j.child, child_boundary="rim",
            parent=j.parent, parent_boundary=j.parent_boundary,
            construction=j.construction, anchor=j.anchor,
            realized_by=j.realized_by)
        r = V.validate(g)
        self.assertIn(("I-SCHEMA", "unresolved_boundary_ref"), _kinds(r))

    def test_unknown_open_boundary_ref(self):
        g = _cont_graph()
        g.open_boundaries.append("nope/rim_start")
        r = V.validate(g)
        self.assertIn(("I-SCHEMA", "unresolved_open_boundary"), _kinds(r))

    def test_unresolved_parent_prim(self):
        g = _cont_graph()
        j = g.terminus_continuations[0]
        g.terminus_continuations[0] = P.Joint(
            id=j.id, joint=j.joint, child=j.child,
            child_boundary=j.child_boundary, parent="ghost",
            parent_boundary=j.parent_boundary,
            construction=j.construction, anchor=j.anchor,
            realized_by=j.realized_by)
        r = V.validate(g)
        self.assertIn(("I-SCHEMA", "unresolved_primitive_ref"), _kinds(r))


# ---------------------------------------------------------------------------
# C1 — axis (engine I-AXIS mapping; axis normalization hides ctor paths)
# ---------------------------------------------------------------------------
class TestAxis(unittest.TestCase):
    def test_non_unit_axis_mutation(self):
        g = _cont_graph()
        g.get("a").axis = (2.0, 0.0, 0.0)
        r = V.validate(g)
        self.assertIn(("I-AXIS", "axis_norm"), _kinds(r))
        e = _by_kind(r, "axis_norm")[0]
        self.assertEqual(e.ids, ("a",))
        self.assertAlmostEqual(e.actual, 2.0, places=9)
        self.assertAlmostEqual(e.expected, 1.0, places=9)


# ---------------------------------------------------------------------------
# C1 — connectivity (card class 1: orphans listed)
# ---------------------------------------------------------------------------
class TestConnectivity(unittest.TestCase):
    def test_severed_sleeve_two_roots(self):
        torso = _tube("torso", r1=60, r2=60, l=300)
        sleeve = _tube("sleeve", r1=20, r2=20, l=150, origin=(100, 50, 0))
        g = P.UGPGraph(primitives=[torso, sleeve],
                       open_boundaries=["torso/rim_start", "torso/rim_end",
                                        "sleeve/rim_start", "sleeve/rim_end"])
        r = V.validate(g)
        self.assertFalse(r.ok)
        e = _by_kind(r, "root_count")[0]
        self.assertEqual(e.code, "I-GRAPH")
        self.assertEqual(e.actual, 2)
        self.assertEqual(e.expected, 1)
        self.assertEqual(e.ids, ("sleeve", "torso"))

    def test_disconnected_island_lists_orphans(self):
        g = _cont_graph()
        c = _tube("c", l=30, origin=(0, 500, 0))
        g.add(c)
        g.open_boundaries.extend(["c/rim_start", "c/rim_end"])
        r = V.validate(g)
        e = _by_kind(r, "root_count")[0]
        self.assertEqual(e.ids, ("a", "c"))

    def test_unreachable_cycle_lists_all_orphans(self):
        # single root a; b<->c form a parent cycle away from it
        a = _tube("a")
        b = _tube("b", origin=(0, 200, 0))
        c = _tube("c", origin=(0, 300, 0))
        g = P.UGPGraph(primitives=[a, b, c],
                       open_boundaries=["a/rim_start", "a/rim_end"])
        _cast_on(g, "a", "cast_on_1")
        g.add_op(P.KnitOp(id="pick_up_1", op="pick_up",
                          consumes=["b/rim_end"], produces="c/rim_start"))
        g.add_op(P.KnitOp(id="pick_up_2", op="pick_up",
                          consumes=["c/rim_end"], produces="b/rim_start"))
        g.add_joint(_cont_joint("j1", "c", "b", (0, 300, 0), ["pick_up_1"]))
        g.add_joint(_cont_joint("j2", "b", "c", (0, 400, 0), ["pick_up_2"]))
        r = V.validate(g)
        e = _by_kind(r, "unreachable")[0]
        self.assertEqual(e.code, "I-GRAPH")
        self.assertEqual(e.ids, ("b", "c"))
        self.assertEqual(e.actual, 2)
        self.assertEqual(e.expected, 0)

    def test_multiple_parents(self):
        a = _tube("a")
        b = _tube("b", origin=(0, 100, 0))
        c = _tube("c", origin=(0, 300, 0), l=100)
        g = P.UGPGraph(primitives=[a, b, c], open_boundaries=["b/rim_end"])
        _cast_on(g, "a", "cast_on_1")
        _cast_on(g, "c", "cast_on_2")
        _pick_up(g, "pick_up_1", "a", "b")
        _pick_up(g, "pick_up_2", "c", "b")
        g.add_joint(_rim_joint("j1", "b", "a", (10, 100, 0), ["pick_up_1"]))
        g.add_joint(_rim_joint("j2", "b", "c", (10, 400, 0), ["pick_up_2"]))
        r = V.validate(g)
        e = _by_kind(r, "multiple_parents")[0]
        self.assertEqual(e.code, "I-GRAPH")
        self.assertIn("b", e.ids)


# ---------------------------------------------------------------------------
# C2 — engine-class mapping: numeric expected/actual per catalog row
# ---------------------------------------------------------------------------
class TestRimMatch(unittest.TestCase):
    def _mismatch_graph(self, child_r):
        a = _tube("a")
        b = _tube("b", r1=child_r, r2=child_r, l=50, origin=(0, 100, 0))
        g = P.UGPGraph(primitives=[a, b], open_boundaries=["b/rim_end"])
        _cast_on(g, "a", "cast_on_1")
        _pick_up(g, "pick_up_1", "a", "b")
        g.add_joint(_rim_joint("j1", "b", "a", (10, 100, 0), ["pick_up_1"]))
        return g

    def test_rim_length_mismatch_beyond_T_RIM(self):
        r = V.validate(self._mismatch_graph(10.5))   # 2pi*0.5 = 3.14 mm
        e = _by_kind(r, "rim_length_mismatch")[0]
        self.assertEqual(e.code, "I-RIMMATCH")
        self.assertEqual(e.ids, ("j1",))
        self.assertAlmostEqual(e.expected, 1.0, places=9)
        self.assertAlmostEqual(e.actual, 3.142, places=2)

    def test_rim_mismatch_within_T_RIM_is_clean(self):
        a = _tube("a")
        b = _tube("b", r1=10.05, r2=10.05, l=50, origin=(0, 100, 0))
        g = P.UGPGraph(primitives=[a, b], open_boundaries=["b/rim_end"])
        _cast_on(g, "a", "cast_on_1")
        _pick_up(g, "pick_up_1", "a", "b")
        g.add_joint(_rim_joint("j1", "b", "a", (10, 100, 0), ["pick_up_1"]))
        r = V.validate(g)
        self.assertTrue(r.ok, _kinds(r))


class TestContinuation(unittest.TestCase):
    def test_radius_step_beyond_T_RIM(self):
        g = _cont_graph(child_r2=20)                 # dr = 10 mm
        r = V.validate(g)
        e = _by_kind(r, "radius_step")[0]
        self.assertEqual(e.code, "I-CONT")
        self.assertEqual(e.ids, ("j1",))
        self.assertAlmostEqual(e.expected, 1.0, places=9)
        self.assertAlmostEqual(e.actual, 10.0, places=9)

    def test_axis_turn_beyond_max(self):
        # 120-degree continuation turn: only |turn| > MAX (90) fails, so
        # tilt the child 30 degrees off the parent then 120 total via -150:
        # use a 120-degree turn directly (sin120/cos120)
        a = _tube("a")
        ang = math.radians(120)
        b = _tube("b", l=50, origin=(0, 100, 0),
                  axis=(math.sin(ang), math.cos(ang), 0.0))
        g = P.UGPGraph(primitives=[a, b], open_boundaries=["b/rim_end"])
        _cast_on(g, "a", "cast_on_1")
        _pick_up(g, "pick_up_1", "a", "b")
        g.add_joint(_cont_joint("j1", "b", "a", (0, 100, 0), ["pick_up_1"]))
        r = V.validate(g)
        e = _by_kind(r, "axis_turn")[0]
        self.assertEqual(e.code, "I-CONT")
        self.assertAlmostEqual(e.expected, 90.0, places=9)
        self.assertAlmostEqual(e.actual, 120.0, places=9)

    def test_axis_turn_within_max_clean(self):
        # 30-degree continuation turn: legal
        a = _tube("a")
        b = _tube("b", l=50, origin=(0, 100, 0),
                  axis=(math.sin(math.radians(30)), math.cos(math.radians(30)),
                        0.0))
        g = P.UGPGraph(primitives=[a, b], open_boundaries=["b/rim_end"])
        _cast_on(g, "a", "cast_on_1")
        _pick_up(g, "pick_up_1", "a", "b")
        g.add_joint(_cont_joint("j1", "b", "a", (0, 100, 0), ["pick_up_1"]))
        r = V.validate(g)
        self.assertTrue(r.ok, _kinds(r))


class TestSeal(unittest.TestCase):
    def test_floating_rim(self):
        g = _cont_graph()
        g.open_boundaries.remove("b/rim_end")
        g.ops = [o for o in g.ops if o.id != "cast_on_1"]
        # b/rim_start stays produced by pick_up_1; a/rim_end is now floating
        r = V.validate(g)
        e = _by_kind(r, "floating_rim")[0]
        self.assertEqual(e.code, "I-SEAL")
        self.assertEqual(e.ids[0], "a/rim_start")

    def test_conflicting_states(self):
        g = _cont_graph()
        g.open_boundaries.append("a/rim_start")  # produced + declared_open
        r = V.validate(g)
        e = _by_kind(r, "conflicting_states")[0]
        self.assertEqual(e.code, "I-SEAL")
        self.assertEqual(e.ids[0], "a/rim_start")

    def test_multi_consumed(self):
        # consumption must be the rim's ONLY state: b/rim_end stays off
        # open_boundaries and two bind_offs claim it
        g = _cont_graph()
        g.open_boundaries.remove("b/rim_end")
        g.add_op(P.KnitOp(id="bind_off_1", op="bind_off",
                          consumes=["b/rim_end"]))
        g.add_op(P.KnitOp(id="bind_off_2", op="bind_off",
                          consumes=["b/rim_end"]))
        r = V.validate(g)
        kinds = _kinds(r)
        self.assertIn(("I-SEAL", "multi_consumed"), kinds)
        e = _by_kind(r, "multi_consumed")[0]
        self.assertEqual(e.ids, ("b/rim_end",))
        self.assertEqual(e.expected, 1)
        self.assertEqual(e.actual, 2)

    def test_inert_consumed(self):
        a = _tube("a")
        d = P.Primitive(id="d", kind="disk",
                        params={"r": 10}, origin=(0, 100, 0))
        g = P.UGPGraph(primitives=[a, d], open_boundaries=["a/rim_start"])
        _cast_on(g, "a", "cast_on_1")
        g.add_op(P.KnitOp(id="bind_off_1", op="bind_off",
                          consumes=["d/rim"]))
        g.add_joint(_rim_joint("j1", "d", "a", (10, 100, 0), [],
                               child_boundary="rim"))
        r = V.validate(g)
        kinds = _kinds(r)
        self.assertIn(("I-SEAL", "inert_consumed"), kinds)


class TestJointRules(unittest.TestCase):
    def test_anchor_feature_mismatch(self):
        g = _cont_graph()
        j = g.terminus_continuations[0]
        g.terminus_continuations[0] = P.Joint(
            id=j.id, joint="rim_joint", child=j.child,
            child_boundary=j.child_boundary, parent=j.parent,
            parent_boundary=j.parent_boundary, construction=j.construction,
            anchor={"feature": "terminus", "boundary": "rim_end",
                    "point": j.anchor["point"]},
            realized_by=j.realized_by)
        r = V.validate(g)
        kinds = _kinds(r)
        self.assertIn(("I-JOINT", "anchor_feature_mismatch"), kinds)

    def test_construction_illegal(self):
        g = _cont_graph()
        j = g.terminus_continuations[0]
        g.terminus_continuations[0] = P.Joint(
            id=j.id, joint=j.joint, child=j.child,
            child_boundary=j.child_boundary, parent=j.parent,
            parent_boundary=j.parent_boundary, construction="selvedge_seam",
            anchor=j.anchor, realized_by=j.realized_by)
        r = V.validate(g)
        kinds = _kinds(r)
        self.assertIn(("I-JOINT", "construction_illegal"), kinds)


class TestAnchor(unittest.TestCase):
    def test_anchor_off_feature_beyond_T_ANCHOR(self):
        g = _cont_graph()
        j = g.terminus_continuations[0]
        g.terminus_continuations[0] = P.Joint(
            id=j.id, joint=j.joint, child=j.child,
            child_boundary=j.child_boundary, parent=j.parent,
            parent_boundary=j.parent_boundary, construction=j.construction,
            anchor={"feature": "terminus", "boundary": "rim_end",
                    "point": (0, 103, 0)},
            realized_by=j.realized_by)
        r = V.validate(g)
        e = _by_kind(r, "anchor_off_feature")[0]
        self.assertEqual(e.code, "I-ANCHOR")
        self.assertEqual(e.ids, ("j1",))
        self.assertAlmostEqual(e.expected, 0.5, places=9)
        self.assertAlmostEqual(e.actual, 3.0, places=9)


class TestToleranceOverride(unittest.TestCase):
    def test_relaxed_T_RIM_accepts_bigger_step(self):
        # rim diff 3.14 mm and radius step 0.5 mm both pass at T_RIM=4
        a = _tube("a")
        b = _tube("b", r1=10.5, r2=10.5, l=50, origin=(0, 100, 0))
        g = P.UGPGraph(primitives=[a, b], open_boundaries=["b/rim_end"])
        _cast_on(g, "a", "cast_on_1")
        _pick_up(g, "pick_up_1", "a", "b")
        g.add_joint(_rim_joint("j1", "b", "a", (10, 100, 0), ["pick_up_1"]))
        g.tolerances["T_RIM"] = 4.0
        r = V.validate(g)
        self.assertTrue(r.ok, _kinds(r))

    def test_tightened_T_ANCHOR_rejects_off_arc_point(self):
        # anchor 0.3 mm off the arc: within default T_ANCHOR=0.5, outside 0.01
        a = _tube("a")
        b = _tube("b", l=50, origin=(0, 100, 0))
        g = P.UGPGraph(primitives=[a, b], open_boundaries=["b/rim_end"])
        _cast_on(g, "a", "cast_on_1")
        _pick_up(g, "pick_up_1", "a", "b")
        g.add_joint(_rim_joint("j1", "b", "a", (10.3, 100, 0),
                               ["pick_up_1"]))
        r = V.validate(g)
        self.assertTrue(r.ok, _kinds(r))     # clean at defaults
        g.tolerances["T_ANCHOR"] = 0.01
        r = V.validate(g)
        self.assertFalse(r.ok)
        self.assertIn(("I-ANCHOR", "anchor_off_feature"), _kinds(r))


class TestCatalogCompleteness(unittest.TestCase):
    def test_every_engine_fail_maps_to_non_generic_kind(self):
        # any engine FAIL on a mutated graph must land in a named kind,
        # never the generic 'engine_finding' fallback
        import itertools
        mutations = []
        base = _cont_graph
        g = base(); g.get("a").axis = (2.0, 0.0, 0.0); mutations.append(g)
        g = base(); g.get("a").params["r1"] = 0; mutations.append(g)
        g = base(); g.get("a").params["l"] = float("nan"); mutations.append(g)
        g = base()
        j = g.terminus_continuations[0]
        g.terminus_continuations[0] = P.Joint(
            id=j.id, joint="rim_joint", child=j.child,
            child_boundary=j.child_boundary, parent=j.parent,
            parent_boundary=j.parent_boundary, construction=j.construction,
            anchor=j.anchor, realized_by=j.realized_by)
        mutations.append(g)
        g = base(); g.get("b").kind = "octahedron"; mutations.append(g)
        for g in mutations:
            r = V.validate(g)
            for e in r.errors:
                self.assertNotEqual(e.kind, "engine_finding", e.as_tuple())

    def test_validate_strict_raises_with_catalog_in_message(self):
        g = _cont_graph(child_r2=20)
        with self.assertRaises(P.GraphValidationError) as ctx:
            V.validate_strict(g)
        self.assertIn("I-CONT[j1]", str(ctx.exception))
        self.assertIn("radius step", str(ctx.exception))

    def test_validate_rejects_non_graph(self):
        with self.assertRaises(TypeError):
            V.validate("not a graph")

    def test_result_to_dict_roundtrip_keys(self):
        r = V.validate(_cont_graph())
        d = r.to_dict()
        for key in ("ok", "fatal", "errors", "findings"):
            self.assertIn(key, d)
        self.assertTrue(d["ok"])


if __name__ == "__main__":
    unittest.main()

