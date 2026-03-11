"""Half-edge mesh builder: converts quads to CDmePolygonMesh topology for CS2 .vmap files.

This module builds the complete half-edge data structure that Source 2 uses for polygon
mesh representation.  Half-edges are stored as consecutive twin pairs:
    [he0, twin0, he1, twin1, ...]
so edgeOppositeIndices is always [1,0, 3,2, 5,4, ...] and edgeDataIndices is
always [0,0, 1,1, 2,2, ...].  Boundary twins get edgeFaceIndices == -1 and
zero normals / tangents in faceVertexData.
"""

import math
from dataclasses import dataclass, field
from collections import defaultdict
from converter.mesh_generator import Quad


EPSILON = 1e-6


def _vec_key(v: tuple) -> tuple:
    """Round vertex to avoid floating point comparison issues."""
    return (round(v[0], 4), round(v[1], 4), round(v[2], 4))


@dataclass
class HalfEdgeMesh:
    """Complete half-edge mesh data ready for VMap serialization."""
    # Vertex data
    vertex_positions: list          # list of (x, y, z) tuples
    vertex_edge_indices: list[int]  # one half-edge index per vertex
    vertex_data_indices: list[int]  # maps vertex -> position data index (0..V-1)

    # Edge (half-edge) data — stored as consecutive twin pairs
    edge_vertex_indices: list[int]   # to_vertex for each half-edge
    edge_opposite_indices: list[int] # always [1,0, 3,2, 5,4, ...]
    edge_next_indices: list[int]     # next half-edge in face/boundary loop
    edge_face_indices: list[int]     # face index (-1 for boundary)
    edge_data_indices: list[int]     # always [0,0, 1,1, 2,2, ...]
    edge_vertex_data_indices: list[int]  # maps half-edge -> faceVertexData index

    # Face data
    face_edge_indices: list[int]  # one half-edge per face (into the face loop)
    face_data_indices: list[int]  # maps face -> face data index (0..F-1)

    # Per-face info for computing attributes
    face_normals: list   # (nx, ny, nz) per face
    face_quads: list     # original Quad per face

    # Counts
    num_vertices: int = 0
    num_half_edges: int = 0        # total (always even)
    num_geometric_edges: int = 0   # = num_half_edges // 2
    num_faces: int = 0


