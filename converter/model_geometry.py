"""Model-based geometry generator for non-full-cube Minecraft blocks.

Reads Minecraft model JSON files (via ModelResolver) and generates CS2 quads
from the model elements (cuboid shapes with per-face textures).
Supports multipart blockstates (fences, walls) and variant selection (stairs, crops).
"""

import math
from converter.mesh_generator import Quad, mc_to_cs2
from textures.model_resolver import ModelResolver, MC_FACE_TO_DIR


# Vertex patterns for each face of a cuboid element [from (x1,y1,z1) to (x2,y2,z2)]
# Vertices in CW order in MC coords so that after the handedness-flipping
# coordinate transform (negate Z) they become CCW when viewed from outside.
_ELEMENT_FACE_VERTS = {
    "east":  lambda x1,y1,z1,x2,y2,z2: [(x2,y2,z1),(x2,y2,z2),(x2,y1,z2),(x2,y1,z1)],
    "west":  lambda x1,y1,z1,x2,y2,z2: [(x1,y1,z2),(x1,y2,z2),(x1,y2,z1),(x1,y1,z1)],
    "up":    lambda x1,y1,z1,x2,y2,z2: [(x1,y2,z2),(x2,y2,z2),(x2,y2,z1),(x1,y2,z1)],
    "down":  lambda x1,y1,z1,x2,y2,z2: [(x2,y1,z1),(x2,y1,z2),(x1,y1,z2),(x1,y1,z1)],
    "south": lambda x1,y1,z1,x2,y2,z2: [(x2,y1,z2),(x2,y2,z2),(x1,y2,z2),(x1,y1,z2)],
    "north": lambda x1,y1,z1,x2,y2,z2: [(x1,y2,z1),(x2,y2,z1),(x2,y1,z1),(x1,y1,z1)],
}

# MC face normals (in MC coords)
_MC_FACE_NORMALS = {
    "east":  ( 1, 0, 0),
    "west":  (-1, 0, 0),
    "up":    ( 0, 1, 0),
    "down":  ( 0,-1, 0),
    "south": ( 0, 0, 1),
    "north": ( 0, 0,-1),
}

# Per-face UV axis mapping: (u_coord_index, u_invert, v_coord_index, v_invert)
# Determines how element vertex positions map to UV coordinates for each MC face.
_FACE_UV_AXES = {
    "north": (0, True,  1, True),    # u from x (inverted), v from y (inverted)
    "south": (0, False, 1, True),    # u from x, v from y (inverted)
    "east":  (2, True,  1, True),    # u from z (inverted), v from y (inverted)
    "west":  (2, False, 1, True),    # u from z, v from y (inverted)
    "up":    (0, False, 2, False),   # u from x, v from z
    "down":  (0, False, 2, True),    # u from x, v from z (inverted)
}


def _compute_element_face_uvs(mc_face, face_data, from_pos, to_pos):
    """Compute UV coordinates for each vertex of a model element face.

    Uses the model's UV data [u1, v1, u2, v2] (in 0-16 range) to compute
    per-vertex UVs based on the vertex's parametric position in the element.

    When no UV is specified, auto-generates from element positions per MC spec:
    each face's UVs are derived from the element's from/to coordinates so the
    texture is NOT stretched.

    Returns list of 4 (u, v) tuples in 0-1 range.
    """
    uv = face_data.get("uv")
    if uv is None:
        # Auto-generate UVs from element positions per Minecraft spec
        x1, y1, z1 = from_pos
        x2, y2, z2 = to_pos
        if mc_face == "north":
            uv = [16 - x2, 16 - y2, 16 - x1, 16 - y1]
        elif mc_face == "south":
            uv = [x1, 16 - y2, x2, 16 - y1]
        elif mc_face == "east":
            uv = [16 - z2, 16 - y2, 16 - z1, 16 - y1]
        elif mc_face == "west":
            uv = [z1, 16 - y2, z2, 16 - y1]
        elif mc_face == "up":
            uv = [x1, z1, x2, z2]
        elif mc_face == "down":
            uv = [x1, 16 - z2, x2, 16 - z1]
        else:
            uv = [0, 0, 16, 16]

    u1, v1, u2, v2 = uv[0] / 16.0, uv[1] / 16.0, uv[2] / 16.0, uv[3] / 16.0
    u_idx, u_inv, v_idx, v_inv = _FACE_UV_AXES[mc_face]

    verts = _ELEMENT_FACE_VERTS[mc_face](*from_pos, *to_pos)
    f = list(from_pos)
    t = list(to_pos)

    uvs = []
    for vx, vy, vz in verts:
        coords = [vx, vy, vz]
        u_range = t[u_idx] - f[u_idx]
        v_range = t[v_idx] - f[v_idx]

        tu = (coords[u_idx] - f[u_idx]) / u_range if abs(u_range) > 0.001 else 0.0
        tv = (coords[v_idx] - f[v_idx]) / v_range if abs(v_range) > 0.001 else 0.0

        if u_inv:
            tu = 1.0 - tu
        if v_inv:
            tv = 1.0 - tv

        u = u1 + (u2 - u1) * tu
        v = v1 + (v2 - v1) * tv
        uvs.append((u, v))

    return uvs


