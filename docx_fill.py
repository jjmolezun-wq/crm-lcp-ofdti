import re
import shutil
import zipfile

PLACEHOLDERS = [
    "Cliquez ou appuyez ici pour entrer du texte.",
    "Cliquez ou appuyez ici pour entrer une date.",
    "Cliquez ici pour taper du texte.",
]
BOX = "\u2610"
CHECKED = "\u2612"
TYPES = ["FIP", "FID", "FCP", "FCD", "FPT"]


def _paragraphs(xml):
    parts = re.split(r"(</w:p>)", xml)
    buf, out = "", []
    for part in parts:
        buf += part
        if part == "</w:p>":
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return out


def _ptext(p):
    return "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p))


def _replace_in_paragraph(p, values):
    it = iter(values)

    def cb(m):
        try:
            return next(it)
        except StopIteration:
            return m.group(0)

    pat = re.compile("|".join(re.escape(x) for x in PLACEHOLDERS))
    return pat.sub(cb, p)


def _fill_placeholders(xml, resolver):
    """resolver(texte_paragraphe) -> liste de valeurs pour les placeholders de ce paragraphe."""
    out = []
    for p in _paragraphs(xml):
        if any(ph in p for ph in PLACEHOLDERS):
            values = resolver(_ptext(p))
            if values:
                p = _replace_in_paragraph(p, values)
        out.append(p)
    return "".join(out)


def _check_domaines(xml, domaines_sel, types_sel, label_map):
    """Coche ☒ dans le tableau des domaines pour les (domaine, type) sélectionnés."""
    rows = re.findall(r"(<w:tr\b.*?</w:tr>)", xml, re.S)
    for row in rows:
        rtext = _ptext(row)
        code = None
        for c, lib in label_map.items():
            if lib in rtext:
                code = c
                break
        if code is None or code not in (domaines_sel or []):
            continue
        cells = re.findall(r"(<w:tc\b.*?</w:tc>)", row, re.S)
        # cellule 0 = libellé du domaine, cellules 1..5 = FIP..FPT
        for i, t in enumerate(TYPES):
            if t not in (types_sel or []):
                continue
            ci = i + 1
            if ci < len(cells):
                cell = cells[ci]
                if BOX in cell:
                    cells[ci] = cell.replace(BOX, CHECKED, 1)
        new_row = row
        for old, new in zip(cells, cells):
            pass
        # reconstruire la ligne avec les cellules modifiées
        parts = re.split(r"(<w:tc\b.*?</w:tc>)", row, flags=re.S)
        rebuilt = []
        ci = 0
        for part in parts:
            if part.startswith("<w:tc"):
                rebuilt.append(cells[ci] if ci < len(cells) else part)
                ci += 1
            else:
                rebuilt.append(part)
        new_row = "".join(rebuilt)
        xml = xml.replace(row, new_row, 1)
    return xml


def _rewrite(template_path, out_path, transform):
    zin = zipfile.ZipFile(template_path)
    xml = zin.read("word/document.xml").decode("utf-8")
    xml = transform(xml)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    zin.close()


def fill_certificat(template_path, out_path, *, numero, nom, adresse, siren, enregistrement,
                    emis_le, prise_effet, valable, edite_le, domaines_sel, types_sel, label_map):
    def resolver(txt):
        if txt.startswith("N°"):
            return [f"N° {numero}"]
        if "Emis le" in txt:
            return [emis_le, prise_effet, valable]
        if "Edit" in txt and "Pessac" in txt:
            return [edite_le]
        if txt.startswith("Nom"):
            return [nom]
        if txt.startswith("Adresse"):
            return [adresse]
        if "SIREN" in txt:
            return [siren]
        if "enregistrement" in txt:
            return [enregistrement]
        return []

    def transform(xml):
        xml = _fill_placeholders(xml, resolver)
        xml = _check_domaines(xml, domaines_sel, types_sel, label_map)
        return xml

    _rewrite(template_path, out_path, transform)


def fill_demande(template_path, out_path, identity):
    """Pré-remplit le bloc identification de l'OF (17 premiers placeholders), le reste est à compléter par l'OF."""
    queue = [
        identity.get("organisme", ""), identity.get("code_ape", ""), identity.get("siren", ""),
        identity.get("tva_intracom", ""), identity.get("numero_enregistrement", ""), identity.get("adresse", ""),
        identity.get("dirigeant", ""), identity.get("contact_nom", ""), identity.get("dirigeant_fonction", ""),
        identity.get("contact_fonction", ""), identity.get("dirigeant_tel", ""), identity.get("contact_tel", ""),
        identity.get("dirigeant_mail", ""), identity.get("contact_mail", ""),
        identity.get("effectifs_formation", ""), identity.get("nb_formateurs", ""), identity.get("periode_demande", ""),
    ]
    state = {"i": 0}
    LCP_RESERVE = ("DATE DE RECEPTION", "DATE DE VALIDATION", "PERSONNE AYANT")

    def resolver(txt):
        if any(m in txt.upper() for m in LCP_RESERVE):
            return []
        if state["i"] >= len(queue):
            return []
        v = queue[state["i"]]
        state["i"] += 1
        return [v]

    def transform(xml):
        return _fill_placeholders(xml, resolver)

    _rewrite(template_path, out_path, transform)