def build_halfedge_mesh(quads: list[Quad]) -> HalfEdgeMesh:
    """Build a HalfEdgeMesh from a list of quads.

    The output stores half-edges as consecutive twin pairs so that
    edgeOppositeIndices is always [1,0,3,2,...] and edgeDataIndices
    is always [0,0,1,1,...], matching the format CS2 Hammer expects.
    """
    if not quads:
        return HalfEdgeMesh(
            vertex_positions=[], vertex_edge_indices=[], vertex_data_indices=[],
            edge_vertex_indices=[], edge_opposite_indices=[], edge_next_indices=[],
            edge_face_indices=[], edge_data_indices=[], edge_vertex_data_indices=[],
            face_edge_indices=[], face_data_indices=[],
            face_normals=[], face_quads=[]
        )

    # ------------------------------------------------------------------
    # 1. Collect unique vertices
    # ------------------------------------------------------------------
    vertex_map = {}   # _vec_key -> vertex index
    vertices = []

    for quad in quads:
        for v in quad.vertices:
            key = _vec_key(v)
            if key not in vertex_map:
                vertex_map[key] = len(vertices)
                vertices.append(v)

    num_verts = len(vertices)
    num_faces = len(quads)

    # ------------------------------------------------------------------
    # 2. Build temporary face half-edges (sequentially per face)
    # ------------------------------------------------------------------
    # Temporary storage: each entry is one half-edge
    tmp_from = []
    tmp_to = []
    tmp_face = []
    tmp_next = []        # index into tmp arrays
    tmp_fv_idx = []      # face-vertex data index for TO vertex

    face_first_tmp = []  # first tmp index per face
    face_normals_list = []
    face_quads_list = []
    fv_counter = 0

    for fi, quad in enumerate(quads):
        face_normals_list.append(quad.normal)
        face_quads_list.append(quad)

        v_indices = [vertex_map[_vec_key(v)] for v in quad.vertices]
        n = len(v_indices)
        first = len(tmp_from)
        face_first_tmp.append(first)

        for ei in range(n):
            tmp_from.append(v_indices[ei])
            tmp_to.append(v_indices[(ei + 1) % n])
            tmp_face.append(fi)
            tmp_fv_idx.append(fv_counter + (ei + 1) % n)
            tmp_next.append(first + (ei + 1) % n)

        fv_counter += n

    num_tmp = len(tmp_from)

    # ------------------------------------------------------------------
    # 3. Pair face half-edges and create boundary twins
    # ------------------------------------------------------------------
    edge_lookup = defaultdict(list)
    for i in range(num_tmp):
        edge_lookup[(tmp_from[i], tmp_to[i])].append(i)

    partner = [-1] * num_tmp   # tmp index of paired face HE (-1 = needs boundary twin)
    used = [False] * num_tmp

    for i in range(num_tmp):
        if partner[i] != -1:
            continue
        opp_key = (tmp_to[i], tmp_from[i])
        for j in edge_lookup.get(opp_key, []):
            if partner[j] == -1 and j != i:
                partner[i] = j
                partner[j] = i
                break

    # Collect boundary face HEs (those without a face partner)
    boundary_face_hes = [i for i in range(num_tmp) if partner[i] == -1]

    # ------------------------------------------------------------------
    # 4. Build final half-edge list as consecutive twin pairs
    #    Pair types:
    #      A) Two face HEs that are twins: [face_he_A, face_he_B]
    #      B) One face HE + one boundary twin: [face_he, boundary_twin]
    # ------------------------------------------------------------------
    # Assign final indices.  We process pairs once: iterate face HEs,
    # skip if already assigned.
    final_count = 0
    tmp_to_final = [-1] * num_tmp          # tmp index -> final index
    # For boundary twins we track them separately
    boundary_twins = []  # list of (from_v, to_v, partner_face_he_tmp_idx)

    # Type A: paired face HEs
    for i in range(num_tmp):
        if tmp_to_final[i] != -1:
            continue
        j = partner[i]
        if j != -1:
            # Two face HEs
            tmp_to_final[i] = final_count
            tmp_to_final[j] = final_count + 1
            final_count += 2
        # else handled below

    # Type B: face HE + boundary twin
    for i in boundary_face_hes:
        tmp_to_final[i] = final_count
        boundary_twins.append((tmp_to[i], tmp_from[i], i, final_count + 1))
        final_count += 2

    num_he = final_count
    num_geo_edges = num_he // 2

    # ------------------------------------------------------------------
    # 5. Populate final arrays
    # ------------------------------------------------------------------
    out_to = [0] * num_he
    out_opp = [0] * num_he
    out_next = [0] * num_he
    out_face = [0] * num_he
    out_edge_data = [0] * num_he
    out_fv_data = [0] * num_he

    # 5a. Fill face half-edges
    for i in range(num_tmp):
        fi = tmp_to_final[i]
        out_to[fi] = tmp_to[i]
        out_face[fi] = tmp_face[i]
        out_next[fi] = tmp_to_final[tmp_next[i]]
        out_fv_data[fi] = tmp_fv_idx[i]

    # 5b. Fill twin-pair structure (opposite + edge_data)
    for pair_idx in range(num_geo_edges):
        a = pair_idx * 2
        b = pair_idx * 2 + 1
        out_opp[a] = b
        out_opp[b] = a
        out_edge_data[a] = pair_idx
        out_edge_data[b] = pair_idx

    # 5c. Fill boundary twins
    for b_from, b_to, face_tmp, b_final in boundary_twins:
        out_to[b_final] = b_to
        out_face[b_final] = -1
        out_fv_data[b_final] = b_final  # maps to its own slot (will hold zeros)

    # 5d-pre. Split non-manifold vertices.
    # A vertex is non-manifold if the fan of faces around it has multiple
    # disconnected components.  This happens when blocks share vertex
    # positions at 3D corners/edges but the faces around that position
    # come from different surface patches.  We detect these and duplicate
    # the vertex once per fan component so the half-edge mesh is manifold.
    # ------------------------------------------------------------------
    # Gather outgoing HE indices per vertex (FROM vertex)
    _vert_out = defaultdict(set)
    # Also build reverse index: vertex -> list of HEs pointing TO it.
    # This avoids an O(V_nonmanifold * E) scan when updating to-vertices.
    _vert_in = defaultdict(list)
    for he in range(num_he):
        from_v = out_to[out_opp[he]]
        _vert_out[from_v].add(he)
        _vert_in[out_to[he]].append(he)

    for v in list(_vert_out.keys()):
        out_hes = _vert_out[v]
        if len(out_hes) < 2:
            continue

        # Fan-walk to find connected groups
        remaining = set(out_hes)
        groups = []
        while remaining:
            start = next(iter(remaining))
            group = [start]
            remaining.discard(start)

            # Walk CW: face HE h -> prev_in_quad -> twin
            h = start
            while True:
                if out_face[h] != -1:
                    prev_h = out_next[out_next[out_next[h]]]
                    nxt = out_opp[prev_h]
                    if nxt in remaining:
                        group.append(nxt)
                        remaining.discard(nxt)
                        h = nxt
                    else:
                        break
                else:
                    break

            # Walk CCW: twin(h) -> next
            h = start
            while True:
                twin = out_opp[h]
                if out_face[twin] != -1:
                    nxt = out_next[twin]
                    if nxt in remaining:
                        group.append(nxt)
                        remaining.discard(nxt)
                        h = nxt
                    else:
                        break
                else:
                    break

            groups.append(group)

        if len(groups) <= 1:
            continue  # manifold vertex, nothing to do

        # Split: group 0 keeps original vertex v.
        # Groups 1..N get new vertex copies.
        he_group = {}
        for gi, grp in enumerate(groups):
            for he in grp:
                he_group[he] = gi

        new_vertex_ids = [v]  # group 0 -> v
        for _ in range(1, len(groups)):
            new_idx = len(vertices)
            vertices.append(vertices[v])
            new_vertex_ids.append(new_idx)

        # Update HEs that point TO v using the prebuilt reverse index
        for he in _vert_in[v]:
            outgoing = out_opp[he]
            gi = he_group.get(outgoing, 0)
            out_to[he] = new_vertex_ids[gi]

    num_verts = len(vertices)
    # ------------------------------------------------------------------

    # 5d. Link boundary twin next pointers
    # For boundary HE `b` going → V (to_v = V), find the next boundary
    # HE that leaves V.  Walk the fan of faces around V:
    #   1. opp(b) is a face HE leaving V
    #   2. prev(opp(b)) is the face HE arriving at V in that face
    #      (for quads, prev = next^3)
    #   3. opp(prev) — if boundary, that's our answer
    #   4. otherwise it's a face HE leaving V on the adjacent face;
    #      repeat from step 2 with that HE.
    for b_from, b_to, face_tmp, b_final in boundary_twins:
        to_v = out_to[b_final]

        # Start: face HE leaving V (twin of our boundary HE)
        f = out_opp[b_final]

        found = False
        for _ in range(num_he):  # safety limit
            # prev(f) = the face HE arriving at V in this face
            p = out_next[out_next[out_next[f]]]
            t = out_opp[p]
            if out_face[t] == -1:
                # t is a boundary twin leaving V — that's our next
                out_next[b_final] = t
                found = True
                break
            # t is a face HE leaving V on the adjacent face; continue
            f = t

        if not found:
            # Fallback: self-loop (shouldn't happen in valid mesh)
            out_next[b_final] = b_final

    # ------------------------------------------------------------------
    # 6. Vertex edge indices (use updated num_verts after splitting)
    # ------------------------------------------------------------------
    vertex_edge = [-1] * num_verts
    for fi in range(num_he):
        from_v = _get_from_vertex(fi, out_to, out_opp)
        if vertex_edge[from_v] == -1:
            vertex_edge[from_v] = fi

    # ------------------------------------------------------------------
    # 7. Face edge indices (re-map from tmp first-HE to final index)
    # ------------------------------------------------------------------
    face_edge_indices = [tmp_to_final[face_first_tmp[fi]] for fi in range(num_faces)]

    # ------------------------------------------------------------------
    # 8. Remap faceVertexData indices so face-HE entries use their
    #    original face-vertex data index and boundary entries use
    #    dedicated slots. faceVertexData size = num_half_edges.
    #    We'll build a new mapping: final_he_index -> fvdata_index.
    #    Face HEs keep their original fv_idx (from tmp); boundary twins
    #    get unique indices after the face ones.
    #
    #    Actually, the simplest correct approach is:
    #    fvdata[final_idx] = final_idx, so edgeVertexDataIndices[i] = i
    #    and we generate faceVertexData in the order of final half-edges,
    #    outputting real data for face HEs and zeros for boundary twins.
    # ------------------------------------------------------------------
    # We'll use the simple identity mapping:
    for i in range(num_he):
        out_fv_data[i] = i

    # ------------------------------------------------------------------
    # Build mesh
    # ------------------------------------------------------------------
    return HalfEdgeMesh(
        vertex_positions=vertices,
        vertex_edge_indices=vertex_edge,
        vertex_data_indices=list(range(num_verts)),
        edge_vertex_indices=out_to,
        edge_opposite_indices=out_opp,
        edge_next_indices=out_next,
        edge_face_indices=out_face,
        edge_data_indices=out_edge_data,
        edge_vertex_data_indices=out_fv_data,
        face_edge_indices=face_edge_indices,
        face_data_indices=list(range(num_faces)),
        face_normals=face_normals_list,
        face_quads=face_quads_list,
        num_vertices=num_verts,
        num_half_edges=num_he,
        num_geometric_edges=num_geo_edges,
        num_faces=num_faces,
    )


