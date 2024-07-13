import bpy
import bmesh
from io import BytesIO
import struct
import os
from math import degrees
from mathutils import Matrix

# Determines the verbosity of logging.
IMPORT_LOG_LEVEL = 0

# Keyframe types
MKEY_X, MKEY_Y, MKEY_Z, MKEY_PITCH, MKEY_ROLL, MKEY_YAW, MKEY_VISIBILITY, MKEY_SCALE_X, MKEY_SCALE_Y, MKEY_SCALE_Z, MKEY_COUNT = range(11)

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
    log(msg)

def bone_depth(bone):
    if not bone.parent:
        return 0
    else:
        return 1 + bone_depth(bone.parent)

def generate_bbox(meshes):
    xx = []
    yy = []
    zz = []
    for mesh in meshes:
        nv = [v.co for v in mesh.verts]
        xx += [co[0] for co in nv]
        yy += [co[1] for co in nv]
        zz += [co[2] for co in nv]
    return [min(xx), min(yy), min(zz), max(xx), max(yy), max(zz)]

def create_mesh_data(mesh, vert, index, name, mname):
    meshdata = BytesIO()
    meshdata.write(struct.pack("<i", index))
    meshdata.write(struct.pack("<i", 1)) # mode? huh? dunno...
    meshdata.write(struct.pack("<i", len(vert))) # vertices count
    meshdata.write(struct.pack("<6f", *generate_bbox([mesh]))) # bounding box
    meshdata.write(struct.pack("<i", -1)) # bone link... dunno... TODO
    meshdata.write(struct.pack("<B", len(name))) 
    meshdata.write(struct.pack("<B", len(mname))) 
    meshdata.write(name)
    meshdata.write(struct.pack("<B", 0)) 
    meshdata.write(mname)
    meshdata.write(struct.pack("<B", 0)) 
    return meshdata.getvalue()

def create_vrts_data(verts, meshindex):
    data = BytesIO()
    data.write(struct.pack("<i", meshindex))
    for v in verts:
        data.write(struct.pack("<3f", *v.co))
    return data.getvalue()

def create_face_data(verts, faces, meshindex):
    data = BytesIO()
    data.write(struct.pack("<i", meshindex))
    data.write(struct.pack("<i", len(faces)))
    if len(verts) < 255:
        data.write(struct.pack("<B", 1))
        str = '<3B'
    else:
        data.write(struct.pack("<B", 2))
        str = '<3H'
    for f in faces:
        data.write(struct.pack(str, *f))
    return data.getvalue()

def create_tang_data(tang, meshindex):
    data = BytesIO()
    data.write(struct.pack("<i", meshindex))
    data.write(struct.pack("<i", 0)) # huh?
    for t in tang:
        data.write(struct.pack('<3f', *list(t)))
    return data.getvalue()

def write_block(file, name, data):
    file.write(name.encode('utf8')[:4])
    file.write(struct.pack("<i", len(data)))
    file.write(data)

def create_texc_data(texc, meshindex):
    for i in range(len(texc)):
        texc[i] = [texc[i][0], 1.0 - texc[i][1]]
    data = BytesIO()
    data.write(struct.pack("<i", meshindex))
    data.write(struct.pack("<i", 0)) # huh?
    for t in texc:
        data.write(struct.pack("<2f", *t))
    return data.getvalue()

def create_colr_data(colr, meshindex):
    data = BytesIO()
    data.write(struct.pack("<i", meshindex))
    for c in colr:
        data.write(struct.pack("<4B", c.r, c.g, c.b, c.a))
    return data.getvalue()

def create_nrml_data(verts, meshindex):
    data = BytesIO()
    data.write(struct.pack("<i", meshindex))
    for v in verts:
        data.write(struct.pack("<3f", *v.normal))
    return data.getvalue()

def create_lnk1_data(lnk1, meshindex, bone_indices):
    data = BytesIO()
    data.write(struct.pack("<i", meshindex))
    data.write(struct.pack("<i", len(lnk1)))
    for influences in lnk1:
        influences = [inf for inf in influences if inf[0] in bone_indices]
        l = len(influences)
        data.write(struct.pack("<i", l))
        if l > 0:
            data.write(struct.pack('<%df' % l, *[inf[1] for inf in influences]))
            data.write(struct.pack('<%dI' % l, *[bone_indices[inf[0]] for inf in influences]))
    return data.getvalue()

def create_sign_data(meshindex, sign):
    data = BytesIO()
    data.write(struct.pack("<i", meshindex))
    data.write(struct.pack("<i", 0))
    for s in sign:
        data.write(struct.pack("<b", s))
    return data.getvalue()

def calcFaceSigns(ftexc):
    fsigns = []
    for uv in ftexc:
        if ((uv[1][0] - uv[0][0]) * (uv[2][1] - uv[1][1]) - (uv[1][1] - uv[0][1]) * (uv[2][0] - uv[1][0])) > 0:
            fsigns.append((0, 0, 0))
        else:
            fsigns.append((-1, -1, -1))
    return fsigns

