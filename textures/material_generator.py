"""CS2 material (.vmat) generator with addon export support."""

import os
import math
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
from textures.pack_reader import TexturePackReader
from config.defaults import DEFAULT_MATERIAL
from config.blocks import (get_texture_name, get_texture_name_for_face, get_color_tint,
                           is_self_illuminated, is_translucent, FACE_TEXTURE_MAP,
                           TEXTURE_REMAP, get_block_base_name, TINT_MASK_OVERLAYS,
                           is_forced_translucent, TRANSPARENT_BLOCKS, get_glow_power)

# Texture name patterns that need F_RENDER_BACKFACES (visible from both sides).
# Primarily plants, leaves, and thin geometry rendered as quads.
_BACKFACE_PATTERNS = frozenset({
    "vine", "vines", "short_grass", "tall_grass", "fern", "bush", "sapling",
    "tulip", "dandelion", "poppy", "orchid", "allium", "bluet", "daisy",
    "cornflower", "lily_of_the_valley", "rose", "lily_pad", "cobweb",
    "sugar_cane", "kelp", "seagrass", "dead_bush", "bamboo",
    "azalea", "spore_blossom", "dripleaf", "hanging_roots",
    "glow_lichen", "sculk_vein", "torch", "lantern",
    # Crops
    "wheat", "carrots", "potatoes", "beetroots", "nether_wart",
    "sweet_berry", "cocoa", "melon_stem", "pumpkin_stem", "crop",
    # Tall flowers missing from substring matches
    "peony", "pitcher",
})


def _needs_render_backfaces(block_name: str) -> bool:
    """Return True if this texture needs backface rendering."""
    for pat in _BACKFACE_PATTERNS:
        if pat in block_name:
            return True
    return False


def _generate_vmat_content(texture_path: str, *,
                           translucent: bool = False,
                           alpha_test: bool = False,
                           render_backfaces: bool = False,
                           translucency_path: str = "",
                           self_illum: bool = False,
                           self_illum_mask_path: str = "",
                           glow_power: float = 0.0,
                           color_tint: str | None = None,
                           tint_mask_path: str = "",
                           animated: bool = False,
                           animation_grid: tuple[int, int] | None = None,
                           animation_cells: int = 0,
                           animation_frametime: float = 0.1) -> str:
    """Generate .vmat file content based on block properties."""
    lines = ["// THIS FILE IS AUTO-GENERATED", "", "Layer0", "{"]

    if translucent or alpha_test or self_illum or animated or tint_mask_path or render_backfaces:
        # Complex shader
        lines.append('\tshader "csgo_complex.vfx"')
        lines.append("")
        if render_backfaces:
            lines.append("\t//---- Rendering ----")
            lines.append("\tF_RENDER_BACKFACES 1")
            lines.append("")
        if animated:
            lines.append("\t//---- Animation ----")
            lines.append("\tF_TEXTURE_ANIMATION 1")
            lines.append("")
        if self_illum:
            lines.append("\t//---- PBR ----")
            lines.append("\tF_SELF_ILLUM 1")
            lines.append("")
        if tint_mask_path:
            lines.append("\t//---- Tint Mask ----")
            lines.append("\tF_TINT_MASK 2")
            lines.append("")
        if translucent:
            lines.append("\t//---- Translucent ----")
            lines.append("\tF_TRANSLUCENT 1")
            lines.append("")
        elif alpha_test:
            lines.append("\t//---- Alpha Test ----")
            lines.append("\tF_ALPHA_TEST 1")
            lines.append("")
    else:
        # Simple shader
        lines.append('\tshader "csgo_simple.vfx"')
        lines.append("")

    # Ambient Occlusion
    lines.append("\t//---- Ambient Occlusion ----")
    lines.append('\tTextureAmbientOcclusion "materials/default/default_ao.tga"')
    lines.append("")

    # Color
    lines.append("\t//---- Color ----")
    lines.append('\tg_flModelTintAmount "1.000"')
    lines.append('\tg_flTexCoordRotation "0.000"')
    lines.append('\tg_nScaleTexCoordUByModelScaleAxis "0" // None')
    lines.append('\tg_nScaleTexCoordVByModelScaleAxis "0" // None')
    tint = color_tint if color_tint else "[1.000000 1.000000 1.000000 0.000000]"
    lines.append(f'\tg_vColorTint "{tint}"')
    lines.append('\tg_vTexCoordCenter "[0.500 0.500]"')
    lines.append('\tg_vTexCoordOffset "[0.000 0.000]"')
    lines.append('\tg_vTexCoordScale "[1.000 1.000]"')
    lines.append('\tg_vTexCoordScrollSpeed "[0.000 0.000]"')
    lines.append(f'\tTextureColor "{texture_path}"')
    lines.append("")

    # Fog
    lines.append("\t//---- Fog ----")
    lines.append('\tg_bFogEnabled "1"')
    lines.append("")

    # Lighting
    lines.append("\t//---- Lighting ----")
    lines.append('\tg_flMetalness "0.000"')
    lines.append('\tTextureRoughness "materials/default/default_rough.tga"')
    lines.append("")

    # Normal Map
    lines.append("\t//---- Normal Map ----")
    lines.append('\tTextureNormal "materials/default/default_normal.tga"')
    lines.append("")

    # Self Illum section (only for complex shader with self illum)
    if self_illum:
        lines.append("\t//---- Self Illum ----")
        lines.append('\tg_flSelfIllumAlbedoFactor "1.000"')
        if glow_power > 0:
            lines.append(f'\tg_flSelfIllumBrightness "{glow_power:.3f}"')
        else:
            lines.append('\tg_flSelfIllumBrightness "0.000"')
        lines.append('\tg_flSelfIllumScale "1.000"')
        lines.append('\tg_vSelfIllumScrollSpeed "[0.000 0.000]"')
        if glow_power > 0:
            lines.append('\tTextureSelfIllumMask "[1.000000 1.000000 1.000000 0.000000]"')
        elif self_illum_mask_path:
            lines.append(f'\tTextureSelfIllumMask "{self_illum_mask_path}"')
        else:
            lines.append('\tg_vSelfIllumTint "[1.000000 1.000000 1.000000 0.000000]"')
            lines.append('\tTextureSelfIllumMask "[1.000000 1.000000 1.000000 0.000000]"')
        lines.append("")

    # Texture Address Mode
    lines.append("\t//---- Texture Address Mode ----")
    lines.append('\tg_nTextureAddressModeU "0" // Wrap')
    lines.append('\tg_nTextureAddressModeV "0" // Wrap')

    # Tint Mask section (complex shader with separate tint mask texture)
    if tint_mask_path:
        lines.append("")
        lines.append("\t//---- Tint Mask ----")
        lines.append(f'\tTextureTintMask "{tint_mask_path}"')

    # Texture Animation section
    if animated and animation_grid:
        lines.append("")
        lines.append("\t//---- Texture Animation ----")
        lines.append('\tg_flAnimationFrame "0.000"')
        lines.append('\tg_flAnimationTimeOffset "0.000"')
        lines.append(f'\tg_flAnimationTimePerFrame "{animation_frametime:.3f}"')
        lines.append(f'\tg_nNumAnimationCells "{animation_cells}"')
        lines.append(f'\tg_vAnimationGrid "[{animation_grid[0]} {animation_grid[1]}]"')

    # Translucent / Alpha Test section
    if translucent:
        lines.append("")
        lines.append("\t//---- Translucent ----")
        lines.append('\tg_flOpacityScale "1.000"')
        lines.append(f'\tTextureTranslucency "{translucency_path}"')
    elif alpha_test:
        lines.append("")
        lines.append("\t//---- Alpha Test ----")
        lines.append('\tg_flAlphaTestReference "0.500"')
        lines.append(f'\tTextureTranslucency "{translucency_path}"')

    lines.append("}")
    return "\n".join(lines) + "\n"


