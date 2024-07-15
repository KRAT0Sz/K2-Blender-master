import bpy
from bpy.props import StringProperty, BoolProperty, IntProperty
from bpy.utils import previews
import os

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

# Import the necessary modules
from . import k2_import
from . import k2_export

# Load the logo image from K2-Blender-master-main
def load_logo():
    global custom_icons
    custom_icons = previews.new()
    icons_dir = os.path.join(os.path.dirname(__file__), "..", "K2-Blender-master-main")
    logo_path = os.path.join(icons_dir, "logo.png")
    if os.path.exists(logo_path):
        custom_icons.load("logo", logo_path, 'IMAGE')
    else:
        print(f"Logo file not found at: {logo_path}")

def clear_logo():
    global custom_icons
    previews.remove(custom_icons)

class K2_OT_Import(bpy.types.Operator):
    """Import K2 Model"""
    bl_idname = "wm.k2_import"
    bl_label = "Import K2 Model"

    def execute(self, context):
        import_path = context.scene.k2_import_path
        try:
            if not os.path.exists(import_path):
                self.report({'ERROR'}, f"Invalid path: {import_path}")
                return {'CANCELLED'}
            k2_import.read(import_path, True)
            self.report({'INFO'}, f"Imported model from: {import_path}")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to import model: {str(e)}")
        return {'FINISHED'}

class K2_OT_Export(bpy.types.Operator):
    """Export K2 Model"""
    bl_idname = "wm.k2_export"
    bl_label = "Export K2 Model"

    def execute(self, context):
        export_path = context.scene.k2_export_path
        try:
            if not os.path.exists(os.path.dirname(export_path)):
                self.report({'ERROR'}, f"Invalid path: {export_path}")
                return {'CANCELLED'}
            k2_export.export_k2_mesh(export_path, context.scene.k2_apply_modifiers)
            self.report({'INFO'}, f"Exported model to: {export_path}")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to export model: {str(e)}")
        return {'FINISHED'}

class K2_OT_ImportClip(bpy.types.Operator):
    """Import K2 Clip"""
    bl_idname = "wm.k2_import_clip"
    bl_label = "Import K2 Clip"

    def execute(self, context):
        import_path = context.scene.k2_import_clip_path
        try:
            if not os.path.exists(import_path):
                self.report({'ERROR'}, f"Invalid path: {import_path}")
                return {'CANCELLED'}
            k2_import.readclip(import_path)
            self.report({'INFO'}, f"Imported clip from: {import_path}")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to import clip: {str(e)}")
        return {'FINISHED'}

class K2_OT_ExportClip(bpy.types.Operator):
    """Export K2 Clip"""
    bl_idname = "wm.k2_export_clip"
    bl_label = "Export K2 Clip"

    def execute(self, context):
        export_path = context.scene.k2_export_clip_path
        try:
            if not os.path.exists(os.path.dirname(export_path)):
                self.report({'ERROR'}, f"Invalid path: {export_path}")
                return {'CANCELLED'}
            k2_export.export_k2_clip(export_path, context.scene.k2_frame_start, context.scene.k2_frame_end)
            self.report({'INFO'}, f"Exported clip to: {export_path}")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to export clip: {str(e)}")
        return {'FINISHED'}

class K2_PT_SettingsPanel(bpy.types.Panel):
    """Creates a Panel in the 3D View Sidebar"""
    bl_label = "K2 Import/Export Settings"
    bl_idname = "VIEW3D_PT_k2_settings"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "K2 Import/Export"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Display the logo and text
        row = layout.row()
        row.alignment = 'CENTER'
        row.scale_y = 1.5
        row.label(text="S2 Games Model Import/Exporter Version 4")
        row = layout.row()
        row.alignment = 'RIGHT'
        if "logo" in custom_icons:
            row.template_icon(custom_icons["logo"].icon_id, scale=5)
        else:
            row.label(text="Logo not found", icon='ERROR')

        layout.separator()

        # Import Settings
        box = layout.box()
        box.label(text="Import Settings", icon='IMPORT')
        box.prop(scene, "k2_import_path", text="Model Path")
        box.prop(scene, "k2_import_clip_path", text="Clip Path")
        box.operator("wm.k2_import", text="Import K2 Model", icon='IMPORT')
        box.operator("wm.k2_import_clip", text="Import K2 Clip", icon='IMPORT')

        layout.separator()

        # Export Settings
        box = layout.box()
        box.label(text="Export Settings", icon='EXPORT')
        box.prop(scene, "k2_export_path", text="Model Path")
        box.prop(scene, "k2_export_clip_path", text="Clip Path")
        box.prop(scene, "k2_apply_modifiers", text="Apply Modifiers")
        box.prop(scene, "k2_frame_start", text="Start Frame")
        box.prop(scene, "k2_frame_end", text="End Frame")
        box.operator("wm.k2_export", text="Export K2 Model", icon='EXPORT')
        box.operator("wm.k2_export_clip", text="Export K2 Clip", icon='EXPORT')

def register():
    load_logo()
    bpy.utils.register_class(K2_PT_SettingsPanel)
    bpy.utils.register_class(K2_OT_Import)
    bpy.utils.register_class(K2_OT_Export)
    bpy.utils.register_class(K2_OT_ImportClip)
    bpy.utils.register_class(K2_OT_ExportClip)
    bpy.types.Scene.k2_import_path = StringProperty(name="K2 Import Path", subtype='FILE_PATH', description="Path to import K2 model")
    bpy.types.Scene.k2_import_clip_path = StringProperty(name="K2 Import Clip Path", subtype='FILE_PATH', description="Path to import K2 clip")
    bpy.types.Scene.k2_export_path = StringProperty(name="K2 Export Path", subtype='FILE_PATH', description="Path to export K2 model")
    bpy.types.Scene.k2_export_clip_path = StringProperty(name="K2 Export Clip Path", subtype='FILE_PATH', description="Path to export K2 clip")
    bpy.types.Scene.k2_apply_modifiers = BoolProperty(name="Apply Modifiers", default=True, description="Apply modifiers on export")
    bpy.types.Scene.k2_frame_start = IntProperty(name="Start Frame", default=0, description="Start frame for exporting clip")
    bpy.types.Scene.k2_frame_end = IntProperty(name="End Frame", default=250, description="End frame for exporting clip")

def unregister():
    clear_logo()
    bpy.utils.unregister_class(K2_PT_SettingsPanel)
    bpy.utils.unregister_class(K2_OT_Import)
    bpy.utils.unregister_class(K2_OT_Export)
    bpy.utils.unregister_class(K2_OT_ImportClip)
    bpy.utils.unregister_class(K2_OT_ExportClip)
    del bpy.types.Scene.k2_import_path
    del bpy.types.Scene.k2_import_clip_path
    del bpy.types.Scene.k2_export_path
    del bpy.types.Scene.k2_export_clip_path
    del bpy.types.Scene.k2_apply_modifiers
    del bpy.types.Scene.k2_frame_start
    del bpy.types.Scene.k2_frame_end

if __name__ == "__main__":
    register()
