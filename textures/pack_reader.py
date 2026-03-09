"""Minecraft resource/texture pack reader with animation detection.

Supports Java Edition resource packs (.zip) and Bedrock Edition resource
packs (.mcpack / folder with manifest.json).  Bedrock packs also load PBR
textures: MER (Metalness/Emissive/Roughness) and heightmap images.
"""

import io
import os
import json
import re
import zipfile
from PIL import Image


# Bedrock PBR suffixes to skip when scanning for *colour* textures
_BEDROCK_SKIP_RE = re.compile(r"(_mer|_heightmap|_normal|_s|_n|_e)$", re.I)

# These texture names legitimately end with a PBR-like suffix but are NOT PBR
# data — they must pass through the skip filter unharmed.
_BEDROCK_NOT_PBR: frozenset[str] = frozenset({
    "rail_normal", "rail_normal_turned",
    "sandstone_normal", "red_sandstone_normal",
    "piston_top_normal",
})

# Bedrock block-texture name → Java name (common renames)
_BEDROCK_TO_JAVA: dict[str, str] = {
    # Grass
    "grass_top": "grass_block_top",
    "grass_side": "grass_block_side",
    "grass_side_snowed": "grass_block_snow",
    "grass_side_carried": "grass_block_side",
    "grass_carried": "grass_block_top",
    "grass_path_top": "dirt_path_top",
    "grass_path_side": "dirt_path_side",
    "tallgrass": "short_grass",
    "double_plant_grass_bottom": "tall_grass_bottom",
    "double_plant_grass_top": "tall_grass_top",
    "double_plant_fern_bottom": "large_fern_bottom",
    "double_plant_fern_top": "large_fern_top",
    "double_plant_sunflower_bottom": "sunflower_bottom",
    "double_plant_sunflower_top": "sunflower_top",
    "double_plant_sunflower_front": "sunflower_front",
    "double_plant_sunflower_back": "sunflower_back",
    "double_plant_syringa_bottom": "lilac_bottom",
    "double_plant_syringa_top": "lilac_top",
    "double_plant_rose_bottom": "rose_bush_bottom",
    "double_plant_rose_top": "rose_bush_top",
    "double_plant_paeonia_bottom": "peony_bottom",
    "double_plant_paeonia_top": "peony_top",
    # Water / lava
    "water_still_grey": "water_still",
    "water_flow_grey": "water_flow",
    "lava_still": "lava_still",
    "lava_flow": "lava_flow",
    "waterlily": "lily_pad",
    # Stone / brick renames
    "brick": "bricks",
    "furnace_front_off": "furnace_front",
    "stonebrick": "stone_bricks",
    "stonebrick_mossy": "mossy_stone_bricks",
    "stonebrick_cracked": "cracked_stone_bricks",
    "stonebrick_carved": "chiseled_stone_bricks",
    "cobblestone_mossy": "mossy_cobblestone",
    "nether_brick": "nether_bricks",
    "red_nether_brick": "red_nether_bricks",
    "end_bricks": "end_stone_bricks",
    "prismarine_rough": "prismarine",
    "prismarine_dark": "dark_prismarine",
    "hardened_clay": "terracotta",
    # Sandstone / quartz
    "sandstone_carved": "chiseled_sandstone",
    "sandstone_smooth": "cut_sandstone",
    "red_sandstone_carved": "chiseled_red_sandstone",
    "red_sandstone_smooth": "cut_red_sandstone",
    "quartz_block_chiseled": "chiseled_quartz_block",
    "quartz_block_chiseled_top": "chiseled_quartz_block_top",
    "quartz_block_lines": "quartz_pillar",
    "quartz_block_lines_top": "quartz_pillar_top",
    "quartz_block_bottom": "quartz_block_bottom",
    "quartz_block_side": "quartz_block_side",
    "quartz_block_top": "quartz_block_top",
    # Leaves
    "leaves_oak": "oak_leaves", "leaves_spruce": "spruce_leaves",
    "leaves_birch": "birch_leaves", "leaves_jungle": "jungle_leaves",
    "leaves_acacia": "acacia_leaves", "leaves_big_oak": "dark_oak_leaves",
    # Logs
    "log_oak": "oak_log", "log_spruce": "spruce_log",
    "log_birch": "birch_log", "log_jungle": "jungle_log",
    "log_acacia": "acacia_log", "log_big_oak": "dark_oak_log",
    "log_oak_top": "oak_log_top", "log_spruce_top": "spruce_log_top",
    "log_birch_top": "birch_log_top", "log_jungle_top": "jungle_log_top",
    "log_acacia_top": "acacia_log_top", "log_big_oak_top": "dark_oak_log_top",
    # Stripped logs
    "stripped_oak_log_side": "stripped_oak_log",
    "stripped_spruce_log_side": "stripped_spruce_log",
    "stripped_birch_log_side": "stripped_birch_log",
    "stripped_jungle_log_side": "stripped_jungle_log",
    "stripped_acacia_log_side": "stripped_acacia_log",
    "stripped_dark_oak_log_side": "stripped_dark_oak_log",
    "stripped_oak_log_top": "stripped_oak_log_top",
    "stripped_spruce_log_top": "stripped_spruce_log_top",
    "stripped_birch_log_top": "stripped_birch_log_top",
    "stripped_jungle_log_top": "stripped_jungle_log_top",
    "stripped_acacia_log_top": "stripped_acacia_log_top",
    "stripped_dark_oak_log_top": "stripped_dark_oak_log_top",
    # Planks
    "planks_oak": "oak_planks", "planks_spruce": "spruce_planks",
    "planks_birch": "birch_planks", "planks_jungle": "jungle_planks",
    "planks_acacia": "acacia_planks", "planks_big_oak": "dark_oak_planks",
    # Doors
    "door_oak_lower": "oak_door_bottom", "door_oak_upper": "oak_door_top",
    "door_spruce_lower": "spruce_door_bottom", "door_spruce_upper": "spruce_door_top",
    "door_birch_lower": "birch_door_bottom", "door_birch_upper": "birch_door_top",
    "door_jungle_lower": "jungle_door_bottom", "door_jungle_upper": "jungle_door_top",
    "door_acacia_lower": "acacia_door_bottom", "door_acacia_upper": "acacia_door_top",
    "door_dark_oak_lower": "dark_oak_door_bottom", "door_dark_oak_upper": "dark_oak_door_top",
    "door_iron_lower": "iron_door_bottom", "door_iron_upper": "iron_door_top",
    # Trapdoors
    "trapdoor": "oak_trapdoor",
    "spruce_trapdoor": "spruce_trapdoor",
    "birch_trapdoor": "birch_trapdoor",
    "jungle_trapdoor": "jungle_trapdoor",
    "acacia_trapdoor": "acacia_trapdoor",
    "dark_oak_trapdoor": "dark_oak_trapdoor",
    "iron_trapdoor": "iron_trapdoor",
    # Plants
    "deadbush": "dead_bush",
    "fern": "fern",
    "sapling_oak": "oak_sapling", "sapling_spruce": "spruce_sapling",
    "sapling_birch": "birch_sapling", "sapling_jungle": "jungle_sapling",
    "sapling_acacia": "acacia_sapling", "sapling_roofed_oak": "dark_oak_sapling",
    # Flowers
    "flower_dandelion": "dandelion", "flower_rose": "poppy",
    "flower_blue_orchid": "blue_orchid", "flower_allium": "allium",
    "flower_houstonia": "azure_bluet",
    "flower_tulip_red": "red_tulip", "flower_tulip_orange": "orange_tulip",
    "flower_tulip_white": "white_tulip", "flower_tulip_pink": "pink_tulip",
    "flower_oxeye_daisy": "oxeye_daisy", "flower_cornflower": "cornflower",
    "flower_lily_of_the_valley": "lily_of_the_valley",
    # Mushrooms / nether
    "mushroom_red": "red_mushroom", "mushroom_brown": "brown_mushroom",
    "mushroom_red_block": "red_mushroom_block",
    "mushroom_brown_block": "brown_mushroom_block",
    "mushroom_block_inside": "mushroom_block_inside",
    "mushroom_block_skin_brown": "brown_mushroom_block",
    "mushroom_block_skin_red": "red_mushroom_block",
    "mushroom_block_skin_stem": "mushroom_stem",
    # Nether
    "soul_fire_0": "soul_fire_0",
    "soul_fire_1": "soul_fire_1",
    "soul_sand": "soul_sand",
    "soul_soil": "soul_soil",
    "nether_wart_stage_0": "nether_wart_stage0",
    "nether_wart_stage_1": "nether_wart_stage1",
    "nether_wart_stage_2": "nether_wart_stage2",
    # Redstone
    "piston_top": "piston_top",
    "piston_side": "piston_side",
    "piston_bottom": "piston_bottom",
    "piston_top_sticky": "piston_top_sticky",
    "piston_inner": "piston_inner",
    "redstone_dust_cross": "redstone_dust_dot",
    "redstone_dust_line": "redstone_dust_line0",
    "repeater": "repeater",
    "observer_front": "observer_front",
    "observer_back": "observer_back",
    "observer_side": "observer_side",
    "observer_top": "observer_top",
    # Misc renames
    "torch_on": "torch", "soul_torch": "soul_torch",
    "redstone_torch_on": "redstone_torch",
    "redstone_torch_off": "redstone_torch_off",
    "melon_side": "melon_side", "melon_top": "melon_top",
    "pumpkin_side": "pumpkin_side", "pumpkin_top": "pumpkin_top",
    "pumpkin_face_off": "carved_pumpkin",
    "pumpkin_face_on": "jack_o_lantern",
    "web": "cobweb",
    "hay_block_side": "hay_block_side", "hay_block_top": "hay_block_top",
    "iron_bars": "iron_bars",
    "rail_normal": "rail", "rail_normal_turned": "rail_corner",
    "rail_golden": "powered_rail", "rail_golden_powered": "powered_rail_on",
    "rail_detector": "detector_rail", "rail_detector_powered": "detector_rail_on",
    "rail_activator": "activator_rail", "rail_activator_powered": "activator_rail_on",
    "cauldron_inner": "cauldron_inner", "cauldron_side": "cauldron_side",
    "cauldron_bottom": "cauldron_bottom", "cauldron_top": "cauldron_top",
    "anvil_base": "anvil", "anvil_top_damaged_0": "anvil_top",
    "anvil_top_damaged_1": "chipped_anvil_top",
    "anvil_top_damaged_2": "damaged_anvil_top",
    "mob_spawner": "spawner",
    "itemframe_background": "item_frame",
    "trip_wire_source": "tripwire_hook", "trip_wire": "tripwire",
    "flower_pot": "flower_pot",
    "brewing_stand": "brewing_stand",
    "brewing_stand_base": "brewing_stand_base",
    "enchanting_table_bottom": "enchanting_table_bottom",
    "enchanting_table_side": "enchanting_table_side",
    "enchanting_table_top": "enchanting_table_top",
    "dragon_egg": "dragon_egg",
    "end_rod": "end_rod",
    "chorus_plant": "chorus_plant",
    "chorus_flower": "chorus_flower",
    "chorus_flower_dead": "chorus_flower_dead",
    "frosted_ice_0": "frosted_ice_0",
    "frosted_ice_1": "frosted_ice_1",
    "frosted_ice_2": "frosted_ice_2",
    "frosted_ice_3": "frosted_ice_3",
    "kelp_a": "kelp", "kelp_b": "kelp", "kelp_c": "kelp", "kelp_d": "kelp",
    "kelp_top": "kelp", "kelp_plant": "kelp_plant",
    "seagrass": "seagrass",
    "sea_pickle": "sea_pickle",
    "conduit": "conduit",
    "bamboo_leaf": "bamboo_large_leaves",
    "bamboo_sapling": "bamboo_stage0",
    "bamboo_singleleaf": "bamboo_singleleaf",
    "bamboo_small_leaves": "bamboo_small_leaves",
    "bamboo_stem": "bamboo_stalk",
    "scaffolding_top": "scaffolding_top",
    "scaffolding_side": "scaffolding_side",
    "scaffolding_bottom": "scaffolding_bottom",
    # Stained hardened clay → terracotta
    "hardened_clay_stained_white": "white_terracotta",
    "hardened_clay_stained_orange": "orange_terracotta",
    "hardened_clay_stained_magenta": "magenta_terracotta",
    "hardened_clay_stained_light_blue": "light_blue_terracotta",
    "hardened_clay_stained_yellow": "yellow_terracotta",
    "hardened_clay_stained_lime": "lime_terracotta",
    "hardened_clay_stained_pink": "pink_terracotta",
    "hardened_clay_stained_gray": "gray_terracotta",
    "hardened_clay_stained_silver": "light_gray_terracotta",
    "hardened_clay_stained_cyan": "cyan_terracotta",
    "hardened_clay_stained_purple": "purple_terracotta",
    "hardened_clay_stained_blue": "blue_terracotta",
    "hardened_clay_stained_brown": "brown_terracotta",
    "hardened_clay_stained_green": "green_terracotta",
    "hardened_clay_stained_red": "red_terracotta",
    "hardened_clay_stained_black": "black_terracotta",
    # Ore / mineral renames
    "coal_ore": "coal_ore", "iron_ore": "iron_ore",
    "gold_ore": "gold_ore", "diamond_ore": "diamond_ore",
    "emerald_ore": "emerald_ore", "lapis_ore": "lapis_ore",
    "redstone_ore": "redstone_ore", "quartz_ore": "nether_quartz_ore",
    "gold_block": "gold_block", "iron_block": "iron_block",
    "diamond_block": "diamond_block", "emerald_block": "emerald_block",
    "lapis_block": "lapis_block", "redstone_block": "redstone_block",
    "coal_block": "coal_block",
    "sponge": "sponge", "wet_sponge": "wet_sponge",
    # Copper
    "copper_block": "copper_block",
    "exposed_copper": "exposed_copper",
    "weathered_copper": "weathered_copper",
    "oxidized_copper": "oxidized_copper",
    "cut_copper": "cut_copper",
    "exposed_cut_copper": "exposed_cut_copper",
    "weathered_cut_copper": "weathered_cut_copper",
    "oxidized_cut_copper": "oxidized_cut_copper",
    # Door renames (Bedrock uses door_wood for oak)
    "door_wood_lower": "oak_door_bottom", "door_wood_upper": "oak_door_top",
    # Noteblock / jukebox
    "noteblock": "note_block",
    # Glass pane top colours
    "glass_pane_top": "glass_pane_top",
    # Leaves (opaque variants → same as transparent)
    "leaves_oak_opaque": "oak_leaves",
    "leaves_spruce_opaque": "spruce_leaves",
    "leaves_birch_opaque": "birch_leaves",
    "leaves_jungle_opaque": "jungle_leaves",
    "leaves_acacia_opaque": "acacia_leaves",
    "leaves_big_oak_opaque": "dark_oak_leaves",
    "azalea_leaves_opaque": "azalea_leaves",
    "azalea_leaves_flowers_opaque": "flowering_azalea_leaves",
    "azalea_leaves_flowers": "flowering_azalea_leaves",
    "mangrove_leaves_opaque": "mangrove_leaves",
    "cherry_leaves_opaque": "cherry_leaves",
    "pale_oak_leaves_opaque": "pale_oak_leaves",
    # Misc blocks
    "reeds": "sugar_cane",
    "bush": "sweet_berry_bush_stage3",
    "fire_0": "fire_0", "fire_1": "fire_1",
    "portal": "nether_portal",
    "sea_lantern": "sea_lantern",
    "glowstone": "glowstone",
    "redstone_lamp_on": "redstone_lamp_on",
    "redstone_lamp_off": "redstone_lamp",
    "stone_slab_side": "smooth_stone_slab_side",
    "stone_slab_top": "smooth_stone",
    "ice_packed": "packed_ice",
    "blue_ice": "blue_ice",
    "comparator_off": "comparator", "comparator_on": "comparator_on",
    "repeater_off": "repeater", "repeater_on": "repeater_on",
    # Deepslate subdirectory textures
    "deepslate": "deepslate",
    "deepslate_top": "deepslate_top",
    "cobbled_deepslate": "cobbled_deepslate",
    "polished_deepslate": "polished_deepslate",
    "deepslate_bricks": "deepslate_bricks",
    "cracked_deepslate_bricks": "cracked_deepslate_bricks",
    "deepslate_tiles": "deepslate_tiles",
    "cracked_deepslate_tiles": "cracked_deepslate_tiles",
    "chiseled_deepslate": "chiseled_deepslate",
    "deepslate_coal_ore": "deepslate_coal_ore",
    "deepslate_iron_ore": "deepslate_iron_ore",
    "deepslate_copper_ore": "deepslate_copper_ore",
    "deepslate_gold_ore": "deepslate_gold_ore",
    "deepslate_diamond_ore": "deepslate_diamond_ore",
    "deepslate_emerald_ore": "deepslate_emerald_ore",
    "deepslate_lapis_ore": "deepslate_lapis_ore",
    "deepslate_redstone_ore": "deepslate_redstone_ore",
    # Huge fungus subdirectory textures (crimson / warped wood)
    "crimson_log_side": "crimson_stem",
    "crimson_log_top": "crimson_stem_top",
    "crimson_door_lower": "crimson_door_bottom",
    "crimson_door_top": "crimson_door_top",
    "crimson_planks": "crimson_planks",
    "crimson_trapdoor": "crimson_trapdoor",
    "stripped_crimson_stem_side": "stripped_crimson_stem",
    "stripped_crimson_stem_top": "stripped_crimson_stem_top",
    "warped_stem_side": "warped_stem",
    "warped_stem_top": "warped_stem_top",
    "warped_door_lower": "warped_door_bottom",
    "warped_door_top": "warped_door_top",
    "warped_planks": "warped_planks",
    "warped_trapdoor": "warped_trapdoor",
    "stripped_warped_stem_side": "stripped_warped_stem",
    "stripped_warped_stem_top": "stripped_warped_stem_top",
    # Cherry / Mangrove / Pale Oak / Bamboo logs
    "cherry_log_side": "cherry_log",
    "cherry_log_top": "cherry_log_top",
    "stripped_cherry_log_side": "stripped_cherry_log",
    "stripped_cherry_log_top": "stripped_cherry_log_top",
    "mangrove_log_side": "mangrove_log",
    "mangrove_log_top": "mangrove_log_top",
    "stripped_mangrove_log_side": "stripped_mangrove_log",
    "stripped_mangrove_log_top": "stripped_mangrove_log_top",
    "pale_oak_log_side": "pale_oak_log",
    "pale_oak_log_top": "pale_oak_log_top",
    "stripped_pale_oak_log_side": "stripped_pale_oak_log",
    "stripped_pale_oak_log_top": "stripped_pale_oak_log_top",
    # Stone variants
    "stone_andesite": "andesite",
    "stone_andesite_smooth": "polished_andesite",
    "stone_diorite": "diorite",
    "stone_diorite_smooth": "polished_diorite",
    "stone_granite": "granite",
    "stone_granite_smooth": "polished_granite",
    # Glass pane top colour variants
    "glass_pane_top_black": "black_stained_glass_pane_top",
    "glass_pane_top_blue": "blue_stained_glass_pane_top",
    "glass_pane_top_brown": "brown_stained_glass_pane_top",
    "glass_pane_top_cyan": "cyan_stained_glass_pane_top",
    "glass_pane_top_gray": "gray_stained_glass_pane_top",
    "glass_pane_top_green": "green_stained_glass_pane_top",
    "glass_pane_top_light_blue": "light_blue_stained_glass_pane_top",
    "glass_pane_top_lime": "lime_stained_glass_pane_top",
    "glass_pane_top_magenta": "magenta_stained_glass_pane_top",
    "glass_pane_top_orange": "orange_stained_glass_pane_top",
    "glass_pane_top_pink": "pink_stained_glass_pane_top",
    "glass_pane_top_purple": "purple_stained_glass_pane_top",
    "glass_pane_top_red": "red_stained_glass_pane_top",
    "glass_pane_top_silver": "light_gray_stained_glass_pane_top",
    "glass_pane_top_white": "white_stained_glass_pane_top",
    "glass_pane_top_yellow": "yellow_stained_glass_pane_top",
    # Stained glass (base names)
    "glass": "glass",
    "glass_black": "black_stained_glass",
    "glass_blue": "blue_stained_glass",
    "glass_brown": "brown_stained_glass",
    "glass_cyan": "cyan_stained_glass",
    "glass_gray": "gray_stained_glass",
    "glass_green": "green_stained_glass",
    "glass_light_blue": "light_blue_stained_glass",
    "glass_lime": "lime_stained_glass",
    "glass_magenta": "magenta_stained_glass",
    "glass_orange": "orange_stained_glass",
    "glass_pink": "pink_stained_glass",
    "glass_purple": "purple_stained_glass",
    "glass_red": "red_stained_glass",
    "glass_silver": "light_gray_stained_glass",
    "glass_white": "white_stained_glass",
    "glass_yellow": "yellow_stained_glass",
    # Dirt path
    "dirt_podzol_side": "podzol_side",
    "dirt_podzol_top": "podzol_top",
    # Misc
    "sponge_wet": "wet_sponge",
    "flower_rose_blue": "wither_rose",
    "flower_wither_rose": "wither_rose",
    "flower_paeonia": "peony",
    # ── Crop stages: Bedrock uses underscore before number ──
    "beetroots_stage_0": "beetroots_stage0",
    "beetroots_stage_1": "beetroots_stage1",
    "beetroots_stage_2": "beetroots_stage2",
    "beetroots_stage_3": "beetroots_stage3",
    "carrots_stage_0": "carrots_stage0",
    "carrots_stage_1": "carrots_stage1",
    "carrots_stage_2": "carrots_stage2",
    "carrots_stage_3": "carrots_stage3",
    "potatoes_stage_0": "potatoes_stage0",
    "potatoes_stage_1": "potatoes_stage1",
    "potatoes_stage_2": "potatoes_stage2",
    "potatoes_stage_3": "potatoes_stage3",
    "cocoa_stage_0": "cocoa_stage0",
    "cocoa_stage_1": "cocoa_stage1",
    "cocoa_stage_2": "cocoa_stage2",
    "wheat_stage_0": "wheat_stage0",
    "wheat_stage_1": "wheat_stage1",
    "wheat_stage_2": "wheat_stage2",
    "wheat_stage_3": "wheat_stage3",
    "wheat_stage_4": "wheat_stage4",
    "wheat_stage_5": "wheat_stage5",
    "wheat_stage_6": "wheat_stage6",
    "wheat_stage_7": "wheat_stage7",
    "torchflower_crop_stage_0": "torchflower_crop_stage0",
    "torchflower_crop_stage_1": "torchflower_crop_stage1",
    "pitcher_crop_bottom_stage_1": "pitcher_crop_bottom_stage1",
    "pitcher_crop_bottom_stage_2": "pitcher_crop_bottom_stage2",
    "pitcher_crop_bottom_stage_3": "pitcher_crop_bottom_stage3",
    "pitcher_crop_bottom_stage_4": "pitcher_crop_bottom_stage4",
    "pitcher_crop_top_stage_3": "pitcher_crop_top_stage3",
    "pitcher_crop_top_stage_4": "pitcher_crop_top_stage4",
    "sweet_berry_bush_stage0": "sweet_berry_bush_stage0",
    "sweet_berry_bush_stage1": "sweet_berry_bush_stage1",
    "sweet_berry_bush_stage2": "sweet_berry_bush_stage2",
    "sweet_berry_bush_stage3": "sweet_berry_bush_stage3",
    # ── Furnace / smoker / blast furnace off-state ──
    "blast_furnace_front_off": "blast_furnace_front",
    "smoker_front_off": "smoker_front",
    # ── Slime ──
    "slime": "slime_block",
    # ── End portal frame ──
    "endframe_eye": "end_portal_frame_eye",
    "endframe_side": "end_portal_frame_side",
    "endframe_top": "end_portal_frame_top",
    # ── Sandstone default side ──
    "sandstone_normal": "sandstone",
    "red_sandstone_normal": "red_sandstone",
    # ── Farmland ──
    "farmland_dry": "farmland",
    "farmland_wet": "farmland_moist",
    # ── Corals: Bedrock color names → Java type names ──
    "coral_blue": "tube_coral_block",
    "coral_blue_dead": "dead_tube_coral_block",
    "coral_pink": "brain_coral_block",
    "coral_pink_dead": "dead_brain_coral_block",
    "coral_purple": "bubble_coral_block",
    "coral_purple_dead": "dead_bubble_coral_block",
    "coral_red": "fire_coral_block",
    "coral_red_dead": "dead_fire_coral_block",
    "coral_yellow": "horn_coral_block",
    "coral_yellow_dead": "dead_horn_coral_block",
    "coral_fan_blue": "tube_coral_fan",
    "coral_fan_blue_dead": "dead_tube_coral_fan",
    "coral_fan_pink": "brain_coral_fan",
    "coral_fan_pink_dead": "dead_brain_coral_fan",
    "coral_fan_purple": "bubble_coral_fan",
    "coral_fan_purple_dead": "dead_bubble_coral_fan",
    "coral_fan_red": "fire_coral_fan",
    "coral_fan_red_dead": "dead_fire_coral_fan",
    "coral_fan_yellow": "horn_coral_fan",
    "coral_fan_yellow_dead": "dead_horn_coral_fan",
    "coral_plant_blue": "tube_coral",
    "coral_plant_blue_dead": "dead_tube_coral",
    "coral_plant_pink": "brain_coral",
    "coral_plant_pink_dead": "dead_brain_coral",
    "coral_plant_purple": "bubble_coral",
    "coral_plant_purple_dead": "dead_bubble_coral",
    "coral_plant_red": "fire_coral",
    "coral_plant_red_dead": "dead_fire_coral",
    "coral_plant_yellow": "horn_coral",
    "coral_plant_yellow_dead": "dead_horn_coral",
    # ── Stonecutter (Bedrock: stonecutter2 for the new one) ──
    "stonecutter2_bottom": "stonecutter_bottom",
    "stonecutter2_saw": "stonecutter_saw",
    "stonecutter2_side": "stonecutter_side",
    "stonecutter2_top": "stonecutter_top",
    # ── Lectern sides (Java singular) ──
    "lectern_sides": "lectern_side",
    # ── Dispenser / dropper ──
    "dispenser_front_horizontal": "dispenser_front",
    "dropper_front_horizontal": "dropper_front",
    "dispenser_front_vertical": "dispenser_front_vertical",
    "dropper_front_vertical": "dropper_front_vertical",
    # ── Melon / pumpkin stems ──
    "melon_stem_connected": "attached_melon_stem",
    "melon_stem_disconnected": "melon_stem",
    "pumpkin_stem_connected": "attached_pumpkin_stem",
    "pumpkin_stem_disconnected": "pumpkin_stem",
    # ── Dried kelp block ──
    "dried_kelp_side_a": "dried_kelp_side",
    "dried_kelp_side_b": "dried_kelp_side",
    # ── Chain ──
    "chain1": "chain",
    "chain2": "chain",
    # ── Double-tall seagrass ──
    "seagrass_doubletall_bottom_a": "tall_seagrass_bottom",
    "seagrass_doubletall_bottom_b": "tall_seagrass_bottom",
    "seagrass_doubletall_top_a": "tall_seagrass_top",
    "seagrass_doubletall_top_b": "tall_seagrass_top",
    # ── Fletching table ──
    "fletcher_table_side1": "fletching_table_front",
    "fletcher_table_side2": "fletching_table_side",
    "fletcher_table_top": "fletching_table_top",
    # ── Honey block ──
    "honey_bottom": "honey_block_bottom",
    "honey_side": "honey_block_side",
    "honey_top": "honey_block_top",
    # ── Weeping / twisting vines ──
    "weeping_vines_base": "weeping_vines_plant",
    "weeping_vines_bottom": "weeping_vines",
    "twisting_vines_base": "twisting_vines_plant",
    "twisting_vines_bottom": "twisting_vines",
    # ── Cartography table ──
    "cartography_table_side1": "cartography_table_side1",
    "cartography_table_side2": "cartography_table_side2",
    "cartography_table_side3": "cartography_table_side3",
    # ── Bamboo ──
    "bamboo_small_leaf": "bamboo_small_leaves",
    # ── Respawn anchor ──
    "respawn_anchor_side0": "respawn_anchor_side0",
    "respawn_anchor_side1": "respawn_anchor_side1",
    "respawn_anchor_side2": "respawn_anchor_side2",
    "respawn_anchor_side3": "respawn_anchor_side3",
    "respawn_anchor_side4": "respawn_anchor_side4",
    "respawn_anchor_top_off": "respawn_anchor_top",
    # ── Observer ──
    "observer_back_lit": "observer_back_on",
    # ── Froglight ──
    "ochre_froglight_side": "ochre_froglight_side",
    "ochre_froglight_top": "ochre_froglight_top",
    "pearlescent_froglight_side": "pearlescent_froglight_side",
    "pearlescent_froglight_top": "pearlescent_froglight_top",
    "verdant_froglight_side": "verdant_froglight_side",
    "verdant_froglight_top": "verdant_froglight_top",
    # ── Mycelium ──
    "mycelium_side": "mycelium_side",
    "mycelium_top": "mycelium_top",
    # ── Hopper ──
    "hopper_inside": "hopper_inside",
    "hopper_outside": "hopper_outside",
    "hopper_top": "hopper_top",
    # ── Lit redstone ore (Java uses separate texture) ──
    "redstone_ore_lit": "redstone_ore",
    "deepslate_redstone_ore_lit": "deepslate_redstone_ore",
    # ── Copper variants (oxidation stages) ──
    "copper_door_bottom": "copper_door_bottom",
    "copper_door_top": "copper_door_top",
    "copper_trapdoor": "copper_trapdoor",
    "copper_grate": "copper_grate",
    "copper_bulb": "copper_bulb",
    "copper_bulb_lit": "copper_bulb_lit",
    "copper_bulb_powered": "copper_bulb_powered",
    "copper_bulb_lit_powered": "copper_bulb_lit_powered",
    "exposed_copper_door_bottom": "exposed_copper_door_bottom",
    "exposed_copper_door_top": "exposed_copper_door_top",
    "exposed_copper_trapdoor": "exposed_copper_trapdoor",
    "exposed_copper_grate": "exposed_copper_grate",
    "exposed_copper_bulb": "exposed_copper_bulb",
    "exposed_copper_bulb_lit": "exposed_copper_bulb_lit",
    "exposed_copper_bulb_powered": "exposed_copper_bulb_powered",
    "exposed_copper_bulb_lit_powered": "exposed_copper_bulb_lit_powered",
    "weathered_copper_door_bottom": "weathered_copper_door_bottom",
    "weathered_copper_door_top": "weathered_copper_door_top",
    "weathered_copper_trapdoor": "weathered_copper_trapdoor",
    "weathered_copper_grate": "weathered_copper_grate",
    "weathered_copper_bulb": "weathered_copper_bulb",
    "weathered_copper_bulb_lit": "weathered_copper_bulb_lit",
    "weathered_copper_bulb_powered": "weathered_copper_bulb_powered",
    "weathered_copper_bulb_lit_powered": "weathered_copper_bulb_lit_powered",
    "oxidized_copper_door_bottom": "oxidized_copper_door_bottom",
    "oxidized_copper_door_top": "oxidized_copper_door_top",
    "oxidized_copper_trapdoor": "oxidized_copper_trapdoor",
    "oxidized_copper_grate": "oxidized_copper_grate",
    "oxidized_copper_bulb": "oxidized_copper_bulb",
    "oxidized_copper_bulb_lit": "oxidized_copper_bulb_lit",
    "oxidized_copper_bulb_powered": "oxidized_copper_bulb_powered",
    "oxidized_copper_bulb_lit_powered": "oxidized_copper_bulb_lit_powered",
    "chiseled_copper": "chiseled_copper",
    "exposed_chiseled_copper": "exposed_chiseled_copper",
    "weathered_chiseled_copper": "weathered_chiseled_copper",
    "oxidized_chiseled_copper": "oxidized_chiseled_copper",
    # ── Mangrove ──
    "mangrove_door_bottom": "mangrove_door_bottom",
    "mangrove_door_top": "mangrove_door_top",
    "mangrove_trapdoor": "mangrove_trapdoor",
    "mangrove_planks": "mangrove_planks",
    "mangrove_roots_side": "mangrove_roots_side",
    "mangrove_roots_top": "mangrove_roots_top",
    "muddy_mangrove_roots_side": "muddy_mangrove_roots_side",
    "muddy_mangrove_roots_top": "muddy_mangrove_roots_top",
    # ── Cherry ──
    "cherry_door_bottom": "cherry_door_bottom",
    "cherry_door_top": "cherry_door_top",
    "cherry_planks": "cherry_planks",
    "cherry_trapdoor": "cherry_trapdoor",
    "cherry_sapling": "cherry_sapling",
    # ── Pale oak ──
    "pale_oak_door_bottom": "pale_oak_door_bottom",
    "pale_oak_door_top": "pale_oak_door_top",
    "pale_oak_planks": "pale_oak_planks",
    "pale_oak_trapdoor": "pale_oak_trapdoor",
    "pale_oak_sapling": "pale_oak_sapling",
    # ── Bamboo wood ──
    "bamboo_door_bottom": "bamboo_door_bottom",
    "bamboo_door_top": "bamboo_door_top",
    "bamboo_planks": "bamboo_planks",
    "bamboo_trapdoor": "bamboo_trapdoor",
    "bamboo_block": "bamboo_block",
    "bamboo_block_top": "bamboo_block_top",
    "bamboo_mosaic": "bamboo_mosaic",
    "bamboo_fence": "bamboo_fence",
    "bamboo_fence_gate": "bamboo_fence_gate",
    "stripped_bamboo_block": "stripped_bamboo_block",
    "stripped_bamboo_block_top": "stripped_bamboo_block_top",
    # ── Sculk ──
    "sculk": "sculk",
    "sculk_vein": "sculk_vein",
    "sculk_catalyst_bottom": "sculk_catalyst_bottom",
    "sculk_catalyst_side": "sculk_catalyst_side",
    "sculk_catalyst_side_bloom": "sculk_catalyst_side_bloom",
    "sculk_catalyst_top": "sculk_catalyst_top",
    "sculk_catalyst_top_bloom": "sculk_catalyst_top_bloom",
    "sculk_sensor_bottom": "sculk_sensor_bottom",
    "sculk_sensor_side": "sculk_sensor_side",
    "sculk_sensor_top": "sculk_sensor_top",
    "sculk_sensor_tendril_active": "sculk_sensor_tendril_active",
    "sculk_sensor_tendril_inactive": "sculk_sensor_tendril_inactive",
    "sculk_shrieker_bottom": "sculk_shrieker_bottom",
    "sculk_shrieker_side": "sculk_shrieker_side",
    "sculk_shrieker_top": "sculk_shrieker_top",
    "sculk_shrieker_inner_top": "sculk_shrieker_inner_top",
    "sculk_shrieker_can_summon_inner_top": "sculk_shrieker_can_summon_inner_top",
    "calibrated_sculk_sensor_amethyst": "calibrated_sculk_sensor_amethyst",
    "calibrated_sculk_sensor_input_side": "calibrated_sculk_sensor_input_side",
    "calibrated_sculk_sensor_top": "calibrated_sculk_sensor_top",
    # ── Blackstone ──
    "blackstone": "blackstone",
    "blackstone_top": "blackstone_top",
    "polished_blackstone": "polished_blackstone",
    "polished_blackstone_bricks": "polished_blackstone_bricks",
    "cracked_polished_blackstone_bricks": "cracked_polished_blackstone_bricks",
    "chiseled_polished_blackstone": "chiseled_polished_blackstone",
    "gilded_blackstone": "gilded_blackstone",
    # ── Basalt ──
    "basalt_side": "basalt_side",
    "basalt_top": "basalt_top",
    "polished_basalt_side": "polished_basalt_side",
    "polished_basalt_top": "polished_basalt_top",
    "smooth_basalt": "smooth_basalt",
    # ── Nether ──
    "crimson_nylium_side": "crimson_nylium_side",
    "crimson_nylium_top": "crimson_nylium",
    "warped_nylium_side": "warped_nylium_side",
    "warped_nylium_top": "warped_nylium",
    "crimson_fungus": "crimson_fungus",
    "warped_fungus": "warped_fungus",
    "crimson_roots": "crimson_roots",
    "warped_roots": "warped_roots",
    "crimson_roots_pot": "potted_crimson_roots",
    "warped_roots_pot": "potted_warped_roots",
    "nether_sprouts": "nether_sprouts",
    "shroomlight": "shroomlight",
    "warped_wart_block": "warped_wart_block",
    "nether_wart_block": "nether_wart_block",
    "nether_gold_ore": "nether_gold_ore",
    "netherite_block": "netherite_block",
    "netherrack": "netherrack",
    "crying_obsidian": "crying_obsidian",
    "lodestone_side": "lodestone_side",
    "lodestone_top": "lodestone_top",
    # ── Copper chains / lanterns / lightning rods ──
    "copper_chain1": "copper_chain",
    "copper_chain2": "copper_chain",
    "exposed_copper_chain1": "exposed_copper_chain",
    "exposed_copper_chain2": "exposed_copper_chain",
    "weathered_copper_chain1": "weathered_copper_chain",
    "weathered_copper_chain2": "weathered_copper_chain",
    "oxidized_copper_chain1": "oxidized_copper_chain",
    "oxidized_copper_chain2": "oxidized_copper_chain",
    "copper_lantern": "copper_lantern",
    "exposed_copper_lantern": "exposed_copper_lantern",
    "weathered_copper_lantern": "weathered_copper_lantern",
    "oxidized_copper_lantern": "oxidized_copper_lantern",
    "copper_bars": "copper_bars",
    "exposed_copper_bars": "exposed_copper_bars",
    "weathered_copper_bars": "weathered_copper_bars",
    "oxidized_copper_bars": "oxidized_copper_bars",
    "lightning_rod": "lightning_rod",
    "lightning_rod_powered": "lightning_rod_on",
    "exposed_lightning_rod": "exposed_lightning_rod",
    "weathered_lightning_rod": "weathered_lightning_rod",
    "oxidized_lightning_rod": "oxidized_lightning_rod",
    # ── Tuff ──
    "tuff": "tuff",
    "tuff_bricks": "tuff_bricks",
    "chiseled_tuff": "chiseled_tuff",
    "chiseled_tuff_top": "chiseled_tuff_top",
    "chiseled_tuff_bricks": "chiseled_tuff_bricks",
    "chiseled_tuff_bricks_top": "chiseled_tuff_bricks_top",
    "polished_tuff": "polished_tuff",
    # ── Amethyst ──
    "amethyst_block": "amethyst_block",
    "budding_amethyst": "budding_amethyst",
    "amethyst_cluster": "amethyst_cluster",
    "large_amethyst_bud": "large_amethyst_bud",
    "medium_amethyst_bud": "medium_amethyst_bud",
    "small_amethyst_bud": "small_amethyst_bud",
    # ── Dripstone ──
    "dripstone_block": "dripstone_block",
    "pointed_dripstone_down_base": "pointed_dripstone_down_base",
    "pointed_dripstone_down_frustum": "pointed_dripstone_down_frustum",
    "pointed_dripstone_down_merge": "pointed_dripstone_down_merge",
    "pointed_dripstone_down_middle": "pointed_dripstone_down_middle",
    "pointed_dripstone_down_tip": "pointed_dripstone_down_tip",
    "pointed_dripstone_up_base": "pointed_dripstone_up_base",
    "pointed_dripstone_up_frustum": "pointed_dripstone_up_frustum",
    "pointed_dripstone_up_merge": "pointed_dripstone_up_merge",
    "pointed_dripstone_up_middle": "pointed_dripstone_up_middle",
    "pointed_dripstone_up_tip": "pointed_dripstone_up_tip",
    # ── Misc new blocks (same name in Java) ──
    "moss_block": "moss_block",
    "mud": "mud",
    "mud_bricks": "mud_bricks",
    "packed_mud": "packed_mud",
    "calcite": "calcite",
    "dirt_with_roots": "rooted_dirt",
    "raw_copper_block": "raw_copper_block",
    "raw_gold_block": "raw_gold_block",
    "raw_iron_block": "raw_iron_block",
    "hanging_roots": "hanging_roots",
    "spore_blossom": "spore_blossom",
    "glow_lichen": "glow_lichen",
    "powder_snow": "powder_snow",
    "tinted_glass": "tinted_glass",
    "copper_ore": "copper_ore",
    "heavy_core": "heavy_core",
    "resin_block": "resin_block",
    "resin_bricks": "resin_bricks",
    "chiseled_resin_bricks": "chiseled_resin_bricks",
    "resin_clump": "resin_clump",
    # ── Dripleaf ──
    "big_dripleaf_side1": "big_dripleaf_side",
    "big_dripleaf_side2": "big_dripleaf_side",
    "big_dripleaf_stem": "big_dripleaf_stem",
    "big_dripleaf_top": "big_dripleaf_top",
    "small_dripleaf_side": "small_dripleaf_side",
    "small_dripleaf_stem_bottom": "small_dripleaf_stem_bottom",
    "small_dripleaf_stem_top": "small_dripleaf_stem_top",
    "small_dripleaf_top": "small_dripleaf_top",
    # ── Cave vines ──
    "cave_vines_body": "cave_vines_plant",
    "cave_vines_body_berries": "cave_vines_plant_lit",
    "cave_vines_head": "cave_vines",
    "cave_vines_head_berries": "cave_vines_lit",
    # ── Misc blocks ──
    "composter_bottom": "composter_bottom",
    "composter_side": "composter_side",
    "composter_top": "composter_top",
    "compost": "composter_compost",
    "compost_ready": "composter_compost",
    "grindstone_pivot": "grindstone_pivot",
    "grindstone_round": "grindstone_round",
    "grindstone_side": "grindstone_side",
    "smithing_table_bottom": "smithing_table_bottom",
    "smithing_table_front": "smithing_table_front",
    "smithing_table_side": "smithing_table_side",
    "smithing_table_top": "smithing_table_top",
    "loom_bottom": "loom_bottom",
    "loom_front": "loom_front",
    "loom_side": "loom_side",
    "loom_top": "loom_top",
    "target_side": "target_side",
    "target_top": "target_top",
    "honeycomb": "honeycomb_block",
    "soul_lantern": "soul_lantern",
    "frogspawn": "frogspawn",
    "vine": "vine",
    "snow": "snow",
    "ice": "ice",
    "sand": "sand",
    "red_sand": "red_sand",
    "gravel": "gravel",
    "clay": "clay",
    "obsidian": "obsidian",
    "stone": "stone",
    "cobblestone": "cobblestone",
    "coarse_dirt": "coarse_dirt",
    "dirt": "dirt",
    "bedrock": "bedrock",
    "end_stone": "end_stone",
    "purpur_block": "purpur_block",
    "purpur_pillar": "purpur_pillar",
    "purpur_pillar_top": "purpur_pillar_top",
    "prismarine_bricks": "prismarine_bricks",
    "cracked_nether_bricks": "cracked_nether_bricks",
    "chiseled_nether_bricks": "chiseled_nether_bricks",
    "quartz_bricks": "quartz_bricks",
    # ── Campfire ──
    "campfire": "campfire_fire",
    "campfire_log": "campfire_log",
    "campfire_log_lit": "campfire_log_lit",
    "soul_campfire": "soul_campfire_fire",
    "soul_campfire_log_lit": "soul_campfire_log_lit",
    # ── Barrel ──
    "barrel_bottom": "barrel_bottom",
    "barrel_side": "barrel_side",
    "barrel_top": "barrel_top",
    "barrel_top_open": "barrel_top_open",
    # ── Smoker ──
    "smoker_bottom": "smoker_bottom",
    "smoker_side": "smoker_side",
    "smoker_top": "smoker_top",
    # ── Bee nest / beehive ──
    "bee_nest_bottom": "bee_nest_bottom",
    "bee_nest_front": "bee_nest_front",
    "bee_nest_front_honey": "bee_nest_front_honey",
    "bee_nest_side": "bee_nest_side",
    "bee_nest_top": "bee_nest_top",
    "beehive_front": "beehive_front",
    "beehive_front_honey": "beehive_front_honey",
    "beehive_side": "beehive_side",
    "beehive_top": "beehive_top",
    # ── Daylight detector ──
    "daylight_detector_inverted_top": "daylight_detector_inverted_top",
    "daylight_detector_side": "daylight_detector_side",
    "daylight_detector_top": "daylight_detector_top",
    # ── Crafting table ──
    "crafting_table_front": "crafting_table_front",
    "crafting_table_side": "crafting_table_side",
    "crafting_table_top": "crafting_table_top",
    # ── Bone block ──
    "bone_block_side": "bone_block_side",
    "bone_block_top": "bone_block_top",
    # ── TNT ──
    "tnt_bottom": "tnt_bottom",
    "tnt_side": "tnt_side",
    "tnt_top": "tnt_top",
    # ── Candles (Bedrock has color prefix; Java is same) ──
    "candle": "candle",
    "candle_lit": "candle_lit",
    "black_candle": "black_candle",
    "black_candle_lit": "black_candle_lit",
    "blue_candle": "blue_candle",
    "blue_candle_lit": "blue_candle_lit",
    "brown_candle": "brown_candle",
    "brown_candle_lit": "brown_candle_lit",
    "cyan_candle": "cyan_candle",
    "cyan_candle_lit": "cyan_candle_lit",
    "gray_candle": "gray_candle",
    "gray_candle_lit": "gray_candle_lit",
    "green_candle": "green_candle",
    "green_candle_lit": "green_candle_lit",
    "light_blue_candle": "light_blue_candle",
    "light_blue_candle_lit": "light_blue_candle_lit",
    "light_gray_candle": "light_gray_candle",
    "light_gray_candle_lit": "light_gray_candle_lit",
    "lime_candle": "lime_candle",
    "lime_candle_lit": "lime_candle_lit",
    "magenta_candle": "magenta_candle",
    "magenta_candle_lit": "magenta_candle_lit",
    "orange_candle": "orange_candle",
    "orange_candle_lit": "orange_candle_lit",
    "pink_candle": "pink_candle",
    "pink_candle_lit": "pink_candle_lit",
    "purple_candle": "purple_candle",
    "purple_candle_lit": "purple_candle_lit",
    "red_candle": "red_candle",
    "red_candle_lit": "red_candle_lit",
    "white_candle": "white_candle",
    "white_candle_lit": "white_candle_lit",
    "yellow_candle": "yellow_candle",
    "yellow_candle_lit": "yellow_candle_lit",
    # ── Pale oak / pale moss ──
    "pale_moss": "pale_moss_block",
    "pale_moss_block": "pale_moss_block",
    "pale_hanging_moss_middle": "pale_hanging_moss",
    "pale_hanging_moss_tip": "pale_hanging_moss_tip",
    # ── Creaking heart ──
    "creaking_heart_side_active": "creaking_heart_active",
    "creaking_heart_side_dormant": "creaking_heart_dormant",
    "creaking_heart_side_inactive": "creaking_heart_inactive",
    "creaking_heart_top_active": "creaking_heart_top_active",
    "creaking_heart_top_dormant": "creaking_heart_top_dormant",
    "creaking_heart_top_inactive": "creaking_heart_top_inactive",
    # ── Reinforced deepslate ──
    "reinforced_deepslate_bottom": "reinforced_deepslate_bottom",
    "reinforced_deepslate_side": "reinforced_deepslate_side",
    "reinforced_deepslate_top": "reinforced_deepslate_top",
    # ── Misc ──
    "beacon": "beacon",
    "bookshelf": "bookshelf",
    "cake_bottom": "cake_bottom",
    "cake_inner": "cake_inner",
    "cake_side": "cake_side",
    "cake_top": "cake_top",
    "cactus_bottom": "cactus_bottom",
    "cactus_side": "cactus_side",
    "cactus_top": "cactus_top",
    "ladder": "ladder",
    "lantern": "lantern",
    "lever": "lever",
    "jukebox_side": "jukebox_side",
    "jukebox_top": "jukebox_top",
    "furnace_side": "furnace_side",
    "furnace_top": "furnace_top",
    "furnace_front_on": "furnace_front_on",
    "blast_furnace_front_on": "blast_furnace_front_on",
    "blast_furnace_side": "blast_furnace_side",
    "blast_furnace_top": "blast_furnace_top",
    "smoker_front_on": "smoker_front_on",
    "glow_item_frame": "glow_item_frame",
    "pumpkin_face_lit": "jack_o_lantern",
    "pumpkin_side_lit": "pumpkin_side",
    "pumpkin_top_lit": "pumpkin_top",
}
# Bulk colour→Java renames (wool, concrete, glazed terracotta, stained glass)
for _c, _j in [("white", "white"), ("orange", "orange"), ("magenta", "magenta"),
               ("light_blue", "light_blue"), ("yellow", "yellow"), ("lime", "lime"),
               ("pink", "pink"), ("gray", "gray"), ("silver", "light_gray"),
               ("cyan", "cyan"), ("purple", "purple"), ("blue", "blue"),
               ("brown", "brown"), ("green", "green"), ("red", "red"), ("black", "black")]:
    _BEDROCK_TO_JAVA[f"wool_colored_{_c}"] = f"{_j}_wool"
    _BEDROCK_TO_JAVA[f"concrete_{_c}"] = f"{_j}_concrete"
    _BEDROCK_TO_JAVA[f"concrete_powder_{_c}"] = f"{_j}_concrete_powder"
    _BEDROCK_TO_JAVA[f"glazed_terracotta_{_c}"] = f"{_j}_glazed_terracotta"
    _BEDROCK_TO_JAVA[f"stained_glass_{_c}"] = f"{_j}_stained_glass"


