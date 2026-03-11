"""VMap writer: serializes half-edge meshes to Source 2 .vmap files (KeyValues2 DMX format)."""

import uuid
import random
from converter.halfedge import (
    HalfEdgeMesh, compute_face_texcoords, compute_face_tangent, compute_texture_axes
)
from converter.mesh_generator import Quad
from config.defaults import (
    EDITOR_BUILD, EDITOR_VERSION, DEFAULT_TEXTURE_SCALE, DEFAULT_SKY,
    DEFAULT_SMOOTHING_ANGLE, DEFAULT_MATERIAL
)


def _uid() -> str:
    return str(uuid.uuid4())


def _rand_seed() -> int:
    return random.randint(0, 2**31 - 1)


def _rand_ref() -> str:
    return f"0x{random.getrandbits(64):016x}"


def _fmt_vec3(v) -> str:
    """Format a vector3 as 'x y z'."""
    return f"{v[0]:g} {v[1]:g} {v[2]:g}"


def _fmt_vec2(v) -> str:
    return f"{v[0]:g} {v[1]:g}"


def _fmt_vec4(v) -> str:
    return f"{v[0]:g} {v[1]:g} {v[2]:g} {v[3]:g}"


class VMapWriter:
    """Writes .vmap files in KeyValues2 DMX format."""

    def __init__(self, max_indent: int = 0):
        self.lines = []
        self.indent = 0
        self.max_indent = max_indent  # 0 = unlimited (full indentation)
        self._array_items = []  # buffer for current array items
        self._in_array = False
        self._array_dtype = ""

    def _w(self, text: str = ""):
        if text:
            depth = self.indent if self.max_indent == 0 else min(self.indent, self.max_indent)
            self.lines.append("\t" * depth + text)
        else:
            self.lines.append("")

    def _begin(self, text: str):
        self._w(text)
        self._w("{")
        self.indent += 1

    def _end(self):
        self.indent -= 1
        self._w("}")

    def _trailing_comma(self):
        """Append a comma to the last written line (for element_array separators)."""
        if self.lines:
            self.lines[-1] += ","

    def _prop(self, name: str, dtype: str, value: str):
        self._w(f'"{name}" "{dtype}" "{value}"')

    def _begin_array(self, name: str, dtype: str):
        self._w(f'"{name}" "{dtype}" ')
        self._w("[")
        self.indent += 1
        self._array_items = []
        self._in_array = True
        self._array_dtype = dtype

    def _end_array(self):
        # Flush buffered items with commas between them
        items = self._array_items
        if self.max_indent and len(items) > 8:
            # Compact mode: write multiple values per line to reduce file size
            depth = min(self.indent, self.max_indent)
            prefix = "\t" * depth
            # Determine values per line based on array data type
            dt = self._array_dtype
            if 'vector4' in dt:
                per_line = 4
            elif 'vector3' in dt:
                per_line = 5
            elif 'vector2' in dt:
                per_line = 8
            else:
                per_line = 16

            for start in range(0, len(items), per_line):
                chunk = items[start:start + per_line]
                line_parts = []
                for idx, item in enumerate(chunk):
                    is_last = (start + idx == len(items) - 1)
                    line_parts.append(item + ("" if is_last else ","))
                self.lines.append(prefix + " ".join(line_parts))
        else:
            for i, item in enumerate(items):
                if i < len(items) - 1:
                    self._w(item + ",")
                else:
                    self._w(item)
        self._array_items = []
        self._in_array = False
        self.indent -= 1
        self._w("]")

    def _array_item(self, value: str):
        self._array_items.append(f'"{value}"')

    def _array_element_block(self, lines: list[str]):
        """Add a multi-line element block as a single array item."""
        self._array_items.append(lines)

    def _begin_element(self, name: str, etype: str):
        self._w(f'"{name}" "{etype}"')
        self._w("{")
        self.indent += 1

    def _write_data_stream(self, name: str, standard_attr: str, semantic: str,
                           sem_idx: int, data_state: int, dtype: str, data: list,
                           formatter=None):
        """Write a CDmePolygonMeshDataStream."""
        self._begin('"CDmePolygonMeshDataStream"')
        self._prop("id", "elementid", _uid())
        self._prop("name", "string", f"{name}:{sem_idx}")
        self._prop("standardAttributeName", "string", standard_attr)
        self._prop("semanticName", "string", semantic)
        self._prop("semanticIndex", "int", str(sem_idx))
        self._prop("vertexBufferLocation", "int", "0")
        self._prop("dataStateFlags", "int", str(data_state))
        self._prop("subdivisionBinding", "element", "")
        self._begin_array("data", dtype)
        for item in data:
            if formatter:
                self._array_item(formatter(item))
            else:
                self._array_item(str(item))
        self._end_array()
        self._end()

    def _write_data_array(self, name: str, size: int, streams_fn):
        """Write a CDmePolygonMeshDataArray block."""
        self._begin_element(name, "CDmePolygonMeshDataArray")
        self._prop("id", "elementid", _uid())
        self._prop("size", "int", str(size))
        self._begin_array("streams", "element_array")
        streams_fn()
        self._end_array()
        self._end()

    def _write_mesh_data(self, mesh: HalfEdgeMesh, materials: list[str], scale: float = 64.0):
        """Write the CDmePolygonMesh block with all topology and data arrays."""
        self._begin_element("meshData", "CDmePolygonMesh")
        self._prop("id", "elementid", _uid())
        self._prop("name", "string", "meshData")

        # vertexEdgeIndices
        self._begin_array("vertexEdgeIndices", "int_array")
        for idx in mesh.vertex_edge_indices:
            self._array_item(str(idx))
        self._end_array()

        # vertexDataIndices
        self._begin_array("vertexDataIndices", "int_array")
        for idx in mesh.vertex_data_indices:
            self._array_item(str(idx))
        self._end_array()

        # edgeVertexIndices
        self._begin_array("edgeVertexIndices", "int_array")
        for idx in mesh.edge_vertex_indices:
            self._array_item(str(idx))
        self._end_array()

        # edgeOppositeIndices
        self._begin_array("edgeOppositeIndices", "int_array")
        for idx in mesh.edge_opposite_indices:
            self._array_item(str(idx))
        self._end_array()

        # edgeNextIndices
        self._begin_array("edgeNextIndices", "int_array")
        for idx in mesh.edge_next_indices:
            self._array_item(str(idx))
        self._end_array()

        # edgeFaceIndices
        self._begin_array("edgeFaceIndices", "int_array")
        for idx in mesh.edge_face_indices:
            self._array_item(str(idx))
        self._end_array()

        # edgeDataIndices
        self._begin_array("edgeDataIndices", "int_array")
        for idx in mesh.edge_data_indices:
            self._array_item(str(idx))
        self._end_array()

        # edgeVertexDataIndices
        self._begin_array("edgeVertexDataIndices", "int_array")
        for idx in mesh.edge_vertex_data_indices:
            self._array_item(str(idx))
        self._end_array()

        # faceEdgeIndices
        self._begin_array("faceEdgeIndices", "int_array")
        for idx in mesh.face_edge_indices:
            self._array_item(str(idx))
        self._end_array()

        # faceDataIndices
        self._begin_array("faceDataIndices", "int_array")
        for idx in mesh.face_data_indices:
            self._array_item(str(idx))
        self._end_array()

        # materials
        self._begin_array("materials", "string_array")
        for mat in materials:
            self._array_item(mat)
        self._end_array()

        # --- vertexData ---
        def write_vertex_streams():
            positions = mesh.vertex_positions
            self._write_data_stream(
                "position", "position", "position", 0, 3,
                "vector3_array", positions, _fmt_vec3
            )

        self._write_data_array("vertexData", mesh.num_vertices, write_vertex_streams)
        self._w("")

        # --- faceVertexData ---
        # Size = total half-edges (face + boundary).  Each HE gets one
        # texcoord, normal, tangent entry.  Boundary HEs get zeros.
        num_fv = mesh.num_half_edges

        # Pre-compute per-face attributes (indexed by face index)
        face_uvs_map = {}   # face_idx -> list of 4 uv pairs
        face_tang_map = {}  # face_idx -> tangent vec4
        for fi in range(mesh.num_faces):
            quad = mesh.face_quads[fi]
            normal = mesh.face_normals[fi]
            # Use model-provided UVs if available, otherwise compute from vertices
            if hasattr(quad, 'texcoords') and quad.texcoords is not None:
                face_uvs_map[fi] = quad.texcoords
            else:
                face_uvs_map[fi] = compute_face_texcoords(quad, scale)
            face_tang_map[fi] = compute_face_tangent(normal)

        # Walk each face to build a map: face_he_final_index -> (face_idx, vertex_position_within_face)
        face_he_info = {}  # final_he_index -> (face_idx, vert_slot 0..3)
        for fi in range(mesh.num_faces):
            he = mesh.face_edge_indices[fi]
            for slot in range(4):
                face_he_info[he] = (fi, slot)
                he = mesh.edge_next_indices[he]

        def write_face_vertex_streams():
            texcoords = []
            normals_data = []
            tangents_data = []

            for hei in range(mesh.num_half_edges):
                if hei in face_he_info:
                    fi, slot = face_he_info[hei]
                    # The UV slot corresponds to the TO vertex of this HE,
                    # which is vertex (slot+1)%4 in the face.
                    uv_slot = (slot + 1) % 4
                    texcoords.append(face_uvs_map[fi][uv_slot])
                    normals_data.append(mesh.face_normals[fi])
                    tangents_data.append(face_tang_map[fi])
                else:
                    # Boundary half-edge: zeros
                    texcoords.append((0.0, 0.0))
                    normals_data.append((0.0, 0.0, 0.0))
                    tangents_data.append((0.0, 0.0, 0.0, 0.0))

            self._write_data_stream(
                "texcoord", "texcoord", "texcoord", 0, 1,
                "vector2_array", texcoords, _fmt_vec2
            )
            self._trailing_comma()
            self._write_data_stream(
                "normal", "normal", "normal", 0, 1,
                "vector3_array", normals_data, _fmt_vec3
            )
            self._trailing_comma()
            self._write_data_stream(
                "tangent", "tangent", "tangent", 0, 1,
                "vector4_array", tangents_data, _fmt_vec4
            )

        self._write_data_array("faceVertexData", num_fv, write_face_vertex_streams)
        self._w("")

        # --- edgeData ---
        def write_edge_streams():
            flags = [0] * mesh.num_geometric_edges
            self._write_data_stream(
                "flags", "flags", "flags", 0, 3,
                "int_array", flags
            )

        self._write_data_array("edgeData", mesh.num_geometric_edges, write_edge_streams)
        self._w("")

        # --- faceData ---
        def write_face_streams():
            tex_scales = []
            tex_axis_u = []
            tex_axis_v = []
            mat_indices = []
            face_flags = []
            lightmap_sb = []

            # Build material index map
            mat_index_map = {}
            for mi, mat in enumerate(materials):
                mat_index_map[mat] = mi

            for fi in range(mesh.num_faces):
                quad = mesh.face_quads[fi]
                normal = mesh.face_normals[fi]

                tex_scales.append((DEFAULT_TEXTURE_SCALE, DEFAULT_TEXTURE_SCALE))
                axis_u, axis_v = compute_texture_axes(normal)
                tex_axis_u.append(axis_u)
                tex_axis_v.append(axis_v)

                # Material index lookup
                from config.blocks import get_block_base_name, get_texture_name_for_face
                # Prefer model-resolved texture name if available
                mat_path = None
                if hasattr(quad, 'texture_name') and quad.texture_name:
                    for mat in materials:
                        if mat.endswith(f"/{quad.texture_name}.vmat"):
                            mat_path = mat
                            break
                if mat_path is None:
                    block_base = get_block_base_name(quad.block_type)
                    mat_path = _get_material_for_block(block_base, materials, quad.face_dir)
                mat_idx = mat_index_map.get(mat_path, 0)
                mat_indices.append(mat_idx)
                face_flags.append(0)
                lightmap_sb.append(0)

            self._write_data_stream(
                "textureScale", "textureScale", "textureScale", 0, 0,
                "vector2_array", tex_scales, _fmt_vec2
            )
            self._trailing_comma()
            self._write_data_stream(
                "textureAxisU", "textureAxisU", "textureAxisU", 0, 0,
                "vector4_array", tex_axis_u, _fmt_vec4
            )
            self._trailing_comma()
            self._write_data_stream(
                "textureAxisV", "textureAxisV", "textureAxisV", 0, 0,
                "vector4_array", tex_axis_v, _fmt_vec4
            )
            self._trailing_comma()
            self._write_data_stream(
                "materialindex", "materialindex", "materialindex", 0, 8,
                "int_array", mat_indices
            )
            self._trailing_comma()
            self._write_data_stream(
                "flags", "flags", "flags", 0, 3,
                "int_array", face_flags
            )
            self._trailing_comma()
            self._write_data_stream(
                "lightmapScaleBias", "lightmapScaleBias", "lightmapScaleBias", 0, 1,
                "int_array", lightmap_sb
            )

        self._write_data_array("faceData", mesh.num_faces, write_face_streams)
        self._w("")

        # --- subdivisionData ---
        # Write minimal subdivisionData (empty arrays).
        # Hammer regenerates this on save; skipping the per-half-edge zeros
        # drastically reduces file size for large maps.
        self._begin_element("subdivisionData", "CDmePolygonMeshSubdivisionData")
        self._prop("id", "elementid", _uid())
        self._begin_array("subdivisionLevels", "int_array")
        self._end_array()
        self._begin_array("streams", "element_array")
        self._end_array()
        self._end()

        # Close meshData
        self._w("")
        self._end()

    def _write_mesh_properties(self, physics_type: str = "default",
                               disable_shadows: bool = False):
        """Write CMapMesh properties after meshData."""
        self._prop("origin", "vector3", "0 0 0")
        self._prop("angles", "qangle", "0 0 0")
        self._prop("scales", "vector3", "1 1 1")
        self._prop("transformLocked", "bool", "0")
        self._prop("force_hidden", "bool", "0")
        self._prop("editorOnly", "bool", "0")
        self._prop("customVisGroup", "string", "")
        self._prop("randomSeed", "int", str(_rand_seed()))
        self._prop("disableShadows", "int", "1" if disable_shadows else "0")
        self._prop("bakelighting", "bool", "1")
        self._prop("cubeMapName", "string", "")
        self._prop("emissiveLightingEnabled", "bool", "1")
        self._prop("emissiveLightingBoost", "float", "1")
        self._prop("lightingDummy", "bool", "0")
        self._prop("visexclude", "bool", "0")
        self._prop("disablemerging", "bool", "0")
        self._prop("renderwithdynamic", "bool", "0")
        self._prop("renderToCubemaps", "bool", "1")
        self._prop("keep_vertices", "bool", "0")
        self._prop("fademindist", "float", "-1")
        self._prop("fademaxdist", "float", "0")
        self._prop("disableHeightDisplacement", "bool", "0")
        self._prop("smoothingAngle", "float", f"{DEFAULT_SMOOTHING_ANGLE:g}")
        self._prop("tintColor", "color", "255 255 255 255")
        self._prop("renderAmt", "int", "255")
        self._prop("physicsType", "string", physics_type)
        self._prop("physicsCollisionProperty", "string", "")
        self._prop("physicsGroup", "string", "")
        self._prop("physicsInteractsAs", "string", "")
        self._prop("physicsInteractsWith", "string", "")
        self._prop("physicsInteractsExclude", "string", "")
        self._prop("physicsSimplificationOverride", "bool", "0")
        self._prop("physicsSimplificationError", "float", "0")

    def _write_entity_properties(self):
        """Write the worldspawn entity properties block."""
        self._begin_element("entity_properties", "EditGameClassProps")
        self._prop("id", "elementid", _uid())
        self._prop("classname", "string", "worldspawn")
        self._prop("targetname", "string", "")
        self._prop("skyname", "string", DEFAULT_SKY)
        self._prop("startdark", "string", "0")
        self._prop("startcolor", "string", "0 0 0")
        self._prop("pvstype", "string", "10")
        self._prop("newunit", "string", "0")
        self._prop("maxpropscreenwidth", "string", "-1")
        self._prop("minpropscreenwidth", "string", "0")
        self._prop("max_lightmap_resolution", "string", "0")
        self._prop("lightmap_queries", "string", "1")
        # Steam Audio settings
        for prefix in ["reverb", "pathing", "customdata"]:
            self._prop(f"steamaudio_{prefix}_rebake_option", "string", "0")
            self._prop(f"steamaudio_{prefix}_generation_type", "string", "0")
            self._prop(f"steamaudio_{prefix}_filter_volumes", "string", "1")
            self._prop(f"steamaudio_{prefix}_filter_navmesh", "string", "0")
            self._prop(f"steamaudio_{prefix}_grid_spacing", "string", "6")
            self._prop(f"steamaudio_{prefix}_height_above_floor", "string", "1.5")

        self._prop("steamaudio_reverb_rays", "string", "32768")
        self._prop("steamaudio_reverb_bounces", "string", "32")
        self._prop("steamaudio_reverb_ir_duration", "string", "1.0")
        self._prop("steamaudio_reverb_ambisonic_order", "string", "1")
        self._prop("steamaudio_reverb_clustering_enable", "string", "0")
        self._prop("steamaudio_reverb_clustering_cubemap_resolution", "string", "16")
        self._prop("steamaudio_reverb_clustering_depth_threshold", "string", "10.0")
        self._prop("steamaudio_pathing_visibility_samples", "string", "1")
        self._prop("steamaudio_pathing_visibility_radius", "string", "0.0")
        self._prop("steamaudio_pathing_visibility_threshold", "string", "0.1")
        self._prop("steamaudio_pathing_visibility_pathrange", "string", "100.0")
        self._prop("steamaudio_customdata_bake_occlusion", "string", "0")
        self._prop("steamaudio_customdata_bake_dimensions", "string", "0")
        self._prop("steamaudio_customdata_bake_materials", "string", "0")
        self._prop("steamaudio_customdata_occlusion_pathing", "string", "1")
        self._prop("steamaudio_customdata_occlusion_reflection", "string", "0")
        self._prop("steamaudio_customdata_occlusion_reflection_rays", "string", "8192")
        self._prop("steamaudio_customdata_occlusion_reflection_bounces", "string", "8")
        self._end()

    def _write_func_water_entity_props(self):
        """Write entity_properties for a func_water entity."""
        self._begin_element("entity_properties", "EditGameClassProps")
        self._prop("id", "elementid", _uid())
        self._prop("classname", "string", "func_water")
        self._prop("vscripts", "string", "")
        self._prop("targetname", "string", "")
        self._prop("parentname", "string", "")
        self._prop("parentAttachmentName", "string", "")
        self._prop("useLocalOffset", "string", "0")
        self._prop("local.origin", "string", "")
        self._prop("local.angles", "string", "")
        self._prop("local.scales", "string", "")
        self._end()

    def _write_trigger_hurt_entity_props(self):
        """Write entity_properties for a trigger_hurt entity."""
        self._begin_element("entity_properties", "EditGameClassProps")
        self._prop("id", "elementid", _uid())
        self._prop("classname", "string", "trigger_hurt")
        self._prop("vscripts", "string", "")
        self._prop("targetname", "string", "")
        self._prop("parentname", "string", "")
        self._prop("parentAttachmentName", "string", "")
        self._prop("useLocalOffset", "string", "0")
        self._prop("local.origin", "string", "")
        self._prop("local.angles", "string", "")
        self._prop("local.scales", "string", "")
        self._prop("StartDisabled", "string", "0")
        self._prop("globalname", "string", "")
        self._prop("spawnflags", "string", "4097")
        self._prop("filtername", "string", "")
        self._prop("master", "string", "")
        self._prop("damage", "string", "10")
        self._prop("damagecap", "string", "20")
        self._prop("damagetype", "string", "0")
        self._prop("damagemodel", "string", "0")
        self._prop("forgivedelay", "string", "3")
        self._prop("nodmgforce", "string", "0")
        self._prop("damageforce", "string", "")
        self._prop("thinkalways", "string", "0")
        self._end()

    def _write_slime_bounce_entity_props(self):
        """Write entity_properties for a slime bounce trigger_multiple entity."""
        self._begin_element("entity_properties", "EditGameClassProps")
        self._prop("id", "elementid", _uid())
        self._prop("classname", "string", "trigger_multiple")
        self._prop("vscripts", "string", "")
        self._prop("targetname", "string", "")
        self._prop("parentname", "string", "")
        self._prop("parentAttachmentName", "string", "")
        self._prop("useLocalOffset", "string", "0")
        self._prop("local.origin", "string", "")
        self._prop("local.angles", "string", "")
        self._prop("local.scales", "string", "")
        self._prop("StartDisabled", "string", "0")
        self._prop("globalname", "string", "")
        self._prop("spawnflags", "string", "4097")
        self._prop("filtername", "string", "")
        self._prop("wait", "string", "0")
        self._end()

    def _write_point_script_entity(self, script_path: str,
                                   node_id_start: int) -> int:
        """Write a point_script entity that runs a JavaScript script.

        Returns:
            Next available node_id after writing
        """
        self._begin('"CMapEntity"')
        self._prop("id", "elementid", _uid())
        self._prop("nodeID", "int", str(node_id_start))
        self._prop("referenceID", "uint64", _rand_ref())
        self._begin_array("children", "element_array")
        self._end_array()
        self._begin_array("variableTargetKeys", "string_array")
        self._end_array()
        self._begin_array("variableNames", "string_array")
        self._end_array()

        self._begin_element("relayPlugData", "DmePlugList")
        self._prop("id", "elementid", _uid())
        self._begin_array("names", "string_array")
        self._end_array()
        self._begin_array("dataTypes", "int_array")
        self._end_array()
        self._begin_array("plugTypes", "int_array")
        self._end_array()
        self._begin_array("descriptions", "string_array")
        self._end_array()
        self._end()
        self._w("")

        self._begin_array("connectionsData", "element_array")
        self._end_array()

        self._begin_element("entity_properties", "EditGameClassProps")
        self._prop("id", "elementid", _uid())
        self._prop("classname", "string", "point_script")
        self._prop("targetname", "string", "mc_script")
        self._prop("cs_script", "string", script_path)
        self._end()
        self._w("")

        self._prop("hitNormal", "vector3", "0 0 1")
        self._prop("isProceduralEntity", "bool", "0")
        self._prop("origin", "vector3", "0 0 0")
        self._prop("angles", "qangle", "0 0 0")
        self._prop("scales", "vector3", "1 1 1")
        self._prop("transformLocked", "bool", "0")
        self._prop("force_hidden", "bool", "0")
        self._prop("editorOnly", "bool", "0")
        self._prop("customVisGroup", "string", "")
        self._prop("randomSeed", "int", str(_rand_seed()))
        self._end()  # CMapEntity

        return node_id_start + 1

    def _write_light_entity(self, x: float, y: float, z: float,
                            color: str, lumens: int, light_range: float,
                            node_id_start: int) -> int:
        """Write a light_omni2 entity at the given CS2 position.

        Returns:
            Next available node_id after writing
        """
        self._begin('"CMapEntity"')
        self._prop("id", "elementid", _uid())
        self._prop("nodeID", "int", str(node_id_start))
        self._prop("referenceID", "uint64", _rand_ref())
        self._begin_array("children", "element_array")
        self._end_array()
        self._begin_array("variableTargetKeys", "string_array")
        self._end_array()
        self._begin_array("variableNames", "string_array")
        self._end_array()

        self._begin_element("relayPlugData", "DmePlugList")
        self._prop("id", "elementid", _uid())
        self._begin_array("names", "string_array")
        self._end_array()
        self._begin_array("dataTypes", "int_array")
        self._end_array()
        self._begin_array("plugTypes", "int_array")
        self._end_array()
        self._begin_array("descriptions", "string_array")
        self._end_array()
        self._end()
        self._w("")

        self._begin_array("connectionsData", "element_array")
        self._end_array()

        self._begin_element("entity_properties", "EditGameClassProps")
        self._prop("id", "elementid", _uid())
        self._prop("classname", "string", "light_omni2")
        self._prop("targetname", "string", "")
        self._prop("enabled", "string", "1")
        self._prop("color", "string", color)
        self._prop("colormode", "string", "0")
        self._prop("brightness_lumens", "string", str(lumens))
        self._prop("brightness_units", "string", "1")
        self._prop("range", "string", f"{light_range:g}")
        self._prop("skirt", "string", "0.1")
        self._prop("castshadows", "string", "2")
        self._prop("falloff", "string", "1")
        self._prop("bouncelight", "string", "1")
        self._prop("bouncescale", "string", "1.0")
        self._prop("rendertocubemaps", "string", "1")
        self._end()
        self._w("")

        self._prop("hitNormal", "vector3", "0 0 1")
        self._prop("isProceduralEntity", "bool", "0")
        self._prop("origin", "vector3", f"{x:g} {y:g} {z:g}")
        self._prop("angles", "qangle", "0 0 0")
        self._prop("scales", "vector3", "1 1 1")
        self._prop("transformLocked", "bool", "0")
        self._prop("force_hidden", "bool", "0")
        self._prop("editorOnly", "bool", "0")
        self._prop("customVisGroup", "string", "")
        self._prop("randomSeed", "int", str(_rand_seed()))
        self._end()  # CMapEntity

        return node_id_start + 1

    def _write_entity_mesh(self, meshes, materials: list[str],
                           entity_type: str, node_id_start: int,
                           scale: float = 64.0) -> int:
        """Write a CMapEntity wrapping one or more CMapMesh children.

        Args:
            meshes: A single HalfEdgeMesh or list of HalfEdgeMesh objects
            materials: Material paths list
            entity_type: "func_water", "trigger_hurt", or "slime_bounce"
            node_id_start: Starting node ID counter
            scale: Block scale

        Returns:
            Next available node_id after writing
        """
        # Normalize to list
        if not isinstance(meshes, list):
            meshes = [meshes]

        entity_node_id = node_id_start
        next_node_id = node_id_start + 1

        self._begin('"CMapEntity"')
        self._prop("id", "elementid", _uid())
        self._prop("nodeID", "int", str(entity_node_id))
        self._prop("referenceID", "uint64", _rand_ref())

        # Children: CMapMesh objects
        self._begin_array("children", "element_array")
        for mi, mesh in enumerate(meshes):
            self._begin('"CMapMesh"')
            self._prop("id", "elementid", _uid())
            self._prop("nodeID", "int", str(next_node_id))
            self._prop("referenceID", "uint64", _rand_ref())
            self._begin_array("children", "element_array")
            self._end_array()
            self._begin_array("variableTargetKeys", "string_array")
            self._end_array()
            self._begin_array("variableNames", "string_array")
            self._end_array()
            self._write_mesh_data(mesh, materials, scale)
            self._w("")
            self._write_mesh_properties()

            # Extra entity-mesh properties
            self._begin_array("physicsIncludedDetailLayers", "element_array")
            self._end_array()
            self._begin_array("physicsMissingDetailLayers", "element_array")
            self._end_array()

            self._end()  # CMapMesh
            if mi < len(meshes) - 1:
                self._trailing_comma()
            next_node_id += 1
        self._end_array()  # children

        # Entity boilerplate
        self._begin_array("variableTargetKeys", "string_array")
        self._end_array()
        self._begin_array("variableNames", "string_array")
        self._end_array()

        self._begin_element("relayPlugData", "DmePlugList")
        self._prop("id", "elementid", _uid())
        self._begin_array("names", "string_array")
        self._end_array()
        self._begin_array("dataTypes", "int_array")
        self._end_array()
        self._begin_array("plugTypes", "int_array")
        self._end_array()
        self._begin_array("descriptions", "string_array")
        self._end_array()
        self._end()
        self._w("")

        self._begin_array("connectionsData", "element_array")
        if entity_type == "slime_bounce":
            self._begin('"DmeConnectionData"')
            self._prop("id", "elementid", _uid())
            self._prop("outputName", "string", "OnStartTouch")
            self._prop("targetType", "int", "7")
            self._prop("targetName", "string", "mc_script")
            self._prop("inputName", "string", "RunScriptInput")
            self._prop("overrideParam", "string", "slime_bounce")
            self._prop("delay", "float", "0")
            self._prop("timesToFire", "int", "-1")
            self._end()
            self._trailing_comma()
            self._begin('"DmeConnectionData"')
            self._prop("id", "elementid", _uid())
            self._prop("outputName", "string", "OnEndTouch")
            self._prop("targetType", "int", "7")
            self._prop("targetName", "string", "mc_script")
            self._prop("inputName", "string", "RunScriptInput")
            self._prop("overrideParam", "string", "slime_exit")
            self._prop("delay", "float", "0")
            self._prop("timesToFire", "int", "-1")
            self._end()
        self._end_array()

        # Entity properties
        if entity_type == "func_water":
            self._write_func_water_entity_props()
        elif entity_type == "trigger_hurt":
            self._write_trigger_hurt_entity_props()
        elif entity_type == "slime_bounce":
            self._write_slime_bounce_entity_props()
        self._w("")

        self._prop("hitNormal", "vector3", "0 0 1")
        self._prop("isProceduralEntity", "bool", "0")
        self._prop("origin", "vector3", "0 0 0")
        self._prop("angles", "qangle", "0 0 0")
        self._prop("scales", "vector3", "1 1 1")
        self._prop("transformLocked", "bool", "0")
        self._prop("force_hidden", "bool", "0")
        self._prop("editorOnly", "bool", "0")
        self._prop("customVisGroup", "string", "")
        self._prop("randomSeed", "int", str(_rand_seed()))
        self._end()  # CMapEntity

        return next_node_id

    def write_vmap(self, meshes: list[HalfEdgeMesh], materials: list[str],
                   material_map: dict[str, str] = None,
                   scale: float = 64.0,
                   entity_meshes: list[tuple] = None,
                   mesh_physics_types: list[str] = None,
                   mesh_disable_shadows: list[bool] = None,
                   script_path: str = None,
                   light_sources: list[tuple] = None) -> str:
        """Generate a complete .vmap file string.

        Args:
            meshes: List of HalfEdgeMesh objects (one per CMapMesh)
            materials: List of material paths used
            material_map: Optional block_type -> material path mapping
            scale: Block size in Hammer units
            entity_meshes: Optional list of (HalfEdgeMesh, entity_type) tuples
                           where entity_type is "func_water", "trigger_hurt",
                           or "slime_bounce"
            mesh_physics_types: Optional list of physics type strings per mesh
                                ("default" or "none"), same length as meshes.
            mesh_disable_shadows: Optional list of bools per mesh, same length
                                  as meshes. True disables shadow casting.
            script_path: Optional script path for point_script entity (e.g.
                         "scripts/slime_bounce.js")
            light_sources: Optional list of (cs2_x, cs2_y, cs2_z, block_name)
                           tuples for auto-placed light_omni2 entities.

        Returns:
            Complete .vmap file content as string
        """
        self.lines = []
        self.indent = 0
        self._material_map = material_map or {}

        # DMX header
        self.lines.append("<!-- dmx encoding keyvalues2 4 format vmap 40 -->")

        # $prefix_element$
        self._begin('"$prefix_element$"')
        self._prop("id", "elementid", _uid())
        self._begin_array("map_asset_references", "string_array")
        for mat in materials:
            self._array_item(mat)
        if script_path:
            self._array_item(script_path)
        self._end_array()
        self._end()

        # CMapRootElement
        self._begin('"CMapRootElement"')
        self._prop("id", "elementid", _uid())
        self._prop("isprefab", "bool", "0")
        self._prop("editorbuild", "int", str(EDITOR_BUILD))
        self._prop("editorversion", "int", str(EDITOR_VERSION))
        self._prop("itemFile", "string", "")

        # Default camera
        self._begin_element("defaultcamera", "CStoredCamera")
        self._prop("id", "elementid", _uid())
        self._prop("position", "vector3", "0 -1000 1000")
        self._prop("lookat", "vector3", "0 0 0")
        self._end()
        self._w("")

        # 3D cameras
        self._begin_element("3dcameras", "CStoredCameras")
        self._prop("id", "elementid", _uid())
        self._prop("activecamera", "int", "-1")
        self._begin_array("cameras", "element_array")
        self._end_array()
        self._end()
        self._w("")

        # World
        self._begin_element("world", "CMapWorld")
        self._prop("id", "elementid", _uid())
        self._prop("nodeID", "int", "1")
        self._prop("referenceID", "uint64", "0x0")

        # Children (CMapMesh objects + entity-wrapped meshes + point_script + lights)
        has_entities = entity_meshes and len(entity_meshes) > 0
        has_script = script_path is not None
        has_lights = light_sources and len(light_sources) > 0
        total_children = (len(meshes)
                          + (len(entity_meshes) if has_entities else 0)
                          + (1 if has_script else 0)
                          + (len(light_sources) if has_lights else 0))

        self._begin_array("children", "element_array")
        node_id = 2
        for mi, mesh in enumerate(meshes):
            self._begin('"CMapMesh"')
            self._prop("id", "elementid", _uid())
            self._prop("nodeID", "int", str(node_id))
            self._prop("referenceID", "uint64", _rand_ref())
            self._begin_array("children", "element_array")
            self._end_array()
            self._begin_array("variableTargetKeys", "string_array")
            self._end_array()
            self._begin_array("variableNames", "string_array")
            self._end_array()
            self._write_mesh_data(mesh, materials, scale)
            self._w("")
            pt = "default"
            if mesh_physics_types and mi < len(mesh_physics_types):
                pt = mesh_physics_types[mi]
            noshadow = False
            if mesh_disable_shadows and mi < len(mesh_disable_shadows):
                noshadow = mesh_disable_shadows[mi]
            self._write_mesh_properties(physics_type=pt,
                                        disable_shadows=noshadow)
            self._end()
            child_idx = mi
            if child_idx < total_children - 1:
                self._trailing_comma()
            node_id += 1

        # Write entity-wrapped meshes (func_water, trigger_hurt, slime_bounce)
        if has_entities:
            for ei, (ent_mesh, ent_type) in enumerate(entity_meshes):
                node_id = self._write_entity_mesh(
                    ent_mesh, materials, ent_type, node_id, scale
                )
                child_idx = len(meshes) + ei
                if child_idx < total_children - 1:
                    self._trailing_comma()

        # Write point_script entity for scripts (slime bounce, etc.)
        if has_script:
            node_id = self._write_point_script_entity(script_path, node_id)
            if has_lights:
                self._trailing_comma()

        # Write light_omni2 entities for auto-lighting
        if has_lights:
            from config.blocks import get_light_properties
            scale_factor = scale / 40.0  # table values calibrated at scale=40
            for li, (lx, ly, lz, block_name) in enumerate(light_sources):
                props = get_light_properties(block_name)
                if props is None:
                    continue
                level, color, lumens = props
                # Scale lumens and range proportionally to block scale
                lumens = int(lumens * scale_factor)
                # Range = 62.5% of base lumens, scaled (250 range for 400 lumen torch)
                light_range = props[2] * 0.625 * scale_factor
                node_id = self._write_light_entity(
                    lx, ly, lz, color, lumens, light_range, node_id)
                if li < len(light_sources) - 1:
                    self._trailing_comma()

        self._end_array()

        # World variable/relay/connections
        self._begin_array("variableTargetKeys", "string_array")
        self._end_array()
        self._begin_array("variableNames", "string_array")
        self._end_array()

        # relayPlugData
        self._begin_element("relayPlugData", "DmePlugList")
        self._prop("id", "elementid", _uid())
        self._begin_array("names", "string_array")
        self._end_array()
        self._begin_array("dataTypes", "int_array")
        self._end_array()
        self._begin_array("plugTypes", "int_array")
        self._end_array()
        self._begin_array("descriptions", "string_array")
        self._end_array()
        self._end()
        self._w("")

        self._begin_array("connectionsData", "element_array")
        self._end_array()

        # Entity properties
        self._write_entity_properties()
        self._w("")

        self._prop("nextDecalID", "int", "0")
        self._prop("fixupEntityNames", "bool", "1")
        self._prop("mapUsageType", "string", "standard")
        self._prop("origin", "vector3", "0 0 0")
        self._prop("angles", "qangle", "0 0 0")
        self._prop("scales", "vector3", "1 1 1")
        self._prop("transformLocked", "bool", "0")
        self._prop("force_hidden", "bool", "0")
        self._prop("editorOnly", "bool", "0")
        self._prop("customVisGroup", "string", "")
        self._prop("randomSeed", "int", str(_rand_seed()))
        self._end()  # CMapWorld
        self._w("")

        # Visibility manager
        self._begin_element("visbility", "CVisibilityMgr")
        self._prop("id", "elementid", _uid())
        self._prop("nodeID", "int", "0")
        self._prop("referenceID", "uint64", "0x0")
        self._begin_array("children", "element_array")
        self._end_array()
        self._begin_array("variableTargetKeys", "string_array")
        self._end_array()
        self._begin_array("variableNames", "string_array")
        self._end_array()
        self._begin_array("nodes", "element_array")
        self._end_array()
        self._begin_array("hiddenFlags", "int_array")
        self._end_array()
        self._prop("origin", "vector3", "0 0 0")
        self._prop("angles", "qangle", "0 0 0")
        self._prop("scales", "vector3", "1 1 1")
        self._prop("transformLocked", "bool", "0")
        self._prop("force_hidden", "bool", "0")
        self._prop("editorOnly", "bool", "0")
        self._prop("customVisGroup", "string", "")
        self._prop("randomSeed", "int", str(_rand_seed()))
        self._end()
        self._w("")

        # Map variables
        self._begin_element("mapVariables", "CMapVariableSet")
        self._prop("id", "elementid", _uid())
        self._begin_array("variableNames", "string_array")
        self._end_array()
        self._begin_array("variableValues", "string_array")
        self._end_array()
        self._begin_array("variableTypeNames", "string_array")
        self._end_array()
        self._begin_array("variableTypeParameters", "string_array")
        self._end_array()
        self._begin_array("m_ChoiceGroups", "element_array")
        self._end_array()
        self._end()
        self._w("")

        # Root selection set
        self._begin_element("rootSelectionSet", "CMapSelectionSet")
        self._prop("id", "elementid", _uid())
        self._begin_array("children", "element_array")
        self._end_array()
        self._prop("selectionSetName", "string", "")
        self._prop("selectionSetData", "element", "")
        self._end()
        self._w("")

        # Trailing arrays
        self._begin_array("m_ReferencedMeshSnapshots", "element_array")
        self._end_array()
        self._prop("m_bIsCordoning", "bool", "0")
        self._prop("m_bCordonsVisible", "bool", "0")
        self._begin_array("nodeInstanceData", "element_array")
        self._end_array()

        self._end()  # CMapRootElement
        self._w("")

        return "\n".join(self.lines)


