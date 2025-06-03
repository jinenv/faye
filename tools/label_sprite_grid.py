#!/usr/bin/env python3
# tools/label_sprite_grid.py

import os
from PIL import Image, ImageDraw, ImageFont

# ── CONFIGURATION ────────────────────────────────────────────────────────────

# 1) Where your master sprite-sheet lives (relative to project root):
SPRITE_SHEET_REL = os.path.join("assets", "ui", "item_icons.png")

# 2) Size of each icon/tile (in pixels):
TILE_W = 32
TILE_H = 32

# 3) Grid line and text colors / styling:
GRID_COLOR     = (255, 255, 255, 128)   # white, 50% opacity
LINE_THICKNESS = 1                      # 1px grid lines

LABEL_FONT_SIZE = 12
LABEL_COLOR     = (255, 255, 255, 255)  # solid white text

# 4) Output filename (in the same folder as the original sheet):
OUTPUT_FILENAME = "item_icons_labeled.png"
# ─────────────────────────────────────────────────────────────────────────────


def main():
    # Ensure we run from project root:
    project_root = os.getcwd()
    sprite_path = os.path.join(project_root, SPRITE_SHEET_REL)
    if not os.path.isfile(sprite_path):
        print(f"ERROR: Cannot find sprite sheet at:\n  {sprite_path}")
        return

    # Open the sheet:
    sheet = Image.open(sprite_path).convert("RGBA")
    sheet_w, sheet_h = sheet.size
    print(f"Loaded sprite sheet: {sprite_path}  ({sheet_w}×{sheet_h})")

    # Calculate how many columns and rows:
    cols = sheet_w // TILE_W
    rows = sheet_h // TILE_H

    # Create a transparent overlay for grid+labels:
    overlay = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # ① Draw grid lines:
    #   vertical lines at x = n*TILE_W
    for c in range(cols + 1):
        x = c * TILE_W
        draw.line([(x, 0), (x, sheet_h)], fill=GRID_COLOR, width=LINE_THICKNESS)

    #   horizontal lines at y = n*TILE_H
    for r in range(rows + 1):
        y = r * TILE_H
        draw.line([(0, y), (sheet_w, y)], fill=GRID_COLOR, width=LINE_THICKNESS)

    # ② Prepare a small font for labeling (fallback to default if needed):
    try:
        # You can point to your own .ttf if you like—just be sure the path is correct.
        font_path = os.path.join(project_root, "assets", "ui", "fonts", "PressStart2P.ttf")
        label_font = ImageFont.truetype(font_path, LABEL_FONT_SIZE)
    except Exception:
        label_font = ImageFont.load_default()

    # ③ Loop over each cell and draw "(c,r)" in the top-left corner of that cell:
    padding_x = 2  # tiny offset so text doesn’t sit exactly on the grid line
    padding_y = 0

    for r in range(rows):
        for c in range(cols):
            text = f"{c},{r}"
            x0 = c * TILE_W + padding_x
            y0 = r * TILE_H + padding_y
            draw.text((x0, y0), text, font=label_font, fill=LABEL_COLOR)

    # Composite the grid/labels on top of the original:
    combined = Image.alpha_composite(sheet, overlay)

    # Save next to the original sheet:
    output_path = os.path.join(os.path.dirname(sprite_path), OUTPUT_FILENAME)
    combined.save(output_path)
    print(f"Saved labeled grid to:\n  {output_path}")


if __name__ == "__main__":
    main()
