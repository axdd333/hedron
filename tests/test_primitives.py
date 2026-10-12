"""UGC-01 spec v2 tests: Universal Garment Primitive (ugc.primitives).

Every behavior is written test-first against DESIGN.md IR spec v2:
joint taxonomy (type x construction x anchor), boundary descriptors,
default_knit op set, and the I-* invariants (§6 of DESIGN.md).
"""
import math
import unittest

import ugc.primitives as P


# ---------------------------------------------------------------------------
# §2 render primitives: defaults, units, axis normalization (kept from v1)
# ---------------------------------------------------------------------------
class TestPrimitiveDefaultsAndNormalization(unittest.TestCase):
    def test_tube_defaults_all_params_ten_mm(self):
        t = P.Primitive(id="t1", kind="tube", params={}, origin=(0, 0, 0))
        self.assertEqual(t.params["r1"], 10)
        self.assertEqual(t.params["r2"], 10)
        self.assertEqual(t.params["l"], 10)

    def test_default_orientation_is_unit_y(self):
        t = P.Primitive(id="t2", kind="tube", params={}, origin=(0, 0, 0))
        self.assertEqual(t.axis, (0.0, 1.0, 0.0))

    def test_axis_is_normalized_on_ingest(self):
        t = P.Primitive(id="t3", kind="tube", params={}, origin=(0, 0, 0),
                        axis=(2, 0, 0))
        self.assertEqual(t.axis, (1.0, 0.0, 0.0))

    def test_zero_axis_is_rejected(self):
        with self.assertRaises(ValueError):
            P.Primitive(id="t4", kind="tube", params={}, origin=(0, 0, 0),
                        axis=(0, 0, 0))

    def test_nonfinite_axis_is_rejected(self):
        with self.assertRaises(ValueError):
            P.Primitive(id="t4b", kind="tube", params={}, origin=(0, 0, 0),
                        axis=(0, float("nan"), 0))


# ---------------------------------------------------------------------------
# §2 render geometry: metrics stay (render view only, no knit claims)
# ---------------------------------------------------------------------------
class TestTransforms(unittest.TestCase):
    def test_world_to_local_translates_and_inverse_rotates(self):
        t = P.Primitive(id="w1", kind="tube", params={"l": 100},
                        origin=(5, 0, 0), axis=(0, 1, 0))
        world_pt = (15, 50, 0)          # local (10, 50, 0)
        self.assertEqual(t.world_to_local(world_pt), (10.0, 50.0, 0.0))

    def test_rotation_matrix_maps_z_to_x_for_90deg_y(self):
        r = P.Primitive.rotation_matrix(90.0, (0, 1, 0))
        self.assertAlmostEqual(r[0][0], 0.0, places=9)
        self.assertAlmostEqual(r[0][2], 1.0, places=9)
        self.assertAlmostEqual(r[2][0], -1.0, places=9)


class TestRenderMetrics(unittest.TestCase):
    def test_sphere_metrics_closed_form(self):
        s = P.Primitive(id="s", kind="sphere", params={"r": 10},
                        origin=(0, 0, 0))
        m = s.metrics()
        self.assertAlmostEqual(m["volume"], 4000.0 * math.pi / 3.0, delta=0.02)
        self.assertAlmostEqual(m["surfaceArea"], 400.0 * math.pi, delta=0.02)

    def test_tapered_tube_metrics(self):
        t = P.Primitive(id="tt", kind="tube",
                        params={"r1": 10, "r2": 5, "l": 50}, origin=(0, 0, 0))
        m = t.metrics()
        expected = math.pi * 50.0 * (100.0 + 50.0 + 25.0) / 3.0
        self.assertAlmostEqual(m["volume"], expected, delta=0.02)
        self.assertEqual(m["terminus"], (0.0, 50.0, 0.0))


