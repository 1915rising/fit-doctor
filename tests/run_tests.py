"""Synthetic test suite for Fit Doctor. Run INSIDE Blender:

    blender -b --factory-startup --python tests/run_tests.py

Builds a body sphere (r=1.0) and an outfit sphere (r=1.05) with
planted defects — two missing shape keys, 5 + 3 cross-side weight
contamination, 4 unweighted vertices, 6 vertices pushed inside
the body — and asserts the checker reports each plant with the
exact count. A clean outfit must report all zeros, and the
adjustable thresholds must change the verdicts. Prints PASS/FAIL
lines and a final sentinel:

    FIT_DOCTOR_SYNTHETIC: PASS
"""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fit_doctor import core  # noqa: E402

FAILURES = []

# Planted defect counts — the checker must reproduce these exactly.
PLANT_LEFT_CONTAM = 5     # verts on +X carrying Arm.R weight
PLANT_RIGHT_CONTAM = 3    # verts on -X carrying Arm.L weight
PLANT_UNWEIGHTED = 4
PLANT_CLIPPING = 6


def check(label, condition, detail=""):
    if condition:
        print("PASS: %s" % label)
    else:
        print("FAIL: %s %s" % (label, detail))
        FAILURES.append(label)


def make_sphere(name, radius, key_names):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16,
                                         radius=radius)
    obj = bpy.context.active_object
    obj.name = name
    for key_name in key_names:
        obj.shape_key_add(name=key_name, from_mix=False)
    return obj


def pick(obj, predicate, count):
    out = []
    for v in obj.data.vertices:
        if predicate(v.co):
            out.append(v.index)
            if len(out) == count:
                break
    assert len(out) == count, "only picked %d of %d" % (len(out), count)
    return out


def build_pair():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    body = make_sphere("Body", 1.0, ["Basis", "Smile", "Blink", "Brow"])
    outfit = make_sphere("Outfit", 1.05, ["Basis", "Smile"])

    spine = outfit.vertex_groups.new(name="Spine")
    arm_l = outfit.vertex_groups.new(name="Arm.L")
    arm_r = outfit.vertex_groups.new(name="Arm.R")
    n = len(outfit.data.vertices)
    spine.add(list(range(n)), 1.0, "REPLACE")

    # Plant: cross-side contamination.
    left_verts = pick(outfit, lambda co: co.x > 0.6, PLANT_LEFT_CONTAM)
    arm_r.add(left_verts, 0.4, "REPLACE")
    right_verts = pick(outfit, lambda co: co.x < -0.6, PLANT_RIGHT_CONTAM)
    arm_l.add(right_verts, 0.4, "REPLACE")

    # Plant: unweighted vertices (bottom cap, |x| small).
    bare = pick(outfit, lambda co: abs(co.x) < 0.2 and co.z < -0.6,
                PLANT_UNWEIGHTED)
    for group in (spine, arm_l, arm_r):
        group.remove(bare)

    # Plant: clipping vertices (top cap, pushed to 45% radius).
    sunk = pick(outfit, lambda co: abs(co.x) < 0.2 and co.z > 0.6,
                PLANT_CLIPPING)
    for i in sunk:
        v = outfit.data.vertices[i]
        v.co = v.co * 0.45

    # Clean control outfit: all keys, all weighted, nothing sunk.
    clean = make_sphere("OutfitClean", 1.05,
                        ["Basis", "Smile", "Blink", "Brow"])
    g = clean.vertex_groups.new(name="Spine")
    g.add(list(range(len(clean.data.vertices))), 1.0, "REPLACE")
    return body, outfit, clean


def main():
    body, outfit, clean = build_pair()

    # ---- analyze: planted defects --------------------------------
    r = core.analyze(body, outfit)
    ft = r["follow_through"]
    check("follow-through missing",
          ft["missing"] == ["Blink", "Brow"], "got %s" % ft["missing"])
    c = r["contamination"]
    check("contamination left", c["left"] == PLANT_LEFT_CONTAM,
          "got %d" % c["left"])
    check("contamination right", c["right"] == PLANT_RIGHT_CONTAM,
          "got %d" % c["right"])
    check("contamination total",
          c["total"] == PLANT_LEFT_CONTAM + PLANT_RIGHT_CONTAM,
          "got %d" % c["total"])
    check("contamination per-group",
          c["per_group"] == {"Arm.R": PLANT_LEFT_CONTAM,
                             "Arm.L": PLANT_RIGHT_CONTAM},
          "got %s" % c["per_group"])
    check("unweighted count", r["unweighted"]["count"] == PLANT_UNWEIGHTED,
          "got %d" % r["unweighted"]["count"])
    cl = r["clipping"]
    check("clipping available", cl["available"] is True)
    check("clipping count", cl["count"] == PLANT_CLIPPING,
          "got %d" % cl["count"])
    check("clipping depth sane", 0.3 < cl["max_depth"] < 0.6,
          "got %s" % cl["max_depth"])

    # ---- thresholds actually adjust the verdicts ------------------
    r2 = core.analyze(body, outfit, clip_depth=0.6)
    check("clip_depth threshold", r2["clipping"]["count"] == 0,
          "got %d" % r2["clipping"]["count"])
    r3 = core.analyze(body, outfit, side_margin=2.0)
    check("side_margin threshold", r3["contamination"]["total"] == 0,
          "got %d" % r3["contamination"]["total"])
    r4 = core.analyze(body, outfit, min_weight=0.5)
    check("min_weight threshold", r4["contamination"]["total"] == 0,
          "got %d" % r4["contamination"]["total"])

    # ---- clean control: no false positives ------------------------
    rc = core.analyze(body, clean)
    check("clean follow-through", rc["follow_through"]["missing"] == [],
          "got %s" % rc["follow_through"]["missing"])
    check("clean contamination", rc["contamination"]["total"] == 0,
          "got %d" % rc["contamination"]["total"])
    check("clean unweighted", rc["unweighted"]["count"] == 0,
          "got %d" % rc["unweighted"]["count"])
    check("clean clipping", rc["clipping"]["count"] == 0,
          "got %d" % rc["clipping"]["count"])

    # ---- report plumbing ------------------------------------------
    text = core.write_report_text_block(body, outfit, r)
    check("report text block", "FitCheck_Report" in bpy.data.texts
          and "Fit Doctor report" in text)
    check("report states the caveat", "false" in text.lower()
          and "positives" in text.lower())

    print("FIT_DOCTOR_SYNTHETIC: %s" % ("FAIL" if FAILURES else "PASS"))
    if FAILURES:
        print("FAILURES: %s" % FAILURES)


if __name__ == "__main__":
    main()
