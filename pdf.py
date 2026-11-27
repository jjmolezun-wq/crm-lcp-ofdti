import hashlib
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KEY_DIR = os.path.join(BASE_DIR, "data")
PRIV_KEY = os.path.join(KEY_DIR, "lcp_signing_key.pem")
PUB_KEY = os.path.join(KEY_DIR, "lcp_signing_pub.pem")

PAGE_W, PAGE_H = 595, 842


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


def _content_stream(lines):
    parts = []
    for (x, y, size, text, bold) in lines:
        font = "F2" if bold else "F1"
        parts.append(f"BT /{font} {size} Tf {x} {y} Td ({_enc(text)}) Tj ET".encode("latin-1"))
    return b"\n".join(parts)


def build_pdf(pages):
    """pages : liste de listes de (x, y, taille, texte, gras). PDF 1.4 déterministe."""
    objects = []
    n_pages = len(pages)
    kids = " ".join(f"{5 + 2 * i} 0 R" for i in range(n_pages))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    for i, lines in enumerate(pages):
        page_num = 5 + 2 * i
        content_num = 6 + 2 * i
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                       f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_num} 0 R >>".encode())
        stream = _content_stream(lines)
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


def page_certificat(cert, dossier, organisme, mentions):
    lines = []
    x = 60
    lines.append((x, 780, 22, "CERTIFICAT DE CONFORMITE OFDTI", True))
    lines.append((x, 758, 11, "délivré par LCP — Certification OFDTI", False))
    lines.append((x, 700, 13, "Nous certifions que", False))
    lines += [(x, 668, 20, ln, True) for ln in wrap_text(organisme, 20, PAGE_W - 120)]
    y = 620
    lines.append((x, y, 13, "est certifié conforme au référentiel OFDTI pour le service :", False))
    y -= 26
    for ln in wrap_text(dossier["type_service"], 16, PAGE_W - 120):
        lines.append((x, y, 16, ln, True))
        y -= 22
    y -= 20
    lines.append((x, y, 18, f"N° {cert['numero']}", True))
    y -= 40
    for label, val in (("Délivré le", cert["date_delivrance"][:10]),
                       ("Valable jusqu'au", cert["date_expiration"][:10]),
                       ("Statut", cert["statut"]),
                       ("Dossier", dossier["numero"])):
        lines.append((x, y, 12, f"{label} : {val}", False))
        y -= 20
    y -= 30
    for m in mentions:
        for ln in wrap_text(m, 9, PAGE_W - 120):
            lines.append((x, y, 9, ln, False))
            y -= 13
    return lines


def page_signature(cert, pdf_hash, sig_hex, fingerprint, signe_at, base_url):
    lines = []
    x = 60
    lines.append((x, 780, 18, "ATTESTATION DE SIGNATURE ELECTRONIQUE", True))
    lines.append((x, 756, 11, "Document signé numériquement par LCP — Certification OFDTI", False))
    y = 710
    for label, val in (("Certificat", cert["numero"]),
                       ("Empreinte SHA-256 du document signé", pdf_hash),
                       ("Signature RSA-2048 (PSS, SHA-256)", ""),
                       ("Empreinte de la clé publique", fingerprint),
                       ("Signé le", signe_at)):
        lines.append((x, y, 11, f"{label} :", True))
        y -= 16
        if val:
            for ln in wrap_text(val, 9, PAGE_W - 140):
                lines.append((x + 20, y, 9, ln, False))
                y -= 12
        else:
            for i in range(0, len(sig_hex), 96):
                lines.append((x + 20, y, 8, sig_hex[i:i + 96], False))
                y -= 11
        y -= 8
    y -= 10
    lines.append((x, y, 10, f"Vérification : {base_url}/certificats/{cert['id']}/verify", False))
    y -= 16
    lines.append((x, y, 10, "La vérification recalcule l'empreinte du document et contrôle la signature avec la clé publique.", False))
    return lines


def page_rapport_audit(dossier, candidat, lignes):
    lines = [(60, 780, 18, f"RAPPORT D'AUDIT — {dossier['numero']}", True)]
    y = 750
    for label, val in (("Organisme", candidat["organisme"] or candidat["nom"]),
                       ("Service", dossier["type_service"]),
                       ("Statut", dossier["statut"]),
                       ("Décision", dossier["decision"] or "—"),
                       ("Motif", dossier["motif"] or "—")):
        lines.append((60, y, 11, f"{label} : {val}", False))
        y -= 18
    y -= 20
    lines.append((60, y, 14, "Observations et non-conformités", True))
    y -= 24
    if not lignes:
        lines.append((60, y, 11, "Aucune observation enregistrée.", False))
        y -= 16
    for auteur, at, contenu in lignes:
        lines.append((60, y, 11, f"[{at[:16]}] {auteur} :", True))
        y -= 15
        for ln in wrap_text(contenu, 10, PAGE_W - 140):
            lines.append((80, y, 10, ln, False))
            y -= 13
        y -= 8
    return lines


def certificat_pdf_unsigned(cert, dossier, candidat, mentions):
    return build_pdf([page_certificat(cert, dossier, candidat["organisme"] or candidat["nom"], mentions)])


def certificat_pdf_signe(cert, dossier, candidat, mentions, base_url, signe_at):
    priv, pub = get_keys()
    unsigned = certificat_pdf_unsigned(cert, dossier, candidat, mentions)
    pdf_hash, sig_hex = signer_hash(unsigned, priv)
    pages = [page_certificat(cert, dossier, candidat["organisme"] or candidat["nom"], mentions),
             page_signature(cert, pdf_hash, sig_hex, key_fingerprint(pub), signe_at, base_url)]
    return build_pdf(pages), pdf_hash, sig_hex, key_fingerprint(pub)
