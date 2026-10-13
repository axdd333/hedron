"""Backend lowering — ugc.backend (t_c97edfbf).

Turns a geometrically valid UGPGraph (per ugc.validation, t_ff7ea486) into
an ordered program of machine-shaped ops for a declared backend (§8).

Contract
--------
1. validation gates lowering: lower() runs ugc.validation.validate() first
   and refuses the whole graph on any cataloged error — BackendNotApplicable
   carries the result, so callers get the specific (code, kind) failures.
   Fatal §7 graphs (degenerate/schema) are refused the same way, before any
   op is emitted. A graph that never validates never lowers: no silent
   partial programs, no fabricated geometry.
2. program order: ops are emitted keyed by the primitive they act on
   (producing op -> its produced prim; consuming op -> its consumed rim's
   owner), primitives walked breadth-first from the root; ties inside one
   primitive resolve by graph op id. The program therefore depends only on
   graph content, never insertion order, and byte-identical re-lowerings
   are the determinism contract.
3. reference machine verbs (NOT a vendor format — a neutral reference):
     cast_on          -> ("CAST_ON",)
     bind_off         -> ("BIND_OFF",)
     short_row_close  -> ("SHORT_ROW_CLOSE",)
     graft            -> ("GRAFT",)
     selvedge_seam    -> ("SELVEDGE_SEAM",)
     pick_up          -> ("PICK_UP", "KNIT")   # form new fabric, knit on
   lower_ops(backend_id) exposes the verb set for the backend's op set
   (the two canonical defaults share the reference set; custom backends
   with other op ids must lower themselves — this module ships reference
   lowering for OP_SET_DEFAULT_KNIT only, and says so rather than guessing).
4. JSON export: versioned envelope (version 1), sorted keys, sorted
   open_boundaries; roundtrips through lowered_from_json.

This module is a reference lowering for planning/simulation. It does not
drive hardware, and geometric validity never implies knitability (§9).
"""
import copy
import json
import re
from collections import deque

import ugc.primitives as P
import ugc.validation as V
from ugc.garments import GARMENT_FAMILIES, build_garment

__all__ = ["BackendError", "BackendNotApplicable", "LoweredOp",
           "LoweringResult", "lower", "lower_all", "lower_ops",
           "lowered_to_json", "lowered_from_json", "garment_stats",
           "LOWERING_VERSION"]


LOWERING_VERSION = 1


class BackendError(P._BaseError, ValueError):
    """Base class for backend lowering failures."""


class BackendNotApplicable(BackendError, ValueError):
    """The graph does not satisfy the spec-v2 invariants; lowering refused.

    .result is the ugc.validation.ValidationResult whose .errors carry the
    specific (code, kind, ids, message[, expected, actual]) catalog tuples.
    """

    def __init__(self, result, message=None):
        self.result = result
        n = len(result.errors)
        detail = "; ".join("%s %s" % (e.code, e.kind)
                           for e in result.errors[:5])
        if n > 5:
            detail += "; ... (%d total)" % n
        super(BackendError, self).__init__(
            message or ("graph is not buildable: %d cataloged error(s): %s"
                        % (n, detail)))


# ---------------------------------------------------------------------------
# reference machine verbs
# ---------------------------------------------------------------------------
_REFERENCE_VERBS = {
    "cast_on": ("CAST_ON",),
    "bind_off": ("BIND_OFF",),
    "short_row_close": ("SHORT_ROW_CLOSE",),
    "graft": ("GRAFT",),
    "selvedge_seam": ("SELVEDGE_SEAM",),
    "pick_up": ("PICK_UP", "KNIT"),
}


def lower_ops(backend_id):
    """Reference machine verb set for a declared backend (§8).

    Returns the verbs the reference lowering emits for the backend's op
    set, sorted. Both canonical default backends declare the default_knit
    op set, so both map to the same reference verb set. Unknown op sets
    (custom backends) raise RegistryError here — not a guessed mapping.
    """
    be = P.get_backend(backend_id)          # RegistryError if unknown
    op_set = set(P.OP_SET_DEFAULT_KNIT)
    verbs = []
    for op in be["checks"] and sorted(op_set):
        verbs.extend(_REFERENCE_VERBS[op])
    return tuple(sorted(verbs))


# ---------------------------------------------------------------------------
# program order
# ---------------------------------------------------------------------------
def _actor_id(g, op, owner_of):
    """The primitive this op instance acts on (§4.3 semantics).

    cast_on: the rim it starts (its produced prim). pick_up: the child
    rim it forms (its produced prim). graft/selvedge_seam: the joint's
    child opening (the closure that finishes the child piece or mates it
    to the parent). bind_off/short_row_close: the rim they seal.
    """
    if op.produces:
        return op.produces.partition("/")[0]
    if op.op in ("graft", "selvedge_seam"):
        for j in g.joints():
            if op.id in j.realized_by:
                return j.child
    return op.consumes[0].partition("/")[0]


