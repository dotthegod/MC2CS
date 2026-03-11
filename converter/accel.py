"""Acceleration layer — uses Rust (mctocs_rust) when available, falls back to pure Python.

Import from here instead of directly from halfedge / greedy_mesh to get
automatic Rust acceleration:

    from converter.accel import build_halfedge_mesh, generate_greedy_quads
"""

RUST_AVAILABLE = False

try:
    from mctocs_rust import (
        Quad as RustQuad,
        HalfEdgeMesh as RustHalfEdgeMesh,
        build_halfedge_mesh as _rust_build_halfedge_mesh,
        compute_face_texcoords as rust_compute_face_texcoords,
        compute_face_tangent as rust_compute_face_tangent,
        compute_texture_axes as rust_compute_texture_axes,
        generate_greedy_quads as _rust_generate_greedy_quads,
        write_vmap_string as rust_write_vmap_string,
    )
    RUST_AVAILABLE = True
except ImportError:
    pass

# Always import Python versions (kept as fallback and for compatibility)
from converter.halfedge import (
    HalfEdgeMesh as PyHalfEdgeMesh,
    build_halfedge_mesh as _py_build_halfedge_mesh,
    compute_face_texcoords as py_compute_face_texcoords,
    compute_face_tangent as py_compute_face_tangent,
    compute_texture_axes as py_compute_texture_axes,
)
from converter.mesh_generator import Quad as PyQuad
from converter.greedy_mesh import generate_greedy_quads as _py_generate_greedy_quads


def _convert_quad_to_rust(quad):
    """Convert a Python Quad to a Rust Quad."""
    return RustQuad(
        vertices=list(quad.vertices),
        normal=tuple(quad.normal),
        block_type=quad.block_type,
        face_dir=quad.face_dir,
        block_pos=tuple(quad.block_pos) if quad.block_pos else (0.0, 0.0, 0.0),
        texcoords=list(quad.texcoords) if quad.texcoords else None,
        texture_name=quad.texture_name if hasattr(quad, 'texture_name') else None,
    )


def _convert_rust_mesh_to_python(rust_mesh):
    """Convert a Rust HalfEdgeMesh to a Python HalfEdgeMesh for writer compatibility."""
    # Convert Rust Quad objects back to Python Quad objects
    py_quads = []
    for rq in rust_mesh.face_quads:
        py_quads.append(PyQuad(
            vertices=list(rq.vertices),
            normal=rq.normal,
            block_type=rq.block_type,
            face_dir=rq.face_dir,
            block_pos=rq.block_pos,
            texcoords=list(rq.texcoords) if rq.texcoords else None,
            texture_name=rq.texture_name,
        ))

    return PyHalfEdgeMesh(
        vertex_positions=list(rust_mesh.vertex_positions),
        vertex_edge_indices=list(rust_mesh.vertex_edge_indices),
        vertex_data_indices=list(rust_mesh.vertex_data_indices),
        edge_vertex_indices=list(rust_mesh.edge_vertex_indices),
        edge_opposite_indices=list(rust_mesh.edge_opposite_indices),
        edge_next_indices=list(rust_mesh.edge_next_indices),
        edge_face_indices=list(rust_mesh.edge_face_indices),
        edge_data_indices=list(rust_mesh.edge_data_indices),
        edge_vertex_data_indices=list(rust_mesh.edge_vertex_data_indices),
        face_edge_indices=list(rust_mesh.face_edge_indices),
        face_data_indices=list(rust_mesh.face_data_indices),
        face_normals=list(rust_mesh.face_normals),
        face_quads=py_quads,
        num_vertices=rust_mesh.num_vertices,
        num_half_edges=rust_mesh.num_half_edges,
        num_geometric_edges=rust_mesh.num_geometric_edges,
        num_faces=rust_mesh.num_faces,
    )


def build_halfedge_mesh(quads):
    """Build half-edge mesh — uses Rust when available."""
    if RUST_AVAILABLE:
        rust_quads = [_convert_quad_to_rust(q) for q in quads]
        rust_mesh = _rust_build_halfedge_mesh(rust_quads)
        return _convert_rust_mesh_to_python(rust_mesh)
    return _py_build_halfedge_mesh(quads)


def generate_greedy_quads(grid, scale=64.0, offset=(0.0, 0.0, 0.0),
                          progress_callback=None):
    """Generate greedy quads — uses Rust when available."""
    if RUST_AVAILABLE:
        import numpy as np
        from config.blocks import (should_generate_geometry, is_solid_for_culling,
                                   get_block_base_name)

        # Flatten block grid for Rust
        blocks_flat = grid.blocks.flatten(order='C').astype(np.int32).tolist()

        # Build sets for Rust
        should_gen_set = set()
        solid_cull_set = set()
        for idx, name in grid.palette.items():
            base = get_block_base_name(name)
            if should_generate_geometry(name):
                should_gen_set.add(base)
            if is_solid_for_culling(name):
                solid_cull_set.add(base)
                solid_cull_set.add(name)

        rust_quads = _rust_generate_greedy_quads(
            blocks_flat, grid.palette, grid.width, grid.height, grid.length,
            scale, offset, should_gen_set, solid_cull_set, progress_callback,
        )

        # Convert Rust quads to Python quads
        return [PyQuad(
            vertices=list(rq.vertices),
            normal=rq.normal,
            block_type=rq.block_type,
            face_dir=rq.face_dir,
        ) for rq in rust_quads]

    return _py_generate_greedy_quads(grid, scale, offset, progress_callback)


# Re-export texture helpers with automatic conversion
if RUST_AVAILABLE:
    def compute_face_texcoords(quad, scale=64.0):
        if isinstance(quad, PyQuad):
            quad = _convert_quad_to_rust(quad)
        return rust_compute_face_texcoords(quad, scale)

    def compute_face_tangent(normal):
        return rust_compute_face_tangent(normal)

    def compute_texture_axes(normal):
        return rust_compute_texture_axes(normal)
else:
    compute_face_texcoords = py_compute_face_texcoords
    compute_face_tangent = py_compute_face_tangent
    compute_texture_axes = py_compute_texture_axes
