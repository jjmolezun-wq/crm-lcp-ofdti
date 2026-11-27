"""Convertit les visuels SVG (docs/screenshots/*.svg) en PNG (docs/screenshots/*.png).

Rastériseur pur Python (pas de dépendance) : parse le SVG, dessine rect/line/texte
(police bitmap 5x7 intégrée), encode le PNG (zlib). Usage :
    python3 tools/svg2png.py docs/screenshots
"""
import os
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zlib

SVGNS = "{http://www.w3.org/2000/svg}"
SCALE = 1  # largeur finale des PNG = largeur réelle de la page (1200px) : affichage 1:1 lisible

# Police 5x7 (7 lignes de 5 colonnes), caractères ASCII + accents aplatis.
F = {
 " ": [""]*7,
 "A": [".###.","#...#","#...#","#####","#...#","#...#","#...#"],
 "B": ["####.","#...#","#...#","####.","#...#","#...#","####."],
 "C": [".###.","#...#","#....","#....","#....","#...#",".###."],
 "D": ["####.","#...#","#...#","#...#","#...#","#...#","####."],
 "E": ["#####","#....","#....","####.","#....","#....","#####"],
 "F": ["#####","#....","#....","####.","#....","#....","#...."],
 "G": [".###.","#...#","#....","#.###","#...#","#...#",".###."],
 "H": ["#...#","#...#","#...#","#####","#...#","#...#","#...#"],
 "I": ["#####","..#..","..#..","..#..","..#..","..#..","#####"],
 "J": ["..###","...#.","...#.","...#.","...#.","#..#.",".##.."],
 "K": ["#...#","#..#.","#.#..","##...","#.#..","#..#.","#...#"],
 "L": ["#....","#....","#....","#....","#....","#....","#####"],
 "M": ["#...#","##.##","#.#.#","#.#.#","#...#","#...#","#...#"],
 "N": ["#...#","##..#","#.#.#","#..##","#...#","#...#","#...#"],
 "O": [".###.","#...#","#...#","#...#","#...#","#...#",".###."],
 "P": ["####.","#...#","#...#","####.","#....","#....","#...."],
 "Q": [".###.","#...#","#...#","#...#","#.#.#","#..#.",".##.#"],
 "R": ["####.","#...#","#...#","####.","#.#..","#..#.","#...#"],
 "S": [".####","#....","#....",".###.","....#","....#","####."],
 "T": ["#####","..#..","..#..","..#..","..#..","..#..","..#.."],
 "U": ["#...#","#...#","#...#","#...#","#...#","#...#",".###."],
 "V": ["#...#","#...#","#...#","#...#","#...#",".#.#.","..#.."],
 "W": ["#...#","#...#","#...#","#.#.#","#.#.#","##.##","#...#"],
 "X": ["#...#","#...#",".#.#.","..#..",".#.#.","#...#","#...#"],
 "Y": ["#...#","#...#",".#.#.","..#..","..#..","..#..","..#.."],
 "Z": ["#####","....#","...#.","..#..",".#...","#....","#####"],
 "a": [".....",".....",".###.","....#",".####","#...#",".####"],
 "b": ["#....","#....","####.","#...#","#...#","#...#","####."],
 "c": [".....",".....",".###.","#....","#....","#...#",".###."],
 "d": ["....#","....#",".####","#...#","#...#","#...#",".####"],
 "e": [".....",".....",".###.","#...#","#####","#....",".###."],
 "f": ["..##.",".#..#",".#...","###..",".#...",".#...",".#..."],
 "g": [".....",".####","#...#","#...#",".####","....#",".###."],
 "h": ["#....","#....","####.","#...#","#...#","#...#","#...#"],
 "i": ["..#..",".....",".##..","..#..","..#..","..#..",".###."],
 "j": ["...#.",".....","..##.","...#.","...#.","#..#.",".##.."],
 "k": ["#....","#....","#..#.","#.#..","##...","#.#..","#..#."],
 "l": [".##..","..#..","..#..","..#..","..#..","..#..",".###."],
 "m": [".....",".....","##.#.","#.#.#","#.#.#","#.#.#","#.#.#"],
 "n": [".....",".....","####.","#...#","#...#","#...#","#...#"],
 "o": [".....",".....",".###.","#...#","#...#","#...#",".###."],
 "p": [".....","####.","#...#","#...#","####.","#....","#...."],
 "q": [".....",".####","#...#","#...#",".####","....#","....#"],
 "r": [".....",".....","#.##.","##..#","#....","#....","#...."],
 "s": [".....",".....",".####","#....",".###.","....#","####."],
 "t": [".#...",".#...","###..",".#...",".#...",".#..#","..##."],
 "u": [".....",".....","#...#","#...#","#...#","#...#",".####"],
 "v": [".....",".....","#...#","#...#","#...#",".#.#.","..#.."],
 "w": [".....",".....","#...#","#.#.#","#.#.#","#.#.#",".#.#."],
 "x": [".....",".....","#...#",".#.#.","..#..",".#.#.","#...#"],
 "y": [".....",".....","#...#","#...#",".####","....#",".###."],
 "z": [".....",".....","#####","...#.","..#..",".#...","#####"],
 "0": [".###.","#...#","#..##","#.#.#","##..#","#...#",".###."],
 "1": ["..#..",".##..","..#..","..#..","..#..","..#..",".###."],
 "2": [".###.","#...#","....#","..##.",".#...","#....","#####"],
 "3": ["####.","....#","....#",".###.","....#","....#","####."],
 "4": ["...#.","..##.",".#.#.","#..#.","#####","...#.","...#."],
 "5": ["#####","#....","####.","....#","....#","#...#",".###."],
 "6": ["..##.",".#...","#....","####.","#...#","#...#",".###."],
 "7": ["#####","....#","...#.","..#..","..#..","..#..","..#.."],
 "8": [".###.","#...#","#...#",".###.","#...#","#...#",".###."],
 "9": [".###.","#...#","#...#",".####","....#","...#.",".##.."],
 ".": [".....",".....",".....",".....",".....",".##..",".##.."],
 ",": [".....",".....",".....",".....",".##..",".##..",".#..."],
 ":": [".....",".##..",".##..",".....",".##..",".##..","....."],
 ";": [".....",".##..",".##..",".....",".##..",".##..",".#..."],
 "!": ["..#..","..#..","..#..","..#..","..#..",".....","..#.."],
 "?": [".###.","#...#","....#","..##.","..#..",".....","..#.."],
 "'": ["..#..","..#..",".#...",".....",".....",".....","....."],
 '"': [".#.#.",".#.#.",".#.#.",".....",".....",".....","....."],
 "-": [".....",".....",".....","#####",".....",".....","....."],
 "(": ["...#.","..#..",".#...",".#...",".#...","..#..","...#."],
 ")": [".#...","..#..","...#.","...#.","...#.","..#..",".#..."],
 "/": ["....#","....#","...#.","..#..",".#...","#....","#...."],
 "%": ["##..#","##.#.","...#.","..#..",".#...",".#.##","#..##"],
 "+": [".....","..#..","..#..","#####","..#..","..#..","....."],
 "*": [".....",".#.#.","..#..",".###.","..#..",".#.#.","....."],
 "=": [".....",".....","#####",".....","#####",".....","....."],
 "<": ["...#.","..#..",".#...","#....",".#...","..#..","...#."],
 ">": [".#...","..#..","...#.","....#","...#.","..#..",".#..."],
 "#": [".#.#.","#####",".#.#.",".#.#.",".#.#.","#####",".#.#."],
 "&": [".##..","#..#.","#.#..",".##..","#.#.#","#..#.",".##.#"],
 "@": [".###.","#...#","#.###","#.#.#","#.##.","#....",".###."],
 "_": [".....",".....",".....",".....",".....",".....","#####"],
 "[": [".###.",".#...",".#...",".#...",".#...",".#...",".###."],
 "]": [".###.","...#.","...#.","...#.","...#.","...#.",".###."],
 "{": ["...#.","..#..","..#..",".#...","..#..","..#..","...#."],
 "}": [".#...","..#..","..#..","...#.","..#..","..#..",".#..."],
 "|": ["..#..","..#..","..#..","..#..","..#..","..#..","..#.."],
 "^": ["..#..",".#.#.","#...#",".....",".....",".....","....."],
 "`": [".#...","..#..",".....",".....",".....",".....","....."],
 "~": [".....",".....",".#.#.","#.#.#",".....",".....","....."],
 "€": [".###.","#...#","#....","####.","#....","#...#",".###."],
 "°": [".##..","#..#.",".##..",".....",".....",".....","....."],
 "«": ["..##.",".#..#","#..#.",".....",".....",".....","....."],
 "»": [".##..","#..#.","..#.#",".....",".....",".....","....."],
 "→": [".....","..#..","...#.","#####","...#.","..#..","....."],
 "·": [".....",".....",".....",".##..",".##..",".....","....."],
 "—": [".....",".....",".....","#####",".....",".....","....."],
 "☒": ["#####","#.#.#","#####","#####","#####","#.#.#","#####"],
 "☐": ["#####","#...#","#...#","#...#","#...#","#...#","#####"],
}

