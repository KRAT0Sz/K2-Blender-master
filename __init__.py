import bpy
from bpy.props import StringProperty, BoolProperty, IntProperty, PointerProperty

bl_info = {
    "name": "K2 Model/Animation Import-Export",
    "author": "Anton Romanov",
    "version": (1, 0, 0),
    "blender": (4, 0, 1),
    "location": "File > Import-Export > K2 model/clip",
    "description": "Import-Export meshes and animations used by K2 engine (Savage 2 and Heroes of Newerth games)",
    "warning": "",
    "wiki_url": "https://github.com/KRAT0Sz/K2-Blender-master-v2/wiki",
    "tracker_url": "https://discord.gg/T4dwSUP",
    "category": "Import-Export"
}

# Operator for importing K2/Silverlight clip data
class K2ImporterClip(bpy.types.Operator):
    """Load K2/Silverlight clip data"""
    bl_idname = "import_clip.k2"
    bl_label = "Import K2 Clip"

    filepath: StringProperty(
        subtype='FILE_PATH'
    )
    filter_glob: StringProperty(
        default="*.clip", options={'HIDDEN'}
    )

    def execute(self, context):
        from . import k2_import
        k2_import.readclip(self.filepath)
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

# Operator for importing K2/Silverlight mesh data
class K2Importer(bpy.types.Operator):
    """Load K2/Silverlight mesh data"""
    bl_idname = "import_mesh.k2"
    bl_label = "Import K2 Mesh"

    filepath: StringProperty(
        subtype='FILE_PATH'
    )
    filter_glob: StringProperty(
        default="*.model", options={'HIDDEN'}
    )
    flipuv: BoolProperty(
        name="Flip UV",
        description="Flip UV",
        default=True
    )

    def execute(self, context):
        from . import k2_import
        k2_import.read(self.filepath, self.flipuv)

        # Create a special context that includes VIEW_3D type areas and regions
        found_view3d = False
        for window in bpy.context.window_manager.windows:
            screen = window.screen
            for area in screen.areas:
                if area.type == 'VIEW_3D':
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            override = {
                                'window': window,
                                'screen': screen,
                                'area': area,
                                'region': region,
                                'scene': context.scene,
                            }
                            with context.temp_override(**override):
                                bpy.ops.view3d.view_all(center=False)
                            found_view3d = True
                            break
                if found_view3d:
                    break
            if found_view3d:
                break

        if not found_view3d:
            self.report({'WARNING'}, "Failed to focus on 3D view.")
            return {'CANCELLED'}

        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

# Operator for exporting K2 triangle clip data
class K2ClipExporter(bpy.types.Operator):
    """Save K2 triangle clip data"""
    bl_idname = "export_clip.k2"
    bl_label = "Export K2 Clip"

    filepath: StringProperty(
        subtype='FILE_PATH'
    )
    filter_glob: StringProperty(
        default="*.clip", options={'HIDDEN'}
    )
    check_existing: BoolProperty(
        name="Check Existing",
        description="Check and warn on overwriting existing files",
        default=True,
        options={'HIDDEN'}
    )
    apply_modifiers: BoolProperty(
        name="Apply Modifiers",
        description="Use transformed mesh data from each object",
        default=True
    )
    frame_start: IntProperty(
        name="Start Frame",
        description="Starting frame for the animation",
        default=0
    )
    frame_end: IntProperty(
        name="Ending Frame",
        description="Ending frame for the animation",
        default=250
    )

    def execute(self, context):
        from . import k2_export
        k2_export.export_k2_clip(
            self.filepath, self.apply_modifiers,
            self.frame_start, self.frame_end
        )
        return {'FINISHED'}

    def invoke(self, context, event):
        if not self.filepath:
            self.filepath = bpy.path.ensure_ext(bpy.data.filepath, ".clip")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

