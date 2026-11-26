"""Draw the integration icon (a power bolt with a flame, no ZSE logo) into ``custom_components/zse_energia/brand/``.

    python tools/make_icon.py        (needs: pip install pillow)
"""
from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw

OUT = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "zse_energia" / "brand"
SCALE = 4  # draw big, shrink for smooth edges


def draw(size: int) -> Image.Image:
    s = size * SCALE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def p(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [(x * s, y * s) for x, y in points]

    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.22), fill="#1f2a44")
    # lightning bolt (electricity)
    d.polygon(p([(0.46, 0.10), (0.20, 0.54), (0.40, 0.54), (0.30, 0.90), (0.62, 0.42), (0.43, 0.42), (0.56, 0.10)]), fill="#ffd23f")
    # flame (gas)
    d.polygon(
        p([(0.74, 0.34), (0.86, 0.52), (0.88, 0.68), (0.82, 0.82), (0.70, 0.88), (0.60, 0.80), (0.58, 0.66), (0.66, 0.56), (0.68, 0.46)]),
        fill="#ff7a3d",
    )
    d.polygon(p([(0.73, 0.62), (0.79, 0.72), (0.77, 0.82), (0.70, 0.84), (0.66, 0.77), (0.69, 0.69)]), fill="#ffd23f")
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    draw(256).save(OUT / "icon.png")
    draw(512).save(OUT / "icon@2x.png")
    print("written", OUT)


if __name__ == "__main__":
    main()
