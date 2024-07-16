import bpy
import bmesh
import struct
import chunk
from mathutils import Vector, Matrix, Euler
import math
from bpy.props import *

# Log level
IMPORT_LOG_LEVEL = 3

def log(msg):
    if IMPORT_LOG_LEVEL >= 1:
        print(msg)

def vlog(msg):
    if IMPORT_LOG_LEVEL >= 2:
        print(msg)

def dlog(msg):
    if IMPORT_LOG_LEVEL >= 3:
        print(msg)

def err(msg):
    log(f"ERROR: {msg}")

def read_int(honchunk):
    return struct.unpack("<i", honchunk.read(4))[0]

def read_float(honchunk):
    return struct.unpack("<f", honchunk.read(4))[0]

def parse_vertices(honchunk):
    vlog('Parsing vertices chunk')
    numverts = int((honchunk.chunksize - 4) / 12)
    vlog(f'{numverts} vertices')
    meshindex = read_int(honchunk)
    return [struct.unpack("<3f", honchunk.read(12)) for _ in range(numverts)]

def parse_faces(honchunk, version):
    vlog('Parsing faces chunk')
    meshindex = read_int(honchunk)
    numfaces = read_int(honchunk)
    vlog(f'{numfaces} faces')

    if version == 3:
        size = struct.unpack('B', honchunk.read(1))[0]
    elif version == 1:
        size = 4

    if size == 2:
        return [struct.unpack("<3H", honchunk.read(6)) for _ in range(numfaces)]
    elif size == 1:
        return [struct.unpack("<3B", honchunk.read(3)) for _ in range(numfaces)]
    elif size == 4:
        return [struct.unpack("<3I", honchunk.read(12)) for _ in range(numfaces)]
    else:
        log(f"Unknown size for faces: {size}")
        return []

def parse_normals(honchunk):
    vlog('Parsing normals chunk')
    numverts = int((honchunk.chunksize - 4) / 12)
    vlog(f'{numverts} normals')
    meshindex = read_int(honchunk)
    return [struct.unpack("<3f", honchunk.read(12)) for _ in range(numverts)]

def parse_texc(honchunk, version):
    vlog('Parsing UV texc chunk')
    numverts = int((honchunk.chunksize - 4) / 8)
    vlog(f'{numverts} texc')
    meshindex = read_int(honchunk)
    if version == 3:
        vlog(read_int(honchunk))  # huh?
    return [struct.unpack("<2f", honchunk.read(8)) for _ in range(numverts)]

def parse_colr(honchunk):
    vlog('Parsing vertex colors chunk')
    numverts = int((honchunk.chunksize - 4) / 4)
    meshindex = read_int(honchunk)
    return [struct.unpack("<4B", honchunk.read(4)) for _ in range(numverts)]

def parse_links(honchunk, bone_names):
    mesh_index = read_int(honchunk)
    numverts = read_int(honchunk)
    log("Parsing links")
    vlog(f"Mesh index: {mesh_index}")
    vlog(f"Number of vertices: {numverts}")

    vgroups = {}
    for i in range(numverts):
        num_weights = read_int(honchunk)
        if num_weights > 0:
            weights = struct.unpack(f"<{num_weights}f", honchunk.read(num_weights * 4))
            indexes = struct.unpack(f"<{num_weights}I", honchunk.read(num_weights * 4))
        else:
            weights = indexes = []

        for ii, index in enumerate(indexes):
            name = bone_names[index]
            if name not in vgroups:
                vgroups[name] = []
            vgroups[name].append((i, weights[ii]))

    honchunk.skip()
    return vgroups

def parse_sign(honchunk):
    vlog('Parsing sign chunk')
    numverts = honchunk.chunksize - 8
    meshindex = read_int(honchunk)
    vlog(read_int(honchunk))  # huh?
    return [struct.unpack("<b", honchunk.read(1)) for _ in range(numverts)]