# ---------------------------------------------------------------------------
# §4.1 boundary descriptors — the knit view, test-first
# ---------------------------------------------------------------------------
class TestBoundaryDescriptors(unittest.TestCase):
    def test_tube_has_two_knit_bearing_rims(self):
        t = P.Primitive(id="b1", kind="tube",
                        params={"r1": 10, "r2": 8, "l": 50}, origin=(0, 0, 0))
        ids = [b.boundary for b in t.boundaries]
        self.assertEqual(ids, ["rim_start", "rim_end"])
        for b in t.boundaries:
            self.assertEqual(b.kind, "rim")
            self.assertTrue(b.knit_bearing)

    def test_rim_length_is_circumference_in_mm(self):
        t = P.Primitive(id="b2", kind="tube", params={"r1": 10, "l": 50},
                        origin=(0, 0, 0))
        rim = t.boundary("rim_start")
        self.assertAlmostEqual(rim.length_mm, 2.0 * math.pi * 10.0, delta=1e-9)

    def test_rim_start_centered_on_origin_rim_end_on_terminus(self):
        t = P.Primitive(id="b3", kind="tube", params={"r1": 10, "r2": 6},
                        origin=(0, 0, 0))
        start = t.boundary("rim_start")
        end = t.boundary("rim_end")
        self.assertEqual(start.frame["center"], (0.0, 0.0, 0.0))
        self.assertEqual(end.frame["center"], (0.0, 10.0, 0.0))  # l = 10
        # normals point outward along the axis: start down-stream, end up
        self.assertEqual(start.frame["normal"], (0.0, -1.0, 0.0))
        self.assertEqual(end.frame["normal"], (0.0, 1.0, 0.0))

    def test_rim_end_length_uses_r2(self):
        t = P.Primitive(id="b3b", kind="tube",
                        params={"r1": 10, "r2": 6, "l": 20}, origin=(0, 0, 0))
        self.assertAlmostEqual(t.boundary("rim_end").length_mm,
                               2.0 * math.pi * 6.0, delta=1e-9)

    def test_hemisphere_has_one_joinable_rim(self):
        h = P.Primitive(id="b4", kind="hemisphere", params={"r": 30},
                        origin=(0, 0, 0))
        self.assertEqual([b.boundary for b in h.boundaries], ["rim"])
        rim = h.boundary("rim")
        self.assertTrue(rim.knit_bearing)
        self.assertAlmostEqual(rim.length_mm, 2.0 * math.pi * 30.0, delta=1e-9)
        self.assertEqual(rim.frame["normal"], (0.0, -1.0, 0.0))  # outward

    def test_sphere_ellipsoid_have_no_boundaries(self):
        s = P.Primitive(id="b5", kind="sphere", params={"r": 10},
                        origin=(0, 0, 0))
        e = P.Primitive(id="b6", kind="ellipsoid",
                        params={"rx": 10, "ry": 12, "rz": 14},
                        origin=(0, 0, 0))
        self.assertEqual(s.boundaries, [])
        self.assertEqual(e.boundaries, [])
        self.assertEqual(s.closure, "integral")
        self.assertEqual(e.closure, "integral")

    def test_disk_has_inert_rim_with_zero_loops(self):
        d = P.Primitive(id="b7", kind="disk", params={"r": 10},
                        origin=(0, 0, 0))
        rim = d.boundary("rim")
        self.assertFalse(d.knit_bearing)
        self.assertEqual(rim.kind, "inert")
        self.assertFalse(rim.knit_bearing)
        self.assertEqual(rim.loops, 0.0)
        self.assertFalse(rim.consumable)

    def test_rect_has_four_inert_edges(self):
        r = P.Primitive(id="b8", kind="rect", params={"w": 40, "h": 20},
                        origin=(0, 0, 0))
        self.assertEqual([b.boundary for b in r.boundaries],
                         ["edge_bottom", "edge_top", "edge_left",
                          "edge_right"])
        for b in r.boundaries:
            self.assertEqual(b.kind, "inert")
            self.assertEqual(b.loops, 0.0)

    def test_loops_are_null_without_gauge(self):
        t = P.Primitive(id="b9", kind="tube", params={}, origin=(0, 0, 0))
        self.assertIsNone(t.boundary("rim_start").loops)

    def test_loops_derive_from_gauge(self):
        t = P.Primitive(id="b10", kind="tube", params={"r1": 10},
                        origin=(0, 0, 0))
        wale = 2.5
        expected = 2.0 * math.pi * 10.0 / wale
        self.assertAlmostEqual(
            t.boundary("rim_start").loops_for({"wale_mm": wale}), expected,
            delta=1e-9)

    def test_boundary_json_roundtrip(self):
        t = P.Primitive(id="b11", kind="tube", params={"r1": 12, "l": 40},
                        origin=(1, 2, 3), axis=(0, 0, 1))
        rt = P.Primitive.from_dict(t.to_dict())
        self.assertEqual(rt.boundaries, t.boundaries)

    def test_unknown_boundary_id_raises(self):
        t = P.Primitive(id="b12", kind="tube", params={}, origin=(0, 0, 0))
        with self.assertRaises(KeyError):
            t.boundary("nope")


# ---------------------------------------------------------------------------
# §6 invariants — validate() runs every class, hard errors for FAILs
# ---------------------------------------------------------------------------
def _tube(pid, r1=50.0, r2=50.0, l=100.0, origin=(0, 0, 0), axis=(0, 1, 0)):
    return P.Primitive(id=pid, kind="tube",
                       params={"r1": r1, "r2": r2, "l": l},
                       origin=origin, axis=axis)


def _joint(jid, joint, child, child_b, parent, parent_b, construction,
           feature, point, anchor_b=None, realized_by=()):
    return P.Joint(id=jid, joint=joint, child=child, child_boundary=child_b,
                   parent=parent, parent_boundary=parent_b,
                   construction=construction,
                   anchor={"feature": feature, "boundary": anchor_b,
                           "point": point},
                   realized_by=list(realized_by))


def _sealed_graph(gauge={"wale_mm": 2.5, "course_mm": 1.6}):
    """Two tubes: cast_on -> pick_up continuation -> bind_off. Fully sealed."""
    t1 = _tube("t1")
    t2 = _tube("t2", origin=(0, 100, 0))
    j1 = _joint("j1", "terminus_continuation", "t2", "rim_start", "t1",
                "rim_end", "knitted_in", "terminus", (0, 100, 0),
                anchor_b="rim_end", realized_by=["op_pu"])
    ops = [
        P.KnitOp(id="op_co", op="cast_on", consumes=[],
                 produces="t1/rim_start"),
        P.KnitOp(id="op_pu", op="pick_up", consumes=["t1/rim_end"],
                 produces="t2/rim_start"),
        P.KnitOp(id="op_bo", op="bind_off", consumes=["t2/rim_end"]),
    ]
    return P.UGPGraph([t1, t2], [j1], ops, gauge=gauge)


def _status(findings, invariant):
    return [f.status for f in findings if f.invariant == invariant]


def _failed(findings, invariant):
    return any(f.status == "FAIL" and f.invariant == invariant
               for f in findings)


