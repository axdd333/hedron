"""Universal Garment Primitive (UGP) — the core representation.

A garment is a graph of parametric solid primitives (tubes, spheres, disks...)
connected by exactly four relation tags: branch, continuation, seam, mount.
All lengths in millimeters, all axes unit-normalized.
"""
import json
import math

__all__ = ["Primitive", "UGPGraph", "VALID_TAGS", "PRIMITIVE_KINDS",
           "DEFAULTS", "CLOSED_KINDS"]

VALID_TAGS = ("branch", "continuation", "seam", "mount")
_PLURAL = {"branch": "branches", "continuation": "continuations",
           "seam": "seams", "mount": "mounts"}
PRIMITIVE_KINDS = ("tube", "sphere", "ellipsoid", "hemisphere", "disk",
                   "rect")
CLOSED_KINDS = ("sphere", "ellipsoid", "hemisphere", "disk", "rect")
DEFAULTS = {
    "tube": {"r1": 10, "r2": 10, "l": 10},
    "sphere": {"r": 10},
    "ellipsoid": {"rx": 10, "ry": 10, "rz": 10},
    "hemisphere": {"r": 10},
    "disk": {"r": 10},
    "rect": {"w": 10, "h": 10},
}


def _norm(v):
    x, y, z = (float(c) for c in v)
    n = math.sqrt(x * x + y * y + z * z)
    if n == 0.0:
        raise ValueError("axis must be a nonzero vector")
    return (x / n, y / n, z / n)


def _vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _vadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


