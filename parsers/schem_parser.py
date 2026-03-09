"""Parser for Sponge Schematic (.schem) files (v1, v2, v3) using nbtlib."""

import numpy as np
import nbtlib

from parsers.block_grid import BlockGrid


def _read_varint_array(data: bytes, expected_length: int) -> list[int]:
    """Decode a varint-encoded byte array into a list of integers."""
    result = []
    i = 0
    while i < len(data) and len(result) < expected_length:
        value = 0
        shift = 0
        while True:
            if i >= len(data):
                break
            b = data[i]
            i += 1
            value |= (b & 0x7F) << shift
            shift += 7
            if (b & 0x80) == 0:
                break
        result.append(value)
    return result


def parse_schem(filepath: str) -> BlockGrid:
    """Parse a Sponge Schematic .schem file into a BlockGrid.

    Sponge format (v1/v2/v3):
        - Schematic compound (may be root or nested)
        - Width, Height, Length: TAG_Short
        - Palette: TAG_Compound mapping block state strings to int indices
        - BlockData: TAG_Byte_Array (varint-encoded palette indices)
        - Index: x + (z * Width) + (y * Width * Length)
    """
    nbt_file = nbtlib.load(filepath)
    root = nbt_file.root if hasattr(nbt_file, 'root') else nbt_file

    # Handle nested "Schematic" tag (v3)
    if "Schematic" in root:
        root = root["Schematic"]

    width = int(root["Width"])
    height = int(root["Height"])
    length = int(root["Length"])

    total_blocks = width * height * length

    # Get palette and block data - handle v2 vs v3 differences
    if "Blocks" in root and hasattr(root["Blocks"], "__getitem__"):
        blocks_compound = root["Blocks"]
        if "Palette" in blocks_compound:
            # v3 format: Blocks.Palette and Blocks.Data
            palette_tag = blocks_compound["Palette"]
            block_data_raw = bytes(blocks_compound["Data"])
        else:
            # Unexpected structure, try direct
            palette_tag = root.get("Palette", {})
            block_data_raw = bytes(root.get("BlockData", b""))
    else:
        # v1/v2 format: Palette and BlockData at root level
        palette_tag = root["Palette"]
        block_data_raw = bytes(root["BlockData"])

    # Build palette: sponge format maps "block_state_string" -> int
    # We need int -> string
    palette = {}
    for key in palette_tag:
        idx = int(palette_tag[key])
        palette[idx] = str(key)

    # Decode varint block data
    block_indices = _read_varint_array(block_data_raw, total_blocks)

    # Build 3D array from flat block indices.
    # Index layout: x + (z * Width) + (y * Width * Length)
    # = X fastest, Z middle, Y slowest → reshape to (H, L, W) then transpose to (W, H, L)
    total_blocks = width * height * length
    flat = np.array(block_indices[:total_blocks], dtype=np.int32)
    if len(flat) < total_blocks:
        flat = np.pad(flat, (0, total_blocks - len(flat)))
    blocks_array = flat.reshape((height, length, width)).transpose(2, 0, 1)

    return BlockGrid(width, height, length, blocks_array, palette)
