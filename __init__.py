# SPDX-FileCopyrightText: 2025-2026 The French Monkey
# SPDX-License-Identifier: GPL-3.0-or-later

bl_info = {
    "name": "Framer",
    "author": "The French Monkey",
    "version": (1, 0, 3),
    "blender": (4, 2, 0),
    "location": "Sidebar > Framer",
    "description": "Configure Camera Resolution and render settings",
    "category": "Render",
    "license": "GPL-3.0-or-later",
}

import bpy
import os
import json
import gpu
import math
import bpy_extras.view3d_utils
from gpu_extras.batch import batch_for_shader

try:
    from . import relay_updater
except ImportError:  # the Addon Collection has its own updates
    relay_updater = None

draw_handler = None

# ------------------------------
# Add-on Data Path / Preset File
# ------------------------------

def get_addon_data_path():
    addon_id = "framer"
    try:
        path = bpy.utils.extension_path_user(addon_id)
    except Exception:
        path = bpy.utils.user_resource('SCRIPTS', path=f"addons/{addon_id}", create=True)
    os.makedirs(path, exist_ok=True)
    return path

def get_preset_file():
    return os.path.join(get_addon_data_path(), "framer_presets.json")

# ------------------------------
# Preset File Helpers
# ------------------------------

def clean_presets(data):
    """Only well formed presets, so a hand edited file cannot break saving."""
    if not isinstance(data, list):
        return []
    return [p for p in data if isinstance(p, dict) and "name" in p]

def load_presets_from_file():
    fpath = get_preset_file()
    if not os.path.exists(fpath):
        return []
    try:
        with open(fpath, "r") as f:
            return clean_presets(json.load(f))
    except Exception:
        return []

def save_presets_to_file(presets):
    with open(get_preset_file(), "w") as f:
        json.dump(presets, f, indent=4)

def save_preset_to_file(preset_dict):
    presets = load_presets_from_file()
    presets = [p for p in presets if p['name'] != preset_dict['name']]
    presets.append(preset_dict)
    save_presets_to_file(presets)

def get_available_presets():
    presets = [p['name'] for p in load_presets_from_file()]
    return ["None"] + presets


def get_preset_by_name(name):
    for p in load_presets_from_file():
        if p['name'] == name:
            return p
    return None

# ------------------------------
# Presets
# ------------------------------

_PRESET_SIZES = [
    # --- Standard HD / UHD (Landscape) ---
    ("HD_720",       "HD 1280×720 (16:9)",          "HD 720×1280 (9:16)",          1280, 720,  False),
    ("FULL_HD_1080", "Full HD 1920×1080 (16:9)",    "Full HD 1080×1920 (9:16)",    1920, 1080, False),
    ("QHD_1440",     "QHD 2560×1440 (16:9)",        "QHD 1440×2560 (9:16)",        2560, 1440, False),
    ("UHD_4K",       "4K UHD 3840×2160 (16:9)",     "4K UHD 2160×3840 (9:16)",     3840, 2160, False),
    ("UHD_8K",       "8K UHD 7680×4320 (16:9)",     "8K UHD 4320×7680 (9:16)",     7680, 4320, False),

    # --- Cinema Formats ---
    ("DCI_2K",       "DCI 2K 2048×1080 (17:9)",     "DCI 2K 1080×2048 (9:17)",     2048, 1080, False),
    ("DCI_4K",       "DCI 4K 4096×2160 (17:9)",     "DCI 4K 2160×4096 (9:17)",     4096, 2160, False),
    ("CINEMASCOPE",  "Cinemascope 4096×1716 (2.39:1)", "Cinemascope 1716×4096 (1:2.39)", 4096, 1716, False),

    # --- Photography / Print ---
    ("PHOTO_3_2",    "Photo 3×2 – 3000×2000 (3:2)", "Photo 2×3 – 2000×3000 (2:3)", 3000, 2000, False),
    ("PHOTO_4_3",    "Photo 4×3 – 4000×3000 (4:3)", "Photo 3×4 – 3000×4000 (3:4)", 4000, 3000, False),
    ("SQUARE",       "Square 1080×1080 (1:1)",      "Square 1080×1080 (1:1)",      1080, 1080, False),

    # Instagram Portrait (4:5)
    ("IG_4_5_1080",  "Instagram Portrait 1080×1350 (4:5)", "Instagram Portrait 1080×1350 (4:5)", 1080, 1350, True),
    ("IG_4_5_2048",  "Instagram Portrait 2048×2560 (4:5)", "Instagram Portrait 2048×2560 (4:5)", 2048, 2560, True),

    # Stories / Reels (9:16)
    ("STORY_9_16_1080", "Story / Reel 1080×1920 (9:16)", "Story / Reel 1080×1920 (9:16)", 1080, 1920, True),
    ("STORY_9_16_1440", "Story / Reel 1440×2560 (9:16)", "Story / Reel 1440×2560 (9:16)", 1440, 2560, True),
    
    # Instagram Portrait (4:5)
    ("TFMSTYLE_4K_VERT", "TFMSTYLE 2160×3840 (9:16)", "TFMSTYLE 2160×3840 (9:16)", 2160, 3840, True),

    # --- Misc Landscape ---
    ("WUXGA",        "WUXGA 1920×1200 (16:10)",     "WUXGA 1200×1920 (10:16)",     1920, 1200, False),
    ("ULTRAWIDE",    "Ultrawide 3440×1440 (21:9)",  "Ultrawide 1440×3440 (9:21)",  3440, 1440, False),
    ("PANORAMA",     "Panorama 3840×1080 (32:9)",   "Panorama 1080×3840 (9:32)",   3840, 1080, False),
]

