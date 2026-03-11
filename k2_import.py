"""
K2 engine model (.model) and animation clip (.clip) importer for Blender.
Supports SMDL v1/v3 meshes and CLIP v1/v2+ animations.
"""

import bpy
import struct
import chunk
import math
from mathutils import Vector, Matrix, Euler

from .k2_common import (
    log, vlog, dlog, err,
    read_int, read_float,
    bone_depth,
    round_vector, round_matrix,
    vec_roll_to_mat3, mat3_to_vec_roll,
    view_all_in_3d_view,
    MKEY_X, MKEY_Y, MKEY_Z,
    MKEY_PITCH, MKEY_ROLL, MKEY_YAW,
    MKEY_SCALE_X, MKEY_SCALE_Y, MKEY_SCALE_Z,
    MKEY_VISIBILITY,
)

# ============================================================================
# Chunk parsers — each reads one chunk type from the binary stream
# ============================================================================

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


def parse_vertices(honchunk):
    vlog('Parsing vertices chunk')
    numverts = int((honchunk.chunksize - 4) / 12)
    vlog(f'{numverts} vertices')
    meshindex = read_int(honchunk)
    return [struct.unpack("<3f", honchunk.read(12)) for _ in range(numverts)]


def parse_sign(honchunk):
    vlog('Parsing sign chunk')
    numverts = honchunk.chunksize - 8
    meshindex = read_int(honchunk)
    read_int(honchunk)  # padding / unknown field
    return [struct.unpack("<b", honchunk.read(1)) for _ in range(numverts)]


def parse_faces(honchunk, version):
    vlog('Parsing faces chunk')
    meshindex = read_int(honchunk)
    numfaces = read_int(honchunk)
    vlog(f'{numfaces} faces')

    if version == 3:
        size = struct.unpack('B', honchunk.read(1))[0]
    elif version == 1:
        size = 4

    fmt_map = {1: ("<3B", 3), 2: ("<3H", 6), 4: ("<3I", 12)}
    if size in fmt_map:
        fmt, nbytes = fmt_map[size]
        return [struct.unpack(fmt, honchunk.read(nbytes)) for _ in range(numfaces)]

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
    meshindex = read_int(honchunk)
    uv_channel = 0
    if version == 3:
        uv_channel = read_int(honchunk)
        numverts = (honchunk.chunksize - 8) // 8
    else:
        numverts = (honchunk.chunksize - 4) // 8
    vlog(f'{numverts} texc (channel {uv_channel})')
    uvs = [struct.unpack("<2f", honchunk.read(8)) for _ in range(numverts)]
    return uv_channel, uvs


def parse_colr(honchunk):
    vlog('Parsing vertex colors chunk')
    numverts = int((honchunk.chunksize - 4) / 4)
    meshindex = read_int(honchunk)
    return [struct.unpack("<4B", honchunk.read(4)) for _ in range(numverts)]


def parse_surf(honchunk):
    vlog('Parsing surface chunk')
    surfindex = read_int(honchunk)
    num_planes = read_int(honchunk)
    num_points = read_int(honchunk)
    num_edges = read_int(honchunk)
    num_tris = read_int(honchunk)

    # BMIN(3f), BMAX(3f), FLAGS(i)
    honchunk.read(4 * 3 + 4 * 3 + 4)
    return (
        [struct.unpack("<4f", honchunk.read(4 * 4)) for _ in range(num_planes)],
        [struct.unpack("<3f", honchunk.read(4 * 3)) for _ in range(num_points)],
        [struct.unpack("<6f", honchunk.read(4 * 6)) for _ in range(num_edges)],
        [struct.unpack("<3I", honchunk.read(4 * 3)) for _ in range(num_tris)],
    )


# ============================================================================
# Sub-chunk dispatcher — reads child chunks inside a mesh block
# ============================================================================

