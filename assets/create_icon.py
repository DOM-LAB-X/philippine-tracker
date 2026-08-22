"""
Run once to generate assets/icon.ico and assets/icon.png.
Requires Pillow: pip install Pillow
"""
import math
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    raise SystemExit("Pillow is required: pip install Pillow")

HERE = Path(__file__).parent

# Philippine flag colours
BLUE   = "#0038A8"
GOLD   = "#FCD116"
WHITE  = "#FFFFFF"
TRANSPARENT = (0, 0, 0, 0)


def _draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    d = ImageDraw.Draw(img)

    cx = cy = size / 2
    r = size / 2 - 2

    # Background circle
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=BLUE)

    # 8 sun rays
    inner_r = r * 0.30
    outer_r = r * 0.68
    half_ang = math.pi / 8 * 0.65
    for i in range(8):
        angle = 2 * math.pi * i / 8 - math.pi / 2
        tip = (cx + outer_r * math.cos(angle), cy + outer_r * math.sin(angle))
        left = (
            cx + inner_r * math.cos(angle - half_ang),
            cy + inner_r * math.sin(angle - half_ang),
        )
        right = (
            cx + inner_r * math.cos(angle + half_ang),
            cy + inner_r * math.sin(angle + half_ang),
        )
        d.polygon([tip, left, right], fill=GOLD)

    # Sun centre circle
    sr = r * 0.20
    d.ellipse([cx - sr, cy - sr, cx + sr, cy + sr], fill=GOLD)

    # Airplane silhouette (white, pointing right)
    s = r * 0.48
    # Fuselage
    d.polygon(
        [
            (cx - s * 0.80, cy - s * 0.09),
            (cx + s * 0.55, cy - s * 0.09),
            (cx + s * 0.95, cy),
            (cx + s * 0.55, cy + s * 0.09),
            (cx - s * 0.80, cy + s * 0.09),
        ],
        fill=WHITE,
    )
    # Top wing
    d.polygon(
        [
            (cx - s * 0.05, cy - s * 0.09),
            (cx - s * 0.50, cy - s * 0.09),
            (cx - s * 0.72, cy - s * 0.62),
            (cx + s * 0.10, cy - s * 0.42),
        ],
        fill=WHITE,
    )
    # Bottom wing (mirror)
    d.polygon(
        [
            (cx - s * 0.05, cy + s * 0.09),
            (cx - s * 0.50, cy + s * 0.09),
            (cx - s * 0.72, cy + s * 0.62),
            (cx + s * 0.10, cy + s * 0.42),
        ],
        fill=WHITE,
    )
    # Tail fin
    d.polygon(
        [
            (cx - s * 0.58, cy - s * 0.09),
            (cx - s * 0.80, cy - s * 0.09),
            (cx - s * 0.80, cy - s * 0.36),
            (cx - s * 0.58, cy - s * 0.09),
        ],
        fill=WHITE,
    )

    return img


def generate(dest: Path = HERE) -> None:
    large = _draw_icon(512)
    large.save(dest / "icon.png")

    sizes = [16, 24, 32, 48, 64, 128, 256]
    icons = [_draw_icon(s) for s in sizes]
    icons[0].save(
        dest / "icon.ico",
        format="ICO",
        append_images=icons[1:],
        sizes=[(s, s) for s in sizes],
    )
    print(f"Icon saved → {dest / 'icon.ico'} and {dest / 'icon.png'}")


if __name__ == "__main__":
    generate()
