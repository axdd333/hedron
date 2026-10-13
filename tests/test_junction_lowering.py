"""Spec v3 junction-graph lowering — op-pattern rules (C4, t_8ea48971).

RED contract for cycle 4 (DESIGN_V3_TOPOLOGY.md): the junction graph
lowers to a per-junction knit plan alongside (never replacing) the v2
op-program lowering.

Rules under test:
- every junction lowers to exactly one plan entry, sorted by junction id,
  content-keyed and byte-deterministic;
- construction -> op pattern:
    knitted_in    -> ("PICK_UP", "KNIT")  per identified pair
    grafted       -> ("GRAFT",)           per identified pair
    selvedge_seam -> ("SELVEDGE_SEAM",)   per identified pair
    unsupported   -> no pattern (documented refusal, like v2 §10)
- realization is checked against the v2 op program verbatim: a junction
  pair is REALIZED only when some v2 op both consumes and produces/-
  consumes the two member curve refs by their exact names. Junctions
  across synthetic curves (shirt armholes, trousers leg tops, the
  hoodie's re-id'd neck) are UNREALIZED — the v3 pattern is advised,
  the v2 program casts fresh fabric instead, and the plan says so;
- invalid graphs are refused (BackendNotApplicable), never planned;
- v2-only graphs (no patches) lower to an empty plan.
"""
import json
import unittest

from ugc import backend as B
from ugc.garments import build_garment
from ugc.primitives import (Boundary, Junction, Patch, UGPGraph)

# family: (n_junction_plan_entries, n_realized, n_unrealized)
PLAN = {
    "hat":      (1, 1, 0),
    "sock":     (2, 2, 0),
    "glove":    (1, 1, 0),
    "skirt":    (0, 0, 0),
    "dress":    (1, 1, 0),
    "trousers": (2, 0, 2),
    "shorts":   (2, 0, 2),
    "shirt":    (2, 0, 2),
    "hoodie":   (3, 0, 3),
}


class TestJunctionPlan(unittest.TestCase):
    def test_every_family_plans_its_junctions(self):
        for fam, (n, realized, unrealized) in PLAN.items():
            plan = B.lower_junctions(build_garment(fam))
            self.assertEqual(len(plan), n, fam)
            self.assertEqual(
                sum(1 for e in plan if e.status == "REALIZED"), realized,
                fam)
            self.assertEqual(
                sum(1 for e in plan if e.status == "UNREALIZED"), unrealized,
                fam)

    def test_construction_to_pattern_rules(self):
        g = UGPGraph(gauge={"wale_mm": 2.5, "course_mm": 1.6})
        g.add_patch(Patch("a", [Boundary("r1", "rim", 100),
                                Boundary("r2", "rim", 100)]))
        g.add_patch(Patch("b", [Boundary("r1", "rim", 100),
                                Boundary("r2", "rim", 100)]))
        g.declared_chi = 0
        g.add_junction(Junction("j_knit", [("a", "r1", "cw"),
                                           ("b", "r1", "ccw")],
                                construction="knitted_in"))
        g.add_junction(Junction("j_seam", [("a", "r2", "cw"),
                                           ("b", "r2", "ccw")],
                                construction="selvedge_seam"))
        plan = {e.graph_junction: e for e in B.lower_junctions(g)}
        self.assertEqual(plan["j_knit"].machine_ops, ("PICK_UP", "KNIT"))
        self.assertEqual(plan["j_seam"].machine_ops, ("SELVEDGE_SEAM",))

    def test_unsupported_construction_gets_no_pattern(self):
        g = UGPGraph(gauge={"wale_mm": 2.5, "course_mm": 1.6})
        g.add_patch(Patch("a", [Boundary("r1", "rim", 100),
                                Boundary("r2", "rim", 100)]))
        g.add_patch(Patch("b", [Boundary("r1", "rim", 100),
                                Boundary("r2", "rim", 100)]))
        g.declared_chi = 0
        g.add_junction(Junction("j_u", [("a", "r1", "cw"),
                                        ("b", "r1", "ccw")],
                                construction="unsupported"))
        plan = B.lower_junctions(g)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0].status, "NO_PATTERN")
        self.assertEqual(plan[0].machine_ops, ())
        self.assertIn("unsupported", plan[0].notes[0])

    def test_arity4_graft_emits_two_grafts(self):
        g = UGPGraph(gauge={"wale_mm": 2.5, "course_mm": 1.6})
        g.add_patch(Patch("web", [Boundary("w1", "rim", 100),
                                  Boundary("w2", "rim", 100)]))
        g.add_patch(Patch("p2", [Boundary("a", "rim", 100),
                                 Boundary("b", "rim", 100)]))
        g.add_patch(Patch("p3", [Boundary("a", "rim", 100),
                                 Boundary("b", "rim", 100)]))
        g.declared_chi = 0
        g.add_junction(Junction("j4", [("web", "w1", "cw"),
                                       ("p2", "a", "ccw"),
                                       ("web", "w2", "cw"),
                                       ("p3", "a", "ccw")],
                                construction="grafted"))
        plan = B.lower_junctions(g)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0].machine_ops, ("GRAFT", "GRAFT"))

    def test_realized_plan_matches_the_realizing_ops_verbs(self):
        # sock heel: knitted_in junction realized by a v2 pick_up op ->
        # the plan's machine verbs must equal that op's reference verbs
        g = build_garment("sock")
        plan = {e.graph_junction: e for e in B.lower_junctions(g)}
        heel = plan["sock_j_heel_v3"]
        self.assertEqual(heel.status, "REALIZED")
        self.assertEqual(heel.machine_ops, ("PICK_UP", "KNIT"))
        self.assertEqual(heel.realized_by, ("sock_foot_pick_up",))

    def test_synthetic_curves_are_honestly_unrealized(self):
        g = build_garment("shirt")
        plan = {e.graph_junction: e for e in B.lower_junctions(g)}
        for jid in ("shirt_j_sleeve_l_v3", "shirt_j_sleeve_r_v3"):
            self.assertEqual(plan[jid].status, "UNREALIZED", jid)
            self.assertEqual(plan[jid].machine_ops, ("PICK_UP", "KNIT"))
            self.assertEqual(plan[jid].realized_by, ())
            self.assertTrue(plan[jid].notes, jid)

    def test_invalid_graph_is_refused_not_planned(self):
        g = build_garment("sock")
        g.declared_chi = 99          # break the v3 closure
        with self.assertRaises(B.BackendNotApplicable):
            B.lower_junctions(g)

    def test_v2_only_graph_plans_nothing(self):
        from ugc.primitives import validate
        self.assertEqual(B.lower_junctions(UGPGraph()), ())

    def test_plan_is_byte_deterministic(self):
        g = build_garment("hoodie")
        a = json.dumps([e.to_dict() for e in B.lower_junctions(g)],
                       sort_keys=True)
        b = json.dumps([e.to_dict() for e in B.lower_junctions(g)],
                       sort_keys=True)
        self.assertEqual(a, b)

    def test_plan_sorted_by_junction_id(self):
        plan = B.lower_junctions(build_garment("hoodie"))
        self.assertEqual([e.graph_junction for e in plan],
                         sorted(e.graph_junction for e in plan))

    def test_v2_lowering_path_untouched(self):
        # additive: the v2 program lowering ignores the v3 layer —
        # same machine_ops, same 1:1 op count as before C4
        res = B.lower(build_garment("shirt"))
        self.assertEqual(len(res.ops), len(build_garment("shirt").ops))
        self.assertEqual(res.machine_ops, ("CAST_ON",) * 3)


if __name__ == "__main__":
    unittest.main()
