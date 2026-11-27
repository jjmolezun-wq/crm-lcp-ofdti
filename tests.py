import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import http.cookiejar

BASE = "http://127.0.0.1:8765"
DB = "/tmp/test_crm_lcp.db"

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + detail if detail and not ok else ""))


def make_opener():
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def get(op, path):
    return op.open(BASE + path, timeout=10)


def post(op, path, data):
    return op.open(BASE + path, urllib.parse.urlencode(data).encode(), timeout=10)


def post_multi(op, path, pairs):
    return op.open(BASE + path, urllib.parse.urlencode(pairs).encode(), timeout=10)


def post_multipart(op, path, fields, filename, content):
    boundary = "----vibetestboundary"
    parts = []
    for k, v in fields:
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"fichier\"; filename=\"{filename}\"\r\nContent-Type: application/pdf\r\n\r\n".encode() + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(BASE + path, data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    return op.open(req, timeout=10)


def csrf_of(html_text):
    m = re.search(r'name="csrf" value="([^"]+)"', html_text)
    return m.group(1) if m else ""


def login(op, email, password):
    r = post(op, "/login", {"email": email, "password": password})
    return r.read().decode("utf-8")


def main():
    if os.path.exists(DB):
        os.remove(DB)
    env = dict(os.environ, PORT="8765", CRM_LCP_DB=DB, PYTHONPATH="/workspace/lcp-crm")
    proc = subprocess.Popen([sys.executable, "/workspace/lcp-crm/app.py", "--reset"], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(BASE + "/health", timeout=1).read()
                break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError("serveur non démarré")

        cand = make_opener()
        page = login(cand, "candidat@exemple.fr", "demo123")
        check("login candidat", "Tableau de bord" in page)
        csrf = csrf_of(get(cand, "/dossiers/nouveau").read().decode("utf-8"))
        check("csrf présent", bool(csrf))

        r = post_multi(cand, "/dossiers", [("csrf", csrf), ("domaines", "dpe_sans"), ("domaines", "gaz"),
                                            ("types_formation", "FIP"), ("types_formation", "FCP"),
                                            ("description", "Dossier de test automatisé OFDTI.")])
        body = r.read().decode("utf-8")
        m = re.search(r"DOS-\d{4}-\d{4}", body)
        check("création dossier", bool(m), body[:200])
        numero = m.group(0) if m else ""
        mid = re.search(r'/dossiers/(\d+)/statut', body)
        did = mid.group(1) if mid else ""
        check("dossier visible en détail", did != "")

        page = get(cand, f"/dossiers/{did}").read().decode("utf-8")
        csrf = csrf_of(page)
        post(cand, f"/dossiers/{did}/statut", {"csrf": csrf, "statut": "depose", "commentaire": "Dépôt initial"})
        page = get(cand, f"/dossiers/{did}").read().decode("utf-8")
        check("statut déposé", "posée" in page.lower())
        check("portée affichée (domaines)", "DPE sans mention" in page and "Gaz" in page)

        bad = make_opener()
        login(bad, "candidat@exemple.fr", "demo123")
        try:
            post(bad, f"/dossiers/{did}/statut", {"csrf": "faux", "statut": "certifie", "commentaire": "x"})
            check("CSRF rejeté", False, "pas d'erreur 403")
        except urllib.error.HTTPError as e:
            check("CSRF rejeté", e.code == 403, str(e.code))

        admin = make_opener()
        page = login(admin, "admin@lcp.fr", "admin123")
        csrf = csrf_of(get(admin, "/admin/users").read().decode("utf-8"))
        page = get(admin, f"/dossiers/{did}").read().decode("utf-8")
        post(admin, f"/dossiers/{did}/statut", {"csrf": csrf, "statut": "en_recevabilite", "commentaire": "revue"})
        r = post(admin, f"/dossiers/{did}/statut", {"csrf": csrf, "statut": "recevable", "commentaire": "test sans demande signée"})
        page = r.read().decode("utf-8")
        check("recevabilité bloquée sans demande signée retournée", "signée" in page)
        csrf_cand = csrf_of(get(cand, f"/dossiers/{did}").read().decode("utf-8"))
        post_multipart(cand, f"/dossiers/{did}/pieces", [("csrf", csrf_cand), ("categorie", "demande_signee")], "demande_signee.pdf", b"%PDF-1.4 signe")
        post(admin, f"/dossiers/{did}/statut", {"csrf": csrf, "statut": "recevable", "commentaire": "demande signée reçue"})
        for statut in ("en_audit", "certifie"):
            post(admin, f"/dossiers/{did}/statut", {"csrf": csrf, "statut": statut, "commentaire": f"vers {statut}"})
        page = get(admin, f"/dossiers/{did}").read().decode("utf-8")
        check("demande signée reçue affichée", "reçu" in page)
        page = get(admin, f"/dossiers/{did}").read().decode("utf-8")
        check("dossier certifié", "Certifié OFDTI" in page)
        check("certificat créé sur le dossier", "OFDTI-" in page)
        check("facture créée sur le dossier", "FAC-" in page)

        certs = get(admin, "/certificats").read().decode("utf-8")
        check("registre certificats contient OFDTI", "OFDTI-" in certs and numero in certs)
        facs = get(admin, "/factures").read().decode("utf-8")
        check("liste factures", "FAC-" in facs)

        mpdf = re.search(r"/certificats/(\d+)/pdf", page)
        if mpdf:
            cid = mpdf.group(1)
            r = get(admin, f"/certificats/{cid}/pdf")
            pdfb = r.read()
            check("PDF signé généré", r.status == 200 and pdfb.startswith(b"%PDF") and "pdf" in (r.headers.get("Content-Type") or ""))
            check("PDF conforme au modèle OFDTI (titre, domaines, types)",
                  b"Certificat OFDTI" in pdfb and b"DPE sans mention" in pdfb and b"FIP" in pdfb and b"Pessac" in pdfb)
            rdoc = get(admin, f"/certificats/{cid}/document")
            docb = rdoc.read()
            import zipfile as zf, io as _io
            zx = zf.ZipFile(_io.BytesIO(docb))
            docxml = zx.read("word/document.xml").decode("utf-8")
            check("certificat Word = modèle officiel V007 rempli", "OFDTI-" in docxml and "Société Exemple" in docxml)
            check("cases cochées ☒ = portée sélectionnée (2 domaines × 2 types = 4)", docxml.count("\u2612") == 4, str(docxml.count("\u2612")))
            ver = get(admin, f"/certificats/{cid}/verify").read().decode("utf-8")
            check("vérification signature RSA valide", "signature valide" in ver)
            pub = get(admin, "/api/pubkey").read().decode("utf-8")
            check("clé publique servie", "BEGIN PUBLIC KEY" in pub)
        else:
            check("PDF signé généré", False, "lien pdf introuvable")

        stats = get(admin, "/stats").read().decode("utf-8")
        check("page statistiques avec graphiques SVG", "<svg" in stats and "Statistiques" in stats)
        dos = get(admin, "/dossiers").read().decode("utf-8")
        check("dossier de renouvellement auto créé", "Renouvellement" in dos)
        outbox2 = get(admin, "/admin/outbox").read().decode("utf-8")
        check("outbox: e-mails simulés sans SMTP", "simulé" in outbox2)
        docs = get(admin, "/documents").read().decode("utf-8")
        check("page documents de référence (procédure V016, modèle certificat, demande V0010)",
              "Procedure_certification_OFDTI_V016.docx" in docs and "Modele_certificat_OFDTI_V007.docx" in docs
              and "Element_technique_demande_certification_V0010.docx" in docs)
        rdem = get(cand, f"/dossiers/{did}/demande-document")
        demb = rdem.read()
        import zipfile as zf2, io as _io2
        zx2 = zf2.ZipFile(_io2.BytesIO(demb))
        demxml = zx2.read("word/document.xml").decode("utf-8")
        check("demande Word V0010 pré-remplie (identité OF)", "Société Exemple" in demxml and "OFDTI" in demxml)
        post(cand, "/profil", {"csrf": csrf_cand, "organisme": "Société Exemple SARL", "siret": "12345678900012",
                               "numero_enregistrement": "11-33-000000-01", "adresse": "10 avenue des Services, 69001 Lyon",
                               "code_ape": "8559A", "dirigeant": "Jean Dupont"})
        prof = get(cand, "/profil").read().decode("utf-8")
        check("profil OF enregistré (code APE 8559A)", "8559A" in prof)

        mcert = re.search(r"/certificats/(\d+)/print", get(cand, "/certificats").read().decode("utf-8"))
        if mcert:
            cert_page = get(cand, f"/certificats/{mcert.group(1)}/print").read().decode("utf-8")
            check("page certificat imprimable", "CERTIFICAT DE CONFORMITÉ OFDTI" in cert_page and "Société Exemple" in cert_page)
        else:
            check("page certificat imprimable", False, "aucun certificat trouvé pour le candidat")

        post(admin, "/admin/automations/run", {"csrf": csrf})
        outbox = get(admin, "/admin/outbox").read().decode("utf-8")
        check("automatisation relance facture en retard (e-mail simulé)", "retard" in outbox.lower())
        notifs = get(admin, "/notifications").read().decode("utf-8")
        check("notifications présentes", len(notifs) > 0)

        csv_cert = get(admin, "/exports/certifies.csv").read().decode("utf-8")
        check("export CSV registre certifiés", "OFDTI-" in csv_cert and "certificat" in csv_cert.splitlines()[0])
        csv_dos = get(admin, "/exports/dossiers.csv").read().decode("utf-8")
        check("export CSV dossiers", numero in csv_dos)

        try:
            get(cand, "/admin/users")
            check("candidat bloqué sur /admin", False)
        except urllib.error.HTTPError as e:
            check("candidat bloqué sur /admin", e.code == 403, str(e.code))

        aud = make_opener()
        page = login(aud, "auditeur@lcp.fr", "audit123")
        check("login auditeur", "Tableau de bord" in page)
        try:
            get(aud, "/admin/parametres")
            check("auditeur bloqué sur params admin", False)
        except urllib.error.HTTPError as e:
            check("auditeur bloqué sur params admin", e.code == 403, str(e.code))

        page = get(cand, "/dossiers").read().decode("utf-8")
        check("liste dossiers candidat", numero in page)

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} tests réussis")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
