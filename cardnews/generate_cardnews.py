import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

BASE = Path(__file__).parent
SLIDES = BASE / "slides"

W, H = 1080, 1350

NAVY = (26, 32, 53, 255)
WHITE = (255, 255, 255, 255)
ORANGE = (255, 107, 53, 255)
LIGHT_BG = (250, 248, 244, 255)
GRAY_TEXT = (60, 60, 60, 255)

TITLE_FONT = ImageFont.truetype(str(BASE / "BlackHanSans-Regular.ttf"), 88)
SUBTITLE_FONT = ImageFont.truetype(str(BASE / "BlackHanSans-Regular.ttf"), 52)
HEADING_FONT = ImageFont.truetype(str(BASE / "BlackHanSans-Regular.ttf"), 64)
BULLET_FONT = ImageFont.truetype(str(BASE / "malgunbd.ttf"), 42)
BRAND_FONT = ImageFont.truetype(str(BASE / "malgunbd.ttf"), 34)
PAGE_FONT = ImageFont.truetype(str(BASE / "malgun.ttf"), 30)


def cover_crop(img, target_w, target_h):
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w, new_h = round(src_w * scale), round(src_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def draw_brand_tag(draw, brand):
    draw.rectangle([(0, 0), (W, 110)], fill=NAVY)
    draw.text((50, 55), brand, font=BRAND_FONT, fill=WHITE, anchor="lm")


def wrap_text(text, font, max_width, draw):
    words = list(text)
    lines = []
    cur = ""
    for ch in text:
        test = cur + ch
        if draw.textlength(test, font=font) > max_width and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def render_cover(slide, page, total):
    img = Image.open(BASE / slide["bg_image"]).convert("RGB")
    img = cover_crop(img, W, H).convert("RGBA")

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for y in range(int(H * 0.55), H):
        t = (y - H * 0.55) / (H * 0.45)
        alpha = int(min(190, t * 190))
        odraw.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img, overlay)

    draw = ImageDraw.Draw(img)
    draw_brand_tag(draw, "머니테이블")
    draw.text((W // 2, H - 260), slide["title"], font=TITLE_FONT, fill=WHITE,
              stroke_width=6, stroke_fill=(0, 0, 0, 255), anchor="mm")
    draw.text((W // 2, H - 160), slide["subtitle"], font=SUBTITLE_FONT, fill=ORANGE,
              stroke_width=4, stroke_fill=(0, 0, 0, 255), anchor="mm")
    return img.convert("RGB")


def render_content(slide, page, total, mode="content"):
    img = Image.new("RGBA", (W, H), LIGHT_BG)
    draw = ImageDraw.Draw(img)
    draw_brand_tag(draw, "머니테이블")

    accent = ORANGE if mode != "warning" else (220, 50, 50, 255)

    draw.rectangle([(0, 110), (14, H)], fill=accent)

    heading_lines = wrap_text(slide["heading"], HEADING_FONT, W - 160, draw)
    y = 230
    for line in heading_lines:
        draw.text((80, y), line, font=HEADING_FONT, fill=NAVY, anchor="lm")
        y += 82

    y += 40
    icon = "⚠ " if mode == "warning" else ("✅ " if mode == "checklist" else "• ")
    for bullet in slide["bullets"]:
        lines = wrap_text(icon + bullet, BULLET_FONT, W - 200, draw)
        for i, line in enumerate(lines):
            indent = 90 if i == 0 else 130
            draw.text((indent, y), line, font=BULLET_FONT, fill=GRAY_TEXT, anchor="lm")
            y += 62
        y += 30

    draw.text((W - 60, H - 50), f"{page}/{total}", font=PAGE_FONT, fill=GRAY_TEXT, anchor="rm")
    return img.convert("RGB")


def render_cta(slide, page, total):
    img = Image.new("RGBA", (W, H), NAVY)
    draw = ImageDraw.Draw(img)

    draw.text((W // 2, H // 2 - 140), slide["heading"], font=HEADING_FONT, fill=WHITE, anchor="mm")

    lines = wrap_text(slide["subtitle"], SUBTITLE_FONT, W - 160, draw)
    y = H // 2 - 20
    for line in lines:
        draw.text((W // 2, y), line, font=SUBTITLE_FONT, fill=ORANGE, anchor="mm")
        y += 66

    draw.rounded_rectangle([(W // 2 - 220, H - 260), (W // 2 + 220, H - 180)], radius=40, outline=WHITE, width=4)
    draw.text((W // 2, H - 220), "@mnt202606", font=BULLET_FONT, fill=WHITE, anchor="mm")

    return img.convert("RGB")


def main():
    data = json.loads((BASE / "slides_content.json").read_text(encoding="utf-8"))
    slides = data["slides"]
    total = len(slides)
    SLIDES.mkdir(exist_ok=True)

    paths = []
    for i, slide in enumerate(slides, start=1):
        if slide["type"] == "cover":
            img = render_cover(slide, i, total)
        elif slide["type"] == "cta":
            img = render_cta(slide, i, total)
        else:
            img = render_content(slide, i, total, mode=slide["type"])
        out_path = SLIDES / f"slide_{i}.jpg"
        img.save(out_path, quality=92)
        paths.append(out_path)
        print(f"saved {out_path}")

    print(f"\nDONE: {total} slides in {SLIDES}")


if __name__ == "__main__":
    main()
