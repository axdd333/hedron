"""Garment generators — the six U-01 families on the spec-v2 IR.

Each family is a pure function (family, scale) -> UGPGraph with mm
geometry, declared spec-v2 joints (type x construction x anchor), and an
explicit default_knit op program satisfying I-SEAL. Nine names, six
builders: shorts shares trousers, dress shares skirt.

Construction choices follow DESIGN.md §5.4 and real whole-garment practice:
- knitted_in where whole-garment machines form the child from the parent's
  live rim (sleeve-side pick-ups, legs off the hips, skirt off the torso,
  sock foot off the leg across a knitted heel turn);
- grafted for separately-shaped closures mated to a live rim (dome tops,
  toe caps, hood);
- short_row_close for shaped terminations knit within one piece;
- unsupported (documented, not hidden) where v2's op set cannot claim the
  realization — glove fingers need mid-fabric pick_up_path (§10).

Graph assembly order (UGPGraph contract): primitives first, then op
instances, then joints (add_joint resolves both endpoints immediately).
"""
import math

from ugc.primitives import (Primitive, UGPGraph, KnitOp, Joint,
                            PrimitiveError)

__all__ = ["build_garment", "GARMENT_FAMILIES"]

GARMENT_FAMILIES = ("hat", "sock", "glove", "skirt", "dress", "trousers",
                    "shorts", "shirt", "hoodie")

_LINEAR_KEYS = ("r1", "r2", "l", "r", "rx", "ry", "rz", "w", "h")

# world-frame +Y is the body's vertical: garments hang downward (-Y) from
# the waist/shoulder; upward (+Y) flows are head/limb directions.


def _scaled_params(params, scale):
    return {k: (v * scale if k in _LINEAR_KEYS else v)
            for k, v in params.items()}


def _scaled_pos(pos, scale):
    return tuple(c * scale for c in pos)


def _prim(pid, kind, params, pos, axis=(0, 1, 0), scale=1.0):
    return Primitive(id=pid, kind=kind,
                     params=_scaled_params(params, scale),
                     origin=_scaled_pos(pos, scale), axis=axis)


def _root_cast_on(graph, rim_prim, op_id):
    """Start the root piece's fabric at rim_start (§4.2 fabric_start)."""
    graph.add_op(KnitOp(id=op_id, op="cast_on",
                        consumes=[], produces="%s/rim_start" % rim_prim.id))


def _rim_joint(gid, child, parent, construction, anchor_point,
               realized_by=None):
    """Parent rim mates child opening over the full perimeter (§5.4)."""
    return Joint(id=gid, joint="rim_joint", child=child.id,
                 child_boundary="rim_start", parent=parent.id,
                 parent_boundary="rim_end", construction=construction,
                 anchor={"feature": "rim",
                         "boundary": "rim_end",
                         "point": anchor_point},
                 realized_by=realized_by)


def _continuation(gid, child, parent, construction, anchor_point,
                  realized_by=None):
    """Child claims the parent's terminus fabric flow (§5.1)."""
    return Joint(id=gid, joint="terminus_continuation", child=child.id,
                 child_boundary="rim_start", parent=parent.id,
                 parent_boundary="rim_end", construction=construction,
                 anchor={"feature": "terminus",
                         "boundary": "rim_end",
                         "point": anchor_point},
                 realized_by=realized_by)


def _branch(gid, child, parent, anchor_point, child_boundary="rim_start"):
    """surface_branch: unsupported-only in v2 (§5.4, §10).

    child_boundary is the child's opening on the parent surface: rim_start
    for tubes (the fabric the pick_up produces), rim for render-only caps.
    """
    return Joint(id=gid, joint="surface_branch", child=child.id,
                 child_boundary=child_boundary, parent=parent.id,
                 parent_boundary=None, construction="unsupported",
                 anchor={"feature": "surface", "boundary": None,
                         "point": anchor_point})


# --- builders ----------------------------------------------------------------


def _build_hat(scale):
    g = UGPGraph()
    crown = _prim("hat_crown", "tube", {"r1": 95, "r2": 90, "l": 110},
                  (0, 0, 0), scale=scale)
    dome = _prim("hat_dome", "hemisphere", {"r": 90}, (0, 110, 0),
                 scale=scale)
    g.add(crown)
    g.add(dome)
    _root_cast_on(g, crown, "hat_cast_on")
    # the cast-on edge is this graph's only fabric start; sealing the
    # crown's lower edge keeps rim_start in exactly one terminal state.
    g.add_op(KnitOp(id="hat_crown_bind_off", op="bind_off",
                    consumes=["hat_crown/rim_start"]))
    g.add_op(KnitOp(id="hat_dome_graft", op="graft",
                    consumes=["hat_crown/rim_end", "hat_dome/rim"]))
    g.add_joint(_rim_joint("hat_j_dome", dome, crown, "grafted", dome.origin,
                           realized_by=["hat_dome_graft"]))
    return g