class Primitive:
    """One parametric solid in the garment graph."""

    def __init__(self, id, kind, params, pos, axis=(0, 1, 0)):
        if kind not in PRIMITIVE_KINDS:
            raise ValueError("unknown primitive kind: %r" % (kind,))
        self.id = id
        self.kind = kind
        merged = dict(DEFAULTS[kind])
        merged.update(params or {})
        self.params = merged
        self.origin = (float(pos[0]), float(pos[1]), float(pos[2]))
        self.axis = _norm(axis)
        # edges["branches"|"continuations"|"seams"|"mounts"]
        #   -> list of {"child": id, "pos": [x, y, z]}
        self.edges = {_PLURAL[t]: [] for t in VALID_TAGS}

    # -- transforms --------------------------------------------------------
    @staticmethod
    def rotation_matrix(deg, axis):
        x, y, z = _norm(axis)
        rad = math.radians(deg)
        c, s = math.cos(rad), math.sin(rad)
        C = 1.0 - c
        return [
            [c + x * x * C, x * y * C - z * s, x * z * C + y * s],
            [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
            [z * x * C - y * s, z * y * C + x * s, c + z * z * C],
        ]

    def _basis(self):
        """Orthonormal right-handed local frame (x, y, z); y = self.axis."""
        y_ax = self.axis
        ref = (0.0, 0.0, 1.0) if abs(y_ax[1]) > 0.9 else (0.0, 1.0, 0.0)
        x_ax = _norm(_vcross(y_ax, ref))
        z_ax = _vcross(x_ax, y_ax)
        return x_ax, y_ax, z_ax

    def world_to_local(self, p):
        x_ax, y_ax, z_ax = self._basis()
        d = _vsub((float(p[0]), float(p[1]), float(p[2])), self.origin)
        return (d[0] * x_ax[0] + d[1] * x_ax[1] + d[2] * x_ax[2],
                d[0] * y_ax[0] + d[1] * y_ax[1] + d[2] * y_ax[2],
                d[0] * z_ax[0] + d[1] * z_ax[1] + d[2] * z_ax[2])

    # -- geometry ----------------------------------------------------------
    def metrics(self):
        k, p = self.kind, self.params
        if k == "tube":
            r1, r2, l = p["r1"], p["r2"], p["l"]
            vol = math.pi * l * (r1 * r1 + r1 * r2 + r2 * r2) / 3.0
            slant = math.sqrt(l * l + (r1 - r2) ** 2)
            area = math.pi * (r1 + r2) * slant + math.pi * (r1 * r1 + r2 * r2)
            return {"volume": vol, "surfaceArea": area, "closed": False,
                    "terminus": _vadd(self.origin, _vscale(self.axis, l))}
        if k == "sphere":
            r = p["r"]
            return {"volume": 4.0 / 3.0 * math.pi * r ** 3,
                    "surfaceArea": 4.0 * math.pi * r ** 2, "closed": True}
        if k == "ellipsoid":
            rx, ry, rz = p["rx"], p["ry"], p["rz"]
            vol = 4.0 / 3.0 * math.pi * rx * ry * rz
            # Knud Thomsen approximation
            a, b, c = sorted((rx, ry, rz), reverse=True)
            p_const = 1.6075
            area = 4.0 * math.pi * (
                (a ** p_const * b ** p_const + a ** p_const * c ** p_const
                 + b ** p_const * c ** p_const) / 3.0) ** (1.0 / p_const)
            return {"volume": vol, "surfaceArea": area, "closed": True}
        if k == "hemisphere":
            r = p["r"]
            return {"volume": 2.0 / 3.0 * math.pi * r ** 3,
                    "surfaceArea": 3.0 * math.pi * r ** 2, "closed": True}
        if k == "disk":
            r = p["r"]
            return {"volume": 0.0, "surfaceArea": 2.0 * math.pi * r ** 2,
                    "closed": True}
        if k == "rect":
            w, h = p["w"], p["h"]
            return {"volume": 0.0, "surfaceArea": 2.0 * w * h, "closed": True}
        raise ValueError("unhandled kind %r" % (k,))

    # -- attachment ----------------------------------------------------------
    def _attach(self, child, tag, pos):
        if tag not in VALID_TAGS:
            raise ValueError("unknown attachment tag: %r" % (tag,))
        child.origin = (float(pos[0]), float(pos[1]), float(pos[2]))
        self.edges[_PLURAL[tag]].append({"child": child.id,
                                         "pos": list(child.origin)})
        return {"tag": tag, "parent": self.id, "child": child.id,
                "pos": list(child.origin)}

    def attach_branch(self, child, pos):
        return self._attach(child, "branch", pos)

    def attach_continuation(self, child, pos):
        return self._attach(child, "continuation", pos)

    def attach_seam(self, child, pos):
        return self._attach(child, "seam", pos)

    def attach_mount(self, child, pos):
        return self._attach(child, "mount", pos)

    # -- serialization -------------------------------------------------------
    def to_dict(self):
        return {"id": self.id, "kind": self.kind, "params": self.params,
                "origin": list(self.origin), "axis": list(self.axis),
                "edges": self.edges}

    @classmethod
    def from_dict(cls, d):
        prim = cls(id=d["id"], kind=d["kind"], params=d["params"],
                   pos=d["origin"], axis=d["axis"])
        prim.edges = {_PLURAL[t]: list(d["edges"].get(_PLURAL[t], []))
                      for t in VALID_TAGS}
        return prim


def _vcross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _vscale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


class UGPGraph:
    """Order-ordered collection of primitives; serialization root."""

    def __init__(self, primitives=None):
        self._prims = []
        for p in (primitives or []):
            self.add(p)

    def add(self, prim):
        if any(p.id == prim.id for p in self._prims):
            raise ValueError("duplicate primitive id: %r" % (prim.id,))
        self._prims.append(prim)
        return prim

    def get(self, prim_id):
        for p in self._prims:
            if p.id == prim_id:
                return p
        raise KeyError(prim_id)

    def __len__(self):
        return len(self._prims)

    def __iter__(self):
        return iter(self._prims)

    def to_json(self):
        return json.dumps([p.to_dict() for p in self._prims], indent=2)

    @classmethod
    def from_json(cls, blob):
        data = json.loads(blob) if isinstance(blob, str) else blob
        return cls([Primitive.from_dict(d) for d in data])