class TestDegenerateValidation(unittest.TestCase):
    """I-DEGENERATE: §7.1-3. Constructor-level rejects (§6 I-DEGENERATE)."""

    def test_zero_radius_rejected(self):
        with self.assertRaises(P.PrimitiveError):
            _tube("d1", r1=0)

    def test_negative_length_rejected(self):
        with self.assertRaises(P.PrimitiveError):
            _tube("d2", l=-5)

    def test_zero_width_rect_rejected(self):
        with self.assertRaises(P.PrimitiveError):
            P.Primitive(id="d3", kind="rect", params={"w": 0, "h": 10},
                        origin=(0, 0, 0))

    def test_nan_param_rejected(self):
        with self.assertRaises(P.PrimitiveError):
            _tube("d4", r1=float("nan"))

    def test_nan_origin_rejected(self):
        with self.assertRaises(P.PrimitiveError):
            _tube("d5", origin=(0, float("nan"), 0))

    def test_nan_anchor_point_rejected(self):
        with self.assertRaises(P.JointError):
            _joint("d6", "rim_joint", "c", "rim", "p", "rim_end",
                   "unsupported", "rim", (0, float("nan"), 0),
                   anchor_b="rim_end")

    def test_unknown_primitive_kind_rejected(self):
        with self.assertRaises(P.PrimitiveError):
            P.Primitive(id="d7", kind="torus", params={}, origin=(0, 0, 0))

    def test_unknown_param_key_rejected(self):
        with self.assertRaises(P.PrimitiveError):
            P.Primitive(id="d8b", kind="tube", params={"depth": 5},
                        origin=(0, 0, 0))


class TestValidateContract(unittest.TestCase):
    def test_valid_graph_passes_every_class(self):
        findings = P.validate(_sealed_graph())
        by_class = {f.invariant: f.status for f in findings}
        for inv in P.INARIANT_CLASSES:
            self.assertEqual(by_class.get(inv), "PASS", inv)

    def test_validate_never_raises_reports_fail_instead(self):
        g = _sealed_graph()
        g.add_op(P.KnitOp(id="op_bo2", op="bind_off",
                          consumes=["t1/rim_start"]))
        findings = P.validate(g)          # must not raise
        self.assertTrue(_failed(findings, "I-SEAL"))

    def test_validate_strict_raises_graph_validation_error(self):
        g = _sealed_graph()
        g.open_boundaries = ["t1/rim_start"]   # contradicts cast_on
        with self.assertRaises(P.GraphValidationError) as ctx:
            P.validate_strict(g)
        self.assertTrue(any(f.invariant == "I-SEAL"
                            for f in ctx.exception.findings))


class TestSchemaInvariant(unittest.TestCase):
    def test_unknown_child_boundary_fails(self):
        g = _sealed_graph()
        g.rim_joints.append(_joint("jx", "rim_joint", "t2", "nope", "t1",
                                   "rim_end", "grafted", "rim", (50, 100, 0),
                                   anchor_b="rim_end", realized_by=["op_g"]))
        self.assertTrue(_failed(P.validate(g), "I-SCHEMA"))

    def test_unknown_parent_boundary_fails(self):
        g = _sealed_graph()
        g.rim_joints.append(_joint("jx", "rim_joint", "t2", "rim_start",
                                   "t1", "nope", "grafted", "rim",
                                   (50, 100, 0), anchor_b="rim_end",
                                   realized_by=["op_g"]))
        self.assertTrue(_failed(P.validate(g), "I-SCHEMA"))

    def test_op_referencing_unknown_boundary_fails(self):
        g = _sealed_graph()
        g.add_op(P.KnitOp(id="op_x", op="bind_off",
                          consumes=["ghost/rim_end"]))
        self.assertTrue(_failed(P.validate(g), "I-SCHEMA"))

    def test_realized_by_unknown_op_fails(self):
        g = _sealed_graph()
        g.terminus_continuations[0].realized_by = ["ghost_op"]
        self.assertTrue(_failed(P.validate(g), "I-SCHEMA"))

    def test_unknown_open_boundary_fails(self):
        g = _sealed_graph()
        g.open_boundaries = ["t1/nope"]
        self.assertTrue(_failed(P.validate(g), "I-SCHEMA"))

    def test_duplicate_joint_id_fails(self):
        g = _sealed_graph()
        g.rim_joints.append(_joint("j1", "rim_joint", "t2", "rim_start",
                                   "t1", "rim_end", "grafted", "rim",
                                   (50, 100, 0), anchor_b="rim_end",
                                   realized_by=["op_g"]))
        self.assertTrue(_failed(P.validate(g), "I-SCHEMA"))

    def test_duplicate_op_id_raises_at_add(self):
        g = _sealed_graph()
        with self.assertRaises(P.SchemaError):
            g.add_op(P.KnitOp(id="op_bo", op="bind_off",
                              consumes=["t2/rim_end"]))


