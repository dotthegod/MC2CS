//! VMap string writer — Rust port of the serialisation hot-path from
//! vmap/writer.py.
//!
//! Only the core `write_vmap_string` function is ported: it receives
//! pre-computed mesh topology and material data from Python and produces
//! the KeyValues2 DMX string much faster than Python string concatenation.
//!
//! The full `VMapWriter` class with entity logic stays in Python because
//! it is not a performance bottleneck and has complex branching.

use pyo3::prelude::*;
use uuid::Uuid;
use rand::Rng;
use std::fmt::Write as FmtWrite;

// ─── helpers ────────────────────────────────────────────────────────

#[inline]
fn uid() -> String {
    Uuid::new_v4().to_string()
}

#[inline]
#[allow(dead_code)]
fn rand_seed() -> i64 {
    let mut rng = rand::thread_rng();
    rng.gen_range(0..i32::MAX) as i64
}

#[inline]
#[allow(dead_code)]
fn rand_ref() -> String {
    let mut rng = rand::thread_rng();
    format!("0x{:016x}", rng.gen::<u64>())
}

#[inline]
fn fmt_g(v: f64) -> String {
    // Match Python's {:g} formatting (strip trailing zeros)
    if v == 0.0 {
        "0".to_string()
    } else if v == v.floor() && v.abs() < 1e15 {
        format!("{}", v as i64)
    } else {
        // Strip trailing zeros like Python's {:g}
        let s = format!("{}", v);
        if s.contains('.') {
            let trimmed = s.trim_end_matches('0').trim_end_matches('.');
            trimmed.to_string()
        } else {
            s
        }
    }
}

// ─── Writer ─────────────────────────────────────────────────────────

struct KV2Writer {
    buf: String,
    indent: usize,
}

impl KV2Writer {
    fn new(capacity: usize) -> Self {
        Self {
            buf: String::with_capacity(capacity),
            indent: 0,
        }
    }

    fn w(&mut self, text: &str) {
        for _ in 0..self.indent {
            self.buf.push('\t');
        }
        self.buf.push_str(text);
        self.buf.push('\n');
    }

    fn blank(&mut self) {
        self.buf.push('\n');
    }

    fn begin(&mut self, text: &str) {
        self.w(text);
        self.w("{");
        self.indent += 1;
    }

    fn end(&mut self) {
        self.indent -= 1;
        self.w("}");
    }

    fn prop(&mut self, name: &str, dtype: &str, value: &str) {
        for _ in 0..self.indent {
            self.buf.push('\t');
        }
        write!(self.buf, "\"{}\" \"{}\" \"{}\"\n", name, dtype, value).unwrap();
    }

    fn begin_array(&mut self, name: &str, dtype: &str) {
        for _ in 0..self.indent {
            self.buf.push('\t');
        }
        write!(self.buf, "\"{}\" \"{}\" \n", name, dtype).unwrap();
        self.w("[");
        self.indent += 1;
    }

    fn end_array(&mut self) {
        self.indent -= 1;
        self.w("]");
    }

    fn array_item(&mut self, value: &str) {
        for _ in 0..self.indent {
            self.buf.push('\t');
        }
        write!(self.buf, "\"{}\"\n", value).unwrap();
    }

    fn array_item_comma(&mut self, value: &str) {
        for _ in 0..self.indent {
            self.buf.push('\t');
        }
        write!(self.buf, "\"{}\",\n", value).unwrap();
    }

    fn trailing_comma(&mut self) {
        // Append comma to last non-empty line
        if let Some(pos) = self.buf.rfind('\n') {
            if pos > 0 {
                // Find the actual last content newline
                let _before = &self.buf[..pos];
                self.buf.insert(pos, ',');
            }
        }
    }

