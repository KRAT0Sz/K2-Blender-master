"""
K2 engine model (.model) and animation clip (.clip) exporter for Blender.
Writes SMDL v3 meshes and CLIP v2 animations.
"""

import bpy
import bmesh
from io import BytesIO
import struct
import os
from math import degrees
from mathutils import Matrix

from .k2_common import (
    log, vlog, dlog, err,
    bone_depth,
    MKEY_X, MKEY_Y, MKEY_Z,
    MKEY_PITCH, MKEY_ROLL, MKEY_YAW,
    MKEY_VISIBILITY,
    MKEY_SCALE_X, MKEY_SCALE_Y, MKEY_SCALE_Z,
    MKEY_COUNT,
)

# ============================================================================
# Binary writing helpers
# ============================================================================

def write_block(file, name, data):
    file.write(name.encode('utf8')[:4])
    file.write(struct.pack("<i", len(data)))
    file.write(data)


# ============================================================================
# Bounding box
# ============================================================================

def generate_bbox(meshes):
    xx, yy, zz = [], [], []
    for mesh in meshes:
        for v in mesh.verts:
            xx.append(v.co[0])
            yy.append(v.co[1])
            zz.append(v.co[2])
    return [min(xx), min(yy), min(zz), max(xx), max(yy), max(zz)]


# ============================================================================
# Chunk data builders
# ============================================================================

def create_mesh_data(mesh, vert, index, name, mname):
    buf = BytesIO()
    buf.write(struct.pack("<i", index))
    buf.write(struct.pack("<i", 1))  # mode
    buf.write(struct.pack("<i", len(vert)))
    buf.write(struct.pack("<6f", *generate_bbox([mesh])))
    buf.write(struct.pack("<i", -1))  # bone link (TODO: proper value)
    buf.write(struct.pack("<B", len(name)))
    buf.write(struct.pack("<B", len(mname)))
    buf.write(name)
    buf.write(struct.pack("<B", 0))
    buf.write(mname)
    buf.write(struct.pack("<B", 0))
    return buf.getvalue()


def create_vrts_data(verts, meshindex):
    buf = BytesIO()
    buf.write(struct.pack("<i", meshindex))
    for v in verts:
        buf.write(struct.pack("<3f", *v.co))
    return buf.getvalue()


def create_face_data(verts, faces, meshindex):
    buf = BytesIO()
    buf.write(struct.pack("<i", meshindex))
    buf.write(struct.pack("<i", len(faces)))
    if len(verts) < 255:
        buf.write(struct.pack("<B", 1))
        fmt = '<3B'
    else:
        buf.write(struct.pack("<B", 2))
        fmt = '<3H'
    for f in faces:
        if len(f) == 3:
            buf.write(struct.pack(fmt, *f))
        else:
            log(f"Warning: Face {f} is not a triangle and will be skipped")
    return buf.getvalue()


def create_tang_data(tang, meshindex):
    buf = BytesIO()
    buf.write(struct.pack("<i", meshindex))
    buf.write(struct.pack("<i", 0))
    for t in tang:
        buf.write(struct.pack('<3f', *list(t)))
    return buf.getvalue()


def create_texc_data(texc, meshindex):
    buf = BytesIO()
    buf.write(struct.pack("<i", meshindex))
    buf.write(struct.pack("<i", 0))
    for t in texc:
        buf.write(struct.pack("<2f", t[0], 1.0 - t[1]))
    return buf.getvalue()


def create_colr_data(colr, meshindex):
    buf = BytesIO()
    buf.write(struct.pack("<i", meshindex))
    for c in colr:
        buf.write(struct.pack("<4B", c.r, c.g, c.b, c.a))
    return buf.getvalue()


def create_nrml_data(verts, meshindex):
    buf = BytesIO()
    buf.write(struct.pack("<i", meshindex))
    for v in verts:
        buf.write(struct.pack("<3f", *v.normal))
    return buf.getvalue()


