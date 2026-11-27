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
    """resolver(texte_paragraphe, texte_paragraphe_précédent) -> liste de valeurs pour les placeholders."""
    out = []
    prev = ""
    for p in _paragraphs(xml):
        if any(ph in p for ph in PLACEHOLDERS):
            values = resolver(_ptext(p), prev)
            if values:
                p = _replace_in_paragraph(p, values)
        t = _ptext(p)
        if t.strip() and not any(ph in t for ph in PLACEHOLDERS):
            prev = t
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
    def resolver(txt, prev=""):
        for t in (txt, prev):
            if t.startswith("N°"):
                return [f"N° {numero}"]
            if "Emis le" in t:
                return [emis_le, prise_effet, valable]
            if "Edit" in t and "Pessac" in t:
                return [edite_le]
            if t.startswith("Nom"):
                return [nom]
            if t.startswith("Adresse"):
                return [adresse]
            if "SIREN" in t:
                return [siren]
            if "enregistrement" in t:
                return [enregistrement]
        return []

    def transform(xml):
        xml = _fill_placeholders(xml, resolver)
        xml = _check_domaines(xml, domaines_sel, types_sel, label_map)
        return xml

    _rewrite(template_path, out_path, transform)


def fill_generic(template_path, out_path, label_values, check_box_index=None):
    """Remplit les placeholders dont le paragraphe commence par un des libellés donnés.
    label_values : liste de (prefix_libellé, valeur). check_box_index : index de la case ☐ à cocher (☒)."""
    def resolver(txt, prev=""):
        for prefix, value in label_values:
            if txt.strip().startswith(prefix) or (any(ph in txt for ph in PLACEHOLDERS) and prev.strip().startswith(prefix)):
                return [value]
        return []

    def transform(xml):
        xml = _fill_placeholders(xml, resolver)
        if check_box_index is not None:
            boxes = [m.start() for m in re.finditer(re.escape(BOX), xml)]
            if len(boxes) > check_box_index:
                pos = boxes[check_box_index]
                xml = xml[:pos] + CHECKED + xml[pos + 1:]
        return xml

    _rewrite(template_path, out_path, transform)


def fill_attestation_recevabilite(template_path, out_path, *, contact, numero, organisme, adresse, lieu, date_emission):
    fill_generic(template_path, out_path, [
        ("Nom et Prénom", contact),
        ("Dossier N°", numero),
        ("Organisme", organisme),
        ("Adresse", adresse),
        ("Fait à", lieu),
        ("Le", date_emission),
    ])


def fill_dossier_candidature(template_path, out_path, *, organisme, numero, contact, prepare_par, renouvellement=False):
    fill_generic(template_path, out_path, [
        ("Organisme", organisme),
        ("Réf Offre", numero),
        ("A l'attention de", contact),
        ("Préparé par", prepare_par),
    ], check_box_index=1 if renouvellement else 0)


def fill_avenant_tarifaire(template_path, out_path, *, numero_avenant, numero_dossier, date_signature):
    fill_generic(template_path, out_path, [
        ("Avenant n°", numero_avenant),
        ("Dossier n°", numero_dossier),
        ("Dossier signé le", date_signature),
    ])


