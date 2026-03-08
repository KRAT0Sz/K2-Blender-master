"""
Shared constants, logging, and utilities for K2 import/export.
"""

import struct
from mathutils import Vector, Matrix
import math

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_LEVEL = 3

def log(msg):
    if LOG_LEVEL >= 1:
        print(msg)

def vlog(msg):
    if LOG_LEVEL >= 2:
        print(msg)

def dlog(msg):
    if LOG_LEVEL >= 3:
        print(msg)

def err(msg):
    log(f"ERROR: {msg}")

# ---------------------------------------------------------------------------
# MKEY constants (motion key types for clip data)
# ---------------------------------------------------------------------------

MKEY_X = 0
MKEY_Y = 1
MKEY_Z = 2
MKEY_PITCH = 3
MKEY_ROLL = 4
MKEY_YAW = 5
MKEY_VISIBILITY = 6
MKEY_SCALE_X = 7
MKEY_SCALE_Y = 8
MKEY_SCALE_Z = 9
MKEY_COUNT = 10

# ---------------------------------------------------------------------------
# Binary helpers
# ---------------------------------------------------------------------------

def read_int(chunk):
    return struct.unpack("<i", chunk.read(4))[0]

def read_float(chunk):
    return struct.unpack("<f", chunk.read(4))[0]

# ---------------------------------------------------------------------------
# Bone helpers
# ---------------------------------------------------------------------------

def bone_depth(bone):
    depth = 0
    while bone.parent:
        depth += 1
        bone = bone.parent
    return depth

# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def round_vector(vec, dec=17):
    return Vector([round(v, dec) for v in vec])

def round_matrix(mat, dec=17):
    return Matrix([round_vector(row, dec) for row in mat])

def vec_roll_to_mat3(vec, roll):
    target = Vector((0, 1, 0))
    nor = vec.normalized()
    axis = target.cross(nor)
    if axis.dot(axis) > 0.000001:
        axis.normalize()
        theta = target.angle(nor)
        b_matrix = Matrix.Rotation(theta, 3, axis)
    else:
        updown = 1 if target.dot(nor) > 0 else -1
        b_matrix = Matrix.Scale(updown, 3)
    r_matrix = Matrix.Rotation(roll, 3, nor)
    return r_matrix @ b_matrix

def mat3_to_vec_roll(mat):
    vec = mat.col[1]
    vecmat = vec_roll_to_mat3(mat.col[1], 0)
    vecmatinv = vecmat.inverted()
    rollmat = vecmatinv @ mat
    roll = math.atan2(rollmat[0][2], rollmat[2][2])
    return vec, roll

# ---------------------------------------------------------------------------
# Blender view helpers
# ---------------------------------------------------------------------------

def view_all_in_3d_view():
    """Focus all 3D viewports on the scene content. Returns True on success."""
    import bpy
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
                            'scene': bpy.context.scene,
                        }
                        with bpy.context.temp_override(**override):
                            bpy.ops.view3d.view_all(center=False)
                        return True
    return False
