"""Block classification registry for Minecraft blocks."""

from config.texture_mapping import TEXTURE_REMAP, FACE_TEXTURE_MAP

# Blocks that are considered air (no geometry generated)
AIR_BLOCKS = frozenset({
    "minecraft:air",
    "minecraft:cave_air",
    "minecraft:void_air",
})

# Blocks that are transparent (faces adjacent to these are still rendered)
TRANSPARENT_BLOCKS = frozenset({
    "minecraft:glass",
    "minecraft:glass_pane",
    "minecraft:white_stained_glass", "minecraft:orange_stained_glass",
    "minecraft:magenta_stained_glass", "minecraft:light_blue_stained_glass",
    "minecraft:yellow_stained_glass", "minecraft:lime_stained_glass",
    "minecraft:pink_stained_glass", "minecraft:gray_stained_glass",
    "minecraft:light_gray_stained_glass", "minecraft:cyan_stained_glass",
    "minecraft:purple_stained_glass", "minecraft:blue_stained_glass",
    "minecraft:brown_stained_glass", "minecraft:green_stained_glass",
    "minecraft:red_stained_glass", "minecraft:black_stained_glass",
    "minecraft:white_stained_glass_pane", "minecraft:orange_stained_glass_pane",
    "minecraft:magenta_stained_glass_pane", "minecraft:light_blue_stained_glass_pane",
    "minecraft:yellow_stained_glass_pane", "minecraft:lime_stained_glass_pane",
    "minecraft:pink_stained_glass_pane", "minecraft:gray_stained_glass_pane",
    "minecraft:light_gray_stained_glass_pane", "minecraft:cyan_stained_glass_pane",
    "minecraft:purple_stained_glass_pane", "minecraft:blue_stained_glass_pane",
    "minecraft:brown_stained_glass_pane", "minecraft:green_stained_glass_pane",
    "minecraft:red_stained_glass_pane", "minecraft:black_stained_glass_pane",
    "minecraft:tinted_glass",
    "minecraft:ice",
    "minecraft:frosted_ice",
    "minecraft:water",
    "minecraft:lava",
    "minecraft:oak_leaves", "minecraft:spruce_leaves", "minecraft:birch_leaves",
    "minecraft:jungle_leaves", "minecraft:acacia_leaves", "minecraft:dark_oak_leaves",
    "minecraft:mangrove_leaves", "minecraft:cherry_leaves", "minecraft:azalea_leaves",
    "minecraft:flowering_azalea_leaves",
    "minecraft:slime_block", "minecraft:honey_block",
    "minecraft:barrier",
    "minecraft:light",
    "minecraft:structure_void",
    # Plants, flowers, crops — textures with alpha transparency
    "minecraft:short_grass", "minecraft:tall_grass", "minecraft:fern", "minecraft:large_fern",
    "minecraft:dead_bush", "minecraft:vine", "minecraft:glow_lichen",
    "minecraft:dandelion", "minecraft:poppy", "minecraft:blue_orchid",
    "minecraft:allium", "minecraft:azure_bluet", "minecraft:red_tulip",
    "minecraft:orange_tulip", "minecraft:white_tulip", "minecraft:pink_tulip",
    "minecraft:oxeye_daisy", "minecraft:cornflower", "minecraft:lily_of_the_valley",
    "minecraft:wither_rose", "minecraft:sunflower", "minecraft:lilac",
    "minecraft:rose_bush", "minecraft:peony", "minecraft:torchflower",
    "minecraft:pitcher_plant",
    "minecraft:sugar_cane", "minecraft:bamboo",
    "minecraft:lily_pad",
    "minecraft:wheat", "minecraft:carrots", "minecraft:potatoes", "minecraft:beetroots",
    "minecraft:nether_wart", "minecraft:sweet_berry_bush",
    "minecraft:melon_stem", "minecraft:pumpkin_stem",
    "minecraft:oak_sapling", "minecraft:spruce_sapling", "minecraft:birch_sapling",
    "minecraft:jungle_sapling", "minecraft:acacia_sapling", "minecraft:dark_oak_sapling",
    "minecraft:cherry_sapling", "minecraft:pale_oak_sapling",
    "minecraft:brown_mushroom", "minecraft:red_mushroom",
    "minecraft:torch", "minecraft:wall_torch",
    "minecraft:soul_torch", "minecraft:soul_wall_torch",
    "minecraft:redstone_torch", "minecraft:redstone_wall_torch",
    "minecraft:lantern", "minecraft:soul_lantern",
    # Rails
    "minecraft:rail", "minecraft:powered_rail", "minecraft:detector_rail", "minecraft:activator_rail",
    # Nether wart
    "minecraft:nether_wart",
    "minecraft:cactus",
    "minecraft:chorus_flower", "minecraft:chorus_plant",
    # Trapdoors
    "minecraft:oak_trapdoor", "minecraft:spruce_trapdoor", "minecraft:birch_trapdoor",
    "minecraft:jungle_trapdoor", "minecraft:acacia_trapdoor", "minecraft:dark_oak_trapdoor",
    "minecraft:crimson_trapdoor", "minecraft:warped_trapdoor", "minecraft:mangrove_trapdoor",
    "minecraft:cherry_trapdoor", "minecraft:bamboo_trapdoor", "minecraft:iron_trapdoor",
    # Seagrass and corals
    "minecraft:seagrass", "minecraft:tall_seagrass",
    "minecraft:tube_coral", "minecraft:brain_coral", "minecraft:bubble_coral",
    "minecraft:fire_coral", "minecraft:horn_coral",
    "minecraft:dead_tube_coral", "minecraft:dead_brain_coral", "minecraft:dead_bubble_coral",
    "minecraft:dead_fire_coral", "minecraft:dead_horn_coral",
    "minecraft:tube_coral_fan", "minecraft:brain_coral_fan", "minecraft:bubble_coral_fan",
    "minecraft:fire_coral_fan", "minecraft:horn_coral_fan",
    "minecraft:dead_tube_coral_fan", "minecraft:dead_brain_coral_fan",
    "minecraft:dead_bubble_coral_fan", "minecraft:dead_fire_coral_fan",
    "minecraft:dead_horn_coral_fan",
    "minecraft:tube_coral_wall_fan", "minecraft:brain_coral_wall_fan",
    "minecraft:bubble_coral_wall_fan", "minecraft:fire_coral_wall_fan",
    "minecraft:horn_coral_wall_fan",
    "minecraft:dead_tube_coral_wall_fan", "minecraft:dead_brain_coral_wall_fan",
    "minecraft:dead_bubble_coral_wall_fan", "minecraft:dead_fire_coral_wall_fan",
    "minecraft:dead_horn_coral_wall_fan",
    # Coral blocks (full cube but transparent)
    "minecraft:tube_coral_block", "minecraft:brain_coral_block",
    "minecraft:bubble_coral_block", "minecraft:fire_coral_block",
    "minecraft:horn_coral_block",
    "minecraft:dead_tube_coral_block", "minecraft:dead_brain_coral_block",
    "minecraft:dead_bubble_coral_block", "minecraft:dead_fire_coral_block",
    "minecraft:dead_horn_coral_block",
    # Iron bars (model-based, not full cube)
    "minecraft:iron_bars",
    # Beds (non-full-cube, model blocks)
    "minecraft:white_bed", "minecraft:orange_bed", "minecraft:magenta_bed",
    "minecraft:light_blue_bed", "minecraft:yellow_bed", "minecraft:lime_bed",
    "minecraft:pink_bed", "minecraft:gray_bed", "minecraft:light_gray_bed",
    "minecraft:cyan_bed", "minecraft:purple_bed", "minecraft:blue_bed",
    "minecraft:brown_bed", "minecraft:green_bed", "minecraft:red_bed",
    "minecraft:black_bed",
    # Flower pots
    "minecraft:flower_pot",
    "minecraft:potted_dandelion", "minecraft:potted_poppy", "minecraft:potted_blue_orchid",
    "minecraft:potted_allium", "minecraft:potted_azure_bluet",
    "minecraft:potted_red_tulip", "minecraft:potted_orange_tulip",
    "minecraft:potted_white_tulip", "minecraft:potted_pink_tulip",
    "minecraft:potted_oxeye_daisy", "minecraft:potted_cornflower",
    "minecraft:potted_lily_of_the_valley", "minecraft:potted_wither_rose",
    "minecraft:potted_oak_sapling", "minecraft:potted_spruce_sapling",
    "minecraft:potted_birch_sapling", "minecraft:potted_jungle_sapling",
    "minecraft:potted_acacia_sapling", "minecraft:potted_dark_oak_sapling",
    "minecraft:potted_cherry_sapling", "minecraft:potted_bamboo",
    "minecraft:potted_red_mushroom", "minecraft:potted_brown_mushroom",
    "minecraft:potted_fern", "minecraft:potted_dead_bush",
    "minecraft:potted_cactus", "minecraft:potted_azalea_bush",
    "minecraft:potted_flowering_azalea_bush", "minecraft:potted_torchflower",
})

