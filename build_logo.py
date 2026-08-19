#!/usr/bin/env python3
"""
Rebuild the logo as: coral spiral icon + "nepalacts.com" in DM Sans Medium (white).
Reuses the official high-res icon and matches its proportions, then sizes the
result to the current logo height so nothing else in the layout shifts.

Output: fonts/_logo_cached.png  (transparent, white wordmark for the dark gradient)
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np

HERE      = Path(__file__).parent
SITE_LOGO = HERE / "assets" / "nepalacts-official-logo.png"  # official hi-res logo
DM_SANS   = HERE / "fonts" / "DMSans-VariableFont.ttf"       # DM Sans variable
OUT       = HERE / "fonts" / "_logo_cached.png"
TARGET_H  = 60                                    # keep current display height

# Official layout (measured):
#   icon bbox (100,97)-(828,728);  text starts x≈1124, top y≈120, height≈593
TEXT_LEFT   = 1124
TEXT_TOP    = 120
TEXT_HEIGHT = 593

# 1. Icon-only layer: keep coral pixels from the official logo, drop the rest.
site = Image.open(SITE_LOGO).convert("RGBA")
arr  = np.array(site)
r, g, b, a = (arr[..., i].astype(int) for i in range(4))
coral = (r > 180) & (g < 150) & (b < 150) & (a > 80)

icon = np.zeros_like(arr)
icon[coral] = arr[coral]            # keep coral pixels as-is
icon_img = Image.fromarray(icon, "RGBA")

# 2. Render "nepalacts.com" in DM Sans Medium, white, then scale to match height.
def dm_font(size):
    f = ImageFont.truetype(str(DM_SANS), size)
    try:
        f.set_variation_by_name("Medium")
    except Exception:
        try:
            f.set_variation_by_axes([14, 500])   # opsz, wght
        except Exception:
            pass
    return f

BIG = 700
font = dm_font(BIG)
tmp  = Image.new("RGBA", (7000, 1200), (0, 0, 0, 0))
td   = ImageDraw.Draw(tmp)
td.text((10, 10), "nepalacts.com", font=font, fill=(255, 255, 255, 255))
tb   = tmp.getbbox()                                   # tight bbox of the text
text = tmp.crop(tb)

scale = TEXT_HEIGHT / text.height
text  = text.resize((round(text.width * scale), round(text.height * scale)), Image.LANCZOS)

# 3. Composite icon + text on a transparent canvas wide enough for ".com".
canvas_w = max(site.width, TEXT_LEFT + text.width + 60)
canvas = Image.new("RGBA", (canvas_w, site.height), (0, 0, 0, 0))
canvas.alpha_composite(icon_img)
canvas.alpha_composite(text, (TEXT_LEFT, TEXT_TOP))

# 4. Crop to content and resize to the target display height.
logo = canvas.crop(canvas.getbbox())
logo = logo.resize((round(logo.width * TARGET_H / logo.height), TARGET_H), Image.LANCZOS)
logo.save(OUT)
print(f"Saved {OUT}  size={logo.size}")
