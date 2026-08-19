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
TEXT_MARGIN_R = 80      # headline right margin

# ── Left block (red line + tag + title share this left edge) ─────────────────
BLOCK_LEFT     = 150    # left edge of the red line and the tag

# ── Red accent line (left of the title) ──────────────────────────────────────
RED_LINE_W     = 25            # breadth of the line
RED_LINE_COLOR = "#EA5158"
RED_LINE_GAP   = 80            # gap between the red line and the title text
TITLE_PAD_Y    = 15            # top & bottom spacing around the title text box
                               # (title is centered; red line = box height)

# ── Category tag (above the title) ────────────────────────────────────────────
TAG_BG         = "#145C9E"     # blue background
TAG_TEXT_COLOR = "#ffffff"
TAG_PAD_X      = 35            # left/right padding inside the tag
TAG_BOX_H      = 87            # fixed tag box height (text centered; padding is variable)
TAG_TITLE_GAP  = 50            # gap between the tag bottom and the red line top

# ── Gradient (#181D21, 90% opacity → 0%, bottom → mid-canvas) ───────────────
GRAD_R, GRAD_G, GRAD_B = 24, 29, 33
GRAD_MAX_A = int(0.9 * 255)

# ── Logo ─────────────────────────────────────────────────────────────────────
LOGO_SVG    = Path(__file__).parent / "Logo.svg"
LOGO_PNG    = Path(__file__).parent / "fonts" / "_logo_cached.png"
LOGO_W      = 814       # rendered pixel width

# ── Fonts ────────────────────────────────────────────────────────────────────
# English: Raleway (Latin) — variable font, weight axis set per use.
# Nepali:  Mukta (Devanagari) — Raleway has no Devanagari glyphs, and Mukta is
#          the font nepalacts.com itself uses. Static weight files.
FONTS_DIR = Path(__file__).parent / "fonts"


def _font(name: str) -> Path:
    """Prefer the bundled font (portable to servers); fall back to the
    system-installed copy on this Mac."""
    local = FONTS_DIR / name
    if local.exists():
        return local
    return Path.home() / "Library/Fonts" / name


# Per-language rendering config: title + tag fonts, sizes, weights, line height.
LANG = {
    "en": {
        "title_font":   _font("Raleway-VariableFont_wght.ttf"),
        "title_weight": 700,        # Bold (variable axis)
        "title_size":   100,
        "title_lh":     128,
        "tag_font":     _font("Raleway-VariableFont_wght.ttf"),
        "tag_weight":   600,        # SemiBold (variable axis)
        "tag_size":     40,
        "tag_tracking": 0.10,       # 10% letter-spacing
        "tag_upper":    True,       # ALL CAPS
    },
    "ne": {
        "title_font":   _font("Mukta-Bold.ttf"),
        "title_weight": None,       # static weight file
        "title_size":   120,
        "title_lh":     128,
        "tag_font":     _font("Mukta-SemiBold.ttf"),
        "tag_weight":   None,
        "tag_size":     45,
        "tag_tracking": 0.0,        # Nepali tag: no letter-spacing
    },
}


def load_font(path: Path, size: int, weight=None):
    """Load a font with the Raqm layout engine (for Devanagari shaping) and,
    for variable fonts, set the weight axis."""
    try:
        f = ImageFont.truetype(str(path), size, layout_engine=ImageFont.Layout.RAQM)
    except Exception:
        f = ImageFont.truetype(str(path), size)
    if weight is not None:
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
    return f


# ── Helpers ──────────────────────────────────────────────────────────────────

def hex_to_rgba(hex_color: str, alpha: int = 255):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (r, g, b, alpha)