# Rotation tables for face direction strings.  MC blockstate rotations are
# clockwise when viewed from the positive axis.
_Y_FACE_ROT = {
    90:  {"north": "east", "east": "south", "south": "west", "west": "north"},
    180: {"north": "south", "east": "west", "south": "north", "west": "east"},
    270: {"north": "west", "west": "south", "south": "east", "east": "north"},
}
_X_FACE_ROT = {
    90:  {"up": "north", "north": "down", "down": "south", "south": "up"},
    180: {"up": "down", "north": "south", "down": "up", "south": "north"},
    270: {"up": "south", "south": "down", "down": "north", "north": "up"},
}


def _rotate_cullface(cullface, x_rot, y_rot):
    """Rotate a cullface direction string by blockstate model rotations.

    Applies X then Y rotation (matching generate_quads order).
    x_rot and y_rot are MC CW rotation angles (0, 90, 180, 270).
    """
    face = cullface
    if x_rot and x_rot in _X_FACE_ROT:
        face = _X_FACE_ROT[x_rot].get(face, face)
    if y_rot and y_rot in _Y_FACE_ROT:
        face = _Y_FACE_ROT[y_rot].get(face, face)
    return face


def _rotate_point(x, y, z, origin, axis, angle_deg, rescale=False):
    """Rotate a point around an axis through origin by angle_deg degrees.

    If rescale is True, scale the non-rotation axes by 1/cos(angle) to maintain
    the element's apparent size after rotation (Minecraft model 'rescale' flag).
    """
    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)

    # Translate to origin
    dx = x - origin[0]
    dy = y - origin[1]
    dz = z - origin[2]

    if axis == "x":
        ry = dy * cos_a - dz * sin_a
        rz = dy * sin_a + dz * cos_a
        rx = dx
    elif axis == "y":
        rx = dx * cos_a + dz * sin_a
        rz = -dx * sin_a + dz * cos_a
        ry = dy
    else:  # z
        rx = dx * cos_a - dy * sin_a
        ry = dx * sin_a + dy * cos_a
        rz = dz

    if rescale and abs(cos_a) > 0.001:
        sf = 1.0 / abs(cos_a)
        if axis == "x":
            ry *= sf
            rz *= sf
        elif axis == "y":
            rx *= sf
            rz *= sf
        else:
            rx *= sf
            ry *= sf

    return (rx + origin[0], ry + origin[1], rz + origin[2])


def _rotate_normal(nx, ny, nz, axis, angle_deg):
    """Rotate a normal vector around an axis."""
    return _rotate_point(nx, ny, nz, (0, 0, 0), axis, angle_deg)


def _parse_block_state(block_name: str) -> tuple[str, dict]:
    """Parse 'minecraft:oak_fence[north=true,east=false]' into (short_name, {props}).

    Returns (short_name_without_namespace, state_dict).
    """
    base = block_name.split("[")[0].replace("minecraft:", "")
    props = {}
    if "[" in block_name:
        state_str = block_name.split("[", 1)[1].rstrip("]")
        for pair in state_str.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                props[k.strip()] = v.strip()
    return base, props


def _match_variant_key(variant_key: str, state_props: dict) -> bool:
    """Check if a variant key like 'facing=east,half=bottom' matches state props."""
    if variant_key == "" or variant_key == "normal":
        return True
    for pair in variant_key.split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            if k in state_props and state_props[k] != v:
                return False
    return True


