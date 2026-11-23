"""Fit Doctor — outfit fit diagnosis for Blender.

Free and open source (MIT). Diagnoses how an outfit mesh fits a
body mesh: shape-key follow-through, left/right weight
contamination, unweighted vertices, and approximate clipping.
Diagnosis only — it changes nothing on the meshes.

All functionality is also available headless through
``fit_doctor.core`` — see the README.
"""

import bpy
from bpy.props import FloatProperty, PointerProperty
from bpy.types import Operator, Panel, PropertyGroup

from . import core

bl_info = {
    "name": "Fit Doctor",
    "author": "1915rising",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Fit Doctor",
    "description": "Diagnose outfit fit: shape-key follow-through, "
                   "L/R weight contamination, unweighted vertices, "
                   "approximate clipping",
    "category": "Mesh",
}


def _is_mesh(obj):
    return obj is not None and obj.type == "MESH"


class FitDoctorSettings(PropertyGroup):
    body: PointerProperty(
        name="Body",
        type=bpy.types.Object,
        poll=lambda self, obj: _is_mesh(obj),
        description="The body mesh the outfit should fit",
    )
    outfit: PointerProperty(
        name="Outfit",
        type=bpy.types.Object,
        poll=lambda self, obj: _is_mesh(obj),
        description="The outfit mesh to diagnose",
    )
    side_margin: FloatProperty(
        name="Side margin",
        default=core.DEFAULT_SIDE_MARGIN,
        min=0.0,
        description="Vertices with |local X| beyond this count as "
                    "clearly on one side for the contamination check",
    )
    min_weight: FloatProperty(
        name="Min weight",
        default=core.DEFAULT_MIN_WEIGHT,
        min=0.0,
        max=1.0,
        description="Opposite-side weight above this counts as "
                    "contamination",
    )
    clip_depth: FloatProperty(
        name="Clip depth",
        default=core.DEFAULT_CLIP_DEPTH,
        min=0.0,
        description="An outfit vertex must be inside the body by "
                    "more than this to count as clipping",
    )


class FITDOCTOR_OT_check(Operator):
    bl_idname = "fit_doctor.check"
    bl_label = "Run Fit Check"
    bl_description = "Diagnose the outfit against the body and write " \
                     "a FitCheck_Report text block"

    def execute(self, context):
        settings = context.scene.fit_doctor
        body, outfit = settings.body, settings.outfit
        if not _is_mesh(body) or not _is_mesh(outfit):
            self.report({"ERROR"}, "Pick a body mesh and an outfit mesh first")
            return {"CANCELLED"}
        result = core.analyze(
            body, outfit,
            side_margin=settings.side_margin,
            min_weight=settings.min_weight,
            clip_depth=settings.clip_depth,
        )
        core.write_report_text_block(body, outfit, result)
        self.report(
            {"INFO"},
            "Follow-through %d missing, contamination %d, unweighted %d, "
            "clipping %d — full report in text block 'FitCheck_Report'"
            % (len(result["follow_through"]["missing"]),
               result["contamination"]["total"],
               result["unweighted"]["count"],
               result["clipping"]["count"]))
        return {"FINISHED"}


class FITDOCTOR_PT_panel(Panel):
    bl_idname = "FITDOCTOR_PT_panel"
    bl_label = "Fit Doctor"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Fit Doctor"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.fit_doctor
        layout.prop(settings, "body")
        layout.prop(settings, "outfit")
        layout.separator()
        layout.label(text="Thresholds:")
        layout.prop(settings, "side_margin")
        layout.prop(settings, "min_weight")
        layout.prop(settings, "clip_depth")
        layout.separator()
        layout.operator("fit_doctor.check", icon="VIEWZOOM")
        layout.label(text="Diagnosis only — nothing is modified.")


CLASSES = (
    FitDoctorSettings,
    FITDOCTOR_OT_check,
    FITDOCTOR_PT_panel,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.fit_doctor = PointerProperty(type=FitDoctorSettings)


def unregister():
    del bpy.types.Scene.fit_doctor
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
