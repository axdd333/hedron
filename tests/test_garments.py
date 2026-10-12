"""UGC-01 test batch 2: garment generators on the spec-v2 IR (t_0b0420f0).

The v1 structural tests were rewritten against DESIGN.md spec v2: declared
joints (type x construction x anchor), explicit default_knit ops, boundary
descriptors with real mm lengths and course-unit loops, and every family
validating clean under ugc.primitives.validate_strict.

Cycles (TDD, RED+GREEN per cycle):
  C1  registry, scale contract, unit axes, JSON roundtrip
  C2  v2 knit structure: declared joints + ops + open_boundaries, all
      nine families validate_strict-clean
  C3  gauge + boundary descriptors carrying real mm + course units
"""
import math
import unittest

from ugc.garments import build_garment, GARMENT_FAMILIES
from ugc.primitives import UGPGraph

FAMILIES = ("hat", "sock", "glove", "skirt", "dress", "trousers",
            "shorts", "shirt", "hoodie")

_LINEAR_KEYS = ("r1", "r2", "l", "r", "rx", "ry", "rz", "w", "h")


class TestRegistry(unittest.TestCase):
    def test_all_six_u01_families_registered(self):
        for fam in FAMILIES:
            self.assertIn(fam, GARMENT_FAMILIES)

    def test_unknown_family_raises(self):
        with self.assertRaises(ValueError):
            build_garment("cape")


class TestScaling(unittest.TestCase):
    def test_scale_multiplies_every_linear_param(self):
        base = build_garment("shirt", scale=1.0)
        big = build_garment("shirt", scale=1.2)
        self.assertEqual([p.id for p in base], [p.id for p in big])
        for b, s in zip(base, big):
            self.assertEqual(b.kind, s.kind, b.id)
            for key, val in b.params.items():
                if key in _LINEAR_KEYS:
                    self.assertAlmostEqual(
                        s.params[key], val * 1.2, places=6,
                        msg="%s.%s not scaled" % (b.id, key))
            for c_base, c_big in zip(b.origin, s.origin):
                self.assertAlmostEqual(c_big, c_base * 1.2, places=6,
                                       msg="%s origin not scaled" % b.id)

    def test_scale_keeps_axes_unit(self):
        for p in build_garment("hoodie", scale=3.0):
            n = math.sqrt(sum(c * c for c in p.axis))
            self.assertAlmostEqual(n, 1.0, places=9, msg=p.id)

    def test_scale_is_validated(self):
        for bad in (0, -1, -0.5, float("nan"), float("inf"), True, "2", None):
            with self.assertRaises(ValueError):
                build_garment("hat", scale=bad)


class TestJSONRoundtrip(unittest.TestCase):
    def test_every_family_json_roundtrips(self):
        for fam in FAMILIES:
            g = build_garment(fam)
            g2 = UGPGraph.from_json(g.to_json())
            self.assertEqual(len(g2), len(g), fam)
            self.assertEqual(g2.to_json(), g.to_json(), fam)
            self.assertEqual(g2.to_dict()["version"], 2, fam)


class TestKnitStructure(unittest.TestCase):
    """C2: v2 knit structure per family.

    Each family runs an explicit default_knit op program (cast_on roots,
    pick_up/graft closures) and declares joints of the expected type.
    I-SEAL demands exactly one disposition per knit-bearing rim: produced
    by an op (fabric_start) XOR consumed by an op XOR declared open.
    """
    STRUCTURE = {
        # family: (op verbs, joint types)
        "hat":      ({"cast_on", "graft"}, {"rim_joint"}),
        "sock":     ({"cast_on", "pick_up", "graft"},
                     {"terminus_continuation"}),
        "glove":    ({"cast_on", "graft"},
                     {"rim_joint", "surface_branch"}),
        "skirt":    ({"cast_on"}, set()),
        "dress":    ({"cast_on", "pick_up"}, {"terminus_continuation"}),
        "trousers": ({"cast_on"}, {"surface_branch"}),
        "shorts":   ({"cast_on"}, {"surface_branch"}),
        "shirt":    ({"cast_on"}, {"surface_branch"}),
        "hoodie":   ({"cast_on", "graft"},
                     {"rim_joint", "surface_branch"}),
    }

    def test_family_op_programs_and_joints(self):
        for fam, (verbs, joints) in self.STRUCTURE.items():
            g = build_garment(fam)
            self.assertEqual({o.op for o in g.ops}, verbs, fam)
            self.assertEqual({j.joint for j in g.joints()}, joints, fam)

    def test_every_joint_realized_or_documented_unsupported(self):
        # §5.4: a joint claims realization via ops, or is construction
        # "unsupported" (documented, not hidden — realized_by empty).
        for fam in FAMILIES:
            g = build_garment(fam)
            op_ids = {o.id for o in g.ops}
            for j in g.joints():
                if j.construction == "unsupported":
                    self.assertFalse(j.realized_by, (fam, j.id))
                else:
                    self.assertTrue(j.realized_by, (fam, j.id))
                    for rid in j.realized_by:
                        self.assertIn(rid, op_ids, (fam, j.id, rid))

    def test_one_state_per_rim(self):
        # I-SEAL: a rim in open_boundaries must not also be produced or
        # consumed by any op.
        for fam in FAMILIES:
            g = build_garment(fam)
            produced = {o.produces for o in g.ops if o.produces}
            consumed = {c for o in g.ops for c in o.consumes}
            for ref in g.open_boundaries:
                self.assertNotIn(ref, produced, (fam, ref))
                self.assertNotIn(ref, consumed, (fam, ref))

    def test_every_rim_disposed(self):
        # I-SEAL: every knit-bearing rim has exactly one disposition.
        for fam in FAMILIES:
            g = build_garment(fam)
            produced = {o.produces for o in g.ops if o.produces}
            consumed = {c for o in g.ops for c in o.consumes}
            for p in g:
                for b in p.boundaries:
                    if b.kind != "rim":
                        continue
                    ref = "%s/%s" % (p.id, b.boundary)
                    states = (ref in produced, ref in consumed,
                              ref in g.open_boundaries)
                    self.assertEqual(sum(states), 1, (fam, ref))

    def test_all_families_validate_strict_clean(self):
        from ugc.primitives import validate_strict
        for fam in FAMILIES:
            findings = validate_strict(build_garment(fam))
            self.assertEqual(
                [f for f in findings if f.status == "FAIL"], [], fam)


if __name__ == "__main__":
    unittest.main(verbosity=2)
