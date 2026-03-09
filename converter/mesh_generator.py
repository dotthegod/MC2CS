"""Mesh generator: converts a BlockGrid into a list of quads via face culling."""

from collections import deque
from dataclasses import dataclass, field
import numpy as np
from parsers.block_grid import BlockGrid
from config.blocks import (should_generate_geometry, is_solid_for_culling,
                           get_block_base_name, is_model_block, is_liquid,
                           is_waterlogged, is_damage_block,
                           is_climbable_block, is_slime_block,
                           is_leaf_block, is_stair_block, is_half_height_block,
                           is_light_source, get_light_properties)


def _parse_block_state(block_name: str) -> dict:
    """Parse block state properties from name like 'minecraft:ladder[facing=north]'."""
    if "[" not in block_name:
        return {}
    props_str = block_name.split("[", 1)[1].rstrip("]")
    props = {}
    for pair in props_str.split(","):
        if "=" in pair:
            key, value = pair.split("=", 1)
            props[key.strip()] = value.strip()
    return props


def _generate_ramp_quads(bx, by, bz, facing, block, scale, offset, block_pos,
                         y_base=0.5, y_top=0.75, bridge=False):
    """Generate a ramp (wedge) clip brush for a stair block gap.

    Creates a distorted hexahedron where one edge is collapsed to near-zero
    thickness, forming a ramp surface.  The vertex layout follows the same
    convention as _generate_box_quads so face winding is correct after the
    MC→CS2 coordinate transform.

    y_base: bottom of the ramp (thin edge height)
    y_top:  top of the ramp (slope peak height)
    bridge: If True, place ramp on the FRONT half of the stair (over the top
            step), with slope rising toward the facing direction.  Used for
            inter-stair transition ramps.
    """
    EPS = 1.0 / 128  # thin-edge epsilon to avoid degenerate faces
    ox, oy, oz = offset

    yb = y_base
    yt = y_top

    if not bridge:
        # Normal ramp: covers the BACK half (gap side) of the stair.
        # Tall side at the step edge, thin side at the approach.
        if facing == "north":
            verts = [
                (0, yb, 0.5), (1, yb, 0.5),
                (0, yt, 0.5), (1, yt, 0.5),
                (0, yb, 1.0), (1, yb, 1.0),
                (0, yb + EPS, 1.0), (1, yb + EPS, 1.0),
            ]
        elif facing == "south":
            verts = [
                (0, yb, 0.0), (1, yb, 0.0),
                (0, yb + EPS, 0.0), (1, yb + EPS, 0.0),
                (0, yb, 0.5), (1, yb, 0.5),
                (0, yt, 0.5), (1, yt, 0.5),
            ]
        elif facing == "east":
            verts = [
                (0.0, yb, 0), (0.0, yb, 1),
                (0.0, yb + EPS, 0), (0.0, yb + EPS, 1),
                (0.5, yb, 0), (0.5, yb, 1),
                (0.5, yt, 0), (0.5, yt, 1),
            ]
        elif facing == "west":
            verts = [
                (0.5, yb, 0), (0.5, yb, 1),
                (0.5, yt, 0), (0.5, yt, 1),
                (1.0, yb, 0), (1.0, yb, 1),
                (1.0, yb + EPS, 0), (1.0, yb + EPS, 1),
            ]
        else:
            return []
    else:
        # Bridge ramp: covers the FRONT half (over the top step).
        # Tall side at the forward edge (toward facing), thin at the step edge.
        if facing == "north":
            # z=0..0.5, tall at z=0 (north edge)
            verts = [
                (0, yb, 0.0), (1, yb, 0.0),
                (0, yt, 0.0), (1, yt, 0.0),
                (0, yb, 0.5), (1, yb, 0.5),
                (0, yb + EPS, 0.5), (1, yb + EPS, 0.5),
            ]
        elif facing == "south":
            # z=0.5..1.0, tall at z=1 (south edge)
            verts = [
                (0, yb, 0.5), (1, yb, 0.5),
                (0, yb + EPS, 0.5), (1, yb + EPS, 0.5),
                (0, yb, 1.0), (1, yb, 1.0),
                (0, yt, 1.0), (1, yt, 1.0),
            ]
        elif facing == "east":
            # x=0.5..1.0, tall at x=1 (east edge)
            verts = [
                (0.5, yb, 0), (0.5, yb, 1),
                (0.5, yb + EPS, 0), (0.5, yb + EPS, 1),
                (1.0, yb, 0), (1.0, yb, 1),
                (1.0, yt, 0), (1.0, yt, 1),
            ]
        elif facing == "west":
            # x=0..0.5, tall at x=0 (west edge)
            verts = [
                (0.0, yb, 0), (0.0, yb, 1),
                (0.0, yt, 0), (0.0, yt, 1),
                (0.5, yb, 0), (0.5, yb, 1),
                (0.5, yb + EPS, 0), (0.5, yb + EPS, 1),
            ]
        else:
            return []

    # Six faces using the same index pattern as _generate_box_quads:
    # +x: v3,v7,v5,v1  -x: v4,v6,v2,v0  +y: v6,v7,v3,v2
    # -y: v1,v5,v4,v0  +z: v5,v7,v6,v4  -z: v2,v3,v1,v0
    face_patterns = {
        "+x": ((1, 0, 0), [3, 7, 5, 1]),
        "-x": ((-1, 0, 0), [4, 6, 2, 0]),
        "+y": ((0, 1, 0), [6, 7, 3, 2]),
        "-y": ((0, -1, 0), [1, 5, 4, 0]),
        "+z": ((0, 0, 1), [5, 7, 6, 4]),
        "-z": ((0, 0, -1), [2, 3, 1, 0]),
    }

    result = []
    for face_dir, (normal_mc, indices) in face_patterns.items():
        normal_cs2 = mc_to_cs2(*normal_mc)
        verts_cs2 = []
        for vi in indices:
            vx, vy, vz = verts[vi]
            mx = (bx + vx) * scale
            my = (by + vy) * scale
            mz = (bz + vz) * scale
            verts_cs2.append((mx + ox, -mz + oy, my + oz))
        result.append(Quad(
            vertices=verts_cs2, normal=normal_cs2,
            block_type=block, face_dir=face_dir,
            block_pos=block_pos
        ))
    return result