def _generate_pbr_vmat_content(texture_path: str, *,
                                roughness_path: str = "",
                                metalness_path: str = "",
                                metalness_val: float = 0.0,
                                normal_path: str = "",
                                self_illum: bool = False,
                                self_illum_mask_path: str = "",
                                glow_power: float = 0.0,
                                translucent: bool = False,
                                alpha_test: bool = False,
                                render_backfaces: bool = False,
                                translucency_path: str = "",
                                color_tint: str | None = None,
                                tint_mask_path: str = "",
                                animated: bool = False,
                                animation_grid: tuple[int, int] | None = None,
                                animation_cells: int = 0,
                                animation_frametime: float = 0.1) -> str:
    """Generate a PBR .vmat for Bedrock RTX packs (metalness, roughness, emissive, normal)."""
    lines = ["// THIS FILE IS AUTO-GENERATED (PBR from Bedrock RTX)", "", "Layer0", "{"]

    # Always use complex shader for PBR
    lines.append('\tshader "csgo_complex.vfx"')
    lines.append("")

    lines.append("\t//---- PBR ----")
    if metalness_path:
        lines.append("\tF_METALNESS_TEXTURE 1")
    lines.append("")

    if render_backfaces:
        lines.append("\t//---- Rendering ----")
        lines.append("\tF_RENDER_BACKFACES 1")
        lines.append("")
    if animated:
        lines.append("\t//---- Animation ----")
        lines.append("\tF_TEXTURE_ANIMATION 1")
        lines.append("")
    if self_illum:
        lines.append("\t//---- Self Illumination ----")
        lines.append("\tF_SELF_ILLUM 1")
        lines.append("")
    if tint_mask_path:
        lines.append("\t//---- Tint Mask ----")
        lines.append("\tF_TINT_MASK 2")
        lines.append("")
    if translucent:
        lines.append("\t//---- Translucent ----")
        lines.append("\tF_TRANSLUCENT 1")
        lines.append("")
    elif alpha_test:
        lines.append("\t//---- Alpha Test ----")
        lines.append("\tF_ALPHA_TEST 1")
        lines.append("")

    # AO
    lines.append("\t//---- Ambient Occlusion ----")
    lines.append('\tTextureAmbientOcclusion "materials/default/default_ao.tga"')
    lines.append("")

    # Color
    lines.append("\t//---- Color ----")
    lines.append('\tg_flModelTintAmount "1.000"')
    lines.append('\tg_flTexCoordRotation "0.000"')
    lines.append('\tg_nScaleTexCoordUByModelScaleAxis "0" // None')
    lines.append('\tg_nScaleTexCoordVByModelScaleAxis "0" // None')
    tint = color_tint if color_tint else "[1.000000 1.000000 1.000000 0.000000]"
    lines.append(f'\tg_vColorTint "{tint}"')
    lines.append('\tg_vTexCoordCenter "[0.500 0.500]"')
    lines.append('\tg_vTexCoordOffset "[0.000 0.000]"')
    lines.append('\tg_vTexCoordScale "[1.000 1.000]"')
    lines.append('\tg_vTexCoordScrollSpeed "[0.000 0.000]"')
    lines.append(f'\tTextureColor "{texture_path}"')
    lines.append("")

    # Fog
    lines.append("\t//---- Fog ----")
    lines.append('\tg_bFogEnabled "1"')
    lines.append("")

    # Lighting / Metalness + Roughness
    lines.append("\t//---- Lighting ----")
    if metalness_path:
        lines.append(f'\tTextureMetalness "{metalness_path}"')
    else:
        lines.append(f'\tg_flMetalness "{metalness_val:.3f}"')
    if roughness_path:
        lines.append(f'\tTextureRoughness "{roughness_path}"')
    else:
        lines.append('\tTextureRoughness "materials/default/default_rough.tga"')
    lines.append("")

    # Normal map
    lines.append("\t//---- Normal Map ----")
    if normal_path:
        lines.append(f'\tTextureNormal "{normal_path}"')
    else:
        lines.append('\tTextureNormal "materials/default/default_normal.tga"')
    lines.append("")

    # Self-illumination (emissive) — always write section
    lines.append("\t//---- Self Illum ----")
    lines.append('\tg_flSelfIllumAlbedoFactor "1.000"')
    if glow_power > 0:
        lines.append(f'\tg_flSelfIllumBrightness "{glow_power:.3f}"')
    elif self_illum:
        lines.append('\tg_flSelfIllumBrightness "1.500"')
    else:
        lines.append('\tg_flSelfIllumBrightness "0.000"')
    lines.append('\tg_flSelfIllumScale "1.000"')
    lines.append('\tg_vSelfIllumScrollSpeed "[0.000 0.000]"')
    if glow_power > 0:
        lines.append('\tTextureSelfIllumMask "[1.000000 1.000000 1.000000 0.000000]"')
    elif self_illum and self_illum_mask_path:
        lines.append(f'\tTextureSelfIllumMask "{self_illum_mask_path}"')
    else:
        lines.append('\tTextureSelfIllumMask "[1.000000 1.000000 1.000000 0.000000]"')
        lines.append('\tg_vSelfIllumTint "[1.000000 1.000000 1.000000 0.000000]"')
    lines.append("")

    # Texture address mode
    lines.append("\t//---- Texture Address Mode ----")
    lines.append('\tg_nTextureAddressModeU "0" // Wrap')
    lines.append('\tg_nTextureAddressModeV "0" // Wrap')

    # Tint Mask section
    if tint_mask_path:
        lines.append("")
        lines.append("\t//---- Tint Mask ----")
        lines.append(f'\tTextureTintMask "{tint_mask_path}"')

    # Animation
    if animated and animation_grid:
        lines.append("")
        lines.append("\t//---- Texture Animation ----")
        lines.append('\tg_flAnimationFrame "0.000"')
        lines.append('\tg_flAnimationTimeOffset "0.000"')
        lines.append(f'\tg_flAnimationTimePerFrame "{animation_frametime:.3f}"')
        lines.append(f'\tg_nNumAnimationCells "{animation_cells}"')
        lines.append(f'\tg_vAnimationGrid "[{animation_grid[0]} {animation_grid[1]}]"')

    # Translucency / Alpha Test
    if translucent:
        lines.append("")
        lines.append("\t//---- Translucent ----")
        lines.append('\tg_flOpacityScale "1.000"')
        lines.append(f'\tTextureTranslucency "{translucency_path}"')
    elif alpha_test:
        lines.append("")
        lines.append("\t//---- Alpha Test ----")
        lines.append('\tg_flAlphaTestReference "0.500"')
        lines.append(f'\tTextureTranslucency "{translucency_path}"')

    lines.append("}")
    return "\n".join(lines) + "\n"