def check_fonts():
    needed = {
        "Raleway-VariableFont_wght.ttf": "https://fonts.google.com/specimen/Raleway",
        "Mukta-Bold.ttf":                "https://fonts.google.com/specimen/Mukta",
        "Mukta-SemiBold.ttf":            "https://fonts.google.com/specimen/Mukta",
    }
    missing = []
    for name, url in needed.items():
        if not _font(name).exists():
            missing.append(f"{name}\n    Download → {url}\n    Place in:  fonts/{name}")
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
    postType
    category {
      name
      nameNe
    }
    image {
      url
    }
  }
}
"""

# Nepali labels for the post type (the tag). "NEWS" is the common one for now.
POST_TYPE_NE = {
    "NEWS":      "समाचार",
    "VOICES":    "विचार",
    "OPINION":   "विचार",
    "INTERVIEW": "अन्तर्वार्ता",
    "FEATURE":   "फिचर",
    "ARTICLE":   "लेख",
}


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
    category = post.get("category") or {}

    # The tag = the post type (e.g. "NEWS"). Nepali is mapped; falls back to the
    # category name (or the raw post type) for any unmapped type.
    post_type = post.get("postType") or None
    np_category = category.get("nameNe") or None
    en_tag = post_type
    np_tag = POST_TYPE_NE.get(post_type) or np_category or post_type

    return {
        "en_headline": post.get("title") or None,
        "np_headline": post.get("titleNe") or None,
        "en_tag":      en_tag,
        "np_tag":      np_tag,
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


def _is_combining(ch: str) -> bool:
    """True for Devanagari signs / dependent vowel marks that attach to a base."""
    o = ord(ch)
    return (
        0x0900 <= o <= 0x0903 or   # candrabindu, anusvara, visarga
        0x093A <= o <= 0x094F or   # matras, virama, etc.
        0x0951 <= o <= 0x0957 or   # accents
        0x0962 <= o <= 0x0963 or   # vocalic marks
        ch in ("‍", "‌")  # ZWJ / ZWNJ
    )


def grapheme_clusters(text: str) -> list:
    """Split into grapheme clusters so letter-spacing lands between clusters,
    never inside a Devanagari consonant+matra unit (which would break shaping)."""
    clusters, cur, join_next = [], "", False
    for ch in text:
        if cur == "":
            cur = ch
        elif join_next or _is_combining(ch):
            cur += ch
        else:
            clusters.append(cur)
            cur = ch
        join_next = (ch == "्")   # virama joins the next consonant (conjunct)
    if cur:
        clusters.append(cur)
    return clusters


def tracked_width(draw, text: str, font, tracking: float) -> float:
    """Total width of `text` with `tracking` px added between clusters."""
    cls = grapheme_clusters(text)
    if not cls:
        return 0.0
    w = sum(draw.textlength(c, font=font) + tracking for c in cls)
    return w - tracking          # drop the trailing gap


def draw_tracked(draw, xy, text: str, font, fill, tracking: float, anchor="ls"):
    """Draw `text` cluster-by-cluster with `tracking` px between clusters."""
    x, y = xy
    for c in grapheme_clusters(text):
        draw.text((x, y), c, font=font, fill=fill, anchor=anchor)
        x += draw.textlength(c, font=font) + tracking


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
    cfg: dict,
    text_color: str,
    offset: tuple,
    tag_text: str = None,
    out_path: Path = None,
):
    # 1. Compose photo with gradient
    img = cover_photo(photo.copy(), *offset)
    img = apply_gradient(img)
    draw = ImageDraw.Draw(img)

    # 2. Paste logo
    logo   = render_logo()
    logo_x = LOGO_LEFT
    logo_y = CANVAS_H - LOGO_BOTTOM - logo.height
    img.paste(logo, (logo_x, logo_y), logo)

    # 3. Title — each line vertically centered in its line box; the text block
    #    sits HEADLINE_GAP above the logo.
    title_font = load_font(cfg["title_font"], cfg["title_size"], cfg.get("title_weight"))
    title_left = BLOCK_LEFT + RED_LINE_W + RED_LINE_GAP
    max_w      = CANVAS_W - title_left - TEXT_MARGIN_R
    lines      = wrap_text(headline, title_font, max_w, draw)

    lh             = cfg["title_lh"]
    content_h      = len(lines) * lh
    content_bottom = logo_y - HEADLINE_GAP
    content_top    = content_bottom - content_h
    color          = hex_to_rgba(text_color)

    ascent, descent = title_font.getmetrics()
    for i, line in enumerate(lines):
        line_box_top = content_top + i * lh
        # centre the glyphs within the 128px line box (half-leading top & bottom)
        baseline = line_box_top + (lh - (ascent + descent)) / 2 + ascent
        draw.text((title_left, baseline), line, font=title_font, fill=color, anchor="ls")

    # 4. Red accent line — height = title box = content + TITLE_PAD_Y top & bottom,
    #    with the title vertically centered inside it.
    red_top    = round(content_top - TITLE_PAD_Y)
    red_bottom = round(content_bottom + TITLE_PAD_Y)
    draw.rectangle(
        [BLOCK_LEFT, red_top, BLOCK_LEFT + RED_LINE_W, red_bottom],
        fill=hex_to_rgba(RED_LINE_COLOR),
    )

    # 5. Category tag — fixed-height box (87px) with the text centered vertically
    if tag_text:
        label    = tag_text.upper() if cfg.get("tag_upper") else tag_text
        tag_font = load_font(cfg["tag_font"], cfg["tag_size"], cfg.get("tag_weight"))
        tracking = cfg.get("tag_tracking", 0.0) * cfg["tag_size"]
        text_w   = tracked_width(draw, label, tag_font, tracking)

        box_w      = text_w + 2 * TAG_PAD_X
        box_h      = TAG_BOX_H
        box_left   = BLOCK_LEFT
        box_bottom = red_top - TAG_TITLE_GAP            # 50px above the red line top
        box_top    = box_bottom - box_h

        draw.rectangle(
            [box_left, box_top, box_left + box_w, box_bottom],
            fill=hex_to_rgba(TAG_BG),
        )
        # Centre the text ink vertically within the fixed box height.
        ink        = draw.textbbox((0, 0), label, font=tag_font, anchor="ls")
        ink_center = (ink[1] + ink[3]) / 2              # relative to the baseline
        baseline   = box_top + box_h / 2 - ink_center
        draw_tracked(
            draw, (box_left + TAG_PAD_X, baseline), label,
            tag_font, hex_to_rgba(TAG_TEXT_COLOR), tracking,
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
    ap.add_argument("--en-tag",      default=None,                help="Override English category tag")
    ap.add_argument("--np-tag",      default=None,                help="Override Nepali category tag")
    ap.add_argument("--no-tag",      action="store_true",         help="Hide the category tag")
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
    en_tag  = None if args.no_tag else (args.en_tag or data["en_tag"])
    np_tag  = None if args.no_tag else (args.np_tag or data["np_tag"])

    print(f"  English : {en or '(not found)'}  [tag: {en_tag or '-'}]")
    print(f"  Nepali  : {np_text or '(not found)'}  [tag: {np_tag or '-'}]")
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
        generate_image(photo, en, LANG["en"], args.en_color, offset,
                       tag_text=en_tag, out_path=en_path)
    else:
        print("  ⚠ Skipping English — use --en-headline to set manually.")

    if np_text:
        np_path = unique_path(out, safe_filename(np_text))
        generate_image(photo, np_text, LANG["ne"], args.np_color, offset,
                       tag_text=np_tag, out_path=np_path)
    else:
        print("  ⚠ Skipping Nepali  — use --np-headline to set manually.")

    print("\nDone.")


if __name__ == "__main__":
    main()
