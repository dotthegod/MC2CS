"""Parser for Minecraft Structure Block .nbt files using nbtlib."""

import numpy as np
import nbtlib

from parsers.block_grid import BlockGrid


def parse_nbt(filepath: str) -> BlockGrid:
    """Parse a Minecraft Structure Block .nbt file into a BlockGrid.

    Structure format (Java Edition):
        - size: [width, height, length] (TAG_List of TAG_Int)
        - palette: TAG_List of TAG_Compound, each with 'Name' and optionally 'Properties'
        - blocks: TAG_List of TAG_Compound, each with 'state' (palette index) and 'pos' [x,y,z]
    """
    nbt_file = nbtlib.load(filepath)
    root = nbt_file.root if hasattr(nbt_file, 'root') else nbt_file

    # Dimensions
    size_tag = root["size"]
    width = int(size_tag[0])
    height = int(size_tag[1])
    length = int(size_tag[2])

    # Palette: list of compound tags with "Name" and optional "Properties"
    palette_tag = root["palette"]
    palette = {}
    for i, entry in enumerate(palette_tag):
        name = str(entry["Name"])
        if "Properties" in entry:
            props = entry["Properties"]
            prop_strs = []
            for key in props:
                prop_strs.append(f"{key}={props[key]}")
            if prop_strs:
                name += "[" + ",".join(sorted(prop_strs)) + "]"
        palette[i] = name

    # Blocks: list of compound tags with "state" and "pos"
    blocks_array = np.zeros((width, height, length), dtype=np.int32)

    if "blocks" in root:
        blocks_tag = root["blocks"]
        for block in blocks_tag:
            state = int(block["state"])
            pos = block["pos"]
            x = int(pos[0])
            y = int(pos[1])
            z = int(pos[2])
            if 0 <= x < width and 0 <= y < height and 0 <= z < length:
                blocks_array[x, y, z] = state

    return BlockGrid(width, height, length, blocks_array, palette)
