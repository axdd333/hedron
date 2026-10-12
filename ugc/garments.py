"""Garment generators — the six U-01 families from one primitive vocabulary.

Each family is a pure function (family, scale) -> UGPGraph with mm geometry.
Nine names, six builders: shorts shares trousers, dress shares skirt.
"""
import math

from ugc.primitives import Primitive, UGPGraph

__all__ = ["build_garment", "GARMENT_FAMILIES"]

GARMENT_FAMILIES = ("hat", "sock", "glove", "skirt", "dress", "trousers",
                    "shorts", "shirt", "hoodie")

_LINEAR_KEYS = ("r1", "r2", "l", "r", "rx", "ry", "rz", "w", "h")


def _scaled_params(params, scale):
    return {k: (v * scale if k in _LINEAR_KEYS else v)
            for k, v in params.items()}


def _scaled_pos(pos, scale):
    return tuple(c * scale for c in pos)


def _prim(pid, kind, params, pos, axis=(0, 1, 0), scale=1.0):
    return Primitive(id=pid, kind=kind,
                     params=_scaled_params(params, scale),
                     pos=_scaled_pos(pos, scale), axis=axis)


def _build_hat(scale):
    g = UGPGraph()
    crown = _prim("hat_crown", "tube", {"r1": 95, "r2": 90, "l": 110},
                  (0, 0, 0), scale=scale)
    dome = _prim("hat_dome", "hemisphere", {"r": 90}, (0, 110, 0),
                 scale=scale)
    crown.attach_seam(dome, pos=dome.origin)
    g.add(crown)
    g.add(dome)
    return g


def _build_sock(scale):
    g = UGPGraph()
    leg = _prim("sock_leg", "tube", {"r1": 55, "r2": 50, "l": 250},
                (0, 0, 0), scale=scale)
    heel = _prim("sock_heel", "hemisphere", {"r": 55}, (0, 0, 0),
                 scale=scale)
    foot = _prim("sock_foot", "tube", {"r1": 50, "r2": 45, "l": 180},
                 (0, 0, 0), axis=(1, 0, 0), scale=scale)
    toe = _prim("sock_toe", "hemisphere", {"r": 45}, (180, 0, 0),
                scale=scale)
    leg.attach_continuation(heel, pos=heel.origin)
    heel.attach_continuation(foot, pos=foot.origin)
    foot.attach_continuation(toe, pos=toe.origin)
    for p in (leg, heel, foot, toe):
        g.add(p)
    return g


def _build_glove(scale):
    # Known-open: fingers are closed disks mounted on the palm sphere —
    # geometrically sealed, mechanically unfinished (see DESIGN.md).
    g = UGPGraph()
    palm = _prim("glove_palm", "sphere", {"r": 60}, (0, 0, 0), scale=scale)
    finger_specs = [
        ("finger_1", (0, 58, 0), 10),
        ("finger_2", (0, 56, 14), 10),
        ("finger_3", (0, 56, -14), 10),
        ("finger_4", (0, 50, 26), 9),
        ("thumb", (-40, 30, 0), 12),
    ]
    for pid, pos, r in finger_specs:
        disk = _prim(pid, "disk", {"r": r}, pos, scale=scale)
        palm.attach_branch(disk, pos=disk.origin)
        g.add(disk)
    g.add(palm)
    return g


def _build_skirt(scale):
    g = UGPGraph()
    body = _prim("skirt_body", "tube", {"r1": 90, "r2": 160, "l": 450},
                 (0, 0, 0), axis=(0, -1, 0), scale=scale)
    g.add(body)
    return g


def _build_dress(scale):
    g = UGPGraph()
    torso = _prim("dress_torso", "tube", {"r1": 100, "r2": 95, "l": 350},
                  (0, 0, 0), scale=scale)
    skirt = _prim("dress_skirt", "tube", {"r1": 100, "r2": 170, "l": 450},
                  (0, 0, 0), axis=(0, -1, 0), scale=scale)
    torso.attach_continuation(skirt, pos=skirt.origin)
    g.add(torso)
    g.add(skirt)
    return g


def _build_trousers(scale, leg_length=450):
    g = UGPGraph()
    hips = _prim("trousers_hips", "tube", {"r1": 110, "r2": 100, "l": 150},
                 (0, 0, 0), scale=scale)
    for side, dx in (("l", -55.0), ("r", 55.0)):
        leg = _prim("trousers_leg_%s" % side, "tube",
                    {"r1": 58, "r2": 50, "l": leg_length},
                    (dx, 0, 0), axis=(0, -1, 0), scale=scale)
        hips.attach_branch(leg, pos=leg.origin)
        g.add(leg)
    g.add(hips)
    return g


def _build_shirt(scale, hood=False):
    g = UGPGraph()
    torso = _prim("shirt_torso", "tube", {"r1": 110, "r2": 120, "l": 300},
                  (0, 0, 0), scale=scale)
    for side, dx, ax in (("l", -1.0, (-1, 0, 0)), ("r", 1.0, (1, 0, 0))):
        sleeve = _prim("shirt_sleeve_%s" % side, "tube",
                       {"r1": 55, "r2": 45, "l": 250},
                       (dx * 120, 260, 0), axis=ax, scale=scale)
        torso.attach_branch(sleeve, pos=sleeve.origin)
        g.add(sleeve)
    if hood:
        hood_p = _prim("hood", "hemisphere", {"r": 90}, (0, 300, -40),
                       scale=scale)
        torso.attach_seam(hood_p, pos=hood_p.origin)
        g.add(hood_p)
    g.add(torso)
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
    if not isinstance(scale, (int, float)) or isinstance(scale, bool) \
            or scale <= 0:
        raise ValueError("scale must be a positive number, got %r" % (scale,))
    return _BUILDERS[family](float(scale))