class TestGraphInvariant(unittest.TestCase):
    def test_single_primitive_is_trivially_connected(self):
        g = P.UGPGraph([_tube("solo")])
        self.assertEqual(_status(P.validate(g), "I-GRAPH"), ["PASS"])

    def test_two_roots_are_disconnected(self):
        g = P.UGPGraph([_tube("a"), _tube("b", origin=(500, 0, 0))])
        self.assertTrue(_failed(P.validate(g), "I-GRAPH"))

    def test_multi_parent_primitive_fails(self):
        g = P.UGPGraph([_tube("a"), _tube("b", origin=(0, 100, 0)),
                        _tube("c", origin=(100, 0, 0))])
        g.terminus_continuations.append(
            _joint("j1", "terminus_continuation", "b", "rim_start", "a",
                   "rim_end", "unsupported", "terminus", (0, 100, 0),
                   anchor_b="rim_end"))
        g.rim_joints.append(
            _joint("j2", "rim_joint", "b", "rim_start", "c", "rim_end",
                   "unsupported", "rim", (150, 0, 0), anchor_b="rim_end"))
        self.assertTrue(_failed(P.validate(g), "I-GRAPH"))

    def test_parent_cycle_has_no_root(self):
        g = P.UGPGraph([_tube("a"), _tube("b", origin=(500, 0, 0))])
        g.rim_joints.append(
            _joint("j1", "rim_joint", "a", "rim_start", "b", "rim_end",
                   "unsupported", "rim", (50, 0, 0), anchor_b="rim_end"))
        g.rim_joints.append(
            _joint("j2", "rim_joint", "b", "rim_start", "a", "rim_end",
                   "unsupported", "rim", (550, 0, 0), anchor_b="rim_end"))
        self.assertTrue(_failed(P.validate(g), "I-GRAPH"))


class TestAxisInvariant(unittest.TestCase):
    def test_axes_unit_after_json_roundtrip(self):
        g = P.UGPGraph.from_json(_sealed_graph().to_json())
        findings = P.validate(g)
        self.assertEqual(_status(findings, "I-AXIS"), ["PASS"])
        for p in g:
            n = math.sqrt(sum(c * c for c in p.axis))
            self.assertAlmostEqual(n, 1.0, places=9)


class TestAnchorInvariant(unittest.TestCase):
    def test_terminus_anchor_on_parent_terminus_passes(self):
        self.assertEqual(_status(P.validate(_sealed_graph()), "I-ANCHOR"),
                         ["PASS"])

    def test_terminus_anchor_off_feature_fails(self):
        g = _sealed_graph()
        g.terminus_continuations[0].anchor["point"] = (0, 105, 0)
        self.assertTrue(_failed(P.validate(g), "I-ANCHOR"))

    def test_rim_anchor_on_circle_passes(self):
        g = _sealed_graph()
        g.rim_joints.append(_joint("j2", "rim_joint", "t2", "rim_start",
                                   "t1", "rim_end", "grafted", "rim",
                                   (50, 100, 0), anchor_b="rim_end",
                                   realized_by=["op_g"]))
        self.assertFalse(_failed(P.validate(g), "I-ANCHOR"))

    def test_rim_anchor_off_circle_fails(self):
        g = _sealed_graph()
        g.rim_joints.append(_joint("j2", "rim_joint", "t2", "rim_start",
                                   "t1", "rim_end", "grafted", "rim",
                                   (50, 103, 0), anchor_b="rim_end",
                                   realized_by=["op_g"]))
        self.assertTrue(_failed(P.validate(g), "I-ANCHOR"))

    def test_surface_anchor_on_sphere_passes(self):
        palm = P.Primitive(id="palm", kind="sphere", params={"r": 60},
                           origin=(0, 0, 0))
        pad = P.Primitive(id="pad", kind="disk", params={"r": 8},
                          origin=(0, 60, 0))
        j = _joint("j", "surface_branch", "pad", "rim", "palm", None,
                   "unsupported", "surface", (0, 60, 0))
        g = P.UGPGraph([palm, pad], [j])
        self.assertFalse(_failed(P.validate(g), "I-ANCHOR"))

    def test_surface_anchor_inside_sphere_fails(self):
        palm = P.Primitive(id="palm", kind="sphere", params={"r": 60},
                           origin=(0, 0, 0))
        pad = P.Primitive(id="pad", kind="disk", params={"r": 8},
                          origin=(0, 60, 0))
        j = _joint("j", "surface_branch", "pad", "rim", "palm", None,
                   "unsupported", "surface", (0, 55, 0))
        g = P.UGPGraph([palm, pad], [j])
        self.assertTrue(_failed(P.validate(g), "I-ANCHOR"))


class TestRimMatchInvariant(unittest.TestCase):
    def _rim_joint(self, child_r1):
        t1 = _tube("t1")
        t2 = _tube("t2", r1=child_r1, r2=child_r1, origin=(0, 100, 0))
        j = _joint("j", "rim_joint", "t2", "rim_start", "t1", "rim_end",
                   "grafted", "rim", (50, 100, 0), anchor_b="rim_end",
                   realized_by=["op_g"])
        ops = [
            P.KnitOp(id="op_co", op="cast_on", consumes=[],
                     produces="t1/rim_start"),
            P.KnitOp(id="op_g", op="graft",
                     consumes=["t1/rim_end", "t2/rim_start"]),
            P.KnitOp(id="op_bo", op="bind_off", consumes=["t2/rim_end"]),
        ]
        return P.UGPGraph([t1, t2], [j], ops,
                          gauge={"wale_mm": 2.5, "course_mm": 1.6})

    def test_equal_rims_pass(self):
        self.assertEqual(_status(P.validate(self._rim_joint(50.0)),
                                 "I-RIMMATCH"), ["PASS"])

    def test_mismatched_rim_lengths_fail(self):
        self.assertTrue(_failed(P.validate(self._rim_joint(45.0)),
                                "I-RIMMATCH"))


