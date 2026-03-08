"""
K2 Model/Animation Import-Export addon for Blender.
Supports K2 engine formats used by Savage 2 and Heroes of Newerth.
"""

import os
import bpy
import bpy.utils.previews
from bpy.props import (
    StringProperty, BoolProperty, IntProperty,
    PointerProperty, EnumProperty,
)

bl_info = {
    "name": "K2 Model/Animation Import-Export",
    "author": "Anton Romanov",
    "version": (0, 0, 5),
    "blender": (5, 0, 0),
    "location": "File > Import-Export > K2 model/clip",
    "description": "Import-Export meshes and animations used by K2 engine (Savage 2 and Heroes of Newerth games)",
    "warning": "",
    "wiki_url": "https://github.com/KRAT0Sz/K2-Blender-master-v2/wiki",
    "tracker_url": "https://discord.gg/T4dwSUP",
    "category": "Import-Export",
}

preview_collections = {}


# ============================================================================
# Property groups
# ============================================================================

class K2ImportSettings(bpy.types.PropertyGroup):
    flip_uv: BoolProperty(
        name="Flip UV",
        description="Flip UV coordinates",
        default=True,
    )


class K2ExportSettings(bpy.types.PropertyGroup):
    force_static: BoolProperty(
        name="Force Static",
        description="Export without skeleton/animation",
        default=False,
    )
    remove_hierarchy: BoolProperty(
        name="Remove Hierarchy",
        description="Flatten bone hierarchy on export",
        default=False,
    )
    copy_textures: BoolProperty(
        name="Copy Textures",
        description="Copy texture files alongside exported model",
        default=True,
    )
    export_geometry: BoolProperty(
        name="Geometry",
        description="Export mesh geometry data",
        default=True,
    )
    export_model_def: BoolProperty(
        name="Model Definition",
        description="Export model definition",
        default=True,
    )
    export_materials: BoolProperty(
        name="Materials",
        description="Export material data",
        default=True,
    )
    export_animation: BoolProperty(
        name="Animation",
        description="Export animation data",
        default=False,
    )
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


class K2MeshSettings(bpy.types.PropertyGroup):
    mesh_type: EnumProperty(
        name="Mesh Type",
        items=[
            ('NORMAL', "Normal mesh", "Standard renderable mesh"),
            ('COLLISION', "Collision surface", "Physics collision mesh"),
            ('REFBONE', "Reference bone", "Bone reference point"),
            ('SPRITE', "Sprite", "Sprite type mesh"),
            ('GROUND', "Ground plane", "Ground plane mesh"),
        ],
        default='NORMAL',
    )
    exclude_normals: BoolProperty(
        name="Exclude normals",
        description="Do not export vertex normals for this mesh",
        default=False,
    )
    roof: BoolProperty(
        name="Roof",
        description="Mark this mesh as a roof surface",
        default=False,
    )


# ============================================================================
# Import operators
# ============================================================================

class K2Importer(bpy.types.Operator):
    """Load K2/Silverlight mesh data"""
    bl_idname = "import_mesh.k2"
    bl_label = "Import K2 Mesh"

    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default="*.model", options={'HIDDEN'})

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


# ============================================================================
# Export operators
# ============================================================================

class K2MeshExporter(bpy.types.Operator):
    """Save K2 triangle mesh data"""
    bl_idname = "export_mesh.k2"
    bl_label = "Export K2 Mesh"

    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default="*.model", options={'HIDDEN'})
    check_existing: BoolProperty(default=True, options={'HIDDEN'})

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


class K2ClipExporter(bpy.types.Operator):
    """Save K2 triangle clip data"""
    bl_idname = "export_clip.k2"
    bl_label = "Export K2 Clip"

    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default="*.clip", options={'HIDDEN'})
    check_existing: BoolProperty(default=True, options={'HIDDEN'})

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


# ============================================================================
# Scene info operator
# ============================================================================

class K2_OT_SceneInfo(bpy.types.Operator):
    """Display K2 scene statistics"""
    bl_idname = "k2.scene_info"
    bl_label = "Scene Info"

    def execute(self, context):
        meshes = sum(1 for o in bpy.data.objects if o.type == 'MESH')
        armatures = sum(1 for o in bpy.data.objects if o.type == 'ARMATURE')
        bones = sum(len(o.data.bones) for o in bpy.data.objects if o.type == 'ARMATURE')
        verts = sum(len(o.data.vertices) for o in bpy.data.objects if o.type == 'MESH')
        self.report(
            {'INFO'},
            f"Meshes: {meshes} | Verts: {verts} | Armatures: {armatures} | Bones: {bones}",
        )
        return {'FINISHED'}


# ============================================================================
# Helper — get custom logo icon
# ============================================================================

def _get_logo_icon():
    pcoll = preview_collections.get("k2_icons")
    if pcoll and "logo" in pcoll:
        return pcoll["logo"].icon_id
    return 0


# ============================================================================
# Panels — mirroring S2 Games Model Exporter layout
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
        col_text.label(text="Version 4")
        icon_id = _get_logo_icon()
        if icon_id:
            col_logo = header.column()
            col_logo.template_icon(icon_value=icon_id, scale=5.0)

        layout.separator()

        # ---- Export options ----
        box = layout.box()
        box.label(text="Export options")
        col = box.column(align=True)
        col.prop(settings, "force_static")
        col.prop(settings, "remove_hierarchy")
        col.prop(settings, "copy_textures")
        col.prop(settings, "export_geometry")
        col.prop(settings, "export_model_def")
        col.prop(settings, "export_materials")
        col.prop(settings, "export_animation")

        box.separator()

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

        layout.operator("k2.scene_info", text="Scene Info")


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
    K2MeshSettings,
    K2Importer,
    K2ImporterClip,
    K2MeshExporter,
    K2ClipExporter,
    K2_OT_SceneInfo,
    K2_PT_ExportPanel,
    K2_PT_ImportPanel,
    K2_PT_MeshInfoPanel,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.k2_import_settings = PointerProperty(type=K2ImportSettings)
    bpy.types.Scene.k2_export_settings = PointerProperty(type=K2ExportSettings)
    bpy.types.Object.k2_mesh_settings = PointerProperty(type=K2MeshSettings)

    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

    pcoll = bpy.utils.previews.new()
    icon_path = os.path.join(os.path.dirname(__file__), "logo.png")
    if os.path.exists(icon_path):
        pcoll.load("logo", icon_path, 'IMAGE')
    preview_collections["k2_icons"] = pcoll


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

    del bpy.types.Object.k2_mesh_settings
    del bpy.types.Scene.k2_export_settings
    del bpy.types.Scene.k2_import_settings

    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)

    for pcoll in preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    preview_collections.clear()


if __name__ == "__main__":
    register()