def _esc_xml(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _run(value):
    return f'<w:r><w:t xml:space="preserve">{_esc_xml(value)}</w:t></w:r>'


def _insert_after_text(row, anchor, value):
    pos = row.find(anchor)
    if pos < 0:
        return row
    end = row.find("</w:t>", pos)
    if end < 0:
        return row
    end += len("</w:t>")
    return row[:end] + _run(value) + row[end:]


def _append_row(row, value):
    end = row.rfind("</w:p>")
    if end < 0:
        return row
    return row[:end] + _run(" " + value) + row[end:]


def fill_fiche_ecart(template_path, out_path, *, reference, domaine="", site="", ref_grille="", libelle="", risque="", auditeur="", date="", gravite="mineur"):
    def transform(xml):
        out = []
        last = 0
        for m in re.finditer(r"<w:tr\b.*?</w:tr>", xml, re.S):
            row = m.group(0)
            txt = _ptext(row)
            new = row
            if "Fiche écart N°" in txt:
                new = _insert_after_text(new, "N°", " " + reference)
                if gravite == "majeur":
                    new = _insert_after_text(new, "Ecart Majeur", "").replace(BOX, CHECKED, 0)
                    # coche la case Majeur : 2e case de la ligne
                    idx = [mm.start() for mm in re.finditer(re.escape(BOX), new)]
                    if len(idx) >= 2:
                        p = idx[1]
                        new = new[:p] + CHECKED + new[p + 1:]
                else:
                    idx = [mm.start() for mm in re.finditer(re.escape(BOX), new)]
                    if idx:
                        p = idx[0]
                        new = new[:p] + CHECKED + new[p + 1:]
            elif txt.startswith("Domaine") and "Site concerné" in txt:
                new = _insert_after_text(new, "Domaine", " " + domaine)
                new = _insert_after_text(new, "Site concerné", " " + site)
            elif "Référence de la grille" in txt:
                new = _append_row(new, ref_grille)
            elif "Libellé de l'Ecart" in txt or "Libellé de l’écart" in txt:
                new = _append_row(new, libelle)
            elif "Risque Induit" in txt:
                new = _append_row(new, risque)
            elif "Auditeur" in txt and "Date" in txt and any(ph in new for ph in PLACEHOLDERS):
                new = _insert_after_text(new, "Auditeur", " " + auditeur)
                new = re.sub("|".join(re.escape(x) for x in PLACEHOLDERS), date, new, count=1)
            out.append(xml[last:m.start()])
            out.append(new)
            last = m.end()
        out.append(xml[last:])
        return "".join(out)

    _rewrite(template_path, out_path, transform)


def fill_ordre_mission(template_path, out_path, *, numero_om, organisme, adresse, cp, ville, contact, auditeur, date):
    fill_generic(template_path, out_path, [
        ("Ordre de Mission N°", numero_om),
        ("Organisme", organisme),
        ("Adresse", adresse),
        ("Cp", cp),
        ("Ville", ville),
        ("NOM et Prénom", contact),
    ])
    # second passe pour l'auditeur (label générique répété) : on remplit le premier placeholder restant par l'auditeur
    def resolver2(txt):
        return []
    _ = resolver2


def fill_rapport_audit(template_path, out_path, *, numero_dossier, numero_certificat):
    fill_generic(template_path, out_path, [
        ("Numéro de dossier", numero_dossier),
        ("Numéro de certificat", numero_certificat or "—"),
    ])


def fill_plan_audit(template_path, out_path, *, date_etab, responsable, organisme, adresse, site, contact, tel,
                    domaines_sel, types_sel, label_map):
    def resolver(txt, prev=""):
        for t in (txt.strip(), prev.strip()):
            if t.startswith("Date d'établissement") or t.startswith("Date de Mise"):
                return [date_etab]
            if t.startswith("Nom et prénom du responsable"):
                return [responsable]
            if t.startswith("Nom de l'organisme"):
                return [organisme]
            if t.startswith("Adresse du siège"):
                return [adresse]
            if t.startswith("Site concerné"):
                return [site]
            if t.startswith("Contact Client"):
                return [contact]
            if t.startswith("Téléphone"):
                return [tel]
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

    def resolver(txt, prev=""):
        if any(m in txt.upper() for m in LCP_RESERVE) or any(m in prev.upper() for m in LCP_RESERVE):
            return []
        if state["i"] >= len(queue):
            return []
        v = queue[state["i"]]
        state["i"] += 1
        return [v]

    def transform(xml):
        return _fill_placeholders(xml, resolver)

    _rewrite(template_path, out_path, transform)