def _joint_of_op(g, op_id):
    """The joint realized by this op instance, if any (§5.4)."""
    for j in g.joints():
        if op_id in j.realized_by:
            return j
    return None


def _order_prims(g):
    """Primitive ids in breadth-first order from the single root (the
    validator guarantees exactly one root), insertion-order independent."""
    children, parent_count = V._roots_and_children(g.joints())
    prim_ids = sorted(p.id for p in g)
    root = sorted(pid for pid in prim_ids
                  if pid not in parent_count)
    # validator guarantees len(root) == 1 here
    seen = set()
    order = []
    q = deque(sorted(root))
    while q:
        pid = q.popleft()
        if pid in seen:
            continue
        seen.add(pid)
        order.append(pid)
        for child in sorted(children.get(pid, ())):
            if child not in seen:
                q.append(child)
    return order


def _joint_records(g):
    """joint id -> {child, child_boundary, parent, construction} (§5)."""
    out = {}
    for j in g.joints():
        out[j.id] = {"child": j.child,
                     "child_boundary": j.child_boundary,
                     "parent": j.parent,
                     "construction": j.construction}
    return out


# ---------------------------------------------------------------------------
# lowering
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# junction-graph lowering (spec v3, t_8ea48971 C4)
# ---------------------------------------------------------------------------
class JunctionPlanEntry(object):
    """One junction's knit plan: the op pattern its construction demands,
    the v2 ops that realize it (verbatim curve refs), or an honest
    refusal. Bound to its source junction id for traceability."""

    __slots__ = ("graph_junction", "status", "construction", "machine_ops",
                 "realized_by", "notes")

    def __init__(self, graph_junction, status, construction, machine_ops,
                 realized_by, notes=()):
        self.graph_junction = str(graph_junction)
        self.status = status              # REALIZED | UNREALIZED | NO_PATTERN
        self.construction = construction
        self.machine_ops = tuple(machine_ops)
        self.realized_by = tuple(realized_by)
        if isinstance(notes, str):
            notes = (notes,)              # a lone string is one note
        self.notes = tuple(notes)

    def to_dict(self):
        return {"graph_junction": self.graph_junction,
                "status": self.status,
                "construction": self.construction,
                "machine_ops": list(self.machine_ops),
                "realized_by": list(self.realized_by),
                "notes": list(self.notes)}

    def __eq__(self, other):
        if not isinstance(other, JunctionPlanEntry):
            return NotImplemented
        return self.to_dict() == other.to_dict()

    def __ne__(self, other):
        eq = self.__eq__(other)
        return eq if eq is NotImplemented else not eq

    def __repr__(self):  # pragma: no cover
        return "JunctionPlanEntry(%r, %s)" % (self.graph_junction,
                                              self.status)


# construction -> machine verb pattern per identified pair (v3 §4;
# verbs are the reference set of _REFERENCE_VERBS)
_JUNCTION_PATTERNS = {
    "knitted_in": ("PICK_UP", "KNIT"),
    "grafted": ("GRAFT",),
    "selvedge_seam": ("SELVEDGE_SEAM",),
}


def _op_refs(op):
    """Every primitive/boundary curve ref this op instance touches."""
    refs = set(op.consumes)
    if op.produces:
        refs.add(op.produces)
    return refs