ACCENTS = {"é":"e","è":"e","ê":"e","ë":"e","à":"a","â":"a","ä":"a","ç":"c","î":"i","ï":"i",
           "ô":"o","ö":"o","ù":"u","û":"u","ü":"u","ÿ":"y","É":"E","È":"E","Ê":"E","À":"A",
           "Â":"A","Ç":"C","Î":"I","Ô":"O","Ù":"U","Û":"U","•":"·"}


def norm(ch):
    return ACCENTS.get(ch, ch)


def glyph(ch):
    return F.get(norm(ch), F.get(ch.upper(), F["?"]))


SS = 4  # sur-échantillonnage des formes (rect/ligne) avant moyenne ; le texte est
        # dessiné ensuite, à la résolution finale, avec des glyphes lissés (alpha)

import math
from operator import add as _add


class Img:
    def __init__(self, w, h, bg=(255, 255, 255)):
        self.w, self.h = int(w), int(h)
        row = bytes(bg) * self.w
        self.px = bytearray()
        for _ in range(self.h):
            self.px += row

    def _set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i:i + 3] = bytes(c)

    def _fill(self, x, y, w, h, c):
        x0, y0 = max(int(x), 0), max(int(y), 0)
        x1, y1 = min(int(x + w), self.w), min(int(y + h), self.h)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(c) * (x1 - x0)
        span = (x1 - x0) * 3
        for yy in range(y0, y1):
            base = (yy * self.w + x0) * 3
            self.px[base:base + span] = row

    def rect(self, x, y, w, h, fill=None, stroke=None, sw=1):
        if fill:
            self._fill(x, y, w, h, fill)
        if stroke:
            sw = max(1, int(sw))
            self._fill(x, y, w, sw, stroke)
            self._fill(x, y + h - sw, w, sw, stroke)
            self._fill(x, y, sw, h, stroke)
            self._fill(x + w - sw, y, sw, h, stroke)

    def line(self, x1, y1, x2, y2, color, sw=1):
        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
        dx, dy = abs(x2 - x1), -abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx + dy
        sw = max(1, int(sw))
        while True:
            for t1 in range(sw):
                for t2 in range(sw):
                    self._set(x1 + t1, y1 + t2, color)
            if x1 == x2 and y1 == y2:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x1 += sx
            if e2 <= dx:
                err += dx
                y1 += sy

    _alpha_cache = {}

    def _alpha_glyph(self, ch, scale, bold):
        """Glyphe 5x7 rendu en interne à 4x avec un noyau gaussien, puis moyenné :
        atlas final (5*scale)x(7*scale), bords lisses, alpha 0-255."""
        key = (ch, scale, bold)
        atlas = self._alpha_cache.get(key)
        if atlas is not None:
            return atlas
        g = glyph(ch)
        rows = [(row + ".....")[:5] for row in (list(g) + [""] * 7)[:7]]
        GS = 4
        hs = scale * GS
        w, h = 5 * hs, 7 * hs
        sx = 0.95 if bold else 0.70
        sy = 0.70
        ix = 1.0 / (2.0 * sx * sx)
        iy = 1.0 / (2.0 * sy * sy)
        hi = []
        for py in range(h):
            cy = (py + 0.5) / hs
            row = bytearray(w)
            for pxi in range(w):
                cx = (pxi + 0.5) / hs
                s = 0.0
                for r in range(7):
                    wy = (cy - r - 0.5) ** 2 * iy
                    if wy > 4.0:
                        continue
                    gr = rows[r]
                    for c in range(5):
                        if gr[c] == "#":
                            e = (cx - c - 0.5) ** 2 * ix + wy
                            if e <= 4.0:
                                s += math.exp(-e)
                row[pxi] = int(min(s, 1.0) * 255 + 0.5)
            hi.append(bytes(row))
        atlas = []
        for py in range(7 * scale):
            row = bytearray(5 * scale)
            for pxi in range(5 * scale):
                acc = 0
                for k in range(GS):
                    hr = hi[py * GS + k]
                    base = pxi * GS
                    for j in range(GS):
                        acc += hr[base + j]
                row[pxi] = acc // (GS * GS)
            atlas.append(bytes(row))
        self._alpha_cache[key] = atlas
        return atlas

    def text(self, x, y, s, size, fill, anchor="start", bold=False):
        # size : hauteur de police en pixels de l'image FINALE
        scale = max(1, round(size / 7.0))
        cw = 6 * scale
        total = cw * len(s)
        x = int(x)
        y = int(y)
        if anchor == "middle":
            x -= total // 2
        elif anchor == "end":
            x -= total
        f0, f1, f2 = fill
        px = self.px
        W, H = self.w, self.h
        for ch in s:
            atlas = self._alpha_glyph(ch, scale, bold)
            for py, row in enumerate(atlas):
                yy = y + py
                if yy < 0 or yy >= H:
                    continue
                base = yy * W * 3
                for pxi in range(len(row)):
                    a = row[pxi]
                    if a == 0:
                        continue
                    xx = x + pxi
                    if xx < 0 or xx >= W:
                        continue
                    i = base + xx * 3
                    if a >= 255:
                        px[i] = f0
                        px[i + 1] = f1
                        px[i + 2] = f2
                    else:
                        f = a * (1.0 / 255.0)
                        g = 1.0 - f
                        px[i] = int(px[i] * g + f0 * f)
                        px[i + 1] = int(px[i + 1] * g + f1 * f)
                        px[i + 2] = int(px[i + 2] * g + f2 * f)
            x += cw

    def save_png(self, path):
        def chunk(tag, data):
            c = struct.pack(">I", len(data)) + tag + data
            return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        raw = bytearray()
        stride = self.w * 3
        for y in range(self.h):
            raw.append(0)
            raw += self.px[y * stride:(y + 1) * stride]
        png = (b"\x89PNG\r\n\x1a\n"
               + chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
               + chunk(b"IEND", b""))
        with open(path, "wb") as f:
            f.write(png)