# Non-solid blocks (no geometry, treated like air for face culling)
# These are truly invisible or decorative blocks that produce no mesh at all
NON_SOLID_BLOCKS = frozenset({
    "minecraft:redstone_wire",
    "minecraft:repeater", "minecraft:comparator",
    "minecraft:string",
    "minecraft:tripwire", "minecraft:tripwire_hook",
    "minecraft:painting", "minecraft:item_frame", "minecraft:glow_item_frame",
    "minecraft:fire", "minecraft:soul_fire",
    "minecraft:cobweb",
    "minecraft:sign", "minecraft:wall_sign",
    "minecraft:oak_sign", "minecraft:spruce_sign", "minecraft:birch_sign",
    "minecraft:jungle_sign", "minecraft:acacia_sign", "minecraft:dark_oak_sign",
    "minecraft:oak_wall_sign", "minecraft:spruce_wall_sign", "minecraft:birch_wall_sign",
    "minecraft:jungle_wall_sign", "minecraft:acacia_wall_sign", "minecraft:dark_oak_wall_sign",
    "minecraft:oak_hanging_sign", "minecraft:spruce_hanging_sign",
    "minecraft:birch_hanging_sign", "minecraft:jungle_hanging_sign",
    "minecraft:acacia_hanging_sign", "minecraft:dark_oak_hanging_sign",
    "minecraft:crimson_sign", "minecraft:warped_sign",
    "minecraft:crimson_wall_sign", "minecraft:warped_wall_sign",
    "minecraft:mangrove_sign", "minecraft:mangrove_wall_sign",
    "minecraft:cherry_sign", "minecraft:cherry_wall_sign",
    "minecraft:bamboo_sign", "minecraft:bamboo_wall_sign",
})

