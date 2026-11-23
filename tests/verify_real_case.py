"""Real-case run: a female avatar with Christmas dress. Run INSIDE Blender:

    blender -b --factory-startup --python tests/verify_real_case.py -- \
        <copy-of-graft.blend> <report-out.txt>

The original file's path can be supplied via the FIT_DOCTOR_ORIGINAL
environment variable; when set, this script refuses to open that
file — pass a copy. It joins the body meshes (BodySkin +
BodyBlackSuit + LegsSkin, the surfaces the gown covers) on the
copy and runs Fit Doctor on GenGown, the AI-generated gown
grafted onto the avatar's body. That graft shipped with known
defects (a floating glove and visible clipping), so this is a
field test, not a planted-defect test: there are no count
assertions, the numbers are recorded as found.

Prints a REAL_CASE_RESULT JSON line with the headline counts.
"""

import json
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fit_doctor import core  # noqa: E402

ORIGINAL = os.environ.get("FIT_DOCTOR_ORIGINAL", "")
BODY_PARTS = ("BodySkin", "BodyBlackSuit", "LegsSkin")
OUTFIT = "GenGown"


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    blend_path, out_path = argv[0], argv[1]
    if ORIGINAL and os.path.abspath(blend_path) == os.path.abspath(ORIGINAL):
        raise SystemExit("refusing to open the original file — pass a copy")

    bpy.ops.wm.open_mainfile(filepath=blend_path)

    for name in BODY_PARTS + (OUTFIT,):
        if name not in bpy.data.objects:
            raise SystemExit("expected object %r not in file" % name)

    bpy.ops.object.select_all(action="DESELECT")
    for name in BODY_PARTS:
        bpy.data.objects[name].select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.objects[BODY_PARTS[0]]
    bpy.ops.object.join()
    body = bpy.context.active_object
    body.name = "BodyJoined"
    outfit = bpy.data.objects[OUTFIT]

    result = core.analyze(body, outfit)
    text = core.format_report(body, outfit, result)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(text)
    print("REAL_CASE_RESULT " + json.dumps({
        "body_vertices": result["body_vertices"],
        "outfit_vertices": result["outfit_vertices"],
        "follow_through_missing": len(result["follow_through"]["missing"]),
        "contamination_left": result["contamination"]["left"],
        "contamination_right": result["contamination"]["right"],
        "contamination_total": result["contamination"]["total"],
        "unweighted": result["unweighted"]["count"],
        "clipping": result["clipping"]["count"],
        "clipping_max_depth": result["clipping"]["max_depth"],
    }))


if __name__ == "__main__":
    main()