    fn write_data_stream(
        &mut self,
        name: &str,
        standard_attr: &str,
        semantic: &str,
        sem_idx: i32,
        data_state: i32,
        dtype: &str,
        data: &[String],
    ) {
        self.begin("\"CDmePolygonMeshDataStream\"");
        self.prop("id", "elementid", &uid());
        self.prop("name", "string", &format!("{}:{}", name, sem_idx));
        self.prop("standardAttributeName", "string", standard_attr);
        self.prop("semanticName", "string", semantic);
        self.prop("semanticIndex", "int", &sem_idx.to_string());
        self.prop("vertexBufferLocation", "int", "0");
        self.prop("dataStateFlags", "int", &data_state.to_string());
        self.prop("subdivisionBinding", "element", "");
        self.begin_array("data", dtype);
        let last = data.len().saturating_sub(1);
        for (i, item) in data.iter().enumerate() {
            if i < last {
                self.array_item_comma(item);
            } else {
                self.array_item(item);
            }
        }
        self.end_array();
        self.end();
    }

    fn write_data_array<F>(&mut self, name: &str, size: usize, streams_fn: F)
    where
        F: FnOnce(&mut Self),
    {
        for _ in 0..self.indent {
            self.buf.push('\t');
        }
        write!(self.buf, "\"{}\" \"CDmePolygonMeshDataArray\"\n", name).unwrap();
        self.w("{");
        self.indent += 1;
        self.prop("id", "elementid", &uid());
        self.prop("size", "int", &size.to_string());
        self.begin_array("streams", "element_array");
        streams_fn(self);
        self.end_array();
        self.end();
    }

    fn finish(self) -> String {
        self.buf
    }
}

// ─── Exported function ──────────────────────────────────────────────

