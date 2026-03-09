# MCtoCS

Convert Minecraft structures to Counter-Strike 2 `.vmap` maps.

MCtoCS reads `.nbt` files exported from Minecraft and generates fully textured CS2 maps you can open in Hammer and compile.

---

## Features

- **Full block textures** — applies textures from any Minecraft resource pack (Java `.zip` or Bedrock `.mcpack`)
- **PBR support** — Bedrock RTX packs with normal/MER textures generate proper PBR materials in CS2
- **Model blocks** — fences, torches, stairs, flowers, and other non-cube blocks render with correct geometry when MC assets are provided
- **Face culling** — hidden faces between adjacent solid blocks are removed for performance
- **Animated textures** — water, lava, fire, and other animated textures are exported as sprite sheet animations
- **Liquids as func_water** — optionally convert water/lava to CS2 water entities
- **Damage blocks** — cactus, magma, etc. can generate `trigger_hurt` entities
- **Climbable ladders** — ladders generate `func_ladder` entities
- **Slime bounce** — slime blocks generate bounce trigger brushes
- **Stair/slab clip ramps** — auto-generates invisible ramp brushes so players can walk up stairs and slabs smoothly
- **Auto-lighting** — light-emitting blocks (glowstone, torches, sea lanterns) automatically place `light_omni` entities
- **Multiple output modes** — Per Block, Merge Same Touching, Per Block Type, or Single Mesh
- **Addon export** — exports textures and materials directly into your CS2 addon folder with optional resource compiler integration

---

## Getting Started

### Download

Grab the latest `MCtoCS.exe` from the [Releases](../../releases) page. No installation needed — just run it.

### Running from Source

```
pip install -r requirements.txt
python main.py
```

Requirements: Python 3.11+

### Building the Executable

```powershell
.\build_onefile.ps1
```

Output: `dist/MCtoCS.exe`

---

## Usage

### 1. Select Input File

Click **Browse** and select your Minecraft structure file (`.nbt`, `.schematic`, or `.schem`).

> **Tip:** For structures with **more than 5,000 blocks**, use the **"Merge Same Touching"** output mode. Per Block mode creates a separate mesh per block which can be very slow for large builds.

### 2. Texture Pack (Recommended)

Provide a Minecraft resource pack so blocks get proper textures instead of the default placeholder material.

- **Vanilla Minecraft textures:** Download the default resource pack from  
  https://texture-packs.com/resourcepack/default-pack/  
  and select the `.zip` file.
- **RTX / PBR textures:** For the best visual quality, use a Bedrock RTX `.mcpack` that includes normal maps and MER (Metalness/Emissive/Roughness) textures. These will generate full PBR materials in CS2 with proper metalness, roughness, and normal mapping. Popular RTX packs like **Kelly's RTX**, **SUSPENDED's RTX**, or **Vanilla RTX Normals** work well.

### 3. MC Assets (Optional)

To render model blocks (fences, torches, stairs, flowers, rails, etc.) with correct geometry, provide the vanilla Minecraft client assets. You can point to either:

- A **folder** containing `assets/minecraft/blockstates/` and `assets/minecraft/models/`
- A **`.zip`** file of the same (e.g., the Minecraft client `.jar` file)

Without MC assets, model blocks will fall back to simple cubes.

### 4. Conversion Settings

| Setting | Description |
|---------|-------------|
| **Block Scale** | Size of each block in Hammer units (default: 64) |
| **Cull Hidden Faces** | Remove faces between touching solid blocks (recommended) |
| **Output Mode** | How blocks are grouped into meshes (see below) |
| **Origin Offset** | Shift the map origin (X, Y, Z) in Hammer units |
| **Liquids as func_water** | Convert water/lava to `func_water` entities instead of world geometry |
| **Trigger_hurt** | Add `trigger_hurt` brushes for damage blocks (cactus, magma, etc.) |
| **Climbable ladders** | Generate `func_ladder` entities for ladder blocks |
| **Slime bounce** | Generate bounce triggers for slime blocks |
| **Stair clip ramps** | Add invisible ramp brushes over stairs and slabs for smooth player movement |
| **Auto-lighting** | Place `light_omni` entities at light-emitting blocks |

#### Output Modes

- **Per Block** — Each block is a separate mesh. Best for small builds (<5k blocks).
- **Merge Same Touching** — Adjacent blocks of the same type are merged. **Recommended for most builds.**
- **Per Block Type** — All blocks of the same type become one mesh. Good for very large builds.
- **Single Mesh** — Everything in one mesh. Smallest file but no per-block editing.

### 5. Addon Export

To get textures into CS2:

1. Set **Addon Folder** to your CS2 addon's content directory  
   (e.g., `steamapps/common/Counter-Strike Global Offensive/content/csgo_addons/your_addon/`)
2. Set **Map Name** — textures are organized under `materials/<map_name>/`
3. Optionally set **Resource Compiler** path to auto-compile textures to `.vtex_c`  
   (usually at `game/bin/win64/resourcecompiler.exe`)

Click **Convert** and the `.vmap` file will be saved alongside your input file. Open it in Hammer.

Click **Recompile Textures** to re-export and compile textures without re-converting the map.

---

## Tips

- **Export your builds** from Minecraft using Structure Blocks (`.nbt`) or WorldEdit (`.schematic` / `.schem`).
- **Large builds:** Always use "Merge Same Touching" or "Per Block Type" mode. Per Block mode on 10k+ block structures will produce huge files.
- **RTX packs** significantly improve visual quality in CS2 — normal maps add surface detail and MER textures give proper metallic/roughness values.
- **Stair clip ramps** make stairs walkable like real ramps in CS2 instead of requiring jumping.
- **Auto-lighting** saves you from manually placing lights — glowstone, sea lanterns, torches etc. all emit light automatically.

---
