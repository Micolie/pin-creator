from PIL import Image, ImageDraw

def make_icon(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = size // 2

    # Red rounded background
    draw.rounded_rectangle([0, 0, size, size], radius=size // 5, fill=(230, 0, 35, 255))

    # Pin head (white circle)
    head_r = int(size * 0.28)
    head_cy = int(size * 0.38)
    draw.ellipse([cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r], fill="white")

    # Pin shaft
    shaft_w = int(size * 0.08)
    shaft_top = head_cy + head_r - int(size * 0.04)
    shaft_bot = int(size * 0.82)
    draw.rectangle([cx - shaft_w//2, shaft_top, cx + shaft_w//2, shaft_bot], fill="white")

    # Pin tip
    draw.polygon([
        (cx - shaft_w//2, shaft_bot),
        (cx + shaft_w//2, shaft_bot),
        (cx, shaft_bot + int(size * 0.08))
    ], fill="white")

    # Shine on head
    shine_r = int(size * 0.08)
    draw.ellipse([cx - head_r + int(size*0.06), head_cy - head_r + int(size*0.06),
                  cx - head_r + int(size*0.06) + shine_r, head_cy - head_r + int(size*0.06) + shine_r],
                 fill=(255, 255, 255, 160))
    return img

# Save favicon sizes
icon_512 = make_icon(512)
icon_512.save("static/icon-512.png", "PNG")

icon_192 = make_icon(192)
icon_192.save("static/icon-192.png", "PNG")

icon_32 = make_icon(32)
icon_32.save("static/favicon.ico", format="ICO", sizes=[(32, 32)])

print("Icons saved!")