# ------------------------------
# Aspect Ratio Guides 
# ------------------------------

def framer_update_viewport():
    wm = getattr(bpy.context, "window_manager", None)
    if not wm:
        return 

    for win in wm.windows:
        scr = getattr(win, "screen", None)
        if not scr:
            continue
        for area in scr.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

def _vp_draw_quad_2d(shader, v0, v1, v2, v3, color):
    batch = batch_for_shader(shader, 'TRI_FAN', {"pos": [v0, v1, v2, v3]})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)

def _quad_from_line_2d(p1, p2, width_px):
    x1, y1 = p1
    x2, y2 = p2
    dx, dy = (x2 - x1), (y2 - y1)
    length = math.hypot(dx, dy)
    if length == 0:
        dx, dy = 1.0, 0.0
        length = 1.0
    nx, ny = dx / length, dy / length
    px, py = -ny, nx
    hw = width_px * 0.5
    ox, oy = px * hw, py * hw
    return ((x1 - ox, y1 - oy),
            (x1 + ox, y1 + oy),
            (x2 + ox, y2 + oy),
            (x2 - ox, y2 - oy))

def _draw_thick_line_2d(shader, p1, p2, width_px, color):
    v0, v1, v2, v3 = _quad_from_line_2d(p1, p2, width_px)
    _vp_draw_quad_2d(shader, v0, v1, v2, v3, color)

def _draw_rect_outline_2d(shader, left, right, bottom, top, width_px, color):
    _draw_thick_line_2d(shader, (left, bottom), (right, bottom), width_px, color)
    _draw_thick_line_2d(shader, (right, bottom), (right, top),    width_px, color)
    _draw_thick_line_2d(shader, (right, top),    (left, top),     width_px, color)
    _draw_thick_line_2d(shader, (left, top),     (left, bottom),  width_px, color)

def _draw_polyline_thick_2d(shader, points, width_px, color):
    for i in range(len(points) - 1):
        _draw_thick_line_2d(shader, points[i], points[i+1], width_px, color)

def framer_draw_aspect_guides():
    ctx = bpy.context
    s = getattr(ctx.scene, "framer_settings", None)
    if not s or not s.ShowAspectGuides:
        return

    space = ctx.space_data
    if not space or space.type != 'VIEW_3D':
        return
    rv3d = space.region_3d
    if rv3d.view_perspective != 'CAMERA':
        return

    region = ctx.region
    scene = ctx.scene
    cam = scene.camera
    if not cam:
        return

    frame = cam.data.view_frame(scene=scene)
    corners = []
    for v in frame:
        world = cam.matrix_world @ v
        p = bpy_extras.view3d_utils.location_3d_to_region_2d(region, rv3d, world)
        if p:
            corners.append((p.x, p.y))
    if len(corners) != 4:
        return

    left = min(p[0] for p in corners)
    right = max(p[0] for p in corners)
    bottom = min(p[1] for p in corners)
    top = max(p[1] for p in corners)
    width = right - left
    height = top - bottom

    gpu.state.blend_set('ALPHA')
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    color = (*s.GuideColor, 1.0)
    thickness = 2.0

    _draw_rect_outline_2d(shader, left, right, bottom, top, thickness, color)

    if s.ShowThirds and s.GridDivisions >= 2:
        n = int(s.GridDivisions)
        for i in range(1, n):
            x = left + width * (i / n)
            y = bottom + height * (i / n)
            _draw_thick_line_2d(shader, (x, bottom), (x, top), thickness, color)
            _draw_thick_line_2d(shader, (left, y), (right, y), thickness, color)

    if s.ShowDiagonals:
        _draw_thick_line_2d(shader, (left, bottom), (right, top), thickness, color)
        _draw_thick_line_2d(shader, (left, top), (right, bottom), thickness, color)

    if s.ShowCenter:
        cx = (left + right) / 2.0
        cy = (bottom + top) / 2.0
        half = 10.0
        _draw_thick_line_2d(shader, (cx - half, cy), (cx + half, cy), thickness, color)
        _draw_thick_line_2d(shader, (cx, cy - half), (cx, cy + half), thickness, color)

    if s.ShowSafeMask:
        m = s.SafeFrameMargin * 0.01
        l = left + width * m
        r = right - width * m
        b = bottom + height * m
        t = top - height * m
        _draw_rect_outline_2d(shader, l, r, b, t, thickness, color)

    gpu.state.blend_set('NONE')

def update_aspect_guides(self, context):
    global draw_handler
    if draw_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(draw_handler, 'WINDOW')
        draw_handler = None

    if self.ShowAspectGuides:
        def _add():
            global draw_handler
            draw_handler = bpy.types.SpaceView3D.draw_handler_add(
                framer_draw_aspect_guides, (), 'WINDOW', 'POST_PIXEL'
            )
            framer_update_viewport()
        bpy.app.timers.register(_add, first_interval=0.1)
    else:
        framer_update_viewport()
    
# ------------------------------
# Orientation-aware Resolutions
# ------------------------------

def _resolution_items(self, context):
    s = getattr(context.scene, "framer_settings", None)
    orient = getattr(s, "OrientationMode", 'HORIZ') if s else 'HORIZ'
    items = []

    for enum_id, label_h, label_v, x, y, vertical_only in _PRESET_SIZES:
        if orient == 'HORIZ' and vertical_only:
            continue

        if orient == 'VERT' and not vertical_only:
            continue

        if orient == 'HORIZ':
            name, xid, yid = label_h, x, y
        else:
            name, xid, yid = label_v, x, y

        items.append((enum_id, name, f"Resolution: {int(xid)} x {int(yid)}"))

    if not items:
        items = [("NONE", "No Presets", "No resolution presets available")]

    return items

