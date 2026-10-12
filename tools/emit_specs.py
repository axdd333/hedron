"""Emit the viewer's per-family spec bundles to out/<family>.json.

Committed tool (t_bb76d3b7): regenerates the data the viewer serves, so
the page can be refreshed after any library change with one command.
Every field comes from the library's own surfaces — build_garment,
validate, buildability_report, lower, garment_stats, Boundary.loops_for —
no recomputation, no renames, no fabricated fields.

Per family the bundle carries:
  family, scale, emitted_at_version
  graph            : UGPGraph.to_dict() (the spec JSON itself)
  validation       : ValidationResult.to_dict() (findings + errors)
  buildability     : per-backend report for every registered backend
  plan             : lowered_to_json(lower(...)) envelope (refused graphs
                     carry plan=null + refusal evidence instead)
  boundaries       : per-primitive rim/inert lengths in mm, with loop
                     counts ONLY when a complete gauge is attached
                     (Boundary.loops_for) — null otherwise
  out_path         : where this bundle was written

Usage: python3 tools/emit_specs.py [--out DIR] [--scale S]
                 [--gauge WALE_MM COURSE_MM]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ugc.backend import LOWERING_VERSION, lower, lowered_to_json
from ugc.garments import GARMENT_FAMILIES, build_garment
from ugc.primitives import (UGPGraph, backend_ids, buildability_report)
from ugc.validation import validate


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _gauge_is_complete(gauge):
    return bool(gauge) and "wale_mm" in gauge and "course_mm" in gauge


def _boundary_facts(graph):
    """Per-primitive boundary lengths (mm) + loop counts under the graph's
    gauge when complete. Rim loops come from Boundary.loops_for; inert
    boundaries carry the engine's own constant loops = 0.0 (§4.1)."""
    gauge = graph.gauge if _gauge_is_complete(graph.gauge) else None
    out = {}
    for prim in graph:
        rows = []
        for b in prim.boundaries:
            if b.kind == "inert":
                loops = b.loops            # engine constant 0.0
            elif gauge is not None:
                loops = b.loops_for(gauge)
            else:
                loops = None
            rows.append({"boundary": b.boundary, "kind": b.kind,
                         "length_mm": b.length_mm, "loops": loops})
        out[prim.id] = rows
    return out


def build_bundle(family, scale=1.0, gauge=None):
    graph = build_garment(family, scale)
    if gauge is not None:
        graph.gauge = dict(gauge)
    result = validate(graph)
    bundle = {
        "family": family,
        "scale": scale,
        "emitted_at_version": LOWERING_VERSION,
        "graph": graph.to_dict(),
        "validation": result.to_dict(),
        "buildability": {},
        "plan": None,
        "refusal": None,
        "boundaries": _boundary_facts(graph),
        "out_path": None,
    }
    for backend in backend_ids():
        bundle["buildability"][backend] = buildability_report(graph, backend)
    if result.ok:
        lowered = lower(graph, backend="default_knit")
        envelope = json.loads(lowered_to_json(lowered))
        envelope["graph"] = graph.to_dict()
        envelope["family"] = family
        bundle["plan"] = envelope
    else:
        bundle["refusal"] = {
            "note": "lowering refused; the graph failed the invariant "
                    "catalog (geometric validity never implies "
                    "knitability, and here it fails geometry first)",
            "errors": result.to_dict()["errors"],
        }
    return bundle


def write_bundles(outdir, scale=1.0, gauge=None):
    os.makedirs(outdir, exist_ok=True)
    written = []
    for family in sorted(GARMENT_FAMILIES):
        bundle = build_bundle(family, scale, gauge=gauge)
        path = os.path.join(outdir, "%s.json" % family)
        blob = json.dumps(bundle, indent=2, sort_keys=True) + "\n"
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(blob)
        bundle["out_path"] = path
        written.append(path)
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="emit viewer spec bundles to out/<family>.json")
    ap.add_argument("--out", default=os.path.join(_repo_root(), "out"),
                    help="output directory (default: <repo>/out)")
    ap.add_argument("--scale", default="1.0",
                    help="positive finite scale factor (default 1.0)")
    ap.add_argument("--gauge", nargs=2, type=float,
                    metavar=("WALE_MM", "COURSE_MM"), default=None,
                    help="attach a complete gauge so loop counts and "
                         "machine_verdict=SIMULATED are emitted")
    args = ap.parse_args(argv)
    try:
        scale = float(args.scale)
        if not scale > 0:
            raise ValueError(scale)
    except ValueError:
        ap.error("--scale must be a positive finite number, got %r"
                 % (args.scale,))
    gauge = None
    if args.gauge:
        wale, course = args.gauge
        if wale <= 0 or course <= 0:
            ap.error("gauge values must be positive mm")
        gauge = {"wale_mm": wale, "course_mm": course}
    written = write_bundles(args.out, scale, gauge=gauge)
    print("emitted %d bundles to %s" % (len(written), args.out))
    for path in written:
        print("  %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