# Model blocks: non-solid blocks that DO generate geometry via MC model data.
# These are non-full-cube blocks with model-based meshes (torches, fences, slabs, etc.)
MODEL_BLOCKS = frozenset({
    "minecraft:torch", "minecraft:wall_torch",
    "minecraft:soul_torch", "minecraft:soul_wall_torch",
    "minecraft:redstone_torch", "minecraft:redstone_wall_torch",
    "minecraft:lever",
    "minecraft:rail", "minecraft:powered_rail", "minecraft:detector_rail", "minecraft:activator_rail",
    "minecraft:dandelion", "minecraft:poppy", "minecraft:blue_orchid",
    "minecraft:allium", "minecraft:azure_bluet", "minecraft:red_tulip",
    "minecraft:orange_tulip", "minecraft:white_tulip", "minecraft:pink_tulip",
    "minecraft:oxeye_daisy", "minecraft:cornflower", "minecraft:lily_of_the_valley",
    "minecraft:wither_rose", "minecraft:sunflower", "minecraft:lilac",
    "minecraft:rose_bush", "minecraft:peony", "minecraft:torchflower",
    "minecraft:pitcher_plant",
    "minecraft:tall_grass", "minecraft:short_grass", "minecraft:fern", "minecraft:large_fern",
    "minecraft:dead_bush",
    "minecraft:sugar_cane", "minecraft:bamboo",
    "minecraft:vine", "minecraft:glow_lichen",
    # Crops and crop-like blocks
    "minecraft:wheat", "minecraft:carrots", "minecraft:potatoes", "minecraft:beetroots",
    "minecraft:nether_wart", "minecraft:sweet_berry_bush", "minecraft:cocoa",
    "minecraft:melon_stem", "minecraft:pumpkin_stem",
    "minecraft:attached_melon_stem", "minecraft:attached_pumpkin_stem",
    "minecraft:torchflower_crop", "minecraft:pitcher_crop",
    "minecraft:cave_vines", "minecraft:cave_vines_plant",
    "minecraft:twisting_vines", "minecraft:twisting_vines_plant",
    "minecraft:weeping_vines", "minecraft:weeping_vines_plant",
    "minecraft:kelp", "minecraft:kelp_plant",
    # Cactus and chorus (inset / non-full-cube models)
    "minecraft:cactus",
    "minecraft:chorus_flower", "minecraft:chorus_plant",
    # Seagrass
    "minecraft:seagrass", "minecraft:tall_seagrass",
    # Coral fans and corals
    "minecraft:tube_coral", "minecraft:brain_coral", "minecraft:bubble_coral",
    "minecraft:fire_coral", "minecraft:horn_coral",
    "minecraft:dead_tube_coral", "minecraft:dead_brain_coral", "minecraft:dead_bubble_coral",
    "minecraft:dead_fire_coral", "minecraft:dead_horn_coral",
    "minecraft:tube_coral_fan", "minecraft:brain_coral_fan", "minecraft:bubble_coral_fan",
    "minecraft:fire_coral_fan", "minecraft:horn_coral_fan",
    "minecraft:dead_tube_coral_fan", "minecraft:dead_brain_coral_fan",
    "minecraft:dead_bubble_coral_fan", "minecraft:dead_fire_coral_fan",
    "minecraft:dead_horn_coral_fan",
    "minecraft:tube_coral_wall_fan", "minecraft:brain_coral_wall_fan",
    "minecraft:bubble_coral_wall_fan", "minecraft:fire_coral_wall_fan",
    "minecraft:horn_coral_wall_fan",
    "minecraft:dead_tube_coral_wall_fan", "minecraft:dead_brain_coral_wall_fan",
    "minecraft:dead_bubble_coral_wall_fan", "minecraft:dead_fire_coral_wall_fan",
    "minecraft:dead_horn_coral_wall_fan",
    # Iron bars
    "minecraft:iron_bars",
    # Saplings
    "minecraft:oak_sapling", "minecraft:spruce_sapling", "minecraft:birch_sapling",
    "minecraft:jungle_sapling", "minecraft:acacia_sapling", "minecraft:dark_oak_sapling",
    "minecraft:cherry_sapling", "minecraft:pale_oak_sapling", "minecraft:bamboo_sapling",
    # Mushrooms
    "minecraft:brown_mushroom", "minecraft:red_mushroom",
    # Sea pickle
    "minecraft:sea_pickle",
    "minecraft:ladder",
    "minecraft:snow",
    "minecraft:button", "minecraft:stone_button",
    "minecraft:oak_button", "minecraft:spruce_button", "minecraft:birch_button",
    "minecraft:jungle_button", "minecraft:acacia_button", "minecraft:dark_oak_button",
    "minecraft:crimson_button", "minecraft:warped_button",
    "minecraft:mangrove_button", "minecraft:cherry_button", "minecraft:bamboo_button",
    "minecraft:polished_blackstone_button",
    "minecraft:pressure_plate", "minecraft:stone_pressure_plate",
    "minecraft:oak_pressure_plate", "minecraft:spruce_pressure_plate",
    "minecraft:birch_pressure_plate", "minecraft:jungle_pressure_plate",
    "minecraft:acacia_pressure_plate", "minecraft:dark_oak_pressure_plate",
    "minecraft:crimson_pressure_plate", "minecraft:warped_pressure_plate",
    "minecraft:light_weighted_pressure_plate", "minecraft:heavy_weighted_pressure_plate",
    "minecraft:mangrove_pressure_plate", "minecraft:cherry_pressure_plate",
    "minecraft:bamboo_pressure_plate",
    "minecraft:polished_blackstone_pressure_plate",
    "minecraft:carpet",
    "minecraft:white_carpet", "minecraft:orange_carpet", "minecraft:magenta_carpet",
    "minecraft:light_blue_carpet", "minecraft:yellow_carpet", "minecraft:lime_carpet",
    "minecraft:pink_carpet", "minecraft:gray_carpet", "minecraft:light_gray_carpet",
    "minecraft:cyan_carpet", "minecraft:purple_carpet", "minecraft:blue_carpet",
    "minecraft:brown_carpet", "minecraft:green_carpet", "minecraft:red_carpet",
    "minecraft:black_carpet", "minecraft:moss_carpet",
    "minecraft:lily_pad",
    "minecraft:lantern", "minecraft:soul_lantern",
    "minecraft:campfire", "minecraft:soul_campfire",
    "minecraft:chest", "minecraft:ender_chest", "minecraft:trapped_chest",
    # Beds
    "minecraft:white_bed", "minecraft:orange_bed", "minecraft:magenta_bed",
    "minecraft:light_blue_bed", "minecraft:yellow_bed", "minecraft:lime_bed",
    "minecraft:pink_bed", "minecraft:gray_bed", "minecraft:light_gray_bed",
    "minecraft:cyan_bed", "minecraft:purple_bed", "minecraft:blue_bed",
    "minecraft:brown_bed", "minecraft:green_bed", "minecraft:red_bed",
    "minecraft:black_bed",
    # Flower pot
    "minecraft:flower_pot",
    "minecraft:potted_dandelion", "minecraft:potted_poppy", "minecraft:potted_blue_orchid",
    "minecraft:potted_allium", "minecraft:potted_azure_bluet",
    "minecraft:potted_red_tulip", "minecraft:potted_orange_tulip",
    "minecraft:potted_white_tulip", "minecraft:potted_pink_tulip",
    "minecraft:potted_oxeye_daisy", "minecraft:potted_cornflower",
    "minecraft:potted_lily_of_the_valley", "minecraft:potted_wither_rose",
    "minecraft:potted_oak_sapling", "minecraft:potted_spruce_sapling",
    "minecraft:potted_birch_sapling", "minecraft:potted_jungle_sapling",
    "minecraft:potted_acacia_sapling", "minecraft:potted_dark_oak_sapling",
    "minecraft:potted_cherry_sapling", "minecraft:potted_bamboo",
    "minecraft:potted_red_mushroom", "minecraft:potted_brown_mushroom",
    "minecraft:potted_fern", "minecraft:potted_dead_bush",
    "minecraft:potted_cactus", "minecraft:potted_azalea_bush",
    "minecraft:potted_flowering_azalea_bush", "minecraft:potted_torchflower",
    # Slabs
    "minecraft:oak_slab", "minecraft:spruce_slab", "minecraft:birch_slab",
    "minecraft:jungle_slab", "minecraft:acacia_slab", "minecraft:dark_oak_slab",
    "minecraft:crimson_slab", "minecraft:warped_slab", "minecraft:mangrove_slab",
    "minecraft:cherry_slab", "minecraft:bamboo_slab", "minecraft:bamboo_mosaic_slab",
    "minecraft:stone_slab", "minecraft:smooth_stone_slab", "minecraft:cobblestone_slab",
    "minecraft:sandstone_slab", "minecraft:red_sandstone_slab",
    "minecraft:brick_slab", "minecraft:stone_brick_slab", "minecraft:nether_brick_slab",
    "minecraft:quartz_slab", "minecraft:prismarine_slab", "minecraft:prismarine_brick_slab",
    "minecraft:dark_prismarine_slab", "minecraft:purpur_slab",
    "minecraft:polished_granite_slab", "minecraft:polished_diorite_slab",
    "minecraft:polished_andesite_slab", "minecraft:mossy_cobblestone_slab",
    "minecraft:mossy_stone_brick_slab", "minecraft:smooth_sandstone_slab",
    "minecraft:smooth_red_sandstone_slab", "minecraft:smooth_quartz_slab",
    "minecraft:granite_slab", "minecraft:diorite_slab", "minecraft:andesite_slab",
    "minecraft:red_nether_brick_slab", "minecraft:end_stone_brick_slab",
    "minecraft:blackstone_slab", "minecraft:polished_blackstone_slab",
    "minecraft:polished_blackstone_brick_slab",
    "minecraft:cut_copper_slab", "minecraft:exposed_cut_copper_slab",
    "minecraft:weathered_cut_copper_slab", "minecraft:oxidized_cut_copper_slab",
    "minecraft:waxed_cut_copper_slab", "minecraft:waxed_exposed_cut_copper_slab",
    "minecraft:waxed_weathered_cut_copper_slab", "minecraft:waxed_oxidized_cut_copper_slab",
    "minecraft:cobbled_deepslate_slab", "minecraft:polished_deepslate_slab",
    "minecraft:deepslate_brick_slab", "minecraft:deepslate_tile_slab",
    "minecraft:mud_brick_slab", "minecraft:tuff_slab", "minecraft:polished_tuff_slab",
    "minecraft:tuff_brick_slab",
    # Stairs
    "minecraft:oak_stairs", "minecraft:spruce_stairs", "minecraft:birch_stairs",
    "minecraft:jungle_stairs", "minecraft:acacia_stairs", "minecraft:dark_oak_stairs",
    "minecraft:crimson_stairs", "minecraft:warped_stairs", "minecraft:mangrove_stairs",
    "minecraft:cherry_stairs", "minecraft:bamboo_stairs", "minecraft:bamboo_mosaic_stairs",
    "minecraft:stone_stairs", "minecraft:cobblestone_stairs",
    "minecraft:sandstone_stairs", "minecraft:red_sandstone_stairs",
    "minecraft:brick_stairs", "minecraft:stone_brick_stairs", "minecraft:nether_brick_stairs",
    "minecraft:quartz_stairs", "minecraft:prismarine_stairs", "minecraft:prismarine_brick_stairs",
    "minecraft:dark_prismarine_stairs", "minecraft:purpur_stairs",
    "minecraft:polished_granite_stairs", "minecraft:polished_diorite_stairs",
    "minecraft:polished_andesite_stairs", "minecraft:mossy_cobblestone_stairs",
    "minecraft:mossy_stone_brick_stairs", "minecraft:smooth_sandstone_stairs",
    "minecraft:smooth_red_sandstone_stairs", "minecraft:smooth_quartz_stairs",
    "minecraft:granite_stairs", "minecraft:diorite_stairs", "minecraft:andesite_stairs",
    "minecraft:red_nether_brick_stairs", "minecraft:end_stone_brick_stairs",
    "minecraft:blackstone_stairs", "minecraft:polished_blackstone_stairs",
    "minecraft:polished_blackstone_brick_stairs",
    "minecraft:cut_copper_stairs", "minecraft:oxidized_cut_copper_stairs",
    "minecraft:weathered_cut_copper_stairs", "minecraft:exposed_cut_copper_stairs",
    "minecraft:waxed_cut_copper_stairs", "minecraft:waxed_oxidized_cut_copper_stairs",
    "minecraft:waxed_weathered_cut_copper_stairs", "minecraft:waxed_exposed_cut_copper_stairs",
    "minecraft:cobbled_deepslate_stairs", "minecraft:polished_deepslate_stairs",
    "minecraft:deepslate_brick_stairs", "minecraft:deepslate_tile_stairs",
    "minecraft:mud_brick_stairs", "minecraft:tuff_stairs", "minecraft:polished_tuff_stairs",
    "minecraft:tuff_brick_stairs",
    "minecraft:pale_oak_stairs", "minecraft:resin_brick_stairs",
    # Fences, walls, doors, trapdoors
    "minecraft:oak_fence", "minecraft:spruce_fence", "minecraft:birch_fence",
    "minecraft:jungle_fence", "minecraft:acacia_fence", "minecraft:dark_oak_fence",
    "minecraft:crimson_fence", "minecraft:warped_fence", "minecraft:mangrove_fence",
    "minecraft:cherry_fence", "minecraft:bamboo_fence", "minecraft:nether_brick_fence",
    "minecraft:oak_fence_gate", "minecraft:spruce_fence_gate", "minecraft:birch_fence_gate",
    "minecraft:jungle_fence_gate", "minecraft:acacia_fence_gate", "minecraft:dark_oak_fence_gate",
    "minecraft:crimson_fence_gate", "minecraft:warped_fence_gate",
    "minecraft:mangrove_fence_gate", "minecraft:cherry_fence_gate", "minecraft:bamboo_fence_gate",
    "minecraft:cobblestone_wall", "minecraft:mossy_cobblestone_wall",
    "minecraft:brick_wall", "minecraft:stone_brick_wall", "minecraft:mossy_stone_brick_wall",
    "minecraft:nether_brick_wall", "minecraft:red_nether_brick_wall",
    "minecraft:sandstone_wall", "minecraft:red_sandstone_wall",
    "minecraft:granite_wall", "minecraft:diorite_wall", "minecraft:andesite_wall",
    "minecraft:prismarine_wall", "minecraft:end_stone_brick_wall",
    "minecraft:blackstone_wall", "minecraft:polished_blackstone_wall",
    "minecraft:polished_blackstone_brick_wall",
    "minecraft:cobbled_deepslate_wall", "minecraft:polished_deepslate_wall",
    "minecraft:deepslate_brick_wall", "minecraft:deepslate_tile_wall",
    "minecraft:mud_brick_wall", "minecraft:tuff_wall", "minecraft:polished_tuff_wall",
    "minecraft:tuff_brick_wall",
    "minecraft:oak_door", "minecraft:spruce_door", "minecraft:birch_door",
    "minecraft:jungle_door", "minecraft:acacia_door", "minecraft:dark_oak_door",
    "minecraft:crimson_door", "minecraft:warped_door", "minecraft:mangrove_door",
    "minecraft:cherry_door", "minecraft:bamboo_door", "minecraft:iron_door",
    "minecraft:oak_trapdoor", "minecraft:spruce_trapdoor", "minecraft:birch_trapdoor",
    "minecraft:jungle_trapdoor", "minecraft:acacia_trapdoor", "minecraft:dark_oak_trapdoor",
    "minecraft:crimson_trapdoor", "minecraft:warped_trapdoor", "minecraft:mangrove_trapdoor",
    "minecraft:cherry_trapdoor", "minecraft:bamboo_trapdoor", "minecraft:iron_trapdoor",
    # Farmland (not a full cube — 15/16 height)
    "minecraft:farmland",
    # Daylight detector (6/16 height)
    "minecraft:daylight_detector",
})

