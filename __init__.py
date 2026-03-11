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

from . import k2_ui

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
    tex_color: BoolProperty(
        name="Color",
        description="Import color/diffuse/albedo texture",
        default=True,
    )
    tex_color2: BoolProperty(
        name="Color 2",
        description="Import secondary color texture (team color / tint)",
        default=False,
    )
    tex_color3: BoolProperty(
        name="Color 3",
        description="Import tertiary color texture (detail / specular)",
        default=False,
    )
    tex_normal: BoolProperty(
        name="Normal",
        description="Import normal map texture",
        default=True,
    )
    tex_mrao: BoolProperty(
        name="MRAO",
        description="Import MRAO (Metallic/Roughness/AO) texture",
        default=True,
    )
    tex_emissive: BoolProperty(
        name="Emissive",
        description="Import emissive/glow texture",
        default=True,
    )


class K2ExportSettings(bpy.types.PropertyGroup):
    export_mode: EnumProperty(
        name="Export Mode",
        items=[
            ('STATIC', "Static Mesh", "Export as static mesh without animation"),
            ('ANIMATED', "Animated Mesh", "Export with skeleton and animation"),
        ],
        default='STATIC',
    )
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
        tex_flags = {
            'color': settings.tex_color,
            'color2': settings.tex_color2,
            'color3': settings.tex_color3,
            'normal': settings.tex_normal,
            'mrao': settings.tex_mrao,
            'emissive': settings.tex_emissive,
        }
        k2_import.read(self.filepath, settings.flip_uv, tex_flags)

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


class K2_OT_ImportTextures(bpy.types.Operator):
    """Select any texture file — all textures in that folder will be matched to materials"""
    bl_idname = "k2.import_textures"
    bl_label = "Import Textures"

    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(
        default="*.tga;*.png;*.dds;*.jpg;*.jpeg;*.bmp;*.tif",
        options={'HIDDEN'},
    )

    def execute(self, context):
        import os
        from .k2_texture import assign_textures_to_objects
        tex_dir = os.path.dirname(os.path.abspath(self.filepath))
        settings = context.scene.k2_import_settings
        tex_flags = {
            'color': settings.tex_color,
            'color2': settings.tex_color2,
            'color3': settings.tex_color3,
            'normal': settings.tex_normal,
            'mrao': settings.tex_mrao,
            'emissive': settings.tex_emissive,
        }
        objects = [o for o in context.selected_objects if o.type == 'MESH']
        if not objects:
            objects = [o for o in context.scene.objects if o.type == 'MESH']
        count = assign_textures_to_objects(objects, tex_dir, tex_flags)
        if count:
            self.report({'INFO'}, f"Loaded textures for {count} material(s) from {tex_dir}")
        else:
            self.report({'WARNING'}, f"No matching textures found in {tex_dir}")
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
        opts = k2_export.ExportOptions.from_scene(context.scene)
        k2_export.export_k2_mesh(self.filepath, opts)
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
        opts = k2_export.ExportOptions.from_scene(context.scene)
        k2_export.export_k2_clip(self.filepath, opts)
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
    """Display K2 scene statistics (mirrors original S2 exporter Scene Info)"""
    bl_idname = "k2.scene_info"
    bl_label = "Scene Info"

    def execute(self, context):
        total_verts = 0
        total_faces = 0
        num_meshes = 0
        num_surfs = 0
        num_sprites = 0
        num_bones = 0
        num_skinned = 0
        num_static = 0

        for obj in bpy.data.objects:
            if obj.type == 'MESH':
                mt = 'NORMAL'
                if hasattr(obj, 'k2_mesh_settings'):
                    mt = obj.k2_mesh_settings.mesh_type
                if mt == 'COLLISION':
                    num_surfs += 1
                elif mt in ('SPRITE', 'GROUND'):
                    num_sprites += 1
                else:
                    num_meshes += 1
                    total_verts += len(obj.data.vertices)
                    total_faces += len(obj.data.polygons)
                    has_armature_mod = any(
                        m.type == 'ARMATURE' for m in obj.modifiers
                    )
                    if has_armature_mod:
                        num_skinned += 1
                    else:
                        num_static += 1
            elif obj.type == 'ARMATURE':
                num_bones += len(obj.data.bones)

        lines = [
            f"{total_verts} vertices, {total_faces} faces",
            f"{num_meshes} meshes, {num_bones} bones",
            f"{num_surfs} collision surfaces, {num_sprites} sprites",
            f"Skinned: {num_skinned}, Static: {num_static}",
        ]
        self.report({'INFO'}, " | ".join(lines))
        return {'FINISHED'}


