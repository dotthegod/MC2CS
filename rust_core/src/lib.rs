//! MCtoCS Rust core — high-performance half-edge mesh builder, greedy meshing,
//! and VMap writer exposed to Python via PyO3.

mod halfedge;
mod greedy_mesh;
mod vmap_writer;

use pyo3::prelude::*;

/// The main Python module. Importable as `import mctocs_rust`.
#[pymodule]
fn mctocs_rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<halfedge::PyQuad>()?;
    m.add_class::<halfedge::PyHalfEdgeMesh>()?;
    m.add_function(wrap_pyfunction!(halfedge::build_halfedge_mesh, m)?)?;
    m.add_function(wrap_pyfunction!(halfedge::compute_face_texcoords, m)?)?;
    m.add_function(wrap_pyfunction!(halfedge::compute_face_tangent, m)?)?;
    m.add_function(wrap_pyfunction!(halfedge::compute_texture_axes, m)?)?;

    m.add_function(wrap_pyfunction!(greedy_mesh::generate_greedy_quads, m)?)?;

    m.add_function(wrap_pyfunction!(vmap_writer::write_vmap_string, m)?)?;

    Ok(())
}