# Blocks that emit light (self-illuminated in CS2)
SELF_ILLUMINATED_BLOCKS = frozenset({
    "minecraft:glowstone",
    "minecraft:sea_lantern",
    "minecraft:jack_o_lantern",
    "minecraft:shroomlight",
    "minecraft:magma_block",
    "minecraft:beacon",
    "minecraft:redstone_lamp",
    "minecraft:ochre_froglight", "minecraft:verdant_froglight", "minecraft:pearlescent_froglight",
    "minecraft:end_rod",
    "minecraft:crying_obsidian",
    "minecraft:respawn_anchor",
    "minecraft:sculk_catalyst",
    "minecraft:lantern", "minecraft:soul_lantern",
    "minecraft:campfire", "minecraft:soul_campfire",
    "minecraft:lava",
})


# Light-emitting blocks for auto-lighting (main light providers only).
# Maps block base name -> (light_level, color_rgb, lumens).
# Lumens calibrated with torch = 400 as reference.
LIGHT_EMITTING_BLOCKS = {
    # Full bright (level 15)
    "minecraft:glowstone":          (15, "255 241 224", 640),
    "minecraft:sea_lantern":        (15, "200 230 255", 640),
    "minecraft:jack_o_lantern":     (15, "255 200 100", 560),
    "minecraft:shroomlight":        (15, "255 230 180", 560),
    "minecraft:redstone_lamp":      (15, "255 200 100", 560),
    "minecraft:ochre_froglight":    (15, "255 230 150", 560),
    "minecraft:verdant_froglight":  (15, "200 255 200", 560),
    "minecraft:pearlescent_froglight": (15, "230 200 255", 560),
    # Torches (level 14)
    "minecraft:torch":              (14, "255 200 100", 400),
    "minecraft:wall_torch":         (14, "255 200 100", 400),
    # Soul torches (level 10)
    "minecraft:soul_torch":         (10, "100 200 255", 280),
    "minecraft:soul_wall_torch":    (10, "100 200 255", 280),
    # Lanterns
    "minecraft:lantern":            (15, "255 200 100", 480),
    "minecraft:soul_lantern":       (10, "100 200 255", 320),
    # Campfires
    "minecraft:campfire":           (15, "255 180 80", 480),
    "minecraft:soul_campfire":      (10, "100 200 255", 280),
    # End rod
    "minecraft:end_rod":            (14, "255 255 240", 400),
}

