import io
import os
import base64
import requests
from PIL import Image, ImageDraw, ImageFont

PIN_W, PIN_H = 1000, 1500
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(BASE_DIR, "static", "fonts")

# ── Font setup ────────────────────────────────────────────────────────────────

def _ensure_fonts():
    """Download Montserrat fonts on first use if not already present."""
    os.makedirs(FONTS_DIR, exist_ok=True)
    needed = {
        "Montserrat-Bold.ttf":
            "https://github.com/google/fonts/raw/main/ofl/montserrat/static/Montserrat-Bold.ttf",
        "Montserrat-Regular.ttf":
            "https://github.com/google/fonts/raw/main/ofl/montserrat/static/Montserrat-Regular.ttf",
        "Montserrat-Medium.ttf":
            "https://github.com/google/fonts/raw/main/ofl/montserrat/static/Montserrat-Medium.ttf",
        "PlayfairDisplay-Bold.ttf":
            "https://github.com/google/fonts/raw/main/ofl/playfairdisplay/static/PlayfairDisplay-Bold.ttf",
    }
    for name, url in needed.items():
        dest = os.path.join(FONTS_DIR, name)
        if not os.path.exists(dest):
            try:
                r = requests.get(url, timeout=20)
                if r.status_code == 200:
                    with open(dest, "wb") as f:
                        f.write(r.content)
            except Exception:
                pass

_ensure_fonts()

_WIN = r"C:\Windows\Fonts"
_SYSTEM_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    os.path.join(_WIN, "arialbd.ttf"),
    os.path.join(_WIN, "segoeuib.ttf"),
]
_SYSTEM_REG = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    os.path.join(_WIN, "arial.ttf"),
    os.path.join(_WIN, "segoeui.ttf"),
]
_SYSTEM_SERIF = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSerifBold.ttf",
    os.path.join(_WIN, "georgiab.ttf"),
    os.path.join(_WIN, "timesbd.ttf"),
]

def get_font(size, bold=False):
    candidates = (
        [os.path.join(FONTS_DIR, "Montserrat-Bold.ttf")] + _SYSTEM_BOLD
        if bold else
        [os.path.join(FONTS_DIR, "Montserrat-Regular.ttf")] + _SYSTEM_REG
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()

def get_serif(size):
    candidates = [os.path.join(FONTS_DIR, "PlayfairDisplay-Bold.ttf")] + _SYSTEM_SERIF
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return get_font(size, bold=True)

def get_medium(size):
    candidates = [os.path.join(FONTS_DIR, "Montserrat-Medium.ttf")] + _SYSTEM_REG
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return get_font(size, bold=False)

# ── Drawing helpers ───────────────────────────────────────────────────────────

def _tw(draw, text, font):
    try:
        return draw.textbbox((0, 0), text, font=font)[2]
    except Exception:
        return len(text) * max(getattr(font, "size", 20) // 2, 8)

def _th(draw, font):
    try:
        bb = draw.textbbox((0, 0), "Ag", font=font)
        return bb[3] - bb[1]
    except Exception:
        return max(getattr(font, "size", 20), 16)

def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = (current + " " + word).strip()
        if _tw(draw, test, font) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

def draw_centered(draw, text, font, cx, y, fill):
    """Draw a single line horizontally centered on cx."""
    w = _tw(draw, text, font)
    draw.text((cx - w / 2, y), text, font=font, fill=fill)

def draw_tracked(draw, text, font, cx, y, fill, tracking=8):
    """Draw text with letter-spacing, centered on cx."""
    widths = [_tw(draw, ch, font) for ch in text]
    total  = sum(widths) + tracking * (len(text) - 1)
    x = cx - total / 2
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill)
        x += w + tracking

def download_image(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=12)
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content)).convert("RGB")

def smart_crop(img, target_w, target_h):
    iw, ih = img.size
    tr = target_w / target_h
    cr = iw / ih
    if cr > tr:
        nw = int(ih * tr)
        x  = (iw - nw) // 2
        img = img.crop((x, 0, x + nw, ih))
    elif cr < tr:
        nh = int(iw / tr)
        y  = (ih - nh) // 2
        img = img.crop((0, y, iw, y + nh))
    return img.resize((target_w, target_h), Image.LANCZOS)

def make_gradient(w, h, a0=0, a1=210):
    """Vertical black gradient, transparent at top, opaque at bottom."""
    g = Image.new("RGBA", (1, h))
    for y in range(h):
        a = int(a0 + (a1 - a0) * y / h)
        g.putpixel((0, y), (0, 0, 0, a))
    return g.resize((w, h), Image.NEAREST)

def to_b64(img):
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode()

# ── Template 1: Minimal ───────────────────────────────────────────────────────
#  Image fills top 68%  |  White panel below  |  Red accent bar  |  Domain in red

def render_minimal(img_url, title, domain):
    img_h = int(PIN_H * 0.68)
    pin   = Image.new("RGB", (PIN_W, PIN_H), "#ffffff")

    bg = smart_crop(download_image(img_url), PIN_W, img_h)
    pin.paste(bg, (0, 0))

    draw = ImageDraw.Draw(pin)
    draw.rectangle([0, img_h, PIN_W, img_h + 8], fill="#e60023")

    pad        = 56
    title_font = get_font(54, bold=True)
    lines      = wrap_text(draw, title, title_font, PIN_W - 2 * pad)[:4]
    lh         = _th(draw, title_font) + 12

    y = img_h + 44
    for line in lines:
        draw.text((pad, y), line, font=title_font, fill="#111111")
        y += lh

    domain_font = get_font(36, bold=False)
    draw.text((pad, PIN_H - 68), domain, font=domain_font, fill="#e60023")
    return to_b64(pin)

