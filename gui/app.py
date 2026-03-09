"""Modern GUI application for Minecraft to CS2 converter using CustomTkinter."""

import os
import gc
import subprocess
import threading
import queue
import traceback
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import numpy as np
import customtkinter as ctk
from tkinter import filedialog, messagebox

from parsers.nbt_parser import parse_nbt
from parsers.schematic_parser import parse_schematic
from parsers.schem_parser import parse_schem
from converter.mesh_generator import (generate_quads, group_quads_by_material,
                                       group_quads_by_block_pos, group_quads_merge_connected)
from converter.halfedge import build_halfedge_mesh
from vmap.writer import write_vmap_file
from config.blocks import is_model_block, is_non_solid_model, is_noshadow_mesh
from textures.pack_reader import TexturePackReader
from textures.material_generator import MaterialGenerator
from converter.model_geometry import ModelBlockQuadGenerator
from config.defaults import DEFAULT_BLOCK_SCALE, DEFAULT_MATERIAL


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

SLIME_BOUNCE_SCRIPT = '''\
import { Instance } from "cs_script/point_script";

const tracking = new Map();
const bounceCooldown = new Map();
const noDmgUntil = new Map();

Instance.SetThink(() => {
    const now = Instance.GetGameTime();
    for (const [pawn, data] of tracking) {
        const vel = pawn.GetAbsVelocity();
        const pos = pawn.GetAbsOrigin();
        data.lastVelZ = Math.min(data.lastVelZ, vel.z);
        if (vel.z > 0) continue;
        const traceEnd = { x: pos.x, y: pos.y, z: pos.z - 128 };
        const trace = Instance.TraceLine({ start: pos, end: traceEnd, ignoreEntity: pawn });
        const distToGround = trace.fraction * 128;
        if (distToGround < 16) {
            const lastBounce = bounceCooldown.get(pawn) || 0;
            if (now - lastBounce < 0.15) { tracking.delete(pawn); continue; }
            const fallSpeed = Math.abs(data.lastVelZ);
            if (fallSpeed < 50) { tracking.delete(pawn); continue; }
            const bounceZ = fallSpeed * 0.80;
            pawn.Teleport({ velocity: { x: vel.x, y: vel.y, z: bounceZ } });
            bounceCooldown.set(pawn, now);
            noDmgUntil.set(pawn, now + 0.2);
            tracking.delete(pawn);
        }
    }
    Instance.SetNextThink(Instance.GetGameTime());
});
Instance.SetNextThink(Instance.GetGameTime());

Instance.OnModifyPlayerDamage((event) => {
    const now = Instance.GetGameTime();
    const until = noDmgUntil.get(event.player);
    if (until && now < until) {
        return { abort: true };
    }
});

Instance.OnScriptInput("slime_bounce", ({ activator }) => {
    if (!activator) return;
    tracking.set(activator, { lastVelZ: activator.GetAbsVelocity().z });
});

Instance.OnScriptInput("slime_exit", ({ activator }) => {
    if (!activator) return;
    tracking.delete(activator);
});
'''


def _write_slime_bounce_script(filepath: str):
    """Write the slime block bounce JavaScript file for CS2 point_script."""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(SLIME_BOUNCE_SCRIPT)


FILE_TYPES = [
    ("All Supported", "*.nbt;*.schematic;*.schem"),
    ("Structure Files", "*.nbt"),
    ("Schematic Files", "*.schematic"),
    ("Sponge Schematic", "*.schem"),
]


class ConversionLogWindow(ctk.CTkToplevel):
    """Separate window that shows conversion progress and log output."""

    def __init__(self, master, cancel_callback):
        super().__init__(master)
        self.title("Conversion Progress")
        self.geometry("700x500")
        self.minsize(500, 350)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._cancel_callback = cancel_callback
        self._closed = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Progress section
        prog_frame = ctk.CTkFrame(self)
        prog_frame.grid(row=0, column=0, padx=15, pady=(15, 5), sticky="ew")
        prog_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(prog_frame)
        self.progress_bar.grid(row=0, column=0, padx=12, pady=(12, 2), sticky="ew")
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(prog_frame, text="Starting...",
                                           font=ctk.CTkFont(size=12), text_color="gray")
        self.progress_label.grid(row=1, column=0, padx=12, pady=(0, 5), sticky="w")

        self.step_label = ctk.CTkLabel(prog_frame, text="",
                                       font=ctk.CTkFont(size=13, weight="bold"))
        self.step_label.grid(row=2, column=0, padx=12, pady=(0, 12), sticky="w")

        # Stats section
        stats_frame = ctk.CTkFrame(self)
        stats_frame.grid(row=1, column=0, padx=15, pady=(0, 5), sticky="ew")
        stats_frame.grid_columnconfigure(1, weight=1)
        stats_frame.grid_columnconfigure(3, weight=1)

        self.stat_labels = {}
        stat_items = [("Quads:", "quads", 0, 0), ("Meshes:", "meshes", 0, 2),
                      ("Materials:", "materials", 1, 0), ("Memory:", "memory", 1, 2)]
        for text, key, r, c in stat_items:
            ctk.CTkLabel(stats_frame, text=text, font=ctk.CTkFont(size=12)).grid(
                row=r, column=c, padx=(12, 2), pady=2, sticky="w")
            lbl = ctk.CTkLabel(stats_frame, text="—", font=ctk.CTkFont(size=12),
                               text_color="#2ecc71")
            lbl.grid(row=r, column=c+1, padx=(0, 12), pady=2, sticky="w")
            self.stat_labels[key] = lbl

        # Log textbox
        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=2, column=0, padx=15, pady=(5, 5), sticky="nsew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(log_frame, text="Log",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, padx=12, pady=(10, 2), sticky="w")

        self.log_text = ctk.CTkTextbox(log_frame, font=ctk.CTkFont(family="Consolas", size=11))
        self.log_text.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        self.log_text.configure(state="disabled")

        # Bottom buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=3, column=0, padx=15, pady=(0, 15), sticky="ew")
        btn_frame.grid_columnconfigure(0, weight=1)

        self.cancel_btn = ctk.CTkButton(
            btn_frame, text="Cancel", height=36, fg_color="#c0392b",
            hover_color="#e74c3c", command=self._on_cancel)
        self.cancel_btn.grid(row=0, column=0, sticky="ew")

        self.close_btn = ctk.CTkButton(
            btn_frame, text="Close", height=36, command=self._on_close)

        self.lift()
        self.focus_force()

    def append_log(self, message: str):
        if self._closed:
            return
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def set_progress(self, value: float, text: str = ""):
        if self._closed:
            return
        self.progress_bar.set(value)
        if text:
            self.progress_label.configure(text=text)

    def set_step(self, text: str):
        if self._closed:
            return
        self.step_label.configure(text=text)

    def set_stat(self, key: str, value: str):
        if self._closed:
            return
        if key in self.stat_labels:
            self.stat_labels[key].configure(text=value)

    def show_done(self):
        """Switch from cancel to close button."""
        if self._closed:
            return
        self.cancel_btn.grid_forget()
        self.close_btn.grid(row=0, column=0, sticky="ew")

    def _on_cancel(self):
        self._cancel_callback()

    def _on_close(self):
        self._closed = True
        self.destroy()


class MCtoCSApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("MCtoCS — Minecraft to CS2 Converter")
        self.geometry("900x850")
        self.minsize(800, 750)

        self._msg_queue = queue.Queue()
        self._conversion_thread = None
        self._cancel_flag = threading.Event()

        # State
        self._input_path = ""
        self._texture_pack_path = ""
        self._mc_assets_path = ""
        self._texture_reader = None
        self._material_gen = None
        self._log_window = None

        self._build_ui()
        self._poll_queue()

    def _build_ui(self):
        # Main scrollable frame
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        main_frame = ctk.CTkScrollableFrame(self, corner_radius=0)
        main_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        main_frame.grid_columnconfigure(0, weight=1)

        row = 0

        # ===== HEADER =====
        header = ctk.CTkLabel(main_frame, text="MCtoCS",
                              font=ctk.CTkFont(size=28, weight="bold"))
        header.grid(row=row, column=0, pady=(20, 0), padx=20, sticky="w")
        row += 1

        subtitle = ctk.CTkLabel(main_frame, text="Convert Minecraft structures to CS2 maps",
                                font=ctk.CTkFont(size=14), text_color="gray")
        subtitle.grid(row=row, column=0, pady=(0, 20), padx=20, sticky="w")
        row += 1

        # ===== INPUT FILE =====
        input_frame = ctk.CTkFrame(main_frame)
        input_frame.grid(row=row, column=0, padx=20, pady=(0, 10), sticky="ew")
        input_frame.grid_columnconfigure(1, weight=1)
        row += 1

        ctk.CTkLabel(input_frame, text="Input File",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, columnspan=4, padx=15, pady=(12, 5), sticky="w")

        ctk.CTkLabel(input_frame, text="Structure:").grid(
            row=1, column=0, padx=(15, 5), pady=(0, 12), sticky="w")
        self._input_entry = ctk.CTkEntry(input_frame, placeholder_text="Select .nbt, .schematic, or .schem file...")
        self._input_entry.grid(row=1, column=1, padx=5, pady=(0, 12), sticky="ew")
        ctk.CTkButton(input_frame, text="Browse", width=80,
                      command=self._browse_input).grid(
            row=1, column=2, padx=(5, 0), pady=(0, 12))
        self._preview_btn = ctk.CTkButton(input_frame, text="Preview", width=80,
                                          command=self._show_preview, state="disabled",
                                          fg_color="#555555", hover_color="#666666")
        self._preview_btn.grid(row=1, column=3, padx=(5, 15), pady=(0, 12))

        # Info label
        self._info_label = ctk.CTkLabel(input_frame, text="", text_color="gray",
                                        font=ctk.CTkFont(size=12))
        self._info_label.grid(row=2, column=0, columnspan=4, padx=15, pady=(0, 10), sticky="w")

        # ===== TEXTURE PACK =====
        tex_frame = ctk.CTkFrame(main_frame)
        tex_frame.grid(row=row, column=0, padx=20, pady=(0, 10), sticky="ew")
        tex_frame.grid_columnconfigure(1, weight=1)
        row += 1

        ctk.CTkLabel(tex_frame, text="Texture Pack",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, columnspan=3, padx=15, pady=(12, 5), sticky="w")

        ctk.CTkLabel(tex_frame, text="Pack:").grid(
            row=1, column=0, padx=(15, 5), pady=(0, 5), sticky="w")
        self._tex_entry = ctk.CTkEntry(tex_frame, placeholder_text="Select Minecraft resource pack (.zip / .mcpack)...")
        self._tex_entry.grid(row=1, column=1, padx=5, pady=(0, 5), sticky="ew")
        ctk.CTkButton(tex_frame, text="Browse", width=80,
                      command=self._browse_texture_pack).grid(
            row=1, column=2, padx=(5, 15), pady=(0, 5))

        # Texture size selector
        size_row_frame = ctk.CTkFrame(tex_frame, fg_color="transparent")
        size_row_frame.grid(row=2, column=0, columnspan=3, padx=15, pady=(0, 5), sticky="ew")

        ctk.CTkLabel(size_row_frame, text="Texture Size:").grid(
            row=0, column=0, padx=(0, 5), sticky="w")
        self._texture_size_var = ctk.StringVar(value="512")
        ctk.CTkOptionMenu(size_row_frame, values=["256", "512", "1024", "2048"],
                          variable=self._texture_size_var, width=100).grid(
            row=0, column=1, padx=(0, 10), sticky="w")

        self._tex_info_label = ctk.CTkLabel(tex_frame, text="Select a Minecraft resource pack .zip",
                                            text_color="gray", font=ctk.CTkFont(size=12))
        self._tex_info_label.grid(row=3, column=0, columnspan=3, padx=15, pady=(0, 5), sticky="w")

        # MC Assets folder (for model blocks)
        ctk.CTkLabel(tex_frame, text="MC Assets:").grid(
            row=4, column=0, padx=(15, 5), pady=(0, 5), sticky="w")
        self._assets_entry = ctk.CTkEntry(tex_frame, placeholder_text="Vanilla MC assets folder or .zip (has blockstates/, models/)...")
        self._assets_entry.grid(row=4, column=1, padx=5, pady=(0, 5), sticky="ew")
        ctk.CTkButton(tex_frame, text="Browse", width=80,
                      command=self._browse_mc_assets).grid(
            row=4, column=2, padx=(5, 15), pady=(0, 5))
        self._assets_info_label = ctk.CTkLabel(tex_frame, text="Optional: enables model blocks (fences, torches, stairs...)",
                                               text_color="gray", font=ctk.CTkFont(size=12))
        self._assets_info_label.grid(row=5, column=0, columnspan=3, padx=15, pady=(0, 10), sticky="w")

        # ===== SETTINGS =====
        settings_frame = ctk.CTkFrame(main_frame)
        settings_frame.grid(row=row, column=0, padx=20, pady=(0, 10), sticky="ew")
        settings_frame.grid_columnconfigure(1, weight=1)
        settings_frame.grid_columnconfigure(3, weight=1)
        row += 1

        ctk.CTkLabel(settings_frame, text="Conversion Settings",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, columnspan=4, padx=15, pady=(12, 10), sticky="w")

        # Scale
        ctk.CTkLabel(settings_frame, text="Block Scale:").grid(
            row=1, column=0, padx=(15, 5), pady=5, sticky="w")
        scale_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        scale_frame.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        scale_frame.grid_columnconfigure(0, weight=1)
        self._scale_entry = ctk.CTkEntry(scale_frame, width=80,
                                         placeholder_text=str(DEFAULT_BLOCK_SCALE))
        self._scale_entry.insert(0, str(DEFAULT_BLOCK_SCALE))
        self._scale_entry.grid(row=0, column=0, sticky="w", padx=(0, 5))
        ctk.CTkLabel(scale_frame, text="Hammer units per block",
                     text_color="gray", font=ctk.CTkFont(size=11)).grid(
            row=0, column=1, sticky="w")

        # Cull hidden faces
        ctk.CTkLabel(settings_frame, text="Cull Hidden Faces:").grid(
            row=1, column=2, padx=(20, 5), pady=5, sticky="w")
        self._cull_faces_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(settings_frame, text="Enabled", variable=self._cull_faces_var,
                      onvalue=True, offvalue=False).grid(
            row=1, column=3, padx=(5, 15), pady=5, sticky="w")

        # Output mode
        ctk.CTkLabel(settings_frame, text="Output Mode:").grid(
            row=2, column=0, padx=(15, 5), pady=(5, 12), sticky="w")
        self._output_mode_var = ctk.StringVar(value="Per Block")
        self._output_mode = ctk.CTkOptionMenu(
            settings_frame,
            values=["Per Block", "Merge Same Touching", "Per Block Type", "Single Mesh"],
            variable=self._output_mode_var,
        )
        self._output_mode.grid(row=2, column=1, padx=5, pady=(5, 12), sticky="w")

        # Offset
        offset_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        offset_frame.grid(row=3, column=0, columnspan=4, padx=15, pady=(0, 5), sticky="ew")

        ctk.CTkLabel(offset_frame, text="Origin Offset:").grid(
            row=0, column=0, padx=(0, 10), sticky="w")
        ctk.CTkLabel(offset_frame, text="X:").grid(row=0, column=1, padx=(0, 2))
        self._offset_x = ctk.CTkEntry(offset_frame, width=60, placeholder_text="0")
        self._offset_x.grid(row=0, column=2, padx=(0, 10))
        ctk.CTkLabel(offset_frame, text="Y:").grid(row=0, column=3, padx=(0, 2))
        self._offset_y = ctk.CTkEntry(offset_frame, width=60, placeholder_text="0")
        self._offset_y.grid(row=0, column=4, padx=(0, 10))
        ctk.CTkLabel(offset_frame, text="Z:").grid(row=0, column=5, padx=(0, 2))
        self._offset_z = ctk.CTkEntry(offset_frame, width=60, placeholder_text="0")
        self._offset_z.grid(row=0, column=6)

        # Entity options
        entity_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        entity_frame.grid(row=4, column=0, columnspan=4, padx=15, pady=(5, 12), sticky="ew")

        self._func_water_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(entity_frame, text="Liquids as func_water",
                        variable=self._func_water_var).grid(
            row=0, column=0, padx=(0, 20), sticky="w")

        self._trigger_hurt_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(entity_frame, text="Add trigger_hurt for damage blocks",
                        variable=self._trigger_hurt_var).grid(
            row=0, column=1, padx=(0, 20), sticky="w")

        self._climbable_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(entity_frame, text="Climbable ladders",
                        variable=self._climbable_var).grid(
            row=1, column=0, padx=(0, 20), pady=(5, 0), sticky="w")

        self._slime_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(entity_frame, text="Slime bounce",
                        variable=self._slime_var).grid(
            row=1, column=1, padx=(0, 20), pady=(5, 0), sticky="w")

        self._stair_clip_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(entity_frame, text="Stair clip ramps",
                        variable=self._stair_clip_var).grid(
            row=1, column=2, padx=(0, 20), pady=(5, 0), sticky="w")

        self._auto_light_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(entity_frame, text="Auto-lighting",
                        variable=self._auto_light_var).grid(
            row=2, column=0, padx=(0, 20), pady=(5, 0), sticky="w")

        # ===== ADDON EXPORT =====
        addon_frame = ctk.CTkFrame(main_frame)
        addon_frame.grid(row=row, column=0, padx=20, pady=(0, 10), sticky="ew")
        addon_frame.grid_columnconfigure(1, weight=1)
        row += 1

        ctk.CTkLabel(addon_frame, text="Addon Export",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, columnspan=3, padx=15, pady=(12, 5), sticky="w")

        # Addon folder
        ctk.CTkLabel(addon_frame, text="Addon Folder:").grid(
            row=1, column=0, padx=(15, 5), pady=(0, 5), sticky="w")
        self._addon_entry = ctk.CTkEntry(addon_frame, placeholder_text="Select CS2 addon content folder...")
        self._addon_entry.grid(row=1, column=1, padx=5, pady=(0, 5), sticky="ew")
        ctk.CTkButton(addon_frame, text="Browse", width=80,
                      command=self._browse_addon).grid(
            row=1, column=2, padx=(5, 15), pady=(0, 5))

        # Map name
        ctk.CTkLabel(addon_frame, text="Map Name:").grid(
            row=2, column=0, padx=(15, 5), pady=(0, 5), sticky="w")
        self._map_name_entry = ctk.CTkEntry(addon_frame, placeholder_text="Auto-filled from input file...")
        self._map_name_entry.grid(row=2, column=1, columnspan=2, padx=(5, 15), pady=(0, 5), sticky="ew")

        # Resource compiler
        ctk.CTkLabel(addon_frame, text="Resource Compiler:").grid(
            row=3, column=0, padx=(15, 5), pady=(0, 12), sticky="w")
        self._rc_entry = ctk.CTkEntry(addon_frame, placeholder_text="Auto-detected or browse manually...")
        self._rc_entry.grid(row=3, column=1, padx=5, pady=(0, 12), sticky="ew")

        rc_btn_frame = ctk.CTkFrame(addon_frame, fg_color="transparent")
        rc_btn_frame.grid(row=3, column=2, padx=(5, 15), pady=(0, 12))
        ctk.CTkButton(rc_btn_frame, text="Find", width=38,
                      command=self._auto_find_rc).grid(row=0, column=0, padx=(0, 2))
        ctk.CTkButton(rc_btn_frame, text="Browse", width=38,
                      command=self._browse_rc).grid(row=0, column=1)

        # ===== CONVERT BUTTON =====
        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.grid(row=row, column=0, padx=20, pady=(5, 5), sticky="ew")
        btn_frame.grid_columnconfigure(0, weight=1)
        row += 1

        btn_frame.grid_columnconfigure(1, weight=1)

        self._convert_btn = ctk.CTkButton(
            btn_frame, text="Convert", height=42,
            font=ctk.CTkFont(size=16, weight="bold"),
            command=self._start_conversion
        )
        self._convert_btn.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        self._recompile_btn = ctk.CTkButton(
            btn_frame, text="Recompile Textures", height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#2980b9", hover_color="#3498db",
            command=self._start_recompile_textures
        )
        self._recompile_btn.grid(row=0, column=1, sticky="ew", padx=(5, 0))

        self._cancel_btn = ctk.CTkButton(
            btn_frame, text="Cancel", height=42, fg_color="#c0392b",
            hover_color="#e74c3c", font=ctk.CTkFont(size=16),
            command=self._cancel_conversion
        )

        # ===== STATUS LABEL =====
        self._status_label = ctk.CTkLabel(main_frame, text="Ready",
                                          font=ctk.CTkFont(size=12), text_color="gray")
        self._status_label.grid(row=row, column=0, padx=20, pady=(5, 20), sticky="w")
        row += 1

    # ===== UI CALLBACKS =====

    def _browse_input(self):
        path = filedialog.askopenfilename(
            title="Select Minecraft Structure File",
            filetypes=FILE_TYPES,
        )
        if path:
            self._input_path = path
            self._input_entry.delete(0, "end")
            self._input_entry.insert(0, path)

            # Auto-fill map name from input filename
            base_name = os.path.splitext(os.path.basename(path))[0]
            self._map_name_entry.delete(0, "end")
            self._map_name_entry.insert(0, base_name)

            # Try to load and show info
            self._load_input_info()
            self._preview_btn.configure(state="normal")

    def _show_preview(self):
        """Open a window showing the NBT file contents."""
        path = self._input_entry.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showerror("Error", "No valid input file selected.")
            return

        try:
            grid = self._parse_input_file(path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to parse file:\n{e}")
            return

        # Build block count map
        block_counts = {}
        for idx in np.unique(grid.blocks):
            name = grid.palette.get(int(idx), "minecraft:air")
            count = int(np.sum(grid.blocks == idx))
            block_counts[name] = count

        # Create preview window
        win = ctk.CTkToplevel(self)
        win.title(f"Structure Preview — {os.path.basename(path)}")
        win.geometry("600x500")
        win.minsize(450, 350)
        win.lift()
        win.focus_force()
        win.grid_columnconfigure(0, weight=1)
        win.grid_rowconfigure(2, weight=1)

        # Header info
        info_frame = ctk.CTkFrame(win)
        info_frame.grid(row=0, column=0, padx=15, pady=(15, 5), sticky="ew")
        info_frame.grid_columnconfigure(1, weight=1)

        labels = [
            ("File:", os.path.basename(path)),
            ("Dimensions:", f"{grid.width} x {grid.height} x {grid.length}"),
            ("Total blocks:", f"{grid.width * grid.height * grid.length:,}"),
            ("Solid blocks:", f"{grid.block_count:,}"),
            ("Block types:", str(len(grid.get_unique_block_types()))),
        ]
        for i, (label, value) in enumerate(labels):
            ctk.CTkLabel(info_frame, text=label, font=ctk.CTkFont(weight="bold")).grid(
                row=i, column=0, padx=(12, 5), pady=2, sticky="w")
            ctk.CTkLabel(info_frame, text=value).grid(
                row=i, column=1, padx=(0, 12), pady=2, sticky="w")

        # Block list header
        ctk.CTkLabel(win, text="Block List",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=1, column=0, padx=15, pady=(10, 2), sticky="w")

        # Block list
        block_text = ctk.CTkTextbox(win, font=ctk.CTkFont(family="Consolas", size=12))
        block_text.grid(row=2, column=0, padx=15, pady=(0, 15), sticky="nsew")

        # Sort by count descending
        sorted_blocks = sorted(block_counts.items(), key=lambda x: x[1], reverse=True)
        header_line = f"{'Block Name':<45} {'Count':>8}  {'%':>6}\n"
        block_text.insert("end", header_line)
        block_text.insert("end", "─" * 62 + "\n")

        total = grid.width * grid.height * grid.length
        for name, count in sorted_blocks:
            pct = (count / total * 100) if total > 0 else 0
            line = f"{name:<45} {count:>8,}  {pct:>5.1f}%\n"
            block_text.insert("end", line)

        block_text.configure(state="disabled")

    def _browse_texture_pack(self):
        path = filedialog.askopenfilename(
            title="Select Minecraft Resource Pack",
            filetypes=[("Resource Packs", "*.zip *.mcpack"), ("ZIP files", "*.zip"), ("mcpack files", "*.mcpack")],
        )
        if path:
            self._texture_pack_path = path
            self._tex_entry.delete(0, "end")
            self._tex_entry.insert(0, path)
            self._load_texture_pack()

    def _browse_mc_assets(self):
        # First try file dialog for zip, then fall back to directory
        path = filedialog.askopenfilename(
            title="Select MC Assets (zip) or cancel to pick a folder",
            filetypes=[("ZIP archives", "*.zip"), ("All files", "*.*")],
        )
        if not path:
            path = filedialog.askdirectory(title="Select Vanilla MC Assets Folder")
        if path:
            self._mc_assets_path = path
            self._assets_entry.delete(0, "end")
            self._assets_entry.insert(0, path)
            if os.path.isfile(path) and path.lower().endswith(".zip"):
                import zipfile
                try:
                    with zipfile.ZipFile(path, "r") as zf:
                        names = zf.namelist()
                    has_bs = any("blockstates/" in n for n in names)
                    if has_bs:
                        self._assets_info_label.configure(
                            text="MC assets zip loaded — model blocks enabled",
                            text_color="#2ecc71")
                    else:
                        self._assets_info_label.configure(
                            text="Warning: blockstates/ not found in this zip",
                            text_color="#e7a33c")
                except Exception:
                    self._assets_info_label.configure(
                        text="Error: could not read zip file",
                        text_color="#e74c3c")
            elif os.path.isdir(path):
                has_bs = (os.path.isdir(os.path.join(path, "assets", "minecraft", "blockstates"))
                          or os.path.isdir(os.path.join(path, "blockstates")))
                if has_bs:
                    self._assets_info_label.configure(
                        text="MC assets folder loaded — model blocks enabled",
                        text_color="#2ecc71")
                else:
                    self._assets_info_label.configure(
                        text="Warning: blockstates/ not found in this folder",
                        text_color="#e7a33c")
            else:
                self._assets_info_label.configure(
                    text="Warning: path is not a folder or zip file",
                    text_color="#e7a33c")

    def _browse_addon(self):
        path = filedialog.askdirectory(title="Select CS2 Addon Content Folder")
        if path:
            self._addon_entry.delete(0, "end")
            self._addon_entry.insert(0, path)

    def _browse_rc(self):
        path = filedialog.askopenfilename(
            title="Select resourcecompiler.exe",
            filetypes=[("Executable", "*.exe")],
        )
        if path:
            self._rc_entry.delete(0, "end")
            self._rc_entry.insert(0, path)

    def _auto_find_rc(self):
        """Try to find resourcecompiler.exe automatically."""
        rc_path = self._find_resource_compiler()
        if rc_path:
            self._rc_entry.delete(0, "end")
            self._rc_entry.insert(0, rc_path)
            self._log(f"Found resource compiler: {rc_path}")
        else:
            messagebox.showwarning("Not Found",
                                   "Could not auto-detect resourcecompiler.exe.\n"
                                   "Please browse to it manually.\n\n"
                                   "Usually at: <CS2>/game/bin/win64/resourcecompiler.exe")

    @staticmethod
    def _find_resource_compiler() -> str | None:
        """Try to find CS2 resourcecompiler.exe via registry or drive scanning."""
        import winreg

        # Try Steam registry key
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r"SOFTWARE\WOW6432Node\Valve\Steam")
            steam_path, _ = winreg.QueryValueEx(key, "InstallPath")
            winreg.CloseKey(key)

            # Check default CS2 location
            rc = os.path.join(steam_path, "steamapps", "common",
                              "Counter-Strike Global Offensive",
                              "game", "bin", "win64", "resourcecompiler.exe")
            if os.path.isfile(rc):
                return rc

            # Check libraryfolders.vdf for alternate locations
            lib_file = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
            if os.path.isfile(lib_file):
                with open(lib_file, "r", encoding="utf-8") as f:
                    content = f.read()
                import re
                paths = re.findall(r'"path"\s+"([^"]+)"', content)
                for p in paths:
                    rc = os.path.join(p, "steamapps", "common",
                                      "Counter-Strike Global Offensive",
                                      "game", "bin", "win64", "resourcecompiler.exe")
                    if os.path.isfile(rc):
                        return rc
        except (OSError, FileNotFoundError):
            pass

        # Fallback: scan drive letters
        for letter in "CDEFGH":
            for steam_dir in ["Steam", "SteamLibrary"]:
                rc = os.path.join(f"{letter}:\\", "Program Files (x86)", steam_dir,
                                  "steamapps", "common",
                                  "Counter-Strike Global Offensive",
                                  "game", "bin", "win64", "resourcecompiler.exe")
                if os.path.isfile(rc):
                    return rc
                rc = os.path.join(f"{letter}:\\", steam_dir,
                                  "steamapps", "common",
                                  "Counter-Strike Global Offensive",
                                  "game", "bin", "win64", "resourcecompiler.exe")
                if os.path.isfile(rc):
                    return rc

        return None

    def _load_input_info(self):
        try:
            grid = self._parse_input_file(self._input_path)
            info = (f"{grid.width}x{grid.height}x{grid.length} blocks | "
                    f"{grid.block_count} solid blocks | "
                    f"{len(grid.get_unique_block_types())} block types")
            self._info_label.configure(text=info, text_color="#2ecc71")
            if grid.block_count > 5000 and self._output_mode_var.get() == "Per Block":
                messagebox.showwarning(
                    "Large Structure",
                    f"This structure has {grid.block_count:,} solid blocks.\n\n"
                    "For structures over 5,000 blocks it is strongly recommended "
                    "to use the \"Merge Same Touching\" output mode for better "
                    "performance and smaller file size."
                )
        except Exception as e:
            self._info_label.configure(text=f"Error: {e}", text_color="#e74c3c")

    def _load_texture_pack(self):
        try:
            reader = TexturePackReader(self._texture_pack_path)
            reader.load()
            self._texture_reader = reader
            anim_count = sum(1 for n in reader.texture_names if reader.is_animated(n))
            info = f"Loaded {reader.texture_count} textures ({anim_count} animated)"
            if reader.pack_format:
                info += f" — format {reader.pack_format}"
            if reader.is_bedrock:
                mer_count = sum(1 for n in reader.texture_names if reader.has_mer(n))
                info += f" — Bedrock PBR ({mer_count} MER textures)"
            self._tex_info_label.configure(text=info, text_color="#2ecc71")
            self._log(f"Texture pack loaded: {reader.texture_count} textures, {anim_count} animated")
            if reader.is_bedrock:
                self._log(f"Bedrock pack detected with PBR textures")
            # Auto-populate MC assets path from pack if it contains model data
            if reader.has_mc_assets() and not self._mc_assets_path:
                self._mc_assets_path = self._texture_pack_path
                self._assets_entry.delete(0, "end")
                self._assets_entry.insert(0, self._texture_pack_path)
                self._assets_info_label.configure(
                    text="MC assets auto-detected from resource pack",
                    text_color="#2ecc71")
                self._log("MC assets auto-detected from resource pack")
        except Exception as e:
            self._tex_info_label.configure(text=f"Error: {e}", text_color="#e74c3c")
            self._texture_reader = None

    # ===== LOGGING =====

    def _log(self, message: str):
        """Thread-safe logging."""
        self._msg_queue.put(("log", message))

    def _set_progress(self, value: float, text: str = ""):
        self._msg_queue.put(("progress", value, text))

    def _set_step(self, text: str):
        self._msg_queue.put(("step", text))

    def _set_stat(self, key: str, value: str):
        self._msg_queue.put(("stat", key, value))

    @staticmethod
    def _mem_mb() -> str:
        """Return current process RSS in MB."""
        try:
            import psutil
            mb = psutil.Process().memory_info().rss / (1024 * 1024)
            return f"{mb:,.0f} MB"
        except ImportError:
            # Fallback: rough estimate from sys.getsizeof of gc objects count
            return "N/A"

    def _poll_queue(self):
        """Process messages from the conversion thread."""
        try:
            while True:
                msg = self._msg_queue.get_nowait()
                lw = self._log_window
                if msg[0] == "log":
                    if lw and not lw._closed:
                        lw.append_log(msg[1])
                elif msg[0] == "progress":
                    if lw and not lw._closed:
                        lw.set_progress(msg[1], msg[2] if len(msg) > 2 else "")
                elif msg[0] == "step":
                    if lw and not lw._closed:
                        lw.set_step(msg[1])
                elif msg[0] == "stat":
                    if lw and not lw._closed:
                        lw.set_stat(msg[1], msg[2])
                elif msg[0] == "done":
                    self._on_conversion_done(msg[1])
                elif msg[0] == "error":
                    self._on_conversion_error(msg[1])
        except queue.Empty:
            pass
        self.after(50, self._poll_queue)

    # ===== PARSING =====

    @staticmethod
    def _parse_input_file(filepath: str):
        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".nbt":
            return parse_nbt(filepath)
        elif ext == ".schematic":
            return parse_schematic(filepath)
        elif ext == ".schem":
            return parse_schem(filepath)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

    # ===== CONVERSION =====

    def _start_conversion(self):
        # Validate inputs
        input_path = self._input_entry.get().strip()
        addon_folder = self._addon_entry.get().strip()
        map_name = self._map_name_entry.get().strip()

        if not input_path:
            messagebox.showerror("Error", "Please select an input file.")
            return
        if not os.path.isfile(input_path):
            messagebox.showerror("Error", "Input file does not exist.")
            return
        if not addon_folder:
            messagebox.showerror("Error", "Please select an addon content folder.")
            return
        if not map_name:
            messagebox.showerror("Error", "Please enter a map name.")
            return

        self._input_path = input_path

        self._cancel_flag.clear()
        self._convert_btn.configure(state="disabled")
        self._recompile_btn.configure(state="disabled")
        self._status_label.configure(text="Converting...", text_color="orange")

        # Open log window
        if self._log_window is not None:
            try:
                self._log_window.destroy()
            except Exception:
                pass
        self._log_window = ConversionLogWindow(self, self._cancel_conversion)

        # Start conversion thread
        self._conversion_thread = threading.Thread(
            target=self._run_conversion, daemon=True
        )
        self._conversion_thread.start()

    def _cancel_conversion(self):
        self._cancel_flag.set()
        self._log("Cancelling...")

    def _on_conversion_done(self, output_path: str):
        self._convert_btn.configure(state="normal")
        self._recompile_btn.configure(state="normal")
        self._status_label.configure(text="Done!", text_color="#2ecc71")
        lw = self._log_window
        if lw and not lw._closed:
            lw.append_log(f"Successfully saved to: {output_path}")
            lw.set_progress(1.0, "Done!")
            lw.set_step("Conversion complete")
            lw.show_done()
        messagebox.showinfo("Success", f"VMap file saved to:\n{output_path}")

    def _on_conversion_error(self, error_msg: str):
        self._convert_btn.configure(state="normal")
        self._recompile_btn.configure(state="normal")
        self._status_label.configure(text="Error", text_color="#e74c3c")
        lw = self._log_window
        if lw and not lw._closed:
            lw.append_log(f"ERROR: {error_msg}")
            lw.set_progress(0, "Error")
            lw.show_done()
        messagebox.showerror("Conversion Error", error_msg)

    def _start_recompile_textures(self):
        """Start texture-only recompilation (swap packs without re-converting)."""
        addon_folder = self._addon_entry.get().strip()
        map_name = self._map_name_entry.get().strip()

        if not addon_folder:
            messagebox.showerror("Error", "Please select an addon content folder.")
            return
        if not map_name:
            messagebox.showerror("Error", "Please enter a map name.")
            return

        mat_dir = os.path.join(addon_folder, "materials", map_name)
        if not os.path.isdir(mat_dir):
            messagebox.showerror("Error",
                f"No existing materials found at:\n{mat_dir}\n\n"
                "Run a full conversion first, then use Recompile Textures to swap packs.")
            return

        tex_path = self._tex_entry.get().strip()
        if not tex_path:
            messagebox.showerror("Error", "Please select a texture pack.")
            return

        self._cancel_flag.clear()
        self._convert_btn.configure(state="disabled")
        self._recompile_btn.configure(state="disabled")
        self._status_label.configure(text="Recompiling textures...", text_color="orange")

        if self._log_window is not None:
            try:
                self._log_window.destroy()
            except Exception:
                pass
        self._log_window = ConversionLogWindow(self, self._cancel_conversion)

        self._conversion_thread = threading.Thread(
            target=self._run_recompile_textures, daemon=True
        )
        self._conversion_thread.start()

    def _run_recompile_textures(self):
        """Texture-only recompilation pipeline (runs in background thread)."""
        try:
            addon_folder = self._addon_entry.get().strip()
            map_name = self._map_name_entry.get().strip()
            texture_size = int(self._texture_size_var.get())
            rc_path = self._rc_entry.get().strip()
            tex_path = self._tex_entry.get().strip()

            mat_dir = os.path.join(addon_folder, "materials", map_name)

            # Step 1: Discover existing block names from .vmat files
            self._set_step("Step 1/4: Scanning existing materials")
            self._log("Step 1/4: Scanning existing .vmat files...")
            self._set_progress(0.05, "Scanning...")

            existing_blocks = set()
            for fname in os.listdir(mat_dir):
                if fname.endswith(".vmat"):
                    block_name = fname[:-5]  # strip .vmat
                    existing_blocks.add(block_name)
            self._log(f"Found {len(existing_blocks)} existing materials")

            if not existing_blocks:
                self._msg_queue.put(("error", "No .vmat files found in materials folder."))
                return

            if self._cancel_flag.is_set():
                self._msg_queue.put(("error", "Cancelled"))
                return

            # Step 2: Load texture pack (reload if path changed)
            self._set_step("Step 2/4: Loading texture pack")
            self._log(f"Step 2/4: Loading texture pack: {tex_path}")
            self._set_progress(0.15, "Loading textures...")

            reader = TexturePackReader(tex_path)
            reader.load()
            self._texture_reader = reader
            self._log(f"Loaded {reader.texture_count} textures")
            if reader.is_bedrock:
                mer_count = sum(1 for n in reader.texture_names if reader.has_mer(n))
                self._log(f"Bedrock pack with {mer_count} PBR textures")

            if self._cancel_flag.is_set():
                self._msg_queue.put(("error", "Cancelled"))
                return

            # Step 3: Clear old textures and re-export
            self._set_step("Step 3/4: Re-exporting materials")
            self._log("Step 3/4: Clearing old textures and re-exporting...")
            self._set_progress(0.25, "Clearing old files...")

            # Remove old generated files (textures + vmats)
            removed = 0
            for fname in os.listdir(mat_dir):
                fpath = os.path.join(mat_dir, fname)
                if os.path.isfile(fpath):
                    os.remove(fpath)
                    removed += 1
            self._log(f"Removed {removed} old files")

            # Re-export materials
            used_block_keys = {f"minecraft:{b}" for b in existing_blocks}
            mat_gen = MaterialGenerator(reader)

            def mat_progress(current, total):
                pct = 0.30 + 0.45 * (current / total)
                self._set_progress(pct, f"Materials: {current}/{total}")

            mat_map = mat_gen.export_to_addon(
                addon_folder, map_name,
                used_blocks=used_block_keys,
                texture_size=texture_size,
                progress_callback=mat_progress,
            )
            self._log(f"Exported {len(mat_map)} materials")
            self._set_stat("materials", str(len(mat_map)))

            # Also re-export model textures
            model_tex_names = existing_blocks - {b.split(":")[-1] for b in mat_map}
            if model_tex_names:
                mat_gen.export_model_textures(
                    addon_folder, map_name, model_tex_names, texture_size)
                extra = len(mat_gen.get_all_vmat_paths()) - len(mat_map)
                if extra > 0:
                    self._log(f"Exported {extra} additional model textures")

            if self._cancel_flag.is_set():
                self._msg_queue.put(("error", "Cancelled"))
                return

            # Step 4: Compile .vmat files with resource compiler
            vmat_paths = mat_gen.get_all_vmat_paths()
            if rc_path and os.path.isfile(rc_path) and vmat_paths:
                self._set_step("Step 4/4: Compiling materials")
                self._log(f"Step 4/4: Compiling {len(vmat_paths)} .vmat files...")
                self._set_progress(0.78, "Compiling materials...")

                compiled = 0
                failed = 0
                total_vmats = len(vmat_paths)

                def _compile_one(vmat):
                    try:
                        r = subprocess.run(
                            [rc_path, "-i", vmat],
                            capture_output=True, text=True, timeout=30,
                        )
                        return r.returncode == 0
                    except (subprocess.TimeoutExpired, OSError):
                        return False

                rc_workers = min(total_vmats, os.cpu_count() or 4)
                with ThreadPoolExecutor(max_workers=rc_workers) as executor:
                    futures = {executor.submit(_compile_one, v): v for v in vmat_paths}
                    done_count = 0
                    for future in as_completed(futures):
                        if self._cancel_flag.is_set():
                            executor.shutdown(wait=False, cancel_futures=True)
                            self._msg_queue.put(("error", "Cancelled"))
                            return
                        if future.result():
                            compiled += 1
                        else:
                            failed += 1
                        done_count += 1
                        pct = 0.78 + 0.20 * (done_count / total_vmats)
                        self._set_progress(pct, f"Compiling: {done_count}/{total_vmats}")

                self._log(f"Compiled: {compiled} OK, {failed} failed")
            elif vmat_paths and not rc_path:
                self._log("Step 4/4: Skipped — no resource compiler path set")
            else:
                self._log("Step 4/4: Skipped — no materials to compile")

            self._set_progress(1.0, "Done!")
            self._set_step("Texture recompilation complete")
            self._log(f"Texture recompilation complete! {len(mat_map)} materials updated.")
            self._msg_queue.put(("done", mat_dir))

        except Exception as e:
            tb = traceback.format_exc()
            self._msg_queue.put(("error", f"{e}\n\n{tb}"))

    def _run_conversion(self):
        """Main conversion pipeline (runs in background thread)."""
        try:
            addon_folder = self._addon_entry.get().strip()
            map_name = self._map_name_entry.get().strip()
            texture_size = int(self._texture_size_var.get())
            rc_path = self._rc_entry.get().strip()

            # Step 1: Parse input
            self._set_step("Step 1/7: Parsing input file")
            self._log("Step 1/7: Parsing input file...")
            self._set_progress(0.05, "Parsing...")
            self._set_stat("memory", self._mem_mb())
            grid = self._parse_input_file(self._input_path)
            self._log(f"Loaded: {grid}")
            self._set_stat("memory", self._mem_mb())

            if self._cancel_flag.is_set():
                self._msg_queue.put(("error", "Cancelled"))
                return

            # Step 2: Export materials to addon folder
            self._set_step("Step 2/7: Exporting materials")
            self._log("Step 2/7: Exporting materials...")
            self._set_progress(0.10, "Exporting materials...")

            block_types = grid.get_unique_block_types()

            mat_gen = MaterialGenerator(self._texture_reader)
            if self._texture_reader:
                def mat_progress(current, total):
                    pct = 0.10 + 0.10 * (current / total)
                    self._set_progress(pct, f"Materials: {current}/{total}")

                mat_map = mat_gen.export_to_addon(addon_folder, map_name,
                                                  used_blocks=block_types,
                                                  texture_size=texture_size,
                                                  progress_callback=mat_progress)
                self._log(f"Exported {len(mat_map)} materials to {addon_folder}/materials/{map_name}/")
                self._set_stat("materials", str(len(mat_map)))
            else:
                mat_map = {}
                self._log("No texture pack loaded — using default material")
            materials = mat_gen.get_materials_for_blocks(block_types)
            self._log(f"Using {len(materials)} materials")
            self._set_stat("materials", str(len(materials)))

            if self._cancel_flag.is_set():
                self._msg_queue.put(("error", "Cancelled"))
                return

            # Step 3: Generate mesh
            scale = int(self._scale_entry.get() or DEFAULT_BLOCK_SCALE)
            cull_faces = self._cull_faces_var.get()
            use_func_water = self._func_water_var.get()
            use_trigger_hurt = self._trigger_hurt_var.get()
            use_climbable = self._climbable_var.get()
            use_slime = self._slime_var.get()
            use_stair_clips = self._stair_clip_var.get()
            use_auto_light = self._auto_light_var.get()
            separate_liquids = use_func_water or use_trigger_hurt
            offset = (
                float(self._offset_x.get() or 0),
                float(self._offset_y.get() or 0),
                float(self._offset_z.get() or 0),
            )

            self._set_step("Step 3/7: Generating mesh")
            self._log(f"Step 3/7: Generating mesh (scale={scale}, cull_faces={cull_faces})...")
            self._set_progress(0.22, "Generating mesh...")

            # Create model generator if MC assets path is provided
            model_gen = None
            mc_assets = self._mc_assets_path or self._assets_entry.get().strip()
            if mc_assets and (os.path.isdir(mc_assets)
                              or (os.path.isfile(mc_assets)
                                  and mc_assets.lower().endswith(".zip"))):
                try:
                    model_gen = ModelBlockQuadGenerator(mc_assets)
                    self._log("Model block generator initialized")
                except Exception as e:
                    self._log(f"Warning: Could not init model generator: {e}")

            def mesh_progress(current, total):
                if total > 0:
                    pct = 0.22 + 0.28 * (current / total)
                    self._set_progress(pct, f"Meshing: face direction {current}/{total}")

            quads, water_quads, lava_quads, damage_quads, climbable_quads, slime_quads, stair_clip_quads, light_sources = generate_quads(
                grid, scale, offset, mesh_progress,
                cull_faces=cull_faces,
                model_generator=model_gen,
                separate_liquids=separate_liquids,
                generate_climbable=use_climbable,
                generate_slime=use_slime,
                generate_stair_clips=use_stair_clips,
                generate_lights=use_auto_light)

            if model_gen:
                model_gen.close()

            total_quads = len(quads) + len(water_quads) + len(lava_quads) + len(damage_quads)
            self._log(f"Generated {len(quads)} solid quads")
            if water_quads:
                self._log(f"  + {len(water_quads)} water quads (func_water)")
            if lava_quads:
                self._log(f"  + {len(lava_quads)} lava quads (func_water + trigger_hurt)")
            if damage_quads:
                self._log(f"  + {len(damage_quads)} damage quads (trigger_hurt)")
            if climbable_quads:
                self._log(f"  + {len(climbable_quads)} climbable quads (ladder)")
            if slime_quads:
                self._log(f"  + {len(slime_quads)} slime quads (bounce)")
            if stair_clip_quads:
                self._log(f"  + {len(stair_clip_quads)} stair clip quads")
            if light_sources:
                self._log(f"  + {len(light_sources)} light sources")
            self._set_stat("quads", f"{total_quads:,}")

            # Export any model-specific textures discovered during quad generation
            if self._texture_reader:
                model_tex_names = set()
                for q in quads:
                    if q.texture_name:
                        model_tex_names.add(q.texture_name)
                if model_tex_names:
                    mat_gen.export_model_textures(addon_folder, map_name,
                                                  model_tex_names, texture_size)
                    materials = mat_gen.get_materials_for_blocks(block_types)
                    # Also add model texture materials
                    for tn in model_tex_names:
                        m = mat_gen.get_material_for_block(f"minecraft:{tn}")
                        if m not in materials:
                            materials.append(m)
                    materials = sorted(set(materials))
                    self._log(f"Exported {len(model_tex_names)} model textures")

            # Free the grid — no longer needed
            del grid
            gc.collect()
            self._set_stat("memory", self._mem_mb())

            if self._cancel_flag.is_set():
                self._msg_queue.put(("error", "Cancelled"))
                return

            if not quads and not water_quads and not lava_quads:
                self._msg_queue.put(("error", "No visible faces generated. The structure might be empty or all air."))
                return

            # Step 4: Group quads by output mode
            output_mode = self._output_mode.get()
            self._set_step(f"Step 4/7: Grouping ({output_mode})")
            self._log(f"Step 4/7: Grouping meshes ({output_mode})...")
            self._set_progress(0.52, "Grouping meshes...")

            if output_mode == "Per Block":
                groups = group_quads_by_block_pos(quads)
                quad_groups = list(groups.values())
                del groups
                self._log(f"Split into {len(quad_groups)} per-block meshes")
            elif output_mode == "Merge Same Touching":
                quad_groups = group_quads_merge_connected(quads)
                self._log(f"Merged into {len(quad_groups)} connected groups")
            elif output_mode == "Per Block Type":
                groups = group_quads_by_material(quads)
                quad_groups = list(groups.values())
                del groups
                self._log(f"Split into {len(quad_groups)} block-type groups")
            else:
                quad_groups = [quads] if quads else []

            # Build entity quad groups — each connected region becomes one entity,
            # but internally split to per-block meshes for CS2 compatibility.
            # entity_quad_groups: list of (list_of_per_block_quad_lists, entity_type)
            entity_quad_groups = []
            if water_quads and use_func_water:
                water_groups = group_quads_merge_connected(water_quads)
                for wg in water_groups:
                    block_groups = list(group_quads_by_block_pos(wg).values())
                    entity_quad_groups.append((block_groups, "func_water"))
                self._log(f"Water: {len(water_groups)} func_water entities")
            elif water_quads:
                quad_groups.append(water_quads)

            if lava_quads and use_trigger_hurt:
                lava_groups = group_quads_merge_connected(lava_quads)
                for lg in lava_groups:
                    lava_block_groups = list(group_quads_by_block_pos(lg).values())
                    entity_quad_groups.append((lava_block_groups, "func_water"))
                    entity_quad_groups.append(([list(q) for q in lava_block_groups], "trigger_hurt"))
                self._log(f"Lava: {len(lava_groups)} func_water + trigger_hurt entity pairs")
            elif lava_quads:
                quad_groups.append(lava_quads)

            if damage_quads and use_trigger_hurt:
                dmg_groups = group_quads_merge_connected(damage_quads)
                for dg in dmg_groups:
                    dmg_block_groups = list(group_quads_by_block_pos(dg).values())
                    entity_quad_groups.append((dmg_block_groups, "trigger_hurt"))
                self._log(f"Damage blocks: {len(dmg_groups)} trigger_hurt entities")
            elif damage_quads:
                pass

            # Climbable blocks: add as regular meshes with invisible ladder material (solid)
            LADDER_MATERIAL = "materials/tools/toolsinvisibleladder_wood.vmat"
            climbable_group_start = len(quad_groups)
            if climbable_quads:
                for q in climbable_quads:
                    q.texture_name = "toolsinvisibleladder_wood"
                climb_groups = group_quads_merge_connected(climbable_quads)
                for cg in climb_groups:
                    quad_groups.append(cg)
                if LADDER_MATERIAL not in materials:
                    materials.append(LADDER_MATERIAL)
                    materials.sort()
                self._log(f"Climbable: {len(climb_groups)} ladder meshes")
            climbable_group_end = len(quad_groups)

            # Slime blocks: trigger_multiple for bounce script
            has_slime = False
            TRIGGER_MATERIAL = "materials/tools/toolstrigger.vmat"
            if slime_quads:
                for q in slime_quads:
                    q.texture_name = "toolstrigger"
                slime_groups = group_quads_merge_connected(slime_quads)
                for sg in slime_groups:
                    entity_quad_groups.append(([sg], "slime_bounce"))
                if TRIGGER_MATERIAL not in materials:
                    materials.append(TRIGGER_MATERIAL)
                    materials.sort()
                has_slime = True
                self._log(f"Slime: {len(slime_groups)} bounce trigger entities")

            # Stair clip ramps: invisible solid ramps over stairs for smooth walking
            CLIP_MATERIAL = "materials/tools/toolsclip.vmat"
            stair_clip_group_start = len(quad_groups)
            if stair_clip_quads:
                for q in stair_clip_quads:
                    q.texture_name = "toolsclip"
                clip_groups = group_quads_merge_connected(stair_clip_quads)
                for cg in clip_groups:
                    quad_groups.append(cg)
                if CLIP_MATERIAL not in materials:
                    materials.append(CLIP_MATERIAL)
                    materials.sort()
                self._log(f"Stair clips: {len(clip_groups)} clip meshes")
            stair_clip_group_end = len(quad_groups)

            # Free original flat quads list (data is now in quad_groups)
            del quads
            del water_quads
            del lava_quads
            del damage_quads
            del climbable_quads
            del slime_quads
            del stair_clip_quads
            gc.collect()
            self._set_stat("memory", self._mem_mb())
            # Count total per-block meshes across all entities
            entity_block_count = sum(len(bg_list) for bg_list, _ in entity_quad_groups)
            total_mesh_count = len(quad_groups) + len(entity_quad_groups)
            self._set_stat("meshes", f"{total_mesh_count:,}")

            # Determine physics type per quad group
            # Model-block-only groups get physicsType="none" (non-solid)
            # Climbable / stair-clip groups are always solid (physicsType="default")
            mesh_physics_types = []
            mesh_disable_shadows = []
            for idx, qg in enumerate(quad_groups):
                if climbable_group_start <= idx < climbable_group_end:
                    mesh_physics_types.append("default")
                    mesh_disable_shadows.append(False)
                elif stair_clip_group_start <= idx < stair_clip_group_end:
                    mesh_physics_types.append("default")
                    mesh_disable_shadows.append(False)
                elif all(is_non_solid_model(q.block_type) for q in qg):
                    mesh_physics_types.append("none")
                    noshadow = all(is_noshadow_mesh(q.block_type) for q in qg)
                    mesh_disable_shadows.append(noshadow)
                else:
                    mesh_physics_types.append("default")
                    mesh_disable_shadows.append(False)

            # Step 5: Build half-edge meshes (parallel)
            total_groups = len(quad_groups)
            total_to_build = total_groups + entity_block_count
            self._set_step("Step 5/7: Building half-edge meshes")
            self._log(f"Step 5/7: Building {total_to_build} half-edge mesh(es) in parallel...")
            self._set_progress(0.55, f"Building {total_to_build} meshes...")

            workers = min(total_to_build, max(1, (os.cpu_count() or 4) // 2))
            meshes = [None] * total_groups
            completed = 0

            # Flatten entity block groups for parallel building:
            # entity_build_list: [(entity_idx, block_idx_within_entity, quad_list), ...]
            entity_build_list = []
            for ei, (bg_list, _etype) in enumerate(entity_quad_groups):
                for bi, bq in enumerate(bg_list):
                    entity_build_list.append((ei, bi, bq))

            # Prepare result storage: entity_meshes_by_ent[entity_idx] = {block_idx: mesh}
            entity_meshes_by_ent = {ei: {} for ei in range(len(entity_quad_groups))}

            # Submit all groups for parallel building
            all_groups = [(i, qg) for i, qg in enumerate(quad_groups)]
            all_groups += [(total_groups + j, ebl[2]) for j, ebl in enumerate(entity_build_list)]

            with ProcessPoolExecutor(max_workers=workers) as executor:
                future_to_idx = {
                    executor.submit(build_halfedge_mesh, qg): idx
                    for idx, qg in all_groups
                }
                for future in as_completed(future_to_idx):
                    if self._cancel_flag.is_set():
                        executor.shutdown(wait=False, cancel_futures=True)
                        self._msg_queue.put(("error", "Cancelled"))
                        return

                    idx = future_to_idx[future]
                    mesh = future.result()
                    if idx < total_groups:
                        meshes[idx] = mesh
                    else:
                        # Entity block mesh
                        j = idx - total_groups
                        ei, bi, _ = entity_build_list[j]
                        entity_meshes_by_ent[ei][bi] = mesh
                    completed += 1
                    pct = 0.55 + 0.20 * (completed / total_to_build)
                    self._set_progress(pct, f"Built mesh {completed}/{total_to_build}")
                    if completed % max(1, total_to_build // 20) == 0 or completed == total_to_build:
                        self._log(f"  Built {completed}/{total_to_build} meshes")
                        self._set_stat("memory", self._mem_mb())

            # Assemble entity mesh pairs: each entity gets a list of per-block meshes
            entity_mesh_pairs = []
            for ei, (bg_list, ent_type) in enumerate(entity_quad_groups):
                block_meshes = []
                for bi in range(len(bg_list)):
                    m = entity_meshes_by_ent[ei].get(bi)
                    if m is not None:
                        block_meshes.append(m)
                if block_meshes:
                    entity_mesh_pairs.append((block_meshes, ent_type))

            # Free quad groups (mesh data has been extracted)
            del quad_groups
            del entity_quad_groups
            gc.collect()
            self._set_stat("memory", self._mem_mb())

            # Step 6: Write vmap to addon/maps/
            maps_dir = os.path.join(addon_folder, "maps")
            os.makedirs(maps_dir, exist_ok=True)
            output_vmap = os.path.join(maps_dir, f"{map_name}.vmap")

            self._set_step("Step 6/7: Writing .vmap")
            self._log(f"Step 6/7: Writing .vmap to {output_vmap}...")
            self._set_progress(0.78, "Writing .vmap...")

            material_map = {k: mat_gen.get_material_for_block(k) for k in block_types}
            # Ensure water_flow material is included for func_water entities
            wf_mat = mat_gen.get_material_for_block("minecraft:water_flow")
            if wf_mat != DEFAULT_MATERIAL and wf_mat not in materials:
                materials.append(wf_mat)
                materials.sort()

            # Write slime bounce script if slime blocks exist
            script_path = None
            if has_slime:
                scripts_dir = os.path.join(addon_folder, "scripts")
                os.makedirs(scripts_dir, exist_ok=True)
                script_path = "scripts/slime_bounce.js"
                script_full_path = os.path.join(scripts_dir, "slime_bounce.js")
                _write_slime_bounce_script(script_full_path)
                self._log("Wrote slime bounce script")

            write_vmap_file(output_vmap, meshes, materials, material_map,
                            scale=scale,
                            entity_meshes=entity_mesh_pairs if entity_mesh_pairs else None,
                            mesh_physics_types=mesh_physics_types,
                            mesh_disable_shadows=mesh_disable_shadows,
                            script_path=script_path,
                            light_sources=light_sources if light_sources else None)
            self._log(f"VMap written: {output_vmap}")
            if entity_mesh_pairs:
                self._log(f"  Included {len(entity_mesh_pairs)} entity meshes")
            if light_sources:
                self._log(f"  Included {len(light_sources)} light entities")

            # Free meshes after writing
            del meshes
            del entity_mesh_pairs
            gc.collect()
            self._set_stat("memory", self._mem_mb())

            # Step 7: Compile .vmat files with resource compiler
            vmat_paths = mat_gen.get_all_vmat_paths()
            if rc_path and os.path.isfile(rc_path) and vmat_paths:
                self._set_step("Step 7/7: Compiling materials")
                self._log(f"Step 7/7: Compiling {len(vmat_paths)} .vmat files in parallel...")
                self._set_progress(0.82, "Compiling materials...")

                compiled = 0
                failed = 0
                total_vmats = len(vmat_paths)

                def _compile_one(vmat):
                    try:
                        r = subprocess.run(
                            [rc_path, "-i", vmat],
                            capture_output=True, text=True, timeout=30,
                        )
                        return r.returncode == 0
                    except (subprocess.TimeoutExpired, OSError):
                        return False

                rc_workers = min(total_vmats, os.cpu_count() or 4)
                with ThreadPoolExecutor(max_workers=rc_workers) as executor:
                    futures = {executor.submit(_compile_one, v): v for v in vmat_paths}
                    done_count = 0
                    for future in as_completed(futures):
                        if self._cancel_flag.is_set():
                            executor.shutdown(wait=False, cancel_futures=True)
                            self._msg_queue.put(("error", "Cancelled"))
                            return
                        if future.result():
                            compiled += 1
                        else:
                            failed += 1
                        done_count += 1
                        pct = 0.82 + 0.16 * (done_count / total_vmats)
                        self._set_progress(pct, f"Compiling: {done_count}/{total_vmats}")

                self._log(f"Compiled: {compiled} OK, {failed} failed")
            elif vmat_paths and not rc_path:
                self._log("Step 7/7: Skipped — no resource compiler path set")
            elif vmat_paths and rc_path and not os.path.isfile(rc_path):
                self._log(f"Step 7/7: Skipped — resource compiler not found at: {rc_path}")
            else:
                self._log("Step 7/7: Skipped — no materials to compile")

            # Compile slime bounce script if it was written
            if has_slime and rc_path and os.path.isfile(rc_path):
                self._log("Compiling slime bounce script...")
                try:
                    r = subprocess.run(
                        [rc_path, "-i", script_full_path],
                        capture_output=True, text=True, timeout=30,
                    )
                    if r.returncode == 0:
                        self._log("Script compiled OK")
                    else:
                        self._log(f"Script compilation failed: {r.stderr[:200] if r.stderr else 'unknown error'}")
                except (subprocess.TimeoutExpired, OSError) as e:
                    self._log(f"Script compilation error: {e}")

            self._set_progress(1.0, "Done!")
            self._msg_queue.put(("done", output_vmap))

        except MemoryError:
            gc.collect()
            self._msg_queue.put(("error",
                "Out of memory! Try:\n"
                "• Use 'Single Mesh' or 'Per Block Type' output mode\n"
                "• Enable 'Cull Hidden Faces'\n"
                "• Convert a smaller structure\n"
                "• Close other applications"))
        except Exception as e:
            tb = traceback.format_exc()
            self._msg_queue.put(("error", f"{e}\n\n{tb}"))


def run_app():
    app = MCtoCSApp()
    app.mainloop()