def _get_from_vertex(he_idx: int, out_to: list, out_opp: list) -> int:
    """Get the from-vertex of a half-edge (= to-vertex of its opposite)."""
    return out_to[out_opp[he_idx]]


def compute_face_texcoords(quad: Quad, scale: float = 64.0) -> list[tuple]:
    """Compute UV texture coordinates for a quad's vertices.

    For axis-aligned faces, projects vertices onto the appropriate UV plane.
    Returns list of 4 (u, v) tuples.
    """
    verts = quad.vertices
    normal = quad.normal
    nx, ny, nz = normal

    # Determine dominant axis
    anx, any_, anz = abs(nx), abs(ny), abs(nz)

    if anz >= anx and anz >= any_:
        # Z-dominant (top/bottom in CS2): project onto XY
        # Negate Y because CS2-Y is flipped vs MC-Z
        coords = [(v[0], -v[1]) for v in verts]
    elif any_ >= anx:
        # Y-dominant: project onto XZ, negate Z so V decreases going up
        coords = [(v[0], -v[2]) for v in verts]
    else:
        # X-dominant: project onto YZ, negate Z so V decreases going up
        # Negate Y because CS2-Y is flipped vs MC-Z
        coords = [(-v[1], -v[2]) for v in verts]

    # Normalize UVs relative to first vertex
    base_u, base_v = coords[0]
    texcoords = []
    for u, v in coords:
        texcoords.append(((u - base_u) / scale, (v - base_v) / scale))

    return texcoords


