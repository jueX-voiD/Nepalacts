#!/usr/bin/env python3
"""
nepalacts.com News Image Generator
Generates English and Nepali headline images from article URLs.

Usage:
    python generate.py <url>
    python generate.py <url> --photo-x 0 --photo-y -100
    python generate.py <url> --en-headline "Override" --np-headline "ओभरराइड"
    python generate.py <url> --en-color "#ffffff" --np-color "#EB4F57"
"""

import argparse
import sys
import io
import re
import subprocess
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

# ── Canvas & Layout ─────────────────────────────────────────────────────────
CANVAS_W     = 1926
CANVAS_H     = 2400
LOGO_LEFT    = 150      # px from left
LOGO_BOTTOM  = 200      # px from bottom
HEADLINE_GAP = 100      # px gap between headline bottom and logo top
TEXT_MARGIN_L = 150     # headline left margin
TEXT_MARGIN_R = 80      # headline right margin

# ── Gradient (#181D21, 90% opacity → 0%, bottom → mid-canvas) ───────────────
GRAD_R, GRAD_G, GRAD_B = 24, 29, 33
GRAD_MAX_A = int(0.9 * 255)

# ── Logo ─────────────────────────────────────────────────────────────────────
LOGO_SVG    = Path(__file__).parent / "Logo.svg"
LOGO_PNG    = Path(__file__).parent / "fonts" / "_logo_cached.png"
LOGO_W      = 814       # rendered pixel width

# ── Fonts ────────────────────────────────────────────────────────────────────
# English: Abhaya Libre ExtraBold (serif, matches the reference design)
# Nepali:  Mukta ExtraBold (the Devanagari font nepalacts.com itself uses)
FONTS_DIR = Path(__file__).parent / "fonts"


def _font(name: str) -> Path:
    """Prefer the bundled font (portable to servers); fall back to the
    system-installed copy on this Mac."""
    local = FONTS_DIR / name
    if local.exists():
        return local
    return Path.home() / "Library/Fonts" / name


FONT_EN_PATH = _font("AbhayaLibre-ExtraBold.ttf")
FONT_NP_PATH = _font("Mukta-ExtraBold.ttf")
FONT_EN_SIZE = 112
FONT_EN_LH   = 128
FONT_NP_SIZE = 120
FONT_NP_LH   = 140


# ── Helpers ──────────────────────────────────────────────────────────────────

def hex_to_rgba(hex_color: str, alpha: int = 255):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (r, g, b, alpha)


def check_fonts():
    missing = []
    if not FONT_EN_PATH.exists():
        missing.append(
            "AbhayaLibre-ExtraBold.ttf\n"
            "    Download → https://fonts.google.com/specimen/Abhaya+Libre\n"
            "    Place in:  fonts/AbhayaLibre-ExtraBold.ttf"
        )
    if not FONT_NP_PATH.exists():
        missing.append(
            "Raleway-ExtraBold.ttf\n"
            "    Download → https://fonts.google.com/specimen/Raleway\n"
            "    Place in:  fonts/Raleway-ExtraBold.ttf"
        )
    if missing:
        print("\nMissing fonts. Please install them:\n")
        for m in missing:
            print(f"  {m}\n")
        sys.exit(1)


def render_logo() -> Image.Image:
    """Render SVG logo to PNG (cached after first run)."""
    if LOGO_PNG.exists():
        return Image.open(LOGO_PNG).convert("RGBA")

    FONTS_DIR.mkdir(exist_ok=True)
    png_bytes = None

    # Try cairosvg first
    # Try rsvg-convert (Homebrew: brew install librsvg)
    for rsvg in ["/opt/homebrew/bin/rsvg-convert", "rsvg-convert"]:
        result = subprocess.run(
            [rsvg, "-w", str(LOGO_W), str(LOGO_SVG)],
            capture_output=True
        )
        if result.returncode == 0:
            png_bytes = result.stdout
            break

    # Fallback: cairosvg
    if png_bytes is None:
        try:
            import cairosvg
            png_bytes = cairosvg.svg2png(url=str(LOGO_SVG), output_width=LOGO_W)
        except Exception:
            pass

    if png_bytes is None:
        sys.exit(
            "Cannot render SVG logo. Run:\n"
            "  brew install librsvg"
        )

    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    img.save(LOGO_PNG)
    return img


