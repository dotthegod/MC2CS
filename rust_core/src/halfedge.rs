//! Half-edge mesh builder — Rust port of converter/halfedge.py.
//!
//! Converts quad lists into the CDmePolygonMesh half-edge topology that
//! Source 2 / CS2 Hammer expects.  Half-edges are stored as consecutive
//! twin pairs: [he0, twin0, he1, twin1, ...].

use pyo3::prelude::*;
use rustc_hash::FxHashMap;
use std::collections::BTreeSet;

// ─── helpers ────────────────────────────────────────────────────────

/// Round a coordinate to 4 decimals → integer key for hash lookup.
#[inline]
fn vec_key(x: f64, y: f64, z: f64) -> (i64, i64, i64) {
    fn r(v: f64) -> i64 {
        (v * 10_000.0).round() as i64
    }
    (r(x), r(y), r(z))
}

// ─── Python-visible data structures ────────────────────────────────

/// Python-visible Quad — mirrors `converter.mesh_generator.Quad`.
#[pyclass(name = "Quad")]
#[derive(Clone, Debug)]
pub struct PyQuad {
    #[pyo3(get, set)]
    pub vertices: Vec<(f64, f64, f64)>,
    #[pyo3(get, set)]
    pub normal: (f64, f64, f64),
    #[pyo3(get, set)]
    pub block_type: String,
    #[pyo3(get, set)]
    pub face_dir: String,
    #[pyo3(get, set)]
    pub block_pos: (f64, f64, f64),
    #[pyo3(get, set)]
    pub texcoords: Option<Vec<(f64, f64)>>,
    #[pyo3(get, set)]
    pub texture_name: Option<String>,
}

#[pymethods]
impl PyQuad {
    #[new]
    #[pyo3(signature = (vertices, normal, block_type, face_dir, block_pos=(0.0,0.0,0.0), texcoords=None, texture_name=None))]
    fn new(
        vertices: Vec<(f64, f64, f64)>,
        normal: (f64, f64, f64),
        block_type: String,
        face_dir: String,
        block_pos: (f64, f64, f64),
        texcoords: Option<Vec<(f64, f64)>>,
        texture_name: Option<String>,
    ) -> Self {
        Self {
            vertices,
            normal,
            block_type,
            face_dir,
            block_pos,
            texcoords,
            texture_name,
        }
    }
}

/// Python-visible HalfEdgeMesh — mirrors `converter.halfedge.HalfEdgeMesh`.
#[pyclass(name = "HalfEdgeMesh")]
#[derive(Clone, Debug)]
pub struct PyHalfEdgeMesh {
    #[pyo3(get)]
    pub vertex_positions: Vec<(f64, f64, f64)>,
    #[pyo3(get)]
    pub vertex_edge_indices: Vec<i32>,
    #[pyo3(get)]
    pub vertex_data_indices: Vec<i32>,

    #[pyo3(get)]
    pub edge_vertex_indices: Vec<i32>,
    #[pyo3(get)]
    pub edge_opposite_indices: Vec<i32>,
    #[pyo3(get)]
    pub edge_next_indices: Vec<i32>,
    #[pyo3(get)]
    pub edge_face_indices: Vec<i32>,
    #[pyo3(get)]
    pub edge_data_indices: Vec<i32>,
    #[pyo3(get)]
    pub edge_vertex_data_indices: Vec<i32>,

    #[pyo3(get)]
    pub face_edge_indices: Vec<i32>,
    #[pyo3(get)]
    pub face_data_indices: Vec<i32>,

    #[pyo3(get)]
    pub face_normals: Vec<(f64, f64, f64)>,
    // face_quads stored as PyQuad references
    #[pyo3(get)]
    pub face_quads: Vec<PyQuad>,

    #[pyo3(get)]
    pub num_vertices: usize,
    #[pyo3(get)]
    pub num_half_edges: usize,
    #[pyo3(get)]
    pub num_geometric_edges: usize,
    #[pyo3(get)]
    pub num_faces: usize,
}

// ─── Core algorithm ────────────────────────────────────────────────

