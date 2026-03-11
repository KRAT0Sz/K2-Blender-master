"""
K2 Blender Addon - UI Panel definitions.
Separated from core logic for easier maintenance and modification.
"""

import bpy


# ============================================================================
# UI Panels
# ============================================================================

class K2_PT_ExportPanel(bpy.types.Panel):
    """Top section: Export header + options + buttons"""
    bl_label = "Export"
    bl_idname = "K2_PT_ExportPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'K2'

    def draw(self, context):
        layout = self.layout
        settings = context.scene.k2_export_settings

        # ---- Header with logo ----
        header = layout.row()
        col_text = header.column()
        col_text.label(text="S2 Games")
        col_text.label(text="Model Exporter")
        col_text.label(text="Version 1")
        icon_id = get_logo_icon()
        if icon_id:
            col_logo = header.column()
            col_logo.template_icon(icon_value=icon_id, scale=5.0)

        layout.separator()

        # ---- Export Mode box (radio buttons like 3ds Max) ----
        box = layout.box()
        box.label(text="Export Mode")
        col = box.column(align=True)
        col.prop(settings, "export_mode", expand=True)

        layout.separator()

        # ---- Export Options box ----
        box = layout.box()
        box.label(text="Export Options")
        col = box.column(align=True)
        col.prop(settings, "force_static")
        col.prop(settings, "remove_hierarchy")
        col.prop(settings, "copy_textures")
        col.prop(settings, "export_geometry")
        col.prop(settings, "export_model_def")
        col.prop(settings, "export_materials")
        col.prop(settings, "export_animation")

        box.separator()

        # ---- Export Buttons (side by side like 3ds Max) ----
        row = box.row(align=True)
        row.operator("export_mesh.k2", text="Export")
        row.operator("export_clip.k2", text="Clip")

        layout.separator()

        # ---- Frame range (visible when Animation is on) ----
        if settings.export_animation:
            row_fr = layout.row(align=True)
            row_fr.prop(settings, "frame_start")
            row_fr.prop(settings, "frame_end")
            layout.separator()

        layout.separator()

        # ---- Bottom buttons (Scene Info + Close) ----
        row = layout.row(align=True)
        row.operator("k2.scene_info", text="Scene Info")
        row.operator("wm.quit_blender", text="Close", icon='X')


class K2_PT_ImportPanel(bpy.types.Panel):
    """Import section — kept separate from the original Export-only tool"""
    bl_label = "Import"
    bl_idname = "K2_PT_ImportPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'K2'

    def draw(self, context):
        layout = self.layout
        settings = context.scene.k2_import_settings

        row = layout.row(align=True)
        row.operator("import_mesh.k2", text="Mesh")
        row.operator("import_clip.k2", text="Clip")

        layout.prop(settings, "flip_uv")

        box = layout.box()
        box.label(text="Textures", icon='TEXTURE')
        col = box.column(align=True)
        col.prop(settings, "tex_color")
        col.prop(settings, "tex_color2")
        col.prop(settings, "tex_color3")
        col.prop(settings, "tex_normal")
        col.prop(settings, "tex_mrao")
        col.prop(settings, "tex_emissive")
        box.separator()
        box.operator("k2.import_textures", text="Import Textures", icon='IMPORT')


class K2_PT_ArmaturePanel(bpy.types.Panel):
    """Armature display tools — bone names, colors, display type"""
    bl_label = "Armature"
    bl_idname = "K2_PT_ArmaturePanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'K2'

    @classmethod
    def poll(cls, context):
        return any(o.type == 'ARMATURE' for o in bpy.data.objects)

    def draw(self, context):
        layout = self.layout
        arms = get_armature_objects()
        if not arms:
            return

        arm = arms[0].data
        show_names = arm.show_names

        box = layout.box()
        box.label(text="Bone Names")
        row = box.row(align=True)
        icon = 'HIDE_OFF' if show_names else 'HIDE_ON'
        row.operator("k2.toggle_bone_names", text="Names ON" if show_names else "Names OFF", icon=icon)

        box = layout.box()
        box.label(text="Bone Display")
        row = box.row(align=True)
        row.operator("k2.fix_bone_display", text="Fix Colors", icon='COLORSET_09_VEC')
        row.operator("k2.reset_bone_display", text="Reset", icon='LOOP_BACK')

        row = box.row(align=True)
        row.operator("k2.cycle_bone_display", text=f"Style: {arm.display_type}", icon='BONE_DATA')

        box.separator()
        box.prop(arm, "show_axes", text="Show Bone Axes")
        box.prop(arm, "relation_line_position", text="Relation Lines")


class K2_PT_MeshInfoPanel(bpy.types.Panel):
    """Bottom section: Mesh Info — mesh type, options, materials"""
    bl_label = "Mesh Info"
    bl_idname = "K2_PT_MeshInfoPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'K2'

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        msh = obj.data
        ms = obj.k2_mesh_settings

        # ---- Mesh box ----
        box = layout.box()
        box.label(text="Mesh")
        box.prop(obj, "name", text="")

        col = box.column(align=True)
        col.prop(ms, "exclude_normals")
        col.prop(ms, "roof")

        box.separator()

        col = box.column(align=True)
        col.prop(ms, "mesh_type", expand=True)

        layout.separator()

        # ---- Material box ----
        box = layout.box()
        box.label(text="Material")
        if msh.materials:
            for mat in msh.materials:
                if mat:
                    box.prop(mat, "name", text="", icon='MATERIAL')
                else:
                    box.label(text="(empty slot)", icon='ERROR')
        else:
            box.label(text="No materials assigned")


# ============================================================================
# Helper functions
# ============================================================================

def get_armature_objects():
    """Get all armature objects in the scene."""
    return [o for o in bpy.data.objects if o.type == 'ARMATURE']


def get_logo_icon():
    """Get custom logo icon ID for UI display."""
    from . import preview_collections
    pcoll = preview_collections.get("k2_icons")
    if pcoll and "logo" in pcoll:
        return pcoll["logo"].icon_id
    return 0


# ============================================================================
# Registration
# ============================================================================

_panel_classes = (
    K2_PT_ExportPanel,
    K2_PT_ImportPanel,
    K2_PT_ArmaturePanel,
    K2_PT_MeshInfoPanel,
)


def register_ui(register_func):
    """Register UI panels. Call from main __init__.py register()."""
    for cls in _panel_classes:
        register_func(cls)


def unregister_ui(unregister_func):
    """Unregister UI panels. Call from main __init__.py unregister()."""
    for cls in reversed(_panel_classes):
        unregister_func(cls)
