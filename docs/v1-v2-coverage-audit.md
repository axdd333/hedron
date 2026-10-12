# v1 → v2 coverage audit — ugc.primitives

Every behavior covered by the OLD `tests/test_primitives.py` (v1, 14 tests)
and its API surface is mapped below to its spec-v2 equivalent (with an
updated test) or documented as a removal. No coverage was silently dropped.

## Old API surface

| v1 name | Status | v2 home |
|---|---|---|
| `VALID_TAGS` ("branch", "continuation", "seam", "mount") | REMOVED | v1 tags mixed topology/construction/placement. Replaced by the closed sets `JOINT_TYPES` x `CONSTRUCTIONS` x `ANCHOR_FEATURES` (DESIGN.md §5.1-5.3). The v1 tags survive only as the §5.1 migration mapping. |
| `Primitive.attach_branch / attach_continuation / attach_seam / attach_mount` | REMOVED | v2 has no auto-classification (§5.1): joints are explicit `Joint` objects with declared type/construction/anchor, stored in graph-level plural collections. |
| `Primitive.edges` dict of four plural lists | REMOVED | `UGPGraph.rim_joints / surface_branches / terminus_continuations` (§11 kept: plural edge collections — moved from per-primitive to per-graph where they belong). |
| `Primitive.pos` param | RENAMED | `Primitive.origin` — matches graph JSON §12. |
| `VALID_TAGS`-keyed attachment snapping (child origin forced to parent pos) | REMOVED | v2 anchors are data (`anchor.point`), checked mechanically by I-ANCHOR against the declared parent feature (§5.3, §6). No silent snapping: an off-feature anchor is a hard error, never auto-corrected. |
| `"closed"` key in `metrics()` (v1 called closed-forms "sealed") | REMOVED from metrics | v2 separates the two views: render "closed" becomes `Primitive.closure == "integral"` (§4.1 knit reading); sealing is an op disposition (I-SEAL), never a metrics flag. |
| `metrics()` volume/surfaceArea/terminus | KEPT | `Primitive.metrics()` — render-view geometry only (updated test `TestRenderMetrics`). |
| axis normalization on ingest, zero-axis reject | KEPT | `_norm` at construction + I-AXIS post-mutation sweep (`TestPrimitiveDefaultsAndNormalization`, `TestAxisInvariant`). |
| mm units, defaults of 10 | KEPT | `DEFAULTS`, `TestPrimitiveDefaultsAndNormalization.test_tube_defaults_all_params_ten_mm`. |
| `rotation_matrix`, `world_to_local` | KEPT | unchanged (`TestTransforms`). |
| `UGPGraph` add/get/len/iter, duplicate-primitive-id reject | KEPT | duplicate id now a `SchemaError` (§7.4); `TestSchemaInvariant`. |
| `to_json`/`from_json` roundtrip | KEPT | v2 §12 shape: version 2, gauge, tolerances, open_boundaries, primitives, joints{plural}, ops (`TestGraphJsonSchema`). |
| `Primitive.metrics()["closed"]` garment tests (test_garments.py) | DELEGATED | test_garments.py still on the old API — owned by t_9c8cd55b; tracked red in this task's runs until that card lands. |

## Old test → new test mapping (tests/test_primitives.py)

| old v1 test (14) | v2 test |
|---|---|
| test_tube_defaults_all_params_ten_mm | same name, `origin=` |
| test_default_orientation_is_unit_y | same name |
| test_axis_is_normalized_on_ingest | same name |
| test_zero_axis_is_rejected | same name + `test_nonfinite_axis_is_rejected` |
| test_world_to_local_translates_and_inverse_rotates | same name |
| test_rotation_matrix_maps_z_to_x_for_90deg_y | same name |
| test_branch_child_origin_snaps_to_parent_origin | REMOVED — snapping contradicts §5.3; replaced by I-ANCHOR tests (`TestAnchorInvariant`): off-feature anchors are FAILs, not auto-corrections |
| test_continuation_child_snaps_to_parent_terminus | same removal; replaced by `test_terminus_anchor_on_parent_terminus_passes` (anchor data + I-ANCHOR) |
| test_unknown_attachment_tag_is_rejected | replaced by `Joint` enum rejects + `TestJointLegality` matrix tests |
| test_seam_seals_open_rim_with_closed_cap | REMOVED — v2's central correction: a seam does not seal; the v1 test encoded the disk-closes-it fallacy. Replaced by `TestSealInvariant.test_disk_cap_closes_nothing` and `test_disk_cap_with_parent_side_bind_off_passes` |
| test_mount_lays_closed_child_on_closed_parent_surface | replaced by `TestBranchOrientInvariant` + `TestAnchorInvariant` surface tests (`surface_branch` + `unsupported` per §5.4) |
| test_sphere_metrics_closed_form | `TestRenderMetrics.test_sphere_metrics_closed_form` (metrics without the "closed" flag) + `test_sphere_ellipsoid_have_no_boundaries` (closure: "integral") |
| test_tapered_tube_metrics | same name, terminus via metrics |
| test_json_roundtrip_preserves_everything | `TestGraphJsonSchema.test_roundtrip_preserves_joints_ops_gauge` (v2 graph shape) |

## Documented removals (nothing silent)

1. **`attach_*` methods and per-primitive `edges`** — v1 API; joint type is
   declared data in v2 (§5.1). A mechanical `grep` for `attach_` in
   ugc/ returns nothing after this task.
2. **Attachment snapping** (child origin forced to the joint pos) — anchors
   are checked (I-ANCHOR), not enforced.
3. **`metrics()["closed"]`** — replaced by `closure` ("integral") on the
   knit view; sealing is op-disposition (§4.2).
4. **`VALID_TAGS` / the four tags as fields** — replaced by the three-way
   taxonomy; the §5.1 mapping is documentation-only.