def parse_surf(honchunk):
    vlog('Parsing surface chunk')
    surfindex = read_int(honchunk)
    num_planes = read_int(honchunk)
    num_points = read_int(honchunk)
    num_edges = read_int(honchunk)
    num_tris = read_int(honchunk)

    # BMINf, BMAXf, FLAGSi
    honchunk.read(4 * 3 + 4 * 3 + 4)
    return (
        [struct.unpack("<4f", honchunk.read(4 * 4)) for _ in range(num_planes)],
        [struct.unpack("<3f", honchunk.read(4 * 3)) for _ in range(num_points)],
        [struct.unpack("<6f", honchunk.read(4 * 6)) for _ in range(num_edges)],
        [struct.unpack("<3I", honchunk.read(4 * 3)) for _ in range(num_tris)]
    )

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

def create_blender_mesh(filename, objname, flipuv):
    obj = None
    rig = None
    try:
        with open(filename, 'rb') as file:
            sig = file.read(4)
            if sig != b'SMDL':
                err('Unknown file signature')
                return

            honchunk = chunk.Chunk(file, bigendian=False, align=False)
            if honchunk.getname() != b'head':
                log('File does not start with head chunk!')
                return

            version = read_int(honchunk)
            num_meshes = read_int(honchunk)
            num_sprites = read_int(honchunk)
            num_surfs = read_int(honchunk)
            num_bones = read_int(honchunk)

            vlog(f"Version {version}")
            vlog(f"{num_meshes} mesh(es)")
            vlog(f"{num_sprites} sprite(s)")
            vlog(f"{num_surfs} surf(s)")
            vlog(f"{num_bones} bone(s)")
            vlog("Bounding box: (%f, %f, %f) - (%f, %f, %f)" % struct.unpack("<ffffff", honchunk.read(24)))
            honchunk.skip()

            scn = bpy.context.scene

            try:
                honchunk = chunk.Chunk(file, bigendian=False, align=False)
            except EOFError:
                log('Error reading bone chunk')
                return

            # Read bones
            armature_data = bpy.data.armatures.new(f'{objname}_Armature')
            armature_data.display_type = 'STICK'
            armature_data.show_names = True
            rig = bpy.data.objects.new(f'{objname}_Rig', armature_data)
            scn.collection.objects.link(rig)
            bpy.context.view_layer.objects.active = rig
            rig.select_set(True)

            bpy.ops.object.mode_set(mode='EDIT')

            bones = []
            bone_names = []
            parents = []
            for i in range(num_bones):
                parent_bone_index = read_int(honchunk)

                if version == 3:
                    inv_matrix = Matrix([struct.unpack('<3f', honchunk.read(12)) + (0.0,),
                                         struct.unpack('<3f', honchunk.read(12)) + (0.0,),
                                         struct.unpack('<3f', honchunk.read(12)) + (0.0,),
                                         struct.unpack('<3f', honchunk.read(12)) + (1.0,)])
                    matrix = Matrix([struct.unpack('<3f', honchunk.read(12)) + (0.0,),
                                     struct.unpack('<3f', honchunk.read(12)) + (0.0,),
                                     struct.unpack('<3f', honchunk.read(12)) + (0.0,),
                                     struct.unpack('<3f', honchunk.read(12)) + (1.0,)])
                    name_length = struct.unpack("B", honchunk.read(1))[0]
                    name = honchunk.read(name_length).decode()
                    honchunk.read(1)  # zero
                elif version == 1:
                    pos = honchunk.tell() - 4
                    b = honchunk.read(1)
                    name = ''
                    while b != b'\0':
                        name += b.decode()
                        b = honchunk.read(1)
                    honchunk.seek(pos + 0x24)
                    inv_matrix = Matrix([struct.unpack('<4f', honchunk.read(16)),
                                         struct.unpack('<4f', honchunk.read(16)),
                                         struct.unpack('<4f', honchunk.read(16)),
                                         struct.unpack('<4f', honchunk.read(16))])
                    matrix = Matrix([struct.unpack('<4f', honchunk.read(16)),
                                     struct.unpack('<4f', honchunk.read(16)),
                                     struct.unpack('<4f', honchunk.read(16)),
                                     struct.unpack('<4f', honchunk.read(16))])

                log(f"Bone name: {name}, parent {parent_bone_index}")
                bone_names.append(name)
                matrix.transpose()
                matrix = round_matrix(matrix, 4)
                pos = matrix.translation
                axis, roll = mat3_to_vec_roll(matrix.to_3x3())
                bone = armature_data.edit_bones.new(name)
                bone.head = pos
                bone.tail = pos + axis * 0.1  # Adjusted for better visibility
                bone.roll = roll
                parents.append(parent_bone_index)
                bones.append(bone)

            for i in range(num_bones):
                if parents[i] != -1:
                    bones[i].parent = bones[parents[i]]

            honchunk.skip()

            bpy.ops.object.mode_set(mode='OBJECT')
            rig.show_in_front = True
            bpy.context.view_layer.update()

            try:
                honchunk = chunk.Chunk(file, bigendian=False, align=False)
            except EOFError:
                log('Error reading mesh chunk')
                return

            while honchunk and honchunk.getname() in [b'mesh', b'surf']:
                verts = []
                faces = []
                signs = []
                nrml = []
                texc = []
                colors = []
                surf_planes = []
                surf_points = []
                surf_edges = []
                surf_tris = []

                if honchunk.getname() == b'mesh':
                    surf = False
                    vlog(f"Mesh index: {read_int(honchunk)}")
                    mode = 1
                    if version == 3:
                        mode = read_int(honchunk)
                        vlog(f"Mode: {mode}")
                        vlog(f"Vertices count: {read_int(honchunk)}")
                        vlog("Bounding box: (%f, %f, %f) - (%f, %f, %f)" % struct.unpack("<ffffff", honchunk.read(24)))
                        bone_link = read_int(honchunk)
                        vlog(f"Bone link: {bone_link}")
                        sizename = struct.unpack('B', honchunk.read(1))[0]
                        sizemat = struct.unpack('B', honchunk.read(1))[0]
                        meshname = honchunk.read(sizename).decode()
                        honchunk.read(1)  # zero
                        materialname = honchunk.read(sizemat).decode()
                    elif version == 1:
                        bone_link = -1
                        pos = honchunk.tell() - 4
                        b = honchunk.read(1)
                        meshname = ''
                        while b != b'\0':
                            meshname += b.decode()
                            b = honchunk.read(1)
                        honchunk.seek(pos + 0x24)
                        b = honchunk.read(1)
                        materialname = ''
                        while b != b'\0':
                            materialname += b.decode()
                            b = honchunk.read(1)

                    honchunk.skip()

                    while True:
                        try:
                            honchunk = chunk.Chunk(file, bigendian=False, align=False)
                        except EOFError:
                            vlog('Done reading chunks')
                            honchunk = None
                            break
                        if honchunk.getname() in [b'mesh', b'surf']:
                            break
                        elif mode != 1:
                            honchunk.skip()
                        else:
                            if honchunk.getname() == b'vrts':
                                verts = parse_vertices(honchunk)
                            elif honchunk.getname() == b'face':
                                faces = parse_faces(honchunk, version)
                            elif honchunk.getname() == b'nrml':
                                nrml = parse_normals(honchunk)
                            elif honchunk.getname() == b'texc':
                                texc = parse_texc(honchunk, version)
                            elif honchunk.getname() == b'colr':
                                colors = parse_colr(honchunk)
                            elif honchunk.getname() in [b'lnk1', b'lnk3']:
                                vgroups = parse_links(honchunk, bone_names)
                            elif honchunk.getname() == b'sign':
                                signs = parse_sign(honchunk)
                            elif honchunk.getname == b'tang':
                                honchunk.skip()
                            else:
                                vlog(f'Unknown chunk: {honchunk.getname()}')
                                honchunk.skip()
                elif honchunk.getname() == b'surf':
                    surf_planes, surf_points, surf_edges, surf_tris = parse_surf(honchunk)
                    print(surf_planes)
                    print(surf_points)
                    print(surf_edges)
                    print(surf_tris)
                    verts = surf_points
                    faces = surf_tris
                    surf = True
                    meshname = f'{objname}_surf'
                    honchunk.skip()
                    mode = 1
                    try:
                        honchunk = chunk.Chunk(file, bigendian=False, align=False)
                    except EOFError:
                        vlog('Done reading chunks')
                        honchunk = None

                if mode != 1:
                    continue

                msh = bpy.data.meshes.new(name=meshname)
                msh.from_pydata(verts, [], faces)
                msh.update()

                if materialname is not None:
                    msh.materials.append(bpy.data.materials.new(materialname))

                if len(texc) > 0:
                    if flipuv:
                        texc = [(uv[0], 1 - uv[1]) for uv in texc]

                    # Generate texCoords for faces
                    texcoords = [texc[vert_id] for face in faces for vert_id in face]

                    # Create a UV map
                    uv_layer = msh.uv_layers.new(name=f'UVMain{meshname}')
                    for face in msh.polygons:
                        for vert_idx, loop_idx in zip(face.vertices, face.loop_indices):
                            uv_layer.data[loop_idx].uv = texc[vert_idx]

                obj = bpy.data.objects.new(f'{meshname}_Object', msh)
                # Link object to scene
                scn.collection.objects.link(obj)
                bpy.context.view_layer.objects.active = obj
                bpy.context.view_layer.update()

                if surf or mode != 1:
                    obj.display_type = 'WIRE'
                else:
                    # Vertex groups
                    if bone_link >= 0:
                        grp = obj.vertex_groups.new(name=bone_names[bone_link])
                        grp.add(list(range(len(msh.vertices))), 1.0, 'REPLACE')
                    for name, vg in vgroups.items():
                        grp = obj.vertex_groups.new(name=name)
                        for v, w in vg:
                            grp.add([v], w, 'REPLACE')

                    mod = obj.modifiers.new(name='MyRigModif', type='ARMATURE')
                    mod.object = rig
                    mod.use_bone_envelopes = False
                    mod.use_vertex_groups = True

                    bpy.context.view_layer.objects.active = rig
                    rig.select_set(True)
                    bpy.ops.object.mode_set(mode='POSE')
                    pose = rig.pose
                    for b in pose.bones:
                        b.rotation_mode = 'QUATERNION'
                    bpy.ops.object.mode_set(mode='OBJECT')
                    rig.select_set(False)
                bpy.context.view_layer.objects.active = None

            bpy.context.view_layer.update()

            view_all_in_3d_view()

    except IOError as e:
        log(f"File IO Error: {e}")
    except Exception as e:
        log(f"Unexpected error: {e}")

    return obj, rig  # Ensure obj and rig are defined before returning