GRAPHQL_ENDPOINT = "https://api.nepalacts.com/graphql"

GQL_QUERY = """
query GetPost($slug: String!) {
  postBySlug(slug: $slug) {
    title
    titleNe
    image {
      url
    }
  }
}
"""


def slug_from_url(url: str) -> str:
    """Extract the last path segment as the article slug."""
    return url.rstrip("/").split("/")[-1]


def fetch_article(url: str) -> dict:
    slug = slug_from_url(url)

    payload = {"query": GQL_QUERY, "variables": {"slug": slug}}
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://nepalacts.com",
        "Referer": "https://nepalacts.com/",
    }
    r = requests.post(GRAPHQL_ENDPOINT, json=payload, headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json()

    if "errors" in data and not data.get("data"):
        raise RuntimeError(f"GraphQL error: {data['errors'][0]['message']}")

    post = (data.get("data") or {}).get("postBySlug") or {}

    return {
        "en_headline": post.get("title") or None,
        "np_headline": post.get("titleNe") or None,
        "image_url":   (post.get("image") or {}).get("url") or None,
    }


def fetch_photo(url: str) -> Image.Image:
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content)).convert("RGBA")


def cover_photo(photo: Image.Image, offset_x=0, offset_y=0) -> Image.Image:
    """Scale to cover canvas (crop-to-fill), apply offset."""
    scale = max(CANVAS_W / photo.width, CANVAS_H / photo.height)
    w = int(photo.width * scale)
    h = int(photo.height * scale)
    photo = photo.resize((w, h), Image.LANCZOS)
    x = (CANVAS_W - w) // 2 + offset_x
    y = (CANVAS_H - h) // 2 + offset_y
    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 255))
    canvas.paste(photo, (x, y))
    return canvas