def _is_binary_alpha(img: Image.Image) -> bool:
    """Return True if every pixel's alpha is either 0 or 255 (no partial translucency)."""
    if img.mode != "RGBA":
        return False
    alpha = np.array(img.split()[3], dtype=np.uint8)
    return bool(np.all((alpha == 0) | (alpha == 255)))


def _heightmap_to_normal(heightmap: Image.Image, strength: float = 1.0) -> Image.Image:
    """Convert a grayscale heightmap to a tangent-space normal map."""
    hm = np.array(heightmap.convert("L"), dtype=np.float32) / 255.0
    # Sobel-like derivatives
    dy = np.zeros_like(hm)
    dx = np.zeros_like(hm)
    dy[1:-1, :] = (hm[2:, :] - hm[:-2, :]) * strength
    dx[:, 1:-1] = (hm[:, 2:] - hm[:, :-2]) * strength
    # Normal vector (tangent space: X=right, Y=down for DirectX/Source2, Z=out)
    nx = -dx
    ny = dy
    nz = np.ones_like(hm)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    length[length == 0] = 1.0
    nx /= length
    ny /= length
    nz /= length
    # Pack to 0-255
    r = ((nx * 0.5 + 0.5) * 255).clip(0, 255).astype(np.uint8)
    g = ((ny * 0.5 + 0.5) * 255).clip(0, 255).astype(np.uint8)
    b = ((nz * 0.5 + 0.5) * 255).clip(0, 255).astype(np.uint8)
    return Image.merge("RGB", [Image.fromarray(r), Image.fromarray(g),
                                Image.fromarray(b)])


