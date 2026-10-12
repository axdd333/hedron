#!/usr/bin/env python3
"""Benchmark — benchmark/benchmark.py (t_ce16ab48).

Measures what the U-01 engine actually does across the nine garment
families and the canonical backends, straight from the engine's own
surfaces — never recomputed, never rounded, never guessed:

- graph facts from the live UGPGraph: primitives with their engine
  Boundary descriptors (length_mm in mm; loop counts from the engine's
  own Boundary.loops_for when the graph carries a complete gauge),
  joints with their declared construction (including "unsupported" —
  documented, not hidden, §10), declared open boundaries, and the
  full ValidationResult (ok / fatal / cataloged errors / findings);
- per-backend buildability from ugc.primitives.buildability_report,
  verbatim (per-invariant-class PASS/FAIL/UNVERIFIED + the engine's
  own non-claim note, §9);
- the lowered program from ugc.backend.lower: one LoweredOp dict per
  op, counts by kind, machine verbs by verb, and machine_verdict —
  SIMULATED only when the graph carries a complete gauge (the exact
  condition under which the engine checked loop correspondence),
  else UNSIMULATED (§9: geometric validity never implies knitability);
- refusals: a graph that fails validation is recorded per backend as
  {"lowerable": false, "refusal": {...}} carrying the exact catalog
  error count, codes and message from BackendNotApplicable — a
  datapoint, not a crash and never a partial program.

Gauge scenarios are graphs built with a gauge: benchmark_family (and
run_benchmark) set graph.gauge before any engine call, so every
loop-derived number IS the engine's number for that graph.
"""
import json
import math
import os

from ugc.primitives import buildability_report, RegistryError
from ugc.garments import GARMENT_FAMILIES, build_garment
from ugc.backend import BackendNotApplicable, lower, garment_stats

__all__ = ["BENCHMARK_VERSION", "benchmark_graph", "benchmark_family",
           "run_benchmark", "report_to_json", "write_report"]

BENCHMARK_VERSION = 1

CANONICAL_BACKENDS = ("default_knit", "default_sim")


def _validate_gauge(gauge):
    if gauge is None:
        return None
    if not isinstance(gauge, dict):
        raise ValueError("gauge must be a dict or None, got %r" % (gauge,))
    wale = gauge.get("wale_mm")
    course = gauge.get("course_mm")
    for name, v in (("wale_mm", wale), ("course_mm", course)):
        if not isinstance(v, (int, float)) or isinstance(v, bool) \
                or not math.isfinite(v) or v <= 0:
            raise ValueError("gauge.%s must be a positive finite number, "
                             "got %r" % (name, v))
    return {"wale_mm": float(wale), "course_mm": float(course)}


def _boundary_facts(prim, gauge):
    """Engine Boundary descriptors for one primitive (§4.1).

    loops comes from the engine's own loop conversion (Boundary.loops_for,
    length_mm / gauge wale_mm) — None without a complete gauge, exactly
    as the engine reports it.
    """
    out = []
    for b in prim.boundaries:
        out.append({"boundary": b.boundary, "kind": b.kind,
                    "length_mm": b.length_mm, "loops": b.loops_for(gauge)})
    return out


def _graph_facts(graph):
    """Render + knit view facts, straight from the live graph."""
    gauge = graph.gauge
    primitives = []
    for p in graph:
        primitives.append({
            "id": p.id,
            "kind": p.kind,
            "params": dict(sorted(p.params.items())),
            "origin": list(p.origin),
            "axis": list(p.axis),
            "boundaries": _boundary_facts(p, gauge),
        })
    joints = []
    for j in graph.joints():
        joints.append({
            "id": j.id,
            "joint": j.joint,
            "child": j.child,
            "child_boundary": j.child_boundary,
            "parent": j.parent,
            "parent_boundary": j.parent_boundary,
            "construction": j.construction,
            "anchor": {"feature": j.anchor["feature"],
                       "boundary": j.anchor["boundary"],
                       "point": list(j.anchor["point"])},
            "realized_by": list(j.realized_by or []),
        })
    # validation verdict — the full ValidationResult, canonical order
    from ugc.validation import validate
    vres = validate(graph)
    return {
        "gauge": dict(gauge) if gauge else None,
        "loop_counts_available": bool(gauge) and "wale_mm" in gauge,
        "piece_count": len(primitives),
        "joint_count": len(joints),
        "primitives": primitives,
        "joints": joints,
        "open_boundaries": list(sorted(graph.open_boundaries)),
        "validation": vres.to_dict(),
    }


