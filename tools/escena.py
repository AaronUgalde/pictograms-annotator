"""Genera los fondos en pixel art (frontend/escena/escena-dia.png y escena-noche.png).

Es una escena original (colinas, árboles, una cabaña con la ventana encendida), dibujada píxel a píxel
con colores propios: no usa texturas ni recursos de ningún juego. La interfaz la muestra oscurecida y
algo desenfocada detrás de los paneles, como un mundo con el inventario abierto.

Uso (solo hace falta para regenerar las imágenes; Pillow no es dependencia de la app):
    pip install pillow && python tools/escena.py
"""
import math
import random
from pathlib import Path

from PIL import Image

W, H = 384, 216
OUT = Path(__file__).resolve().parents[1] / "frontend" / "escena"  # no usar /img: es la ruta de los pictogramas


def hx(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Canvas:
    def __init__(self, night: bool):
        self.night = night
        self.img = Image.new("RGB", (W, H))
        self.px = self.img.load()

    def tone(self, c):
        """De día, el color tal cual con un toque cálido; de noche, más oscuro y azulado."""
        c = hx(c) if isinstance(c, str) else c
        if self.night:
            dark = tuple(int(v * 0.30) for v in c)
            return mix(dark, (20, 26, 58), 0.35)
        return mix(c, (255, 196, 140), 0.08)

    def put(self, x, y, c, raw=False):
        if 0 <= x < W and 0 <= y < H:
            self.px[x, y] = (hx(c) if isinstance(c, str) else c) if raw else self.tone(c)

    def glow(self, cx, cy, radius, color, strength):
        """Halo de luz cálida, en escalones (sin degradados suaves, para que siga siendo pixel art)."""
        col = hx(color)
        for y in range(cy - radius, cy + radius + 1):
            for x in range(cx - radius, cx + radius + 1):
                if not (0 <= x < W and 0 <= y < H):
                    continue
                d = math.hypot(x - cx, y - cy) / radius
                if d < 1:
                    t = strength * (1 - math.floor(d * 4) / 4)
                    self.px[x, y] = mix(self.px[x, y], col, t)


def terrain(rng, base, amp, step_min, step_max, smooth=0.6):
    """Alturas por columnas en escalones (relieve de bloques)."""
    heights, x, h = [], 0, base
    while x < W:
        w = rng.randint(step_min, step_max)
        target = base + rng.randint(-amp, amp)
        h = round(h * smooth + target * (1 - smooth))
        heights += [h] * w
        x += w
    return heights[:W]


def draw(night: bool, seed=7) -> Image.Image:
    rng = random.Random(seed)
    cv = Canvas(night)

    # ---------------------------------------------------------- cielo en franjas, con tramado entre franjas
    if night:
        bands = ["#0b0f2a", "#0f1534", "#141b40", "#1a224c", "#212a58", "#2a2f63", "#352f66", "#433366"]
    else:
        bands = ["#5d8fd8", "#6e9ddf", "#84ace4", "#9fbbe4", "#c3c4d8", "#e4c2ac", "#f2bd8c", "#f6ad6e"]
    sky_h = 132
    bh = sky_h / len(bands)
    for y in range(sky_h):
        i = min(int(y / bh), len(bands) - 1)
        frac = y / bh - i
        for x in range(W):
            c = bands[i]
            if frac > 0.75 and i + 1 < len(bands) and (x + y) % 2 == 0:
                c = bands[i + 1]
            cv.put(x, y, c, raw=True)

    # ---------------------------------------------------------- sol / luna y estrellas
    if night:
        for _ in range(170):
            x, y = rng.randrange(W), rng.randrange(0, 100)
            cv.put(x, y, rng.choice(["#ffffff", "#fff3c4", "#cfd8ff", "#9aa6d8", "#9aa6d8"]), raw=True)
            if rng.random() < 0.06:
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    cv.put(x + dx, y + dy, "#6f7bb0", raw=True)
        mx, my = 312, 34
        cv.glow(mx + 7, my + 7, 26, "#8e9be0", 0.18)
        for y in range(14):
            for x in range(14):
                cv.put(mx + x, my + y, "#efeacb" if (x + y) % 7 else "#e2dcb8", raw=True)
        for cx, cy in ((4, 4), (9, 8), (5, 10)):
            cv.put(mx + cx, my + cy, "#cfc8a2", raw=True)
            cv.put(mx + cx + 1, my + cy, "#cfc8a2", raw=True)
    else:
        sx, sy = 300, 92
        cv.glow(sx + 8, sy + 8, 46, "#ffe3a0", 0.35)
        for y in range(16):
            for x in range(16):
                cv.put(sx + x, sy + y, "#fff1b8" if 2 < x < 13 and 2 < y < 13 else "#ffd98a", raw=True)

    # ---------------------------------------------------------- nubes de bloques
    for _ in range(6):
        cx, cy = rng.randrange(-20, W), rng.randrange(14, 70)
        for _ in range(rng.randint(3, 5)):
            w, h = rng.randint(12, 26), rng.randint(3, 6)
            ox, oy = rng.randint(-10, 18), rng.randint(-3, 2)
            for y in range(h):
                for x in range(w):
                    if night:
                        c = "#2c3466" if y < h - 1 else "#262c58"
                    else:
                        c = "#fff6ea" if y < h - 1 else "#f3d9c6"
                    cv.put(cx + ox + x, cy + oy + y, c, raw=True)

    # ---------------------------------------------------------- montañas lejanas y colinas medias
    far = terrain(rng, 104, 14, 6, 16, 0.5)
    for x in range(W):
        for y in range(far[x], 160):
            if night:
                c = "#222a55" if y < far[x] + 2 else "#1a2148"
            else:
                c = "#8f9fc2" if y < far[x] + 2 else "#7f8fb5"
            cv.put(x, y, c, raw=True)
    mid = terrain(rng, 124, 7, 4, 10, 0.55)
    for x in range(W):
        for y in range(mid[x], 170):
            cv.put(x, y, "#5c8f52" if y > mid[x] + 1 else "#6fa25e")
    for _ in range(26):  # siluetas de árboles lejanos
        x = rng.randrange(W)
        top = mid[x] - rng.randint(4, 8)
        for y in range(top, mid[x]):
            for dx in range(-2, 3):
                if abs(dx) < 2 or y > top + 1:
                    cv.put(x + dx, y, "#4d7d46")

    # ---------------------------------------------------------- primer plano: hierba, tierra y piedra
    ground = terrain(rng, 160, 6, 5, 14, 0.5)
    for x in range(110, 150):  # explanada para la cabaña
        ground[x] = 156
    pond = range(232, 270)
    for x in pond:
        ground[x] = max(ground[x], 166)
    grass = ["#6aa83c", "#5e9a35", "#78b848", "#64a23a"]
    dirt = ["#8a5b3b", "#7b5034", "#97664a", "#835639"]
    stone = ["#767676", "#6a6a6a", "#828282", "#707070"]
    for x in range(W):
        g = ground[x]
        for y in range(g, H):
            d = y - g
            if d < 3:
                c = rng.choice(grass)
            elif d < 24 + (x * 7 % 5):
                c = rng.choice(dirt)
            else:
                depth = min(1.0, (d - 24) / 30)
                c = mix(hx(rng.choice(stone)), (38, 30, 28), 0.25 + 0.55 * depth)
            cv.put(x, y, c)
        if rng.random() < 0.35 and x not in pond:  # matas de hierba
            cv.put(x, g - 1, rng.choice(grass))
    for x in pond:  # estanque
        for y in range(162, 166 + (2 if 238 < x < 264 else 0)):
            cv.put(x, y, "#7aa6e6" if y == 162 else "#4a7cc6")
        if rng.random() < 0.12:
            cv.put(x, 164, "#9cc0f0")
    for _ in range(40):  # flores
        x = rng.randrange(W)
        if x in pond:
            continue
        cv.put(x, ground[x] - 1, rng.choice(["#e2453c", "#f2d24b", "#f4f0e6", "#c46ad6"]))

    # ---------------------------------------------------------- árboles
    def tree(x, size):
        g = ground[x]
        trunk_h = 6 + size
        for y in range(g - trunk_h, g):
            cv.put(x, y, "#6b4a2b")
            cv.put(x + 1, y, "#5b3d23")
        r = 5 + size
        cy = g - trunk_h - r + 2
        leaves = ["#3f7d2e", "#4a8d34", "#56a03b", "#3a7229"]
        for y in range(cy - r, cy + r):
            for xx in range(x - r - 1, x + r + 3):
                dx, dy = xx - x - 0.5, (y - cy) * 1.15
                if dx * dx + dy * dy < r * r + rng.randint(-6, 6):
                    c = leaves[1] if dy < -r / 3 else rng.choice(leaves)
                    if dy < -r / 2 and rng.random() < 0.3:
                        c = "#6bb446"
                    cv.put(xx, y, c)
        if size >= 2 and not night:  # alguna manzana
            for _ in range(3):
                cv.put(x + rng.randint(-r + 2, r), cy + rng.randint(-r // 2, r // 2), "#d8402f")

    for x, s in ((24, 2), (58, 1), (168, 3), (204, 1), (290, 2), (338, 3), (366, 1)):
        tree(x, s)

    # ---------------------------------------------------------- cabaña con ventana encendida
    bx, by = 114, 156
    w, h = 30, 18
    for y in range(by - h, by):
        for x in range(bx, bx + w):
            plank = "#b07a4a" if (y - by) % 4 else "#8f5e36"
            if x in (bx, bx + w - 1):
                plank = "#6e4527"
            cv.put(x, y, plank)
    for i in range(10):  # tejado escalonado
        for x in range(bx - 3 + i, bx + w + 3 - i):
            cv.put(x, by - h - 1 - i, "#8a3d2b" if i % 2 else "#7a3324")
    for y in range(by - h - 12, by - h - 3):  # chimenea
        for x in range(bx + 22, bx + 26):
            cv.put(x, y, "#8c8c8c" if (x + y) % 3 else "#777777")
    for y in range(by - 10, by):  # puerta
        for x in range(bx + 4, bx + 10):
            cv.put(x, y, "#5a3a22")
    cv.put(bx + 8, by - 5, "#d9b45a")
    wx, wy = bx + 16, by - 12
    for y in range(wy, wy + 6):  # ventana
        for x in range(wx, wx + 8):
            lit = "#ffd27a" if (x - wx) not in (3, 4) and (y - wy) != 3 else "#c7863e"
            cv.put(x, y, lit, raw=True)
    cv.glow(wx + 4, wy + 3, 12 if night else 8, "#ffb050", 0.28 if night else 0.14)
    for i, (dx, dy) in enumerate(((0, 0), (2, -4), (1, -9), (4, -14), (3, -20))):  # humo
        for y in range(3):
            for x in range(3 + (i > 2)):
                cv.put(bx + 23 + dx + x, by - h - 15 + dy + y, "#5a5f80" if night else "#e6e0da", raw=True)
    for y in range(by - 9, by):  # farol junto a la puerta
        cv.put(bx - 4, y, "#4a3a2a")
    cv.put(bx - 4, by - 10, "#ffcf6a", raw=True)
    cv.put(bx - 4, by - 11, "#ffcf6a", raw=True)
    if night:
        cv.glow(bx - 4, by - 10, 7, "#ffb050", 0.30)

    # ---------------------------------------------------------- luciérnagas (noche)
    if night:
        for _ in range(18):
            x = rng.randrange(W)
            y = ground[x] - rng.randint(3, 22)
            cv.glow(x, y, 2, "#d8ff6a", 0.18)
            cv.put(x, y, "#f4ff8a", raw=True)

    return cv.img


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    draw(False).save(OUT / "escena-dia.png", optimize=True)
    draw(True).save(OUT / "escena-noche.png", optimize=True)
    for f in ("escena-dia.png", "escena-noche.png"):
        print(f, (OUT / f).stat().st_size, "bytes")