def _filter_black_frames(img: Image.Image, frame_count: int) -> tuple[Image.Image, int]:
    """Remove trailing near-black frames from animated textures.

    Some textures (magma, sea lanterns) have fully-black padding frames at the
    end of the strip.  Detect and strip them so the animation loops cleanly.

    Returns (cropped_image, new_frame_count).
    """
    if frame_count <= 1:
        return img, frame_count
    frame_w = img.width
    frame_h = frame_w  # square frames

    # Walk backwards, dropping frames that are nearly black
    keep = frame_count
    for i in range(frame_count - 1, 0, -1):
        frame = img.crop((0, i * frame_h, frame_w, (i + 1) * frame_h))
        arr = np.array(frame.convert("RGB"), dtype=np.float32)
        if arr.mean() < 3.0:          # nearly black
            keep = i
        else:
            break

    if keep == frame_count:
        return img, frame_count    # nothing to strip

    cropped = img.crop((0, 0, frame_w, keep * frame_h))
    return cropped, keep


def _make_grid_atlas(img: Image.Image, frame_count: int, target_size: int) -> tuple[Image.Image, int, int]:
    """Convert a vertical strip of frames into a grid atlas for CS2 animations.

    Uses a fixed column count (4, or 8 for >= 64 frames) matching the
    layout used by MinePBRtoCS.  Each frame is resized to target_size x
    target_size.  Rows are rounded up to the next power of 2.
    Empty cells are filled with a copy of the first frame.

    Returns (atlas_image, grid_cols, grid_rows).
    """
    frame_w = img.width
    frame_h = frame_w  # Each frame is square

    # Column count: 4 normally, 8 for large animations
    cols = 8 if frame_count >= 64 else 4

    # Rows = ceil(frame_count / cols), rounded up to next power of 2
    raw_rows = math.ceil(frame_count / cols)
    rows = 1
    while rows < raw_rows:
        rows *= 2

    cell_size = target_size
    atlas_w = cols * cell_size
    atlas_h = rows * cell_size

    atlas = Image.new("RGBA", (atlas_w, atlas_h), (0, 0, 0, 0))

    # Pre-resize the first frame for use as padding
    first_frame = img.crop((0, 0, frame_w, frame_h)).resize((cell_size, cell_size), Image.NEAREST)

    for i in range(cols * rows):
        c = i % cols
        r = i // cols
        if i < frame_count:
            frame = img.crop((0, i * frame_h, frame_w, (i + 1) * frame_h))
            frame = frame.resize((cell_size, cell_size), Image.NEAREST)
        else:
            frame = first_frame
        atlas.paste(frame, (c * cell_size, r * cell_size))

    return atlas, cols, rows