def _apply_resolution_from_enum(context, enum_id):
    scene = context.scene 
    s = scene.framer_settings
    orient = s.OrientationMode

    rec = next((r for r in _PRESET_SIZES if r[0] == enum_id), None)
    if not rec:
        return

    _id, _lh, _lv, x, y, vertical_only = rec
    if orient == 'VERT' and not vertical_only:
        x, y = y, x

    r = scene.render
    r.resolution_x = int(x)
    r.resolution_y = int(y)

# ------------------------------
# Capture / Apply Render Settings
# ------------------------------

def capture_render_settings(scene):
    r = scene.render
    cycles = getattr(scene, "cycles", None)
    eevee = getattr(scene, "eevee", None)
    color_mgmt = scene.view_settings
    output = r.image_settings
    film = getattr(r, "film", None)

    data = {
        # --- Engine & Device ---
        "engine": r.engine,
        "use_persistent_data": getattr(r, "use_persistent_data", False),
        "feature_set": getattr(cycles, "feature_set", "SUPPORTED"),
        "device": getattr(cycles, "device", "GPU"),

        # --- Resolution & Format ---
        "resolution_x": r.resolution_x,
        "resolution_y": r.resolution_y,
        "resolution_percentage": r.resolution_percentage,
        "fps": r.fps,
        "filepath": r.filepath,
        "use_file_extension": getattr(r, "use_file_extension", True),
        "use_overwrite": getattr(r, "use_overwrite", True),
        "use_placeholder": getattr(r, "use_placeholder", False),

        # --- Output Settings ---
        "file_format": output.file_format,
        "color_mode": output.color_mode,
        "color_depth": output.color_depth,
        "compression": getattr(output, "compression", 0),
        "quality": getattr(output, "quality", 90),
        "use_preview": getattr(output, "use_preview", False),

        # --- Film ---
        "film_exposure": getattr(r, "film_exposure", 1.0),
        "film_filter_size": getattr(r, "film_filter_size", 1.5),
        "film_transparent": getattr(r, "film_transparent", False),
        "film_transparent_glass": getattr(r, "film_transparent_glass", False),

        # --- Motion Blur ---
        "use_motion_blur": getattr(r, "use_motion_blur", False),
        "motion_blur_shutter": getattr(r, "motion_blur_shutter", 0.5),
    }

    # --- Film subpanel ---
    if film:
        data.update({
            "film_grain": getattr(film, "grain", 0.0),
            "film_pixel_filter_type": getattr(film, "pixel_filter_type", "BLACKMAN_HARRIS"),
            "film_filter_width": getattr(film, "filter_width", 1.5),
            "film_use_highlight_compression": getattr(film, "use_highlight_compression", False),
            "film_highlight_compression": getattr(film, "highlight_compression", 1.0),
        })

    # --- Cycles: Sampling ---
    if cycles:
        data.update({
            "cycles_samples": cycles.samples,
            "cycles_preview_samples": cycles.preview_samples,
            "cycles_time_limit": getattr(cycles, "time_limit", 0),
            "cycles_use_adaptive_sampling": getattr(cycles, "use_adaptive_sampling", False),
            "cycles_adaptive_threshold": getattr(cycles, "adaptive_threshold", 0.01),
            "cycles_use_auto_tile": getattr(cycles, "use_auto_tile", False),
            "cycles_sample_offset": getattr(cycles, "sample_offset", 0),
            "cycles_sampling_pattern": getattr(cycles, "sampling_pattern", "SOBOL"),
            "cycles_light_sampling_threshold": getattr(cycles, "light_sampling_threshold", 0.01),
            "cycles_denoiser": getattr(cycles, "use_denoising", False),
        })

        # --- Cycles: Light Paths ---
        data.update({
            "cycles_max_bounces": cycles.max_bounces,
            "cycles_diffuse_bounces": cycles.diffuse_bounces,
            "cycles_glossy_bounces": cycles.glossy_bounces,
            "cycles_transmission_bounces": cycles.transmission_bounces,
            "cycles_volume_bounces": cycles.volume_bounces,
            "cycles_transparent_max_bounces": getattr(cycles, "transparent_max_bounces", 8),
            "cycles_transparent_min_bounces": getattr(cycles, "transparent_min_bounces", 0),
            "cycles_use_fast_gi": getattr(cycles, "use_fast_gi_approximation", False),
            "cycles_fast_gi_method": getattr(cycles, "fast_gi_method", "RENDER"),
            "cycles_caustics_reflective": getattr(cycles, "caustics_reflective", False),
            "cycles_caustics_refractive": getattr(cycles, "caustics_refractive", False),
            "cycles_clamp_direct": getattr(cycles, "sample_clamp_direct", 0.0),
            "cycles_clamp_indirect": getattr(cycles, "sample_clamp_indirect", 0.0),
        })

        # --- Cycles: Volumes ---
        data.update({
            "cycles_volume_step_rate": getattr(cycles, "volume_step_rate", 1.0),
            "cycles_volume_max_steps": getattr(cycles, "volume_max_steps", 1024),
            "cycles_use_volume_light_cache": getattr(cycles, "use_volume_light_cache", False),
        })

        # --- Cycles: Curves ---
        data.update({
            "cycles_curve_subdivisions": getattr(cycles, "curve_subdivisions", 2),
            "cycles_curve_min_pixels": getattr(cycles, "curve_min_pixels", 1.0),
        })

        # --- Cycles: Simplify ---
        data.update({
            "cycles_use_simplify": getattr(cycles, "use_simplify", False),
            "cycles_simplify_subdivision": getattr(cycles, "simplify_subdivision_render", 6),
            "cycles_simplify_child_particles": getattr(cycles, "simplify_child_particles", 1.0),
            "cycles_simplify_shadow_catcher": getattr(cycles, "simplify_shadow_catcher", False),
        })

        # --- Cycles: Performance ---
        data.update({
            "cycles_use_auto_tile": getattr(cycles, "use_auto_tile", False),
            "cycles_tile_size": getattr(cycles, "tile_size", 256),
            "cycles_threads_mode": getattr(cycles, "threads_mode", "AUTO"),
            "cycles_threads": getattr(cycles, "threads", 0),
            "cycles_use_progressive_refine": getattr(cycles, "use_progressive_refine", False),
            "cycles_use_persistent_data": getattr(cycles, "use_persistent_data", False),
        })

        # --- Cycles: Bake ---
        data.update({
            "cycles_bake_type": getattr(cycles, "bake_type", "COMBINED"),
            "cycles_bake_margin": getattr(cycles, "bake_margin", 16),
            "cycles_bake_margin_type": getattr(cycles, "bake_margin_type", "ADJACENT_FACES"),
            "cycles_use_bake_selected_to_active": getattr(cycles, "use_bake_selected_to_active", False),
            "cycles_use_bake_clear": getattr(cycles, "use_bake_clear", True),
            "cycles_use_bake_multires": getattr(cycles, "use_bake_multires", False),
        })

    # --- Eevee / Eevee Next ---
    if eevee:
        data.update({
            "eevee_taa_render_samples": getattr(eevee, "taa_render_samples", 64),
            "eevee_taa_viewport_samples": getattr(eevee, "taa_samples", 16),
            "eevee_use_bloom": getattr(eevee, "use_bloom", False),
            "eevee_bloom_intensity": getattr(eevee, "bloom_intensity", 0.05),
            "eevee_use_motion_blur": getattr(eevee, "use_motion_blur", False),
            "eevee_motion_blur_shutter": getattr(eevee, "motion_blur_shutter", 0.5),
            "eevee_use_volumetric_lights": getattr(eevee, "use_volumetric_lights", False),
            "eevee_volumetric_end": getattr(eevee, "volumetric_end", 100.0),
            "eevee_use_ssr": getattr(eevee, "use_ssr", False),
            "eevee_use_gtao": getattr(eevee, "use_gtao", False),
            "eevee_use_raytracing": getattr(eevee, "use_raytracing", False),
            "eevee_raytracing_method": getattr(eevee, "ray_tracing_method", "SCREEN"),
        })

    # --- Freestyle ---
    if hasattr(scene, "render") and hasattr(scene.render, "use_freestyle"):
        data["use_freestyle"] = scene.render.use_freestyle
        data["line_thickness_mode"] = getattr(scene.render, "line_thickness_mode", "ABSOLUTE")
        data["line_thickness"] = getattr(scene.render, "line_thickness", 1.0)

    # --- Grease Pencil ---
    if hasattr(scene, "grease_pencil_settings"):
        gp = scene.grease_pencil_settings
        data.update({
            "gp_antialias_threshold": getattr(gp, "antialias_threshold", 1.0),
            "gp_use_fast_stroke_mode": getattr(gp, "use_fast_stroke_mode", False),
        })

    # --- Color Management ---
    data.update({
        "view_transform": color_mgmt.view_transform,
        "look": color_mgmt.look,
        "exposure": color_mgmt.exposure,
        "gamma": color_mgmt.gamma,
        "use_curve_mapping": getattr(color_mgmt, "use_curve_mapping", False),
    })

    return data

