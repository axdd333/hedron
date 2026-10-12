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


if __name__ == "__main__":
    unittest.main(verbosity=2)