class TestContinuityInvariant(unittest.TestCase):
    def _cont_graph(self, child_r1=50.0, child_axis=(0, 1, 0)):
        t1 = _tube("t1")
        t2 = _tube("t2", r1=child_r1, r2=child_r1, origin=(0, 100, 0),
                   axis=child_axis)
        j = _joint("j", "terminus_continuation", "t2", "rim_start", "t1",
                   "rim_end", "knitted_in", "terminus", (0, 100, 0),
                   anchor_b="rim_end", realized_by=["op_pu"])
        ops = [
            P.KnitOp(id="op_co", op="cast_on", consumes=[],
                     produces="t1/rim_start"),
            P.KnitOp(id="op_pu", op="pick_up", consumes=["t1/rim_end"],
                     produces="t2/rim_start"),
            P.KnitOp(id="op_bo", op="bind_off", consumes=["t2/rim_end"]),
        ]
        return P.UGPGraph([t1, t2], [j], ops,
                          gauge={"wale_mm": 2.5, "course_mm": 1.6})

    def test_straight_continuation_passes(self):
        self.assertEqual(_status(P.validate(self._cont_graph()), "I-CONT"),
                         ["PASS"])

    def test_ninety_degree_heel_turn_passes(self):
        self.assertFalse(_failed(P.validate(self._cont_graph(
            child_axis=(1, 0, 0))), "I-CONT"))

    def test_kink_beyond_limit_fails(self):
        self.assertTrue(_failed(P.validate(self._cont_graph(
            child_axis=(0, -1, 0))), "I-CONT"))

    def test_radius_step_fails(self):
        self.assertTrue(_failed(P.validate(self._cont_graph(
            child_r1=40.0)), "I-CONT"))


class TestBranchOrientInvariant(unittest.TestCase):
    def _branch_graph(self, child_axis=(0, 1, 0), anchor=(0, 60, 0)):
        palm = P.Primitive(id="palm", kind="sphere", params={"r": 60},
                           origin=(0, 0, 0))
        finger = P.Primitive(id="finger", kind="disk", params={"r": 8},
                             origin=anchor, axis=child_axis)
        j = _joint("j", "surface_branch", "finger", "rim", "palm", None,
                   "unsupported", "surface", anchor)
        return P.UGPGraph([palm, finger], [j])

    def test_finger_along_outward_normal_passes(self):
        self.assertEqual(_status(P.validate(self._branch_graph()),
                                 "I-BRANCHORIENT"), ["PASS"])

    def test_filer_pointing_into_material_fails(self):
        self.assertTrue(_failed(P.validate(self._branch_graph(
            child_axis=(0, -1, 0))), "I-BRANCHORIENT"))

    def test_tilted_within_limit_passes(self):
        inv = 1.0 / math.sqrt(2.0)
        self.assertFalse(_failed(P.validate(self._branch_graph(
            child_axis=(inv, inv, 0))), "I-BRANCHORIENT"))

    def test_tilted_beyond_limit_fails(self):
        self.assertTrue(_failed(P.validate(self._branch_graph(
            child_axis=(-0.6, -0.8, 0))), "I-BRANCHORIENT"))


class TestLoopInvariant(unittest.TestCase):
    def test_matching_loops_pass_under_gauge(self):
        self.assertEqual(_status(P.validate(_sealed_graph()), "I-LOOP"),
                         ["PASS"])

    def test_gauge_absent_reports_unverified(self):
        findings = P.validate(_sealed_graph(gauge=None))
        self.assertEqual(_status(findings, "I-LOOP"), ["UNVERIFIED"])

    def test_loop_mismatch_beyond_tolerance_fails(self):
        g = _sealed_graph()
        t2 = g.get("t2")
        t2.params["r1"] = 45.0      # rim_start loops drop ~12.6 below parent
        self.assertTrue(_failed(P.validate(g), "I-LOOP"))


class TestSealInvariant(unittest.TestCase):
    def test_fully_sealed_graph_passes(self):
        self.assertEqual(_status(P.validate(_sealed_graph()), "I-SEAL"),
                         ["PASS"])

    def test_floating_rim_fails(self):
        g = _sealed_graph()
        g.ops = [o for o in g.ops if o.id != "op_bo"]   # t2/rim_end orphaned
        self.assertTrue(_failed(P.validate(g), "I-SEAL"))

    def test_double_consumed_rim_fails(self):
        g = _sealed_graph()
        g.add_op(P.KnitOp(id="op_bo2", op="bind_off",
                          consumes=["t1/rim_start"]))
        self.assertTrue(_failed(P.validate(g), "I-SEAL"))

    def test_produced_twice_fails(self):
        g = _sealed_graph()
        g.add_op(P.KnitOp(id="op_co2", op="cast_on", consumes=[],
                          produces="t1/rim_start"))
        self.assertTrue(_failed(P.validate(g), "I-SEAL"))

    def test_declared_open_boundary_passes(self):
        g = _sealed_graph()
        g.ops = [o for o in g.ops if o.id != "op_bo"]
        g.open_boundaries = ["t2/rim_end"]
        self.assertEqual(_status(P.validate(g), "I-SEAL"), ["PASS"])

    def test_open_and_consumed_is_contradiction(self):
        g = _sealed_graph()
        g.open_boundaries = ["t1/rim_start"]    # also produced by cast_on
        self.assertTrue(_failed(P.validate(g), "I-SEAL"))

    def test_disk_cap_closes_nothing(self):
        t1 = _tube("t1")
        cap = P.Primitive(id="cap", kind="disk", params={"r": 50},
                          origin=(0, 100, 0))
        j = _joint("j", "rim_joint", "cap", "rim", "t1", "rim_end",
                   "unsupported", "rim", (50, 100, 0), anchor_b="rim_end")
        ops = [P.KnitOp(id="op_co", op="cast_on", consumes=[],
                        produces="t1/rim_start")]
        g = P.UGPGraph([t1, cap], [j], ops)
        self.assertTrue(_failed(P.validate(g), "I-SEAL"))

    def test_disk_cap_with_parent_side_bind_off_passes(self):
        t1 = _tube("t1")
        cap = P.Primitive(id="cap", kind="disk", params={"r": 50},
                          origin=(0, 100, 0))
        j = _joint("j", "rim_joint", "cap", "rim", "t1", "rim_end",
                   "unsupported", "rim", (50, 100, 0), anchor_b="rim_end")
        ops = [
            P.KnitOp(id="op_co", op="cast_on", consumes=[],
                     produces="t1/rim_start"),
            P.KnitOp(id="op_bo", op="bind_off", consumes=["t1/rim_end"]),
        ]
        g = P.UGPGraph([t1, cap], [j], ops)
        self.assertEqual(_status(P.validate(g), "I-SEAL"), ["PASS"])

    def test_op_consuming_inert_boundary_fails(self):
        t1 = _tube("t1")
        cap = P.Primitive(id="cap", kind="disk", params={"r": 50},
                          origin=(0, 100, 0))
        j = _joint("j", "rim_joint", "cap", "rim", "t1", "rim_end",
                   "unsupported", "rim", (50, 100, 0), anchor_b="rim_end")
        ops = [
            P.KnitOp(id="op_co", op="cast_on", consumes=[],
                     produces="t1/rim_start"),
            P.KnitOp(id="op_bo", op="bind_off", consumes=["t1/rim_end"]),
            P.KnitOp(id="op_bad", op="bind_off", consumes=["cap/rim"]),
        ]
        g = P.UGPGraph([t1, cap], [j], ops)
        self.assertTrue(_failed(P.validate(g), "I-SEAL"))


