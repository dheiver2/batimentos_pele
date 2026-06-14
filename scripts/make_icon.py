"""Gera o ícone do VitalScan (coração + ECG) em PNG e .icns (macOS).

Uso:  python3 scripts/make_icon.py
Saída: assets/icon.png e assets/VitalScan.icns (este último só no macOS).
"""

import math
import os
import subprocess

from PIL import Image, ImageDraw

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(RAIZ, "assets")
ACC = (92, 240, 138, 255)
BG = (10, 10, 10, 255)


def desenha(sz: int) -> Image.Image:
    s = sz
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(s * 0.225)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=r, fill=BG)
    d.rounded_rectangle(
        [int(s * 0.02), int(s * 0.02), s - 1 - int(s * 0.02), s - 1 - int(s * 0.02)],
        radius=int(r * 0.9), outline=(40, 40, 40, 255), width=max(1, int(s * 0.004)))
    cx, cy, u = s * 0.5, s * 0.46, s * 0.20
    pts = []
    for i in range(201):
        t = i / 200 * 2 * math.pi
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x / 16 * u, cy - y / 16 * u))
    d.polygon(pts, fill=ACC)
    w = max(2, int(s * 0.022))
    by = s * 0.55
    seg = [(s * 0.16, by), (s * 0.34, by), (s * 0.40, by - s * 0.10),
           (s * 0.46, by + s * 0.16), (s * 0.52, by - s * 0.22),
           (s * 0.58, by + s * 0.08), (s * 0.64, by), (s * 0.84, by)]
    d.line(seg, fill=BG, width=int(w * 2.2), joint="curve")
    d.line(seg, fill=ACC, width=w, joint="curve")
    return img


def main():
    os.makedirs(ASSETS, exist_ok=True)
    base = desenha(1024)
    base.save(os.path.join(ASSETS, "icon.png"))
    print("assets/icon.png gerado")

    # .icns (apenas macOS, via iconutil)
    iconset = os.path.join(ASSETS, "VitalScan.iconset")
    os.makedirs(iconset, exist_ok=True)
    for z in (16, 32, 64, 128, 256, 512, 1024):
        base.resize((z, z), Image.LANCZOS).save(
            os.path.join(iconset, f"icon_{z}x{z}.png"))
        if z <= 512:
            base.resize((z * 2, z * 2), Image.LANCZOS).save(
                os.path.join(iconset, f"icon_{z}x{z}@2x.png"))
    try:
        subprocess.run(
            ["iconutil", "-c", "icns", iconset,
             "-o", os.path.join(ASSETS, "VitalScan.icns")], check=True)
        print("assets/VitalScan.icns gerado")
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("iconutil indisponível (não-macOS) — .icns não gerado")


if __name__ == "__main__":
    main()