def _open_image(data: bytes) -> Image.Image:
    """Open an image from raw bytes (TGA or PNG)."""
    return Image.open(io.BytesIO(data))


class TexturePackReader:
    """Reads Minecraft resource pack files and extracts block textures.

    Supports Java Edition packs (with ``pack.mcmeta``) and Bedrock Edition
    packs (with ``manifest.json``).  For Bedrock packs, PBR data (MER and
    heightmap) is loaded as well.
    """

    BLOCK_TEXTURE_PATH = "assets/minecraft/textures/block/"

    def __init__(self, pack_path: str):
        self.zip_path = pack_path      # kept for backwards compat
        self._pack_path = pack_path
        self._textures: dict[str, Image.Image] = {}
        self._full_images: dict[str, Image.Image] = {}
        self._animations: dict[str, dict] = {}
        self._pack_format = None
        self._pack_description = ""
        self._is_bedrock = False
        # PBR maps (Bedrock only): block_name -> PIL.Image
        self._mer_textures: dict[str, Image.Image] = {}
        self._heightmaps: dict[str, Image.Image] = {}
        self._normal_maps: dict[str, Image.Image] = {}

    # ---------------------------------------------------------------- public
    @property
    def is_bedrock(self) -> bool:
        return self._is_bedrock

    @property
    def pack_format(self):
        return self._pack_format

    @property
    def pack_description(self) -> str:
        return self._pack_description

    @property
    def texture_names(self) -> list[str]:
        return sorted(self._textures.keys())

    @property
    def texture_count(self) -> int:
        return len(self._textures)

    def get_texture(self, block_name: str) -> Image.Image | None:
        return self._textures.get(block_name)

    def has_texture(self, block_name: str) -> bool:
        return block_name in self._textures

    def is_animated(self, block_name: str) -> bool:
        return block_name in self._animations

    def get_animation_info(self, block_name: str) -> dict | None:
        return self._animations.get(block_name)

    def get_full_image(self, block_name: str) -> Image.Image | None:
        return self._full_images.get(block_name)

    def get_mer_texture(self, block_name: str) -> Image.Image | None:
        """MER image (R=metalness, G=emissive, B=roughness). Bedrock only."""
        return self._mer_textures.get(block_name)

    def has_mer(self, block_name: str) -> bool:
        return block_name in self._mer_textures

    def get_heightmap(self, block_name: str) -> Image.Image | None:
        """Heightmap image. Bedrock only."""
        return self._heightmaps.get(block_name)

    def get_normal_map(self, block_name: str) -> Image.Image | None:
        """Direct normal map image. Bedrock only."""
        return self._normal_maps.get(block_name)

    def has_normal_map(self, block_name: str) -> bool:
        return block_name in self._normal_maps

    def has_mc_assets(self) -> bool:
        """True if the pack contains blockstates/models (Java packs)."""
        if self._is_bedrock:
            return False
        if os.path.isdir(self._pack_path):
            return os.path.isdir(
                os.path.join(self._pack_path, "assets", "minecraft", "blockstates"))
        try:
            with zipfile.ZipFile(self._pack_path, "r") as zf:
                return any(n.startswith("assets/minecraft/blockstates/")
                           for n in zf.namelist())
        except Exception:
            return False

    # ----------------------------------------------------------------- load
    def load(self):
        """Auto-detect format and load."""
        if os.path.isdir(self._pack_path):
            self._load_directory(self._pack_path)
        else:
            with zipfile.ZipFile(self._pack_path, "r") as zf:
                names = zf.namelist()
                if "manifest.json" in names or any(
                        n.startswith("textures/") for n in names):
                    self._load_bedrock_zip(zf)
                else:
                    self._load_java_zip(zf)

    def _load_directory(self, root: str):
        if os.path.isfile(os.path.join(root, "manifest.json")):
            self._load_bedrock_dir(root)
        elif os.path.isfile(os.path.join(root, "pack.mcmeta")):
            self._load_java_dir(root)
        elif os.path.isdir(os.path.join(root, "textures", "blocks")):
            self._load_bedrock_dir(root)
        elif os.path.isdir(os.path.join(root, "assets", "minecraft",
                                        "textures", "block")):
            self._load_java_dir(root)
        else:
            raise ValueError(f"Cannot determine pack type for: {root}")

    # =========================================================== Java (zip)
    def _load_java_zip(self, zf: zipfile.ZipFile):
        try:
            with zf.open("pack.mcmeta") as f:
                meta = json.loads(f.read().decode("utf-8"))
                pi = meta.get("pack", {})
                self._pack_format = pi.get("pack_format")
                self._pack_description = pi.get("description", "")
        except (KeyError, json.JSONDecodeError):
            pass

        mcmeta_data = {}
        for name in zf.namelist():
            if (name.startswith(self.BLOCK_TEXTURE_PATH)
                    and name.endswith(".png.mcmeta")):
                rel = name[len(self.BLOCK_TEXTURE_PATH):]
                bn = rel.replace(".png.mcmeta", "")
                if "/" not in bn:
                    try:
                        with zf.open(name) as f:
                            d = json.loads(f.read().decode("utf-8"))
                            mcmeta_data[bn] = d.get("animation", {}).get(
                                "frametime", 1)
                    except (KeyError, json.JSONDecodeError):
                        mcmeta_data[bn] = 1

        for name in zf.namelist():
            if not name.startswith(self.BLOCK_TEXTURE_PATH):
                continue
            if not name.lower().endswith(".png"):
                continue
            rel = name[len(self.BLOCK_TEXTURE_PATH):]
            bn = os.path.splitext(rel)[0]
            if "/" in bn:
                continue
            try:
                with zf.open(name) as f:
                    img = Image.open(f).copy()
                self._ingest_java_texture(bn, img, mcmeta_data)
            except Exception:
                continue

    # =========================================================== Java (dir)
    def _load_java_dir(self, root: str):
        pack_mcmeta = os.path.join(root, "pack.mcmeta")
        if os.path.isfile(pack_mcmeta):
            try:
                with open(pack_mcmeta, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    pi = meta.get("pack", {})
                    self._pack_format = pi.get("pack_format")
                    self._pack_description = pi.get("description", "")
            except (json.JSONDecodeError, OSError):
                pass

        tex_dir = os.path.join(root, "assets", "minecraft", "textures",
                               "block")
        if not os.path.isdir(tex_dir):
            return

        mcmeta_data = {}
        for fn in os.listdir(tex_dir):
            if fn.endswith(".png.mcmeta"):
                bn = fn.replace(".png.mcmeta", "")
                try:
                    with open(os.path.join(tex_dir, fn), "r",
                              encoding="utf-8") as f:
                        d = json.load(f)
                        mcmeta_data[bn] = d.get("animation", {}).get(
                            "frametime", 1)
                except (json.JSONDecodeError, OSError):
                    mcmeta_data[bn] = 1

        for fn in os.listdir(tex_dir):
            if not fn.lower().endswith(".png"):
                continue
            bn = os.path.splitext(fn)[0]
            try:
                img = Image.open(os.path.join(tex_dir, fn)).copy()
                self._ingest_java_texture(bn, img, mcmeta_data)
            except Exception:
                continue

    def _ingest_java_texture(self, bn: str, img: Image.Image,
                             mcmeta_data: dict):
        if bn in mcmeta_data:
            self._full_images[bn] = img.copy()
            fc = img.height // img.width if img.width > 0 else 1
            ft = mcmeta_data[bn] * 0.05
            self._animations[bn] = {"frame_count": max(fc, 1),
                                    "frametime": ft}
            if img.height > img.width:
                img = img.crop((0, 0, img.width, img.width))
        elif img.height > img.width:
            img = img.crop((0, 0, img.width, img.width))
        self._textures[bn] = img

    # ========================================================= Bedrock (zip)
    def _load_bedrock_zip(self, zf: zipfile.ZipFile):
        self._is_bedrock = True
        try:
            with zf.open("manifest.json") as f:
                m = json.loads(f.read().decode("utf-8"))
                self._pack_format = m.get("format_version")
                self._pack_description = m.get("header", {}).get(
                    "description", "")
        except (KeyError, json.JSONDecodeError):
            pass

        # Parse flipbook_textures.json for animation frametime overrides
        flipbook_frametimes: dict[str, float] = {}
        try:
            with zf.open("textures/flipbook_textures.json") as f:
                flipbook = json.loads(f.read().decode("utf-8"))
                for entry in flipbook:
                    atlas = entry.get("atlas_tile", "")
                    tpf = entry.get("ticks_per_frame", 1)
                    if atlas:
                        flipbook_frametimes[atlas] = tpf * 0.05
        except (KeyError, json.JSONDecodeError):
            pass

        prefix = "textures/blocks/"
        # Build lookup of available files (lowercase -> original name)
        available: dict[str, str] = {}
        for n in zf.namelist():
            if n.startswith(prefix):
                available[n.lower()] = n

        for name in list(available.values()):
            if not name.startswith(prefix):
                continue
            lower = name.lower()
            if not (lower.endswith(".tga") or lower.endswith(".png")):
                continue
            rel = name[len(prefix):]
            # Allow up to one level of subdirectory (deepslate/, candles/, etc.)
            parts = rel.replace("\\", "/").split("/")
            if len(parts) > 2:
                continue
            base = os.path.splitext(parts[-1])[0]
            # For files in subdirectories, the key for PBR lookup uses subdir prefix
            rel_base = os.path.splitext(rel.replace("\\", "/"))[0]
            if _BEDROCK_SKIP_RE.search(base) and base not in _BEDROCK_NOT_PBR:
                continue
            java_name = _BEDROCK_TO_JAVA.get(base, base)
            # Prefer transparent leaf textures over opaque variants
            if "_opaque" in base.lower() and java_name in self._textures:
                continue
            try:
                data = zf.read(name)
                img = _open_image(data).convert("RGBA")
                if img.height > img.width and img.height % img.width == 0:
                    fc = img.height // img.width
                    if fc > 1:
                        self._full_images[java_name] = img.copy()
                        ft = flipbook_frametimes.get(base, 0.05)
                        self._animations[java_name] = {
                            "frame_count": fc, "frametime": ft}
                        img = img.crop((0, 0, img.width, img.width))
                self._textures[java_name] = img
            except Exception:
                continue

            # Load MER (check with same subdirectory prefix)
            for ext in (".tga", ".png"):
                mer_key = f"{prefix}{rel_base}_mer{ext}".lower()
                if mer_key in available:
                    try:
                        mer = _open_image(zf.read(available[mer_key])).convert("RGBA")
                        self._mer_textures[java_name] = mer
                    except Exception:
                        pass
                    break

            # Load heightmap
            for ext in (".tga", ".png"):
                hm_key = f"{prefix}{rel_base}_heightmap{ext}".lower()
                if hm_key in available:
                    try:
                        hm = _open_image(zf.read(available[hm_key])).convert("L")
                        self._heightmaps[java_name] = hm
                    except Exception:
                        pass
                    break

            # Load direct normal map
            for ext in (".tga", ".png"):
                nm_key = f"{prefix}{rel_base}_normal{ext}".lower()
                if nm_key in available:
                    try:
                        nm = _open_image(zf.read(available[nm_key])).convert("RGB")
                        self._normal_maps[java_name] = nm
                    except Exception:
                        pass
                    break

        # Composite grass_side overlay onto dirt to make grass_block_side
        self._composite_grass_side()

    # ========================================================= Bedrock (dir)
    def _load_bedrock_dir(self, root: str):
        self._is_bedrock = True
        mf = os.path.join(root, "manifest.json")
        if os.path.isfile(mf):
            try:
                with open(mf, "r", encoding="utf-8") as f:
                    m = json.load(f)
                    self._pack_format = m.get("format_version")
                    self._pack_description = m.get("header", {}).get(
                        "description", "")
            except (json.JSONDecodeError, OSError):
                pass

        # Parse flipbook_textures.json for animation frametime overrides
        flipbook_frametimes: dict[str, float] = {}
        fb_path = os.path.join(root, "textures", "flipbook_textures.json")
        if os.path.isfile(fb_path):
            try:
                with open(fb_path, "r", encoding="utf-8") as f:
                    flipbook = json.load(f)
                    for entry in flipbook:
                        atlas = entry.get("atlas_tile", "")
                        tpf = entry.get("ticks_per_frame", 1)
                        if atlas:
                            flipbook_frametimes[atlas] = tpf * 0.05
            except (json.JSONDecodeError, OSError):
                pass

        tex_dir = os.path.join(root, "textures", "blocks")
        if not os.path.isdir(tex_dir):
            return

        # Build case-insensitive file map, walking subdirectories
        files_lower: dict[str, str] = {}
        for dirpath, _dirnames, filenames in os.walk(tex_dir):
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, tex_dir).replace("\\", "/")
                files_lower[rel.lower()] = rel

        for rel in list(files_lower.values()):
            lower = rel.lower()
            if not (lower.endswith(".tga") or lower.endswith(".png")):
                continue
            parts = rel.replace("\\", "/").split("/")
            if len(parts) > 2:
                continue
            base = os.path.splitext(parts[-1])[0]
            rel_base = os.path.splitext(rel)[0]
            if _BEDROCK_SKIP_RE.search(base) and base not in _BEDROCK_NOT_PBR:
                continue
            java_name = _BEDROCK_TO_JAVA.get(base, base)
            # Prefer transparent leaf textures over opaque variants
            if "_opaque" in base.lower() and java_name in self._textures:
                continue
            fpath = os.path.join(tex_dir, rel)
            try:
                img = Image.open(fpath).convert("RGBA")
                if img.height > img.width and img.height % img.width == 0:
                    fc = img.height // img.width
                    if fc > 1:
                        self._full_images[java_name] = img.copy()
                        ft = flipbook_frametimes.get(base, 0.05)
                        self._animations[java_name] = {
                            "frame_count": fc, "frametime": ft}
                        img = img.crop((0, 0, img.width, img.width))
                self._textures[java_name] = img
            except Exception:
                continue

            # Load MER
            for ext in (".tga", ".png"):
                mer_rel = f"{rel_base}_mer{ext}".lower()
                if mer_rel in files_lower:
                    try:
                        mer = Image.open(os.path.join(
                            tex_dir, files_lower[mer_rel])).convert("RGBA")
                        self._mer_textures[java_name] = mer
                    except Exception:
                        pass
                    break

            # Load heightmap
            for ext in (".tga", ".png"):
                hm_rel = f"{rel_base}_heightmap{ext}".lower()
                if hm_rel in files_lower:
                    try:
                        hm = Image.open(os.path.join(
                            tex_dir, files_lower[hm_rel])).convert("L")
                        self._heightmaps[java_name] = hm
                    except Exception:
                        pass
                    break

            # Load direct normal map
            for ext in (".tga", ".png"):
                nm_rel = f"{rel_base}_normal{ext}".lower()
                if nm_rel in files_lower:
                    try:
                        nm = Image.open(os.path.join(
                            tex_dir, files_lower[nm_rel])).convert("RGB")
                        self._normal_maps[java_name] = nm
                    except Exception:
                        pass
                    break

        # Composite grass_side overlay onto dirt to make grass_block_side
        self._composite_grass_side()

    # =============================================== Bedrock grass compositing
    def _composite_grass_side(self):
        """Bedrock grass_side is just the grass overlay (no dirt).

        Composite it on top of the dirt texture to produce a proper
        grass_block_side matching Java Edition's baked texture.
        """
        grass_key = "grass_block_side"
        dirt_key = "dirt"
        if grass_key not in self._textures or dirt_key not in self._textures:
            return
        grass_overlay = self._textures[grass_key]
        dirt = self._textures[dirt_key]
        # Check if the grass_side is truly an overlay (has transparency)
        if grass_overlay.mode != "RGBA":
            return
        alpha = grass_overlay.split()[3]
        if alpha.getextrema() == (255, 255):
            return  # Already opaque — no compositing needed
        # Preserve the overlay as a separate texture for tint masking
        self._textures["grass_block_side_overlay"] = grass_overlay.copy()
        # Resize dirt to match grass overlay size
        if dirt.size != grass_overlay.size:
            dirt = dirt.resize(grass_overlay.size, Image.NEAREST)
        dirt_rgba = dirt.convert("RGBA")
        # Composite: paste grass overlay on top of dirt
        composited = dirt_rgba.copy()
        composited.paste(grass_overlay, (0, 0), grass_overlay)
        self._textures[grass_key] = composited

        # Also composite MER if both exist
        grass_mer = self._mer_textures.get(grass_key)
        dirt_mer = self._mer_textures.get(dirt_key)
        if grass_mer is not None and dirt_mer is not None:
            if dirt_mer.size != grass_mer.size:
                dirt_mer = dirt_mer.resize(grass_mer.size, Image.NEAREST)
            dirt_mer_rgba = dirt_mer.convert("RGBA")
            comp_mer = dirt_mer_rgba.copy()
            comp_mer.paste(grass_mer, (0, 0), grass_overlay)
            self._mer_textures[grass_key] = comp_mer

        # Composite heightmap
        grass_hm = self._heightmaps.get(grass_key)
        dirt_hm = self._heightmaps.get(dirt_key)
        if grass_hm is not None and dirt_hm is not None:
            import numpy as np
            if dirt_hm.size != grass_hm.size:
                dirt_hm = dirt_hm.resize(grass_hm.size, Image.NEAREST)
            alpha_arr = np.array(alpha, dtype=np.float32) / 255.0
            g_arr = np.array(grass_hm, dtype=np.float32)
            d_arr = np.array(dirt_hm, dtype=np.float32)
            blended = (g_arr * alpha_arr + d_arr * (1.0 - alpha_arr))
            self._heightmaps[grass_key] = Image.fromarray(
                blended.clip(0, 255).astype(np.uint8), mode="L")