def apply_render_preset(scene, preset_data):
    """Apply all render-related settings from a saved preset."""
    r = scene.render
    cycles = getattr(scene, "cycles", None)
    eevee = getattr(scene, "eevee", None)
    color_mgmt = scene.view_settings
    output = r.image_settings
    film = getattr(r, "film", None)

    # --- Engine / Device ---
    if "engine" in preset_data:
        r.engine = preset_data["engine"]
    if cycles:
        if "feature_set" in preset_data:
            cycles.feature_set = preset_data["feature_set"]
        if "device" in preset_data:
            cycles.device = preset_data["device"]

    # --- Resolution & Format ---
    r.resolution_x = preset_data.get("resolution_x", r.resolution_x)
    r.resolution_y = preset_data.get("resolution_y", r.resolution_y)
    r.resolution_percentage = preset_data.get("resolution_percentage", r.resolution_percentage)
    r.fps = preset_data.get("fps", r.fps)
    r.filepath = preset_data.get("filepath", r.filepath)
    r.use_file_extension = preset_data.get("use_file_extension", r.use_file_extension)
    r.use_overwrite = preset_data.get("use_overwrite", r.use_overwrite)
    r.use_placeholder = preset_data.get("use_placeholder", r.use_placeholder)

    # --- Output ---
    output.file_format = preset_data.get("file_format", output.file_format)
    output.color_mode = preset_data.get("color_mode", output.color_mode)
    output.color_depth = preset_data.get("color_depth", output.color_depth)
    if "compression" in preset_data:
        output.compression = preset_data["compression"]
    if "quality" in preset_data:
        output.quality = preset_data["quality"]
    if "use_preview" in preset_data:
        output.use_preview = preset_data["use_preview"]

    # --- Film ---
    if hasattr(r, "film"):
        film = r.film
        if "film_exposure" in preset_data:
            setattr(film, "exposure", preset_data["film_exposure"])
        if "film_filter_size" in preset_data and hasattr(film, "filter_size"):
            film.filter_size = preset_data["film_filter_size"]
        if "film_transparent" in preset_data:
            r.film_transparent = preset_data["film_transparent"]
        if "film_transparent_glass" in preset_data and hasattr(film, "use_transparent_glass"):
            film.use_transparent_glass = preset_data["film_transparent_glass"]
    else:
        # Fallback for older Blender versions
        if hasattr(r, "film_exposure"):
            r.film_exposure = preset_data.get("film_exposure", getattr(r, "film_exposure", 1.0))
        if hasattr(r, "film_filter_size"):
            r.film_filter_size = preset_data.get("film_filter_size", getattr(r, "film_filter_size", 1.5))
        if hasattr(r, "film_transparent"):
            r.film_transparent = preset_data.get("film_transparent", getattr(r, "film_transparent", False))
        if hasattr(r, "film_transparent_glass"):
            r.film_transparent_glass = preset_data.get("film_transparent_glass", getattr(r, "film_transparent_glass", False))

    # --- Motion Blur ---
    if hasattr(r, "use_motion_blur"):
        r.use_motion_blur = preset_data.get("use_motion_blur", r.use_motion_blur)
    if hasattr(r, "motion_blur_shutter"):
        r.motion_blur_shutter = preset_data.get("motion_blur_shutter", r.motion_blur_shutter)

    # --- Film Subpanel ---
    if film:
        if "film_grain" in preset_data:
            film.grain = preset_data["film_grain"]
        if "film_pixel_filter_type" in preset_data:
            film.pixel_filter_type = preset_data["film_pixel_filter_type"]
        if "film_filter_width" in preset_data:
            film.filter_width = preset_data["film_filter_width"]
        if hasattr(film, "use_highlight_compression"):
            film.use_highlight_compression = preset_data.get("film_use_highlight_compression", film.use_highlight_compression)
        if hasattr(film, "highlight_compression"):
            film.highlight_compression = preset_data.get("film_highlight_compression", film.highlight_compression)

    # --- Cycles ---
    if cycles:
        # Sampling
        cycles.samples = preset_data.get("cycles_samples", cycles.samples)
        cycles.preview_samples = preset_data.get("cycles_preview_samples", cycles.preview_samples)
        if "cycles_time_limit" in preset_data:
            cycles.time_limit = preset_data["cycles_time_limit"]
        if "cycles_use_adaptive_sampling" in preset_data:
            cycles.use_adaptive_sampling = preset_data["cycles_use_adaptive_sampling"]
        if "cycles_adaptive_threshold" in preset_data:
            cycles.adaptive_threshold = preset_data["cycles_adaptive_threshold"]
        if "cycles_use_auto_tile" in preset_data:
            cycles.use_auto_tile = preset_data["cycles_use_auto_tile"]
        if "cycles_sample_offset" in preset_data:
            cycles.sample_offset = preset_data["cycles_sample_offset"]
        if "cycles_sampling_pattern" in preset_data:
            cycles.sampling_pattern = preset_data["cycles_sampling_pattern"]
        if "cycles_light_sampling_threshold" in preset_data:
            cycles.light_sampling_threshold = preset_data["cycles_light_sampling_threshold"]
        if "cycles_denoiser" in preset_data:
            cycles.use_denoising = preset_data["cycles_denoiser"]

        # Light Paths
        cycles.max_bounces = preset_data.get("cycles_max_bounces", cycles.max_bounces)
        cycles.diffuse_bounces = preset_data.get("cycles_diffuse_bounces", cycles.diffuse_bounces)
        cycles.glossy_bounces = preset_data.get("cycles_glossy_bounces", cycles.glossy_bounces)
        cycles.transmission_bounces = preset_data.get("cycles_transmission_bounces", cycles.transmission_bounces)
        cycles.volume_bounces = preset_data.get("cycles_volume_bounces", cycles.volume_bounces)
        if hasattr(cycles, "transparent_max_bounces"):
            cycles.transparent_max_bounces = preset_data.get("cycles_transparent_max_bounces", cycles.transparent_max_bounces)
        if hasattr(cycles, "transparent_min_bounces"):
            cycles.transparent_min_bounces = preset_data.get("cycles_transparent_min_bounces", cycles.transparent_min_bounces)
        if hasattr(cycles, "use_fast_gi_approximation"):
            cycles.use_fast_gi_approximation = preset_data.get("cycles_use_fast_gi", cycles.use_fast_gi_approximation)
        if hasattr(cycles, "fast_gi_method"):
            cycles.fast_gi_method = preset_data.get("cycles_fast_gi_method", cycles.fast_gi_method)
        if hasattr(cycles, "caustics_reflective"):
            cycles.caustics_reflective = preset_data.get("cycles_caustics_reflective", cycles.caustics_reflective)
        if hasattr(cycles, "caustics_refractive"):
            cycles.caustics_refractive = preset_data.get("cycles_caustics_refractive", cycles.caustics_refractive)
        if hasattr(cycles, "sample_clamp_direct"):
            cycles.sample_clamp_direct = preset_data.get("cycles_clamp_direct", cycles.sample_clamp_direct)
        if hasattr(cycles, "sample_clamp_indirect"):
            cycles.sample_clamp_indirect = preset_data.get("cycles_clamp_indirect", cycles.sample_clamp_indirect)

        # Volumes
        if hasattr(cycles, "volume_step_rate"):
            cycles.volume_step_rate = preset_data.get("cycles_volume_step_rate", cycles.volume_step_rate)
        if hasattr(cycles, "volume_max_steps"):
            cycles.volume_max_steps = preset_data.get("cycles_volume_max_steps", cycles.volume_max_steps)
        if hasattr(cycles, "use_volume_light_cache"):
            cycles.use_volume_light_cache = preset_data.get("cycles_use_volume_light_cache", cycles.use_volume_light_cache)

        # Curves
        if hasattr(cycles, "curve_subdivisions"):
            cycles.curve_subdivisions = preset_data.get("cycles_curve_subdivisions", cycles.curve_subdivisions)
        if hasattr(cycles, "curve_min_pixels"):
            cycles.curve_min_pixels = preset_data.get("cycles_curve_min_pixels", cycles.curve_min_pixels)

        # Simplify
        if hasattr(cycles, "use_simplify"):
            cycles.use_simplify = preset_data.get("cycles_use_simplify", cycles.use_simplify)
        if hasattr(cycles, "simplify_subdivision_render"):
            cycles.simplify_subdivision_render = preset_data.get("cycles_simplify_subdivision", cycles.simplify_subdivision_render)
        if hasattr(cycles, "simplify_child_particles"):
            cycles.simplify_child_particles = preset_data.get("cycles_simplify_child_particles", cycles.simplify_child_particles)
        if hasattr(cycles, "simplify_shadow_catcher"):
            cycles.simplify_shadow_catcher = preset_data.get("cycles_simplify_shadow_catcher", cycles.simplify_shadow_catcher)

        # Performance
        if hasattr(cycles, "tile_size"):
            cycles.tile_size = preset_data.get("cycles_tile_size", cycles.tile_size)
        if hasattr(cycles, "threads_mode"):
            cycles.threads_mode = preset_data.get("cycles_threads_mode", cycles.threads_mode)
        if hasattr(cycles, "threads"):
            cycles.threads = preset_data.get("cycles_threads", cycles.threads)
        if hasattr(cycles, "use_progressive_refine"):
            cycles.use_progressive_refine = preset_data.get("cycles_use_progressive_refine", cycles.use_progressive_refine)
        if hasattr(cycles, "use_persistent_data"):
            cycles.use_persistent_data = preset_data.get("cycles_use_persistent_data", cycles.use_persistent_data)

        # Bake
        if hasattr(cycles, "bake_type"):
            cycles.bake_type = preset_data.get("cycles_bake_type", cycles.bake_type)
        if hasattr(cycles, "bake_margin"):
            cycles.bake_margin = preset_data.get("cycles_bake_margin", cycles.bake_margin)
        if hasattr(cycles, "bake_margin_type"):
            cycles.bake_margin_type = preset_data.get("cycles_bake_margin_type", cycles.bake_margin_type)
        if hasattr(cycles, "use_bake_selected_to_active"):
            cycles.use_bake_selected_to_active = preset_data.get("cycles_use_bake_selected_to_active", cycles.use_bake_selected_to_active)
        if hasattr(cycles, "use_bake_clear"):
            cycles.use_bake_clear = preset_data.get("cycles_use_bake_clear", cycles.use_bake_clear)
        if hasattr(cycles, "use_bake_multires"):
            cycles.use_bake_multires = preset_data.get("cycles_use_bake_multires", cycles.use_bake_multires)

    # --- Eevee (Legacy + Next Compatibility) ---
    if eevee:
        # Universal sample settings
        if hasattr(eevee, "taa_render_samples"):
            eevee.taa_render_samples = preset_data.get("eevee_taa_render_samples", eevee.taa_render_samples)
        if hasattr(eevee, "taa_samples"):
            eevee.taa_samples = preset_data.get("eevee_taa_viewport_samples", eevee.taa_samples)

        # Eevee Legacy (< 4.0)
        if hasattr(eevee, "use_bloom"):
            eevee.use_bloom = preset_data.get("eevee_use_bloom", eevee.use_bloom)
            eevee.bloom_intensity = preset_data.get("eevee_bloom_intensity", eevee.bloom_intensity)
            eevee.use_motion_blur = preset_data.get("eevee_use_motion_blur", eevee.use_motion_blur)
            eevee.motion_blur_shutter = preset_data.get("eevee_motion_blur_shutter", eevee.motion_blur_shutter)
            eevee.use_volumetric_lights = preset_data.get("eevee_use_volumetric_lights", eevee.use_volumetric_lights)
            eevee.volumetric_end = preset_data.get("eevee_volumetric_end", eevee.volumetric_end)
            eevee.use_ssr = preset_data.get("eevee_use_ssr", eevee.use_ssr)
            eevee.use_gtao = preset_data.get("eevee_use_gtao", eevee.use_gtao)
            eevee.use_raytracing = preset_data.get("eevee_use_raytracing", eevee.use_raytracing)

        # Eevee Next (≥ 4.0)
        else:
            if hasattr(eevee, "bloom_enabled"):
                eevee.bloom_enabled = preset_data.get("eevee_use_bloom", eevee.bloom_enabled)
            if hasattr(eevee, "bloom_intensity"):
                eevee.bloom_intensity = preset_data.get("eevee_bloom_intensity", eevee.bloom_intensity)
            if hasattr(eevee, "motion_blur_enable"):
                eevee.motion_blur_enable = preset_data.get("eevee_use_motion_blur", eevee.motion_blur_enable)
            if hasattr(eevee, "motion_blur_shutter"):
                eevee.motion_blur_shutter = preset_data.get("eevee_motion_blur_shutter", eevee.motion_blur_shutter)
            if hasattr(eevee, "volumetric_lights_enable"):
                eevee.volumetric_lights_enable = preset_data.get("eevee_use_volumetric_lights", eevee.volumetric_lights_enable)
            if hasattr(eevee, "volumetric_end"):
                eevee.volumetric_end = preset_data.get("eevee_volumetric_end", eevee.volumetric_end)
            if hasattr(eevee, "ray_tracing_enabled"):
                eevee.ray_tracing_enabled = preset_data.get("eevee_use_ssr", eevee.ray_tracing_enabled)
            if hasattr(eevee, "use_ambient_occlusion"):
                eevee.use_ambient_occlusion = preset_data.get("eevee_use_gtao", eevee.use_ambient_occlusion)

    # --- Freestyle ---
    if hasattr(scene.render, "use_freestyle"):
        scene.render.use_freestyle = preset_data.get("use_freestyle", scene.render.use_freestyle)
        if "line_thickness_mode" in preset_data:
            scene.render.line_thickness_mode = preset_data["line_thickness_mode"]
        if "line_thickness" in preset_data:
            scene.render.line_thickness = preset_data["line_thickness"]

    # --- Grease Pencil (Legacy Only) ---
    if hasattr(scene, "grease_pencil_settings"):
        gp = scene.grease_pencil_settings
        if hasattr(gp, "antialias_threshold") and "gp_antialias_threshold" in preset_data:
            gp.antialias_threshold = preset_data["gp_antialias_threshold"]
        if hasattr(gp, "use_fast_stroke_mode") and "gp_use_fast_stroke_mode" in preset_data:
            gp.use_fast_stroke_mode = preset_data["gp_use_fast_stroke_mode"]
    else:
        # Grease Pencil 3.0+ (Blender 4.x) has no scene-level grease pencil settings
        pass

    # --- Color Management ---
    color_mgmt.view_transform = preset_data.get("view_transform", color_mgmt.view_transform)
    color_mgmt.look = preset_data.get("look", color_mgmt.look)
    color_mgmt.exposure = preset_data.get("exposure", color_mgmt.exposure)
    color_mgmt.gamma = preset_data.get("gamma", color_mgmt.gamma)
    if hasattr(color_mgmt, "use_curve_mapping"):
        color_mgmt.use_curve_mapping = preset_data.get("use_curve_mapping", color_mgmt.use_curve_mapping)