# Operator for exporting K2 triangle mesh data
class K2MeshExporter(bpy.types.Operator):
    """Save K2 triangle mesh data"""
    bl_idname = "export_mesh.k2"
    bl_label = "Export K2 Mesh"

    filepath: StringProperty(
        subtype='FILE_PATH'
    )
    filter_glob: StringProperty(
        default="*.model", options={'HIDDEN'}
    )
    check_existing: BoolProperty(
        name="Check Existing",
        description="Check and warn on overwriting existing files",
        default=True,
        options={'HIDDEN'}
    )
    apply_modifiers: BoolProperty(
        name="Apply Modifiers",
        description="Use transformed mesh data from each object",
        default=True
    )

    def execute(self, context):
        from . import k2_export
        k2_export.export_k2_mesh(self.filepath, self.apply_modifiers)
        return {'FINISHED'}

    def invoke(self, context, event):
        if not self.filepath:
            self.filepath = bpy.path.ensure_ext(bpy.data.filepath, ".model")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

# Panel in the 3D View sidebar
class K2_PT_ImportExportPanel(bpy.types.Panel):
    bl_label = "K2 Import-Export"
    bl_idname = "K2_PT_ImportExportPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'K2 Import-Export'

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        
        # Import section
        col.label(text="Import Options:")
        col.operator("import_mesh.k2", text="Import K2 Mesh")
        col.operator("import_clip.k2", text="Import K2 Clip")
        col.separator()
        
        # Export section
        col.label(text="Export Options:")
        col.operator("export_mesh.k2", text="Export K2 Mesh")
        col.operator("export_clip.k2", text="Export K2 Clip")
        col.separator()

        # Import Settings
        col.label(text="Import Settings:")
        col.prop(context.scene.k2_import_settings, "flip_uv", text="Flip UV")

        # Export Settings
        col.label(text="Export Settings:")
        col.prop(context.scene.k2_export_settings, "apply_modifiers", text="Apply Modifiers")
        col.prop(context.scene.k2_export_settings, "frame_start", text="Start Frame")
        col.prop(context.scene.k2_export_settings, "frame_end", text="End Frame")

# Properties for import settings
class K2ImportSettings(bpy.types.PropertyGroup):
    flip_uv: BoolProperty(
        name="Flip UV",
        description="Flip UV coordinates",
        default=True
    )

# Properties for export settings
class K2ExportSettings(bpy.types.PropertyGroup):
    apply_modifiers: BoolProperty(
        name="Apply Modifiers",
        description="Apply modifiers before exporting",
        default=True
    )
    frame_start: IntProperty(
        name="Start Frame",
        description="Starting frame for export",
        default=0
    )
    frame_end: IntProperty(
        name="End Frame",
        description="Ending frame for export",
        default=250
    )

# Register the add-on
def register():
    bpy.utils.register_class(K2ImporterClip)
    bpy.utils.register_class(K2Importer)
    bpy.utils.register_class(K2ClipExporter)
    bpy.utils.register_class(K2MeshExporter)
    bpy.utils.register_class(K2_PT_ImportExportPanel)
    bpy.utils.register_class(K2ImportSettings)
    bpy.utils.register_class(K2ExportSettings)
    bpy.types.Scene.k2_import_settings = PointerProperty(type=K2ImportSettings)
    bpy.types.Scene.k2_export_settings = PointerProperty(type=K2ExportSettings)

# Unregister the add-on
def unregister():
    bpy.utils.unregister_class(K2ImporterClip)
    bpy.utils.unregister_class(K2Importer)
    bpy.utils.unregister_class(K2ClipExporter)
    bpy.utils.unregister_class(K2MeshExporter)
    bpy.utils.unregister_class(K2_PT_ImportExportPanel)
    bpy.utils.unregister_class(K2ImportSettings)
    bpy.utils.unregister_class(K2ExportSettings)
    del bpy.types.Scene.k2_import_settings
    del bpy.types.Scene.k2_export_settings

if __name__ == "__main__":
    register()
