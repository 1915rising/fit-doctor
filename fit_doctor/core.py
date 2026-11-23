"""Core logic for Fit Doctor.

Everything here takes two Blender mesh objects — a body and an
outfit — and works through the plain Python API, so the whole tool
can be driven headless:

    import fit_doctor.core as fd
    report = fd.analyze(body_obj, outfit_obj)
    print(fd.format_report(body_obj, outfit_obj, report))

Checks performed by analyze() — diagnosis only, nothing is fixed:

  1. Shape-key follow-through: body shape keys (excluding the
     reference key) that the outfit does not have. An outfit missing
     a key cannot follow the body when that key is driven.
  2. Left/right weight contamination: outfit vertices clearly on
     one side of the outfit's local X axis carrying weight for
     opposite-side vertex groups (.L/.R, _L/_R, " L"/" R" and
     Left/Right naming are recognised). Assumes +X is the left
     side in the outfit's local space — if your model's local axes
     disagree, the two side counts swap meaning.
  3. Unweighted vertices: outfit vertices whose total vertex-group
     weight is zero. They will not follow the armature at all.
  4. Approximate clipping: outfit vertices estimated to be inside
     the body, from the nearest body surface point and its face
     normal (world space). This is an approximation — it can
     produce false positives where surfaces touch or cross at
     grazing angles, and it assumes the body's normals point
     outward. Confirm visually; the count is a triage number,
     not a verdict.
"""

import re

import bpy
import numpy as np
from mathutils.bvhtree import BVHTree

# Defaults — the panel exposes the same three settings.
DEFAULT_SIDE_MARGIN = 0.01    # |x| beyond this counts as "clearly on a side"
DEFAULT_MIN_WEIGHT = 0.05     # opposite-side weight above this is contamination
DEFAULT_CLIP_DEPTH = 0.001    # vertex must be inside by more than this

_WEIGHT_EPS = 1e-6
_SAMPLE_LIMIT = 10


# ---------------------------------------------------------------- helpers

def _shape_key_names(obj):
    """Shape key names excluding the reference key (index 0)."""
    if obj is None or obj.type != "MESH" or not obj.data.shape_keys:
        return []
    return [kb.name for kb in obj.data.shape_keys.key_blocks][1:]


def group_side(name):
    """'L', 'R' or None for a vertex-group / bone name.

    Recognises .L/.R, _L/_R, ' L'/' R', trailing Left/Right and
    leading Left/Right. A trailing Blender duplicate suffix
    ('.001') is stripped first.
    """
    n = re.sub(r"\.\d{3}$", "", name)
    for suffix, side in ((".L", "L"), (".R", "R"),
                         ("_L", "L"), ("_R", "R"),
                         (" L", "L"), (" R", "R")):
        if n.endswith(suffix) and len(n) > len(suffix):
            return side
    if n.endswith("Left"):
        return "L"
    if n.endswith("Right"):
        return "R"
    if n.startswith("Left"):
        return "L"
    if n.startswith("Right"):
        return "R"
    return None


def _require_mesh(obj, role):
    if obj is None or getattr(obj, "type", None) != "MESH":
        raise ValueError("%s object must be a mesh, got %r"
                         % (role, getattr(obj, "name", obj)))


# ---------------------------------------------------------------- checks

def _check_follow_through(body, outfit):
    body_keys = _shape_key_names(body)
    outfit_keys = _shape_key_names(outfit)
    outfit_set = set(outfit_keys)
    missing = [k for k in body_keys if k not in outfit_set]
    return {
        "body_keys": body_keys,
        "outfit_keys": outfit_keys,
        "missing": missing,
    }


def _vertex_weights(outfit):
    """Yield (index, local_co, [(group_index, weight), ...])."""
    for v in outfit.data.vertices:
        yield v.index, v.co, [(g.group, g.weight) for g in v.groups]


def _check_contamination(outfit, side_margin, min_weight):
    side_by_group = {g.index: group_side(g.name)
                     for g in outfit.vertex_groups}
    left = 0          # verts on +X (left) carrying right-side weight
    right = 0         # verts on -X (right) carrying left-side weight
    per_group = {}
    sample = []
    for index, co, weights in _vertex_weights(outfit):
        if co.x > side_margin:
            side, opposite = "L", "R"
        elif co.x < -side_margin:
            side, opposite = "R", "L"
        else:
            continue
        bad_groups = [outfit.vertex_groups[gi].name
                      for gi, w in weights
                      if w > min_weight and side_by_group.get(gi) == opposite]
        if bad_groups:
            if side == "L":
                left += 1
            else:
                right += 1
            for name in bad_groups:
                per_group[name] = per_group.get(name, 0) + 1
            if len(sample) < _SAMPLE_LIMIT:
                sample.append(index)
    return {
        "left": left,
        "right": right,
        "total": left + right,
        "per_group": per_group,
        "sample": sample,
    }


def _check_unweighted(outfit):
    count = 0
    sample = []
    for index, _co, weights in _vertex_weights(outfit):
        if sum(w for _gi, w in weights) <= _WEIGHT_EPS:
            count += 1
            if len(sample) < _SAMPLE_LIMIT:
                sample.append(index)
    return {"count": count, "sample": sample}