/// Build a HalfEdgeMesh from a list of quads.
///
/// This is the hot-path function — the performance bottleneck that
/// motivated the Rust port.
#[pyfunction]
pub fn build_halfedge_mesh(quads: Vec<PyQuad>) -> PyResult<PyHalfEdgeMesh> {
    if quads.is_empty() {
        return Ok(PyHalfEdgeMesh {
            vertex_positions: vec![],
            vertex_edge_indices: vec![],
            vertex_data_indices: vec![],
            edge_vertex_indices: vec![],
            edge_opposite_indices: vec![],
            edge_next_indices: vec![],
            edge_face_indices: vec![],
            edge_data_indices: vec![],
            edge_vertex_data_indices: vec![],
            face_edge_indices: vec![],
            face_data_indices: vec![],
            face_normals: vec![],
            face_quads: vec![],
            num_vertices: 0,
            num_half_edges: 0,
            num_geometric_edges: 0,
            num_faces: 0,
        });
    }

    // ── 1. Collect unique vertices ──────────────────────────────────
    let mut vertex_map: FxHashMap<(i64, i64, i64), i32> = FxHashMap::default();
    let mut vertices: Vec<(f64, f64, f64)> = Vec::new();

    for quad in &quads {
        for v in &quad.vertices {
            let key = vec_key(v.0, v.1, v.2);
            if !vertex_map.contains_key(&key) {
                let idx = vertices.len() as i32;
                vertex_map.insert(key, idx);
                vertices.push(*v);
            }
        }
    }

    let num_faces = quads.len();

    // ── 2. Build temporary face half-edges ──────────────────────────
    let mut tmp_from: Vec<i32> = Vec::new();
    let mut tmp_to: Vec<i32> = Vec::new();
    let mut tmp_face: Vec<i32> = Vec::new();
    let mut tmp_next: Vec<usize> = Vec::new();
    let mut tmp_fv_idx: Vec<i32> = Vec::new();
    let mut face_first_tmp: Vec<usize> = Vec::new();
    let mut face_normals_list: Vec<(f64, f64, f64)> = Vec::with_capacity(num_faces);
    let mut fv_counter: i32 = 0;

    for (fi, quad) in quads.iter().enumerate() {
        face_normals_list.push(quad.normal);
        let v_indices: Vec<i32> = quad
            .vertices
            .iter()
            .map(|v| vertex_map[&vec_key(v.0, v.1, v.2)])
            .collect();
        let n = v_indices.len();
        let first = tmp_from.len();
        face_first_tmp.push(first);

        for ei in 0..n {
            tmp_from.push(v_indices[ei]);
            tmp_to.push(v_indices[(ei + 1) % n]);
            tmp_face.push(fi as i32);
            tmp_fv_idx.push(fv_counter + ((ei + 1) % n) as i32);
            tmp_next.push(first + (ei + 1) % n);
        }
        fv_counter += n as i32;
    }

    let num_tmp = tmp_from.len();

    // ── 3. Pair face half-edges and create boundary twins ───────────
    let mut edge_lookup: FxHashMap<(i32, i32), Vec<usize>> = FxHashMap::default();
    for i in 0..num_tmp {
        edge_lookup
            .entry((tmp_from[i], tmp_to[i]))
            .or_default()
            .push(i);
    }

    let mut partner: Vec<i32> = vec![-1; num_tmp];
    for i in 0..num_tmp {
        if partner[i] != -1 {
            continue;
        }
        let opp_key = (tmp_to[i], tmp_from[i]);
        if let Some(candidates) = edge_lookup.get(&opp_key) {
            for &j in candidates {
                if partner[j] == -1 && j != i {
                    partner[i] = j as i32;
                    partner[j] = i as i32;
                    break;
                }
            }
        }
    }

    let boundary_face_hes: Vec<usize> = (0..num_tmp)
        .filter(|&i| partner[i] == -1)
        .collect();

    // ── 4. Build final half-edge list as consecutive twin pairs ─────
    let mut final_count: usize = 0;
    let mut tmp_to_final: Vec<i32> = vec![-1; num_tmp];
    let mut boundary_twins: Vec<(i32, i32, usize, usize)> = Vec::new();

    // Type A: paired face HEs
    for i in 0..num_tmp {
        if tmp_to_final[i] != -1 {
            continue;
        }
        let j = partner[i];
        if j != -1 {
            tmp_to_final[i] = final_count as i32;
            tmp_to_final[j as usize] = (final_count + 1) as i32;
            final_count += 2;
        }
    }

    // Type B: face HE + boundary twin
    for &i in &boundary_face_hes {
        tmp_to_final[i] = final_count as i32;
        boundary_twins.push((tmp_to[i], tmp_from[i], i, final_count + 1));
        final_count += 2;
    }

    let num_he = final_count;
    let num_geo_edges = num_he / 2;

    // ── 5. Populate final arrays ────────────────────────────────────
    let mut out_to = vec![0i32; num_he];
    let mut out_opp = vec![0i32; num_he];
    let mut out_next = vec![0i32; num_he];
    let mut out_face = vec![0i32; num_he];
    let mut out_edge_data = vec![0i32; num_he];
    let mut out_fv_data = vec![0i32; num_he];

    // 5a. Fill face half-edges
    for i in 0..num_tmp {
        let fi = tmp_to_final[i] as usize;
        out_to[fi] = tmp_to[i];
        out_face[fi] = tmp_face[i];
        out_next[fi] = tmp_to_final[tmp_next[i]];
        out_fv_data[fi] = tmp_fv_idx[i];
    }

    // 5b. Fill twin-pair structure
    for pair_idx in 0..num_geo_edges {
        let a = pair_idx * 2;
        let b = pair_idx * 2 + 1;
        out_opp[a] = b as i32;
        out_opp[b] = a as i32;
        out_edge_data[a] = pair_idx as i32;
        out_edge_data[b] = pair_idx as i32;
    }

    // 5c. Fill boundary twins
    for &(b_from, b_to, _face_tmp, b_final) in &boundary_twins {
        out_to[b_final] = b_to;
        out_face[b_final] = -1;
        out_fv_data[b_final] = b_final as i32;
        let _ = b_from; // used later in 5d
    }

    // ── 5d-pre. Split non-manifold vertices ─────────────────────────
    // Build outgoing and incoming HE index maps per vertex.
    let mut vert_out: FxHashMap<i32, BTreeSet<usize>> = FxHashMap::default();
    let mut vert_in: FxHashMap<i32, Vec<usize>> = FxHashMap::default();
    for he in 0..num_he {
        let from_v = out_to[out_opp[he] as usize];
        vert_out.entry(from_v).or_default().insert(he);
        vert_in.entry(out_to[he]).or_default().push(he);
    }

    let vkeys: Vec<i32> = vert_out.keys().copied().collect();
    for v in vkeys {
        let out_hes = match vert_out.get(&v) {
            Some(s) => s.clone(),
            None => continue,
        };
        if out_hes.len() < 2 {
            continue;
        }

        // Fan-walk to find connected groups
        let mut remaining: BTreeSet<usize> = out_hes;
        let mut groups: Vec<Vec<usize>> = Vec::new();

        while !remaining.is_empty() {
            let start = *remaining.iter().next().unwrap();
            let mut group = vec![start];
            remaining.remove(&start);

            // Walk CW: face HE h -> prev_in_quad(next^3) -> twin
            let mut h = start;
            loop {
                if out_face[h] != -1 {
                    let prev_h = out_next[out_next[out_next[h] as usize] as usize] as usize;
                    let nxt = out_opp[prev_h] as usize;
                    if remaining.remove(&nxt) {
                        group.push(nxt);
                        h = nxt;
                    } else {
                        break;
                    }
                } else {
                    break;
                }
            }

            // Walk CCW: twin(h) -> next
            h = start;
            loop {
                let twin = out_opp[h] as usize;
                if out_face[twin] != -1 {
                    let nxt = out_next[twin] as usize;
                    if remaining.remove(&nxt) {
                        group.push(nxt);
                        h = nxt;
                    } else {
                        break;
                    }
                } else {
                    break;
                }
            }

            groups.push(group);
        }

        if groups.len() <= 1 {
            continue; // manifold
        }

        // Build HE -> group index map
        let mut he_group: FxHashMap<usize, usize> = FxHashMap::default();
        for (gi, grp) in groups.iter().enumerate() {
            for &he in grp {
                he_group.insert(he, gi);
            }
        }

        // Group 0 keeps original vertex; groups 1..N get new copies
        let mut new_vertex_ids: Vec<i32> = vec![v];
        for _ in 1..groups.len() {
            let new_idx = vertices.len() as i32;
            vertices.push(vertices[v as usize]);
            new_vertex_ids.push(new_idx);
        }

        // Update HEs that point TO v
        if let Some(incoming) = vert_in.get(&v) {
            for &he in incoming {
                let outgoing = out_opp[he] as usize;
                let gi = he_group.get(&outgoing).copied().unwrap_or(0);
                out_to[he] = new_vertex_ids[gi];
            }
        }
    }

    let num_verts = vertices.len();

    // ── 5d. Link boundary twin next pointers ────────────────────────
    for &(_b_from, _b_to, _face_tmp, b_final) in &boundary_twins {
        let to_v = out_to[b_final];
        let _ = to_v;

        let mut f = out_opp[b_final] as usize;
        let mut found = false;

        for _ in 0..num_he {
            let p = out_next[out_next[out_next[f] as usize] as usize] as usize;
            let t = out_opp[p] as usize;
            if out_face[t] == -1 {
                out_next[b_final] = t as i32;
                found = true;
                break;
            }
            f = t;
        }

        if !found {
            out_next[b_final] = b_final as i32; // self-loop fallback
        }
    }

    // ── 6. Vertex edge indices ──────────────────────────────────────
    let mut vertex_edge = vec![-1i32; num_verts];
    for fi in 0..num_he {
        let from_v = out_to[out_opp[fi] as usize];
        if from_v >= 0 && (from_v as usize) < num_verts && vertex_edge[from_v as usize] == -1 {
            vertex_edge[from_v as usize] = fi as i32;
        }
    }

    // ── 7. Face edge indices ────────────────────────────────────────
    let face_edge_indices: Vec<i32> = (0..num_faces)
        .map(|fi| tmp_to_final[face_first_tmp[fi]])
        .collect();

    // ── 8. Identity fvdata mapping ──────────────────────────────────
    for i in 0..num_he {
        out_fv_data[i] = i as i32;
    }

    // ── Build mesh ──────────────────────────────────────────────────
    Ok(PyHalfEdgeMesh {
        vertex_positions: vertices,
        vertex_edge_indices: vertex_edge,
        vertex_data_indices: (0..num_verts as i32).collect(),
        edge_vertex_indices: out_to,
        edge_opposite_indices: out_opp,
        edge_next_indices: out_next,
        edge_face_indices: out_face,
        edge_data_indices: out_edge_data,
        edge_vertex_data_indices: out_fv_data,
        face_edge_indices,
        face_data_indices: (0..num_faces as i32).collect(),
        face_normals: face_normals_list,
        face_quads: quads,
        num_vertices: num_verts,
        num_half_edges: num_he,
        num_geometric_edges: num_geo_edges,
        num_faces,
    })
}