def _build_sock(scale):
    g = UGPGraph()
    leg = _prim("sock_leg", "tube", {"r1": 55, "r2": 50, "l": 250},
                (0, 0, 0), scale=scale)
    foot = _prim("sock_foot", "tube", {"r1": 50, "r2": 45, "l": 180},
                 (0, 0, 0), axis=(1, 0, 0), scale=scale)
    toe = _prim("sock_toe", "hemisphere", {"r": 45}, (180, 0, 0),
                scale=scale)
    g.add(leg)
    g.add(foot)
    g.add(toe)
    _root_cast_on(g, leg, "sock_cast_on")
    g.add_op(KnitOp(id="sock_cuff_bind_off", op="bind_off",
                    consumes=["sock_leg/rim_start"]))
    # heel turn: fabric continues through the terminus and comes back
    # horizontal — a 90° knitted-in turn (§5.1), the parent card's
    # d48fd0d decision.
    g.add_op(KnitOp(id="sock_foot_pick_up", op="pick_up",
                    consumes=["sock_leg/rim_end"],
                    produces="sock_foot/rim_start"))
    g.add_joint(_continuation("sock_j_heel", foot, leg, "knitted_in",
                              leg.metrics()["terminus"],
                              realized_by=["sock_foot_pick_up"]))
    g.add_op(KnitOp(id="sock_toe_graft", op="graft",
                    consumes=["sock_foot/rim_end", "sock_toe/rim"]))
    g.add_joint(_continuation("sock_j_toe", toe, foot, "grafted",
                              foot.metrics()["terminus"],
                              realized_by=["sock_toe_graft"]))
    return g


def _build_glove(scale):
    # Known-open per DESIGN.md §10: v2 expresses the finger joints
    # (surface_branch on the palm surface) but cannot claim their knit
    # realization — mid-fabric pick-up needs pick_up_path, reserved and
    # not in the v2 op set. Fingers stay render-only disks with inert
    # rims and construction "unsupported"; documented, not hidden.
    g = UGPGraph()
    palm = _prim("glove_palm", "sphere", {"r": 60}, (0, 0, 0), scale=scale)
    finger_specs = [
        ("finger_1", (0, 58, 0), 10),
        ("finger_2", (0, 56, 14), 10),
        ("finger_3", (0, 56, -14), 10),
        ("finger_4", (0, 50, 26), 9),
        ("thumb", (-40, 30, 0), 12),
    ]
    g.add(palm)
    for pid, pos, r in finger_specs:
        g.add(_prim(pid, "disk", {"r": r}, pos, scale=scale))
        g.add_joint(_branch("glove_j_%s" % pid, g.get(pid), palm,
                            _scaled_pos(pos, scale), child_boundary="rim"))
    _root_cast_on(g, palm, "glove_cast_on")
    g.add_op(KnitOp(id="glove_wrist_bind_off", op="bind_off",
                    consumes=["glove_palm/rim_start"]))
    return g


def _build_skirt(scale):
    g = UGPGraph()
    body = _prim("skirt_body", "tube", {"r1": 90, "r2": 160, "l": 450},
                 (0, 0, 0), axis=(0, -1, 0), scale=scale)
    g.add(body)
    _root_cast_on(g, body, "skirt_cast_on")
    # waistband edge and hem stay open by design (§4.2 declared_open)
    g.open_boundaries = ["skirt_body/rim_start", "skirt_body/rim_end"]
    return g


def _build_dress(scale):
    g = UGPGraph()
    torso = _prim("dress_torso", "tube", {"r1": 100, "r2": 95, "l": 350},
                  (0, 0, 0), scale=scale)
    skirt = _prim("dress_skirt", "tube", {"r1": 100, "r2": 170, "l": 450},
                  (0, 0, 0), axis=(0, -1, 0), scale=scale)
    g.add(torso)
    g.add(skirt)
    _root_cast_on(g, torso, "dress_cast_on")
    g.add_op(KnitOp(id="dress_neckline_bind_off", op="bind_off",
                    consumes=["dress_torso/rim_start"]))
    g.add_op(KnitOp(id="dress_skirt_pick_up", op="pick_up",
                    consumes=["dress_torso/rim_end"],
                    produces="dress_skirt/rim_start"))
    g.add_joint(_continuation("dress_j_skirt", skirt, torso, "knitted_in",
                              torso.metrics()["terminus"],
                              realized_by=["dress_skirt_pick_up"]))
    g.open_boundaries = ["dress_skirt/rim_end"]
    return g