def downsample(px, w, h, s):
    """Moyenne par blocs s x s (par canal) : anti-crénelage du rendu sur-échantillonné."""
    ow, oh = w // s, h // s
    out = bytearray(ow * oh * 3)
    div = (s * s).__rfloordiv__
    for c in range(3):
        ch = bytes(px[c::3])
        for rp in range(oh):
            acc = None
            for k in range(s):
                row = ch[(rp * s + k) * w:(rp * s + k + 1) * w]
                hsum = row[0::s]
                for i in range(1, s):
                    hsum = map(_add, hsum, row[i::s])
                acc = hsum if acc is None else map(_add, acc, hsum)
            start = rp * ow * 3 + c
            out[start:start + (ow - 1) * 3 + 1:3] = bytes(map(div, acc))
    return out


def _num(v, default=0.0):
    m = re.match(r"[-+]?[0-9]*\.?[0-9]+", v or "")
    return float(m.group()) if m else default


def parse_color(v, default=(28, 39, 51)):
    if not v or v == "none":
        return None
    v = v.strip()
    if v.startswith("#"):
        v = v[1:]
        if len(v) == 3:
            v = "".join(c * 2 for c in v)
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    named = {"white": (255, 255, 255), "black": (0, 0, 0)}
    return named.get(v, default)