def _read_mesh_subchunks(file, version, bone_names):
    """Read all sub-chunks that follow a 'mesh' chunk until the next mesh/surf or EOF."""
    verts = []
    faces = []
    signs = []
    nrml = []
    texc = []
    colors = []
    vgroups = {}
    honchunk = None

    while True:
        try:
            honchunk = chunk.Chunk(file, bigendian=False, align=False)
        except EOFError:
            vlog('Done reading chunks')
            return verts, faces, signs, nrml, texc, colors, vgroups, None

        name = honchunk.getname()
        if name in (b'mesh', b'surf'):
            return verts, faces, signs, nrml, texc, colors, vgroups, honchunk

        if name == b'vrts':
            verts = parse_vertices(honchunk)
        elif name == b'face':
            faces = parse_faces(honchunk, version)
        elif name == b'nrml':
            nrml = parse_normals(honchunk)
        elif name == b'texc':
            channel, uvs = parse_texc(honchunk, version)
            if channel == 0 or not texc:
                texc = uvs
            else:
                vlog(f'Skipping UV channel {channel} (using channel 0)')
        elif name == b'colr':
            colors = parse_colr(honchunk)
        elif name in (b'lnk1', b'lnk3'):
            vgroups = parse_links(honchunk, bone_names)
        elif name == b'sign':
            signs = parse_sign(honchunk)
        else:
            vlog(f'Skipping chunk: {name}')

        honchunk.skip()


# ============================================================================
# Bone reading
# ============================================================================

def _read_bone_v3(honchunk):
    """Read a single bone entry in SMDL version 3 format."""
    parent_index = read_int(honchunk)
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
    honchunk.read(1)  # null terminator
    return parent_index, name, matrix


def _read_bone_v1(honchunk):
    """Read a single bone entry in SMDL version 1 format."""
    parent_index = read_int(honchunk)
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
    return parent_index, name, matrix


def _read_bones(honchunk, num_bones, version, armature_data):
    """Read all bones, create edit bones, and return bone_names + parent indices."""
    bones = []
    bone_names = []
    parents = []

    for _ in range(num_bones):
        if version == 3:
            parent_index, name, matrix = _read_bone_v3(honchunk)
        elif version == 1:
            parent_index, name, matrix = _read_bone_v1(honchunk)
        else:
            err(f"Unsupported version {version}")
            return [], [], []

        log(f"Bone name: {name}, parent {parent_index}")
        bone_names.append(name)

        matrix.transpose()
        matrix = round_matrix(matrix, 4)
        pos = matrix.translation
        axis, roll = mat3_to_vec_roll(matrix.to_3x3())

        bone = armature_data.edit_bones.new(name)
        bone.head = pos
        bone.tail = pos + axis
        bone.roll = roll
        parents.append(parent_index)
        bones.append(bone)

    for i in range(num_bones):
        if parents[i] != -1:
            bones[i].parent = bones[parents[i]]

    honchunk.skip()
    return bones, bone_names, parents


# ============================================================================
# Mesh header reading
# ============================================================================

def _read_mesh_header_v3(honchunk):
    """Read mesh header fields for SMDL v3."""
    mode = read_int(honchunk)
    vlog(f"Mode: {mode}")
    vlog(f"Vertices count: {read_int(honchunk)}")
    vlog("Bounding box: (%f, %f, %f) - (%f, %f, %f)" % struct.unpack("<ffffff", honchunk.read(24)))
    bone_link = read_int(honchunk)
    vlog(f"Bone link: {bone_link}")
    sizename = struct.unpack('B', honchunk.read(1))[0]
    sizemat = struct.unpack('B', honchunk.read(1))[0]
    meshname = honchunk.read(sizename).decode().rstrip('\x00')
    honchunk.read(1)  # null terminator
    materialname = honchunk.read(sizemat).decode().rstrip('\x00')
    return mode, bone_link, meshname, materialname


def _read_mesh_header_v1(honchunk):
    """Read mesh header fields for SMDL v1."""
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
    return 1, -1, meshname, materialname


# ============================================================================
# Texture auto-detection and material setup
# ============================================================================

import os
import glob as _glob