def _build_trousers(scale, leg_length=450):
    g = UGPGraph()
    hips = _prim("trousers_hips", "tube", {"r1": 110, "r2": 100, "l": 150},
                 (0, 0, 0), scale=scale)
    g.add(hips)
    for side, dx in (("l", -55.0), ("r", 55.0)):
        g.add(_prim("trousers_leg_%s" % side, "tube",
                    {"r1": 58, "r2": 50, "l": leg_length},
                    (dx, 0, 0), axis=(0, -1, 0), scale=scale))
    _root_cast_on(g, hips, "trousers_cast_on")
    g.add_op(KnitOp(id="trousers_waist_bind_off", op="bind_off",
                    consumes=["trousers_hips/rim_start"]))
    for side, dx in (("l", -55.0), ("r", 55.0)):
        # §10 note: real trousers split into two legs from one knitting
        # front (a mid-fabric branch) — surface_branch cannot claim that
        # realization in v2, so the branch is honest: unsupported.
        # Each leg's fabric starts at the hip rim it faces via pick_up.
        leg = g.get("trousers_leg_%s" % side)
        g.add_op(KnitOp(id="trousers_leg_%s_pick_up" % side, op="pick_up",
                        consumes=["trousers_hips/rim_end"],
                        produces="trousers_leg_%s/rim_start" % side))
        g.add_joint(_branch("trousers_j_leg_%s" % side, leg, hips,
                            (dx * scale, 0.0, 0.0)))
    return g


def _build_shirt(scale, hood=False):
    g = UGPGraph()
    torso = _prim("shirt_torso", "tube", {"r1": 110, "r2": 120, "l": 300},
                  (0, 0, 0), scale=scale)
    g.add(torso)
    for side, dx, ax in (("l", -1.0, (-1, 0, 0)), ("r", 1.0, (1, 0, 0))):
        g.add(_prim("shirt_sleeve_%s" % side, "tube",
                    {"r1": 55, "r2": 45, "l": 250},
                    (dx * 120, 260, 0), axis=ax, scale=scale))
    if hood:
        g.add(_prim("hood", "hemisphere", {"r": 90}, (0, 300, -40),
                    scale=scale))
    _root_cast_on(g, torso, "shirt_cast_on")
    g.add_op(KnitOp(id="shirt_neckline_bind_off", op="bind_off",
                    consumes=["shirt_torso/rim_start"]))
    for side, dx in (("l", -1.0), ("r", 1.0)):
        # shoulder armhole is a mid-fabric branch: unsupported in v2
        # (§10). Fabric for each sleeve starts at the armhole via pick_up
        # from the torso's live terminus.
        sleeve = g.get("shirt_sleeve_%s" % side)
        g.add_op(KnitOp(id="shirt_sleeve_%s_pick_up" % side, op="pick_up",
                        consumes=["shirt_torso/rim_end"],
                        produces="shirt_sleeve_%s/rim_start" % side))
        g.add_joint(_branch("shirt_j_sleeve_%s" % side, sleeve, torso,
                            (dx * 120 * scale, 260 * scale, 0.0)))
    if hood:
        hood_p = g.get("hood")
        # hood dome grafted onto the neck opening
        g.add_op(KnitOp(id="hood_graft", op="graft",
                        consumes=["shirt_torso/rim_end", "hood/rim"]))
        g.add_joint(_rim_joint("shirt_j_hood", hood_p, torso, "grafted",
                               hood_p.origin, realized_by=["hood_graft"]))
    else:
        # no hood: the torso's own terminus is a raw hem — declared open
        g.open_boundaries = ["shirt_torso/rim_end"]
    return g


_BUILDERS = {
    "hat": lambda s: _build_hat(s),
    "sock": lambda s: _build_sock(s),
    "glove": lambda s: _build_glove(s),
    "skirt": lambda s: _build_skirt(s),
    "dress": lambda s: _build_dress(s),
    "trousers": lambda s: _build_trousers(s),
    "shorts": lambda s: _build_trousers(s, leg_length=150),
    "shirt": lambda s: _build_shirt(s),
    "hoodie": lambda s: _build_shirt(s, hood=True),
}


def build_garment(family, scale=1.0):
    if family not in _BUILDERS:
        raise ValueError("unknown garment family: %r (known: %s)"
                         % (family, ", ".join(GARMENT_FAMILIES)))
    if (not isinstance(scale, (int, float)) or isinstance(scale, bool)
            or not math.isfinite(scale) or scale <= 0):
        raise ValueError("scale must be a positive finite number, got %r"
                         % (scale,))
    return _BUILDERS[family](float(scale))
