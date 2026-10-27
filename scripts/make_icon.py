"""Generate src/YiQu/Assets/YiQu.ico (rounded gradient tile with the 译 glyph).

Run with any Python that has Pillow: python scripts/make_icon.py
Each size is drawn separately at 4x and downsampled so small sizes stay crisp.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "YiQu" / "Assets" / "YiQu.ico"
FONT = Path(r"C:\Windows\Fonts\msyhbd.ttc")
TOP, BOTTOM = (0x6A, 0x8B, 0xFF), (0x3A, 0x52, 0xE0)
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def tile(size: int) -> Image.Image:
    scale = 4
    big = size * scale
    inset = round(big * (0.04 if size >= 32 else 0.0))
    side = big - 2 * inset
    gradient = Image.new("RGBA", (side, side))
    pixels = gradient.load()
    for y in range(side):
        for x in range(side):
            t = (x * 0.35 + y * 0.65) / side
            pixels[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)) + (255,)
    mask = Image.new("L", (side, side), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, side - 1, side - 1), radius=round(side * 0.24), fill=255)
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    image.paste(gradient, (inset, inset), mask)
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(FONT), round(side * 0.62))
    box = draw.textbbox((0, 0), "译", font=font)
    x = (big - (box[2] - box[0])) / 2 - box[0]
    y = (big - (box[3] - box[1])) / 2 - box[1]
    draw.text((x, y), "译", font=font, fill=(255, 255, 255, 255))
    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    images = [tile(s) for s in SIZES]
    images[-1].save(OUT, format="ICO", sizes=[(s, s) for s in SIZES], append_images=images[:-1])
    print(OUT, OUT.stat().st_size)


if __name__ == "__main__":
    main()