# ------------------------------
# Operators
# ------------------------------

class FRAMER_OT_apply_changes(bpy.types.Operator):
    bl_idname = "framer.apply_changes"
    bl_label = "Apply Changes"
    bl_description = "Apply the selected orientation, resolution, and (optionally) render preset"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        s = scene.framer_settings

        if s.ResolutionPreset:
            class _FakeContext:
                def __init__(self, scn):
                    self.scene = scn
            _apply_resolution_from_enum(_FakeContext(scene), s.ResolutionPreset)

        if s.SelectedPreset and s.SelectedPreset.lower() != "none":
            preset = get_preset_by_name(s.SelectedPreset)
            if preset:
                apply_render_preset(scene, preset["settings"])
                self.report({'INFO'}, f"Applied render preset: {s.SelectedPreset}")
            else:
                self.report({'WARNING'}, f"Render preset '{s.SelectedPreset}' not found")

        return {'FINISHED'}

class FRAMER_OT_save_preset(bpy.types.Operator):
    bl_idname = "framer.save_preset"
    bl_label = "Save Current Render Settings"
    preset_name: bpy.props.StringProperty(name="Preset Name")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        name = self.preset_name.strip()
        if not name:
            self.report({'WARNING'}, "Preset name cannot be empty.")
            return {'CANCELLED'}
        data = capture_render_settings(context.scene)
        save_preset_to_file({"name": name, "settings": data})
        context.scene.framer_settings.SelectedPreset = name
        self.report({'INFO'}, f"Saved render preset: {name}")
        return {'FINISHED'}

