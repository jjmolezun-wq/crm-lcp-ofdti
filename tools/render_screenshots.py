"""Rend des pages HTML capturées de l'app en visuels SVG (docs/screenshots/).

Usage :
    python3 tools/render_screenshots.py /tmp/pages docs/screenshots
"""
import os
import sys

from bs4 import BeautifulSoup

W = 1200
MAIN_W = 1120
MAIN_X = (W - MAIN_W) // 2
FONT = "Segoe UI, Roboto, Helvetica, Arial, sans-serif"

C = {
    "bg": "#f4f6fa", "header": "#14304f", "nav": "#d7e3f4", "brand": "#ffffff",
    "brand2": "#7fb3ff", "text": "#1c2733", "muted": "#5b6b7c", "link": "#1668c4",
    "card": "#ffffff", "border": "#e2e8f0", "rowline": "#e8edf3",
    "input_border": "#c9d4e0", "btn": "#1668c4", "btn2": "#e8edf3",
    "flash_bg": "#dcf5e3", "flash_bd": "#9edcb4", "flash_tx": "#177245",
    "err_bg": "#fde2e2", "err_bd": "#f3b6b6", "err_tx": "#b3261e",
    "badge": {"ok": ("#dcf5e3", "#177245"), "warn": ("#fdf0d3", "#9a6a00"),
              "danger": ("#fde2e2", "#b3261e"), "info": ("#ddeafd", "#1a56b0"),
              "muted": ("#e8edf3", "#5b6b7c")},
}


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def tw(s, size):
    return len(str(s)) * size * 0.52


def wrap(s, size, maxw):
    words = str(s).split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if tw(t, size) <= maxw:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


class Canvas:
    def __init__(self):
        self.parts = []

    def add(self, s):
        self.parts.append(s)

    def rect(self, x, y, w, h, fill, stroke=None, rx=0, sw=1):
        s = f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" fill="{fill}" rx="{rx}"'
        if stroke:
            s += f' stroke="{stroke}" stroke-width="{sw}"'
        self.add(s + "/>")

    def line(self, x1, y1, x2, y2, stroke):
        self.add(f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" stroke="{stroke}" stroke-width="1"/>')

    def text(self, x, y, s, size=14, fill=C["text"], weight="normal", anchor="start"):
        self.add(f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size}" fill="{fill}" font-weight="{weight}" '
                 f'font-family="{FONT}" text-anchor="{anchor}">{esc(s)}</text>')

    def badge(self, x, y, label, cls):
        bg, fg = C["badge"].get(cls, C["badge"]["muted"])
        w = tw(label, 12) + 20
        self.rect(x, y - 12, w, 20, bg, rx=10)
        self.text(x + 10, y + 2, label, size=12, fill=fg, weight="bold")
        return w

    def pill_btn(self, x, y, label, primary=True):
        bg = C["btn"] if primary else C["btn2"]
        fg = "#ffffff" if primary else C["text"]
        w = tw(label, 14) + 28
        self.rect(x, y - 16, w, 30, bg, rx=7)
        self.text(x + 14, y + 4, label, size=14, fill=fg, weight="bold")
        return w

    def svg(self, h):
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}">'
                f'<rect width="{W}" height="{h}" fill="{C["bg"]}"/>' + "".join(self.parts) + "</svg>")


