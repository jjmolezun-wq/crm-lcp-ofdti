def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def bar_chart(data, w=520, h=260, color="#1668c4", label_size=11):
    """data : liste de (label, valeur)."""
    pad_l, pad_b, pad_t = 40, 46, 16
    cw = (w - pad_l - 10) / max(1, len(data))
    vmax = max([v for _, v in data] + [1])
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
             f'<rect width="{w}" height="{h}" fill="#ffffff" stroke="#e2e8f0" rx="10"/>']
    parts.append(f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{h - pad_b}" stroke="#c9d4e0"/>')
    parts.append(f'<line x1="{pad_l}" y1="{h - pad_b}" x2="{w - 10}" y2="{h - pad_b}" stroke="#c9d4e0"/>')
    for i in range(5):
        v = vmax * i / 4
        y = h - pad_b - (h - pad_b - pad_t) * i / 4
        parts.append(f'<line x1="{pad_l}" y1="{y:.0f}" x2="{w - 10}" y2="{y:.0f}" stroke="#f0f3f7"/>')
        parts.append(f'<text x="{pad_l - 6}" y="{y + 4:.0f}" font-size="9" fill="#5b6b7c" text-anchor="end" font-family="sans-serif">{int(v)}</text>')
    for i, (label, val) in enumerate(data):
        bh = (h - pad_b - pad_t) * val / vmax if vmax else 0
        x = pad_l + 8 + i * cw
        parts.append(f'<rect x="{x:.0f}" y="{h - pad_b - bh:.0f}" width="{cw - 16:.0f}" height="{bh:.0f}" fill="{color}" rx="3"/>')
        parts.append(f'<text x="{x + (cw - 16) / 2:.0f}" y="{h - pad_b - bh - 5:.0f}" font-size="10" fill="#1c2733" text-anchor="middle" font-family="sans-serif" font-weight="bold">{val}</text>')
        parts.append(f'<text x="{x + (cw - 16) / 2:.0f}" y="{h - pad_b + 14:.0f}" font-size="{label_size}" fill="#5b6b7c" text-anchor="middle" font-family="sans-serif">{_esc(label)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def donut(data, w=260, h=260):
    """data : liste de (label, valeur, couleur)."""
    total = sum(v for _, v, _ in data) or 1
    cx, cy, r, ri = w / 2, h / 2, 80, 52
    import math
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
             f'<rect width="{w}" height="{h}" fill="#ffffff" stroke="#e2e8f0" rx="10"/>']
    angle = -90
    for label, val, color in data:
        frac = val / total
        a2 = angle + frac * 360
        large = 1 if frac > 0.5 else 0
        x1 = cx + r * math.cos(math.radians(angle))
        y1 = cy + r * math.sin(math.radians(angle))
        x2 = cx + r * math.cos(math.radians(a2))
        y2 = cy + r * math.sin(math.radians(a2))
        xi1 = cx + ri * math.cos(math.radians(a2))
        yi1 = cy + ri * math.sin(math.radians(a2))
        xi2 = cx + ri * math.cos(math.radians(angle))
        yi2 = cy + ri * math.sin(math.radians(angle))
        parts.append(f'<path d="M {x1:.1f} {y1:.1f} A {r} {r} 0 {large} 1 {x2:.1f} {y2:.1f} L {xi1:.1f} {yi1:.1f} A {ri} {ri} 0 {large} 0 {xi2:.1f} {yi2:.1f} Z" fill="{color}"/>')
        angle = a2
    parts.append(f'<text x="{cx}" y="{cy - 4}" font-size="20" font-weight="bold" text-anchor="middle" fill="#1c2733" font-family="sans-serif">{total}</text>')
    parts.append(f'<text x="{cx}" y="{cy + 14}" font-size="10" text-anchor="middle" fill="#5b6b7c" font-family="sans-serif">total</text>')
    ly = 20
    for label, val, color in data:
        parts.append(f'<rect x="{w - 90}" y="{ly}" width="10" height="10" fill="{color}" rx="2"/>')
        parts.append(f'<text x="{w - 76}" y="{ly + 9}" font-size="10" fill="#1c2733" font-family="sans-serif">{_esc(label)} ({val})</text>')
        ly += 18
    parts.append("</svg>")
    return "".join(parts)