def create_lnk1_data(lnk1, meshindex, bone_indices):
    buf = BytesIO()
    buf.write(struct.pack("<i", meshindex))
    buf.write(struct.pack("<i", len(lnk1)))
    for influences in lnk1:
        influences = [inf for inf in influences if inf[0] in bone_indices]
        count = len(influences)
        buf.write(struct.pack("<i", count))
        if count > 0:
            buf.write(struct.pack(f'<{count}f', *[inf[1] for inf in influences]))
            buf.write(struct.pack(f'<{count}I', *[bone_indices[inf[0]] for inf in influences]))
    return buf.getvalue()


def create_sign_data(meshindex, sign):
    buf = BytesIO()
    buf.write(struct.pack("<i", meshindex))
    buf.write(struct.pack("<i", 0))
    for s in sign:
        buf.write(struct.pack("<b", s))
    return buf.getvalue()


# ============================================================================
# Face / vertex data conversion
# ============================================================================

def calc_face_signs(ftexc):
    fsigns = []
    for uv in ftexc:
        cross = ((uv[1][0] - uv[0][0]) * (uv[2][1] - uv[1][1])
                 - (uv[1][1] - uv[0][1]) * (uv[2][0] - uv[1][0]))
        if cross > 0:
            fsigns.append((0, 0, 0))
        else:
            fsigns.append((-1, -1, -1))
    return fsigns


def face_to_vertices(faces, fdata, verts):
    """Map per-face data to per-vertex data. First-write wins for shared vertices."""
    vdata = [None] * len(verts)
    for fi, f in enumerate(faces):
        if fi >= len(fdata):
            log(f"face_to_vertices: face index {fi} out of range (fdata length {len(fdata)})")
            continue
        face_data = fdata[fi]
        if len(f) != len(face_data):
            log(f"face_to_vertices: mismatch at face {fi} — {len(f)} vs {len(face_data)}")
            continue
        for vi, v in enumerate(f):
            vdata[v] = face_data[vi]
    return vdata


def face_to_vertices_dup(faces, fdata, verts):
    """Map per-face data to per-vertex, duplicating vertices when values conflict."""
    vdata = [None] * len(verts)
    for fi, f in enumerate(faces):
        if fi >= len(fdata):
            log(f"face_to_vertices_dup: face index {fi} out of range (fdata length {len(fdata)})")
            continue
        face_data = fdata[fi]
        if len(f) != len(face_data):
            log(f"face_to_vertices_dup: mismatch at face {fi} — {len(f)} vs {len(face_data)}")
            continue
        for vi, v in enumerate(f):
            if vdata[v] is None or vdata[v] == face_data[vi]:
                vdata[v] = face_data[vi]
            else:
                newind = len(verts)
                verts.append(verts[v])
                faces[fi][vi] = newind
                vdata.append(face_data[vi])
    return vdata


# ============================================================================
# Bone data builder
# ============================================================================

def create_bone_data(armature, arm_matrix, transform):
    bones = sorted(armature.bones.values(), key=bone_depth)
    bone_names = [bone.name for bone in bones]

    bonedata = BytesIO()
    for bone in bones:
        base = bone.matrix_local.copy()
        if transform:
            base = base @ arm_matrix
        base_inv = base.copy()
        base_inv.invert()

        parent_index = bone_names.index(bone.parent.name) if bone.parent else -1

        base_inv.transpose()
        base.transpose()

        bonedata.write(struct.pack("<i", parent_index))
        bonedata.write(struct.pack('<12f', *sum([list(row[0:3]) for row in base_inv], [])))
        bonedata.write(struct.pack('<12f', *sum([list(row[0:3]) for row in base], [])))
        name_bytes = bone.name.encode('utf8')
        bonedata.write(struct.pack("B", len(name_bytes)))
        bonedata.write(name_bytes)
        bonedata.write(struct.pack("B", 0))

    return bone_names, bonedata.getvalue()


# ============================================================================
# Selection helpers
# ============================================================================

def _select_objects_by_type(*types):
    """Deselect all, then select objects matching the given type(s)."""
    bpy.context.view_layer.objects.active = None
    bpy.ops.object.select_all(action='DESELECT')
    found = set()
    for obj in bpy.data.objects:
        if obj.type in types:
            obj.select_set(True)
            found.add(obj.type)
    for t in types:
        if t not in found:
            log(f"No {t.lower()} objects found in the scene.")