def render_inline(el, cv, x, y, maxw, size=14):
    """Rendu inline (liens, badges, texte) ; retourne la nouvelle position y et largeur utilisée."""
    used = 0
    for node in el.children:
        if getattr(node, "name", None) is None:
            t = str(node).strip()
            if t:
                for ln in wrap(t, size, maxw - used):
                    cv.text(x + used, y, ln, size=size)
                    y += size + 4
                used = 0
            continue
        name = node.name
        if name == "a":
            t = node.get_text(strip=True)
            cv.text(x + used, y, t, size=size, fill=C["link"])
            used += tw(t, size) + 8
        elif name == "b" or name == "strong":
            t = node.get_text(strip=True)
            cv.text(x + used, y, t, size=size, weight="bold")
            used += tw(t, size) + 4
        elif name == "span" and "badge" in (node.get("class") or []):
            cls = [c for c in node.get("class") if c in C["badge"]]
            w = cv.badge(x + used, y, node.get_text(strip=True), cls[0] if cls else "muted")
            used += w + 8
        elif name == "br":
            y += size + 4
            used = 0
        elif name == "code":
            t = node.get_text(strip=True)
            cv.text(x + used, y, t, size=size - 1, fill=C["muted"])
            used += tw(t, size - 1) + 4
        else:
            y = render_inline(node, cv, x + used, y, maxw - used, size)
            used = 0
    return y


def render_table(tbl, cv, x, y, w):
    rows = tbl.find_all("tr")
    if not rows:
        return y
    ncols = max(len(r.find_all(["th", "td"])) for r in rows)
    colw = w / ncols
    for ri, r in enumerate(rows):
        cells = r.find_all(["th", "td"])
        cell_lines = []
        maxlines = 1
        for ci, c in enumerate(cells):
            cw = colw * (0.999) - 20
            lines = []
            for node in c.children:
                if getattr(node, "name", None) is None:
                    txt = str(node).strip()
                    if txt:
                        lines += wrap(txt, 13 if ri else 12, cw)
                elif node.name == "a":
                    lines += wrap(node.get_text(strip=True), 13, cw)
                elif node.name == "span" and "badge" in (node.get("class") or []):
                    lines.append("\x00badge:" + " ".join(node.get("class")) + ":" + node.get_text(strip=True))
                elif node.name in ("form", "button"):
                    lines += wrap(node.get_text(strip=True) or "bouton", 13, cw)
                elif node.name == "br":
                    lines.append("")
            cell_lines.append(lines)
            maxlines = max(maxlines, len(lines))
        rh = maxlines * 17 + 14
        if ri == 0:
            cv.rect(x, y, w, rh, "#f8fafc")
        for ci, lines in enumerate(cell_lines):
            cx = x + ci * colw + 10
            cy = y + 20
            for ln in lines:
                if ln.startswith("\x00badge:"):
                    _, cls, label = ln.split(":", 2)
                    cv.badge(cx, cy, label, cls)
                else:
                    cv.text(cx, cy, ln, size=12 if ri == 0 else 13,
                            fill=C["muted"] if ri == 0 else C["text"],
                            weight="bold" if ri == 0 else "normal")
                cy += 17
            if ci:
                cv.line(x + ci * colw, y, x + ci * colw, y + rh, C["rowline"])
        cv.line(x, y + rh, x + w, y + rh, C["rowline"])
        y += rh
    return y


def render_form(form, cv, x, y, w):
    for child in form.find_all(["label", "input", "textarea", "select", "button", "div"], recursive=True):
        if child.name == "div" and child.find(["label", "input"]):
            continue
        if child.name == "label":
            cv.text(x, y + 10, child.get_text(strip=True), size=13, fill="#42566b", weight="bold")
            y += 22
        elif child.name in ("input", "select"):
            ph = child.get("placeholder") or child.get("value") or ""
            cv.rect(x, y, min(w, 420), 30, "#ffffff", stroke=C["input_border"], rx=7)
            if ph:
                cv.text(x + 10, y + 20, ph, size=13, fill=C["muted"])
            y += 38
        elif child.name == "textarea":
            cv.rect(x, y, w, 70, "#ffffff", stroke=C["input_border"], rx=7)
            ph = child.get("placeholder") or ""
            if ph:
                cv.text(x + 10, y + 20, ph, size=13, fill=C["muted"])
            y += 78
        elif child.name == "button":
            label = child.get_text(strip=True)
            y += 6
            cv.pill_btn(x, y + 6, label, primary=("secondary" not in (child.get("class") or []) and "danger" not in (child.get("class") or [])))
            y += 40
    return y


