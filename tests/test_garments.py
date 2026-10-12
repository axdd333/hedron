"""UGC-01 test batch 2: garment generators (ugc.garments)."""
import math
import unittest

from ugc.garments import build_garment, GARMENT_FAMILIES


class TestRegistry(unittest.TestCase):
    def test_all_six_u01_families_registered(self):
        for fam in ("hat", "sock", "glove", "skirt", "dress", "trousers",
                    "shorts", "shirt", "hoodie"):
            self.assertIn(fam, GARMENT_FAMILIES)

    def test_unknown_family_raises(self):
        with self.assertRaises(ValueError):
            build_garment("cape")


class TestStructuralSignatures(unittest.TestCase):
    """Each family must show its defining topology, not just 'a shape'."""

    def ids(self, graph):
        return [p.id for p in graph]

    def test_hat_is_capped_tube(self):
        g = build_garment("hat")
        crown = g.get("hat_crown")
        self.assertEqual(crown.kind, "tube")
        self.assertEqual(len(crown.edges["seams"]), 1)   # dome seals top
        self.assertEqual(crown.edges["continuations"], [])

    def test_sock_has_leg_foot_toe_chain(self):
        g = build_garment("sock")
        for pid in ("sock_leg", "sock_heel", "sock_foot", "sock_toe"):
            self.assertIn(pid, self.ids(g))
        leg = g.get("sock_leg")
        self.assertEqual(len(leg.edges["continuations"]), 1)
        foot = g.get("sock_foot")
        # foot runs horizontal, leg vertical
        self.assertAlmostEqual(abs(foot.axis[0]), 1.0, places=6)

    def test_glove_has_four_fingers_and_thumb(self):
        g = build_garment("glove")
        ids = self.ids(g)
        for i in range(1, 5):
            self.assertIn("finger_%d" % i, ids)
        self.assertIn("thumb", ids)
        palm = g.get("glove_palm")
        self.assertEqual(len(palm.edges["branches"]), 5)

    def test_skirt_is_single_tapered_open_tube(self):
        g = build_garment("skirt")
        self.assertEqual(len(g), 1)
        body = g.get("skirt_body")
        self.assertGreater(body.params["r2"], body.params["r1"])  # A-line
        self.assertFalse(body.metrics()["closed"])

    def test_dress_is_torso_plus_skirt_continuation(self):
        g = build_garment("dress")
        torso = g.get("dress_torso")
        self.assertEqual(len(torso.edges["continuations"]), 1)

    def test_trousers_branch_into_two_legs(self):
        g = build_garment("trousers")
        hips = g.get("trousers_hips")
        self.assertEqual(len(hips.edges["branches"]), 2)
        leg_ids = [e["child"] for e in hips.edges["branches"]]
        self.assertIn("trousers_leg_l", leg_ids)
        self.assertIn("trousers_leg_r", leg_ids)

    def test_shorts_are_short_trousers(self):
        g = build_garment("shorts")
        leg = g.get("trousers_leg_l")
        self.assertLess(leg.params["l"], 250)

    def test_shirt_has_two_sleeve_branches(self):
        g = build_garment("shirt")
        torso = g.get("shirt_torso")
        branches = [e["child"] for e in torso.edges["branches"]]
        self.assertEqual(sorted(branches), ["shirt_sleeve_l",
                                            "shirt_sleeve_r"])

    def test_hoodie_adds_hood_to_shirt(self):
        g = build_garment("hoodie")
        self.assertIn("hood", [p.id for p in g])
        hood = g.get("hood")
        self.assertTrue(hood.metrics()["closed"])


class TestScalingAndValidity(unittest.TestCase):
    def test_scale_multiplies_all_linear_params(self):
        base = build_garment("shirt", scale=1.0)
        big = build_garment("shirt", scale=1.2)
        self.assertAlmostEqual(big.get("shirt_torso").params["r1"],
                               base.get("shirt_torso").params["r1"] * 1.2,
                               places=6)
        self.assertAlmostEqual(big.get("shirt_torso").params["l"],
                               base.get("shirt_torso").params["l"] * 1.2,
                               places=6)

    def test_scale_is_validated(self):
        with self.assertRaises(ValueError):
            build_garment("hat", scale=0)

    def test_all_axes_unit_length(self):
        for fam in GARMENT_FAMILIES:
            g = build_garment(fam)
            for p in g:
                n = math.sqrt(sum(c * c for c in p.axis))
                self.assertAlmostEqual(n, 1.0, places=9,
                                       msg="%s/%s axis not unit" % (fam, p.id))

    def test_every_graph_json_roundtrips(self):
        from ugc.primitives import UGPGraph
        for fam in GARMENT_FAMILIES:
            g = build_garment(fam)
            g2 = UGPGraph.from_json(g.to_json())
            self.assertEqual(len(g2), len(g), fam)


if __name__ == "__main__":
    unittest.main(verbosity=2)
