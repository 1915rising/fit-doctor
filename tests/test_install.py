"""Install test: install the built ZIP like a user would, enable it,
and drive its operator. Run INSIDE Blender:

    blender -b --factory-startup --python tests/test_install.py -- <zip>

Prints FIT_DOCTOR_INSTALL: PASS on success.
"""

import sys

import bpy

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print("PASS: %s" % label)
    else:
        print("FAIL: %s %s" % (label, detail))
        FAILURES.append(label)


def make_sphere(name, radius, key_names):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8,
                                         radius=radius)
    obj = bpy.context.active_object
    obj.name = name
    for key_name in key_names:
        obj.shape_key_add(name=key_name, from_mix=False)
    return obj


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    zip_path = argv[0]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.preferences.addon_install(filepath=zip_path, overwrite=True)
    bpy.ops.preferences.addon_enable(module="fit_doctor")
    check("add-on enabled", "fit_doctor" in bpy.context.preferences.addons)

    body = make_sphere("Body", 1.0, ["Basis", "Smile", "Blink"])
    outfit = make_sphere("Outfit", 1.05, ["Basis", "Smile"])
    g = outfit.vertex_groups.new(name="Spine")
    g.add(list(range(len(outfit.data.vertices))), 1.0, "REPLACE")

    settings = bpy.context.scene.fit_doctor
    settings.body = body
    settings.outfit = outfit

    check("check operator runs",
          bpy.ops.fit_doctor.check() == {"FINISHED"})
    check("report text block written", "FitCheck_Report" in bpy.data.texts)
    text = bpy.data.texts["FitCheck_Report"].as_string()
    check("report names the missing key", "Blink" in text)

    print("FIT_DOCTOR_INSTALL: %s" % ("FAIL" if FAILURES else "PASS"))


if __name__ == "__main__":
    main()