# Blocks whose meshes should not cast shadows.
NOSHADOW_MESH_BLOCKS = frozenset({
    "minecraft:torch", "minecraft:wall_torch",
    "minecraft:soul_torch", "minecraft:soul_wall_torch",
    "minecraft:redstone_torch", "minecraft:redstone_wall_torch",
    "minecraft:oak_trapdoor", "minecraft:spruce_trapdoor",
    "minecraft:birch_trapdoor", "minecraft:jungle_trapdoor",
    "minecraft:acacia_trapdoor", "minecraft:dark_oak_trapdoor",
    "minecraft:crimson_trapdoor", "minecraft:warped_trapdoor",
    "minecraft:mangrove_trapdoor", "minecraft:cherry_trapdoor",
    "minecraft:bamboo_trapdoor", "minecraft:iron_trapdoor",
})


def is_light_source(block_name: str) -> bool:
    """Check if a block emits light for auto-lighting."""
    base = block_name.split("[")[0] if "[" in block_name else block_name
    return base in LIGHT_EMITTING_BLOCKS


def get_light_properties(block_name: str):
    """Get light properties for a block. Returns (level, color, lumens) or None."""
    base = block_name.split("[")[0] if "[" in block_name else block_name
    return LIGHT_EMITTING_BLOCKS.get(base)


def is_noshadow_mesh(block_name: str) -> bool:
    """Check if block's mesh should have shadows disabled."""
    base = block_name.split("[")[0] if "[" in block_name else block_name
    return base in NOSHADOW_MESH_BLOCKS
# Needed because the material generator passes texture names ("lava_still")
# while SELF_ILLUMINATED_BLOCKS stores block names ("minecraft:lava").
def _build_self_illum_texture_names() -> frozenset:
    names = set()
    for block in SELF_ILLUMINATED_BLOCKS:
        short = block[len("minecraft:"):] if block.startswith("minecraft:") else block
        names.add(TEXTURE_REMAP.get(short, short))
    return frozenset(names)

_SELF_ILLUMINATED_TEXTURE_NAMES = _build_self_illum_texture_names()


def is_air(block_name: str) -> bool:
    """Check if block is air (or structure void)."""
    base = block_name.split("[")[0] if "[" in block_name else block_name
    return base in AIR_BLOCKS


def is_solid_for_culling(block_name: str) -> bool:
    """Check if block is solid for face culling purposes.
    Returns True if this block should HIDE adjacent faces (i.e., is opaque and solid).
    """
    base = block_name.split("[")[0] if "[" in block_name else block_name
    if base in AIR_BLOCKS:
        return False
    if base in TRANSPARENT_BLOCKS:
        return False
    if base in NON_SOLID_BLOCKS:
        return False
    if base in MODEL_BLOCKS:
        # Double slabs are full blocks and should cull adjacent faces
        if "type=double" in block_name:
            return True
        return False
    return True


def should_generate_geometry(block_name: str) -> bool:
    """Check if this block should generate mesh geometry."""
    base = block_name.split("[")[0] if "[" in block_name else block_name
    if base in AIR_BLOCKS:
        return False
    if base in NON_SOLID_BLOCKS:
        return False
    return True


def is_model_block(block_name: str) -> bool:
    """Check if this block uses model-based geometry (non-full-cube)."""
    base = block_name.split("[")[0] if "[" in block_name else block_name
    return base in MODEL_BLOCKS


def get_block_base_name(block_name: str) -> str:
    """Strip block state properties: 'minecraft:oak_log[axis=y]' -> 'minecraft:oak_log'"""
    return block_name.split("[")[0] if "[" in block_name else block_name


# FACE_TEXTURE_MAP and TEXTURE_REMAP are imported from config.texture_mapping
# (auto-generated from Minecraft 1.21.11+ Template via textures/model_resolver.py)