def face_to_vertices_dup(faces, fdata, verts):
    vdata = [None] * len(verts)
    for fi, f in enumerate(faces):
        for vi, v in enumerate(f):
            if vdata[v] is None or vdata[v] == fdata[fi][vi]:
                vdata[v] = fdata[fi][vi]
            else:
                newind = len(verts)
                verts.append(verts[v])
                faces[fi][vi] = newind
                vdata.append(fdata[fi][vi])
    return vdata

def face_to_vertices(faces, fdata, verts):
    vdata = [None] * len(verts)
    for fi, f in enumerate(faces):
        for vi, v in enumerate(f):
            vdata[v] = fdata[fi][vi]
    return vdata

def create_bone_data(armature, armMatrix, transform):
    bones = []
    for bone in sorted(armature.bones.values(), key=bone_depth):
        bones.append(bone.name)
    bonedata = BytesIO()
    for name in bones:
        bone = armature.bones[name]
        base = bone.matrix_local.copy()
        if transform:
            base = base @ armMatrix
        baseInv = base.copy()
        baseInv.invert()
        if bone.parent:
            parent_index = bones.index(bone.parent.name)
        else:
            parent_index = -1
        baseInv.transpose()
        base.transpose()
        bonedata.write(struct.pack("<i", parent_index))
        bonedata.write(struct.pack('<12f', *sum([list(row[0:3]) for row in baseInv], [])))
        bonedata.write(struct.pack('<12f', *sum([list(row[0:3]) for row in base], [])))
        name = name.encode('utf8')
        bonedata.write(struct.pack("B", len(name)))
        bonedata.write(name)
        bonedata.write(struct.pack("B", 0))
    return bones, bonedata.getvalue()

def select_armature_and_mesh():
    # Ensure the operator is called in the correct context
    view_layer = bpy.context.view_layer
    view_layer.objects.active = None

    bpy.ops.object.select_all(action='DESELECT')
    
    armatures_found = False
    meshes_found = False
    
    for obj in bpy.data.objects:
        if obj.type == 'ARMATURE':
            obj.select_set(True)
            armatures_found = True
        if obj.type == 'MESH':
            obj.select_set(True)
            meshes_found = True
    
    if not armatures_found:
        print("No armature objects found in the scene.")
    if not meshes_found:
        print("No mesh objects found in the scene.")

def select_armature():
    # Ensure the operator is called in the correct context
    view_layer = bpy.context.view_layer
    view_layer.objects.active = None

    bpy.ops.object.select_all(action='DESELECT')

    armatures_found = False

    for obj in bpy.data.objects:
        if obj.type == 'ARMATURE':
            obj.select_set(True)
            armatures_found = True

    if not armatures_found:
        print("No armature objects found in the scene.")

def export_k2_mesh(filename, applyMods):
    select_armature_and_mesh()
    
    meshes = []
    armature = None
    for obj in bpy.context.selected_objects:
        if obj.type == 'MESH':
            matrix = obj.matrix_world
            if applyMods:
                depsgraph = bpy.context.evaluated_depsgraph_get()
                me = obj.evaluated_get(depsgraph).to_mesh()
            else:
                me = obj.data
            bm = bmesh.new()
            bm.from_mesh(me)
            me = bm
            me.transform(matrix)
            meshes.append((obj, me))
        elif obj.type == 'ARMATURE':
            armature = obj.data
            armMatrix = obj.matrix_world
    if armature:
        armature.pose_position = 'REST'
        bone_indices, bonedata = create_bone_data(armature, armMatrix, applyMods)
    headdata = BytesIO()
    headdata.write(struct.pack("<i", 3))
    headdata.write(struct.pack("<i", len(meshes)))
    headdata.write(struct.pack("<i", 0))
    headdata.write(struct.pack("<i", 0))
    if armature:
        headdata.write(struct.pack("<i", len(armature.bones.values())))
    else:
        headdata.write(struct.pack("<i", 0))
    headdata.write(struct.pack("<6f", *generate_bbox([x for _, x in meshes])))
    meshindex = 0
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    file = open(filename, 'wb')
    file.write(b'SMDL')
    write_block(file, 'head', headdata.getvalue())
    write_block(file, 'bone', bonedata)
    
    for obj, mesh in meshes:
        vert = [vert for vert in mesh.verts]
        faces = []
        ftexc = []
        ftang = []
        fcolr = []
        flnk1 = []
        uv_lay = mesh.loops.layers.uv.active
        if not uv_lay:
            ftexc = None
        col_lay = mesh.loops.layers.color.active
        if not col_lay:
            fcolr = None
        dvert_lay = mesh.verts.layers.deform.active
        if dvert_lay:
            flnk1 = [vert[dvert_lay].items() for vert in mesh.verts]
        for f in mesh.faces:
            uv = []
            col = []
            vindex = []
            tang = []
            for loop in f.loops:
                if ftexc is not None:
                    uv.append(loop[uv_lay].uv)
                vindex.append(loop.vert.index)
                if fcolr is not None:
                    col.append(loop[col_lay].color)
                tang.append(loop.calc_tangent())
            if ftexc is not None:
                ftexc.append(uv)
            ftang.append(tang)
            faces.append(vindex)
            if fcolr:
                fcolr.append(col)
        if ftexc:
            fsign = calcFaceSigns(ftexc)
            sign = face_to_vertices(faces, fsign, vert)
            texc = face_to_vertices(faces, ftexc, vert)
            tang = face_to_vertices(faces, ftang, vert)
        for i in range(len(vert)):
            tang[i] = (tang[i] - vert[i].normal * tang[i].dot(vert[i].normal))
            tang[i].normalize()
        lnk1 = flnk1
        if fcolr is not None:
            colr = face_to_vertices(faces, fcolr, vert)
        else:
            colr = None
        write_block(file, 'mesh', create_mesh_data(mesh, vert, meshindex, obj.name.encode('utf8'), obj.data.materials[0].name.encode('utf8')))
        write_block(file, 'vrts', create_vrts_data(vert, meshindex))
        new_indices = {}
        for group in obj.vertex_groups:
            new_indices[group.index] = bone_indices.index(group.name)
        write_block(file, 'lnk1', create_lnk1_data(lnk1, meshindex, new_indices))
        if len(faces) > 0:
            write_block(file, 'face', create_face_data(vert, faces, meshindex))
            if ftexc is not None:
                write_block(file, "texc", create_texc_data(texc, meshindex))
                for i in range(len(tang)):
                    if sign[i] == 0:
                        tang[i] = -(tang[i].copy())
                write_block(file, "tang", create_tang_data(tang, meshindex))
                write_block(file, "sign", create_sign_data(meshindex, sign))
            write_block(file, "nrml", create_nrml_data(vert, meshindex))
        if fcolr is not None:
            write_block(file, "colr", create_colr_data(colr, meshindex))
        
        meshindex += 1
        vlog('total vertices duplicated: %d' % (len(vert) - len(mesh.verts)))

