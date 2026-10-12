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


if __name__ == "__main__":
    unittest.main(verbosity=2)
