"""Spec v3 topology layer — Patch / Junction (C1, DESIGN_V3_TOPOLOGY.md).

RED contract for cycle 1: patch/junction construction + orientation
validation. v2 Primitive/UGPGraph stay untouched in behavior; the v3
layer is additive (patches + junctions ride on the same graph).

Topology bookkeeping (the invariant I-chi will close in C2):
- a patch spanning k boundary curves contributes chi = 2 - k;
- a junction identifies boundary curves pairwise (even arity,
  alternating traversal directions) and never changes chi;
- declared chi = 2 - 2g - n_free must equal sum(2 - k) over patches.
"""
import unittest

from ugc.primitives import (Boundary, Junction, Patch, PatchError,
                            PrimitiveError, SchemaError, UGPGraph)


def _rim(bid, length_mm, center=(0.0, 0.0, 0.0), normal=(0.0, 1.0, 0.0)):
    return Boundary(bid, "rim", length_mm, frame=(center, normal))


class TestPatchConstruction(unittest.TestCase):
    def test_k2_patch_is_the_tube_case(self):
        p = Patch("torso", [_rim("hem", 600), _rim("neck", 660)])
        self.assertEqual(p.k, 2)
        self.assertEqual(p.chi_contribution, 0)
        self.assertEqual([b.boundary for b in p.boundaries],
                         ["hem", "neck"])

    def test_k1_patch_is_the_cap_case(self):
        p = Patch("dome", [_rim("rim", 565)])
        self.assertEqual(p.k, 1)
        self.assertEqual(p.chi_contribution, 1)

    def test_k4_web_patch(self):
        p = Patch("shirt_torso", [_rim("hem", 700), _rim("neck", 660),
                                  _rim("armhole_l", 330),
                                  _rim("armhole_r", 330)])
        self.assertEqual(p.k, 4)
        self.assertEqual(p.chi_contribution, -2)

    def test_zero_spans_rejected(self):
        with self.assertRaises(PatchError):
            Patch("empty", [])

    def test_nonpositive_length_span_rejected(self):
        # a non-positive Boundary cannot even be constructed (its own ctor
        # raises first). Patch still guards the length itself because
        # Boundary.length_mm is mutable after construction (defense in
        # depth for mutated boundaries).
        with self.assertRaises(PrimitiveError):
            Patch("bad", [Boundary("r", "rim", -1.0)])
        b = Boundary("r", "rim", 10.0)
        b.length_mm = 0.0
        with self.assertRaises(PatchError):
            Patch("bad", [b])

    def test_inert_span_allowed_but_patch_must_carry_one_rim(self):
        with self.assertRaises(PatchError):
            Patch("bad", [Boundary("e", "inert", 10.0)])

    def test_duplicate_span_ids_rejected(self):
        with self.assertRaises(PatchError):
            Patch("bad", [_rim("rim", 10), _rim("rim", 10)])

    def test_bad_id_rejected(self):
        with self.assertRaises(PatchError):
            Patch("has space", [_rim("rim", 10)])

    def test_to_dict_roundtrip(self):
        p = Patch("torso", [_rim("hem", 600), _rim("neck", 660)])
        d = p.to_dict()
        self.assertEqual(d["id"], "torso")
        self.assertEqual([s["boundary"] for s in d["spans"]],
                         ["hem", "neck"])
        p2 = Patch.from_dict(d)
        self.assertEqual(p2, p)


class TestJunctionConstruction(unittest.TestCase):
    def _members(self, dirs=("cw", "ccw")):
        refs = [("torso", "armhole_l"), ("sleeve_l", "armhole")]
        return [(r[0], r[1], d) for r, d in zip(refs, dirs)]

    def test_pair_junction(self):
        j = Junction("j_arm_l", self._members())
        self.assertEqual(j.arity, 2)
        self.assertEqual(j.member_refs,
                         ("torso/armhole_l", "sleeve_l/armhole"))

    def test_single_member_rejected(self):
        with self.assertRaises(PatchError):
            Junction("j1", [("torso", "armhole_l", "cw")])

    def test_odd_arity_rejected(self):
        # identification is pairwise: 3 curves at one site is not a
        # manifold identification (the saddle case is a k>=3 web patch,
        # joined by pairwise junctions).
        with self.assertRaises(PatchError):
            Junction("j3", [("a", "r1", "cw"), ("b", "r1", "ccw"),
                            ("c", "r1", "cw")])

    def test_conflicting_traversal_directions_rejected(self):
        # both members traversed the same way -> the seam folds the
        # fabric inside-out (DESIGN_V3 I-ORIENT, construction level)
        with self.assertRaises(PatchError):
            Junction("j_bad", self._members(dirs=("cw", "cw")))

    def test_duplicate_ref_rejected(self):
        with self.assertRaises(PatchError):
            Junction("j_dup", [("a", "r", "cw"), ("a", "r", "ccw")])

    def test_arity4_alternating_ok(self):
        j = Junction("j4", [("a", "r1", "cw"), ("b", "r1", "ccw"),
                            ("c", "r2", "cw"), ("d", "r2", "ccw")])
        self.assertEqual(j.arity, 4)

    def test_arity4_unbalanced_rejected(self):
        with self.assertRaises(PatchError):
            Junction("j4b", [("a", "r1", "cw"), ("b", "r1", "ccw"),
                             ("c", "r2", "cw"), ("d", "r2", "cw")])

    def test_unknown_construction_rejected(self):
        with self.assertRaises(PatchError):
            Junction("j", self._members(), construction="hot_glue")

    def test_to_dict_roundtrip(self):
        j = Junction("j_arm_l", self._members(), construction="grafted")
        d = j.to_dict()
        self.assertEqual(d["members"][0],
                         {"patch": "torso", "boundary": "armhole_l",
                          "direction": "cw"})
        self.assertEqual(Junction.from_dict(d), j)


