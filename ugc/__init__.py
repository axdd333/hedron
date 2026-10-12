"""ugc — Unified Garment Primitives (spec-v2 knit graph toolkit).

Public surface:
- graph model: Primitive, Boundary, KnitOp, Joint, UGPGraph (+ errors)
- validation: validate / validate_strict -> ValidationResult
- garments: GARMENT_FAMILIES / build_garment
- backend lowering: lower / lower_all / lower_ops / garment_stats /
  lowered_to_json / lowered_from_json / LoweredOp / LoweringResult /
  BackendNotApplicable
"""
from .primitives import (
    OP_SET_DEFAULT_KNIT,
    PRIMITIVE_KINDS,
    RegistryError,
    Boundary,
    Joint,
    JointError,
    KnitOp,
    OpError,
    Primitive,
    PrimitiveError,
    SchemaError,
    UGPGraph,
)
from .validation import (
    ValidationError,
    ValidationResult,
    validate,
    validate_strict,
)
from .garments import GARMENT_FAMILIES, build_garment
from .backend import (
    BackendError,
    BackendNotApplicable,
    LoweredOp,
    LoweringResult,
    lower,
    lower_all,
    lower_ops,
    lowered_from_json,
    lowered_to_json,
    garment_stats,
)

__all__ = [
    "BackendError",
    "BackendNotApplicable",
    "Boundary",
    "GARMENT_FAMILIES",
    "Joint",
    "JointError",
    "KnitOp",
    "LoweredOp",
    "LoweringResult",
    "OP_SET_DEFAULT_KNIT",
    "PRIMITIVE_KINDS",
    "Primitive",
    "PrimitiveError",
    "RegistryError",
    "SchemaError",
    "UGPGraph",
    "ValidationError",
    "ValidationResult",
    "OpError",
    "build_garment",
    "garment_stats",
    "lower",
    "lower_all",
    "lower_ops",
    "lowered_from_json",
    "lowered_to_json",
    "validate",
    "validate_strict",
]