# ============================================================================
# Mesh export
# ============================================================================

def export_k2_mesh(filename, apply_modifiers):
    _select_objects_by_type('ARMATURE', 'MESH')

    meshes = []
    armature = None
    arm_matrix = None
    for obj in bpy.context.selected_objects:
        if obj.type == 'MESH':
            matrix = obj.matrix_world
            if apply_modifiers:
                depsgraph = bpy.context.evaluated_depsgraph_get()
                me = obj.evaluated_get(depsgraph).to_mesh()
            else:
                me = obj.data
            bm = bmesh.new()
            bm.from_mesh(me)
            bmesh.ops.triangulate(bm, faces=bm.faces[:])
            bm.transform(matrix)
            meshes.append((obj, bm))
        elif obj.type == 'ARMATURE':
            armature = obj.data
            arm_matrix = obj.matrix_world

    bone_names = []
    bonedata = b''
    if armature:
        armature.pose_position = 'REST'
        bone_names, bonedata = create_bone_data(armature, arm_matrix, apply_modifiers)

    # Build bone_indices lookup: vertex group index -> bone index
    bone_indices_map = {}

    # Build header
    headdata = BytesIO()
    headdata.write(struct.pack("<i", 3))  # version
    headdata.write(struct.pack("<i", len(meshes)))
    headdata.write(struct.pack("<i", 0))  # sprites
    headdata.write(struct.pack("<i", 0))  # surfs
    headdata.write(struct.pack("<i", len(armature.bones) if armature else 0))
    headdata.write(struct.pack("<6f", *generate_bbox([bm for _, bm in meshes])))

    os.makedirs(os.path.dirname(filename), exist_ok=True)

    with open(filename, 'wb') as file:
        file.write(b'SMDL')
        write_block(file, 'head', headdata.getvalue())
        if armature:
            write_block(file, 'bone', bonedata)

        for meshindex, (obj, mesh) in enumerate(meshes):
            vert = list(mesh.verts)
            faces = []
            ftexc = []
            ftang = []
            fcolr = []
            flnk1 = []

            uv_lay = mesh.loops.layers.uv.active
            has_uv = uv_lay is not None
            col_lay = mesh.loops.layers.color.active
            has_color = col_lay is not None
            dvert_lay = mesh.verts.layers.deform.active
            if dvert_lay:
                flnk1 = [v[dvert_lay].items() for v in mesh.verts]

            for f in mesh.faces:
                uv = []
                col = []
                vindex = []
                tang = []
                for loop in f.loops:
                    if has_uv:
                        uv.append(loop[uv_lay].uv)
                    vindex.append(loop.vert.index)
                    if has_color:
                        col.append(loop[col_lay].color)
                    tang.append(loop.calc_tangent())
                if has_uv:
                    ftexc.append(uv)
                ftang.append(tang)
                faces.append(vindex)
                if has_color:
                    fcolr.append(col)

            texc = None
            tang_data = None
            sign = None
            if has_uv:
                fsign = calc_face_signs(ftexc)
                sign = face_to_vertices(faces, fsign, vert)
                texc = face_to_vertices(faces, ftexc, vert)
                tang_data = face_to_vertices(faces, ftang, vert)
                for i in range(len(vert)):
                    if tang_data[i] is not None:
                        tang_data[i] = tang_data[i] - vert[i].normal * tang_data[i].dot(vert[i].normal)
                        tang_data[i].normalize()

            colr = face_to_vertices(faces, fcolr, vert) if has_color else None

            # Material name (fallback to mesh name if no material assigned)
            if obj.data.materials:
                mat_name = obj.data.materials[0].name.encode('utf8')
            else:
                mat_name = obj.name.encode('utf8')

            write_block(file, 'mesh', create_mesh_data(
                mesh, vert, meshindex, obj.name.encode('utf8'), mat_name))
            write_block(file, 'vrts', create_vrts_data(vert, meshindex))

            if armature:
                bone_indices_map = {}
                for group in obj.vertex_groups:
                    if group.name in bone_names:
                        bone_indices_map[group.index] = bone_names.index(group.name)
                write_block(file, 'lnk1', create_lnk1_data(flnk1, meshindex, bone_indices_map))

            if faces:
                write_block(file, 'face', create_face_data(vert, faces, meshindex))
                if has_uv and texc is not None:
                    write_block(file, "texc", create_texc_data(texc, meshindex))
                    for i in range(len(tang_data)):
                        if sign[i] == 0:
                            tang_data[i] = -(tang_data[i].copy())
                    write_block(file, "tang", create_tang_data(tang_data, meshindex))
                    write_block(file, "sign", create_sign_data(meshindex, sign))
                write_block(file, "nrml", create_nrml_data(vert, meshindex))
            if colr is not None:
                write_block(file, "colr", create_colr_data(colr, meshindex))

            vlog(f'Mesh {meshindex}: {len(vert) - len(mesh.verts)} vertices duplicated')