def _generate_box_quads(bx, by, bz, x0, y0, z0, x1, y1, z1,
                        block, scale, offset, block_pos):
    """Generate 6 face quads for an axis-aligned box in MC local coordinates.

    (x0,y0,z0)-(x1,y1,z1) are in [0..1+] block-local MC coords.
    bx,by,bz is the block grid position.
    """
    ox, oy, oz = offset
    box_faces = {
        "+x": ((1, 0, 0), [(x1, y1, z0), (x1, y1, z1), (x1, y0, z1), (x1, y0, z0)]),
        "-x": ((-1, 0, 0), [(x0, y0, z1), (x0, y1, z1), (x0, y1, z0), (x0, y0, z0)]),
        "+y": ((0, 1, 0), [(x0, y1, z1), (x1, y1, z1), (x1, y1, z0), (x0, y1, z0)]),
        "-y": ((0, -1, 0), [(x1, y0, z0), (x1, y0, z1), (x0, y0, z1), (x0, y0, z0)]),
        "+z": ((0, 0, 1), [(x1, y0, z1), (x1, y1, z1), (x0, y1, z1), (x0, y0, z1)]),
        "-z": ((0, 0, -1), [(x0, y1, z0), (x1, y1, z0), (x1, y0, z0), (x0, y0, z0)]),
    }
    result = []
    for face_dir, (normal_mc, verts) in box_faces.items():
        normal_cs2 = mc_to_cs2(*normal_mc)
        verts_cs2 = []
        for vx, vy, vz in verts:
            mx = (bx + vx) * scale
            my = (by + vy) * scale
            mz = (bz + vz) * scale
            verts_cs2.append((mx + ox, -mz + oy, my + oz))
        result.append(Quad(
            vertices=verts_cs2, normal=normal_cs2,
            block_type=block, face_dir=face_dir,
            block_pos=block_pos
        ))
    return result


@dataclass
class Quad:
    """A single face quad with 4 vertices in CCW winding order."""
    vertices: list  # 4 tuples of (x, y, z) in CS2 coordinates
    normal: tuple   # (nx, ny, nz) face normal
    block_type: str  # e.g. "minecraft:stone"
    face_dir: str   # "+x", "-x", "+y", "-y", "+z", "-z" (Minecraft coords)
    block_pos: tuple = (0, 0, 0)  # (bx, by, bz) Minecraft grid coordinates
    texcoords: list = None  # Optional: 4 (u, v) tuples for explicit UV (model blocks)
    texture_name: str = None  # Optional: resolved texture name (model blocks)


# Face definitions: direction -> (normal_mc, vertex offsets from block origin)
# Vertices ordered CW in MC coords so that after the handedness-flipping
# coordinate transform (negate Z) they become CCW when viewed from outside.
# In Minecraft coords: X=east, Y=up, Z=south
FACE_DEFS = {
    "+x": {
        "normal_mc": (1, 0, 0),
        "neighbor": (1, 0, 0),
        "verts": [(1, 1, 0), (1, 1, 1), (1, 0, 1), (1, 0, 0)],
    },
    "-x": {
        "normal_mc": (-1, 0, 0),
        "neighbor": (-1, 0, 0),
        "verts": [(0, 0, 1), (0, 1, 1), (0, 1, 0), (0, 0, 0)],
    },
    "+y": {
        "normal_mc": (0, 1, 0),
        "neighbor": (0, 1, 0),
        "verts": [(0, 1, 1), (1, 1, 1), (1, 1, 0), (0, 1, 0)],
    },
    "-y": {
        "normal_mc": (0, -1, 0),
        "neighbor": (0, -1, 0),
        "verts": [(1, 0, 0), (1, 0, 1), (0, 0, 1), (0, 0, 0)],
    },
    "+z": {
        "normal_mc": (0, 0, 1),
        "neighbor": (0, 0, 1),
        "verts": [(1, 0, 1), (1, 1, 1), (0, 1, 1), (0, 0, 1)],
    },
    "-z": {
        "normal_mc": (0, 0, -1),
        "neighbor": (0, 0, -1),
        "verts": [(0, 1, 0), (1, 1, 0), (1, 0, 0), (0, 0, 0)],
    },
}


