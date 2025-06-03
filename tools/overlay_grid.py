#!/usr/bin/env python3
# tools/overlay_grid.py

import os
from PIL import Image, ImageDraw

# ── CONFIGURATION ─────────────────────────────────────────────────────────

# 1) Relative path (from project root) to your full sprite sheet:
SPRITE_SHEET_REL_PATH = os.path.join("assets", "ui", "item_icons.png")

# 2) The size (in pixels) of each individual icon tile.
TILE_WIDTH = 32
TILE_HEIGHT = 32

# 3) Color and line thickness for the grid overlay:
GRID_COLOR = (255, 255, 255, 128)   # white at 50% opacity
LINE_THICKNESS = 1                  # 1-pixel lines

# 4) Output filename (placed next to the original sheet):
OUTPUT_FILENAME = "item_icons_with_grid.png"
# ────────────────────────────────────────────────────────────────────────────


def main():
    # Make sure we’re running from the project root:
    project_root = os.getcwd()
    sprite_sheet_path = os.path.join(project_root, SPRITE_SHEET_REL_PATH)

    if not os.path.isfile(sprite_sheet_path):
        print(f"ERROR: Could not find sprite sheet at:\n  {sprite_sheet_path}")
        print("Make sure your sheet is named exactly 'item_icons.png' in assets/ui.")
        return

    # Open the sprite sheet:
    sheet = Image.open(sprite_sheet_path).convert("RGBA")
    sheet_w, sheet_h = sheet.size
    print(f"Loaded sheet: {sprite_sheet_path}  (size: {sheet_w}×{sheet_h})")

    # Create an empty RGBA image for our grid overlay:
    overlay = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Draw vertical grid lines every TILE_WIDTH pixels:
    x = 0
    while x <= sheet_w:
        draw.line(
            [(x, 0), (x, sheet_h)],
            fill=GRID_COLOR,
            width=LINE_THICKNESS
        )
        x += TILE_WIDTH

    # Draw horizontal grid lines every TILE_HEIGHT pixels:
    y = 0
    while y <= sheet_h:
        draw.line(
            [(0, y), (sheet_w, y)],
            fill=GRID_COLOR,
            width=LINE_THICKNESS
        )
        y += TILE_HEIGHT

    # Composite the grid overlay on top of the sheet:
    combined = Image.alpha_composite(sheet, overlay)

    # Save into the same folder as the original sheet:
    out_path = os.path.join(os.path.dirname(sprite_sheet_path), OUTPUT_FILENAME)
    combined.save(out_path)
    print(f"Saved grid‐overlay image to:\n  {out_path}")


if __name__ == "__main__":
    main()