# ============================================================================
# Clip export
# ============================================================================

def _write_clip_bone(file, bone_name_bytes, motion, index):
    """Write all motion key channels for a single bone."""
    for keytype in range(MKEY_COUNT):
        keydata = BytesIO()
        key = motion[keytype]
        if min(key) == max(key):
            key = [key[0]]
        numkeys = len(key)
        keydata.write(struct.pack("<i", index))
        keydata.write(struct.pack("<i", keytype))
        keydata.write(struct.pack("<i", numkeys))
        keydata.write(struct.pack("B", len(bone_name_bytes)))
        keydata.write(bone_name_bytes)
        keydata.write(struct.pack("B", 0))
        if keytype == MKEY_VISIBILITY:
            keydata.write(struct.pack(f'{numkeys}B', *key))
        else:
            keydata.write(struct.pack(f'<{numkeys}f', *key))
        write_block(file, 'bmtn', keydata.getvalue())


def export_k2_clip(filename, transform, frame_start, frame_end):
    _select_objects_by_type('ARMATURE')

    obj_list = bpy.context.selected_objects
    if len(obj_list) != 1 or obj_list[0].type != 'ARMATURE':
        err('Select needed armature only')
        return

    arm_ob = obj_list[0]
    armature = arm_ob.data
    motions = {}

    vlog('Baking animation...')

    world_mat = arm_ob.matrix_world if transform else Matrix.Identity(4)
    scene = bpy.context.scene
    pose = arm_ob.pose

    for frame in range(frame_start, frame_end + 1):
        scene.frame_set(frame)
        for bone in pose.bones:
            matrix = bone.matrix
            if bone.parent:
                matrix = bone.parent.matrix.inverted() @ matrix
            if transform:
                matrix = world_mat @ matrix

            if bone.name not in motions:
                motions[bone.name] = [[] for _ in range(MKEY_COUNT)]

            motion = motions[bone.name]
            translation = matrix.to_translation()
            rotation = matrix.to_euler('YXZ')
            scale = matrix.to_scale()

            motion[MKEY_X].append(translation[0])
            motion[MKEY_Y].append(translation[1])
            motion[MKEY_Z].append(translation[2])
            motion[MKEY_PITCH].append(degrees(rotation[0]))
            motion[MKEY_ROLL].append(degrees(rotation[1]))
            motion[MKEY_YAW].append(degrees(rotation[2]))
            motion[MKEY_SCALE_X].append(scale[0])
            motion[MKEY_SCALE_Y].append(scale[1])
            motion[MKEY_SCALE_Z].append(scale[2])
            motion[MKEY_VISIBILITY].append(255)

    headdata = BytesIO()
    headdata.write(struct.pack("<i", 2))  # version
    headdata.write(struct.pack("<i", len(motions)))
    headdata.write(struct.pack("<i", frame_end - frame_start + 1))

    os.makedirs(os.path.dirname(filename), exist_ok=True)

    with open(filename, 'wb') as file:
        file.write(b'CLIP')
        write_block(file, 'head', headdata.getvalue())

        for index, bone_name in enumerate(
            sorted(armature.bones.keys(), key=lambda x: bone_depth(armature.bones[x]))
        ):
            _write_clip_bone(file, bone_name.encode('utf8'), motions[bone_name], index)