# Textures that need a tint mask (partial tint via overlay texture).
# Maps texture name -> overlay texture name in the resource pack.
# The overlay's alpha channel is used as a grayscale tint mask.
TINT_MASK_OVERLAYS = {
    "grass_block_side": "grass_block_side_overlay",
}


# Blocks that should get a green color tint in their material
# (they are grey/white in the texture pack and tinted in-game)
TINTED_BLOCKS = {
    "grass_block_top": "[0.372549 0.619608 0.207843 0.000000]",
    "grass_block_side": "[0.372549 0.619608 0.207843 0.000000]",
    "oak_leaves": "[0.337255 0.517647 0.207843 0.000000]",
    "spruce_leaves": "[0.380392 0.509804 0.337255 0.000000]",
    "birch_leaves": "[0.505882 0.584314 0.341176 0.000000]",
    "jungle_leaves": "[0.207843 0.552941 0.145098 0.000000]",
    "acacia_leaves": "[0.396078 0.556863 0.207843 0.000000]",
    "dark_oak_leaves": "[0.337255 0.517647 0.207843 0.000000]",
    "mangrove_leaves": "[0.356863 0.576471 0.207843 0.000000]",
    "azalea_leaves": "[0.337255 0.517647 0.207843 0.000000]",
    "flowering_azalea_leaves": "[0.337255 0.517647 0.207843 0.000000]",
    "short_grass": "[0.372549 0.619608 0.207843 0.000000]",
    "tall_grass": "[0.372549 0.619608 0.207843 0.000000]",
    "tall_grass_top": "[0.372549 0.619608 0.207843 0.000000]",
    "tall_grass_bottom": "[0.372549 0.619608 0.207843 0.000000]",
    "fern": "[0.372549 0.619608 0.207843 0.000000]",
    "large_fern": "[0.372549 0.619608 0.207843 0.000000]",
    "large_fern_top": "[0.372549 0.619608 0.207843 0.000000]",
    "large_fern_bottom": "[0.372549 0.619608 0.207843 0.000000]",
    "vine": "[0.372549 0.619608 0.207843 0.000000]",
    "lily_pad": "[0.207843 0.552941 0.145098 0.000000]",
    "sugar_cane": "[0.372549 0.619608 0.207843 0.000000]",
    "pumpkin_stem": "[0.372549 0.619608 0.207843 0.000000]",
    "melon_stem": "[0.372549 0.619608 0.207843 0.000000]",
    "attached_pumpkin_stem": "[0.372549 0.619608 0.207843 0.000000]",
    "attached_melon_stem": "[0.372549 0.619608 0.207843 0.000000]",
    "water_still": "[0.247059 0.462745 0.894118 0.000000]",
    "water_flow": "[0.247059 0.462745 0.894118 0.000000]",
    "lava_still": "[1.000000 1.000000 1.000000 0.000000]",
    "lava_flow": "[1.000000 1.000000 1.000000 0.000000]",
}


def get_texture_name(block_name: str) -> str:
    """Get the expected texture filename for a block (ignoring face direction).
    'minecraft:stone' -> 'stone'
    'minecraft:magma_block' -> 'magma'
    'minecraft:water' -> 'water_still'
    """
    base = get_block_base_name(block_name)
    if base.startswith("minecraft:"):
        short = base[len("minecraft:"):]
    else:
        short = base
    # Check if this block has a different texture name than its block name
    return TEXTURE_REMAP.get(short, short)


def get_texture_name_for_face(block_name: str, face_dir: str) -> str:
    """Get the texture name for a specific face of a block.
    Handles blocks with different top/side/bottom textures.
    """
    base = get_block_base_name(block_name)
    short = base[len("minecraft:"):] if base.startswith("minecraft:") else base
    if short in FACE_TEXTURE_MAP:
        face_map = FACE_TEXTURE_MAP[short]
        if face_dir in face_map:
            return face_map[face_dir]
    return get_texture_name(block_name)


# Texture names that must always get a translucency mask, regardless of
# whether the alpha channel is fully opaque.  Many of these have hard-coded
# alpha in some packs but should be rendered with translucency in CS2.
FORCED_TRANSLUCENT_TEXTURES: frozenset = frozenset({
    # Nether wart growth stages
    "nether_wart_stage0", "nether_wart_stage1", "nether_wart_stage2",
    # Bamboo
    "bamboo_stage0", "bamboo_stalk", "bamboo_singleleaf", "bamboo_small_leaves",
    "bamboo_large_leaves",
    # Cactus
    "cactus_top", "cactus_side", "cactus_bottom",
    # Kelp / seagrass
    "kelp", "kelp_plant", "seagrass", "tall_seagrass_top", "tall_seagrass_bottom",
    # Grasses and ferns (tall variants have _top/_bottom suffixes)
    "short_grass", "tall_grass_top", "tall_grass_bottom",
    "fern", "large_fern_top", "large_fern_bottom",
    # Other plants
    "vine", "dead_bush", "lily_pad", "sugar_cane",
    # Chorus
    "chorus_plant", "chorus_flower", "chorus_flower_dead",
    # Sweet berry bush
    "sweet_berry_bush_stage0", "sweet_berry_bush_stage1",
    "sweet_berry_bush_stage2", "sweet_berry_bush_stage3",
    # Cave vines
    "cave_vines", "cave_vines_lit", "cave_vines_plant", "cave_vines_plant_lit",
    # Saplings
    "oak_sapling", "spruce_sapling", "birch_sapling", "jungle_sapling",
    "acacia_sapling", "dark_oak_sapling", "cherry_sapling",
    # Flowers
    "dandelion", "poppy", "blue_orchid", "allium", "azure_bluet",
    "red_tulip", "orange_tulip", "white_tulip", "pink_tulip",
    "oxeye_daisy", "cornflower", "lily_of_the_valley", "wither_rose",
    "sunflower_top", "sunflower_bottom", "sunflower_front", "sunflower_back",
    "lilac_top", "lilac_bottom", "rose_bush_top", "rose_bush_bottom",
    "peony_top", "peony_bottom", "torchflower",
    # Crops
    "wheat_stage0", "wheat_stage1", "wheat_stage2", "wheat_stage3",
    "wheat_stage4", "wheat_stage5", "wheat_stage6", "wheat_stage7",
    "carrots_stage0", "carrots_stage1", "carrots_stage2", "carrots_stage3",
    "potatoes_stage0", "potatoes_stage1", "potatoes_stage2", "potatoes_stage3",
    "beetroots_stage0", "beetroots_stage1", "beetroots_stage2", "beetroots_stage3",
    "melon_stem", "pumpkin_stem",
    # Mushrooms
    "brown_mushroom", "red_mushroom",
    # Torches
    "torch", "soul_torch", "redstone_torch", "redstone_torch_off",
    # Rails
    "rail", "rail_corner", "powered_rail", "powered_rail_on",
    "detector_rail", "detector_rail_on", "activator_rail", "activator_rail_on",
    # Ladder
    "ladder",
    # Corals
    "tube_coral", "brain_coral", "bubble_coral", "fire_coral", "horn_coral",
    "dead_tube_coral", "dead_brain_coral", "dead_bubble_coral",
    "dead_fire_coral", "dead_horn_coral",
    "tube_coral_fan", "brain_coral_fan", "bubble_coral_fan",
    "fire_coral_fan", "horn_coral_fan",
    "dead_tube_coral_fan", "dead_brain_coral_fan", "dead_bubble_coral_fan",
    "dead_fire_coral_fan", "dead_horn_coral_fan",
})