class TestJointLegality(unittest.TestCase):
    """§5.4 legality matrix — I-JOINT."""

    def _graph_with(self, *joints, prims=None, ops=None):
        prims = prims if prims is not None else [_tube("t1"), _tube("t2",
                                                                 origin=(0,
                                                                         100,
                                                                         0))]
        return P.UGPGraph(prims, list(joints), ops or [])

    def test_rim_joint_knit_child_unsupported_rejected(self):
        j = _joint("j", "rim_joint", "t2", "rim_start", "t1", "rim_end",
                   "unsupported", "rim", (50, 100, 0), anchor_b="rim_end")
        self.assertTrue(_failed(P.validate(self._graph_with(j)), "I-JOINT"))

    def test_rim_joint_inert_child_knitted_in_rejected(self):
        cap = P.Primitive(id="cap", kind="disk", params={"r": 50},
                          origin=(0, 100, 0))
        j = _joint("j", "rim_joint", "cap", "rim", "t1", "rim_end",
                   "knitted_in", "rim", (50, 100, 0), anchor_b="rim_end",
                   realized_by=["op_pu"])
        ops = [P.KnitOp(id="op_pu", op="pick_up",
                        consumes=["t1/rim_end"], produces="cap/rim")]
        g = self._graph_with(j, prims=[_tube("t1"), cap], ops=ops)
        self.assertTrue(_failed(P.validate(g), "I-JOINT"))

    def test_surface_branch_knitted_in_rejected(self):
        palm = P.Primitive(id="palm", kind="sphere", params={"r": 60},
                           origin=(0, 0, 0))
        pad = P.Primitive(id="pad", kind="disk", params={"r": 8},
                          origin=(0, 60, 0))
        j = _joint("j", "surface_branch", "pad", "rim", "palm", None,
                   "knitted_in", "surface", (0, 60, 0), realized_by=["op_pu"])
        ops = [P.KnitOp(id="op_pu", op="pick_up", consumes=["palm/rim"],
                        produces="pad/rim")]
        g = self._graph_with(j, prims=[palm, pad], ops=ops)
        self.assertTrue(_failed(P.validate(g), "I-JOINT"))

    def test_surface_branch_with_parent_boundary_rejected(self):
        palm = P.Primitive(id="palm", kind="sphere", params={"r": 60},
                           origin=(0, 0, 0))
        pad = P.Primitive(id="pad", kind="disk", params={"r": 8},
                          origin=(0, 60, 0))
        j = _joint("j", "surface_branch", "pad", "rim", "palm", "rim",
                   "unsupported", "surface", (0, 60, 0))
        g = self._graph_with(j, prims=[palm, pad])
        self.assertTrue(_failed(P.validate(g), "I-JOINT"))

    def test_terminus_continuation_selvedge_seam_rejected(self):
        j = _joint("j", "terminus_continuation", "t2", "rim_start", "t1",
                   "rim_end", "selvedge_seam", "terminus", (0, 100, 0),
                   anchor_b="rim_end", realized_by=["op_s"])
        ops = [P.KnitOp(id="op_s", op="selvedge_seam",
                        consumes=["t1/rim_end", "t2/rim_start"])]
        self.assertTrue(_failed(
            P.validate(self._graph_with(j, ops=ops)), "I-JOINT"))

    def test_terminus_continuation_inert_child_rejected(self):
        cap = P.Primitive(id="cap", kind="disk", params={"r": 50},
                          origin=(0, 100, 0))
        j = _joint("j", "terminus_continuation", "cap", "rim", "t1",
                   "rim_end", "unsupported", "terminus", (0, 100, 0),
                   anchor_b="rim_end")
        g = self._graph_with(j, prims=[_tube("t1"), cap])
        self.assertTrue(_failed(P.validate(g), "I-JOINT"))

    def test_knitted_in_requires_pick_up_consuming_parent_rim(self):
        j = _joint("j", "terminus_continuation", "t2", "rim_start", "t1",
                   "rim_end", "knitted_in", "terminus", (0, 100, 0),
                   anchor_b="rim_end", realized_by=[])
        self.assertTrue(_failed(
            P.validate(self._graph_with(j)), "I-JOINT"))

    def test_knitted_in_pick_up_must_consume_parent_rim(self):
        j = _joint("j", "terminus_continuation", "t2", "rim_start", "t1",
                   "rim_end", "knitted_in", "terminus", (0, 100, 0),
                   anchor_b="rim_end", realized_by=["op_pu"])
        ops = [P.KnitOp(id="op_pu", op="pick_up",
                        consumes=["t1/rim_start"], produces="t2/rim_start")]
        self.assertTrue(_failed(
            P.validate(self._graph_with(j, ops=ops)), "I-JOINT"))

    def test_grafted_requires_graft_op_consuming_both_rims(self):
        j = _joint("j", "rim_joint", "t2", "rim_start", "t1", "rim_end",
                   "grafted", "rim", (50, 100, 0), anchor_b="rim_end")
        self.assertTrue(_failed(
            P.validate(self._graph_with(j)), "I-JOINT"))

    def test_selvedge_seam_requires_selvedge_op(self):
        j = _joint("j", "rim_joint", "t2", "rim_start", "t1", "rim_end",
                   "selvedge_seam", "rim", (50, 100, 0), anchor_b="rim_end",
                   realized_by=["op_g"])
        ops = [P.KnitOp(id="op_g", op="graft",
                        consumes=["t1/rim_end", "t2/rim_start"])]
        self.assertTrue(_failed(
            P.validate(self._graph_with(j, ops=ops)), "I-JOINT"))

    def test_unsupported_requires_empty_realized_by(self):
        j = _joint("j", "surface_branch", "t2", "rim_start", "t1", None,
                   "unsupported", "surface", (0, 100, 0),
                   realized_by=["op_bo"])
        ops = [P.KnitOp(id="op_bo", op="bind_off",
                        consumes=["t1/rim_end"])]
        self.assertTrue(_failed(
            P.validate(self._graph_with(j, ops=ops)), "I-JOINT"))

    def test_anchor_feature_must_match_joint_type(self):
        j = _joint("j", "rim_joint", "t2", "rim_start", "t1", "rim_end",
                   "grafted", "surface", (50, 100, 0), anchor_b="rim_end",
                   realized_by=["op_g"])
        ops = [P.KnitOp(id="op_g", op="graft",
                        consumes=["t1/rim_end", "t2/rim_start"])]
        self.assertTrue(_failed(
            P.validate(self._graph_with(j, ops=ops)), "I-JOINT"))

    def test_terminus_continuation_requires_terminus_anchor(self):
        j = _joint("j", "terminus_continuation", "t2", "rim_start", "t1",
                   "rim_end", "knitted_in", "rim", (50, 100, 0),
                   anchor_b="rim_end", realized_by=["op_pu"])
        ops = [P.KnitOp(id="op_pu", op="pick_up",
                        consumes=["t1/rim_end"], produces="t2/rim_start")]
        self.assertTrue(_failed(
            P.validate(self._graph_with(j, ops=ops)), "I-JOINT"))

    def test_tube_terminus_boundary_is_rim_end(self):
        self.assertEqual(_tube("x").terminus_boundary, "rim_end")

    def test_hemisphere_terminus_boundary_is_rim(self):
        h = P.Primitive(id="h", kind="hemisphere", params={"r": 30},
                        origin=(0, 0, 0))
        self.assertEqual(h.terminus_boundary, "rim")