def mc_to_cs2(x: float, y: float, z: float) -> tuple:
    """Convert Minecraft coordinates to CS2 coordinates.
    Minecraft: X=east, Y=up, Z=south  (right-handed)
    CS2/Source2: X=east, Y=north, Z=up (left-handed)
    Negate Z→Y to fix handedness (prevents mirrored map).
    """
    return (x, -z, y)


def generate_quads(grid: BlockGrid, scale: float = 64.0,
                   offset: tuple = (0.0, 0.0, 0.0),
                   progress_callback=None,
                   cull_faces: bool = True,
                   model_generator=None,
                   separate_liquids: bool = False,
                   generate_climbable: bool = False,
                   generate_slime: bool = False,
                   generate_stair_clips: bool = False,
                   generate_lights: bool = False) -> tuple:
    """Generate face quads from a BlockGrid using numpy-vectorized face culling.

    Args:
        grid: The BlockGrid to process
        scale: Size of one block in Hammer units (default 64)
        offset: (x, y, z) offset for the entire structure in CS2 coords
        progress_callback: Optional callable(current, total) for progress
        cull_faces: If True, skip faces occluded by solid neighbors (default).
        model_generator: Optional ModelBlockQuadGenerator for non-full-cube blocks
        separate_liquids: If True, return liquid quads separately with entity-
                          compatible culling (no cull against solids, only same-type).
        generate_climbable: If True, generate invisible climbable collision meshes.
        generate_slime: If True, generate slime bounce trigger meshes.
        generate_stair_clips: If True, generate clip ramp meshes for stairs.
        generate_lights: If True, collect light source positions for auto-lighting.

    Returns:
        (solid_quads, water_quads, lava_quads, damage_quads, climbable_quads,
         slime_quads, stair_clip_quads, light_sources)
         where light_sources is a list of (cs2_x, cs2_y, cs2_z, block_name) tuples.
    """
    blocks = grid.blocks  # shape (W, H, L)
    palette = grid.palette
    W, H, L = grid.width, grid.height, grid.length

    # Build lookup tables from palette indices
    max_idx = int(blocks.max()) + 1 if blocks.size > 0 else 1
    geo_lut = np.zeros(max_idx, dtype=bool)
    solid_lut = np.zeros(max_idx, dtype=bool)
    model_lut = np.zeros(max_idx, dtype=bool)
    water_lut = np.zeros(max_idx, dtype=bool)
    lava_lut = np.zeros(max_idx, dtype=bool)
    waterlogged_lut = np.zeros(max_idx, dtype=bool)
    damage_lut = np.zeros(max_idx, dtype=bool)
    climbable_lut = np.zeros(max_idx, dtype=bool)
    slime_lut = np.zeros(max_idx, dtype=bool)
    leaf_lut = np.zeros(max_idx, dtype=bool)
    stair_lut = np.zeros(max_idx, dtype=bool)
    half_height_lut = np.zeros(max_idx, dtype=bool)
    for idx, name in palette.items():
        if idx < max_idx:
            geo_lut[idx] = should_generate_geometry(name)
            solid_lut[idx] = is_solid_for_culling(name)
            model_lut[idx] = is_model_block(name)
            base = get_block_base_name(name)
            water_lut[idx] = (base == "minecraft:water")
            lava_lut[idx] = (base == "minecraft:lava")
            waterlogged_lut[idx] = is_waterlogged(name)
            damage_lut[idx] = is_damage_block(name)
            climbable_lut[idx] = is_climbable_block(name)
            slime_lut[idx] = is_slime_block(name)
            leaf_lut[idx] = is_leaf_block(name)
            stair_lut[idx] = is_stair_block(name)
            half_height_lut[idx] = is_half_height_block(name)

    light_lut = np.zeros(max_idx, dtype=bool)
    if generate_lights:
        for idx, name in palette.items():
            if idx < max_idx:
                light_lut[idx] = is_light_source(name)

    geo_mask = geo_lut[blocks]
    model_mask = model_lut[blocks]
    water_mask = water_lut[blocks]
    lava_mask = lava_lut[blocks]
    waterlogged_mask = waterlogged_lut[blocks]
    damage_mask = damage_lut[blocks]
    climbable_mask = climbable_lut[blocks]
    slime_mask = slime_lut[blocks]
    leaf_mask = leaf_lut[blocks]
    stair_mask = stair_lut[blocks]
    half_height_mask = half_height_lut[blocks]
    liquid_mask = water_mask | lava_mask

    if separate_liquids:
        # Non-liquid full-cube blocks only
        fullcube_geo = geo_mask & ~model_mask & ~liquid_mask
    else:
        fullcube_geo = geo_mask & ~model_mask

    quads = []
    water_quads = []
    lava_quads = []
    damage_quads = []
    climbable_quads = []
    slime_quads = []
    stair_clip_quads = []
    total_faces = 6
    faces_done = 0

    # Separate leaves from regular full-cube blocks for culling purposes
    leaf_geo = fullcube_geo & leaf_mask
    regular_geo = fullcube_geo & ~leaf_mask

    for face_dir, face_def in FACE_DEFS.items():
        dx, dy, dz = face_def["neighbor"]
        # Build neighbor slices
        src_x = slice(max(0, dx), min(W, W + dx))
        dst_x = slice(max(0, -dx), min(W, W - dx))
        src_y = slice(max(0, dy), min(H, H + dy))
        dst_y = slice(max(0, -dy), min(H, H - dy))
        src_z = slice(max(0, dz), min(L, L + dz))
        dst_z = slice(max(0, -dz), min(L, L - dz))

        if cull_faces:
            solid_mask_arr = solid_lut[blocks]
            neighbor_solid = np.zeros((W, H, L), dtype=bool)
            neighbor_solid[dst_x, dst_y, dst_z] = solid_mask_arr[src_x, src_y, src_z]

            # Same-type culling
            neighbor_same_type = np.zeros((W, H, L), dtype=bool)
            neighbor_same_type[dst_x, dst_y, dst_z] = (
                blocks[dst_x, dst_y, dst_z] == blocks[src_x, src_y, src_z]
            )
            neighbor_has_geo = np.zeros((W, H, L), dtype=bool)
            neighbor_has_geo[dst_x, dst_y, dst_z] = geo_mask[src_x, src_y, src_z]

            # Regular blocks: cull against solid neighbors + same-type neighbors
            visible_regular = regular_geo & ~neighbor_solid & ~(neighbor_same_type & neighbor_has_geo)
            # Leaves: only cull against solid neighbors (never same-type cull)
            visible_leaf = leaf_geo & ~neighbor_solid
            visible = visible_regular | visible_leaf
        else:
            visible = fullcube_geo

        # Generate solid block quads
        positions = np.argwhere(visible)
        if len(positions) > 0:
            verts_offsets = np.array(face_def["verts"], dtype=np.float64)
            mnx, mny, mnz = face_def["normal_mc"]
            normal_cs2 = mc_to_cs2(mnx, mny, mnz)
            ox, oy, oz = offset

            for i in range(len(positions)):
                bx, by, bz = positions[i]
                block = palette[int(blocks[bx, by, bz])]
                verts_cs2 = []
                for vx, vy, vz in verts_offsets:
                    mx = (bx + vx) * scale
                    my = (by + vy) * scale
                    mz = (bz + vz) * scale
                    verts_cs2.append((mx + ox, -mz + oy, my + oz))
                quads.append(Quad(
                    vertices=verts_cs2, normal=normal_cs2,
                    block_type=block, face_dir=face_dir,
                    block_pos=(int(bx), int(by), int(bz))
                ))

        # Generate liquid quads separately when entity mode is enabled
        if separate_liquids:
            for liq_mask, liq_list, liq_name in [
                (water_mask, water_quads, "minecraft:water"),
                (lava_mask, lava_quads, "minecraft:lava"),
            ]:
                if not np.any(liq_mask):
                    continue
                if cull_faces:
                    # Liquid entity culling: same-type culling AND waterlogged
                    # so water volumes extend seamlessly through seagrass, kelp, etc.
                    # Also cull liquid faces against solid blocks (invisible behind walls).
                    # Note: water has solid_lut=False, so it does NOT cull adjacent
                    # solid block faces — only solid blocks cull water faces here.
                    neighbor_same_liq = np.zeros((W, H, L), dtype=bool)
                    neighbor_same_liq[dst_x, dst_y, dst_z] = (
                        liq_mask[src_x, src_y, src_z] |
                        waterlogged_mask[src_x, src_y, src_z]
                    )
                    visible_liq = liq_mask & ~neighbor_same_liq & ~neighbor_solid
                else:
                    visible_liq = liq_mask

                liq_positions = np.argwhere(visible_liq)
                if len(liq_positions) == 0:
                    continue

                verts_offsets = np.array(face_def["verts"], dtype=np.float64)
                mnx, mny, mnz = face_def["normal_mc"]
                normal_cs2 = mc_to_cs2(mnx, mny, mnz)
                ox, oy, oz = offset

                for i in range(len(liq_positions)):
                    bx, by, bz = liq_positions[i]
                    block = palette[int(blocks[bx, by, bz])]
                    verts_cs2 = []
                    for vx, vy, vz in verts_offsets:
                        mx = (bx + vx) * scale
                        my = (by + vy) * scale
                        mz = (bz + vz) * scale
                        verts_cs2.append((mx + ox, -mz + oy, my + oz))
                    liq_list.append(Quad(
                        vertices=verts_cs2, normal=normal_cs2,
                        block_type=block, face_dir=face_dir,
                        block_pos=(int(bx), int(by), int(bz))
                    ))

            # Also generate water quads for waterlogged blocks
            if np.any(waterlogged_mask):
                if cull_faces:
                    # Waterlogged water: cull against adjacent water, waterlogged,
                    # and solid blocks (water faces invisible behind walls).
                    neighbor_is_water = np.zeros((W, H, L), dtype=bool)
                    neighbor_is_water[dst_x, dst_y, dst_z] = (
                        water_mask[src_x, src_y, src_z] |
                        waterlogged_mask[src_x, src_y, src_z]
                    )
                    visible_wl = waterlogged_mask & ~neighbor_is_water & ~neighbor_solid
                else:
                    visible_wl = waterlogged_mask

                wl_positions = np.argwhere(visible_wl)
                if len(wl_positions) > 0:
                    verts_offsets = np.array(face_def["verts"], dtype=np.float64)
                    mnx, mny, mnz = face_def["normal_mc"]
                    normal_cs2 = mc_to_cs2(mnx, mny, mnz)
                    ox, oy, oz = offset

                    for i in range(len(wl_positions)):
                        bx, by, bz = wl_positions[i]
                        verts_cs2 = []
                        for vx, vy, vz in verts_offsets:
                            mx = (bx + vx) * scale
                            my = (by + vy) * scale
                            mz = (bz + vz) * scale
                            # Inset top face to avoid z-fighting with block above
                            if face_dir == "+y":
                                my -= scale * (2.0 / 16.0)
                            # Inset all faces slightly inward to avoid z-fighting
                            # with the waterlogged block's own model geometry
                            inset = scale * (0.5 / 16.0)
                            if face_dir == "+x":
                                mx -= inset
                            elif face_dir == "-x":
                                mx += inset
                            elif face_dir == "-y":
                                my += inset
                            elif face_dir == "+z":
                                mz -= inset
                            elif face_dir == "-z":
                                mz += inset
                            verts_cs2.append((mx + ox, -mz + oy, my + oz))
                        water_quads.append(Quad(
                            vertices=verts_cs2, normal=normal_cs2,
                            block_type="minecraft:water",
                            face_dir=face_dir,
                            block_pos=(int(bx), int(by), int(bz))
                        ))

        # Generate trigger_hurt quads for damage blocks (magma, cactus, etc.)
        # Always generate all 6 faces (no culling) so the trigger_hurt entity
        # forms a sealed volume that damages from every direction.
        if separate_liquids and np.any(damage_mask):
            visible_dmg = damage_mask.copy()

            dmg_positions = np.argwhere(visible_dmg)
            if len(dmg_positions) > 0:
                verts_offsets = np.array(face_def["verts"], dtype=np.float64)
                mnx, mny, mnz = face_def["normal_mc"]
                normal_cs2 = mc_to_cs2(mnx, mny, mnz)
                ox, oy, oz = offset

                for i in range(len(dmg_positions)):
                    bx, by, bz = dmg_positions[i]
                    block = palette[int(blocks[bx, by, bz])]
                    verts_cs2 = []
                    for vx, vy, vz in verts_offsets:
                        mx = (bx + vx) * scale
                        my = (by + vy) * scale
                        mz = (bz + vz) * scale
                        verts_cs2.append((mx + ox, -mz + oy, my + oz))
                    damage_quads.append(Quad(
                        vertices=verts_cs2, normal=normal_cs2,
                        block_type=block, face_dir=face_dir,
                        block_pos=(int(bx), int(by), int(bz))
                    ))

        faces_done += 1
        if progress_callback:
            progress_callback(faces_done, total_faces)

    # --- Climbable blocks: thin collision slabs based on facing direction ---
    # Facing = "direction the ladder faces" (toward the player).
    # The ladder back is ON that side of the block: facing=north → back at z=0.
    if generate_climbable and np.any(climbable_mask):
        thickness = 0.25  # block units (= 16 Hammer units at scale=64)
        climb_positions = np.argwhere(climbable_mask)
        for i in range(len(climb_positions)):
            bx, by, bz = climb_positions[i]
            block = palette[int(blocks[bx, by, bz])]
            base = get_block_base_name(block)
            props = _parse_block_state(block)
            bp = (int(bx), int(by), int(bz))

            boxes = []
            if base == "minecraft:ladder":
                facing = props.get("facing", "north")
                # facing = direction the ladder front faces (away from the wall)
                # The back of the ladder attaches to the opposite wall.
                if facing == "north":
                    boxes.append((0, 0, 1 - thickness, 1, 1, 1))
                elif facing == "south":
                    boxes.append((0, 0, 0, 1, 1, thickness))
                elif facing == "east":
                    boxes.append((0, 0, 0, thickness, 1, 1))
                elif facing == "west":
                    boxes.append((1 - thickness, 0, 0, 1, 1, 1))
            elif base == "minecraft:vine":
                if props.get("north") == "true":
                    boxes.append((0, 0, 0, 1, 1, thickness))
                if props.get("south") == "true":
                    boxes.append((0, 0, 1 - thickness, 1, 1, 1))
                if props.get("east") == "true":
                    boxes.append((1 - thickness, 0, 0, 1, 1, 1))
                if props.get("west") == "true":
                    boxes.append((0, 0, 0, thickness, 1, 1))
                if not boxes:
                    boxes.append((0.25, 0, 0.25, 0.75, 1, 0.75))
            else:
                # Vertical vines (cave_vines, twisting_vines, weeping_vines)
                boxes.append((0.25, 0, 0.25, 0.75, 1, 0.75))

            for x0, y0, z0, x1, y1, z1 in boxes:
                climbable_quads.extend(
                    _generate_box_quads(int(bx), int(by), int(bz),
                                       x0, y0, z0, x1, y1, z1,
                                       block, scale, offset, bp))

    # --- Slime blocks: trigger 64 units ABOVE the slime so player enters
    #     it while still falling (before touching the solid surface). ---
    if generate_slime and np.any(slime_mask):
        trigger_top = 1.0 + 64.0 / scale
        slime_positions = np.argwhere(slime_mask)
        for i in range(len(slime_positions)):
            bx, by, bz = slime_positions[i]
            block = palette[int(blocks[bx, by, bz])]
            bp = (int(bx), int(by), int(bz))
            slime_quads.extend(
                _generate_box_quads(int(bx), int(by), int(bz),
                                   0, 1, 0, 1, trigger_top, 1,
                                   block, scale, offset, bp))

    # --- Stair clip ramps: sloped wedge over each stair to assist walking up ---
    if generate_stair_clips and np.any(stair_mask):
        stair_positions = np.argwhere(stair_mask)
        for i in range(len(stair_positions)):
            bx, by, bz = stair_positions[i]
            block = palette[int(blocks[bx, by, bz])]
            props = _parse_block_state(block)
            bp = (int(bx), int(by), int(bz))
            half = props.get("half", "bottom")
            facing = props.get("facing", "north")

            # Skip corner stairs — ramps only for straight shapes
            shape = props.get("shape", "straight")
            if shape != "straight":
                continue

            if half == "bottom":
                # Skip ramps for stairs inside water/lava
                if liquid_mask[bx, by, bz] or waterlogged_mask[bx, by, bz]:
                    continue

                stair_clip_quads.extend(
                    _generate_ramp_quads(int(bx), int(by), int(bz),
                                        facing, block, scale, offset, bp))

                # Inter-stair ramp: if a same-facing stair is one block ahead
                # and one block above, add a half-sized bridge ramp
                # from y=1.0..1.25 over the top step.
                ahead_offsets = {
                    "north": (0, 1, -1),
                    "south": (0, 1, 1),
                    "east": (1, 1, 0),
                    "west": (-1, 1, 0),
                }
                dx, dy, dz = ahead_offsets.get(facing, (0, 0, 0))
                nx, ny, nz = int(bx)+dx, int(by)+dy, int(bz)+dz
                if (0 <= nx < W and 0 <= ny < H and 0 <= nz < L
                        and stair_mask[nx, ny, nz]):
                    nb = palette[int(blocks[nx, ny, nz])]
                    nprops = _parse_block_state(nb)
                    if (nprops.get("facing") == facing
                            and nprops.get("half", "bottom") == "bottom"
                            and nprops.get("shape", "straight") == "straight"):
                        stair_clip_quads.extend(
                            _generate_ramp_quads(int(bx), int(by), int(bz),
                                                facing, block, scale, offset,
                                                bp, y_base=1.0, y_top=1.25,
                                                bridge=True))

                # Ground approach ramp: half-sized ramp from ground level
                # up to y=0.25 at the stair's open side (player steps the rest).
                approach_offsets = {
                    "north": (0, 0, 1),
                    "south": (0, 0, -1),
                    "east":  (-1, 0, 0),
                    "west":  (1, 0, 0),
                }
                adx, ady, adz = approach_offsets.get(facing, (0, 0, 1))
                ax, ay, az = int(bx)+adx, int(by)+ady, int(bz)+adz
                if (0 <= ax < W and 0 <= ay < H and 0 <= az < L):
                    a_idx = blocks[ax, ay, az]
                    # Skip if approach position is in water/lava
                    if liquid_mask[ax, ay, az] or waterlogged_mask[ax, ay, az]:
                        pass
                    elif not (solid_lut[a_idx] or stair_mask[ax, ay, az]
                              or half_height_mask[ax, ay, az]):
                        ba_y = ay - 1
                        if ba_y >= 0 and (solid_lut[blocks[ax, ba_y, az]]
                                          or stair_mask[ax, ba_y, az]
                                          or half_height_mask[ax, ba_y, az]):
                            stair_clip_quads.extend(
                                _generate_ramp_quads(
                                    ax, ay, az, facing, block, scale,
                                    offset, (ax, ay, az),
                                    y_base=0, y_top=0.25, bridge=True))

    # --- Slab / half-height block ramps: half-block slope clips ---
    # Uses the same half-block bridge ramp as stairs, placed at the neighbor.
    _approach_to_facing = {
        "north": "south", "south": "north",
        "east": "west", "west": "east",
    }
    if generate_stair_clips and np.any(half_height_mask):
        hh_positions = np.argwhere(half_height_mask)
        for i in range(len(hh_positions)):
            bx, by, bz = hh_positions[i]
            block = palette[int(blocks[bx, by, bz])]
            props = _parse_block_state(block)

            # Only bottom slabs (type=bottom or absent) get ramps.
            slab_type = props.get("type", "bottom")
            if slab_type != "bottom":
                continue

            # Skip ramps for slabs inside water/lava
            if liquid_mask[bx, by, bz] or waterlogged_mask[bx, by, bz]:
                continue

            # Height guard: skip if block above slab makes total >= 1 block
            above_y = int(by) + 1
            if above_y < H:
                ab_idx = blocks[int(bx), above_y, int(bz)]
                if (solid_lut[ab_idx] or stair_mask[int(bx), above_y, int(bz)]
                        or half_height_mask[int(bx), above_y, int(bz)]):
                    continue

            base = get_block_base_name(block)
            slab_height = 6.0 / 16.0 if base == "minecraft:daylight_detector" else 0.5

            # Check 4 horizontal neighbors for ground accessibility.
            horiz = [("north", 0, 0, -1), ("south", 0, 0, 1),
                     ("east", 1, 0, 0), ("west", -1, 0, 0)]
            for approach, ddx, ddy, ddz in horiz:
                nx2, ny2, nz2 = int(bx)+ddx, int(by)+ddy, int(bz)+ddz
                if not (0 <= nx2 < W and 0 <= ny2 < H and 0 <= nz2 < L):
                    continue
                # Skip if neighbor is in water/lava
                if liquid_mask[nx2, ny2, nz2] or waterlogged_mask[nx2, ny2, nz2]:
                    continue
                # Neighbor must be open: not solid, not another slab/stair,
                # and not a model block (fence, torch, etc.)
                n_idx = blocks[nx2, ny2, nz2]
                if (solid_lut[n_idx] or half_height_mask[nx2, ny2, nz2]
                        or stair_mask[nx2, ny2, nz2]
                        or model_lut[n_idx]):
                    continue
                # Block below neighbor must be solid walkable ground
                below_y = ny2 - 1
                if below_y < 0:
                    continue
                b_idx = blocks[nx2, below_y, nz2]
                if not (solid_lut[b_idx] or half_height_mask[nx2, below_y, nz2]
                        or stair_mask[nx2, below_y, nz2]):
                    continue
                # Place half-sized bridge ramp at the NEIGHBOR position
                ramp_facing = _approach_to_facing[approach]
                stair_clip_quads.extend(
                    _generate_ramp_quads(nx2, ny2, nz2,
                                        ramp_facing, block, scale, offset,
                                        (nx2, ny2, nz2),
                                        y_base=0, y_top=slab_height * 0.5,
                                        bridge=True))

    # --- Second pass: model blocks ---
    if model_generator is not None:
        model_positions = np.argwhere(model_mask)
        for i in range(len(model_positions)):
            bx, by, bz = model_positions[i]
            block = palette[int(blocks[bx, by, bz])]

            # Build neighbor solid info for cullface checks
            neighbor_solid_map = {}
            for mc_face, face_def in FACE_DEFS.items():
                dx, dy, dz = face_def["neighbor"]
                nx, ny, nz = int(bx)+dx, int(by)+dy, int(bz)+dz
                if 0 <= nx < W and 0 <= ny < H and 0 <= nz < L:
                    neighbor_solid_map[mc_face] = bool(solid_lut[blocks[nx, ny, nz]])
                else:
                    neighbor_solid_map[mc_face] = False
            # Map from our face_dir back to MC face names for cullface
            dir_to_mc = {"+x": "east", "-x": "west", "+y": "up", "-y": "down",
                         "+z": "south", "-z": "north"}
            mc_neighbor = {dir_to_mc[fd]: v for fd, v in neighbor_solid_map.items()
                          if fd in dir_to_mc}

            model_quads = model_generator.generate_quads(
                block, (int(bx), int(by), int(bz)),
                scale=scale, offset=offset,
                neighbor_solid=mc_neighbor
            )
            if not model_quads:
                # Fallback for blocks without JSON model data (chests, beds).
                # Use correct box height for slabs, cull faces against solids.
                fb_y0, fb_y1 = 0, 1
                if is_half_height_block(block):
                    fb_props = _parse_block_state(block)
                    fb_stype = fb_props.get("type", "bottom")
                    if fb_stype == "bottom":
                        fb_y1 = 0.5
                    elif fb_stype == "top":
                        fb_y0 = 0.5
                for q in _generate_box_quads(
                        int(bx), int(by), int(bz),
                        0, fb_y0, 0, 1, fb_y1, 1,
                        block, scale, offset,
                        (int(bx), int(by), int(bz))):
                    mc_fn = dir_to_mc.get(q.face_dir)
                    if mc_fn and mc_neighbor.get(mc_fn, False):
                        continue
                    model_quads.append(q)
            quads.extend(model_quads)

    # --- Collect light source positions for auto-lighting ---
    light_sources = []
    if generate_lights and np.any(light_lut[blocks]):
        ox, oy, oz = offset
        # Block lights sit further out (1 block from surface).
        # Model lights (torches) stay at the block center.
        block_light_offset = scale * 1.5
        light_positions = np.argwhere(light_lut[blocks])
        for i in range(len(light_positions)):
            bx, by, bz = light_positions[i]
            block = palette[int(blocks[bx, by, bz])]
            mx = (bx + 0.5) * scale
            my = (by + 0.5) * scale
            mz = (bz + 0.5) * scale

            is_block_light = not model_lut[blocks[int(bx), int(by), int(bz)]]

            if is_block_light:
                # Full-block light: place one light per exposed face,
                # offset 1.5*scale from center (≈1 block from surface).
                six_dirs = [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]
                for ddx, ddy, ddz in six_dirs:
                    nx2, ny2, nz2 = int(bx)+ddx, int(by)+ddy, int(bz)+ddz
                    if (0 <= nx2 < W and 0 <= ny2 < H and 0 <= nz2 < L
                            and solid_lut[blocks[nx2, ny2, nz2]]):
                        continue
                    off_cs2 = mc_to_cs2(ddx, ddy, ddz)
                    cs2_x = mx + ox + off_cs2[0] * block_light_offset
                    cs2_y = -mz + oy + off_cs2[1] * block_light_offset
                    cs2_z = my + oz + off_cs2[2] * block_light_offset
                    light_sources.append((cs2_x, cs2_y, cs2_z, block))
            else:
                # Model light (torch, lantern, etc.): place at block center.
                cs2_x = mx + ox
                cs2_y = -mz + oy
                cs2_z = my + oz
                light_sources.append((cs2_x, cs2_y, cs2_z, block))

    return quads, water_quads, lava_quads, damage_quads, climbable_quads, slime_quads, stair_clip_quads, light_sources


