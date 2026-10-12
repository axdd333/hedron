"""UGC-01 test batch 1: Universal Garment Primitive (ugc.primitives)."""
import math
import unittest

import ugc.primitives as P


class TestPrimitiveDefaultsAndNormalization(unittest.TestCase):
    def test_tube_defaults_all_params_ten_mm(self):
        t = P.Primitive(id="t1", kind="tube", params={}, pos=(0, 0, 0))
        self.assertEqual(t.params["r1"], 10)
        self.assertEqual(t.params["r2"], 10)
        self.assertEqual(t.params["l"], 10)

    def test_default_orientation_is_unit_y(self):
        t = P.Primitive(id="t2", kind="tube", params={}, pos=(0, 0, 0))
        self.assertEqual(t.axis, (0.0, 1.0, 0.0))

    def test_axis_is_normalized_on_ingest(self):
        t = P.Primitive(id="t3", kind="tube", params={}, pos=(0, 0, 0),
                        axis=(2, 0, 0))
        self.assertEqual(t.axis, (1.0, 0.0, 0.0))

    def test_zero_axis_is_rejected(self):
        with self.assertRaises(ValueError):
            P.Primitive(id="t4", kind="tube", params={}, pos=(0, 0, 0),
                        axis=(0, 0, 0))


class TestTransforms(unittest.TestCase):
    def test_world_to_local_translates_and_inverse_rotates(self):
        t = P.Primitive(id="w1", kind="tube", params={"l": 100}, pos=(5, 0, 0),
                        axis=(0, 1, 0))
        world_pt = (15, 50, 0)          # local (10, 50, 0)
        self.assertEqual(t.world_to_local(world_pt), (10.0, 50.0, 0.0))

    def test_rotation_matrix_maps_z_to_x_for_90deg_y(self):
        r = P.Primitive.rotation_matrix(90.0, (0, 1, 0))
        self.assertAlmostEqual(r[0][0], 0.0, places=9)
        self.assertAlmostEqual(r[0][2], 1.0, places=9)
        self.assertAlmostEqual(r[2][0], -1.0, places=9)


class TestAttachment(unittest.TestCase):
    def _parent(self):
        return P.Primitive(id="torso", kind="tube",
                           params={"r1": 100, "r2": 100, "l": 50},
                           pos=(0, 0, 0))

    def test_branch_child_origin_snaps_to_parent_origin(self):
        parent = self._parent()
        child = P.Primitive(id="sleeve", kind="tube",
                            params={"r1": 30, "r2": 25, "l": 100},
                            pos=(10, 10, 10))
        rel = parent.attach_branch(child, pos=(0, 0, 0))
        self.assertEqual(rel["tag"], "branch")
        self.assertEqual(child.origin, parent.origin)

    def test_continuation_child_snaps_to_parent_terminus(self):
        parent = self._parent()
        child = P.Primitive(id="skirt", kind="tube",
                            params={"r1": 100, "r2": 120, "l": 80},
                            pos=(0, 80, 0))
        rel = parent.attach_continuation(child, pos=(0, 50, 0))
        self.assertEqual(rel["tag"], "continuation")
        self.assertEqual(child.origin, (0.0, 50.0, 0.0))
        self.assertEqual(child.world_to_local((0, 50, 0)), (0.0, 0.0, 0.0))

    def test_unknown_attachment_tag_is_rejected(self):
        parent = self._parent()
        child = P.Primitive(id="x", kind="tube", params={}, pos=(0, 0, 0))
        with self.assertRaises(ValueError):
            parent._attach(child, "weld", pos=(0, 0, 0))

    def test_seam_seals_open_rim_with_closed_cap(self):
        parent = self._parent()
        cap = P.Primitive(id="hat_top", kind="sphere", params={"r": 100},
                          pos=(0, 0, 0))
        rel = parent.attach_seam(cap, pos=(0, 0, 0))
        self.assertEqual(rel["tag"], "seam")
        self.assertEqual(cap.origin, parent.origin)
        self.assertIn("hat_top",
                      [e["child"] for e in parent.edges["seams"]])

    def test_mount_lays_closed_child_on_closed_parent_surface(self):
        parent = P.Primitive(id="palm", kind="sphere", params={"r": 40},
                             pos=(0, 0, 0))
        pad = P.Primitive(id="pad", kind="disk", params={"r": 8},
                          pos=(0, 40, 0))
        rel = parent.attach_mount(pad, pos=(0, 40, 0))
        self.assertEqual(rel["tag"], "mount")
        self.assertEqual(pad.origin, (0.0, 40.0, 0.0))
        self.assertIn("pad", [e["child"] for e in parent.edges["mounts"]])


class TestGeometryAndSerialization(unittest.TestCase):
    def test_sphere_metrics_closed_form(self):
        s = P.Primitive(id="s", kind="sphere", params={"r": 10}, pos=(0, 0, 0))
        m = s.metrics()
        self.assertTrue(m["closed"])
        self.assertAlmostEqual(m["volume"], 4000.0 * math.pi / 3.0, delta=0.02)
        self.assertAlmostEqual(m["surfaceArea"], 400.0 * math.pi, delta=0.02)

    def test_tapered_tube_metrics(self):
        t = P.Primitive(id="tt", kind="tube",
                        params={"r1": 10, "r2": 5, "l": 50}, pos=(0, 0, 0))
        m = t.metrics()
        expected = math.pi * 50.0 * (100.0 + 50.0 + 25.0) / 3.0
        self.assertFalse(m["closed"])
        self.assertAlmostEqual(m["volume"], expected, delta=0.02)
        self.assertEqual(m["terminus"], (0.0, 50.0, 0.0))

    def test_json_roundtrip_preserves_everything(self):
        parent = P.Primitive(id="torso", kind="tube",
                             params={"r1": 100, "r2": 110, "l": 50},
                             pos=(0, 0, 0), axis=(0, 1, 0))
        child = P.Primitive(id="skirt", kind="tube",
                            params={"r1": 110, "r2": 130, "l": 80},
                            pos=(0, 80, 0))
        parent.attach_continuation(child, pos=(0, 50, 0))
        blob = P.UGPGraph([parent, child]).to_json()
        graph = P.UGPGraph.from_json(blob)
        g = graph.get("torso")
        self.assertEqual(g.params["r2"], 110)
        self.assertEqual(g.edges["continuations"][0]["child"], "skirt")
        c = graph.get("skirt")
        self.assertEqual(c.origin, (0.0, 50.0, 0.0))
        self.assertEqual(c.axis, (0.0, 1.0, 0.0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