# ============================================================================
# Armature display operators
# ============================================================================

def _get_armature_objects():
    return [o for o in bpy.data.objects if o.type == 'ARMATURE']


class K2_OT_ToggleBoneNames(bpy.types.Operator):
    """Toggle bone name display for all armatures in the scene"""
    bl_idname = "k2.toggle_bone_names"
    bl_label = "Toggle Bone Names"

    def execute(self, context):
        arms = _get_armature_objects()
        if not arms:
            self.report({'WARNING'}, "No armatures in scene")
            return {'CANCELLED'}
        new_state = not arms[0].data.show_names
        for obj in arms:
            obj.data.show_names = new_state
        self.report({'INFO'}, f"Bone names: {'ON' if new_state else 'OFF'}")
        return {'FINISHED'}


class K2_OT_FixBoneDisplay(bpy.types.Operator):
    """Set bone display to visible colors (cyan/yellow) and STICK mode"""
    bl_idname = "k2.fix_bone_display"
    bl_label = "Fix Bone Colors"

    def execute(self, context):
        arms = _get_armature_objects()
        if not arms:
            self.report({'WARNING'}, "No armatures in scene")
            return {'CANCELLED'}
        count = 0
        for obj in arms:
            arm = obj.data
            arm.display_type = 'STICK'
            for bone in arm.bones:
                bone.color.palette = 'CUSTOM'
                bone.color.custom.normal = (0.0, 0.75, 1.0)
                bone.color.custom.select = (1.0, 0.85, 0.0)
                bone.color.custom.active = (0.2, 1.0, 0.4)
                count += 1
        self.report({'INFO'}, f"Fixed {count} bones across {len(arms)} armature(s)")
        return {'FINISHED'}


class K2_OT_ResetBoneDisplay(bpy.types.Operator):
    """Reset bone colors back to Blender defaults"""
    bl_idname = "k2.reset_bone_display"
    bl_label = "Reset Bone Colors"

    def execute(self, context):
        arms = _get_armature_objects()
        if not arms:
            self.report({'WARNING'}, "No armatures in scene")
            return {'CANCELLED'}
        for obj in arms:
            arm = obj.data
            arm.display_type = 'OCTAHEDRAL'
            for bone in arm.bones:
                bone.color.palette = 'DEFAULT'
        self.report({'INFO'}, "Bone display reset to defaults")
        return {'FINISHED'}


class K2_OT_SetBoneDisplayType(bpy.types.Operator):
    """Cycle armature bone display type"""
    bl_idname = "k2.cycle_bone_display"
    bl_label = "Cycle Display Type"

    _types = ['OCTAHEDRAL', 'STICK', 'BBONE', 'ENVELOPE', 'WIRE']

    def execute(self, context):
        arms = _get_armature_objects()
        if not arms:
            self.report({'WARNING'}, "No armatures in scene")
            return {'CANCELLED'}
        cur = arms[0].data.display_type
        idx = (self._types.index(cur) + 1) % len(self._types) if cur in self._types else 0
        new_type = self._types[idx]
        for obj in arms:
            obj.data.display_type = new_type
        self.report({'INFO'}, f"Bone display: {new_type}")
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
    K2_OT_ImportTextures,
    K2MeshExporter,
    K2ClipExporter,
    K2_OT_SceneInfo,
    K2_OT_ToggleBoneNames,
    K2_OT_FixBoneDisplay,
    K2_OT_ResetBoneDisplay,
    K2_OT_SetBoneDisplayType,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

    k2_ui.register_ui(bpy.utils.register_class)

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

    k2_ui.unregister_ui(bpy.utils.unregister_class)

    for pcoll in preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    preview_collections.clear()


if __name__ == "__main__":
    register()