def render_block(el, cv, x, y, w):
    name = el.name
    if name == "h1":
        cv.text(x, y + 22, el.get_text(strip=True), size=22, weight="bold")
        return y + 40
    if name == "h2":
        cv.text(x, y + 18, el.get_text(strip=True), size=17, weight="bold")
        return y + 32
    if name in ("p",):
        lines = wrap(el.get_text(" ", strip=True), 14, w)
        for ln in lines:
            cv.text(x, y + 14, ln, size=14, fill=C["muted"] if "muted" in (el.get("class") or []) else C["text"])
            y += 20
        return y + 6
    if name == "ul":
        for li in el.find_all("li", recursive=False):
            cv.text(x + 6, y + 14, "•", size=14)
            lines = wrap(li.get_text(" ", strip=True), 14, w - 20)
            for ln in lines:
                cv.text(x + 22, y + 14, ln, size=14)
                y += 20
        return y + 6
    if name == "table":
        return render_table(el, cv, x, y, w)
    if name == "form":
        return render_form(el, cv, x, y, w)
    if name == "div":
        cls = el.get("class") or []
        if "flash" in cls:
            lines = wrap(el.get_text(" ", strip=True), 14, w - 28)
            h = len(lines) * 20 + 20
            cv.rect(x, y, w, h, C["flash_bg"], stroke=C["flash_bd"], rx=8)
            for i, ln in enumerate(lines):
                cv.text(x + 14, y + 24 + i * 20, ln, size=14, fill=C["flash_tx"])
            return y + h + 14
        if "erreur" in cls:
            lines = wrap(el.get_text(" ", strip=True), 14, w - 28)
            h = len(lines) * 20 + 20
            cv.rect(x, y, w, h, C["err_bg"], stroke=C["err_bd"], rx=8)
            for i, ln in enumerate(lines):
                cv.text(x + 14, y + 24 + i * 20, ln, size=14, fill=C["err_tx"])
            return y + h + 14
        if "grid" in cls:
            stats = el.find_all("div", class_="stat", recursive=False)
            if stats:
                cw = (w - 14 * (len(stats) - 1)) / len(stats)
                maxh = 0
                for i, st in enumerate(stats):
                    sx = x + i * (cw + 14)
                    n = st.find("div", class_="n")
                    l = st.find("div", class_="l")
                    cv.rect(sx, y, cw, 64, C["card"], stroke=C["border"], rx=10)
                    if n:
                        cv.text(sx + 14, y + 30, n.get_text(strip=True), size=24, weight="bold")
                    if l:
                        cv.text(sx + 14, y + 50, l.get_text(strip=True), size=11, fill=C["muted"])
                    maxh = 64
                return y + maxh + 16
        if "comment" in cls:
            txt = el.get_text(" ", strip=True)
            lines = wrap(txt, 14, w - 24)
            h = len(lines) * 19 + 16
            cv.rect(x, y, 4, h, "#b3261e" if "interne" in cls else "#c9d4e0")
            cv.rect(x + 4, y, w - 4, h, "#fdf3f3" if "interne" in cls else "#f8fafc")
            for i, ln in enumerate(lines):
                cv.text(x + 16, y + 22 + i * 19, ln, size=14)
            return y + h + 8
        if "row" in cls:
            y += 8
            for node in el.children:
                if getattr(node, "name", None) == "a" and "btn" in (node.get("class") or []):
                    primary = "secondary" not in (node.get("class") or [])
                    wbtn = cv.pill_btn(x, y + 4, node.get_text(strip=True), primary=primary)
                    x += wbtn + 10
                elif getattr(node, "name", None) in ("select", "input"):
                    cv.rect(x, y - 12, 220, 28, "#ffffff", stroke=C["input_border"], rx=7)
                    val = node.get("value") or node.get("placeholder") or ""
                    cv.text(x + 8, y + 6, val, size=13, fill=C["muted"])
                    x += 230
                elif getattr(node, "name", None) == "button":
                    wbtn = cv.pill_btn(x, y + 4, node.get_text(strip=True), primary="secondary" not in (node.get("class") or []))
                    x += wbtn + 10
            return y + 26
        if "certificat" in cls:
            return render_certificat(el, cv, x, y, w)
        # conteneur générique
        for child in el.children:
            if getattr(child, "name", None):
                y = render_block(child, cv, x, y, w)
        return y
    if name == "a":
        t = el.get_text(strip=True)
        cv.text(x, y + 14, t, size=14, fill=C["link"])
        return y + 24
    if name == "br":
        return y + 10
    return y


