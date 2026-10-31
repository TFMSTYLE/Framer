# Framer

![framer-thumb](https://github.com/user-attachments/assets/42442271-bebe-41dc-8d0f-b795d7de0fd5)

**Author:** The French Monkey (TFMSTYLE)  
**Version:** 1.0.3  

---

## Overview

Framer is a **camera and render configuration manager** for Blender that simplifies resolution, orientation, and render preset management.  
It allows artists to quickly switch between standard aspect ratios, save and load complex render settings, and apply presets with a single click.  
Framer is ideal for managing multiple output formats such as cinematic, social media, and print layouts — all within a unified, non-destructive workflow.

---

## Parameters

### Orientation
Determines the camera frame orientation.

- **Horizontal:** Landscape layout, ideal for cinematic and widescreen formats.  
- **Vertical:** Portrait layout, used for mobile content, social media, or posters.

---

### Resolution Preset
Selects a predefined resolution matching the chosen **Orientation**.  
Includes a comprehensive range of professional and social media formats:

- **HD / UHD:** 720p, 1080p, 1440p, 4K, 8K  
- **Cinema:** DCI 2K, DCI 4K, Cinemascope  
- **Photography:** 3:2, 4:3, Square  
- **Instagram Portraits:** 4:5 ratios  
- **Stories / Reels:** 9:16  
- **Ultrawide & Panorama:** Extended cinematic and widescreen formats  

---

### Selected Preset
Displays the name of the currently active **render settings preset**.  
This can be saved, applied, or cleared using the preset management tools.

---

## Operators

### Apply Changes
Applies the chosen **Orientation**, **Resolution Preset**, and optionally, a **Render Preset**.  
Automatically adjusts the render dimensions and loads any stored settings.

---

### Save Current Render Settings
Captures all current render configuration values, including:

- Resolution, frame rate, and output path  
- Render engine (Cycles, Eevee, Eevee Next)  
- Sampling, motion blur, and adaptive sampling  
- Film exposure and transparency  
- Output color depth, compression, and format  
- Cycles light paths, bounces, and denoising  
- Eevee post-processing (bloom, AO, SSR, motion blur)  
- Color management and Freestyle settings  

Stores the captured configuration as a named preset in the local `framer_presets.json` file.

---

### Select Render Preset
Assigns an existing render preset from the saved collection.  
The preset is loaded into the scene but not applied until **Apply Changes** is executed.

---

### Delete Render Preset
Removes the selected render preset permanently from the local preset file.

---

### Clear Render Preset
Resets the active preset selection to **None**, ensuring no render preset will be applied during changes.

---

## Menus

### Framer Presets
A dynamic menu listing all user-created render presets.  
Displays options to select a preset or clear the current selection.

---

## Usage Notes

- **Framer** manages both **resolution presets** and **full render presets** independently.  
- Orientation-aware logic automatically filters presets — only vertical or horizontal formats are shown based on your selection.  
- All presets are stored locally for persistence between sessions.  
- Saved presets can include complex Cycles and Eevee configurations for consistent output.  
- The system is designed for cross-project reuse, supporting both artistic and production workflows.  
- Ideal for setting up multiple output targets such as cinematic frames, social media exports, or print-ready renders.

---

## Install

Needs Blender 4.2 or later. Get the zip from [tfmstyle.com](https://tfmstyle.com), then in Blender open Edit > Preferences > Get Extensions, open the menu at the top right and pick Install from Disk.

To build the zip yourself, run this in the repo folder:

```bash
blender --command extension build
```

The addon is `__init__.py`, plus `relay_updater.py` for its update checks. It depends on nothing but Blender.

---

## License

GPL 3.0 or later. See [LICENSE](LICENSE).
