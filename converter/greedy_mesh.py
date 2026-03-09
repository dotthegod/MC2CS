"""Greedy meshing: merges adjacent coplanar same-material quads into larger rectangles."""

import numpy as np
from parsers.block_grid import BlockGrid
from config.blocks import should_generate_geometry, is_solid_for_culling, get_block_base_name
from converter.mesh_generator import Quad, mc_to_cs2

# Face axis definitions for greedy meshing
# For each face direction: (slice_axis, u_axis, v_axis, normal_mc, is_positive)
GREEDY_FACE_DEFS = {
    "+x": {"slice_axis": 0, "u_axis": 2, "v_axis": 1, "normal_mc": (1, 0, 0), "neighbor_offset": (1, 0, 0), "pos_dir": True},
    "-x": {"slice_axis": 0, "u_axis": 2, "v_axis": 1, "normal_mc": (-1, 0, 0), "neighbor_offset": (-1, 0, 0), "pos_dir": False},
    "+y": {"slice_axis": 1, "u_axis": 0, "v_axis": 2, "normal_mc": (0, 1, 0), "neighbor_offset": (0, 1, 0), "pos_dir": True},
    "-y": {"slice_axis": 1, "u_axis": 0, "v_axis": 2, "normal_mc": (0, -1, 0), "neighbor_offset": (0, -1, 0), "pos_dir": False},
    "+z": {"slice_axis": 2, "u_axis": 1, "v_axis": 0, "normal_mc": (0, 0, 1), "neighbor_offset": (0, 0, 1), "pos_dir": True},
    "-z": {"slice_axis": 2, "u_axis": 1, "v_axis": 0, "normal_mc": (0, 0, -1), "neighbor_offset": (0, 0, -1), "pos_dir": False},
}

AXIS_SIZES = {0: "width", 1: "height", 2: "length"}


def _get_axis_size(grid: BlockGrid, axis: int) -> int:
    return [grid.width, grid.height, grid.length][axis]


def _get_block_at(grid: BlockGrid, coords: list) -> str:
    return grid.get_block(coords[0], coords[1], coords[2])


def _build_quad_verts(face_dir: str, slice_val: int, u_start: int, v_start: int,
                      u_end: int, v_end: int, face_def: dict) -> list:
    """Build 4 vertex positions for a greedy-merged quad.

    Returns vertices in Minecraft block coordinates (before scaling).
    """
    sa = face_def["slice_axis"]
    ua = face_def["u_axis"]
    va = face_def["v_axis"]

    # The slice position along the normal axis
    d = slice_val + 1 if face_def["pos_dir"] else slice_val

    # Build corners: (u_start, v_start), (u_end, v_start), (u_end, v_end), (u_start, v_end)
    corners = [
        (u_start, v_start),
        (u_end, v_start),
        (u_end, v_end),
        (u_start, v_end),
    ]

    verts = []
    for u, v in corners:
        pos = [0, 0, 0]
        pos[sa] = d
        pos[ua] = u
        pos[va] = v
        verts.append(tuple(pos))

    # Ensure correct winding when viewed from outside after the
    # handedness-flipping coordinate transform (negate Z→Y).
    if face_def["pos_dir"]:
        verts = [verts[0], verts[3], verts[2], verts[1]]

    return verts


def generate_greedy_quads(grid: BlockGrid, scale: float = 64.0,
                          offset: tuple = (0.0, 0.0, 0.0),
                          progress_callback=None) -> list[Quad]:
    """Generate optimized quads using greedy meshing algorithm.

    For each face direction, iterates through slices perpendicular to that axis.
    For each slice, builds a 2D grid of exposed block materials, then greedily
    merges adjacent same-material cells into larger rectangles.

    Returns list of Quad objects in CS2 coordinate space.
    """
    quads = []
    total_faces = 6
    face_count = 0

    for face_dir, face_def in GREEDY_FACE_DEFS.items():
        face_count += 1
        if progress_callback:
            progress_callback(face_count, total_faces)

        sa = face_def["slice_axis"]
        ua = face_def["u_axis"]
        va = face_def["v_axis"]
        noff = face_def["neighbor_offset"]

        slice_size = _get_axis_size(grid, sa)
        u_size = _get_axis_size(grid, ua)
        v_size = _get_axis_size(grid, va)

        for slice_val in range(slice_size):
            # Build 2D mask: material name or None
            mask = [[None] * v_size for _ in range(u_size)]

            for u in range(u_size):
                for v in range(v_size):
                    coords = [0, 0, 0]
                    coords[sa] = slice_val
                    coords[ua] = u
                    coords[va] = v

                    block = _get_block_at(grid, coords)
                    if not should_generate_geometry(block):
                        continue

                    # Check neighbor
                    n_coords = [coords[0] + noff[0], coords[1] + noff[1], coords[2] + noff[2]]
                    if (0 <= n_coords[0] < grid.width and
                            0 <= n_coords[1] < grid.height and
                            0 <= n_coords[2] < grid.length):
                        if is_solid_for_culling(_get_block_at(grid, n_coords)):
                            continue

                    mask[u][v] = get_block_base_name(block)

            # Greedy merge the 2D mask
            visited = [[False] * v_size for _ in range(u_size)]

            for u in range(u_size):
                for v in range(v_size):
                    if visited[u][v] or mask[u][v] is None:
                        continue

                    material = mask[u][v]

                    # Expand width (u direction)
                    w = 1
                    while u + w < u_size and mask[u + w][v] == material and not visited[u + w][v]:
                        w += 1

                    # Expand height (v direction)
                    h = 1
                    done = False
                    while v + h < v_size and not done:
                        for du in range(w):
                            if mask[u + du][v + h] != material or visited[u + du][v + h]:
                                done = True
                                break
                        if not done:
                            h += 1

                    # Mark as visited
                    for du in range(w):
                        for dv in range(h):
                            visited[u + du][v + dv] = True

                    # Create merged quad
                    verts_mc = _build_quad_verts(
                        face_dir, slice_val,
                        u, v, u + w, v + h,
                        face_def
                    )

                    # Scale and convert to CS2
                    verts_cs2 = []
                    for mx, my, mz in verts_mc:
                        sx, sy, sz = mx * scale, my * scale, mz * scale
                        cx, cy, cz = mc_to_cs2(sx, sy, sz)
                        verts_cs2.append((cx + offset[0], cy + offset[1], cz + offset[2]))

                    normal_cs2 = mc_to_cs2(*face_def["normal_mc"])

                    quads.append(Quad(
                        vertices=verts_cs2,
                        normal=normal_cs2,
                        block_type=f"minecraft:{material.split(':')[-1] if ':' in material else material}",
                        face_dir=face_dir
                    ))

    if progress_callback:
        progress_callback(total_faces, total_faces)

    return quads