class TestGraphV3Layer(unittest.TestCase):
    def _shirtish(self):
        g = UGPGraph()
        g.add_patch(Patch("torso", [_rim("hem", 700), _rim("neck", 660),
                                    _rim("armhole_l", 330),
                                    _rim("armhole_r", 330)]))
        g.add_patch(Patch("sleeve_l", [_rim("armhole", 330),
                                       _rim("cuff", 300)]))
        g.add_patch(Patch("sleeve_r", [_rim("armhole", 330),
                                       _rim("cuff", 300)]))
        return g

    def test_add_and_query_patches_sorted_by_id(self):
        g = self._shirtish()
        self.assertEqual([p.id for p in g.patches()],
                         ["sleeve_l", "sleeve_r", "torso"])

    def test_duplicate_patch_id_rejected(self):
        g = self._shirtish()
        with self.assertRaises(SchemaError):
            g.add_patch(Patch("torso", [_rim("rim", 10)]))

    def test_junction_member_refs_must_resolve(self):
        g = self._shirtish()
        with self.assertRaises(SchemaError):
            g.add_junction(Junction("j", [("torso", "nope", "cw"),
                                          ("sleeve_l", "armhole", "ccw")]))

    def test_duplicate_junction_id_rejected(self):
        g = self._shirtish()
        g.add_junction(Junction("j_l", [("torso", "armhole_l", "cw"),
                                        ("sleeve_l", "armhole", "ccw")]))
        with self.assertRaises(SchemaError):
            g.add_junction(Junction("j_l", [("torso", "armhole_r", "cw"),
                                            ("sleeve_r", "armhole", "ccw")]))

    def test_a_rim_may_sit_in_at_most_one_junction(self):
        g = self._shirtish()
        g.add_junction(Junction("j_l", [("torso", "armhole_l", "cw"),
                                        ("sleeve_l", "armhole", "ccw")]))
        with self.assertRaises(SchemaError):
            g.add_junction(Junction("j_l2", [("torso", "armhole_l", "cw"),
                                             ("sleeve_r", "armhole", "ccw")]))

    def test_junctions_sorted_by_id(self):
        g = self._shirtish()
        g.add_junction(Junction("j_r", [("torso", "armhole_r", "cw"),
                                        ("sleeve_r", "armhole", "ccw")]))
        g.add_junction(Junction("j_l", [("torso", "armhole_l", "cw"),
                                        ("sleeve_l", "armhole", "ccw")]))
        self.assertEqual([j.id for j in g.junctions()], ["j_l", "j_r"])

    def test_to_dict_additive_keys_and_roundtrip(self):
        g = self._shirtish()
        g.add_junction(Junction("j_l", [("torso", "armhole_l", "cw"),
                                        ("sleeve_l", "armhole", "ccw")]))
        d = g.to_dict()
        # version stays 2 (v3 is an additive layer, viewer/CLI unchanged)
        self.assertEqual(d["version"], 2)
        self.assertEqual(len(d["patches"]), 3)
        self.assertEqual(len(d["junctions"]), 1)
        g2 = UGPGraph.from_dict(d)
        self.assertEqual([p.id for p in g2.patches()],
                         [p.id for p in g.patches()])
        self.assertEqual([j.id for j in g2.junctions()],
                         [j.id for j in g.junctions()])

    def test_v2_graph_dict_has_no_patch_keys(self):
        d = UGPGraph().to_dict()
        self.assertNotIn("patches", d)
        self.assertNotIn("junctions", d)


if __name__ == "__main__":
    unittest.main()