def view_all_in_3d_view():
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

##############################
# CLIPS
##############################

MKEY_X, MKEY_Y, MKEY_Z, MKEY_PITCH, MKEY_ROLL, MKEY_YAW, MKEY_VISIBILITY, MKEY_SCALE_X, MKEY_SCALE_Y, MKEY_SCALE_Z = range(10)

def bone_depth(bone):
    if not bone.parent:
        return 0
    else:
        return 1 + bone_depth(bone.parent)

def get_transform_matrix(motions, bone, i, version):
    motion = motions[bone.name]
    # Translation
    x = motion[MKEY_X][i] if i < len(motion[MKEY_X]) else motion[MKEY_X][-1]
    y = motion[MKEY_Y][i] if i < len(motion[MKEY_Y]) else motion[MKEY_Y][-1]
    z = motion[MKEY_Z][i] if i < len(motion[MKEY_Z]) else motion[MKEY_Z][-1]

    # Rotation
    rx = motion[MKEY_PITCH][i] if i < len(motion[MKEY_PITCH]) else motion[MKEY_PITCH][-1]
    ry = motion[MKEY_ROLL][i] if i < len(motion[MKEY_ROLL]) else motion[MKEY_ROLL][-1]
    rz = motion[MKEY_YAW][i] if i < len(motion[MKEY_YAW]) else motion[MKEY_YAW][-1]

    # Scaling
    if version == 1:
        sx = motion[MKEY_SCALE_X][i] if i < len(motion[MKEY_SCALE_X]) else motion[MKEY_SCALE_X][-1]
        sy = sz = sx
    else:
        sx = motion[MKEY_SCALE_X][i] if i < len(motion[MKEY_SCALE_X]) else motion[MKEY_SCALE_X][-1]
        sy = motion[MKEY_SCALE_Y][i] if i < len(motion[MKEY_SCALE_Y]) else motion[MKEY_SCALE_Y][-1]
        sz = motion[MKEY_SCALE_Z][i] if i < len(motion[MKEY_SCALE_Z]) else motion[MKEY_SCALE_Z][-1]

    scale = Vector([sx, sy, sz])
    bone_rotation_matrix = Euler((math.radians(rx), math.radians(ry), math.radians(rz)), 'YXZ').to_matrix().to_4x4()
    bone_rotation_matrix = Matrix.Translation(Vector((x, y, z))) @ bone_rotation_matrix

    return bone_rotation_matrix, scale

