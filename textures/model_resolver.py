"""Minecraft block model resolver: reads blockstates + models to determine per-face textures.

Walks the blockstate → model → parent chain from vanilla Minecraft assets
to resolve which texture each face of a block actually uses.
"""

import json
import os
import zipfile


# Minecraft face names → our face_dir format
# MC coords: X=east, Y=up, Z=south
MC_FACE_TO_DIR = {
    "up": "+y",
    "down": "-y",
    "east": "+x",
    "west": "-x",
    "south": "+z",
    "north": "-z",
}

# Blocks with no proper face model that need special texture mapping
SPECIAL_TEXTURE_BLOCKS = {
    "water": {"all": "water_still"},
    "lava": {"all": "lava_still"},
}


class ModelResolver:
    """Resolves Minecraft block names to per-face texture names using blockstate/model data."""

    def __init__(self, assets_path: str):
        """Initialize with path to Minecraft assets.

        Args:
            assets_path: Path to either:
                - A folder containing assets/minecraft/ (resource pack root)
                - A folder that IS assets/minecraft/
                - A .zip resource pack file
        """
        self._zip = None
        self._folder = None

        if os.path.isfile(assets_path) and assets_path.lower().endswith(".zip"):
            self._zip = zipfile.ZipFile(assets_path, "r")
        elif os.path.isdir(assets_path):
            # Check if this is the root (has assets/) or is assets/minecraft/ itself
            if os.path.isdir(os.path.join(assets_path, "assets", "minecraft")):
                self._folder = os.path.join(assets_path, "assets", "minecraft")
            elif os.path.isdir(os.path.join(assets_path, "blockstates")):
                self._folder = assets_path
            else:
                raise ValueError(f"Cannot find Minecraft assets in: {assets_path}")
        else:
            raise ValueError(f"Invalid assets path: {assets_path}")

        self._cache = {}
        self._model_cache = {}

    def close(self):
        if self._zip:
            self._zip.close()

    def _read_json(self, rel_path: str) -> dict | None:
        """Read a JSON file from the assets."""
        try:
            if self._zip:
                full = f"assets/minecraft/{rel_path}"
                with self._zip.open(full) as f:
                    return json.loads(f.read().decode("utf-8"))
            else:
                full = os.path.join(self._folder, rel_path)
                if os.path.isfile(full):
                    with open(full, "r", encoding="utf-8") as f:
                        return json.load(f)
        except (KeyError, FileNotFoundError, json.JSONDecodeError):
            pass
        return None

    def _extract_first_model(self, blockstate: dict) -> str | None:
        """Get the first model reference from a blockstate definition."""
        variants = blockstate.get("variants", {})
        if variants:
            # Get first variant (prefer "" empty key, else first available)
            first = variants.get("")
            if first is None:
                # Try common default variants
                for key in variants:
                    first = variants[key]
                    break

            if isinstance(first, list):
                first = first[0]
            if isinstance(first, dict):
                return first.get("model")
        # Multipart blocks — try first multipart apply
        multipart = blockstate.get("multipart", [])
        if multipart:
            apply = multipart[0].get("apply", {})
            if isinstance(apply, list):
                apply = apply[0]
            return apply.get("model")
        return None

    def _read_model_chain(self, model_ref: str) -> tuple[dict, list | None]:
        """Read a model and walk its parent chain, collecting all textures and elements.

        Returns (merged_textures, elements_or_None).
        Elements from the lowest model in the chain that has them are used.
        """
        if model_ref in self._model_cache:
            return self._model_cache[model_ref]

        # Normalize reference: "minecraft:block/stone" → "block/stone"
        name = model_ref.replace("minecraft:", "")
        model_data = self._read_json(f"models/{name}.json")
        if model_data is None:
            self._model_cache[model_ref] = ({}, None)
            return ({}, None)

        # Get parent's textures and elements first
        parent_textures = {}
        parent_elements = None
        parent_ref = model_data.get("parent")
        if parent_ref:
            parent_textures, parent_elements = self._read_model_chain(parent_ref)

        # Child textures override parent
        merged = dict(parent_textures)
        merged.update(model_data.get("textures", {}))

        # Child elements override parent elements
        elements = model_data.get("elements", parent_elements)

        self._model_cache[model_ref] = (merged, elements)
        return (merged, elements)

    def _resolve_texture_ref(self, ref: str, textures: dict, depth: int = 0) -> str | None:
        """Resolve a texture reference like '#all' through the textures dict."""
        if depth > 10:
            return None
        if not ref:
            return None
        if ref.startswith("#"):
            key = ref[1:]
            if key in textures:
                return self._resolve_texture_ref(textures[key], textures, depth + 1)
            return None
        # It's a concrete texture path like "minecraft:block/stone" or "block/stone"
        return ref

    def _texture_ref_to_name(self, ref: str) -> str:
        """Convert a texture reference to a simple name.

        'minecraft:block/stone' → 'stone'
        'block/stone' → 'stone'
        """
        ref = ref.replace("minecraft:", "")
        if "/" in ref:
            return ref.rsplit("/", 1)[1]
        return ref

    def get_face_textures(self, block_name: str) -> dict[str, str] | None:
        """Resolve a block to its per-face texture names.

        Args:
            block_name: Block name like 'minecraft:stone' or 'stone'

        Returns:
            Dict mapping face_dir (+x,-x,+y,-y,+z,-z) to texture name (e.g., 'stone'),
            or None if the block cannot be resolved.
        """
        # Normalize
        name = block_name.split("[")[0]  # strip block state
        name = name.replace("minecraft:", "")

        if name in self._cache:
            return self._cache[name]

        # Check special blocks first
        if name in SPECIAL_TEXTURE_BLOCKS:
            spec = SPECIAL_TEXTURE_BLOCKS[name]
            if "all" in spec:
                result = {d: spec["all"] for d in MC_FACE_TO_DIR.values()}
            else:
                result = {MC_FACE_TO_DIR[mc]: tex for mc, tex in spec.items()
                          if mc in MC_FACE_TO_DIR}
            self._cache[name] = result
            return result

        # Read blockstate
        blockstate = self._read_json(f"blockstates/{name}.json")
        if blockstate is None:
            self._cache[name] = None
            return None

        # Get first model
        model_ref = self._extract_first_model(blockstate)
        if model_ref is None:
            self._cache[name] = None
            return None

        # Walk model chain to collect all textures and elements
        textures, elements = self._read_model_chain(model_ref)
        if not textures:
            self._cache[name] = None
            return None

        # If model has inline elements, extract face→texture from the first full-block element
        face_texture_vars = {}
        if elements:
            for elem in elements:
                from_pos = elem.get("from", [0, 0, 0])
                to_pos = elem.get("to", [16, 16, 16])
                # Only use full-block elements (0,0,0 to 16,16,16)
                if from_pos == [0, 0, 0] and to_pos == [16, 16, 16]:
                    faces = elem.get("faces", {})
                    for mc_face, face_data in faces.items():
                        if mc_face not in face_texture_vars:
                            tex_ref = face_data.get("texture", "")
                            face_texture_vars[mc_face] = tex_ref
                    break  # Use only first full-block element

        # Resolve per-face textures
        mc_faces = ["up", "down", "north", "south", "east", "west"]
        result = {}
        for mc_face in mc_faces:
            face_dir = MC_FACE_TO_DIR[mc_face]

            # Try inline element texture ref first
            ref = face_texture_vars.get(mc_face)
            if not ref:
                # Fall back to standard face names from parent chain
                ref = textures.get(mc_face)

            if ref:
                resolved = self._resolve_texture_ref(ref, textures)
                if resolved:
                    result[face_dir] = self._texture_ref_to_name(resolved)

        # If no faces resolved but we have an "all" or "particle" texture, use it
        if not result:
            for fallback_key in ("all", "particle"):
                ref = textures.get(fallback_key)
                if ref:
                    resolved = self._resolve_texture_ref(ref, textures)
                    if resolved:
                        tex_name = self._texture_ref_to_name(resolved)
                        result = {d: tex_name for d in MC_FACE_TO_DIR.values()}
                        break

        self._cache[name] = result if result else None
        return result if result else None

    def get_all_block_textures(self) -> dict[str, dict[str, str]]:
        """Resolve all blocks from blockstates directory.

        Returns:
            Dict mapping block_name → {face_dir: texture_name}
        """
        results = {}

        if self._folder:
            bs_dir = os.path.join(self._folder, "blockstates")
            if os.path.isdir(bs_dir):
                for fname in os.listdir(bs_dir):
                    if fname.endswith(".json"):
                        block_name = fname[:-5]
                        face_textures = self.get_face_textures(block_name)
                        if face_textures:
                            results[block_name] = face_textures
        elif self._zip:
            prefix = "assets/minecraft/blockstates/"
            for name in self._zip.namelist():
                if name.startswith(prefix) and name.endswith(".json"):
                    block_name = name[len(prefix):-5]
                    if "/" not in block_name:
                        face_textures = self.get_face_textures(block_name)
                        if face_textures:
                            results[block_name] = face_textures

        return results

    def generate_face_texture_map(self) -> dict[str, dict[str, str]]:
        """Generate a FACE_TEXTURE_MAP-compatible dict for blocks with non-uniform textures.

        Only includes blocks where at least one face differs from the block name.

        Returns:
            Dict mapping block_name → {face_dir: texture_name}, only for blocks
            where some faces use different textures.
        """
        all_textures = self.get_all_block_textures()
        face_map = {}

        for block_name, faces in all_textures.items():
            # Check if all faces are the same as block name
            values = set(faces.values())
            if len(values) == 1 and block_name in values:
                continue  # All faces match block name, no entry needed
            face_map[block_name] = faces

        return face_map