def group_quads_by_material(quads: list[Quad]) -> dict[str, list[Quad]]:
    """Group quads by block type for per-material mesh output."""
    groups = {}
    for quad in quads:
        base_name = get_block_base_name(quad.block_type)
        if base_name not in groups:
            groups[base_name] = []
        groups[base_name].append(quad)
    return groups


def group_quads_by_face_dir(quads: list[Quad]) -> dict[str, list[Quad]]:
    """Group quads by face direction to ensure manifold half-edge topology.

    Faces from different directions (e.g. +x and -y) can share edges with the
    same traversal direction, creating non-manifold edges that break the
    half-edge data structure. Separating by face_dir prevents this.
    """
    groups = {}
    for quad in quads:
        d = quad.face_dir
        if d not in groups:
            groups[d] = []
        groups[d].append(quad)
    return groups


def group_quads_by_block_pos(quads: list[Quad]) -> dict[tuple, list[Quad]]:
    """Group quads by source block position — each block becomes its own mesh."""
    groups = {}
    for quad in quads:
        pos = quad.block_pos
        if pos not in groups:
            groups[pos] = []
        groups[pos].append(quad)
    return groups


def group_quads_merge_connected(quads: list[Quad]) -> list[list[Quad]]:
    """Group quads by flood-filling connected same-type blocks.

    Uses 6-connected adjacency (±x, ±y, ±z) to find connected components
    of same block type. All quads belonging to a connected component are
    grouped together into one mesh.

    Returns:
        List of quad groups (each group is a list of Quads).
    """
    # Build position -> block_type map and position -> quads map
    pos_type = {}
    pos_quads = {}
    for quad in quads:
        pos = quad.block_pos
        pos_type[pos] = get_block_base_name(quad.block_type)
        if pos not in pos_quads:
            pos_quads[pos] = []
        pos_quads[pos].append(quad)

    # BFS flood fill to find connected components of same type
    visited = set()
    components = []  # list of lists of quads
    neighbors_6 = [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]

    for start_pos in pos_type:
        if start_pos in visited:
            continue
        visited.add(start_pos)
        component_quads = list(pos_quads[start_pos])
        block_type = pos_type[start_pos]

        q = deque([start_pos])
        while q:
            cx, cy, cz = q.popleft()
            for dx, dy, dz in neighbors_6:
                nb = (cx + dx, cy + dy, cz + dz)
                if nb in visited or nb not in pos_type:
                    continue
                if pos_type[nb] == block_type:
                    visited.add(nb)
                    component_quads.extend(pos_quads[nb])
                    q.append(nb)

        components.append(component_quads)

    return components


def group_quads_by_chunk(quads: list[Quad], chunk_size: float) -> dict[tuple, list[Quad]]:
    """Group quads by spatial chunk for chunked mesh output."""
    groups = {}
    for quad in quads:
        # Use center of quad for chunk assignment
        cx = sum(v[0] for v in quad.vertices) / 4.0
        cy = sum(v[1] for v in quad.vertices) / 4.0
        cz = sum(v[2] for v in quad.vertices) / 4.0
        chunk_key = (
            int(cx // chunk_size),
            int(cy // chunk_size),
            int(cz // chunk_size)
        )
        if chunk_key not in groups:
            groups[chunk_key] = []
        groups[chunk_key].append(quad)
    return groups
