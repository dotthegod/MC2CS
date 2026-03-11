//! Greedy meshing — Rust port of converter/greedy_mesh.py.
//!
//! Merges adjacent coplanar same-material quads into larger rectangles.

use pyo3::prelude::*;
use crate::halfedge::PyQuad;

// ─── Face axis definitions ──────────────────────────────────────────

struct FaceDef {
    slice_axis: usize,
    u_axis: usize,
    v_axis: usize,
    normal_mc: (f64, f64, f64),
    neighbor_offset: (i32, i32, i32),
    pos_dir: bool,
}

const FACE_DEFS: &[(&str, FaceDef)] = &[
    ("+x", FaceDef { slice_axis: 0, u_axis: 2, v_axis: 1, normal_mc: (1.0, 0.0, 0.0), neighbor_offset: (1, 0, 0), pos_dir: true }),
    ("-x", FaceDef { slice_axis: 0, u_axis: 2, v_axis: 1, normal_mc: (-1.0, 0.0, 0.0), neighbor_offset: (-1, 0, 0), pos_dir: false }),
    ("+y", FaceDef { slice_axis: 1, u_axis: 0, v_axis: 2, normal_mc: (0.0, 1.0, 0.0), neighbor_offset: (0, 1, 0), pos_dir: true }),
    ("-y", FaceDef { slice_axis: 1, u_axis: 0, v_axis: 2, normal_mc: (0.0, -1.0, 0.0), neighbor_offset: (0, -1, 0), pos_dir: false }),
    ("+z", FaceDef { slice_axis: 2, u_axis: 1, v_axis: 0, normal_mc: (0.0, 0.0, 1.0), neighbor_offset: (0, 0, 1), pos_dir: true }),
    ("-z", FaceDef { slice_axis: 2, u_axis: 1, v_axis: 0, normal_mc: (0.0, 0.0, -1.0), neighbor_offset: (0, 0, -1), pos_dir: false }),
];

// ─── Coordinate transform ───────────────────────────────────────────

/// Minecraft (X, Y, Z) → CS2 (X, -Z, Y)
#[inline]
fn mc_to_cs2(x: f64, y: f64, z: f64) -> (f64, f64, f64) {
    (x, -z, y)
}

// ─── Grid access helpers ────────────────────────────────────────────

/// Flat-array index into the block grid.
#[inline]
fn grid_idx(x: usize, y: usize, z: usize, height: usize, length: usize) -> usize {
    x * height * length + y * length + z
}

// ─── Quad vertex construction ───────────────────────────────────────

fn build_quad_verts(
    slice_val: usize,
    u_start: usize,
    v_start: usize,
    u_end: usize,
    v_end: usize,
    face_def: &FaceDef,
) -> Vec<(f64, f64, f64)> {
    let sa = face_def.slice_axis;
    let ua = face_def.u_axis;
    let va = face_def.v_axis;

    let d = if face_def.pos_dir {
        (slice_val + 1) as f64
    } else {
        slice_val as f64
    };

    let corners = [
        (u_start as f64, v_start as f64),
        (u_end as f64, v_start as f64),
        (u_end as f64, v_end as f64),
        (u_start as f64, v_end as f64),
    ];

    let mut verts = Vec::with_capacity(4);
    for &(u, v) in &corners {
        let mut pos = [0.0f64; 3];
        pos[sa] = d;
        pos[ua] = u;
        pos[va] = v;
        verts.push((pos[0], pos[1], pos[2]));
    }

    if face_def.pos_dir {
        verts = vec![verts[0], verts[3], verts[2], verts[1]];
    }

    verts
}

// ─── Main entry point ───────────────────────────────────────────────