_TEX_KEYWORDS = {
    'color2':   ['_color2', '_diff2', '_team', '_tint'],
    'color3':   ['_color3', '_diff3', '_detail', '_spec', '_specular'],
    'color':    ['_color', '_diff', '_diffuse', '_albedo'],
    'normal':   ['_normal', '_nrm', '_norm'],
    'mrao':     ['_mrao', '_orm'],
    'emissive': ['_emissive', '_emis', '_glow', '_self'],
}
_EXT_PRIORITY = ['.tga', '.png', '.jpg', '.jpeg', '.bmp', '.tif', '.dds']
_TEX_EXTENSIONS = set(_EXT_PRIORITY)

_dir_cache = {}


def _scan_texture_dir(base_dir):
    """Scan a directory and build {prefix: {type: filepath}} preferring .tga over .dds."""
    if base_dir in _dir_cache:
        return _dir_cache[base_dir]

    result = {}
    try:
        files = os.listdir(base_dir)
    except OSError:
        _dir_cache[base_dir] = result
        return result

    for f in files:
        name_lower = f.lower()
        stem, ext = os.path.splitext(name_lower)
        if ext not in _TEX_EXTENSIONS:
            continue

        matched_type = None
        prefix = stem
        for tex_type, keywords in _TEX_KEYWORDS.items():
            for kw in keywords:
                pos = stem.find(kw)
                if pos > 0:
                    matched_type = tex_type
                    prefix = stem[:pos]
                    break
            if matched_type:
                break

        if not matched_type:
            matched_type = 'color'
            prefix = stem

        if prefix not in result:
            result[prefix] = {}
        existing = result[prefix].get(matched_type)
        if existing:
            _, old_ext = os.path.splitext(existing.lower())
            old_pri = _EXT_PRIORITY.index(old_ext) if old_ext in _EXT_PRIORITY else 99
            new_pri = _EXT_PRIORITY.index(ext) if ext in _EXT_PRIORITY else 99
            if new_pri >= old_pri:
                continue
        result[prefix][matched_type] = os.path.join(base_dir, f)

    _dir_cache[base_dir] = result
    return result


def _match_prefix(tex_map, mat_name):
    """Find the best matching texture prefix for a material name."""
    mat_lower = mat_name.lower()
    mat_base = mat_lower.rsplit('/', 1)[-1].rsplit('\\', 1)[-1]
    # Strip trailing .001 etc from Blender material duplicates
    if '.' in mat_base:
        parts = mat_base.rsplit('.', 1)
        if parts[1].isdigit():
            mat_base = parts[0]

    if mat_base in tex_map:
        return mat_base

    for prefix in tex_map:
        if prefix.startswith(mat_base) or mat_base.startswith(prefix):
            return prefix

    for prefix in tex_map:
        if mat_base in prefix or prefix in mat_base:
            return prefix

    return None


def _find_texture(base_dir, mat_name, tex_type):
    """Find a texture file in base_dir matching the material name and texture type."""
    tex_map = _scan_texture_dir(base_dir)
    prefix = _match_prefix(tex_map, mat_name)
    if prefix and tex_type in tex_map[prefix]:
        path = tex_map[prefix][tex_type]
        vlog(f"    Found {tex_type}: {os.path.basename(path)} (prefix='{prefix}')")
        return path
    return None