def is_forced_translucent(texture_name: str) -> bool:
    """Check if a texture name must always be rendered with translucency."""
    return texture_name in FORCED_TRANSLUCENT_TEXTURES


def get_color_tint(texture_name: str) -> str | None:
    """Get color tint for a texture that needs biome tinting, or None."""
    return TINTED_BLOCKS.get(texture_name)


# Light-emitting blocks with glow strength (0-15 scale, converted to 0-1).  
# Blocks in this dict always get F_SELF_ILLUM with brightness = value/15.
LIGHT_BLOCKS: dict[str, int] = {
    "lava_still": 15,
    "lava_flow": 15,
    "beacon": 15,
    "conduit": 15,
    "end_gateway": 15,
    "end_portal": 15,
    "fire_0": 15,
    "fire_1": 15,
    "fire_2": 15,
    "fire_3": 15,
    "sea_pickle": 15,
    "sea_lantern": 15,
    "shroomlight": 10,
    "campfire_fire": 15,
    "respawn_anchor_top": 15,
    "end_rod": 14,
    "torch": 14,
    "blast_furnace_front_on": 13,
    "furnace_front_on": 13,
    "smoker_front_on": 13,
    "nether_portal": 11,
    "soul_campfire_fire": 10,
    "soul_torch": 10,
    "soul_fire_0": 10,
    "soul_fire_1": 10,
    "redstone_torch": 7,
    "sculk_catalyst_top": 6,
    "amethyst_cluster": 5,
    "large_amethyst_bud": 4,
    "medium_amethyst_bud": 2,
    "small_amethyst_bud": 1,
    "brewing_stand": 1,
    "dragon_egg": 1,
    "end_portal_frame_side": 1,
    "end_portal_frame_top": 1,
    "end_portal_frame_eye": 10,
}


def get_glow_power(texture_name: str) -> float:
    """Return glow power (0.0-1.0) for a light block, or 0.0 if not a light block."""
    short = texture_name[len("minecraft:"):] if texture_name.startswith("minecraft:") else texture_name
    level = LIGHT_BLOCKS.get(short, 0)
    return level / 15.0 if level > 0 else 0.0


def is_self_illuminated(block_name: str) -> bool:
    """Check if block emits light. Works with both block names and texture names."""
    base = block_name.split("[")[0] if "[" in block_name else block_name
    if base in SELF_ILLUMINATED_BLOCKS:
        return True
    # Also check by texture name (e.g. "minecraft:lava_still" -> "lava_still")
    short = base[len("minecraft:"):] if base.startswith("minecraft:") else base
    if short in LIGHT_BLOCKS:
        return True
    return short in _SELF_ILLUMINATED_TEXTURE_NAMES


def is_translucent(block_name: str) -> bool:
    """Check if block is translucent (glass, ice, leaves, etc.)."""
    base = block_name.split("[")[0] if "[" in block_name else block_name
    return base in TRANSPARENT_BLOCKS


# Liquid blocks that may be wrapped as entities (func_water / trigger_hurt)
LIQUID_BLOCKS = frozenset({
    "minecraft:water",
    "minecraft:lava",
})


def is_liquid(block_name: str) -> bool:
    """Check if block is a liquid (water or lava)."""
    base = block_name.split("[")[0] if "[" in block_name else block_name
    return base in LIQUID_BLOCKS


def is_waterlogged(block_name: str) -> bool:
    """Check if a block state has waterlogged=true."""
    if "[" not in block_name:
        return False
    props = block_name.split("[")[1].rstrip("]")
    for prop in props.split(","):
        if prop.strip() == "waterlogged=true":
            return True
    return False


# Solid blocks that should also generate a trigger_hurt volume
DAMAGE_BLOCKS = frozenset({
    "minecraft:magma_block",
    "minecraft:cactus",
    "minecraft:wither_rose",
    "minecraft:sweet_berry_bush",
    "minecraft:campfire",
    "minecraft:soul_campfire",
    "minecraft:pointed_dripstone",
})


def is_damage_block(block_name: str) -> bool:
    """Check if block should additionally generate a trigger_hurt volume."""
    base = block_name.split("[")[0] if "[" in block_name else block_name
    return base in DAMAGE_BLOCKS


# Blocks that should be climbable (generate invisible ladder mesh)
CLIMBABLE_BLOCKS = frozenset({
    "minecraft:ladder",
    "minecraft:vine",
    "minecraft:cave_vines", "minecraft:cave_vines_plant",
    "minecraft:twisting_vines", "minecraft:twisting_vines_plant",
    "minecraft:weeping_vines", "minecraft:weeping_vines_plant",
})


def is_climbable_block(block_name: str) -> bool:
    """Check if block should generate an invisible climbable ladder mesh."""
    base = block_name.split("[")[0] if "[" in block_name else block_name
    return base in CLIMBABLE_BLOCKS


# Leaf blocks (disable same-type face culling for transparency)
LEAF_BLOCKS = frozenset({
    "minecraft:oak_leaves", "minecraft:spruce_leaves", "minecraft:birch_leaves",
    "minecraft:jungle_leaves", "minecraft:acacia_leaves", "minecraft:dark_oak_leaves",
    "minecraft:mangrove_leaves", "minecraft:cherry_leaves", "minecraft:azalea_leaves",
    "minecraft:flowering_azalea_leaves", "minecraft:pale_oak_leaves",
})


def is_leaf_block(block_name: str) -> bool:
    """Check if block is a leaf block (needs no same-type face culling)."""
    base = block_name.split("[")[0] if "[" in block_name else block_name
    return base in LEAF_BLOCKS


def is_stair_block(block_name: str) -> bool:
    """Check if block is a stair block (for clip ramp generation)."""
    base = block_name.split("[")[0] if "[" in block_name else block_name
    return base.endswith("_stairs")