/// Generate greedy-meshed quads from block grid data.
///
/// Arguments:
///   blocks: flat i32 array of palette indices (shape width*height*length,
///           C-order x*H*L + y*L + z)
///   palette: dict {int -> str} mapping palette index to block name
///   width, height, length: grid dimensions
///   scale: Hammer units per block (default 64)
///   offset: (ox, oy, oz) translation in CS2 space
///   should_generate_set: set of block base names that need geometry
///   solid_for_culling_set: set of block base names that are solid for culling
///   progress_callback: optional Python callable(face_count, total_faces)
#[pyfunction]
#[pyo3(signature = (blocks, palette, width, height, length, scale=64.0, offset=(0.0,0.0,0.0), should_generate_set=None, solid_for_culling_set=None, progress_callback=None))]
pub fn generate_greedy_quads(
    _py: Python<'_>,
    blocks: Vec<i32>,
    palette: std::collections::HashMap<i32, String>,
    width: usize,
    height: usize,
    length: usize,
    scale: f64,
    offset: (f64, f64, f64),
    should_generate_set: Option<std::collections::HashSet<String>>,
    solid_for_culling_set: Option<std::collections::HashSet<String>>,
    progress_callback: Option<&Bound<'_, pyo3::PyAny>>,
) -> PyResult<Vec<PyQuad>> {
    let mut quads: Vec<PyQuad> = Vec::new();

    // Pre-compute: for each palette index, is it "should generate" and
    // "solid for culling", and what is its base name?
    let should_gen = should_generate_set.unwrap_or_default();
    let solid_cull = solid_for_culling_set.unwrap_or_default();

    // Build per-palette-index lookup tables
    let max_idx = palette.keys().copied().max().unwrap_or(0) as usize;
    let mut pal_generate = vec![false; max_idx + 1];
    let mut pal_solid = vec![false; max_idx + 1];
    let mut pal_base: Vec<Option<String>> = vec![None; max_idx + 1];

    for (&idx, name) in &palette {
        if idx < 0 {
            continue;
        }
        let i = idx as usize;
        let base = get_block_base_name(name);
        if should_gen.contains(&base) {
            pal_generate[i] = true;
        }
        if solid_cull.contains(&base)
            || solid_cull.contains(name.as_str())
        {
            pal_solid[i] = true;
        }
        pal_base[i] = Some(base);
    }

    let total_faces = 6u32;
    let mut face_count = 0u32;

    for &(face_dir_str, ref face_def) in FACE_DEFS {
        face_count += 1;
        if let Some(cb) = &progress_callback {
            cb.call1((face_count, total_faces))?;
        }

        let sa = face_def.slice_axis;
        let ua = face_def.u_axis;
        let va = face_def.v_axis;
        let noff = face_def.neighbor_offset;

        let sizes = [width, height, length];
        let slice_size = sizes[sa];
        let u_size = sizes[ua];
        let v_size = sizes[va];

        for slice_val in 0..slice_size {
            // Build 2D mask: palette base name (or None for skip)
            let mut mask: Vec<Option<&str>> = vec![None; u_size * v_size];

            for u in 0..u_size {
                for v in 0..v_size {
                    let mut coords = [0usize; 3];
                    coords[sa] = slice_val;
                    coords[ua] = u;
                    coords[va] = v;

                    let block_id = blocks[grid_idx(coords[0], coords[1], coords[2], height, length)];
                    if block_id < 0 || block_id as usize > max_idx || !pal_generate[block_id as usize] {
                        continue;
                    }

                    // Check neighbor for culling
                    let nx = coords[0] as i32 + noff.0;
                    let ny = coords[1] as i32 + noff.1;
                    let nz = coords[2] as i32 + noff.2;

                    if nx >= 0
                        && (nx as usize) < width
                        && ny >= 0
                        && (ny as usize) < height
                        && nz >= 0
                        && (nz as usize) < length
                    {
                        let n_id = blocks[grid_idx(nx as usize, ny as usize, nz as usize, height, length)];
                        if n_id >= 0 && (n_id as usize) <= max_idx && pal_solid[n_id as usize] {
                            continue;
                        }
                    }

                    if let Some(ref base) = pal_base[block_id as usize] {
                        mask[u * v_size + v] = Some(base.as_str());
                    }
                }
            }

            // Greedy merge
            let mut visited = vec![false; u_size * v_size];

            for u in 0..u_size {
                for v in 0..v_size {
                    let idx = u * v_size + v;
                    if visited[idx] || mask[idx].is_none() {
                        continue;
                    }
                    let material = mask[idx].unwrap();

                    // Expand width (u direction)
                    let mut w = 1usize;
                    while u + w < u_size {
                        let ni = (u + w) * v_size + v;
                        if mask[ni] == Some(material) && !visited[ni] {
                            w += 1;
                        } else {
                            break;
                        }
                    }

                    // Expand height (v direction)
                    let mut h = 1usize;
                    'outer: loop {
                        if v + h >= v_size {
                            break;
                        }
                        for du in 0..w {
                            let ni = (u + du) * v_size + (v + h);
                            if mask[ni] != Some(material) || visited[ni] {
                                break 'outer;
                            }
                        }
                        h += 1;
                    }

                    // Mark visited
                    for du in 0..w {
                        for dv in 0..h {
                            visited[(u + du) * v_size + (v + dv)] = true;
                        }
                    }

                    // Build quad vertices
                    let verts_mc = build_quad_verts(
                        slice_val, u, v, u + w, v + h, face_def,
                    );

                    let verts_cs2: Vec<(f64, f64, f64)> = verts_mc
                        .iter()
                        .map(|&(mx, my, mz)| {
                            let (sx, sy, sz) = (mx * scale, my * scale, mz * scale);
                            let (cx, cy, cz) = mc_to_cs2(sx, sy, sz);
                            (cx + offset.0, cy + offset.1, cz + offset.2)
                        })
                        .collect();

                    let normal_cs2 = mc_to_cs2(
                        face_def.normal_mc.0,
                        face_def.normal_mc.1,
                        face_def.normal_mc.2,
                    );

                    // Normalise material name
                    let mat_name = if material.contains(':') {
                        format!(
                            "minecraft:{}",
                            material.split(':').last().unwrap_or(material)
                        )
                    } else {
                        format!("minecraft:{}", material)
                    };

                    quads.push(PyQuad {
                        vertices: verts_cs2,
                        normal: normal_cs2,
                        block_type: mat_name,
                        face_dir: face_dir_str.to_string(),
                        block_pos: (0.0, 0.0, 0.0),
                        texcoords: None,
                        texture_name: None,
                    });
                }
            }
        }
    }

    if let Some(cb) = &progress_callback {
        cb.call1((total_faces, total_faces))?;
    }

    Ok(quads)
}

// ─── Utility ────────────────────────────────────────────────────────

/// Strip block state properties: "minecraft:oak_slab[type=top]" → "oak_slab"
fn get_block_base_name(name: &str) -> String {
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
