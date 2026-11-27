import hashlib
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KEY_DIR = os.path.join(BASE_DIR, "data")
PRIV_KEY = os.path.join(KEY_DIR, "lcp_signing_key.pem")
PUB_KEY = os.path.join(KEY_DIR, "lcp_signing_pub.pem")

PAGE_W, PAGE_H = 595, 842
BRAND = (0xF0 / 255, 0x98 / 255, 0x0C / 255)  # #F0980C — couleur de marque LCP


def get_keys():
    os.makedirs(KEY_DIR, exist_ok=True)
    if not os.path.exists(PRIV_KEY):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with open(PRIV_KEY, "wb") as f:
            f.write(key.private_bytes(serialization.Encoding.PEM,
                                      serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
        with open(PUB_KEY, "wb") as f:
            f.write(key.public_key().public_bytes(serialization.Encoding.PEM,
                                                  serialization.PublicFormat.SubjectPublicKeyInfo))
        os.chmod(PRIV_KEY, 0o600)
    with open(PRIV_KEY, "rb") as f:
        priv = serialization.load_pem_private_key(f.read(), password=None)
    with open(PUB_KEY, "rb") as f:
        pub = serialization.load_pem_public_key(f.read())
    return priv, pub


def key_fingerprint(pub):
    return hashlib.sha256(pub.public_bytes(serialization.Encoding.DER,
                                           serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()[:16]


def signer_hash(unsigned_bytes, priv):
    sig = priv.sign(unsigned_bytes,
                    padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                    hashes.SHA256())
    return hashlib.sha256(unsigned_bytes).hexdigest(), sig.hex()


def verifier_hash(unsigned_bytes, sig_hex, pub):
    try:
        pub.verify(bytes.fromhex(sig_hex), unsigned_bytes,
                   padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                   hashes.SHA256())
        return True
    except Exception:
        return False


def _esc(s):
    return str(s).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _enc(s):
    return _esc(s).encode("cp1252", "replace")


def _col(c):
    return f"{c[0]:.3f} {c[1]:.3f} {c[2]:.3f}"


def _content_stream(page):
    parts = []
    for sh in page.get("shapes", []):
        kind = sh[0]
        if kind == "rect":
            _, x, y, w, h, color, filled = sh
            op = "B" if filled else "S"
            parts.append(f"{_col(color)} {'rg' if filled else 'RG'} {x} {y} {w} {h} re {op}".encode("latin-1"))
        elif kind == "line":
            _, x1, y1, x2, y2, color = sh
            parts.append(f"{_col(color)} RG {x1} {y1} m {x2} {y2} l S".encode("latin-1"))
    for ln in page["lines"]:
        x, y, size, text, bold = ln[:5]
        color = ln[5] if len(ln) > 5 and ln[5] else (0, 0, 0)
        font = "F2" if bold else "F1"
        parts.append(f"{_col(color)} rg BT /{font} {size} Tf {x} {y} Td ({_enc(text)}) Tj ET".encode("latin-1"))
    return b"\n".join(parts)


def build_pdf(pages):
    """pages : liste de dicts {"shapes": [...], "lines": [(x, y, taille, texte, gras[, couleur])]}."""
    objects = []
    n_pages = len(pages)
    kids = " ".join(f"{5 + 2 * i} 0 R" for i in range(n_pages))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    for i, page in enumerate(pages):
        page_num = 5 + 2 * i
        content_num = 6 + 2 * i
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                       f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_num} 0 R >>".encode())
        stream = _content_stream(page)
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n").encode()
    return bytes(out)


def wrap_text(s, size, maxw):
    maxchars = max(10, int(maxw / (size * 0.5)))
    words = str(s).split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if len(t) <= maxchars:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def page_certificat(cert, dossier, candidat, mentions, domaines_sel, types_sel, domaines_all, lieu, signataire):
    shapes = [("rect", 36, 36, PAGE_W - 72, PAGE_H - 72, BRAND, False)]
    lines = [(60, 788, 26, "Certificat OFDTI", True, BRAND)]
    lines.append((60, 766, 13, f"N° {cert['numero']}", True, BRAND))
    y = 728
    lines.append((60, y, 12, "L.C.P Certification atteste que l'organisme de formation :", False, None))
    y -= 20
    siret = candidat["siret"] or ""
    for label, val in (("Nom", candidat["organisme"] or candidat["nom"]),
                       ("Adresse", candidat["adresse"] or "—"),
                       ("N° de SIREN", siret[:9] if siret else "—"),
                       ("N° d'enregistrement de l'organisme de formation", candidat["numero_enregistrement"] or "—")):
        for ln in wrap_text(f"{label} : {val}", 11, PAGE_W - 140):
            lines.append((60, y, 11, ln, False, None))
            y -= 15
    y -= 14
    cols = ["FIP", "FID", "FCP", "FCD", "FPT"]
    x_dom, w_dom = 60, 210
    w_col = 52
    tbl_x = 60
    tbl_w = w_dom + w_col * len(cols)
    row_h = 15
    header = ["Formation / Domaine"] + cols
    rows = []
    for code, lib in domaines_all:
        mark = "X" if code in (domaines_sel or []) else " "
        rows.append((lib, code))
    n_rows = 1 + len(rows)
    tbl_top = y
    tbl_bot = y - n_rows * row_h
    for i in range(n_rows + 1):
        yy = tbl_top - i * row_h
        shapes.append(("line", tbl_x, yy, tbl_x + tbl_w, yy, (0.75, 0.75, 0.75)))
    shapes.append(("line", tbl_x, tbl_top, tbl_x, tbl_bot, (0.75, 0.75, 0.75)))
    shapes.append(("line", tbl_x + tbl_w, tbl_top, tbl_x + tbl_w, tbl_bot, (0.75, 0.75, 0.75)))
    shapes.append(("line", tbl_x + w_dom, tbl_top, tbl_x + w_dom, tbl_bot, (0.75, 0.75, 0.75)))
    for i in range(1, len(cols)):
        xx = tbl_x + w_dom + i * w_col
        shapes.append(("line", xx, tbl_top, xx, tbl_bot, (0.75, 0.75, 0.75)))
    lines.append((tbl_x + 4, tbl_top - 11, 9, header[0], True, BRAND))
    for i, c in enumerate(cols):
        lines.append((tbl_x + w_dom + i * w_col + 14, tbl_top - 11, 9, c, True, BRAND))
    for r, (lib, code) in enumerate(rows, start=1):
        yy = tbl_top - r * row_h - 11
        selected = code in (domaines_sel or [])
        lines.append((tbl_x + 4, yy, 9, lib, selected, None))
        for i, c in enumerate(cols):
            mark = "X" if (selected and c in (types_sel or [])) else " "
            lines.append((tbl_x + w_dom + i * w_col + 20, yy, 9, mark, selected, None))
    y = tbl_bot - 24
    lines.append((60, y, 11, "A été jugé conforme au regard des textes en vigueur (voir mentions ci-dessous).", False, None))
    y -= 8
    for m in mentions:
        for ln in wrap_text(m, 8, PAGE_W - 120):
            y -= 11
            lines.append((60, y, 8, ln, False, (0.35, 0.35, 0.35)))
    y -= 16
    for label, val in (("Émis le", cert["date_delivrance"][:10]),
                       ("Date de prise d'effet", cert["date_delivrance"][:10]),
                       ("Valable jusqu'au", cert["date_expiration"][:10])):
        lines.append((60, y, 11, f"{label} : {val}", False, None))
        y -= 16
    y -= 14
    lines.append((60, y, 10, "Ce certificat est émis pour servir et valoir ce que de droit.", False, None))
    y -= 14
    lines.append((60, y, 10, f"Édité le {cert['date_delivrance'][:10]}, à {lieu}.", False, None))
    y -= 14
    lines.append((60, y, 10, f"Par {signataire}", True, None))
    return {"shapes": shapes, "lines": lines}


def page_signature(cert, pdf_hash, sig_hex, fingerprint, signe_at, base_url):
    lines = [(60, 780, 18, "ATTESTATION DE SIGNATURE ELECTRONIQUE", True, BRAND)]
    lines.append((60, 756, 11, "Document signé numériquement par LCP — Certification OFDTI", False, None))
    y = 710
    for label, val in (("Certificat", cert["numero"]),
                       ("Empreinte SHA-256 du document signé", pdf_hash),
                       ("Signature RSA-2048 (PSS, SHA-256)", ""),
                       ("Empreinte de la clé publique", fingerprint),
                       ("Signé le", signe_at)):
        lines.append((60, y, 11, f"{label} :", True, None))
        y -= 16
        if val:
            for ln in wrap_text(val, 9, PAGE_W - 140):
                lines.append((80, y, 9, ln, False, None))
                y -= 12
        else:
            for i in range(0, len(sig_hex), 96):
                lines.append((80, y, 8, sig_hex[i:i + 96], False, None))
                y -= 11
        y -= 8
    y -= 10
    lines.append((60, y, 10, f"Vérification : {base_url}/certificats/{cert['id']}/verify", False, None))
    y -= 16
    lines.append((60, y, 10, "La vérification recalcule l'empreinte du document et contrôle la signature avec la clé publique.", False, None))
    return {"shapes": [], "lines": lines}


def page_rapport_audit(dossier, candidat, lignes):
    lines = [(60, 780, 18, f"RAPPORT D'AUDIT — {dossier['numero']}", True, BRAND)]
    y = 750
    for label, val in (("Organisme", candidat["organisme"] or candidat["nom"]),
                       ("Service", dossier["type_service"]),
                       ("Statut", dossier["statut"]),
                       ("Décision", dossier["decision"] or "—"),
                       ("Motif", dossier["motif"] or "—")):
        lines.append((60, y, 11, f"{label} : {val}", False, None))
        y -= 18
    y -= 20
    lines.append((60, y, 14, "Observations et non-conformités", True, None))
    y -= 24
    if not lignes:
        lines.append((60, y, 11, "Aucune observation enregistrée.", False, None))
        y -= 16
    for auteur, at, contenu in lignes:
        lines.append((60, y, 11, f"[{at[:16]}] {auteur} :", True, None))
        y -= 15
        for ln in wrap_text(contenu, 10, PAGE_W - 140):
            lines.append((80, y, 10, ln, False, None))
            y -= 13
        y -= 8
    return {"shapes": [], "lines": lines}


def certificat_pdf_unsigned(cert, dossier, candidat, mentions, domaines_sel, types_sel, domaines_all, lieu, signataire):
    return build_pdf([page_certificat(cert, dossier, candidat, mentions, domaines_sel, types_sel, domaines_all, lieu, signataire)])


def certificat_pdf_signe(cert, dossier, candidat, mentions, domaines_sel, types_sel, domaines_all, lieu, signataire, base_url, signe_at):
    priv, pub = get_keys()
    unsigned = certificat_pdf_unsigned(cert, dossier, candidat, mentions, domaines_sel, types_sel, domaines_all, lieu, signataire)
    pdf_hash, sig_hex = signer_hash(unsigned, priv)
    pages = [
        page_certificat(cert, dossier, candidat, mentions, domaines_sel, types_sel, domaines_all, lieu, signataire),
        page_signature(cert, pdf_hash, sig_hex, key_fingerprint(pub), signe_at, base_url),
    ]
    return build_pdf(pages), pdf_hash, sig_hex, key_fingerprint(pub)
