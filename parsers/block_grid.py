"""Unified 3D block grid model used by all parsers."""

import numpy as np
from config.blocks import is_air, should_generate_geometry, is_solid_for_culling


class BlockGrid:
    """Represents a 3D grid of Minecraft blocks with a palette.

    Coordinates use Minecraft convention: X (east), Y (up), Z (south).
    The grid stores palette indices; the palette maps index -> block state string.
    """

    def __init__(self, width: int, height: int, length: int,
                 blocks: np.ndarray, palette: dict[int, str]):
        self.width = width    # X size
        self.height = height  # Y size
        self.length = length  # Z size
        self.blocks = blocks  # shape (width, height, length), dtype int
        self.palette = palette  # {index: "minecraft:stone", ...}
        # Reverse map for lookups
        self._reverse_palette = {v: k for k, v in palette.items()}
        self._block_count = None  # cached

    def get_block_id(self, x: int, y: int, z: int) -> int:
        """Get palette index at position. Returns -1 if out of bounds."""
        if 0 <= x < self.width and 0 <= y < self.height and 0 <= z < self.length:
            return int(self.blocks[x, y, z])
        return -1

    def get_block(self, x: int, y: int, z: int) -> str:
        """Get block state string at position. Returns 'minecraft:air' if out of bounds."""
        bid = self.get_block_id(x, y, z)
        if bid < 0:
            return "minecraft:air"
        return self.palette.get(bid, "minecraft:air")

    def is_air(self, x: int, y: int, z: int) -> bool:
        return is_air(self.get_block(x, y, z))

    def should_generate(self, x: int, y: int, z: int) -> bool:
        return should_generate_geometry(self.get_block(x, y, z))

    def is_solid_for_culling(self, x: int, y: int, z: int) -> bool:
        return is_solid_for_culling(self.get_block(x, y, z))

    def get_unique_block_types(self) -> set[str]:
        """Get all unique non-air block types present in the grid."""
        types = set()
        for idx in np.unique(self.blocks):
            name = self.palette.get(int(idx), "minecraft:air")
            if not is_air(name):
                types.add(name)
        return types

    @property
    def block_count(self) -> int:
        """Count of non-air blocks (cached after first call)."""
        if self._block_count is not None:
            return self._block_count
        # Build air palette indices set for fast lookup
        air_indices = set()
        for idx, name in self.palette.items():
            if is_air(name):
                air_indices.add(idx)
        # Count all non-air blocks in one pass
        air_mask = np.isin(self.blocks, list(air_indices))
        self._block_count = int(np.sum(~air_mask))
        return self._block_count

    def __repr__(self):
        return (f"BlockGrid({self.width}x{self.height}x{self.length}, "
                f"{self.block_count:,} solid blocks, {len(self.palette)} palette entries)")
