"""
K2 Model/Animation Import-Export addon for Blender.
Supports K2 engine formats used by Savage 2 and Heroes of Newerth.
"""

import bpy
from bpy.props import StringProperty, BoolProperty, IntProperty, PointerProperty

bl_info = {
    "name": "K2 Model/Animation Import-Export",
    "author": "Anton Romanov",
    "version": (1, 0, 1),
    "blender": (4, 0, 1),
    "location": "File > Import-Export > K2 model/clip",
    "description": "Import-Export meshes and animations used by K2 engine (Savage 2 and Heroes of Newerth games)",
    "warning": "",
    "wiki_url": "https://github.com/KRAT0Sz/K2-Blender-master-v2/wiki",
    "tracker_url": "https://discord.gg/T4dwSUP",
    "category": "Import-Export",
}


# ============================================================================
# Import operators
# ============================================================================

class K2ImporterClip(bpy.types.Operator):
    """Load K2/Silverlight clip data"""
    bl_idname = "import_clip.k2"
    bl_label = "Import K2 Clip"

    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default="*.clip", options={'HIDDEN'})

    def execute(self, context):
        from . import k2_import
        k2_import.readclip(self.filepath)
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class K2Importer(bpy.types.Operator):
    """Load K2/Silverlight mesh data"""
    bl_idname = "import_mesh.k2"
    bl_label = "Import K2 Mesh"

    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default="*.model", options={'HIDDEN'})
    flipuv: BoolProperty(name="Flip UV", description="Flip UV", default=True)

    def execute(self, context):
        from . import k2_import
        settings = context.scene.k2_import_settings
        k2_import.read(self.filepath, settings.flip_uv)

        from .k2_common import view_all_in_3d_view
        if not view_all_in_3d_view():
            self.report({'WARNING'}, "Failed to focus on 3D view.")

        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


# ============================================================================
# Export operators
# ============================================================================

class K2ClipExporter(bpy.types.Operator):
    """Save K2 triangle clip data"""
    bl_idname = "export_clip.k2"
    bl_label = "Export K2 Clip"

    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default="*.clip", options={'HIDDEN'})
    check_existing: BoolProperty(
        name="Check Existing",
        description="Check and warn on overwriting existing files",
        default=True, options={'HIDDEN'},
    )

    def execute(self, context):
        from . import k2_export
        settings = context.scene.k2_export_settings
        k2_export.export_k2_clip(
            self.filepath, settings.apply_modifiers,
            settings.frame_start, settings.frame_end,
        )
        return {'FINISHED'}

    def invoke(self, context, event):
        if not self.filepath:
            self.filepath = bpy.path.ensure_ext(bpy.data.filepath, ".clip")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class K2MeshExporter(bpy.types.Operator):
    """Save K2 triangle mesh data"""
    bl_idname = "export_mesh.k2"
    bl_label = "Export K2 Mesh"

    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default="*.model", options={'HIDDEN'})
    check_existing: BoolProperty(
        name="Check Existing",
        description="Check and warn on overwriting existing files",
        default=True, options={'HIDDEN'},
    )

    def execute(self, context):
        from . import k2_export
        settings = context.scene.k2_export_settings
        k2_export.export_k2_mesh(self.filepath, settings.apply_modifiers)
        return {'FINISHED'}

    def invoke(self, context, event):
        if not self.filepath:
            self.filepath = bpy.path.ensure_ext(bpy.data.filepath, ".model")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


# ============================================================================
# Panel
# ============================================================================

class K2_PT_ImportExportPanel(bpy.types.Panel):
    bl_label = "K2 Import-Export"
    bl_idname = "K2_PT_ImportExportPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'K2 Import-Export'

    def draw(self, context):
        layout = self.layout
        settings_imp = context.scene.k2_import_settings
        settings_exp = context.scene.k2_export_settings

        col = layout.column(align=True)
        col.label(text="Import:")
        col.operator("import_mesh.k2", text="Import K2 Mesh")
        col.operator("import_clip.k2", text="Import K2 Clip")
        col.prop(settings_imp, "flip_uv", text="Flip UV")

        col.separator()

        col.label(text="Export:")
        col.operator("export_mesh.k2", text="Export K2 Mesh")
        col.operator("export_clip.k2", text="Export K2 Clip")
        col.prop(settings_exp, "apply_modifiers", text="Apply Modifiers")
        col.prop(settings_exp, "frame_start", text="Start Frame")
        col.prop(settings_exp, "frame_end", text="End Frame")


# ============================================================================
# Property groups (wired into operators via context.scene)
# ============================================================================

class K2ImportSettings(bpy.types.PropertyGroup):
    flip_uv: BoolProperty(
        name="Flip UV",
        description="Flip UV coordinates",
        default=True,
    )


class K2ExportSettings(bpy.types.PropertyGroup):
    apply_modifiers: BoolProperty(
        name="Apply Modifiers",
        description="Apply modifiers before exporting",
        default=True,
    )
    frame_start: IntProperty(
        name="Start Frame",
        description="Starting frame for export",
        default=0,
    )
    frame_end: IntProperty(
        name="End Frame",
        description="Ending frame for export",
        default=250,
    )


# ============================================================================
# File menu integration
# ============================================================================

def menu_func_import(self, context):
    self.layout.operator(K2Importer.bl_idname, text="K2 Mesh (.model)")
    self.layout.operator(K2ImporterClip.bl_idname, text="K2 Clip (.clip)")


def menu_func_export(self, context):
    self.layout.operator(K2MeshExporter.bl_idname, text="K2 Mesh (.model)")
    self.layout.operator(K2ClipExporter.bl_idname, text="K2 Clip (.clip)")


# ============================================================================
# Registration
# ============================================================================

_classes = (
    K2ImportSettings,
    K2ExportSettings,
    K2ImporterClip,
    K2Importer,
    K2ClipExporter,
    K2MeshExporter,
    K2_PT_ImportExportPanel,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.k2_import_settings = PointerProperty(type=K2ImportSettings)
    bpy.types.Scene.k2_export_settings = PointerProperty(type=K2ExportSettings)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    del bpy.types.Scene.k2_export_settings
    del bpy.types.Scene.k2_import_settings
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