def assign_textures_to_objects(objects, tex_dir, tex_flags):
    """
    Smart texture assignment: match by material name first,
    then fall back to auto-assigning texture groups by order.
    Returns number of materials that got textures.
    """
    _dir_cache.pop(tex_dir, None)
    tex_map = _scan_texture_dir(tex_dir)
    if not tex_map:
        log(f"No texture files found in {tex_dir}")
        return 0

    prefixes = sorted(tex_map.keys())
    log(f"Texture groups found: {prefixes}")

    materials = []
    for obj in objects:
        if obj.type != 'MESH' or not obj.data.materials:
            continue
        for mat in obj.data.materials:
            if mat and mat not in materials:
                materials.append(mat)

    if not materials:
        log("No materials on selected objects")
        return 0

    log(f"Materials to assign: {[m.name for m in materials]}")

    assignments = {}
    used_prefixes = set()
    for mat in materials:
        prefix = _match_prefix(tex_map, mat.name)
        if prefix:
            assignments[mat.name] = prefix
            used_prefixes.add(prefix)
            log(f"  '{mat.name}' -> '{prefix}' (name match)")

    unmatched_mats = [m for m in materials if m.name not in assignments]
    remaining_prefixes = [p for p in prefixes if p not in used_prefixes]

    if unmatched_mats and remaining_prefixes:
        for mat, prefix in zip(unmatched_mats, remaining_prefixes):
            assignments[mat.name] = prefix
            log(f"  '{mat.name}' -> '{prefix}' (auto-assigned)")

    count = 0
    for mat in materials:
        prefix = assignments.get(mat.name)
        if not prefix:
            log(f"  '{mat.name}' -> no texture group available")
            continue
        if _setup_material_from_prefix(mat, tex_map[prefix], tex_flags):
            count += 1

    return count


def _create_image_node(tree, image_path, label, x_pos, y_pos):
    """Create an image texture node and compensate for Blender's upside-down DDS sampling."""
    tex = tree.nodes.new('ShaderNodeTexImage')
    tex.location = (x_pos, y_pos)
    tex.label = label
    tex.image = bpy.data.images.load(image_path, check_existing=True)

    # Blender displays some DDS textures vertically flipped compared to TGA assets.
    # Apply a per-node mapping correction so mesh UVs stay untouched.
    if os.path.splitext(image_path)[1].lower() == '.dds':
        texcoord = tree.nodes.new('ShaderNodeTexCoord')
        texcoord.location = (x_pos - 600, y_pos)
        mapping = tree.nodes.new('ShaderNodeMapping')
        mapping.location = (x_pos - 320, y_pos)
        mapping.inputs['Location'].default_value[1] = 1.0
        mapping.inputs['Scale'].default_value[1] = -1.0
        tree.links.new(texcoord.outputs['UV'], mapping.inputs['Vector'])
        tree.links.new(mapping.outputs['Vector'], tex.inputs['Vector'])

    return tex


def _setup_material_from_prefix(mat, type_map, tex_flags):
    """Set up Principled BSDF for a material using a pre-resolved texture type map."""
    if tex_flags is None or tex_flags is True:
        tex_flags = {k: True for k in _TEX_KEYWORDS}
    if not any(tex_flags.values()):
        return False

    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()

    output = tree.nodes.new('ShaderNodeOutputMaterial')
    output.location = (600, 0)
    bsdf = tree.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.location = (200, 0)
    tree.links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

    x_off = -600
    y = 400
    loaded = False

    if tex_flags.get('color') and 'color' in type_map:
        tex = _create_image_node(tree, type_map['color'], "Color", x_off, y)
        tree.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
        tree.links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])
        y -= 300
        loaded = True

    for ckey, clabel in [('color2', 'Color 2'), ('color3', 'Color 3')]:
        if tex_flags.get(ckey) and ckey in type_map:
            tex = _create_image_node(tree, type_map[ckey], clabel, x_off, y)
            y -= 300
            loaded = True

    if tex_flags.get('normal') and 'normal' in type_map:
        tex = _create_image_node(tree, type_map['normal'], "Normal", x_off, y)
        tex.image.colorspace_settings.name = 'Non-Color'
        nmap = tree.nodes.new('ShaderNodeNormalMap')
        nmap.location = (x_off + 300, y)
        tree.links.new(tex.outputs['Color'], nmap.inputs['Color'])
        tree.links.new(nmap.outputs['Normal'], bsdf.inputs['Normal'])
        y -= 300
        loaded = True

    if tex_flags.get('mrao') and 'mrao' in type_map:
        tex = _create_image_node(tree, type_map['mrao'], "MRAO", x_off, y)
        tex.image.colorspace_settings.name = 'Non-Color'
        sep = tree.nodes.new('ShaderNodeSeparateColor')
        sep.location = (x_off + 300, y)
        tree.links.new(tex.outputs['Color'], sep.inputs['Color'])
        tree.links.new(sep.outputs['Red'], bsdf.inputs['Metallic'])
        tree.links.new(sep.outputs['Green'], bsdf.inputs['Roughness'])
        y -= 300
        loaded = True

    if tex_flags.get('emissive') and 'emissive' in type_map:
        tex = _create_image_node(tree, type_map['emissive'], "Emissive", x_off, y)
        tree.links.new(tex.outputs['Color'], bsdf.inputs['Emission Color'])
        bsdf.inputs['Emission Strength'].default_value = 1.0
        loaded = True

    return loaded


