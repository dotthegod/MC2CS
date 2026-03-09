"""Parser for legacy MCEdit/WorldEdit .schematic files using nbtlib."""

import numpy as np
import nbtlib

from parsers.block_grid import BlockGrid

# Legacy block ID to modern name mapping (subset of common blocks)
LEGACY_BLOCK_MAP = {
    0: "minecraft:air",
    1: "minecraft:stone",
    2: "minecraft:grass_block",
    3: "minecraft:dirt",
    4: "minecraft:cobblestone",
    5: "minecraft:oak_planks",
    6: "minecraft:oak_sapling",
    7: "minecraft:bedrock",
    8: "minecraft:water",
    9: "minecraft:water",
    10: "minecraft:lava",
    11: "minecraft:lava",
    12: "minecraft:sand",
    13: "minecraft:gravel",
    14: "minecraft:gold_ore",
    15: "minecraft:iron_ore",
    16: "minecraft:coal_ore",
    17: "minecraft:oak_log",
    18: "minecraft:oak_leaves",
    19: "minecraft:sponge",
    20: "minecraft:glass",
    21: "minecraft:lapis_ore",
    22: "minecraft:lapis_block",
    23: "minecraft:dispenser",
    24: "minecraft:sandstone",
    25: "minecraft:note_block",
    35: "minecraft:white_wool",
    41: "minecraft:gold_block",
    42: "minecraft:iron_block",
    43: "minecraft:smooth_stone_slab",
    44: "minecraft:smooth_stone_slab",
    45: "minecraft:bricks",
    46: "minecraft:tnt",
    47: "minecraft:bookshelf",
    48: "minecraft:mossy_cobblestone",
    49: "minecraft:obsidian",
    50: "minecraft:torch",
    52: "minecraft:spawner",
    53: "minecraft:oak_stairs",
    54: "minecraft:chest",
    56: "minecraft:diamond_ore",
    57: "minecraft:diamond_block",
    58: "minecraft:crafting_table",
    60: "minecraft:farmland",
    61: "minecraft:furnace",
    65: "minecraft:ladder",
    66: "minecraft:rail",
    67: "minecraft:cobblestone_stairs",
    73: "minecraft:redstone_ore",
    76: "minecraft:redstone_torch",
    78: "minecraft:snow",
    79: "minecraft:ice",
    80: "minecraft:snow_block",
    81: "minecraft:cactus",
    82: "minecraft:clay",
    84: "minecraft:jukebox",
    85: "minecraft:oak_fence",
    86: "minecraft:pumpkin",
    87: "minecraft:netherrack",
    88: "minecraft:soul_sand",
    89: "minecraft:glowstone",
    91: "minecraft:jack_o_lantern",
    95: "minecraft:white_stained_glass",
    97: "minecraft:infested_stone",
    98: "minecraft:stone_bricks",
    99: "minecraft:brown_mushroom_block",
    100: "minecraft:red_mushroom_block",
    101: "minecraft:iron_bars",
    102: "minecraft:glass_pane",
    103: "minecraft:melon",
    108: "minecraft:brick_stairs",
    109: "minecraft:stone_brick_stairs",
    110: "minecraft:mycelium",
    112: "minecraft:nether_bricks",
    113: "minecraft:nether_brick_fence",
    114: "minecraft:nether_brick_stairs",
    121: "minecraft:end_stone",
    123: "minecraft:redstone_lamp",
    125: "minecraft:oak_slab",
    126: "minecraft:oak_slab",
    128: "minecraft:sandstone_stairs",
    129: "minecraft:emerald_ore",
    133: "minecraft:emerald_block",
    134: "minecraft:spruce_stairs",
    135: "minecraft:birch_stairs",
    136: "minecraft:jungle_stairs",
    152: "minecraft:redstone_block",
    153: "minecraft:nether_quartz_ore",
    155: "minecraft:quartz_block",
    156: "minecraft:quartz_stairs",
    159: "minecraft:white_terracotta",
    160: "minecraft:white_stained_glass_pane",
    162: "minecraft:acacia_log",
    163: "minecraft:acacia_stairs",
    164: "minecraft:dark_oak_stairs",
    170: "minecraft:hay_block",
    172: "minecraft:terracotta",
    173: "minecraft:coal_block",
    174: "minecraft:packed_ice",
    179: "minecraft:red_sandstone",
    180: "minecraft:red_sandstone_stairs",
    201: "minecraft:purpur_block",
    202: "minecraft:purpur_pillar",
    203: "minecraft:purpur_stairs",
    206: "minecraft:end_stone_bricks",
    213: "minecraft:magma_block",
    214: "minecraft:nether_wart_block",
    215: "minecraft:red_nether_bricks",
    235: "minecraft:white_glazed_terracotta",
    251: "minecraft:white_concrete",
    252: "minecraft:white_concrete_powder",
}


def parse_schematic(filepath: str) -> BlockGrid:
    """Parse a legacy .schematic file into a BlockGrid.

    Legacy format:
        - Width, Height, Length: TAG_Short
        - Blocks: TAG_Byte_Array (block IDs, 0-255)
        - Data: TAG_Byte_Array (block metadata)
        - Index: x + (z * Width) + (y * Width * Length)
    """
    nbt_file = nbtlib.load(filepath)
    root = nbt_file.root if hasattr(nbt_file, 'root') else nbt_file

    width = int(root["Width"])
    height = int(root["Height"])
    length = int(root["Length"])

    blocks_raw = np.array(root["Blocks"], dtype=np.int32)

    # Build palette from unique block IDs found
    unique_ids = np.unique(blocks_raw)
    palette = {}
    for i, block_id in enumerate(unique_ids):
        palette[i] = LEGACY_BLOCK_MAP.get(int(block_id), f"minecraft:unknown_{block_id}")

    # Create ID remap: old block_id -> new palette index
    id_remap = {}
    for i, block_id in enumerate(unique_ids):
        id_remap[int(block_id)] = i

    # Build 3D array from flat block data.
    # Index layout: x + (z * Width) + (y * Width * Length)
    # = X fastest, Z middle, Y slowest → reshape to (H, L, W) then transpose to (W, H, L)
    total_blocks = width * height * length
    # Remap old IDs to palette indices using vectorized lookup
    max_old = int(blocks_raw.max()) + 1 if len(blocks_raw) > 0 else 1
    remap_lut = np.zeros(max_old, dtype=np.int32)
    for old_id, new_idx in id_remap.items():
        if old_id < max_old:
            remap_lut[old_id] = new_idx
    remapped = remap_lut[blocks_raw[:total_blocks]]
    if len(remapped) < total_blocks:
        remapped = np.pad(remapped, (0, total_blocks - len(remapped)))
    blocks_array = remapped.reshape((height, length, width)).transpose(2, 0, 1)

    return BlockGrid(width, height, length, blocks_array, palette)