class TestGraphJsonSchema(unittest.TestCase):
    """§12 graph JSON shape — version, gauge, tolerances, collections."""

    def test_to_dict_shape_matches_spec(self):
        d = _sealed_graph().to_dict()
        self.assertEqual(d["version"], 2)
        self.assertEqual(d["gauge"], {"wale_mm": 2.5, "course_mm": 1.6})
        for const, default in (("T_ANCHOR", 0.5), ("T_RIM", 1.0),
                               ("T_LOOPS", 2.0), ("T_AXIS_EPS", 1e-9),
                               ("MAX_CONT_TURN_DEG", 90.0),
                               ("MAX_BRANCH_TILT_DEG", 90.0)):
            self.assertEqual(d["tolerances"][const], default)
        self.assertEqual(set(d["joints"].keys()),
                         {"rim_joints", "surface_branches",
                          "terminus_continuations"})
        self.assertEqual([o["op"] for o in d["ops"]],
                         ["cast_on", "pick_up", "bind_off"])

    def test_op_instance_schema_fields(self):
        d = _sealed_graph().to_dict()
        pu = [o for o in d["ops"] if o["op"] == "pick_up"][0]
        self.assertEqual(set(pu.keys()),
                         {"id", "op", "consumes", "produces", "params"})
        self.assertEqual(pu["consumes"], ["t1/rim_end"])
        self.assertEqual(pu["produces"], "t2/rim_start")

    def test_joint_json_schema_fields(self):
        d = _sealed_graph().to_dict()
        j = d["joints"]["terminus_continuations"][0]
        self.assertEqual(set(j.keys()),
                         {"id", "joint", "child", "child_boundary", "parent",
                          "parent_boundary", "construction", "anchor",
                          "realized_by"})
        self.assertEqual(set(j["anchor"].keys()),
                         {"feature", "boundary", "point"})

    def test_roundtrip_preserves_joints_ops_gauge(self):
        g = _sealed_graph()
        rt = P.UGPGraph.from_json(g.to_json())
        self.assertEqual(len(rt.terminus_continuations), 1)
        self.assertEqual(len(rt.ops), 3)
        self.assertEqual(rt.gauge, g.gauge)
        self.assertEqual(rt.open_boundaries, [])
        self.assertEqual(rt.get("t2").origin, (0.0, 100.0, 0.0))

    def test_roundtrip_validates(self):
        rt = P.UGPGraph.from_json(_sealed_graph().to_json())
        self.assertEqual(_status(P.validate(rt), "I-GRAPH"), ["PASS"])

    def test_old_version_json_is_rejected(self):
        with self.assertRaises(P.SchemaError):
            P.UGPGraph.from_dict({"version": 1, "primitives": []})

    def test_tolerances_roundtrip_and_validate_against_them(self):
        g = _sealed_graph()
        g.tolerances["T_RIM"] = 0.001
        rt = P.UGPGraph.from_json(g.to_json())
        self.assertEqual(rt.tolerances["T_RIM"], 0.001)
        # with T_RIM at 0.001, equal rims still pass, but the I-LOOP
        # tolerance stays 2.0 — this graph remains valid
        self.assertFalse(_failed(P.validate(rt), "I-RIMMATCH"))

    def test_unknown_tolerance_constant_rejected(self):
        with self.assertRaises(P.SchemaError):
            P.UGPGraph(tolerances={"T_VIBES": 1.0})

    def test_open_boundaries_roundtrip(self):
        g = _sealed_graph()
        g.ops = [o for o in g.ops if o.id != "op_bo"]
        g.open_boundaries = ["t2/rim_end"]
        rt = P.UGPGraph.from_json(g.to_json())
        self.assertEqual(rt.open_boundaries, ["t2/rim_end"])
        self.assertEqual(_status(P.validate(rt), "I-SEAL"), ["PASS"])