class FRAMER_OT_load_preset(bpy.types.Operator):
    bl_idname = "framer.load_preset"
    bl_label = "Select Render Preset"
    preset_name: bpy.props.StringProperty()

    def execute(self, context):
        s = context.scene.framer_settings
        s.SelectedPreset = self.preset_name
        self.report({'INFO'}, f"Selected render preset: {self.preset_name}")
        return {'FINISHED'}


class FRAMER_OT_delete_preset(bpy.types.Operator):
    bl_idname = "framer.delete_preset"
    bl_label = "Delete Render Preset"

    def execute(self, context):
        s = context.scene.framer_settings
        if not s.SelectedPreset:
            self.report({'WARNING'}, "No preset selected.")
            return {'CANCELLED'}
        presets = load_presets_from_file()
        new = [p for p in presets if p['name'] != s.SelectedPreset]
        save_presets_to_file(new)
        s.SelectedPreset = ""
        self.report({'INFO'}, "Preset deleted.")
        return {'FINISHED'}

# ------------------------------
# Preset Menu
# ------------------------------

class FRAMER_MT_presets_menu(bpy.types.Menu):
    bl_label = "Framer Presets"
    bl_idname = "FRAMER_MT_presets_menu"

    def draw(self, context):
        layout = self.layout
        presets = get_available_presets()

        op = layout.operator("framer.select_none", text="None", icon="X")
        op.clear_selection = True

        layout.separator()

        if len(presets) <= 1:
            layout.label(text="No presets saved")
        else:
            for p in presets[1:]:
                op = layout.operator("framer.load_preset", text=p)
                op.preset_name = p