def render_certificat(el, cv, x, y, w):
    texts = [p.get_text(" ", strip=True) for p in el.find_all(["p", "h1", "div"]) if p.get_text(strip=True)]
    titre = next((t for t in texts if "CONFORMIT" in t.upper()), "Certificat OFDTI")
    org = next((t for t in texts if t and t not in titre and "Nous" not in t and "certifi" not in t.lower()
                and "référentiel" not in t and "délivré" not in t and "Document" not in t and t != "Imprimer"
                and t != "Retour" and not t.startswith("N°") and "OFDTI" not in t), "")
    num = next((t for t in texts if t.startswith("N°")), "")
    svc = next((t for t in texts if "référentiel" in t), "")
    svc = svc.split("service :")[-1].strip() if "service :" in svc else ""
    rows = [tr.get_text(" ", strip=True) for tr in el.find_all("tr")]
    h = 560
    cv.rect(x + 60, y, w - 120, h, "#ffffff", stroke="#14304f", rx=4, sw=3)
    cx = x + w / 2
    yy = y + 60
    cv.text(cx, yy, titre, size=26, weight="bold", anchor="middle")
    yy += 30
    cv.text(cx, yy, "délivré par LCP — Certification OFDTI", size=13, fill=C["muted"], anchor="middle")
    yy += 50
    cv.text(cx, yy, "Nous certifions que", size=15, anchor="middle")
    yy += 40
    cv.text(cx, yy, org, size=22, weight="bold", anchor="middle")
    yy += 40
    cv.text(cx, yy, "est certifié conforme au référentiel OFDTI pour le service :", size=15, anchor="middle")
    yy += 34
    cv.text(cx, yy, svc, size=17, weight="bold", anchor="middle")
    yy += 50
    cv.text(cx, yy, num, size=20, weight="bold", anchor="middle")
    yy += 60
    for r in rows:
        parts = [p.strip() for p in r.split() if p.strip()]
        label = parts[0] if parts else ""
        val = " ".join(parts[1:]) if len(parts) > 1 else ""
        cv.text(cx - 140, yy, label, size=13, fill=C["muted"])
        cv.text(cx + 140, yy, val, size=13, anchor="middle")
        yy += 26
    yy += 30
    cv.text(cx, yy, "Document généré automatiquement par le CRM LCP", size=12, fill=C["muted"], anchor="middle")
    return y + h + 20