def _get_material_for_block(block_base: str, materials: list[str],
                            face_dir: str = None) -> str:
    """Get material path for a block type + face direction."""
    from config.blocks import get_texture_name, get_texture_name_for_face

    # Try face-specific texture first
    if face_dir:
        tex_name = get_texture_name_for_face(block_base, face_dir)
        for mat in materials:
            if mat.endswith(f"/{tex_name}.vmat"):
                return mat

    # Fallback to base texture name
    tex_name = get_texture_name(block_base)
    for mat in materials:
        if mat.endswith(f"/{tex_name}.vmat"):
            return mat

    # Default fallback
    return materials[0] if materials else DEFAULT_MATERIAL


def write_vmap_file(filepath: str, meshes: list[HalfEdgeMesh],
                    materials: list[str], material_map: dict = None,
                    scale: float = 64.0,
                    entity_meshes: list[tuple] = None,
                    mesh_physics_types: list[str] = None,
                    mesh_disable_shadows: list[bool] = None,
                    script_path: str = None,
                    light_sources: list[tuple] = None,
                    max_indent: int = 0):
    """Write a .vmap file to disk.

    Args:
        filepath: Output .vmap file path
        meshes: List of HalfEdgeMesh objects
        materials: List of material paths
        material_map: Optional block_type -> material path mapping
        scale: Block size in Hammer units (default 64)
        entity_meshes: Optional list of (HalfEdgeMesh, entity_type) tuples
        mesh_physics_types: Optional list of physics type strings per mesh
        mesh_disable_shadows: Optional list of bools per mesh (True = no shadows)
        script_path: Optional script path for point_script entity
        light_sources: Optional list of (x, y, z, block_name) for light entities
        max_indent: Maximum indentation depth (0 = unlimited). Lower values
                    reduce file size by capping tab indentation.
    """
    writer = VMapWriter(max_indent=max_indent)
    content = writer.write_vmap(meshes, materials, material_map, scale=scale,
                                entity_meshes=entity_meshes,
                                mesh_physics_types=mesh_physics_types,
                                mesh_disable_shadows=mesh_disable_shadows,
                                script_path=script_path,
                                light_sources=light_sources)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