def apply_gradient(img: Image.Image) -> Image.Image:
    """Bottom-to-midpoint gradient: #181D21 at 90% → transparent."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw    = ImageDraw.Draw(overlay)
    mid_y   = img.height // 2
    span    = img.height - mid_y
    for y in range(mid_y, img.height):
        alpha = int(GRAD_MAX_A * (y - mid_y) / span)
        draw.line([(0, y), (img.width - 1, y)], fill=(GRAD_R, GRAD_G, GRAD_B, alpha))
    return Image.alpha_composite(img, overlay)


def safe_filename(title: str) -> str:
    """Turn a headline into a filesystem-safe base name."""
    # Drop characters that are illegal / awkward in filenames
    name = re.sub(r'[\\/:*?"<>|]', "", title).strip()
    # Collapse whitespace to single spaces
    name = re.sub(r"\s+", " ", name)
    return name or "headline"


def unique_path(directory: Path, base: str, suffix: str = ".png") -> Path:
    """Return a path that doesn't exist yet, adding ' (n)' if needed."""
    candidate = directory / f"{base}{suffix}"
    if not candidate.exists():
        return candidate
    n = 1
    while True:
        candidate = directory / f"{base} ({n}){suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def wrap_text(text: str, font, max_w: int, draw) -> list:
    words   = text.split()
    lines   = []
    current = []
    for word in words:
        test = " ".join(current + [word])
        w    = draw.textbbox((0, 0), test, font=font)[2]
        if w <= max_w:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def generate_image(
    photo: Image.Image,
    headline: str,
    font_path: Path,
    font_size: int,
    line_height: int,
    text_color: str,
    offset: tuple,
    out_path: Path = None,
):
    # 1. Compose photo with gradient
    img = cover_photo(photo.copy(), *offset)
    img = apply_gradient(img)

    # 2. Paste logo
    logo   = render_logo()
    logo_x = LOGO_LEFT
    logo_y = CANVAS_H - LOGO_BOTTOM - logo.height
    img.paste(logo, (logo_x, logo_y), logo)

    # 3. Draw headline
    # Use the Raqm layout engine for proper complex-text shaping (Devanagari
    # conjuncts and reordered vowel signs). Falls back to basic layout if Raqm
    # isn't available.
    try:
        font = ImageFont.truetype(
            str(font_path), font_size,
            layout_engine=ImageFont.Layout.RAQM,
        )
    except Exception:
        font = ImageFont.truetype(str(font_path), font_size)
    # For variable fonts (like Raleway), set weight axis to ExtraBold (800)
    try:
        font.set_variation_by_axes([800])
    except Exception:
        pass
    draw = ImageDraw.Draw(img)
    max_w = CANVAS_W - TEXT_MARGIN_L - TEXT_MARGIN_R
    lines = wrap_text(headline, font, max_w, draw)

    total_h  = len(lines) * line_height
    # Headline bottom must be exactly HEADLINE_GAP above logo top
    text_top = logo_y - HEADLINE_GAP - total_h
    color    = hex_to_rgba(text_color)

    for i, line in enumerate(lines):
        draw.text(
            (TEXT_MARGIN_L, text_top + i * line_height),
            line,
            font=font,
            fill=color,
        )

    result = img.convert("RGB")
    if out_path is not None:
        result.save(out_path, "PNG", dpi=(72, 72))
        print(f"  ✓ Saved: {out_path}")
    return result


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Generate English + Nepali news images from a nepalacts.com article URL.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate.py https://nepalacts.com/voices/birgunj-mayor-singh-arrested
  python generate.py <url> --photo-y -200
  python generate.py <url> --np-headline "वीरगञ्ज महानगर प्रमुख सिंह पक्राउ"
  python generate.py <url> --np-color "#EB4F57"
        """,
    )
    ap.add_argument("url",           help="Article URL")
    ap.add_argument("--photo-x",     type=int, default=0,         help="Photo X offset in pixels (default: 0)")
    ap.add_argument("--photo-y",     type=int, default=0,         help="Photo Y offset in pixels (default: 0)")
    ap.add_argument("--output-dir",  default="output",            help="Output directory (default: ./output)")
    ap.add_argument("--en-headline", default=None,                help="Override English headline")
    ap.add_argument("--np-headline", default=None,                help="Override Nepali headline")
    ap.add_argument("--en-color",    default="#ffffff",           help="English text color hex (default: #ffffff)")
    ap.add_argument("--np-color",    default="#ffffff",           help="Nepali text color hex (default: #ffffff)")
    ap.add_argument("--image-url",   default=None,                help="Override featured image URL")
    args = ap.parse_args()

    check_fonts()

    print(f"\nFetching article: {args.url}")
    data = fetch_article(args.url)

    en      = args.en_headline or data["en_headline"]
    np_text = args.np_headline or data["np_headline"]
    img_url = args.image_url   or data["image_url"]

    print(f"  English : {en or '(not found)'}")
    print(f"  Nepali  : {np_text or '(not found)'}")
    print(f"  Image   : {img_url or '(not found)'}")

    if not img_url:
        sys.exit("\nERROR: Could not find a featured image. Use --image-url to provide one.")

    print("\nFetching photo...")
    photo  = fetch_photo(img_url)
    offset = (args.photo_x, args.photo_y)
    out    = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print("\nGenerating images...")
    if en:
        en_path = unique_path(out, safe_filename(en))
        generate_image(photo, en, FONT_EN_PATH, FONT_EN_SIZE, FONT_EN_LH,
                       args.en_color, offset, en_path)
    else:
        print("  ⚠ Skipping English — use --en-headline to set manually.")

    if np_text:
        np_path = unique_path(out, safe_filename(np_text))
        generate_image(photo, np_text, FONT_NP_PATH, FONT_NP_SIZE, FONT_NP_LH,
                       args.np_color, offset, np_path)
    else:
        print("  ⚠ Skipping Nepali  — use --np-headline to set manually.")

    print("\nDone.")


if __name__ == "__main__":
    main()