class FRAMER_OT_select_none(bpy.types.Operator):
    bl_idname = "framer.select_none"
    bl_label = "Clear Render Preset"
    bl_description = "Select 'None' to disable applying any render preset"
    clear_selection: bpy.props.BoolProperty(default=False)

    def execute(self, context):
        s = context.scene.framer_settings
        s.SelectedPreset = ""
        self.report({'INFO'}, "Render preset cleared (None selected)")
        return {'FINISHED'}

# ------------------------------
# Property Group
# ------------------------------

class FramerSettings(bpy.types.PropertyGroup):
    SelectedPreset: bpy.props.StringProperty(default="")
    OrientationMode: bpy.props.EnumProperty(name="Orientation", items=[('HORIZ', "Horizontal", ""), ('VERT', "Vertical", "")], default='HORIZ')
    ResolutionPreset: bpy.props.EnumProperty(name="Resolution Preset", items=_resolution_items)

    ShowAspectGuides: bpy.props.BoolProperty(name="Show Aspect Ratio Guides", default=False, update=lambda self, ctx: update_aspect_guides(self, ctx))
    GuideColor: bpy.props.FloatVectorProperty(name="Guide Color", subtype='COLOR', default=(1.0, 0.85, 0.0), min=0.0, max=1.0, update=lambda self, ctx: framer_update_viewport())

    ShowThirds: bpy.props.BoolProperty(name="Show Grid / Thirds", default=True, update=lambda self, ctx: framer_update_viewport())
    GridDivisions: bpy.props.IntProperty(name="Grid Divisions", default=3, min=2, max=24, update=lambda self, ctx: framer_update_viewport())
    ShowDiagonals: bpy.props.BoolProperty(name="Show Diagonals", default=False, update=lambda self, ctx: framer_update_viewport())

    ShowCenter: bpy.props.BoolProperty(name="Show Center Crosshair", default=True, update=lambda self, ctx: framer_update_viewport())
    ShowSafeMask: bpy.props.BoolProperty(name="Show Safe Frame", default=False, update=lambda self, ctx: framer_update_viewport())
    SafeFrameMargin: bpy.props.FloatProperty(name="Safe Frame Margin (%)", default=10.0, min=0.0, max=20.0, update=lambda self, ctx: framer_update_viewport())