/// Write the CDmePolygonMesh block for a single mesh as a KV2 string.
///
/// This replaces the inner `_write_mesh_data` hot-loop from Python.
/// The caller (Python VMapWriter) embeds the returned string into
/// the full .vmap structure.
///
/// Arguments:
///   vertex_positions: list of (x,y,z) tuples
///   vertex_edge_indices, vertex_data_indices: int lists
///   edge_vertex_indices .. edge_vertex_data_indices: int lists
///   face_edge_indices, face_data_indices: int lists
///   face_normals: list of (nx,ny,nz) tuples
///   face_quads_texcoords: list of (Option<[(u,v);4]>) per face
///   face_quads_block_types: list of block_type strings per face
///   face_quads_face_dirs: list of face_dir strings per face
///   face_quads_texture_names: list of Option<str> per face
///   materials: list of material path strings
///   scale: block scale in hammer units
///   num_vertices, num_half_edges, num_geometric_edges, num_faces: counts
#[pyfunction]
#[pyo3(signature = (
    vertex_positions,
    vertex_edge_indices,
    vertex_data_indices,
    edge_vertex_indices,
    edge_opposite_indices,
    edge_next_indices,
    edge_face_indices,
    edge_data_indices,
    edge_vertex_data_indices,
    face_edge_indices,
    face_data_indices,
    face_normals,
    face_quads_vertices,
    face_quads_texcoords,
    face_quads_block_types,
    face_quads_face_dirs,
    face_quads_texture_names,
    materials,
    scale,
    num_vertices,
    num_half_edges,
    num_geometric_edges,
    num_faces,
    texture_scale=0.125,
))]
pub fn write_vmap_string(
    vertex_positions: Vec<(f64, f64, f64)>,
    vertex_edge_indices: Vec<i32>,
    vertex_data_indices: Vec<i32>,
    edge_vertex_indices: Vec<i32>,
    edge_opposite_indices: Vec<i32>,
    edge_next_indices: Vec<i32>,
    edge_face_indices: Vec<i32>,
    edge_data_indices: Vec<i32>,
    edge_vertex_data_indices: Vec<i32>,
    face_edge_indices: Vec<i32>,
    face_data_indices: Vec<i32>,
    face_normals: Vec<(f64, f64, f64)>,
    face_quads_vertices: Vec<Vec<(f64, f64, f64)>>,
    face_quads_texcoords: Vec<Option<Vec<(f64, f64)>>>,
    face_quads_block_types: Vec<String>,
    face_quads_face_dirs: Vec<String>,
    face_quads_texture_names: Vec<Option<String>>,
    materials: Vec<String>,
    scale: f64,
    num_vertices: usize,
    num_half_edges: usize,
    num_geometric_edges: usize,
    num_faces: usize,
    texture_scale: f64,
) -> PyResult<String> {
    // Estimate output size (roughly 200 bytes per half-edge)
    let cap = num_half_edges * 200 + num_faces * 300 + 4096;
    let mut w = KV2Writer::new(cap);

    // ── meshData CDmePolygonMesh ────────────────────────────────────
    // Note: we write the INNER contents only; the caller wraps in the
    // "meshData" element begin/end.

    // Index arrays
    write_int_array(&mut w, "vertexEdgeIndices", &vertex_edge_indices);
    write_int_array(&mut w, "vertexDataIndices", &vertex_data_indices);
    write_int_array(&mut w, "edgeVertexIndices", &edge_vertex_indices);
    write_int_array(&mut w, "edgeOppositeIndices", &edge_opposite_indices);
    write_int_array(&mut w, "edgeNextIndices", &edge_next_indices);
    write_int_array(&mut w, "edgeFaceIndices", &edge_face_indices);
    write_int_array(&mut w, "edgeDataIndices", &edge_data_indices);
    write_int_array(&mut w, "edgeVertexDataIndices", &edge_vertex_data_indices);
    write_int_array(&mut w, "faceEdgeIndices", &face_edge_indices);
    write_int_array(&mut w, "faceDataIndices", &face_data_indices);

    // materials
    w.begin_array("materials", "string_array");
    let last_mat = materials.len().saturating_sub(1);
    for (i, mat) in materials.iter().enumerate() {
        if i < last_mat {
            w.array_item_comma(mat);
        } else {
            w.array_item(mat);
        }
    }
    w.end_array();

    // ── vertexData ──────────────────────────────────────────────────
    let pos_data: Vec<String> = vertex_positions
        .iter()
        .map(|p| format!("{} {} {}", fmt_g(p.0), fmt_g(p.1), fmt_g(p.2)))
        .collect();

    w.write_data_array("vertexData", num_vertices, |w| {
        w.write_data_stream(
            "position", "position", "position", 0, 3, "vector3_array", &pos_data,
        );
    });
    w.blank();

    // ── faceVertexData ──────────────────────────────────────────────
    // Pre-compute per-face UVs and tangents
    let mut face_uvs: Vec<Vec<(f64, f64)>> = Vec::with_capacity(num_faces);
    let mut face_tangs: Vec<(f64, f64, f64, f64)> = Vec::with_capacity(num_faces);

    for fi in 0..num_faces {
        let normal = face_normals[fi];
        let uvs = if let Some(ref tc) = face_quads_texcoords[fi] {
            tc.clone()
        } else {
            compute_face_texcoords_inner(&face_quads_vertices[fi], normal, scale)
        };
        face_uvs.push(uvs);
        face_tangs.push(compute_face_tangent_inner(normal));
    }

    // Build HE -> (face, slot) map
    let mut face_he_info: Vec<Option<(usize, usize)>> = vec![None; num_half_edges];
    for fi in 0..num_faces {
        let mut he = face_edge_indices[fi];
        for slot in 0..4 {
            if (he as usize) < num_half_edges {
                face_he_info[he as usize] = Some((fi, slot));
            }
            he = edge_next_indices[he as usize];
        }
    }

    // Build texcoord/normal/tangent lists
    let mut texcoords: Vec<String> = Vec::with_capacity(num_half_edges);
    let mut normals_data: Vec<String> = Vec::with_capacity(num_half_edges);
    let mut tangents_data: Vec<String> = Vec::with_capacity(num_half_edges);

    for hei in 0..num_half_edges {
        if let Some((fi, slot)) = face_he_info[hei] {
            let uv_slot = (slot + 1) % 4;
            let uv = face_uvs[fi][uv_slot];
            texcoords.push(format!("{} {}", fmt_g(uv.0), fmt_g(uv.1)));
            let n = face_normals[fi];
            normals_data.push(format!("{} {} {}", fmt_g(n.0), fmt_g(n.1), fmt_g(n.2)));
            let t = face_tangs[fi];
            tangents_data.push(format!("{} {} {} {}", fmt_g(t.0), fmt_g(t.1), fmt_g(t.2), fmt_g(t.3)));
        } else {
            texcoords.push("0 0".to_string());
            normals_data.push("0 0 0".to_string());
            tangents_data.push("0 0 0 0".to_string());
        }
    }

    w.write_data_array("faceVertexData", num_half_edges, |w| {
        w.write_data_stream("texcoord", "texcoord", "texcoord", 0, 1, "vector2_array", &texcoords);
        w.trailing_comma();
        w.write_data_stream("normal", "normal", "normal", 0, 1, "vector3_array", &normals_data);
        w.trailing_comma();
        w.write_data_stream("tangent", "tangent", "tangent", 0, 1, "vector4_array", &tangents_data);
    });
    w.blank();

    // ── edgeData ────────────────────────────────────────────────────
    let edge_flags: Vec<String> = vec!["0".to_string(); num_geometric_edges];
    w.write_data_array("edgeData", num_geometric_edges, |w| {
        w.write_data_stream("flags", "flags", "flags", 0, 3, "int_array", &edge_flags);
    });
    w.blank();

    // ── faceData ────────────────────────────────────────────────────
    // Build material index map
    let mut mat_index_map: std::collections::HashMap<&str, i32> = std::collections::HashMap::new();
    for (mi, mat) in materials.iter().enumerate() {
        mat_index_map.insert(mat.as_str(), mi as i32);
    }

    let mut tex_scales: Vec<String> = Vec::with_capacity(num_faces);
    let mut tex_axis_u: Vec<String> = Vec::with_capacity(num_faces);
    let mut tex_axis_v: Vec<String> = Vec::with_capacity(num_faces);
    let mut mat_indices: Vec<String> = Vec::with_capacity(num_faces);
    let mut face_flags: Vec<String> = Vec::with_capacity(num_faces);
    let mut lightmap_sb: Vec<String> = Vec::with_capacity(num_faces);

    for fi in 0..num_faces {
        let normal = face_normals[fi];
        tex_scales.push(format!("{} {}", fmt_g(texture_scale), fmt_g(texture_scale)));

        let (au, av) = compute_texture_axes_inner(normal);
        tex_axis_u.push(format!("{} {} {} {}", fmt_g(au.0), fmt_g(au.1), fmt_g(au.2), fmt_g(au.3)));
        tex_axis_v.push(format!("{} {} {} {}", fmt_g(av.0), fmt_g(av.1), fmt_g(av.2), fmt_g(av.3)));

        // Material index: try texture_name first, then block_type lookup
        let mut mat_idx = 0i32;
        let mut found = false;

        if let Some(ref tex_name) = face_quads_texture_names[fi] {
            let suffix = format!("/{}.vmat", tex_name);
            for (mi, mat) in materials.iter().enumerate() {
                if mat.ends_with(&suffix) {
                    mat_idx = mi as i32;
                    found = true;
                    break;
                }
            }
        }

        if !found {
            let block_base = get_block_base_name_str(&face_quads_block_types[fi]);
            // Try face-specific first, then base
            let face_dir = &face_quads_face_dirs[fi];
            let face_tex = get_texture_name_for_face(&block_base, face_dir);
            let suffix = format!("/{}.vmat", face_tex);
            for (mi, mat) in materials.iter().enumerate() {
                if mat.ends_with(&suffix) {
                    mat_idx = mi as i32;
                    found = true;
                    break;
                }
            }
            if !found {
                let base_suffix = format!("/{}.vmat", block_base);
                for (mi, mat) in materials.iter().enumerate() {
                    if mat.ends_with(&base_suffix) {
                        mat_idx = mi as i32;
                        break;
                    }
                }
            }
        }

        mat_indices.push(mat_idx.to_string());
        face_flags.push("0".to_string());
        lightmap_sb.push("0".to_string());
    }

    w.write_data_array("faceData", num_faces, |w| {
        w.write_data_stream("textureScale", "textureScale", "textureScale", 0, 0, "vector2_array", &tex_scales);
        w.trailing_comma();
        w.write_data_stream("textureAxisU", "textureAxisU", "textureAxisU", 0, 0, "vector4_array", &tex_axis_u);
        w.trailing_comma();
        w.write_data_stream("textureAxisV", "textureAxisV", "textureAxisV", 0, 0, "vector4_array", &tex_axis_v);
        w.trailing_comma();
        w.write_data_stream("materialindex", "materialindex", "materialindex", 0, 8, "int_array", &mat_indices);
        w.trailing_comma();
        w.write_data_stream("flags", "flags", "flags", 0, 3, "int_array", &face_flags);
        w.trailing_comma();
        w.write_data_stream("lightmapScaleBias", "lightmapScaleBias", "lightmapScaleBias", 0, 1, "int_array", &lightmap_sb);
    });
    w.blank();

    // ── subdivisionData (empty) ─────────────────────────────────────
    {
        for _ in 0..w.indent {
            w.buf.push('\t');
        }
        write!(w.buf, "\"subdivisionData\" \"CDmePolygonMeshSubdivisionData\"\n").unwrap();
        w.w("{");
        w.indent += 1;
        w.prop("id", "elementid", &uid());
        w.begin_array("subdivisionLevels", "int_array");
        w.end_array();
        w.begin_array("streams", "element_array");
        w.end_array();
        w.end();
    }

    Ok(w.finish())
}

