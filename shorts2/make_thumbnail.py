from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

BASE = Path(__file__).parent
IMAGES = BASE / "images"
ASSETS = BASE / "assets"

W, H = 1080, 1920

HEADLINE_FONT = ImageFont.truetype(str(ASSETS / "BlackHanSans-Regular.ttf"), 132)
SUB_FONT = ImageFont.truetype(str(ASSETS / "BlackHanSans-Regular.ttf"), 78)
LIST_FONT = ImageFont.truetype(str(ASSETS / "malgunbd.ttf"), 62)
NUM_FONT = ImageFont.truetype(str(ASSETS / "BlackHanSans-Regular.ttf"), 72)

WHITE = (255, 255, 255, 255)
YELLOW = (255, 225, 0, 255)
ORANGE = (255, 68, 0, 255)
BLACK = (0, 0, 0, 255)


def draw_stroked_text(draw, pos, text, font, fill, stroke_width, stroke_fill=BLACK, anchor=None):
    draw.text(pos, text, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill, anchor=anchor)


def cover_crop(img, target_w, target_h):
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w, new_h = round(src_w * scale), round(src_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def main():
    base = Image.open(IMAGES / "money1.jpg").convert("RGB")
    base = cover_crop(base, W, H).convert("RGBA")

    # dark scrim band around the vertical center, where the headline sits
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    band_top, band_bottom = int(H * 0.32), int(H * 0.62)
    band_center = (band_top + band_bottom) / 2
    band_half = (band_bottom - band_top) / 2
    for y in range(band_top, band_bottom):
        t = 1 - abs(y - band_center) / band_half
        alpha = int(min(150, t * 150))
        odraw.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    base = Image.alpha_composite(base, overlay)

    draw = ImageDraw.Draw(base)

    # Headline, vertically centered in frame
    center_y = H // 2
    draw_stroked_text(draw, (W // 2, center_y - 80), "지원금 소멸 주의보", HEADLINE_FONT, WHITE, 14, anchor="mm")
    draw_stroked_text(draw, (W // 2, center_y + 70), "8월 31일까지!", SUB_FONT, ORANGE, 12, anchor="mm")

    out_path = BASE / "thumbnail_jiwongeum.jpg"
    base.convert("RGB").save(out_path, quality=95)
    print(f"DONE: {out_path}")


if __name__ == "__main__":
    main()
