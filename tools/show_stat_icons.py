# tools/show_stat_icons.py  (Pillow-only)

import json, os
from PIL import Image

CFG  = json.load(open("data/config/stat_icons.json"))
SHEET_PATH = os.path.join("assets", CFG["sprite_sheet"])
TILE = CFG["tile_size"]

sheet = Image.open(SHEET_PATH).convert("RGBA")

rows = len(CFG["icons"])
strip = Image.new("RGBA", (TILE, rows * TILE), (0, 0, 0, 0))

for idx, (key, (col, row)) in enumerate(CFG["icons"].items()):
    x0, y0 = col * TILE, row * TILE
    icon = sheet.crop((x0, y0, x0 + TILE, y0 + TILE))
    strip.paste(icon, (0, idx * TILE))
    # label (optional):
    # draw = ImageDraw.Draw(strip); draw.text((TILE+4, idx*TILE+4), key, fill="white")

out = "stat_icon_preview.png"
strip.save(out)
Image.open(out).show()          # opens in default viewer
print(f"Preview written to {out}")