class MaterialGenerator:
    """Generates CS2 .vmat material files and exports textures to addon folder."""

    def __init__(self, texture_reader: TexturePackReader = None):
        self.texture_reader = texture_reader
        self._material_map = {}   # "minecraft:block_name" -> "materials/map_name/block.vmat"
        self._vmat_paths = []     # absolute paths of generated .vmat files

    def export_to_addon(self, addon_folder: str, map_name: str,
                        used_blocks: set[str] = None,
                        texture_size: int = 512,
                        progress_callback=None) -> dict[str, str]:
        """Export textures and generate .vmat files into addon folder structure.

        Only exports textures for blocks present in used_blocks.

        Args:
            addon_folder: Root addon folder (e.g., csgo_addon)
            map_name: Map name used as subfolder for materials
            used_blocks: Set of block names (e.g. "minecraft:stone") to export.
                         If None, exports all textures.
            texture_size: Target texture size (power of 2)
            progress_callback: Optional callable(current, total)

        Returns:
            Dict mapping "minecraft:block_name" -> material path for vmap references
        """
        if not self.texture_reader:
            return {}

        # Filter to only textures used by the structure (including face-specific variants)
        if used_blocks is not None:
            needed = set()
            for b in used_blocks:
                base = get_block_base_name(b)
                short = base[len("minecraft:"):] if base.startswith("minecraft:") else base
                if short in FACE_TEXTURE_MAP:
                    for tex in FACE_TEXTURE_MAP[short].values():
                        needed.add(tex)
                else:
                    needed.add(get_texture_name(b))
                    # Also include the raw name so packs with the original
                    # texture (e.g. kelp_plant) still get their own material.
                    needed.add(short)
            # Always export water_flow alongside water_still so func_water
            # entities can reference the flowing animation.
            if "water_still" in needed:
                needed.add("water_flow")
            texture_names = [n for n in self.texture_reader.texture_names
                             if n in needed and self.texture_reader.has_texture(n)]
        else:
            texture_names = self.texture_reader.texture_names

        mat_dir = os.path.join(addon_folder, "materials", map_name)
        os.makedirs(mat_dir, exist_ok=True)

        material_prefix = f"materials/{map_name}/"
        total = len(texture_names)

        def _export_one(block_name: str) -> tuple[str, str, str]:
            """Export a single block's texture + vmat. Returns (texture_name, mat_ref, vmat_path)."""
            img = self.texture_reader.get_texture(block_name)
            if img is None:
                return None

            block_key = f"minecraft:{block_name}"
            is_anim = self.texture_reader.is_animated(block_name)
            is_trans = is_translucent(block_key) or is_forced_translucent(block_name)
            is_illum = is_self_illuminated(block_key)
            glow = get_glow_power(block_name)
            if glow > 0:
                is_illum = True
            tint = get_color_tint(block_name)
            use_pbr = (self.texture_reader.is_bedrock
                       and self.texture_reader.has_mer(block_name))
            backfaces = _needs_render_backfaces(block_name)

            # Also check actual image alpha for translucency
            if not is_trans and img.mode == "RGBA":
                alpha = img.split()[3]
                if alpha.getextrema()[0] < 255:
                    is_trans = True

            # Prefer alpha_test for binary-alpha textures (leaves, flowers)
            # over blended translucency (glass, water, ice).  Alpha test is
            # cheaper and avoids depth-sorting artefacts.
            use_alpha_test = False
            if is_trans and not is_anim:
                check_img = img
                if is_anim:
                    full = self.texture_reader.get_full_image(block_name)
                    if full is not None:
                        check_img = full
                if _is_binary_alpha(check_img):
                    use_alpha_test = True
                    is_trans = False  # mutually exclusive

            trans_ref = ""
            illum_ref = ""
            tint_mask_ref = ""
            rough_ref = ""
            normal_ref = ""
            metalness_ref = ""
            metalness_val = 0.0

            # --- PBR texture export (Bedrock only) ---
            if use_pbr:
                mer_img = self.texture_reader.get_mer_texture(block_name)
                if mer_img is not None:
                    mer_rgba = mer_img.convert("RGBA")
                    mer_resized = mer_rgba.resize(
                        (texture_size, texture_size), Image.NEAREST)
                    r_ch, g_ch, b_ch, _ = mer_resized.split()

                    # Metalness (R channel): save as texture
                    r_arr = np.array(r_ch, dtype=np.float32)
                    if r_arr.max() > 1:
                        metal_fn = f"{block_name}_metal.png"
                        r_ch.save(os.path.join(mat_dir, metal_fn),
                                  format="PNG")
                        metalness_ref = f"{material_prefix}{metal_fn}"
                    metalness_val = float(r_arr.mean() / 255.0)

                    # Emissive (G channel): if non-trivial, use as self-illum
                    # Skip emissive for glass blocks (MER green channel is not emissive)
                    g_arr = np.array(g_ch, dtype=np.float32)
                    if g_arr.max() > 10 and "glass" not in block_name:
                        is_illum = True
                        emissive_fn = f"{block_name}_emissive.png"
                        g_ch.save(os.path.join(mat_dir, emissive_fn),
                                  format="PNG")
                        illum_ref = f"{material_prefix}{emissive_fn}"

                    # Roughness (B channel): save as texture
                    rough_fn = f"{block_name}_rough.png"
                    b_ch.save(os.path.join(mat_dir, rough_fn), format="PNG")
                    rough_ref = f"{material_prefix}{rough_fn}"

                # Normal map (direct or from heightmap)
                nm_img = self.texture_reader.get_normal_map(block_name)
                if nm_img is not None:
                    # Crop to first frame if animated strip
                    if nm_img.height > nm_img.width:
                        nm_img = nm_img.crop(
                            (0, 0, nm_img.width, nm_img.width))
                    normal_resized = nm_img.resize(
                        (texture_size, texture_size), Image.NEAREST)
                    norm_fn = f"{block_name}_normal.png"
                    normal_resized.save(os.path.join(mat_dir, norm_fn),
                                        format="PNG")
                    normal_ref = f"{material_prefix}{norm_fn}"
                else:
                    hm_img = self.texture_reader.get_heightmap(block_name)
                    if hm_img is not None:
                        normal_img = _heightmap_to_normal(hm_img, strength=2.0)
                        normal_resized = normal_img.resize(
                            (texture_size, texture_size), Image.NEAREST)
                        norm_fn = f"{block_name}_normal.png"
                        normal_resized.save(os.path.join(mat_dir, norm_fn),
                                            format="PNG")
                        normal_ref = f"{material_prefix}{norm_fn}"

            # Generate tint mask from overlay texture if available
            if block_name in TINT_MASK_OVERLAYS:
                overlay_name = TINT_MASK_OVERLAYS[block_name]
                overlay_img = self.texture_reader.get_texture(overlay_name)
                if overlay_img is not None:
                    if overlay_img.mode != "RGBA":
                        overlay_img = overlay_img.convert("RGBA")
                    overlay_resized = overlay_img.resize(
                        (texture_size, texture_size), Image.NEAREST
                    )
                    alpha = overlay_resized.split()[3]
                    mask_filename = f"{block_name}_tintmask.png"
                    mask_path = os.path.join(mat_dir, mask_filename)
                    alpha.save(mask_path, format="PNG")
                    tint_mask_ref = f"{material_prefix}{mask_filename}"

            if is_anim:
                full_img = self.texture_reader.get_full_image(block_name)
                anim_info = self.texture_reader.get_animation_info(block_name)
                frame_count = anim_info["frame_count"]
                frametime = anim_info["frametime"]

                full_img, frame_count = _filter_black_frames(full_img, frame_count)
                atlas, grid_cols, grid_rows = _make_grid_atlas(full_img, frame_count, texture_size)

                png_filename = f"{block_name}_color.png"
                png_path = os.path.join(mat_dir, png_filename)
                atlas.save(png_path, format="PNG")

                texture_ref = f"{material_prefix}{png_filename}"

                if is_trans or use_alpha_test:
                    trans_ref = self._save_alpha_mask(atlas, block_name, "_trans", mat_dir, material_prefix)
                if is_illum and not illum_ref:
                    illum_ref = self._save_alpha_mask(atlas, block_name, "_illum", mat_dir, material_prefix)

                if use_pbr:
                    vmat_content = _generate_pbr_vmat_content(
                        texture_ref,
                        roughness_path=rough_ref,
                        metalness_path=metalness_ref,
                        metalness_val=metalness_val,
                        normal_path=normal_ref,
                        self_illum=is_illum,
                        self_illum_mask_path=illum_ref,
                        glow_power=glow,
                        translucent=is_trans,
                        alpha_test=use_alpha_test,
                        render_backfaces=backfaces,
                        translucency_path=trans_ref,
                        color_tint=tint,
                        tint_mask_path=tint_mask_ref,
                        animated=True,
                        animation_grid=(grid_cols, grid_rows),
                        animation_cells=frame_count,
                        animation_frametime=frametime,
                    )
                else:
                    vmat_content = _generate_vmat_content(
                        texture_ref,
                        translucent=is_trans,
                        alpha_test=use_alpha_test,
                        render_backfaces=backfaces,
                        translucency_path=trans_ref,
                        self_illum=is_illum,
                        self_illum_mask_path=illum_ref,
                        glow_power=glow,
                        color_tint=tint,
                        tint_mask_path=tint_mask_ref,
                        animated=True,
                        animation_grid=(grid_cols, grid_rows),
                        animation_cells=frame_count,
                        animation_frametime=frametime,
                    )
            else:
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                resized = img.resize((texture_size, texture_size), Image.NEAREST)

                png_filename = f"{block_name}_color.png"
                png_path = os.path.join(mat_dir, png_filename)
                resized.save(png_path, format="PNG")

                texture_ref = f"{material_prefix}{png_filename}"

                if is_trans or use_alpha_test:
                    trans_ref = self._save_alpha_mask(resized, block_name, "_trans", mat_dir, material_prefix)
                if is_illum and not illum_ref:
                    illum_ref = self._save_alpha_mask(resized, block_name, "_illum", mat_dir, material_prefix)

                if use_pbr:
                    vmat_content = _generate_pbr_vmat_content(
                        texture_ref,
                        roughness_path=rough_ref,
                        metalness_path=metalness_ref,
                        metalness_val=metalness_val,
                        normal_path=normal_ref,
                        self_illum=is_illum,
                        self_illum_mask_path=illum_ref,
                        glow_power=glow,
                        translucent=is_trans,
                        alpha_test=use_alpha_test,
                        render_backfaces=backfaces,
                        translucency_path=trans_ref,
                        color_tint=tint,
                        tint_mask_path=tint_mask_ref,
                    )
                else:
                    vmat_content = _generate_vmat_content(
                        texture_ref,
                        translucent=is_trans,
                        alpha_test=use_alpha_test,
                        render_backfaces=backfaces,
                        translucency_path=trans_ref,
                        self_illum=is_illum,
                        self_illum_mask_path=illum_ref,
                        glow_power=glow,
                        color_tint=tint,
                        tint_mask_path=tint_mask_ref,
                    )

            vmat_filename = f"{block_name}.vmat"
            vmat_path = os.path.join(mat_dir, vmat_filename)
            with open(vmat_path, "w", encoding="utf-8") as f:
                f.write(vmat_content)

            mat_ref = f"{material_prefix}{vmat_filename}"
            return block_name, mat_ref, vmat_path

        workers = min(total, os.cpu_count() or 4, 8)
        completed = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_export_one, n): n for n in texture_names}
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    tex_name, mat_ref, vmat_path = result
                    self._material_map[tex_name] = mat_ref
                    self._vmat_paths.append(vmat_path)
                completed += 1
                if progress_callback:
                    progress_callback(completed, total)

        return self._material_map

    @staticmethod
    def _save_alpha_mask(img: Image.Image, block_name: str, suffix: str,
                         mat_dir: str, material_prefix: str) -> str:
        """Extract alpha channel from image and save as a grayscale mask PNG.
        Returns the material-relative path for the .vmat reference."""
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        alpha = img.split()[3]  # A channel as grayscale
        mask_filename = f"{block_name}{suffix}.png"
        mask_path = os.path.join(mat_dir, mask_filename)
        alpha.save(mask_path, format="PNG")
        return f"{material_prefix}{mask_filename}"

    def export_model_textures(self, addon_folder: str, map_name: str,
                              texture_names: set[str], texture_size: int = 512):
        """Export additional textures needed by model blocks that weren't in the initial export.

        Args:
            addon_folder: Root addon folder
            map_name: Map name subfolder
            texture_names: Set of texture names to export (e.g. {"rail_corner"})
            texture_size: Target texture size
        """
        if not self.texture_reader:
            return
        mat_dir = os.path.join(addon_folder, "materials", map_name)
        os.makedirs(mat_dir, exist_ok=True)
        material_prefix = f"materials/{map_name}/"

        for block_name in texture_names:
            if block_name in self._material_map:
                continue
            img = self.texture_reader.get_texture(block_name)
            if img is None:
                continue

            block_key = f"minecraft:{block_name}"
            is_anim = self.texture_reader.is_animated(block_name)
            is_illum = is_self_illuminated(block_key)
            glow = get_glow_power(block_name)
            if glow > 0:
                is_illum = True
            tint = get_color_tint(block_name)
            use_pbr = (self.texture_reader.is_bedrock
                       and self.texture_reader.has_mer(block_name))
            backfaces = _needs_render_backfaces(block_name)

            rough_ref = ""
            normal_ref = ""
            metalness_ref = ""
            metalness_val = 0.0
            illum_ref = ""

            # --- PBR texture export (Bedrock only) ---
            if use_pbr:
                mer_img = self.texture_reader.get_mer_texture(block_name)
                if mer_img is not None:
                    mer_rgba = mer_img.convert("RGBA")
                    # Crop to first frame if animated strip
                    if mer_rgba.height > mer_rgba.width:
                        mer_rgba = mer_rgba.crop(
                            (0, 0, mer_rgba.width, mer_rgba.width))
                    mer_resized = mer_rgba.resize(
                        (texture_size, texture_size), Image.NEAREST)
                    r_ch, g_ch, b_ch, _ = mer_resized.split()

                    # Metalness (R channel): save as texture
                    r_arr = np.array(r_ch, dtype=np.float32)
                    if r_arr.max() > 1:
                        metal_fn = f"{block_name}_metal.png"
                        r_ch.save(os.path.join(mat_dir, metal_fn),
                                  format="PNG")
                        metalness_ref = f"{material_prefix}{metal_fn}"
                    metalness_val = float(r_arr.mean() / 255.0)

                    g_arr = np.array(g_ch, dtype=np.float32)
                    if g_arr.max() > 10 and "glass" not in block_name:
                        is_illum = True
                        emissive_fn = f"{block_name}_emissive.png"
                        g_ch.save(os.path.join(mat_dir, emissive_fn),
                                  format="PNG")
                        illum_ref = f"{material_prefix}{emissive_fn}"

                    rough_fn = f"{block_name}_rough.png"
                    b_ch.save(os.path.join(mat_dir, rough_fn), format="PNG")
                    rough_ref = f"{material_prefix}{rough_fn}"

                nm_img = self.texture_reader.get_normal_map(block_name)
                if nm_img is not None:
                    # Crop to first frame if animated strip
                    if nm_img.height > nm_img.width:
                        nm_img = nm_img.crop(
                            (0, 0, nm_img.width, nm_img.width))
                    normal_resized = nm_img.resize(
                        (texture_size, texture_size), Image.NEAREST)
                    norm_fn = f"{block_name}_normal.png"
                    normal_resized.save(os.path.join(mat_dir, norm_fn),
                                        format="PNG")
                    normal_ref = f"{material_prefix}{norm_fn}"
                else:
                    hm_img = self.texture_reader.get_heightmap(block_name)
                    if hm_img is not None:
                        normal_img = _heightmap_to_normal(hm_img, strength=2.0)
                        normal_resized = normal_img.resize(
                            (texture_size, texture_size), Image.NEAREST)
                        norm_fn = f"{block_name}_normal.png"
                        normal_resized.save(os.path.join(mat_dir, norm_fn),
                                            format="PNG")
                        normal_ref = f"{material_prefix}{norm_fn}"

            if is_anim:
                full_img = self.texture_reader.get_full_image(block_name)
                anim_info = self.texture_reader.get_animation_info(block_name)
                frame_count = anim_info["frame_count"]
                frametime = anim_info["frametime"]

                full_img, frame_count = _filter_black_frames(full_img, frame_count)
                atlas, grid_cols, grid_rows = _make_grid_atlas(full_img, frame_count, texture_size)

                png_filename = f"{block_name}_color.png"
                png_path = os.path.join(mat_dir, png_filename)
                atlas.save(png_path, format="PNG")
                texture_ref = f"{material_prefix}{png_filename}"

                is_trans = is_forced_translucent(block_name)
                if not is_trans and atlas.mode == "RGBA":
                    alpha = atlas.split()[3]
                    if alpha.getextrema()[0] < 255:
                        is_trans = True

                use_alpha_test = False
                if is_trans and not is_anim and _is_binary_alpha(atlas):
                    use_alpha_test = True
                    is_trans = False

                trans_ref = ""
                if is_trans or use_alpha_test:
                    trans_ref = self._save_alpha_mask(atlas, block_name, "_trans", mat_dir, material_prefix)
                if is_illum and not illum_ref:
                    illum_ref = self._save_alpha_mask(atlas, block_name, "_illum", mat_dir, material_prefix)

                if use_pbr:
                    vmat_content = _generate_pbr_vmat_content(
                        texture_ref,
                        roughness_path=rough_ref,
                        metalness_path=metalness_ref,
                        metalness_val=metalness_val,
                        normal_path=normal_ref,
                        self_illum=is_illum,
                        self_illum_mask_path=illum_ref,
                        glow_power=glow,
                        translucent=is_trans,
                        alpha_test=use_alpha_test,
                        translucency_path=trans_ref,
                        color_tint=tint,
                        animated=True,
                        animation_grid=(grid_cols, grid_rows),
                        animation_cells=frame_count,
                        animation_frametime=frametime,
                        render_backfaces=backfaces,
                    )
                else:
                    vmat_content = _generate_vmat_content(
                        texture_ref,
                        translucent=is_trans,
                        alpha_test=use_alpha_test,
                        translucency_path=trans_ref,
                        self_illum=is_illum,
                        self_illum_mask_path=illum_ref,
                        glow_power=glow,
                        color_tint=tint,
                        animated=True,
                        animation_grid=(grid_cols, grid_rows),
                        animation_cells=frame_count,
                        animation_frametime=frametime,
                        render_backfaces=backfaces,
                    )
            else:
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                resized = img.resize((texture_size, texture_size), Image.NEAREST)

                is_trans = is_forced_translucent(block_name)
                alpha = resized.split()[3]
                if not is_trans and alpha.getextrema()[0] < 255:
                    is_trans = True

                use_alpha_test = False
                if is_trans and _is_binary_alpha(resized):
                    use_alpha_test = True
                    is_trans = False

                trans_ref = ""
                if is_trans or use_alpha_test:
                    trans_ref = self._save_alpha_mask(resized, block_name, "_trans", mat_dir, material_prefix)
                if is_illum and not illum_ref:
                    illum_ref = self._save_alpha_mask(resized, block_name, "_illum", mat_dir, material_prefix)

                png_filename = f"{block_name}_color.png"
                png_path = os.path.join(mat_dir, png_filename)
                resized.save(png_path, format="PNG")
                texture_ref = f"{material_prefix}{png_filename}"

                if use_pbr:
                    vmat_content = _generate_pbr_vmat_content(
                        texture_ref,
                        roughness_path=rough_ref,
                        metalness_path=metalness_ref,
                        metalness_val=metalness_val,
                        normal_path=normal_ref,
                        self_illum=is_illum,
                        self_illum_mask_path=illum_ref,
                        glow_power=glow,
                        translucent=is_trans,
                        alpha_test=use_alpha_test,
                        translucency_path=trans_ref,
                        color_tint=tint,
                        render_backfaces=backfaces,
                    )
                else:
                    vmat_content = _generate_vmat_content(
                        texture_ref,
                        translucent=is_trans,
                        alpha_test=use_alpha_test,
                        translucency_path=trans_ref,
                        self_illum=is_illum,
                        self_illum_mask_path=illum_ref,
                        glow_power=glow,
                        color_tint=tint,
                        render_backfaces=backfaces,
                    )

            vmat_filename = f"{block_name}.vmat"
            vmat_path = os.path.join(mat_dir, vmat_filename)
            with open(vmat_path, "w", encoding="utf-8") as f:
                f.write(vmat_content)

            mat_ref = f"{material_prefix}{vmat_filename}"
            self._material_map[block_name] = mat_ref
            self._vmat_paths.append(vmat_path)

    def get_material_for_block(self, block_name: str, face_dir: str = None) -> str:
        """Get the CS2 material path for a Minecraft block, optionally per-face."""
        # Try face-specific lookup first
        if face_dir:
            tex_name = get_texture_name_for_face(block_name, face_dir)
            if tex_name in self._material_map:
                return self._material_map[tex_name]

        # Try plain texture name
        tex_name = get_texture_name(block_name)
        if tex_name in self._material_map:
            return self._material_map[tex_name]

        return DEFAULT_MATERIAL

    def get_all_materials(self) -> list[str]:
        """Get all unique material paths (for vmap material list)."""
        materials = list(set(self._material_map.values()))
        if not materials:
            materials = [DEFAULT_MATERIAL]
        elif DEFAULT_MATERIAL not in materials:
            materials.insert(0, DEFAULT_MATERIAL)
        return sorted(materials)

    def get_materials_for_blocks(self, block_types: set[str]) -> list[str]:
        """Get the list of materials needed for a set of block types (all faces)."""
        materials = set()
        face_dirs = ["+x", "-x", "+y", "-y", "+z", "-z"]
        for block_type in block_types:
            base = get_block_base_name(block_type)
            short = base[len("minecraft:"):] if base.startswith("minecraft:") else base
            if short in FACE_TEXTURE_MAP:
                for fd in face_dirs:
                    mat = self.get_material_for_block(block_type, fd)
                    materials.add(mat)
            else:
                mat = self.get_material_for_block(block_type)
                materials.add(mat)
        result = sorted(materials)
        if not result:
            result = [DEFAULT_MATERIAL]
        return result

    def get_all_vmat_paths(self) -> list[str]:
        """Get absolute paths of all generated .vmat files (for resource compiler)."""
        return list(self._vmat_paths)