# ------------------------------
# UI
# ------------------------------

class VIEW3D_PT_framer(bpy.types.Panel):
    bl_label = "Framer"
    bl_idname = "VIEW3D_PT_framer"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Framer'

    def draw(self, context):
        if relay_updater:
            relay_updater.draw(self.layout)
        layout = self.layout
        s = context.scene.framer_settings

        layout.operator("framer.apply_changes", icon="SCENE", text="Apply Changes")
        layout.separator(factor=0.5)

        layout.prop(s, "OrientationMode", expand=True)
        layout.prop(s, "ResolutionPreset", text="")

        layout.prop(s, "ShowAspectGuides", text="Show Guides", toggle=True)

        if s.ShowAspectGuides:
            col = layout.column(align=True)
            col.prop(s, "GuideColor", text="")
            col.prop(s, "ShowThirds", toggle=True)

            if s.ShowThirds:
                col.prop(s, "GridDivisions", slider=True)

            col.prop(s, "ShowDiagonals", toggle=True)
            col.prop(s, "ShowCenter", toggle=True)
            col.prop(s, "ShowSafeMask", toggle=True)

            if s.ShowSafeMask:
                col.prop(s, "SafeFrameMargin", slider=True)

        row = layout.row(align=True)
        row.label(text="Render Preset", icon="RENDER_RESULT")
        row.menu(
            "FRAMER_MT_presets_menu",
            text=s.SelectedPreset if s.SelectedPreset else "Select Preset",
            icon="DOWNARROW_HLT"
        )

        if s.SelectedPreset:
            layout.operator("framer.delete_preset", text="Delete Selected Preset", icon="TRASH")

        layout.operator("framer.save_preset", icon="FILE_TICK")

# ------------------------------
# Registration
# ------------------------------

classes = (
    FramerSettings,
    FRAMER_OT_apply_changes,
    FRAMER_OT_save_preset,
    FRAMER_OT_load_preset,
    FRAMER_OT_delete_preset,
    FRAMER_OT_select_none,
    FRAMER_MT_presets_menu,
    VIEW3D_PT_framer,
)

def register():
    if relay_updater:
        relay_updater.register("blender-framer")
    from bpy.utils import register_class
    global draw_handler
    draw_handler = None

    for cls in classes:
        try:
            register_class(cls)
        except ValueError:
            bpy.utils.unregister_class(cls)
            register_class(cls)

    bpy.types.Scene.framer_settings = bpy.props.PointerProperty(type=FramerSettings)
    bpy.app.timers.register(lambda: (framer_update_viewport() or None), first_interval=0.1)

def unregister():
    if relay_updater:
        relay_updater.unregister()
    from bpy.utils import unregister_class
    global draw_handler

    if draw_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(draw_handler, 'WINDOW')
        draw_handler = None

    if hasattr(bpy.types.Scene, "framer_settings"):
        del bpy.types.Scene.framer_settings

    for cls in reversed(classes):
        try:
            unregister_class(cls)
        except RuntimeError:
            pass

    framer_update_viewport()

if __name__ == "__main__":
    register()