def _body_bvh_world(body):
    """BVH of the body's evaluated mesh in world space, or None."""
    if len(body.data.polygons) == 0:
        return None
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = body.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    try:
        mw = body.matrix_world
        verts = [tuple(mw @ v.co) for v in mesh.vertices]
        mesh.calc_loop_triangles()
        tris = [tuple(t.vertices) for t in mesh.loop_triangles]
    finally:
        eval_obj.to_mesh_clear()
    if not tris:
        return None
    return BVHTree.FromPolygons(verts, tris, all_triangles=True)


def _check_clipping(body, outfit, clip_depth):
    bvh = _body_bvh_world(body)
    if bvh is None:
        return {"available": False, "count": 0, "max_depth": None,
                "mean_depth": None, "sample": []}
    mw = outfit.matrix_world
    count = 0
    depths = []
    worst = []  # (depth, index)
    for v in outfit.data.vertices:
        wco = mw @ v.co
        loc, normal, _index, _dist = bvh.find_nearest(wco)
        if loc is None:
            continue
        signed = float((wco - loc).dot(normal))
        if signed < -clip_depth:
            count += 1
            depths.append(-signed)
            worst.append((-signed, v.index))
    worst.sort(reverse=True)
    return {
        "available": True,
        "count": count,
        "max_depth": max(depths) if depths else 0.0,
        "mean_depth": float(np.mean(depths)) if depths else 0.0,
        "sample": [i for _d, i in worst[:_SAMPLE_LIMIT]],
    }


# ---------------------------------------------------------------- analyze

def analyze(body, outfit, side_margin=DEFAULT_SIDE_MARGIN,
            min_weight=DEFAULT_MIN_WEIGHT, clip_depth=DEFAULT_CLIP_DEPTH):
    """Run every check on a (body, outfit) pair. Returns a plain dict."""
    _require_mesh(body, "body")
    _require_mesh(outfit, "outfit")
    return {
        "body": body.name,
        "outfit": outfit.name,
        "body_vertices": len(body.data.vertices),
        "outfit_vertices": len(outfit.data.vertices),
        "settings": {
            "side_margin": side_margin,
            "min_weight": min_weight,
            "clip_depth": clip_depth,
        },
        "follow_through": _check_follow_through(body, outfit),
        "contamination": _check_contamination(outfit, side_margin, min_weight),
        "unweighted": _check_unweighted(outfit),
        "clipping": _check_clipping(body, outfit, clip_depth),
    }


def format_report(body, outfit, result=None):
    """Human-readable report (also written to a Blender text block)."""
    if result is None:
        result = analyze(body, outfit)
    s = result["settings"]
    lines = []
    lines.append("Fit Doctor report — outfit '%s' on body '%s'"
                 % (result["outfit"], result["body"]))
    lines.append("Outfit: %d vertices; body: %d vertices"
                 % (result["outfit_vertices"], result["body_vertices"]))
    lines.append("Settings: side margin %g, min weight %g, clip depth %g"
                 % (s["side_margin"], s["min_weight"], s["clip_depth"]))
    lines.append("")

    ft = result["follow_through"]
    lines.append("SHAPE-KEY FOLLOW-THROUGH: %d missing"
                 % len(ft["missing"]))
    if ft["missing"]:
        for name in ft["missing"]:
            lines.append("  [MISSING] %s" % name)
    elif not ft["body_keys"]:
        lines.append("  (body has no shape keys to follow)")
    else:
        lines.append("  all %d body keys present on the outfit"
                     % len(ft["body_keys"]))
    lines.append("")

    c = result["contamination"]
    lines.append("LEFT/RIGHT WEIGHT CONTAMINATION: %d vertices" % c["total"])
    lines.append("  on +X (left) carrying right-side weight: %d" % c["left"])
    lines.append("  on -X (right) carrying left-side weight: %d" % c["right"])
    if c["per_group"]:
        lines.append("  opposite-side groups involved:")
        for name, n in sorted(c["per_group"].items(),
                              key=lambda kv: -kv[1]):
            lines.append("    %s: %d vertices" % (name, n))
    lines.append("")

    u = result["unweighted"]
    lines.append("UNWEIGHTED VERTICES: %d" % u["count"])
    if u["sample"]:
        lines.append("  first indices: %s"
                     % ", ".join(str(i) for i in u["sample"]))
    lines.append("")

    cl = result["clipping"]
    if cl["available"]:
        lines.append("CLIPPING (approximate): %d outfit vertices inside "
                     "the body" % cl["count"])
        if cl["count"]:
            lines.append("  max depth %g, mean depth %g"
                         % (cl["max_depth"], cl["mean_depth"]))
            lines.append("  deepest indices: %s"
                         % ", ".join(str(i) for i in cl["sample"]))
        lines.append("  NOTE: nearest-surface + normal estimate — false "
                     "positives are possible where")
        lines.append("  surfaces touch or cross at grazing angles. "
                     "Confirm visually.")
    else:
        lines.append("CLIPPING: skipped (body has no faces to test against)")
    lines.append("")

    lines.append("SUMMARY: follow-through %d missing, contamination %d, "
                 "unweighted %d, clipping %d"
                 % (len(ft["missing"]), c["total"], u["count"],
                    cl["count"]))
    lines.append("Diagnosis only — Fit Doctor changes nothing on the meshes.")
    return "\n".join(lines)


def write_report_text_block(body, outfit, result=None):
    """Write the report into a Blender text block and return the text."""
    text = format_report(body, outfit, result)
    block = bpy.data.texts.get("FitCheck_Report")
    if block is None:
        block = bpy.data.texts.new("FitCheck_Report")
    block.clear()
    block.write(text)
    print(text)
    return text