def export_k2_clip(filename, transform, frame_start, frame_end):
    select_armature()
    
    objList = bpy.context.selected_objects
    
    if len(objList) != 1 or objList[0].type != 'ARMATURE':
        err('Select needed armature only')
        return
    
    armob = objList[0]
    print(armob)
    
    motions = {}
    vlog('baking animation')
    
    armature = armob.data
    
    if transform:
        worldmat = armob.matrix_world
    else:
        worldmat = Matrix([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
    
    scene = bpy.context.scene
    pose = armob.pose
    
    for frame in range(frame_start, frame_end + 1):
        scene.frame_set(frame)
        
        for bone in pose.bones:
            matrix = bone.matrix
            if bone.parent:
                matrix = bone.parent.matrix.inverted() @ matrix
            if transform:
                matrix = worldmat @ matrix
            
            if bone.name not in motions:
                motions[bone.name] = [[] for _ in range(MKEY_COUNT)]
            
            motion = motions[bone.name]
            translation = matrix.to_translation()
            rotation = matrix.to_euler('YXZ')
            scale = matrix.to_scale()
            visibility = 255
            motion[MKEY_X].append(translation[0])
            motion[MKEY_Y].append(translation[1])
            motion[MKEY_Z].append(translation[2])
            motion[MKEY_PITCH].append(degrees(rotation[0]))  # Changed sign to correct flipped animation
            motion[MKEY_ROLL].append(degrees(rotation[1]))  # Changed sign to correct flipped animation
            motion[MKEY_YAW].append(degrees(rotation[2]))  # Changed sign to correct flipped animation
            motion[MKEY_SCALE_X].append(scale[0])
            motion[MKEY_SCALE_Y].append(scale[1])
            motion[MKEY_SCALE_Z].append(scale[2])
            motion[MKEY_VISIBILITY].append(visibility)
    
    headdata = BytesIO()
    headdata.write(struct.pack("<i", 2))
    headdata.write(struct.pack("<i", len(motions.keys())))
    headdata.write(struct.pack("<i", frame_end - frame_start + 1))
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    file = open(filename, 'wb')
    file.write(b'CLIP')
    write_block(file, 'head', headdata.getvalue())
    
    index = 0
    
    for bone_name in sorted(armature.bones.keys(), key=lambda x: bone_depth(armature.bones[x])):
        ClipBone(file, bone_name.encode('utf8'), motions[bone_name], index)
        index += 1
    
    file.close()

def ClipBone(file, bone_name, motion, index):
    for keytype in range(MKEY_COUNT):
        keydata = BytesIO()
        key = motion[keytype]
        if min(key) == max(key):
            key = [key[0]]
        numkeys = len(key)
        keydata.write(struct.pack("<i", index))
        keydata.write(struct.pack("<i", keytype))
        keydata.write(struct.pack("<i", numkeys))
        keydata.write(struct.pack("B", len(bone_name)))
        keydata.write(bone_name)
        keydata.write(struct.pack("B", 0))
        if keytype == MKEY_VISIBILITY:
            keydata.write(struct.pack('%dB' % numkeys, *key))
        else:
            keydata.write(struct.pack('<%df' % numkeys, *key))
        write_block(file, 'bmtn', keydata.getvalue())