// ─── Texture helpers ────────────────────────────────────────────────

/// Compute UV texture coordinates for a quad's vertices.
#[pyfunction]
pub fn compute_face_texcoords(quad: &PyQuad, scale: f64) -> Vec<(f64, f64)> {
    let verts = &quad.vertices;
    let (nx, ny, nz) = quad.normal;
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

/// Compute tangent vector for a face given its normal.
/// Returns (tx, ty, tz, sign).
#[pyfunction]
pub fn compute_face_tangent(normal: (f64, f64, f64)) -> (f64, f64, f64, f64) {
    let (nx, ny, nz) = normal;
    let (anx, any, anz) = (nx.abs(), ny.abs(), nz.abs());

    if anz >= anx && anz >= any {
        if nz >= 0.0 {
            (1.0, 0.0, 0.0, -1.0)
        } else {
            (1.0, 0.0, 0.0, 1.0)
        }
    } else if any >= anx {
        if ny >= 0.0 {
            (1.0, 0.0, 0.0, 1.0)
        } else {
            (1.0, 0.0, 0.0, -1.0)
        }
    } else if nx >= 0.0 {
        (0.0, -1.0, 0.0, -1.0)
    } else {
        (0.0, -1.0, 0.0, 1.0)
    }
}

/// Compute textureAxisU and textureAxisV for a face.
/// Returns ((ux,uy,uz,uo), (vx,vy,vz,vo)).
#[pyfunction]
pub fn compute_texture_axes(
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