def animate_bone(name, pose, motions, num_frames, armature, arm_ob, version):
    if name not in armature.bones.keys():
        log(f'{name} not found in armature')
        return

    motion = motions[name]
    bone = armature.bones[name]
    bone_rest_matrix = Matrix(bone.matrix_local)

    if bone.parent is not None:
        parent_bone = bone.parent
        parent_rest_bone_matrix = Matrix(parent_bone.matrix_local)
        parent_rest_bone_matrix.invert()
        bone_rest_matrix = parent_rest_bone_matrix @ bone_rest_matrix

    bone_rest_matrix_inv = Matrix(bone_rest_matrix).inverted()

    pbone = pose.bones[name]
    for i in range(num_frames):
        transform, size = get_transform_matrix(motions, bone, i, version)
        transform = bone_rest_matrix_inv @ transform
        pbone.rotation_quaternion = transform.to_quaternion()
        pbone.location = transform.to_translation()
        pbone.keyframe_insert(data_path='rotation_quaternion', frame=i)
        pbone.keyframe_insert(data_path='location', frame=i)

def create_blender_clip(filename, clipname):
    try:
        with open(filename, 'rb') as file:
            sig = file.read(4)
            if sig != b'CLIP':
                err('Unknown file signature')
                return

            clipchunk = chunk.Chunk(file, bigendian=False, align=False)
            version = read_int(clipchunk)
            num_bones = read_int(clipchunk)
            num_frames = read_int(clipchunk)
            vlog(f"Version: {version}")
            vlog(f"Number of bones: {num_bones}")
            vlog(f"Number of frames: {num_frames}")

            if not bpy.context.selected_objects:
                err('No object selected')
                return

            arm_ob = bpy.context.selected_objects[0]
            if not arm_ob.animation_data:
                arm_ob.animation_data_create()
            armature = arm_ob.data
            action = bpy.data.actions.new(name=clipname)
            arm_ob.animation_data.action = action
            pose = arm_ob.pose

            motions = {}

            while True:
                try:
                    clipchunk = chunk.Chunk(file, bigendian=False, align=False)
                except EOFError:
                    break

                if version == 1:
                    name = clipchunk.read(32).split(b'\0', 1)[0]
                boneindex = read_int(clipchunk)
                keytype = read_int(clipchunk)
                numkeys = read_int(clipchunk)
                if version > 1:
                    namelength = struct.unpack("B", clipchunk.read(1))[0]
                    name = clipchunk.read(namelength)
                    clipchunk.read(1)
                name = name.decode("utf8")

                if name not in motions:
                    motions[name] = {}
                dlog(f"{name}, bone index: {boneindex}, key type: {keytype}, number of keys: {numkeys}")
                if keytype == MKEY_VISIBILITY:
                    data = struct.unpack(f"{numkeys}B", clipchunk.read(numkeys))
                else:
                    data = struct.unpack(f"<{numkeys}f", clipchunk.read(numkeys * 4))
                motions[name][keytype] = list(data)
                clipchunk.skip()

            # File read, now animate
            for bone_name in motions:
                animate_bone(bone_name, pose, motions, num_frames, armature, arm_ob, version)

    except IOError as e:
        log(f"File IO Error: {e}")

def readclip(filepath):
    obj_name = bpy.path.display_name_from_filepath(filepath)
    create_blender_clip(filepath, obj_name)

def read(filepath, flipuv):
    obj_name = bpy.path.display_name_from_filepath(filepath)
    create_blender_mesh(filepath, obj_name, flipuv)