def _setup_material_textures(mat, model_dir, mat_name, tex_flags=None):
    """Set up Principled BSDF with auto-detected texture maps (used during mesh import)."""
    if tex_flags is False:
        return False
    if tex_flags is None or tex_flags is True:
        tex_flags = {k: True for k in _TEX_KEYWORDS}
    if not any(tex_flags.values()):
        return False

    tex_map = _scan_texture_dir(model_dir)
    prefix = _match_prefix(tex_map, mat_name)
    log(f"Searching textures for material '{mat_name}' in {model_dir}")
    log(f"  Available prefixes: {list(tex_map.keys())}")
    if prefix:
        log(f"  Matched prefix: '{prefix}' -> types: {list(tex_map[prefix].keys())}")
        return _setup_material_from_prefix(mat, tex_map[prefix], tex_flags)
    log(f"  No matching prefix found for '{mat_name}'")
    return False


# ============================================================================
# Blender object builders
# ============================================================================

def _build_mesh_object(scn, meshname, materialname, verts, faces, texc, flipuv,
                       vgroups, bone_link, bone_names, rig, is_surf,
                       model_dir='', tex_flags=None):
    """Create a Blender mesh object with UVs, vertex groups, and armature modifier."""
    msh = bpy.data.meshes.new(name=meshname)
    msh.from_pydata(verts, [], faces)
    msh.update()

    if materialname:
        mat = bpy.data.materials.new(materialname)
        msh.materials.append(mat)
        if model_dir and tex_flags:
            _setup_material_textures(mat, model_dir, materialname, tex_flags)

    if texc:
        if flipuv:
            texc = [(uv[0], 1 - uv[1]) for uv in texc]
        uv_layer = msh.uv_layers.new(name=f'UVMain{meshname}')
        for face in msh.polygons:
            for vert_idx, loop_idx in zip(face.vertices, face.loop_indices):
                uv_layer.data[loop_idx].uv = texc[vert_idx]

    obj = bpy.data.objects.new(f'{meshname}_Object', msh)
    scn.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    bpy.context.view_layer.update()

    if is_surf:
        obj.display_type = 'WIRE'
    else:
        if bone_link >= 0 and bone_link < len(bone_names):
            grp = obj.vertex_groups.new(name=bone_names[bone_link])
            grp.add(list(range(len(msh.vertices))), 1.0, 'REPLACE')
        for name, vg in vgroups.items():
            grp = obj.vertex_groups.new(name=name)
            for v, w in vg:
                grp.add([v], w, 'REPLACE')

        mod = obj.modifiers.new(name='K2_Armature', type='ARMATURE')
        mod.object = rig
        mod.use_bone_envelopes = False
        mod.use_vertex_groups = True

        bpy.context.view_layer.objects.active = rig
        rig.select_set(True)
        bpy.ops.object.mode_set(mode='POSE')
        for b in rig.pose.bones:
            b.rotation_mode = 'QUATERNION'
        bpy.ops.object.mode_set(mode='OBJECT')
        rig.select_set(False)

    bpy.context.view_layer.objects.active = None
    return obj


# ============================================================================
# Main mesh import
# ============================================================================