class TestBackendContract(unittest.TestCase):
    """§8: per-class CHECKS/UNVERIFIED declarations + registry semantics."""

    def test_default_knit_backend_preseeded(self):
        be = P.get_backend("default_knit")
        self.assertEqual(be["id"], "default_knit")

    def test_default_sim_backend_preseeded(self):
        self.assertEqual(P.get_backend("default_sim")["id"], "default_sim")

    def test_declaration_covers_exactly_the_invariant_classes(self):
        for bid in ("default_knit", "default_sim"):
            be = P.get_backend(bid)
            declared = set(be["checks"]) | set(be["unverified"])
            self.assertEqual(declared, set(P.INARIANT_CLASSES), bid)
            overlap = set(be["checks"]) & set(be["unverified"])
            self.assertEqual(overlap, set(), bid)

    def test_default_knit_rechecks_everything(self):
        be = P.get_backend("default_knit")
        self.assertEqual(set(be["checks"]), set(P.INARIANT_CLASSES))
        self.assertEqual(be["unverified"], [])

    def test_add_backend_is_additive_not_replacing(self):
        P.add_backend("default_knit", checks=[], unverified=[
            "I-DEGENERATE", "I-SCHEMA", "I-AXIS", "I-GRAPH", "I-ANCHOR",
            "I-RIMMATCH", "I-CONT", "I-BRANCHORIENT", "I-LOOP", "I-SEAL",
            "I-JOINT"])
        try:
            self.assertEqual(P.get_backend("default_knit")["id"],
                             "default_knit")
            self.assertEqual(set(P.get_backend("default_knit")["checks"]),
                             set(P.INARIANT_CLASSES))
            custom = P.get_backend("default_knit__custom")
            self.assertEqual(custom["checks"], [])
        finally:
            P._reset_backends()

    def test_incomplete_declaration_is_registry_error(self):
        with self.assertRaises(P.RegistryError):
            P.add_backend("lazy", checks=["I-SEAL"], unverified=[])

    def test_class_in_both_lists_is_registry_error(self):
        with self.assertRaises(P.RegistryError):
            P.add_backend("greedy", checks=["I-SEAL"],
                          unverified=["I-SEAL", "I-GRAPH", "I-SCHEMA",
                                      "I-AXIS", "I-DEGENERATE", "I-ANCHOR",
                                      "I-RIMMATCH", "I-CONT",
                                      "I-BRANCHORIENT", "I-LOOP",
                                      "I-JOINT"])

    def test_unknown_class_in_declaration_is_registry_error(self):
        classes = list(P.INARIANT_CLASSES)
        with self.assertRaises(P.RegistryError):
            P.add_backend("sloppy", checks=classes[:-1] + ["I-VIBES"],
                          unverified=[])

    def test_buildability_report_per_class(self):
        g = _sealed_graph()
        g.add_op(P.KnitOp(id="op_bo2", op="bind_off",
                          consumes=["t1/rim_start"]))
        report = P.buildability_report(g, "default_knit")
        self.assertEqual(report["backend"], "default_knit")
        self.assertEqual(report["geometric_validity"], "FAIL")
        self.assertEqual(report["per_class"]["I-SEAL"], "FAIL")
        self.assertEqual(report["failing_instances"]["I-SEAL"],
                         ["t1/rim_start"])
        self.assertEqual(
            set(report["per_class"].keys()), set(P.INARIANT_CLASSES))
        # geometric validity never implies knitability (§9)
        self.assertIn("knitability", report["note"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