# ── Template 2: Bold ──────────────────────────────────────────────────────────
#  Full-bleed image  |  Dark gradient bottom 52%  |  White title  |  Domain in pink

def render_bold(img_url, title, domain):
    bg  = smart_crop(download_image(img_url), PIN_W, PIN_H)
    pin = bg.convert("RGBA")

    grad_h = int(PIN_H * 0.52)
    pin.alpha_composite(make_gradient(PIN_W, grad_h, a0=0, a1=225),
                        (0, PIN_H - grad_h))
    pin  = pin.convert("RGB")
    draw = ImageDraw.Draw(pin)

    pad         = 56
    title_font  = get_font(60, bold=True)
    domain_font = get_font(34, bold=False)
    lines       = wrap_text(draw, title, title_font, PIN_W - 2 * pad)[:4]
    lh          = _th(draw, title_font) + 14

    domain_y    = PIN_H - 70
    title_y     = domain_y - len(lines) * lh - 20

    for line in lines:
        draw.text((pad, title_y), line, font=title_font, fill="#ffffff")
        title_y += lh

    draw.text((pad, domain_y), domain, font=domain_font, fill="#ffaaaa")
    return to_b64(pin)

# ── Template 3: Elegant ───────────────────────────────────────────────────────
#  Image top 60%  |  Dark #1a1a1a panel  |  Red separator  |  White title  |  Domain in red

def render_elegant(img_url, title, domain):
    img_h = int(PIN_H * 0.60)
    pin   = Image.new("RGB", (PIN_W, PIN_H), "#1a1a1a")

    bg = smart_crop(download_image(img_url), PIN_W, img_h)
    pin.paste(bg, (0, 0))

    draw = ImageDraw.Draw(pin)
    draw.rectangle([0, img_h, PIN_W, img_h + 6], fill="#e60023")

    pad        = 56
    title_font = get_font(54, bold=True)
    lines      = wrap_text(draw, title, title_font, PIN_W - 2 * pad)[:4]
    lh         = _th(draw, title_font) + 12

    y = img_h + 44
    for line in lines:
        draw.text((pad, y), line, font=title_font, fill="#ffffff")
        y += lh

    domain_font = get_font(36, bold=True)
    draw.text((pad, PIN_H - 76), domain, font=domain_font, fill="#e60023")
    return to_b64(pin)

# ── Template 4: Pancake / Brown (recreated from the Canva SVG) ────────────────
#  Full-bleed photo | brown top+bottom bars | cream rounded title panel (serif)
#  | tracked uppercase domain in footer | decorative corner/edge dots.
#  Coordinates measured from the SVG (750×1125) and scaled ×4/3 to 1000×1500.

BROWN = "#68513f"
CREAM = "#f7f5f0"

def render_pancake(img_url, title, domain):
    pin  = smart_crop(download_image(img_url), PIN_W, PIN_H).convert("RGB")
    draw = ImageDraw.Draw(pin, "RGBA")

    # Decorative dots that bleed off the edges (colors approximated from template)
    for cx, cy, r, col in [
        (99,  99,  99, CREAM),   # top-left
        (870, 199, 99, CREAM),   # top-right
        (969, 679, 85, BROWN),   # right edge
        (121, 963, 85, BROWN),   # left edge
    ]:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)

    # Brown top & bottom bars
    draw.rectangle([0, 0, PIN_W, 81],          fill=BROWN)
    draw.rectangle([0, 1406, PIN_W, PIN_H],    fill=BROWN)

    # Cream rounded title panel
    panel = (100, 185, 900, 472)
    draw.rounded_rectangle(panel, radius=28, fill=CREAM)

    # Title — serif bold, brown, auto-fit + centered in the panel
    cx       = (panel[0] + panel[2]) // 2
    inner_w  = (panel[2] - panel[0]) - 80
    avail_h  = (panel[3] - panel[1]) - 50
    size     = 72
    while size > 34:
        f     = get_serif(size)
        lines = wrap_text(draw, title, f, inner_w)
        lh    = _th(draw, f) + 14
        if len(lines) <= 3 and len(lines) * lh <= avail_h:
            break
        size -= 4
    title_font = get_serif(size)
    lines      = wrap_text(draw, title, title_font, inner_w)[:3]
    lh         = _th(draw, title_font) + 14
    ty         = (panel[1] + panel[3]) // 2 - (len(lines) * lh) // 2
    for line in lines:
        draw_centered(draw, line, title_font, cx, ty, BROWN)
        ty += lh

    # Domain — cream, uppercase, letter-spaced, centered in the bottom bar
    draw_tracked(draw, (domain or "").upper(), get_medium(30),
                 PIN_W // 2, 1428, CREAM, tracking=6)

    return to_b64(pin)

# ── Public API ────────────────────────────────────────────────────────────────

_RENDERERS = {
    "minimal": render_minimal,
    "bold":    render_bold,
    "elegant": render_elegant,
    "pancake": render_pancake,
}

def render_pin(img_url, title, domain, template="bold"):
    fn = _RENDERERS.get(template, render_bold)
    return fn(img_url, title, domain)