def render_svg(svg_path, png_path):
    tree = ET.parse(svg_path)
    root = tree.getroot()
    W = int(_num(root.get("width")))
    H = int(_num(root.get("height")))
    R = SCALE * SS
    buf = Img(W * R, H * R)
    out = Img(W * SCALE, H * SCALE)

    def walk(el, ox, oy, phase):
        for child in el:
            tag = child.tag.replace(SVGNS, "")
            x = ox + _num(child.get("x"))
            y = oy + _num(child.get("y"))
            if tag == "rect":
                if phase == 0:
                    buf.rect(x * R, y * R, _num(child.get("width")) * R, _num(child.get("height")) * R,
                             fill=parse_color(child.get("fill")), stroke=parse_color(child.get("stroke")),
                             sw=max(1, int(_num(child.get("stroke-width", "1")) * R)))
            elif tag == "line":
                if phase == 0:
                    buf.line((ox + _num(child.get("x1"))) * R, (oy + _num(child.get("y1"))) * R,
                             (ox + _num(child.get("x2"))) * R, (oy + _num(child.get("y2"))) * R,
                             parse_color(child.get("stroke"), (200, 200, 200)),
                             sw=max(1, int(_num(child.get("stroke-width", "1")) * R)))
            elif tag == "path":
                pass  # camemberts : ignorés en PNG (les barres suffisent)
            elif tag == "text":
                if phase == 1:
                    size = _num(child.get("font-size"), 14)
                    content = "".join(child.itertext())
                    out.text(x * SCALE, (y - size * 0.8) * SCALE, content, size * SCALE,
                             parse_color(child.get("fill"), (28, 39, 51)),
                             anchor=child.get("text-anchor", "start"),
                             bold=child.get("font-weight") in ("bold", "600", "700"))
            else:
                walk(child, x, y, phase)

    walk(root, 0, 0, 0)
    out.px = downsample(buf.px, buf.w, buf.h, SS)
    walk(root, 0, 0, 1)
    out.save_png(png_path)
    return W, H


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "docs", "screenshots")
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".svg"):
            svg = os.path.join(d, fn)
            png = os.path.join(d, fn[:-4] + ".png")
            w, h = render_svg(svg, png)
            print(f"{png} ({w}x{h} -> {w * SCALE}x{h * SCALE}px)")


if __name__ == "__main__":
    main()