def _program_facts(result):
    """The lowered program from the LoweringResult itself."""
    stats = garment_stats(result.graph, result)
    return {
        "backend": result.backend,
        "op_count": len(result.ops),
        "machine_op_count": len(result.machine_ops),
        "ops": [lo.to_dict() for lo in result.ops],
        "ops_by_kind": stats["ops_by_kind"],
        "machine_ops_by_verb": stats["machine_ops_by_verb"],
        "open_boundaries": list(result.open_boundaries),
        "machine_verdict": stats["machine_verdict"],
        "notes": list(stats["notes"]),
    }


def benchmark_graph(graph, family=None, backends=CANONICAL_BACKENDS):
    """One graph's full benchmark entry, as the engine sees THIS graph.

    The graph is never mutated; its own gauge (if any) drives loop-derived
    facts. backends must be known backend ids (RegistryError fails fast —
    no guessed backends).
    """
    backends = tuple(backends)
    if not backends:
        raise ValueError("backends must be non-empty")
    entry = {"family": family, "graph": _graph_facts(graph),
             "backends": {}}
    for backend_id in backends:
        be = buildability_report(graph, backend_id)   # RegistryError if unknown
        section = {"buildability": be}
        try:
            result = lower(graph, backend_id)
        except BackendNotApplicable as exc:
            section["lowerable"] = False
            section["refusal"] = {
                "error": "BackendNotApplicable",
                "message": str(exc),
                "error_count": len(exc.result.errors),
                "codes": [e.code for e in exc.result.errors],
            }
        else:
            section["lowerable"] = True
            section["program"] = _program_facts(result)
        entry["backends"][backend_id] = section
    return entry


def benchmark_family(family, backends=CANONICAL_BACKENDS, gauge=None,
                     scale=1.0):
    """One U-01 family's benchmark entry (build + measure).

    gauge (optional) is validated then set on the freshly built graph —
    the engine's own SIMULATED condition — before any engine call.
    """
    gauge = _validate_gauge(gauge)
    if family not in GARMENT_FAMILIES:
        raise ValueError("unknown garment family: %r (known: %s)"
                         % (family, ", ".join(sorted(GARMENT_FAMILIES))))
    graph = build_garment(family, scale)
    if gauge:
        graph.gauge = gauge
    return benchmark_graph(graph, family=family, backends=backends)


def run_benchmark(backends=CANONICAL_BACKENDS, gauge=None):
    """All nine U-01 families, one report."""
    gauge = _validate_gauge(gauge)
    backends = tuple(backends)
    families = {}
    for fam in sorted(GARMENT_FAMILIES):
        families[fam] = benchmark_family(fam, backends=backends,
                                         gauge=gauge)
    # aggregate verdict counts per backend, tied to each family's program
    verdict_counts = {b: {} for b in backends}
    for fam_entry in families.values():
        for b in backends:
            section = fam_entry["backends"][b]
            verdict = (section["program"]["machine_verdict"]
                       if section.get("lowerable") else "REFUSED")
            verdict_counts[b][verdict] = \
                verdict_counts[b].get(verdict, 0) + 1
    return {
        "schema_version": BENCHMARK_VERSION,
        "kind": "ugc-benchmark",
        "backends": list(backends),
        "gauge": dict(gauge) if gauge else None,
        "families": families,
        "machine_verdict_counts": verdict_counts,
    }


def report_to_json(report):
    """Canonical JSON: sorted keys, stable bytes for equal reports."""
    return json.dumps(report, indent=2, sort_keys=True)


def write_report(path, backends=CANONICAL_BACKENDS, gauge=None):
    """Run the benchmark and write its canonical JSON to path (absolute)."""
    blob = report_to_json(run_benchmark(backends=backends, gauge=gauge))
    out = os.path.abspath(path)
    with open(out, "w") as fh:
        fh.write(blob + "\n")
    return out


if __name__ == "__main__":
    import sys
    print(write_report(sys.argv[1] if len(sys.argv) > 1
                       else "benchmark/report.json"))