def lower_junctions(graph, backend="default_knit"):
    """Lower the graph's junction layer to a per-junction knit plan.

    Runs the full validation catalog first (v2 + the four v3 classes);
    an invalid graph raises BackendNotApplicable — never planned. Each
    junction gets exactly one JunctionPlanEntry, sorted by junction id:
      REALIZED    the v2 op program already realizes the identification
                  verbatim (member curve refs named by ops); machine_ops
                  match the realizing op's reference verbs.
      UNREALIZED  a pattern exists for the construction but no v2 op
                  names the junction's synthetic curves (armholes, leg
                  tops, re-id'd necks); the advised pattern is emitted
                  with a note — the plan says the gap, never guesses it.
      NO_PATTERN  construction "unsupported": documented refusal, like
                  v2 §10 fingers.
    v2-only graphs (no patches/junctions) plan empty. Additive: the v2
    program lowering (lower()) is untouched.
    """
    if not isinstance(graph, P.UGPGraph):
        raise TypeError("lower_junctions() expects a UGPGraph, got %s"
                        % type(graph).__name__)
    P.get_backend(backend)                   # RegistryError if unknown
    if not graph.patches() and not graph.junctions():
        return ()                            # bare v2 graph: nothing to plan
    result = V.validate(graph)
    if not result.ok:
        raise BackendNotApplicable(result)

    plan = []
    for j in graph.junctions():
        if j.construction == "unsupported":
            plan.append(JunctionPlanEntry(
                j.id, "NO_PATTERN", j.construction, (), (),
                ("construction %r has no op pattern in v3 — documented "
                 "refusal (DESIGN.md §10 convention)" % (j.construction,))))
            continue
        pattern = _JUNCTION_PATTERNS[j.construction]
        # a pair is realized when some v2 op touches both member refs by
        # their exact names (consume+produce, e.g. pick_up consumes the
        # parent rim and produces the child rim)
        realized_by = set()
        for i in range(0, j.arity, 2):
            a_ref = "%s/%s" % (j.members[i][0], j.members[i][1])
            b_ref = "%s/%s" % (j.members[i + 1][0], j.members[i + 1][1])
            for op in graph.ops:
                refs = _op_refs(op)
                if a_ref in refs and b_ref in refs:
                    realized_by.add(op.id)
        # the pattern applies per identified pair (arity 4 -> two runs)
        machine_ops = pattern * (j.arity // 2)
        if realized_by:
            plan.append(JunctionPlanEntry(
                j.id, "REALIZED", j.construction, machine_ops,
                sorted(realized_by)))
        else:
            plan.append(JunctionPlanEntry(
                j.id, "UNREALIZED", j.construction, machine_ops, (),
                ("no v2 op names junction %r's member curves; the %s "
                 "pattern is advised, the v2 program does not realize it"
                 % (j.id, j.construction))))
    plan.sort(key=lambda e: e.graph_junction)
    return tuple(plan)


class LoweredOp(object):
    """One lowered op instance: a machine-shaped step bound to its
    source graph op id (for traceability back to the UGP graph)."""

    __slots__ = ("graph_op", "op", "machine_ops", "consumes", "produces",
                 "joint")

    def __init__(self, graph_op, op, machine_ops, consumes, produces,
                 joint=None):
        self.graph_op = str(graph_op)
        self.op = op
        self.machine_ops = tuple(machine_ops)
        self.consumes = tuple(consumes)
        self.produces = produces
        self.joint = joint

    def to_dict(self):
        d = {"graph_op": self.graph_op,
             "op": self.op,
             "machine_ops": list(self.machine_ops),
             "consumes": list(self.consumes)}
        if self.produces is not None:
            d["produces"] = self.produces
        if self.joint is not None:
            d["joint"] = dict(self.joint)
        return d

    def __eq__(self, other):
        if not isinstance(other, LoweredOp):
            return NotImplemented
        return self.to_dict() == other.to_dict()

    def __ne__(self, other):
        eq = self.__eq__(other)
        return eq if eq is NotImplemented else not eq

    def __repr__(self):  # pragma: no cover
        return "LoweredOp(%r -> %s)" % (self.graph_op,
                                        "+".join(self.machine_ops))


class LoweringResult(object):
    """lower() outcome: the ordered program plus the evidence it rests on."""

    def __init__(self, graph, backend, ops, machine_ops, report, notes):
        self.graph = graph
        self.backend = backend
        self.ops = tuple(ops)
        self.machine_ops = tuple(machine_ops)
        self.report = report
        self.notes = tuple(notes)
        self.open_boundaries = tuple(sorted(graph.open_boundaries))

    @property
    def geometric_validity(self):
        return self.report["geometric_validity"]

    @property
    def stats(self):
        return garment_stats(self.graph, self)

    def to_dict(self):
        return {"backend": self.backend,
                "machine_ops": list(self.machine_ops),
                "ops": [lo.to_dict() for lo in self.ops],
                "open_boundaries": list(self.open_boundaries),
                "notes": list(self.notes),
                "per_class": dict(self.report["per_class"]),
                "geometric_validity": self.report["geometric_validity"],
                "stats": self.stats}

    def __eq__(self, other):
        if isinstance(other, LoweringResult):
            return self.to_dict() == other.to_dict()
        if isinstance(other, dict):
            return self.to_dict() == other
        return NotImplemented

    def __ne__(self, other):
        eq = self.__eq__(other)
        return eq if eq is NotImplemented else not eq


def lower(graph, backend="default_knit"):
    """Lower a UGPGraph to an ordered machine-op program.

    Runs the full ugc.validation catalog first; any error (including
    fatal §7 degeneracy/schema short-circuits) raises BackendNotApplicable
    carrying the ValidationResult. Never lowers a partial or invalid
    program; never mutates the graph.
    """
    if not isinstance(graph, P.UGPGraph):
        raise TypeError("lower() expects a UGPGraph, got %s"
                        % type(graph).__name__)
    P.get_backend(backend)                   # RegistryError if unknown
    result = V.validate(graph)
    if not result.ok:
        raise BackendNotApplicable(result)

    order = _order_prims(graph)
    joints = _joint_records(graph)
    lowered = []
    for pid in order:
        for op in sorted(graph.ops, key=lambda o: (o.op != "cast_on", o.id)):
            if _actor_id(graph, op, None) != pid:
                continue
            jid = None
            if op.op != "cast_on":
                j = _joint_of_op(graph, op.id)
                if j is not None:
                    jid = j.id
            lowered.append(LoweredOp(
                graph_op=op.id,
                op=op.op,
                machine_ops=_REFERENCE_VERBS[op.op],
                consumes=tuple(op.consumes),
                produces=op.produces,
                joint=joints[jid] if jid is not None else None))
    machine_ops = []
    for lo in lowered:
        machine_ops.extend(lo.machine_ops)

    # honesty note: the engine cannot check loop correspondence without a
    # gauge; lowering surfaces that fact rather than guessing loop counts.
    notes = []
    if not graph.gauge or "wale_mm" not in graph.gauge:
        notes.append("I-LOOP UNVERIFIED: no gauge on graph — loop "
                     "correspondence was not checked")

    report = P.buildability_report(graph, backend)
    return LoweringResult(graph, report["backend"], lowered, machine_ops,
                          report, notes)


# ---------------------------------------------------------------------------
# statistical judgment ledger (§8.1 — "in plain english")
# ---------------------------------------------------------------------------
def garment_stats(graph, result):
    """Counts and the machine verdict for a lowered program.

    Every count ties to the lowered program itself (never recomputed by
    feel): sum(ops_by_kind.values()) == len(result.ops) and
    sum(machine_ops_by_verb.values()) == len(result.machine_ops).

    machine_verdict is "SIMULATED" only when the graph carries a complete
    gauge (both wale_mm and course_mm) — the condition under which the
    engine actually checked loop correspondence (I-LOOP). A partial gauge
    is not a simulation. Extra human context rides in "notes".
    """
    ops_by_kind = {}
    machine_by_verb = {}
    for lo in result.ops:
        ops_by_kind[lo.op] = ops_by_kind.get(lo.op, 0) + 1
        for verb in lo.machine_ops:
            machine_by_verb[verb] = machine_by_verb.get(verb, 0) + 1
    gauge = getattr(graph, "gauge", None)
    wale = course = None
    if isinstance(gauge, dict):
        wale = gauge.get("wale_mm")
        course = gauge.get("course_mm")
    complete = wale is not None and course is not None
    pieces = sum(1 for _ in graph)
    joint_count = sum(1 for _ in graph.joints())
    gauge_out = None
    if complete:
        gauge_out = {"wale_mm": wale, "course_mm": course}
    return {
        "piece_count": pieces,
        "joint_count": joint_count,
        "ops_by_kind": ops_by_kind,
        "machine_ops_by_verb": machine_by_verb,
        "open_boundaries": list(result.open_boundaries),
        "gauge": gauge_out,
        "machine_verdict": "SIMULATED" if complete else "UNSIMULATED",
        "notes": list(result.notes),
    }


# ---------------------------------------------------------------------------
# batch + serialization
# ---------------------------------------------------------------------------
def lower_all(backend="default_knit"):
    """Lower every U-01 garment family; insertion-order independent."""
    return {family: lower(build_garment(family, 1.0), backend)
            for family in sorted(GARMENT_FAMILIES)}


def lowered_to_json(result):
    """Canonical JSON: versioned envelope, sorted keys, stable bytes for
    equal lowerings."""
    envelope = {"version": LOWERING_VERSION}
    envelope.update(result.to_dict())
    return json.dumps(envelope, indent=2, sort_keys=True)


def lowered_from_json(blob):
    """Parse a lowering envelope; returns the payload dict (no envelope
    version key), equality-compatible with LoweringResult.to_dict()."""
    data = json.loads(blob if isinstance(blob, str) else blob)
    if not isinstance(data, dict):
        raise ValueError("lowering envelope must be a JSON object")
    if data.get("version") != LOWERING_VERSION:
        raise ValueError("unsupported lowering version: %r"
                         % (data.get("version"),))
    payload = dict(data)
    payload.pop("version", None)
    return payload