def compute_face_tangent(normal: tuple) -> tuple:
    """Compute tangent vector for a face given its normal.
    Returns (tx, ty, tz, sign) where sign is the bitangent sign.
    """
    nx, ny, nz = normal
    anx, any_, anz = abs(nx), abs(ny), abs(nz)

    if anz >= anx and anz >= any_:
        # Z-dominant face: tangent along X
        if nz >= 0:
            return (1.0, 0.0, 0.0, -1.0)
        else:
            return (1.0, 0.0, 0.0, 1.0)
    elif any_ >= anx:
        # Y-dominant face: tangent along X
        if ny >= 0:
            return (1.0, 0.0, 0.0, 1.0)
        else:
            return (1.0, 0.0, 0.0, -1.0)
    else:
        # X-dominant face: tangent along -Y (negated for handedness fix)
        if nx >= 0:
            return (0.0, -1.0, 0.0, -1.0)
        else:
            return (0.0, -1.0, 0.0, 1.0)


def compute_texture_axes(normal: tuple) -> tuple:
    """Compute textureAxisU and textureAxisV for a face.
    Returns (axisU, axisV) where each is (x, y, z, offset).
    """
    nx, ny, nz = normal
    anx, any_, anz = abs(nx), abs(ny), abs(nz)
    if anz >= anx and anz >= any_:
        # Top/bottom: U=X, V=Y (Y negated in CS2, so V=Y gives correct orientation)
        return (1, 0, 0, 0), (0, 1, 0, 0)
    elif any_ >= anx:
        # Front/back: U=X, V=-Z (V increases downward = correct texture orientation)
        return (1, 0, 0, 0), (0, 0, -1, 0)
    else:
        # Left/right: U=-Y, V=-Z (Y negated in CS2)
        return (0, -1, 0, 0), (0, 0, -1, 0)