def generate_mapping_script(template_path: str):
    """Run as a script to generate the static BLOCK_FACE_TEXTURES mapping."""
    resolver = ModelResolver(template_path)
    face_map = resolver.generate_face_texture_map()
    resolver.close()

    print("# Auto-generated block face texture mapping")
    print("# Maps block_name -> {face_dir: texture_name}")
    print("# Only includes blocks where face textures differ from block name")
    print(f"# Generated from: {template_path}")
    print()
    print("BLOCK_FACE_TEXTURES = {")
    for block_name in sorted(face_map.keys()):
        faces = face_map[block_name]
        # Check if all faces are the same (just different from block name)
        values = set(faces.values())
        if len(values) == 1:
            tex = list(values)[0]
            print(f'    "{block_name}": {{')
            print(f'        "+y": "{tex}", "-y": "{tex}",')
            print(f'        "+x": "{tex}", "-x": "{tex}",')
            print(f'        "+z": "{tex}", "-z": "{tex}",')
            print(f'    }},')
        else:
            print(f'    "{block_name}": {{')
            for fd in ["+y", "-y", "+x", "-x", "+z", "-z"]:
                if fd in faces:
                    print(f'        "{fd}": "{faces[fd]}",')
            print(f'    }},')
    print("}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python model_resolver.py <template_path>")
        sys.exit(1)
    generate_mapping_script(sys.argv[1])