def is_slab_block(block_name: str) -> bool:
    """Check if block is a slab block (for clip ramp generation)."""
    base = block_name.split("[")[0] if "[" in block_name else block_name
    return base.endswith("_slab")


def is_half_height_block(block_name: str) -> bool:
    """Check if block is a half-height block that should get walk-up ramps.
    Includes slabs (bottom type) and daylight detectors."""
    base = block_name.split("[")[0] if "[" in block_name else block_name
    if base.endswith("_slab"):
        return True
    if base == "minecraft:daylight_detector":
        return True
    return False


# Slime blocks that should bounce players
SLIME_BLOCKS = frozenset({
    "minecraft:slime_block",
})


def is_slime_block(block_name: str) -> bool:
    """Check if block is a slime block (should bounce players)."""
    base = block_name.split("[")[0] if "[" in block_name else block_name
    return base in SLIME_BLOCKS


# Model blocks that are physically non-solid (pass-through, no collision).
# Everything in MODEL_BLOCKS that is NOT in this set is treated as solid.
_NON_SOLID_MODEL_BLOCKS = frozenset({
    # Flowers and plants
    "minecraft:dandelion", "minecraft:poppy", "minecraft:blue_orchid",
    "minecraft:allium", "minecraft:azure_bluet", "minecraft:red_tulip",
    "minecraft:orange_tulip", "minecraft:white_tulip", "minecraft:pink_tulip",
    "minecraft:oxeye_daisy", "minecraft:cornflower", "minecraft:lily_of_the_valley",
    "minecraft:wither_rose", "minecraft:sunflower", "minecraft:lilac",
    "minecraft:rose_bush", "minecraft:peony", "minecraft:torchflower",
    "minecraft:pitcher_plant",
    "minecraft:tall_grass", "minecraft:short_grass", "minecraft:fern", "minecraft:large_fern",
    "minecraft:dead_bush",
    # Torches
    "minecraft:torch", "minecraft:wall_torch",
    "minecraft:soul_torch", "minecraft:soul_wall_torch",
    "minecraft:redstone_torch", "minecraft:redstone_wall_torch",
    # Rails
    "minecraft:rail", "minecraft:powered_rail", "minecraft:detector_rail", "minecraft:activator_rail",
    # Crops
    "minecraft:wheat", "minecraft:carrots", "minecraft:potatoes", "minecraft:beetroots",
    "minecraft:nether_wart", "minecraft:sweet_berry_bush", "minecraft:cocoa",
    "minecraft:melon_stem", "minecraft:pumpkin_stem",
    "minecraft:attached_melon_stem", "minecraft:attached_pumpkin_stem",
    "minecraft:torchflower_crop", "minecraft:pitcher_crop",
    # Buttons and pressure plates
    "minecraft:button", "minecraft:stone_button",
    "minecraft:oak_button", "minecraft:spruce_button", "minecraft:birch_button",
    "minecraft:jungle_button", "minecraft:acacia_button", "minecraft:dark_oak_button",
    "minecraft:crimson_button", "minecraft:warped_button",
    "minecraft:mangrove_button", "minecraft:cherry_button", "minecraft:bamboo_button",
    "minecraft:polished_blackstone_button",
    "minecraft:pressure_plate", "minecraft:stone_pressure_plate",
    "minecraft:oak_pressure_plate", "minecraft:spruce_pressure_plate",
    "minecraft:birch_pressure_plate", "minecraft:jungle_pressure_plate",
    "minecraft:acacia_pressure_plate", "minecraft:dark_oak_pressure_plate",
    "minecraft:crimson_pressure_plate", "minecraft:warped_pressure_plate",
    "minecraft:light_weighted_pressure_plate", "minecraft:heavy_weighted_pressure_plate",
    "minecraft:mangrove_pressure_plate", "minecraft:cherry_pressure_plate",
    "minecraft:bamboo_pressure_plate",
    "minecraft:polished_blackstone_pressure_plate",
    # Saplings
    "minecraft:oak_sapling", "minecraft:spruce_sapling", "minecraft:birch_sapling",
    "minecraft:jungle_sapling", "minecraft:acacia_sapling", "minecraft:dark_oak_sapling",
    "minecraft:cherry_sapling", "minecraft:pale_oak_sapling", "minecraft:bamboo_sapling",
    # Mushrooms
    "minecraft:brown_mushroom", "minecraft:red_mushroom",
    # Vines/corals/seagrass
    "minecraft:vine", "minecraft:glow_lichen",
    "minecraft:cave_vines", "minecraft:cave_vines_plant",
    "minecraft:twisting_vines", "minecraft:twisting_vines_plant",
    "minecraft:weeping_vines", "minecraft:weeping_vines_plant",
    "minecraft:seagrass", "minecraft:tall_seagrass",
    "minecraft:kelp", "minecraft:kelp_plant",
    # Misc pass-through
    "minecraft:sugar_cane",
    "minecraft:flower_pot",
    "minecraft:ladder",
    "minecraft:sea_pickle",
    # Coral fans
    "minecraft:tube_coral", "minecraft:brain_coral", "minecraft:bubble_coral",
    "minecraft:fire_coral", "minecraft:horn_coral",
    "minecraft:dead_tube_coral", "minecraft:dead_brain_coral", "minecraft:dead_bubble_coral",
    "minecraft:dead_fire_coral", "minecraft:dead_horn_coral",
    "minecraft:tube_coral_fan", "minecraft:brain_coral_fan", "minecraft:bubble_coral_fan",
    "minecraft:fire_coral_fan", "minecraft:horn_coral_fan",
    "minecraft:dead_tube_coral_fan", "minecraft:dead_brain_coral_fan",
    "minecraft:dead_bubble_coral_fan", "minecraft:dead_fire_coral_fan",
    "minecraft:dead_horn_coral_fan",
    "minecraft:tube_coral_wall_fan", "minecraft:brain_coral_wall_fan",
    "minecraft:bubble_coral_wall_fan", "minecraft:fire_coral_wall_fan",
    "minecraft:horn_coral_wall_fan",
    "minecraft:dead_tube_coral_wall_fan", "minecraft:dead_brain_coral_wall_fan",
    "minecraft:dead_bubble_coral_wall_fan", "minecraft:dead_fire_coral_wall_fan",
    "minecraft:dead_horn_coral_wall_fan",
})


def is_non_solid_model(block_name: str) -> bool:
    """Check if a model block is physically non-solid (pass-through)."""
    base = block_name.split("[")[0] if "[" in block_name else block_name
    return base in _NON_SOLID_MODEL_BLOCKS