def create_blender_mesh(filename, objname, flipuv, tex_flags=None):
    """Import a K2 .model file into Blender."""
    model_dir = os.path.dirname(os.path.abspath(filename))
    try:
        with open(filename, 'rb') as file:
            sig = file.read(4)
            if sig != b'SMDL':
                err('Unknown file signature')
                return None, None

            honchunk = chunk.Chunk(file, bigendian=False, align=False)
            if honchunk.getname() != b'head':
                err('File does not start with head chunk')
                return None, None

            version = read_int(honchunk)
            num_meshes = read_int(honchunk)
            num_sprites = read_int(honchunk)
            num_surfs = read_int(honchunk)
            num_bones = read_int(honchunk)

            log(f"K2 Model v{version}: {num_meshes} mesh(es), {num_sprites} sprite(s), {num_surfs} surf(s), {num_bones} bone(s)")
            if num_meshes == 0:
                log("WARNING: Model file contains 0 meshes — only bones will be imported")
            vlog("Bounding box: (%f, %f, %f) - (%f, %f, %f)" % struct.unpack("<ffffff", honchunk.read(24)))
            honchunk.skip()

            scn = bpy.context.scene

            # --- Read bones ---
            try:
                honchunk = chunk.Chunk(file, bigendian=False, align=False)
            except EOFError:
                err('Error reading bone chunk')
                return None, None

            armature_data = bpy.data.armatures.new(f'{objname}_Armature')
            armature_data.display_type = 'STICK'
            armature_data.show_names = True
            rig = bpy.data.objects.new(f'{objname}_Rig', armature_data)
            scn.collection.objects.link(rig)
            bpy.context.view_layer.objects.active = rig
            rig.select_set(True)

            bpy.ops.object.mode_set(mode='EDIT')
            _, bone_names, _ = _read_bones(honchunk, num_bones, version, armature_data)
            bpy.ops.object.mode_set(mode='OBJECT')

            rig.show_in_front = True
            bpy.context.view_layer.update()

            # --- Read meshes / surfs ---
            try:
                honchunk = chunk.Chunk(file, bigendian=False, align=False)
            except EOFError:
                err('Error reading mesh chunk')
                return None, rig

            obj = None
            while honchunk and honchunk.getname() in (b'mesh', b'surf'):
                if honchunk.getname() == b'mesh':
                    vlog(f"Mesh index: {read_int(honchunk)}")

                    if version == 3:
                        mode, bone_link, meshname, materialname = _read_mesh_header_v3(honchunk)
                    elif version == 1:
                        mode, bone_link, meshname, materialname = _read_mesh_header_v1(honchunk)
                    else:
                        err(f"Unsupported version {version}")
                        return obj, rig

                    honchunk.skip()

                    if mode != 1:
                        # Skip non-standard mesh modes entirely
                        while True:
                            try:
                                honchunk = chunk.Chunk(file, bigendian=False, align=False)
                            except EOFError:
                                honchunk = None
                                break
                            if honchunk.getname() in (b'mesh', b'surf'):
                                break
                            honchunk.skip()
                        continue

                    verts, faces, signs, nrml, texc, colors, vgroups, honchunk = \
                        _read_mesh_subchunks(file, version, bone_names)

                    obj = _build_mesh_object(
                        scn, meshname, materialname, verts, faces, texc, flipuv,
                        vgroups, bone_link, bone_names, rig, is_surf=False,
                        model_dir=model_dir, tex_flags=tex_flags,
                    )

                elif honchunk.getname() == b'surf':
                    surf_planes, surf_points, surf_edges, surf_tris = parse_surf(honchunk)
                    dlog(f"Surface: {len(surf_planes)} planes, {len(surf_points)} points, "
                         f"{len(surf_edges)} edges, {len(surf_tris)} tris")

                    honchunk.skip()

                    obj = _build_mesh_object(
                        scn, f'{objname}_surf', None, surf_points, surf_tris, [], flipuv,
                        {}, -1, bone_names, rig, is_surf=True,
                        model_dir=model_dir, tex_flags=None,
                    )

                    try:
                        honchunk = chunk.Chunk(file, bigendian=False, align=False)
                    except EOFError:
                        vlog('Done reading chunks')
                        honchunk = None

            bpy.context.view_layer.update()
            view_all_in_3d_view()
            return obj, rig

    except IOError as e:
        err(f"File IO Error: {e}")
    except Exception as e:
        err(f"Unexpected error: {e}")
    return None, None