// ─── Internal helpers (not exported) ────────────────────────────────

fn write_int_array(w: &mut KV2Writer, name: &str, data: &[i32]) {
    w.begin_array(name, "int_array");
    let last = data.len().saturating_sub(1);
    for (i, &v) in data.iter().enumerate() {
        if i < last {
            w.array_item_comma(&v.to_string());
        } else {
            w.array_item(&v.to_string());
        }
    }
    w.end_array();
}

fn compute_face_texcoords_inner(
    verts: &[(f64, f64, f64)],
    normal: (f64, f64, f64),
    scale: f64,
) -> Vec<(f64, f64)> {
    let (nx, ny, nz) = normal;
    let (anx, any, anz) = (nx.abs(), ny.abs(), nz.abs());

    let coords: Vec<(f64, f64)> = if anz >= anx && anz >= any {
        verts.iter().map(|v| (v.0, -v.1)).collect()
    } else if any >= anx {
        verts.iter().map(|v| (v.0, -v.2)).collect()
    } else {
        verts.iter().map(|v| (-v.1, -v.2)).collect()
    };

    let (base_u, base_v) = coords[0];
    coords
        .iter()
        .map(|(u, v)| ((u - base_u) / scale, (v - base_v) / scale))
        .collect()
}

fn compute_face_tangent_inner(normal: (f64, f64, f64)) -> (f64, f64, f64, f64) {
    let (nx, ny, nz) = normal;
    let (anx, any, anz) = (nx.abs(), ny.abs(), nz.abs());

    if anz >= anx && anz >= any {
        if nz >= 0.0 { (1.0, 0.0, 0.0, -1.0) } else { (1.0, 0.0, 0.0, 1.0) }
    } else if any >= anx {
        if ny >= 0.0 { (1.0, 0.0, 0.0, 1.0) } else { (1.0, 0.0, 0.0, -1.0) }
    } else if nx >= 0.0 {
        (0.0, -1.0, 0.0, -1.0)
    } else {
        (0.0, -1.0, 0.0, 1.0)
    }
}

fn compute_texture_axes_inner(
    normal: (f64, f64, f64),
) -> ((f64, f64, f64, f64), (f64, f64, f64, f64)) {
    let (nx, ny, nz) = normal;
    let (anx, any, anz) = (nx.abs(), ny.abs(), nz.abs());

    if anz >= anx && anz >= any {
        ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0))
    } else if any >= anx {
        ((1.0, 0.0, 0.0, 0.0), (0.0, 0.0, -1.0, 0.0))
    } else {
        ((0.0, -1.0, 0.0, 0.0), (0.0, 0.0, -1.0, 0.0))
    }
}

/// Strip block state: "minecraft:stone" → "stone", "minecraft:oak_slab[type=top]" → "oak_slab"
fn get_block_base_name_str(name: &str) -> String {
    let stripped = if let Some(pos) = name.find('[') {
        &name[..pos]
    } else {
        name
    };
    if let Some(pos) = stripped.find(':') {
        stripped[pos + 1..].to_string()
    } else {
        stripped.to_string()
    }
}

/// Placeholder: face-specific texture name selection.
/// In practice this falls through to the block base name.
fn get_texture_name_for_face(block_base: &str, _face_dir: &str) -> String {
    block_base.to_string()
}