def _match_multipart_when(when: dict, state_props: dict) -> bool:
    """Check if a multipart 'when' condition matches the block state.

    Handles simple conditions like {"north": "true"} and
    OR conditions like {"OR": [{"north": "true"}, {"south": "true"}]}.
    Also handles pipe-separated values like {"north": "low|tall"}.
    """
    if not when:
        return True
    # OR condition
    if "OR" in when:
        return any(_match_multipart_when(sub, state_props) for sub in when["OR"])
    # Simple property match
    for k, v in when.items():
        if k == "OR":
            continue
        actual = state_props.get(k, "")
        # Handle pipe-separated values (e.g. "low|tall")
        options = str(v).split("|")
        if actual not in options:
            return False
    return True


class ModelBlockQuadGenerator:
    """Generates quads from Minecraft model data for non-full-cube blocks."""

    def __init__(self, assets_path: str):
        self._resolver = ModelResolver(assets_path)
        self._geometry_cache = {}  # cache_key -> list of model parts

    def close(self):
        self._resolver.close()

    def _get_model_parts(self, block_name: str):
        """Get all model parts for a block, considering its block state.

        For multipart blocks (fences, walls): returns parts whose 'when'
        conditions match the block state properties.
        For variant blocks (stairs, crops): selects the matching variant.

        Returns list of (elements, textures, y_rot, x_rot) tuples,
        or None if not available.
        """
        short_name, state_props = _parse_block_state(block_name)
        # Cache key includes relevant state properties
        cache_key = block_name.split("[")[0].replace("minecraft:", "")
        if state_props:
            cache_key += "[" + ",".join(f"{k}={v}" for k, v in sorted(state_props.items())) + "]"

        if cache_key in self._geometry_cache:
            return self._geometry_cache[cache_key]

        blockstate = self._resolver._read_json(f"blockstates/{short_name}.json")
        if blockstate is None:
            self._geometry_cache[cache_key] = None
            return None

        parts = []

        if "multipart" in blockstate:
            # Multipart: check each part's 'when' condition
            for part_def in blockstate["multipart"]:
                when = part_def.get("when")
                if not _match_multipart_when(when, state_props):
                    continue
                apply = part_def.get("apply", {})
                if isinstance(apply, list):
                    apply = apply[0]
                model_ref = apply.get("model")
                if not model_ref:
                    continue
                y_rot = apply.get("y", 0)
                x_rot = apply.get("x", 0)
                textures, elements = self._resolver._read_model_chain(model_ref)
                if elements:
                    parts.append((elements, textures, y_rot, x_rot))

        elif "variants" in blockstate:
            variants = blockstate["variants"]
            # Find best matching variant
            matched_apply = None
            # Try exact match first using state_props
            if state_props:
                state_key = ",".join(f"{k}={v}" for k, v in sorted(state_props.items()))
                if state_key in variants:
                    matched_apply = variants[state_key]
                else:
                    # Try matching with different key orderings
                    for vk, vv in variants.items():
                        if _match_variant_key(vk, state_props):
                            matched_apply = vv
                            break
            if matched_apply is None:
                # Fallback: empty key or first variant
                matched_apply = variants.get("", None)
                if matched_apply is None:
                    matched_apply = next(iter(variants.values()))

            if isinstance(matched_apply, list):
                matched_apply = matched_apply[0]
            if isinstance(matched_apply, dict):
                model_ref = matched_apply.get("model")
                y_rot = matched_apply.get("y", 0)
                x_rot = matched_apply.get("x", 0)
                if model_ref:
                    textures, elements = self._resolver._read_model_chain(model_ref)
                    if elements:
                        parts.append((elements, textures, y_rot, x_rot))

        result = parts if parts else None
        self._geometry_cache[cache_key] = result
        return result

    def has_model(self, block_name: str) -> bool:
        """Check if a block has model geometry data."""
        parts = self._get_model_parts(block_name)
        return parts is not None

    def generate_quads(self, block_name: str, block_pos: tuple,
                       scale: float = 64.0, offset: tuple = (0.0, 0.0, 0.0),
                       neighbor_solid: dict = None) -> list[Quad]:
        """Generate quads for a model block at a specific position.

        Args:
            block_name: Full block name e.g. "minecraft:torch" or "minecraft:oak_fence[north=true]"
            block_pos: (bx, by, bz) position in MC block coordinates
            scale: Block size in Hammer units (default 64)
            offset: CS2 coordinate offset
            neighbor_solid: Optional dict {face_dir: bool} for face culling.
                           face_dir is MC face name ("up","down","north","south","east","west").

        Returns:
            List of Quad objects in CS2 coordinate space.
        """
        model_parts = self._get_model_parts(block_name)
        if model_parts is None:
            return []

        bx, by, bz = block_pos
        ox, oy, oz = offset
        quads = []

        for elements, textures, model_y_rot, model_x_rot in model_parts:
            for elem in elements:
                from_pos = elem.get("from", [0, 0, 0])
                to_pos = elem.get("to", [16, 16, 16])
                rotation = elem.get("rotation")
                faces = elem.get("faces", {})

                x1, y1, z1 = from_pos
                x2, y2, z2 = to_pos

                for mc_face, face_data in faces.items():
                    if mc_face not in _ELEMENT_FACE_VERTS:
                        continue

                    # Check cullface: if this face should be culled by adjacent solid blocks
                    # Rotate the cullface direction by the blockstate model rotation
                    # so it matches the world-space neighbor map.
                    cullface = face_data.get("cullface")
                    if cullface:
                        cullface = _rotate_cullface(cullface, model_x_rot, model_y_rot)
                    if cullface and neighbor_solid and neighbor_solid.get(cullface, False):
                        continue

                    # Generate vertices in MC model coords (0-16 range)
                    verts_mc = _ELEMENT_FACE_VERTS[mc_face](x1, y1, z1, x2, y2, z2)

                    # Compute model UVs from pre-rotation vertex positions
                    texcoords = _compute_element_face_uvs(mc_face, face_data, from_pos, to_pos)

                    # Resolve texture name from model data
                    tex_ref = face_data.get("texture", "")
                    tex_name = None
                    if tex_ref:
                        resolved = self._resolver._resolve_texture_ref(tex_ref, textures)
                        if resolved:
                            tex_name = self._resolver._texture_ref_to_name(resolved)

                    # Apply element-level rotation if present
                    if rotation:
                        rot_origin = rotation.get("origin", [8, 8, 8])
                        rot_axis = rotation.get("axis", "y")
                        rot_angle = rotation.get("angle", 0)
                        do_rescale = rotation.get("rescale", False)
                        if rot_angle != 0:
                            verts_mc = [
                                _rotate_point(vx, vy, vz, rot_origin, rot_axis, rot_angle, rescale=do_rescale)
                                for vx, vy, vz in verts_mc
                            ]

                    # Apply whole-model rotation from blockstate (around block center)
                    # MC blockstate rotations are CW when viewed from the positive axis,
                    # but _rotate_point uses standard CCW convention, so negate angles.
                    model_origin = (8, 8, 8)
                    if model_x_rot:
                        verts_mc = [
                            _rotate_point(vx, vy, vz, model_origin, "x", -model_x_rot)
                            for vx, vy, vz in verts_mc
                        ]
                    if model_y_rot:
                        verts_mc = [
                            _rotate_point(vx, vy, vz, model_origin, "y", -model_y_rot)
                            for vx, vy, vz in verts_mc
                        ]

                    # Transform to CS2 world coordinates
                    verts_cs2 = []
                    for vx, vy, vz in verts_mc:
                        wx = (bx + vx / 16.0) * scale + ox
                        wy = (by + vy / 16.0) * scale + oz  # MC Y → CS2 Z
                        wz = (bz + vz / 16.0) * scale + oy  # MC Z → CS2 Y (negated for handedness)
                        verts_cs2.append((wx, -wz, wy))

                    # Normal in MC coords
                    mnx, mny, mnz = _MC_FACE_NORMALS[mc_face]
                    if rotation:
                        rot_axis = rotation.get("axis", "y")
                        rot_angle = rotation.get("angle", 0)
                        if rot_angle != 0:
                            mnx, mny, mnz = _rotate_normal(mnx, mny, mnz, rot_axis, rot_angle)
                    if model_x_rot:
                        mnx, mny, mnz = _rotate_normal(mnx, mny, mnz, "x", -model_x_rot)
                    if model_y_rot:
                        mnx, mny, mnz = _rotate_normal(mnx, mny, mnz, "y", -model_y_rot)
                    normal_cs2 = mc_to_cs2(mnx, mny, mnz)

                    face_dir = MC_FACE_TO_DIR.get(mc_face, mc_face)

                    quads.append(Quad(
                        vertices=verts_cs2,
                        normal=normal_cs2,
                        block_type=block_name,
                        face_dir=face_dir,
                        block_pos=(bx, by, bz),
                        texcoords=texcoords,
                        texture_name=tex_name,
                    ))

        return quads