# ============================================================================
# Clip helpers
# ============================================================================

def _get_motion_value(motion_keys, frame_index):
    """Safely get a motion key value, clamping to the last available frame."""
    if frame_index < len(motion_keys):
        return motion_keys[frame_index]
    return motion_keys[-1]


def get_transform_matrix(motions, bone, frame, version):
    motion = motions[bone.name]
    x = _get_motion_value(motion[MKEY_X], frame)
    y = _get_motion_value(motion[MKEY_Y], frame)
    z = _get_motion_value(motion[MKEY_Z], frame)

    rx = _get_motion_value(motion[MKEY_PITCH], frame)
    ry = _get_motion_value(motion[MKEY_ROLL], frame)
    rz = _get_motion_value(motion[MKEY_YAW], frame)

    sx = _get_motion_value(motion[MKEY_SCALE_X], frame)
    if version == 1:
        sy = sz = sx
    else:
        sy = _get_motion_value(motion[MKEY_SCALE_Y], frame)
        sz = _get_motion_value(motion[MKEY_SCALE_Z], frame)

    rotation_matrix = Euler(
        (math.radians(rx), math.radians(ry), math.radians(rz)), 'YXZ'
    ).to_matrix().to_4x4()
    transform = Matrix.Translation(Vector((x, y, z))) @ rotation_matrix

    return transform, Vector((sx, sy, sz))


def animate_bone(name, pose, motions, num_frames, armature, arm_ob, version):
    if name not in armature.bones.keys():
        log(f'{name} not found in armature')
        return

    bone = armature.bones[name]
    bone_rest_matrix = Matrix(bone.matrix_local)

    if bone.parent is not None:
        parent_rest_inv = Matrix(bone.parent.matrix_local)
        parent_rest_inv.invert()
        bone_rest_matrix = parent_rest_inv @ bone_rest_matrix

    bone_rest_matrix_inv = Matrix(bone_rest_matrix).inverted()

    pbone = pose.bones[name]
    for i in range(num_frames):
        transform, size = get_transform_matrix(motions, bone, i, version)
        transform = bone_rest_matrix_inv @ transform
        pbone.rotation_quaternion = transform.to_quaternion()
        pbone.location = transform.to_translation()
        pbone.keyframe_insert(data_path='rotation_quaternion', frame=i)
        pbone.keyframe_insert(data_path='location', frame=i)


# ============================================================================
# Main clip import
# ============================================================================

def create_blender_clip(filename, clipname):
    """Import a K2 .clip file and apply it to the selected armature."""
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
                dlog(f"{name}, bone index: {boneindex}, key type: {keytype}, keys: {numkeys}")
                if keytype == MKEY_VISIBILITY:
                    data = struct.unpack(f"{numkeys}B", clipchunk.read(numkeys))
                else:
                    data = struct.unpack(f"<{numkeys}f", clipchunk.read(numkeys * 4))
                motions[name][keytype] = list(data)
                clipchunk.skip()

            for bone_name in motions:
                animate_bone(bone_name, pose, motions, num_frames, armature, arm_ob, version)

    except IOError as e:
        err(f"File IO Error: {e}")


# ============================================================================
# Public entry points (called from __init__.py operators)
# ============================================================================

def readclip(filepath):
    obj_name = bpy.path.display_name_from_filepath(filepath)
    create_blender_clip(filepath, obj_name)


def read(filepath, flipuv, tex_flags=None):
    obj_name = bpy.path.display_name_from_filepath(filepath)
    create_blender_mesh(filepath, obj_name, flipuv, tex_flags=tex_flags)