def render_page(html_str, out_path):
    soup = BeautifulSoup(html_str, "html.parser")
    cv = Canvas()
    y = 0
    header = soup.find("header")
    if header:
        cv.rect(0, 0, W, 56, C["header"])
        brand = header.find("div", class_="brand")
        bt = brand.get_text(" ", strip=True) if brand else "CRM LCP"
        cv.text(24, 35, bt, size=18, fill=C["brand"], weight="bold")
        nav = header.find("nav")
        nx = 300
        if nav:
            for a in nav.find_all("a"):
                t = a.get_text(strip=True)
                cv.text(nx, 34, t, size=14, fill=C["nav"])
                nx += tw(t, 14) + 24
        user = header.find("span", class_="user")
        if user:
            ut = user.get_text(" ", strip=True)
            cv.text(W - 24, 34, ut, size=13, fill="#bcd2ee", anchor="end")
        y = 80
    else:
        y = 40
    main = soup.find("main") or soup.find("body")
    x = MAIN_X
    w = MAIN_W
    for child in main.children:
        if getattr(child, "name", None) is None:
            t = str(child).strip()
            if t:
                for ln in wrap(t, 14, w):
                    cv.text(x, y + 14, ln, size=14)
                    y += 20
            continue
        if child.name == "div" and "card" in (child.get("class") or []):
            inner_y = y + 6
            cv_y = inner_y
            for sub in child.children:
                if getattr(sub, "name", None) is None:
                    continue
                if sub.name == "h2":
                    cv.text(x + 18, cv_y + 24, sub.get_text(strip=True), size=17, weight="bold")
                    cv_y += 40
                else:
                    cv_y = render_block(sub, cv, x + 18, cv_y, w - 36)
            card_h = cv_y - inner_y + 14
            cv.rect(x, y, w, card_h, C["card"], stroke=C["border"], rx=10)
            # redessiner le contenu par-dessus la carte : on triche en deux passes
            cv.parts = cv.parts  # la carte est dessinée après -> on la remonte
            y = y + card_h + 18
            # NOTE: pour garder l'ordre z, on insère la carte avant son contenu
        else:
            y = render_block(child, cv, x, y, w)
    # correction d'ordre : reconstruire proprement
    cv2 = Canvas()
    y2 = 0
    if header:
        cv2.rect(0, 0, W, 56, C["header"])
        brand = header.find("div", class_="brand")
        bt = brand.get_text(" ", strip=True) if brand else "CRM LCP"
        cv2.text(24, 35, bt, size=18, fill=C["brand"], weight="bold")
        nav = header.find("nav")
        nx = 300
        if nav:
            for a in nav.find_all("a"):
                t = a.get_text(strip=True)
                cv2.text(nx, 34, t, size=14, fill=C["nav"])
                nx += tw(t, 14) + 24
        user = header.find("span", class_="user")
        if user:
            cv2.text(W - 24, 34, user.get_text(" ", strip=True), size=13, fill="#bcd2ee", anchor="end")
        y2 = 80
    else:
        y2 = 40
    for child in main.children:
        if getattr(child, "name", None) is None:
            t = str(child).strip()
            if t:
                for ln in wrap(t, 14, MAIN_W):
                    cv2.text(MAIN_X, y2 + 14, ln, size=14)
                    y2 += 20
            continue
        if child.name == "div" and "card" in (child.get("class") or []):
            # passe 1 : calculer la hauteur
            probe = Canvas()
            py = 0
            for sub in child.children:
                if getattr(sub, "name", None) is None:
                    continue
                if sub.name == "h2":
                    py += 40
                else:
                    py = render_block(sub, probe, 0, py, MAIN_W - 36)
            card_h = py + 24
            cv2.rect(MAIN_X, y2, MAIN_W, card_h, C["card"], stroke=C["border"], rx=10)
            cy = y2 + 6
            for sub in child.children:
                if getattr(sub, "name", None) is None:
                    continue
                if sub.name == "h2":
                    cv2.text(MAIN_X + 18, cy + 24, sub.get_text(strip=True), size=17, weight="bold")
                    cy += 40
                else:
                    cy = render_block(sub, cv2, MAIN_X + 18, cy, MAIN_W - 36)
            y2 = y2 + card_h + 18
        else:
            y2 = render_block(child, cv2, MAIN_X, y2, MAIN_W)
    h = y2 + 40
    with open(out_path, "w") as f:
        f.write(cv2.svg(h))
    return h


def main():
    pages_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/pages"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "..", "docs", "screenshots")
    os.makedirs(out_dir, exist_ok=True)
    for fn in sorted(os.listdir(pages_dir)):
        if not fn.endswith(".html"):
            continue
        name = fn[:-5]
        with open(os.path.join(pages_dir, fn)) as f:
            html_str = f.read()
        out = os.path.join(out_dir, name + ".svg")
        h = render_page(html_str, out)
        print(f"{out} ({h}px)")


if __name__ == "__main__":
    main()
