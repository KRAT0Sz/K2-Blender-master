"""
K2 Blender Addon - Texture handling module.
Handles texture scanning, matching, and material assignment.
"""

import os
import bpy
from .k2_common import log, vlog


# ============================================================================
# Texture keywords and settings
# ============================================================================

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


# ============================================================================
# Texture scanning
# ============================================================================

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


# ============================================================================
# Material setup
# ============================================================================

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
# Public API
# ============================================================================

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


def clear_cache():
    """Clear the texture directory cache."""
    _dir_cache.clear()
