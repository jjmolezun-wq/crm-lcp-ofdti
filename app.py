import csv
import io
import json
import os
import re
import secrets
import sys
from datetime import timedelta
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import automations
import charts
import db
import pdf as pdfgen
import templates as t
from workflow import STATUTS, peut_voir_dossier, transitions_possibles

SESSION_COOKIE = "lcp_session"
BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")


DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "documents")


def charger_mentions():
    p = os.path.join(DOCS_DIR, "certificat_mentions.txt")
    if os.path.exists(p):
        with open(p) as f:
            return [l.strip() for l in f if l.strip()]
    return [
        "Certificat délivré conformément au référentiel OFDTI en vigueur.",
        "Toute modification du périmètre certifié invalide le présent certificat.",
        "Vérification de l'authenticité en ligne disponible depuis le CRM LCP.",
    ]


def contexte_certificat(ctx, cert):
    d = get_dossier(ctx, cert["dossier_id"])
    candidat = ctx.conn.execute("SELECT * FROM users WHERE id = ?", (d["candidat_id"],)).fetchone()
    domaines_sel = json.loads(d["domaines"]) if d["domaines"] else []
    types_sel = json.loads(d["types_formation"]) if d["types_formation"] else []
    domaines_all = [(r["code"], r["libelle"]) for r in ctx.conn.execute("SELECT code, libelle FROM domaines ORDER BY rowid").fetchall()]
    lieu = db.get_param(ctx.conn, "lieu_edition_certificat", "Pessac")
    signataire = db.get_param(ctx.conn, "signataire_certificat", "Responsable de certification")
    return d, candidat, domaines_sel, types_sel, domaines_all, lieu, signataire


def portee_dossier(ctx, d):
    labels = {r["code"]: r["libelle"] for r in ctx.conn.execute("SELECT code, libelle FROM domaines").fetchall()}
    try:
        doms = json.loads(d["domaines"]) if d["domaines"] else []
    except Exception:
        doms = []
    try:
        types = json.loads(d["types_formation"]) if d["types_formation"] else []
    except Exception:
        types = []
    txt = ", ".join(labels.get(c, c) for c in doms)
    if types:
        txt = (txt + "  ·  " if txt else "") + ", ".join(types)
    return txt
SESSION_DUREE = timedelta(hours=8)
TAILLE_MAX_PIECE = 10 * 1024 * 1024

ROUTES = []


def route(method, pattern, roles=None, csrf=True):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn, roles, csrf))
        return fn
    return deco


class Redirect(Exception):
    def __init__(self, location):
        self.location = location


def parse_multipart(content_type, body):
    msg = BytesParser(policy=email_policy).parsebytes(
        b"Content-Type: " + content_type.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
    )
    fields, files = {}, {}
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename:
            files[name] = (filename, part.get_content_type(), payload)
        else:
            fields[name] = payload.decode("utf-8", "replace")
    return fields, files


class Ctx:
    def __init__(self, handler, method, path, query, body):
        self.handler = handler
        self.method = method
        self.path = path
        self.query = query
        self.conn = db.connect()
        self.cookies = {}
        raw = handler.headers.get("Cookie", "")
        for chunk in raw.split(";"):
            if "=" in chunk:
                k, v = chunk.strip().split("=", 1)
                self.cookies[k] = v
        self.user = None
        self.session = None
        token = self.cookies.get(SESSION_COOKIE)
        if token:
            row = self.conn.execute(
                "SELECT s.token AS stoken, s.csrf AS scsrf, u.* FROM sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token = ? AND s.expires_at > ?",
                (token, db.now()),
            ).fetchone()
            if row and row["actif"]:
                self.session = row
                self.user = row
        self.csrf = self.session["scsrf"] if self.session else ""
        self.form = {}
        self.form_list = {}
        self.files = {}
        if method == "POST":
            ct = handler.headers.get("Content-Type", "")
            if ct.startswith("multipart/form-data"):
                self.form, self.files = parse_multipart(ct, body)
                self.form_list = {}
                for k, v in self.form.items():
                    self.form_list[k] = [v]
            else:
                self.form_list = parse_qs(body.decode("utf-8", "replace"))
                self.form = {k: v[0] for k, v in self.form_list.items()}

    def unread(self):
        if not self.user:
            return 0
        return self.conn.execute(
            "SELECT COUNT(*) AS c FROM notifications WHERE user_id = ? AND lu = 0", (self.user["id"],)
        ).fetchone()["c"]

    def users_map(self):
        return {u["id"]: dict(u) for u in self.conn.execute("SELECT * FROM users").fetchall()}


def respond(ctx, body, status=200, ctype="text/html; charset=utf-8", headers=None):
    data = body.encode("utf-8") if isinstance(body, str) else body
    h = ctx.handler
    h.send_response(status)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(data)))
    for k, v in (headers or {}).items():
        h.send_header(k, v)
    h.end_headers()
    h.wfile.write(data)


def redirect(ctx, location, headers=None):
    respond(ctx, "", status=303, headers={"Location": location, **(headers or {})})


def page(ctx, title, body):
    return t.layout(ctx.user, title, body, unread=ctx.unread())


def get_dossier(ctx, did):
    return ctx.conn.execute("SELECT * FROM dossiers WHERE id = ?", (did,)).fetchone()


def verifier_acces_dossier(ctx, dossier):
    return peut_voir_dossier(ctx.user, dossier)


def creer_certificat_et_facture(ctx, dossier):
    duree_mois = int(db.get_param(ctx.conn, "duree_certification_mois", "36"))
    montant = float(db.get_param(ctx.conn, "montant_frais_euros", "1500.00"))
    delai_j = int(db.get_param(ctx.conn, "delai_paiement_jours", "30"))
    now = db.utcnow()
    num_cert = db.next_numero(ctx.conn, "OFDTI", "certificats", "numero")
    ctx.conn.execute(
        "INSERT INTO certificats(dossier_id, numero, date_delivrance, date_expiration, statut, created_at) VALUES (?,?,?,?,?,?)",
        (dossier["id"], num_cert, db.iso(now), db.iso(now + timedelta(days=duree_mois * 30)), "valide", db.now()),
    )
    num_fac = db.next_numero(ctx.conn, "FAC", "factures", "numero")
    ctx.conn.execute(
        "INSERT INTO factures(dossier_id, numero, montant, statut, emise_at, echeance) VALUES (?,?,?,?,?,?)",
        (dossier["id"], num_fac, montant, "emise", db.iso(now), db.iso(now + timedelta(days=delai_j))),
    )
    candidat = ctx.conn.execute("SELECT * FROM users WHERE id = ?", (dossier["candidat_id"],)).fetchone()
    organisme = candidat["organisme"] or candidat["nom"]
    db.notify(ctx.conn, candidat["id"], "certification",
              f"Certification OFDTI délivrée — {num_cert}",
              f"Votre dossier {dossier['numero']} est certifié OFDTI. Certificat {num_cert}, valable jusqu'au {db.iso(now + timedelta(days=duree_mois * 30))[:10]}. Une facture {num_fac} de {montant:.2f} € vous a été émise.",
              lien=f"/dossiers/{dossier['id']}", cle=f"certif:{dossier['id']}")
    db.send_email(ctx.conn, candidat["email"],
                  f"[LCP] Votre certification OFDTI {num_cert} est délivrée",
                  f"Bonjour,\n\n{organisme} est certifié conforme au référentiel OFDTI pour « {dossier['type_service']} ».\n"
                  f"Certificat : {num_cert}\nValable jusqu'au : {db.iso(now + timedelta(days=duree_mois * 30))[:10]}\n"
                  f"Facture : {num_fac} — {montant:.2f} €\n\nLCP — Certification OFDTI",
                  dossier_id=dossier["id"])
    return num_cert, num_fac


@route("GET", r"/login", roles=None, csrf=False)
def login_get(ctx):
    if ctx.user:
        redirect(ctx, "/")
        return
    return t.page_login()


@route("POST", r"/login", roles=None, csrf=False)
def login_post(ctx):
    email = ctx.form.get("email", "").strip().lower()
    password = ctx.form.get("password", "")
    user = ctx.conn.execute("SELECT * FROM users WHERE email = ? AND actif = 1", (email,)).fetchone()
    if not user or not db.verify_password(password, user["password_hash"]):
        return t.page_login("Identifiants invalides.")
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(16)
    ctx.conn.execute(
        "INSERT INTO sessions(token, user_id, csrf, created_at, expires_at) VALUES (?,?,?,?,?)",
        (token, user["id"], csrf, db.now(), db.iso(db.utcnow() + SESSION_DUREE)),
    )
    ctx.conn.execute("DELETE FROM sessions WHERE expires_at < ?", (db.now(),))
    ctx.conn.commit()
    db.audit(ctx.conn, user["id"], "login", "session", None, email)
    ctx.conn.commit()
    redirect(ctx, ctx.query.get("next", ["/"])[0] or "/",
             headers={"Set-Cookie": f"{SESSION_COOKIE}={token}; HttpOnly; Path=/; SameSite=Lax"})


@route("GET", r"/logout", roles=None, csrf=False)
def logout(ctx):
    token = ctx.cookies.get(SESSION_COOKIE)
    if token:
        ctx.conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        ctx.conn.commit()
    redirect(ctx, "/login", headers={"Set-Cookie": f"{SESSION_COOKIE}=; HttpOnly; Path=/; Max-Age=0"})


@route("GET", r"/")
def dashboard(ctx):
    c = ctx.conn
    u = ctx.user
    if u["role"] == "candidat":
        mes_dossiers = c.execute(
            "SELECT * FROM dossiers WHERE candidat_id = ? ORDER BY updated_at DESC LIMIT 8", (u["id"],)
        ).fetchall()
        mes_factures = c.execute(
            "SELECT f.*, d.numero AS dossier_numero FROM factures f JOIN dossiers d ON d.id = f.dossier_id "
            "WHERE d.candidat_id = ? AND f.statut != 'payee' ORDER BY f.echeance", (u["id"],)
        ).fetchall()
        mes_certs = c.execute(
            "SELECT cert.*, d.numero AS dossier_numero FROM certificats cert JOIN dossiers d ON d.id = cert.dossier_id "
            "WHERE d.candidat_id = ? AND cert.statut = 'valide' ORDER BY cert.date_expiration", (u["id"],)
        ).fetchall()
        alertes = []
        for f in mes_factures:
            if f["statut"] == "en_retard":
                alertes.append(f"Facture {f['numero']} en retard ({f['montant']:.2f} €, échéance {f['echeance'][:10]}).")
        for cert in mes_certs:
            jr = t.jours_restants(cert["date_expiration"])
            if jr is not None and jr <= 30:
                alertes.append(f"Certificat {cert['numero']} expire dans {jr} jour(s) ({cert['date_expiration'][:10]}).")
        stats = [
            (len(mes_dossiers), "mes dossiers"),
            (sum(1 for d in mes_dossiers if d["statut"] == "certifie"), "certifiés OFDTI"),
            (len(mes_factures), "factures impayées"),
            (sum(1 for cert in mes_certs if (t.jours_restants(cert["date_expiration"]) or 999) <= 90), "expirations < 90 j"),
        ]
        recents = []
        dossiers_recents = []
        return t.page_dashboard(u, stats, dossiers_recents, alertes, mes_dossiers, mes_factures, mes_certs)
    stats_rows = c.execute("SELECT statut, COUNT(*) AS c FROM dossiers GROUP BY statut").fetchall()
    en_retard = c.execute("SELECT COUNT(*) AS c FROM factures WHERE statut = 'en_retard'").fetchone()["c"]
    exp = c.execute("SELECT COUNT(*) AS c FROM certificats WHERE statut = 'valide' AND date_expiration < ?",
                    (db.iso(db.utcnow() + timedelta(days=90)),)).fetchone()["c"]
    en_cours = sum(r["c"] for r in stats_rows if r["statut"] in ("depose", "en_instruction", "en_audit", "non_conforme"))
    stats = [
        (en_cours, "dossiers en cours"),
        (sum(r["c"] for r in stats_rows if r["statut"] == "certifie"), "certifiés OFDTI"),
        (en_retard, "factures en retard"),
        (exp, "expirations < 90 j"),
    ]
    dossiers_recents = c.execute(
        "SELECT d.*, u.nom, u.organisme FROM dossiers d JOIN users u ON u.id = d.candidat_id ORDER BY d.updated_at DESC LIMIT 8"
    ).fetchall()
    alertes = []
    for f in c.execute(
        "SELECT f.numero, f.montant, f.echeance, u.organisme, u.nom FROM factures f JOIN dossiers d ON d.id = f.dossier_id "
        "JOIN users u ON u.id = d.candidat_id WHERE f.statut = 'en_retard' ORDER BY f.echeance LIMIT 5"
    ).fetchall():
        alertes.append(f"Facture {f['numero']} en retard — {f['organisme'] or f['nom']} ({f['montant']:.2f} €, échéance {f['echeance'][:10]}).")
    for cert in c.execute(
        "SELECT cert.numero, cert.date_expiration, u.organisme, u.nom FROM certificats cert JOIN dossiers d ON d.id = cert.dossier_id "
        "JOIN users u ON u.id = d.candidat_id WHERE cert.statut = 'valide' AND cert.date_expiration < ? ORDER BY cert.date_expiration LIMIT 5",
        (db.iso(db.utcnow() + timedelta(days=30)),),
    ).fetchall():
        jr = t.jours_restants(cert["date_expiration"])
        alertes.append(f"Certificat {cert['numero']} expire dans {jr} j — {cert['organisme'] or cert['nom']}.")
    return t.page_dashboard(u, stats, dossiers_recents, alertes)


@route("GET", r"/dossiers")
def dossiers_liste(ctx):
    filtre = ctx.query.get("statut", [""])[0]
    q = ctx.query.get("q", [""])[0].strip()
    sql = "SELECT d.*, u.nom, u.organisme FROM dossiers d JOIN users u ON u.id = d.candidat_id WHERE 1=1"
    params = []
    if ctx.user["role"] == "candidat":
        sql += " AND d.candidat_id = ?"
        params.append(ctx.user["id"])
    if filtre in STATUTS:
        sql += " AND d.statut = ?"
        params.append(filtre)
    if q:
        sql += " AND (d.numero LIKE ? OR u.organisme LIKE ? OR u.nom LIKE ?)"
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    sql += " ORDER BY d.updated_at DESC"
    dossiers = ctx.conn.execute(sql, params).fetchall()
    return t.page_dossiers(ctx.user, dossiers, filtre, q)


@route("GET", r"/dossiers/nouveau", roles=["candidat"])
def dossier_new_get(ctx):
    domaines = [(r["code"], r["libelle"]) for r in ctx.conn.execute("SELECT code, libelle FROM domaines ORDER BY rowid").fetchall()]
    return t.page_dossier_new(ctx.user, ctx.csrf, domaines, db.TYPES_FORMATION)


@route("POST", r"/dossiers", roles=["candidat"])
def dossier_new_post(ctx):
    domaines = [(r["code"], r["libelle"]) for r in ctx.conn.execute("SELECT code, libelle FROM domaines ORDER BY rowid").fetchall()]
    codes_ok = {c for c, _ in domaines}
    domaines_sel = [c for c in ctx.form_list.get("domaines", []) if c in codes_ok]
    types_sel = [c for c in ctx.form_list.get("types_formation", []) if c in db.TYPES_FORMATION]
    description = ctx.form.get("description", "").strip()
    if not domaines_sel or not description:
        return t.page_dossier_new(ctx.user, ctx.csrf, domaines, db.TYPES_FORMATION,
                                  "Sélectionnez au moins un domaine de certification et décrivez la demande.")
    labels = dict(domaines)
    type_service = ", ".join(labels.get(c, c) for c in domaines_sel[:3]) + ("…" if len(domaines_sel) > 3 else "")
    numero = db.next_numero(ctx.conn, "DOS", "dossiers", "numero")
    now = db.now()
    cur = ctx.conn.execute(
        "INSERT INTO dossiers(numero, candidat_id, type_service, description, statut, domaines, types_formation, created_at, updated_at) VALUES (?,?,?,?, 'brouillon', ?,?, ?, ?)",
        (numero, ctx.user["id"], type_service, description, json.dumps(domaines_sel), json.dumps(types_sel), now, now),
    )
    did = cur.lastrowid
    ctx.conn.execute(
        "INSERT INTO historique(dossier_id, ancien, nouveau, acteur_id, commentaire, at) VALUES (?,?,?,?,?,?)",
        (did, None, "brouillon", ctx.user["id"], "Création du dossier", now),
    )
    db.audit(ctx.conn, ctx.user["id"], "dossier_cree", "dossier", did, numero)
    db.notify_role(ctx.conn, "admin", "dossier_cree", f"Nouveau brouillon {numero}",
                   f"{ctx.user['organisme'] or ctx.user['nom']} a créé le brouillon {numero} ({type_service}).",
                   lien=f"/dossiers/{did}", cle=f"new:{did}")
    ctx.conn.commit()
    redirect(ctx, f"/dossiers/{did}?msg=Dossier {numero} créé.")


@route("GET", r"/dossiers/(\d+)")
def dossier_detail(ctx, did):
    d = get_dossier(ctx, int(did))
    if not d or not verifier_acces_dossier(ctx, d):
        return t.page_erreur(ctx.user, "Dossier introuvable ou accès refusé.", "Accès refusé"), 403
    hist = ctx.conn.execute(
        "SELECT * FROM historique WHERE dossier_id = ? ORDER BY at, id", (d["id"],)
    ).fetchall()
    pieces = ctx.conn.execute(
        "SELECT id, dossier_id, nom, taille, uploader_id, at FROM pieces WHERE dossier_id = ? ORDER BY at DESC", (d["id"],)
    ).fetchall()
    if ctx.user["role"] == "candidat":
        commentaires = ctx.conn.execute(
            "SELECT * FROM commentaires WHERE dossier_id = ? AND interne = 0 ORDER BY at, id", (d["id"],)
        ).fetchall()
    else:
        commentaires = ctx.conn.execute(
            "SELECT * FROM commentaires WHERE dossier_id = ? ORDER BY at, id", (d["id"],)
        ).fetchall()
    cert = ctx.conn.execute("SELECT * FROM certificats WHERE dossier_id = ?", (d["id"],)).fetchone()
    facture = ctx.conn.execute("SELECT * FROM factures WHERE dossier_id = ?", (d["id"],)).fetchone()
    users = ctx.users_map()
    d = dict(d)
    d["organisme"] = users.get(d["candidat_id"], {}).get("organisme", "")
    trans = transitions_possibles(ctx.user, d)
    msg = ctx.query.get("msg", [""])[0]
    erreur = ctx.query.get("erreur", [""])[0]
    return t.page_dossier_detail(ctx.user, d, hist, pieces, commentaires, users, cert, facture, trans, ctx.csrf, msg=msg, erreur=erreur, portee=portee_dossier(ctx, d))


@route("POST", r"/dossiers/(\d+)/statut", roles=["admin", "auditeur", "candidat"])
def dossier_statut(ctx, did):
    d = get_dossier(ctx, int(did))
    if not d or not verifier_acces_dossier(ctx, d):
        return t.page_erreur(ctx.user, "Accès refusé.", "Accès refusé"), 403
    cible = ctx.form.get("statut", "")
    commentaire = ctx.form.get("commentaire", "").strip()
    dispo = transitions_possibles(ctx.user, d)
    if cible not in dispo:
        redirect(ctx, f"/dossiers/{d['id']}?erreur=Transition non autorisée ({t.esc(d['statut'])} → {t.esc(cible)}).")
        return
    if cible == "refuse" and not commentaire:
        redirect(ctx, f"/dossiers/{d['id']}?erreur=Un motif de refus est obligatoire.")
        return
    now = db.now()
    updates = {"statut": cible, "updated_at": now}
    if cible == "depose":
        updates["depose_at"] = now
    if cible in ("certifie", "refuse"):
        updates["decision"] = "certification OFDTI accordée" if cible == "certifie" else "certification OFDTI refusée"
        updates["decision_at"] = now
        updates["decideur_id"] = ctx.user["id"]
        updates["motif"] = commentaire if cible == "refuse" else None
    sets = ", ".join(f"{k} = ?" for k in updates)
    ctx.conn.execute(f"UPDATE dossiers SET {sets} WHERE id = ?", (*updates.values(), d["id"]))
    ctx.conn.execute(
        "INSERT INTO historique(dossier_id, ancien, nouveau, acteur_id, commentaire, at) VALUES (?,?,?,?,?,?)",
        (d["id"], d["statut"], cible, ctx.user["id"], commentaire or None, now),
    )
    db.audit(ctx.conn, ctx.user["id"], f"statut:{d['statut']}->{cible}", "dossier", d["id"], d["numero"])
    candidat = ctx.conn.execute("SELECT * FROM users WHERE id = ?", (d["candidat_id"],)).fetchone()
    if cible == "depose":
        db.notify_role(ctx.conn, "admin", "dossier_depose", f"Dossier {d['numero']} déposé",
                       f"{candidat['organisme'] or candidat['nom']} a déposé le dossier {d['numero']} ({d['type_service']}).",
                       lien=f"/dossiers/{d['id']}", cle=f"depose:{d['id']}")
        db.notify_role(ctx.conn, "auditeur", "dossier_depose", f"Dossier {d['numero']} déposé",
                       f"{candidat['organisme'] or candidat['nom']} a déposé le dossier {d['numero']} ({d['type_service']}).",
                       lien=f"/dossiers/{d['id']}", cle=f"depose:{d['id']}")
        db.notify(ctx.conn, candidat["id"], "dossier_depose", f"Dossier {d['numero']} déposé",
                  f"Votre dossier {d['numero']} a bien été déposé et entre en instruction.",
                  lien=f"/dossiers/{d['id']}", cle=f"depose_own:{d['id']}")
        db.send_email(ctx.conn, candidat["email"], f"[LCP] Accusé de réception — dossier {d['numero']}",
                      f"Bonjour,\n\nVotre dossier {d['numero']} ({d['type_service']}) a bien été déposé le {now[:10]}. Il entre en instruction.\n\nLCP — Certification OFDTI",
                      dossier_id=d["id"])
    elif cible == "certifie":
        num_cert, num_fac = creer_certificat_et_facture(ctx, d)
        db.notify_role(ctx.conn, "admin", "certification", f"Certificat OFDTI {num_cert} délivré",
                       f"Dossier {d['numero']} certifié — certificat {num_cert}, facture {num_fac}.",
                       lien=f"/dossiers/{d['id']}", cle=f"cert_admin:{d['id']}")
        db.audit(ctx.conn, ctx.user["id"], "certificat_delivre", "certificat", None, num_cert)
    elif cible == "refuse":
        db.notify(ctx.conn, candidat["id"], "refus", f"Dossier {d['numero']} refusé",
                  f"Votre demande de certification OFDTI pour le dossier {d['numero']} a été refusée. Motif : {commentaire}",
                  lien=f"/dossiers/{d['id']}", cle=f"refus:{d['id']}")
        db.send_email(ctx.conn, candidat["email"], f"[LCP] Décision — dossier {d['numero']} refusé",
                      f"Bonjour,\n\nVotre dossier {d['numero']} a été refusé.\nMotif : {commentaire}\n\nLCP — Certification OFDTI",
                      dossier_id=d["id"])
    elif cible in ("suspendu", "retire"):
        ctx.conn.execute("UPDATE certificats SET statut = ? WHERE dossier_id = ?", (cible, d["id"]))
        db.notify(ctx.conn, candidat["id"], "cert_statut", f"Certificat {cible}",
                  f"Le statut de votre certification pour le dossier {d['numero']} passe à « {cible} ».",
                  lien=f"/dossiers/{d['id']}", cle=f"cert_{cible}:{d['id']}")
    else:
        db.notify(ctx.conn, candidat["id"], "statut", f"Dossier {d['numero']} : {STATUTS.get(cible, cible)}",
                  f"Le statut de votre dossier {d['numero']} passe à « {STATUTS.get(cible, cible)} ».",
                  lien=f"/dossiers/{d['id']}", cle=f"statut:{d['id']}:{cible}")
    ctx.conn.commit()
    redirect(ctx, f"/dossiers/{d['id']}?msg=Statut mis à jour : {STATUTS.get(cible, cible)}.")


@route("POST", r"/dossiers/(\d+)/pieces", roles=["admin", "auditeur", "candidat"])
def piece_upload(ctx, did):
    d = get_dossier(ctx, int(did))
    if not d or not verifier_acces_dossier(ctx, d):
        return t.page_erreur(ctx.user, "Accès refusé.", "Accès refusé"), 403
    if "fichier" not in ctx.files:
        redirect(ctx, f"/dossiers/{d['id']}?erreur=Aucun fichier sélectionné.")
        return
    nom, ctype, payload = ctx.files["fichier"]
    if not nom:
        redirect(ctx, f"/dossiers/{d['id']}?erreur=Nom de fichier vide.")
        return
    if len(payload) > TAILLE_MAX_PIECE:
        redirect(ctx, f"/dossiers/{d['id']}?erreur=Fichier trop volumineux (max 10 Mo).")
        return
    ctx.conn.execute(
        "INSERT INTO pieces(dossier_id, nom, content_type, taille, contenu, uploader_id, at) VALUES (?,?,?,?,?,?,?)",
        (d["id"], os.path.basename(nom), ctype, len(payload), payload, ctx.user["id"], db.now()),
    )
    db.audit(ctx.conn, ctx.user["id"], "piece_ajoutee", "piece", None, f"{d['numero']} / {nom}")
    ctx.conn.commit()
    redirect(ctx, f"/dossiers/{d['id']}?msg=Pièce « {nom} » téléversée.")


@route("GET", r"/pieces/(\d+)")
def piece_download(ctx, pid):
    p = ctx.conn.execute("SELECT * FROM pieces WHERE id = ?", (int(pid),)).fetchone()
    if not p:
        return t.page_erreur(ctx.user, "Pièce introuvable.", "Introuvable"), 404
    d = get_dossier(ctx, p["dossier_id"])
    if not d or not verifier_acces_dossier(ctx, d):
        return t.page_erreur(ctx.user, "Accès refusé.", "Accès refusé"), 403
    respond(ctx, p["contenu"], ctype=p["content_type"] or "application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{p["nom"]}"'})


@route("POST", r"/pieces/(\d+)/supprimer", roles=["admin", "candidat"])
def piece_delete(ctx, pid):
    p = ctx.conn.execute("SELECT * FROM pieces WHERE id = ?", (int(pid),)).fetchone()
    if not p:
        return t.page_erreur(ctx.user, "Pièce introuvable.", "Introuvable"), 404
    d = get_dossier(ctx, p["dossier_id"])
    if not d or not verifier_acces_dossier(ctx, d):
        return t.page_erreur(ctx.user, "Accès refusé.", "Accès refusé"), 403
    if ctx.user["role"] == "candidat" and p["uploader_id"] != ctx.user["id"]:
        return t.page_erreur(ctx.user, "Vous ne pouvez supprimer que vos propres pièces.", "Accès refusé"), 403
    ctx.conn.execute("DELETE FROM pieces WHERE id = ?", (p["id"],))
    db.audit(ctx.conn, ctx.user["id"], "piece_supprimee", "piece", p["id"], f"{d['numero']} / {p['nom']}")
    ctx.conn.commit()
    redirect(ctx, f"/dossiers/{d['id']}?msg=Pièce supprimée.")


@route("POST", r"/dossiers/(\d+)/commentaires", roles=["admin", "auditeur", "candidat"])
def commentaire_post(ctx, did):
    d = get_dossier(ctx, int(did))
    if not d or not verifier_acces_dossier(ctx, d):
        return t.page_erreur(ctx.user, "Accès refusé.", "Accès refusé"), 403
    contenu = ctx.form.get("contenu", "").strip()
    if not contenu:
        redirect(ctx, f"/dossiers/{d['id']}?erreur=Message vide.")
        return
    interne = 1 if (ctx.user["role"] in ("admin", "auditeur") and ctx.form.get("interne") == "1") else 0
    ctx.conn.execute(
        "INSERT INTO commentaires(dossier_id, auteur_id, interne, contenu, at) VALUES (?,?,?,?,?)",
        (d["id"], ctx.user["id"], interne, contenu, db.now()),
    )
    candidat = ctx.conn.execute("SELECT * FROM users WHERE id = ?", (d["candidat_id"],)).fetchone()
    if ctx.user["role"] == "candidat":
        db.notify_role(ctx.conn, "admin", "message", f"Nouveau message — {d['numero']}",
                       f"{candidat['organisme'] or candidat['nom']} : {contenu[:100]}", lien=f"/dossiers/{d['id']}",
                       cle=f"msg:{d['id']}:{db.now()}")
        db.notify_role(ctx.conn, "auditeur", "message", f"Nouveau message — {d['numero']}",
                       f"{candidat['organisme'] or candidat['nom']} : {contenu[:100]}", lien=f"/dossiers/{d['id']}",
                       cle=f"msg:{d['id']}:{db.now()}")
    elif not interne:
        db.notify(ctx.conn, candidat["id"], "message", f"Réponse LCP — {d['numero']}",
                  contenu[:200], lien=f"/dossiers/{d['id']}", cle=f"msg:{d['id']}:{db.now()}")
        db.send_email(ctx.conn, candidat["email"], f"[LCP] Nouveau message sur le dossier {d['numero']}",
                      f"Bonjour,\n\nNouveau message de LCP sur votre dossier {d['numero']} :\n\n{contenu}\n\nLCP — Certification OFDTI",
                      dossier_id=d["id"])
    db.audit(ctx.conn, ctx.user["id"], "commentaire", "dossier", d["id"], d["numero"])
    ctx.conn.commit()
    redirect(ctx, f"/dossiers/{d['id']}")


@route("GET", r"/certificats")
def certificats_liste(ctx):
    if ctx.user["role"] == "candidat":
        certs = ctx.conn.execute(
            "SELECT c.*, d.numero AS dossier_numero, d.type_service, u.nom, u.organisme FROM certificats c "
            "JOIN dossiers d ON d.id = c.dossier_id JOIN users u ON u.id = d.candidat_id "
            "WHERE d.candidat_id = ? ORDER BY c.date_expiration", (ctx.user["id"],)
        ).fetchall()
    else:
        certs = ctx.conn.execute(
            "SELECT c.*, d.numero AS dossier_numero, d.type_service, u.nom, u.organisme FROM certificats c "
            "JOIN dossiers d ON d.id = c.dossier_id JOIN users u ON u.id = d.candidat_id ORDER BY c.date_expiration"
        ).fetchall()
    return t.page_certificats(ctx.user, certs)


@route("GET", r"/certificats/(\d+)/print")
def certificat_print(ctx, cid):
    cert = ctx.conn.execute("SELECT * FROM certificats WHERE id = ?", (int(cid),)).fetchone()
    if not cert:
        return t.page_erreur(ctx.user, "Certificat introuvable.", "Introuvable"), 404
    d = get_dossier(ctx, cert["dossier_id"])
    if not d or not verifier_acces_dossier(ctx, d):
        return t.page_erreur(ctx.user, "Accès refusé.", "Accès refusé"), 403
    candidat = ctx.conn.execute("SELECT * FROM users WHERE id = ?", (d["candidat_id"],)).fetchone()
    return t.page_certificat_print(cert, d, candidat, candidat["organisme"] or candidat["nom"])


@route("GET", r"/factures")
def factures_liste(ctx):
    if ctx.user["role"] == "candidat":
        factures = ctx.conn.execute(
            "SELECT f.*, d.numero AS dossier_numero, u.nom, u.organisme FROM factures f "
            "JOIN dossiers d ON d.id = f.dossier_id JOIN users u ON u.id = d.candidat_id "
            "WHERE d.candidat_id = ? ORDER BY f.emise_at DESC", (ctx.user["id"],)
        ).fetchall()
    else:
        factures = ctx.conn.execute(
            "SELECT f.*, d.numero AS dossier_numero, u.nom, u.organisme FROM factures f "
            "JOIN dossiers d ON d.id = f.dossier_id JOIN users u ON u.id = d.candidat_id ORDER BY f.emise_at DESC"
        ).fetchall()
    return t.page_factures(ctx.user, factures)


@route("POST", r"/factures/(\d+)/payer", roles=["admin"])
def facture_payer(ctx, fid):
    f = ctx.conn.execute("SELECT * FROM factures WHERE id = ?", (int(fid),)).fetchone()
    if not f:
        return t.page_erreur(ctx.user, "Facture introuvable.", "Introuvable"), 404
    ctx.conn.execute("UPDATE factures SET statut = 'payee', payee_at = ? WHERE id = ?", (db.now(), f["id"]))
    d = get_dossier(ctx, f["dossier_id"])
    db.audit(ctx.conn, ctx.user["id"], "facture_payee", "facture", f["id"], f["numero"])
    if d:
        candidat = ctx.conn.execute("SELECT * FROM users WHERE id = ?", (d["candidat_id"],)).fetchone()
        db.notify(ctx.conn, candidat["id"], "paiement", f"Facture {f['numero']} enregistrée comme payée",
                  f"Le paiement de la facture {f['numero']} ({f['montant']:.2f} €) a été enregistré.",
                  lien=f"/dossiers/{d['id']}", cle=f"paye:{f['id']}")
    ctx.conn.commit()
    redirect(ctx, f"/factures")


@route("GET", r"/notifications")
def notifs_liste(ctx):
    notifs = ctx.conn.execute(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY at DESC LIMIT 100", (ctx.user["id"],)
    ).fetchall()
    return t.page_notifications(ctx.user, notifs, ctx.csrf)


@route("GET", r"/notifications/(\d+)/lire", roles=None)
def notif_lire(ctx, nid):
    n = ctx.conn.execute("SELECT * FROM notifications WHERE id = ? AND user_id = ?", (int(nid), ctx.user["id"])).fetchone()
    if n:
        ctx.conn.execute("UPDATE notifications SET lu = 1 WHERE id = ?", (n["id"],))
        ctx.conn.commit()
        redirect(ctx, n["lien"] or "/notifications")
    else:
        redirect(ctx, "/notifications")


@route("POST", r"/notifications/tout_lire")
def notifs_tout_lire(ctx):
    ctx.conn.execute("UPDATE notifications SET lu = 1 WHERE user_id = ?", (ctx.user["id"],))
    ctx.conn.commit()
    redirect(ctx, "/notifications")


@route("GET", r"/admin", roles=["admin"])
def admin_home(ctx):
    redirect(ctx, "/admin/users")


@route("GET", r"/admin/users", roles=["admin"])
def admin_users_get(ctx):
    users = ctx.conn.execute("SELECT * FROM users ORDER BY created_at, id").fetchall()
    msg = ctx.query.get("msg", [""])[0]
    return t.page_admin_users(ctx.user, users, ctx.csrf, msg=msg)


@route("POST", r"/admin/users", roles=["admin"])
def admin_users_post(ctx):
    email = ctx.form.get("email", "").strip().lower()
    password = ctx.form.get("password", "")
    nom = ctx.form.get("nom", "").strip()
    role = ctx.form.get("role", "candidat")
    organisme = ctx.form.get("organisme", "").strip()
    siret = ctx.form.get("siret", "").strip()
    if not email or not password or not nom or role not in ("admin", "auditeur", "candidat"):
        redirect(ctx, "/admin/users?msg=" + "Champs invalides.")
        return
    try:
        ctx.conn.execute(
            "INSERT INTO users(email, password_hash, nom, role, organisme, siret, actif, created_at) VALUES (?,?,?,?,?,?,1,?)",
            (email, db.hash_password(password), nom, role, organisme, siret, db.now()),
        )
        db.audit(ctx.conn, ctx.user["id"], "user_cree", "user", None, f"{email} ({role})")
        ctx.conn.commit()
        redirect(ctx, "/admin/users?msg=Utilisateur créé.")
    except Exception:
        ctx.conn.rollback()
        redirect(ctx, "/admin/users?msg=Cet e-mail est déjà utilisé.")


@route("POST", r"/admin/users/(\d+)/toggle", roles=["admin"])
def admin_user_toggle(ctx, uid):
    u = ctx.conn.execute("SELECT * FROM users WHERE id = ?", (int(uid),)).fetchone()
    if u and u["id"] != ctx.user["id"]:
        ctx.conn.execute("UPDATE users SET actif = 1 - actif WHERE id = ?", (u["id"],))
        db.audit(ctx.conn, ctx.user["id"], "user_toggle", "user", u["id"], u["email"])
        ctx.conn.commit()
    redirect(ctx, "/admin/users")


@route("GET", r"/admin/parametres", roles=["admin"])
def admin_params_get(ctx):
    params = {cle: db.get_param(ctx.conn, cle) for cle in db.DEFAULT_PARAMS}
    msg = ctx.query.get("msg", [""])[0]
    return t.page_admin_params(ctx.user, params, ctx.csrf, msg=msg)


@route("POST", r"/admin/parametres", roles=["admin"])
def admin_params_post(ctx):
    for cle in db.DEFAULT_PARAMS:
        if cle in ctx.form:
            db.set_param(ctx.conn, cle, ctx.form[cle].strip())
    db.audit(ctx.conn, ctx.user["id"], "params_modifies", "parametres", None, ", ".join(db.DEFAULT_PARAMS))
    ctx.conn.commit()
    redirect(ctx, "/admin/parametres?msg=Paramètres enregistrés.")


@route("POST", r"/admin/automations/run", roles=["admin"])
def admin_automations_run(ctx):
    result = automations.run_automations(ctx.conn)
    redirect(ctx, "/admin/parametres?msg=Automatisations exécutées : " + str(result).replace(" ", ""))


@route("GET", r"/admin/outbox", roles=["admin"])
def admin_outbox(ctx):
    emails = ctx.conn.execute("SELECT * FROM outbox ORDER BY at DESC LIMIT 100").fetchall()
    return t.page_admin_outbox(ctx.user, emails)


@route("GET", r"/admin/audit", roles=["admin"])
def admin_audit(ctx):
    logs = ctx.conn.execute("SELECT * FROM audit_log ORDER BY at DESC, id DESC LIMIT 200").fetchall()
    users = {u["id"]: u["nom"] for u in ctx.conn.execute("SELECT id, nom FROM users").fetchall()}
    return t.page_admin_audit(ctx.user, logs, users)


def export_csv(ctx, filename, header, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    respond(ctx, "\ufeff" + buf.getvalue(), ctype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@route("GET", r"/exports/dossiers.csv")
def export_dossiers(ctx):
    sql = ("SELECT d.numero, u.email, u.organisme, d.type_service, d.statut, d.created_at, d.depose_at, d.decision, d.decision_at, d.motif "
           "FROM dossiers d JOIN users u ON u.id = d.candidat_id")
    params = []
    if ctx.user["role"] == "candidat":
        sql += " WHERE d.candidat_id = ?"
        params = [ctx.user["id"]]
    sql += " ORDER BY d.created_at"
    rows = ctx.conn.execute(sql, params).fetchall()
    export_csv(ctx, "dossiers_ofdti.csv",
               ["numero", "email", "organisme", "type_service", "statut", "cree_le", "depose_le", "decision", "decision_le", "motif"],
               [tuple(r) for r in rows])


@route("GET", r"/exports/certifies.csv")
def export_certifies(ctx):
    sql = ("SELECT c.numero, d.numero AS dossier, u.organisme, d.type_service, c.statut, c.date_delivrance, c.date_expiration "
           "FROM certificats c JOIN dossiers d ON d.id = c.dossier_id JOIN users u ON u.id = d.candidat_id")
    params = []
    if ctx.user["role"] == "candidat":
        sql += " WHERE d.candidat_id = ?"
        params = [ctx.user["id"]]
    sql += " ORDER BY c.date_delivrance"
    rows = ctx.conn.execute(sql, params).fetchall()
    export_csv(ctx, "registre_certifies_ofdti.csv",
               ["certificat", "dossier", "organisme", "service", "statut", "delivrance", "expiration"],
               [tuple(r) for r in rows])


@route("GET", r"/exports/factures.csv")
def export_factures(ctx):
    sql = ("SELECT f.numero, d.numero AS dossier, u.organisme, f.montant, f.statut, f.emise_at, f.echeance, f.payee_at, f.nb_relances "
           "FROM factures f JOIN dossiers d ON d.id = f.dossier_id JOIN users u ON u.id = d.candidat_id")
    params = []
    if ctx.user["role"] == "candidat":
        sql += " WHERE d.candidat_id = ?"
        params = [ctx.user["id"]]
    sql += " ORDER BY f.emise_at"
    rows = ctx.conn.execute(sql, params).fetchall()
    export_csv(ctx, "factures_ofdti.csv",
               ["facture", "dossier", "organisme", "montant", "statut", "emise_le", "echeance", "payee_le", "relances"],
               [tuple(r) for r in rows])


@route("GET", r"/certificats/(\d+)/pdf")
def certificat_pdf(ctx, cid):
    cert = ctx.conn.execute("SELECT * FROM certificats WHERE id = ?", (int(cid),)).fetchone()
    if not cert:
        return t.page_erreur(ctx.user, "Certificat introuvable.", "Introuvable"), 404
    d = get_dossier(ctx, cert["dossier_id"])
    if not d or not verifier_acces_dossier(ctx, d):
        return t.page_erreur(ctx.user, "Accès refusé.", "Accès refusé"), 403
    d, candidat, dom_sel, typ_sel, dom_all, lieu, signataire = contexte_certificat(ctx, cert)
    signe_at = db.now()
    pdf_bytes, pdf_hash, sig_hex, fp = pdfgen.certificat_pdf_signe(
        cert, d, candidat, charger_mentions(), dom_sel, typ_sel, dom_all, lieu, signataire, BASE_URL, signe_at)
    ctx.conn.execute(
        "INSERT INTO signatures(certificat_id, pdf_hash, signature, key_fingerprint, signe_at) VALUES (?,?,?,?,?) "
        "ON CONFLICT(certificat_id) DO UPDATE SET pdf_hash=excluded.pdf_hash, signature=excluded.signature, "
        "key_fingerprint=excluded.key_fingerprint, signe_at=excluded.signe_at",
        (cert["id"], pdf_hash, sig_hex, fp, signe_at),
    )
    db.audit(ctx.conn, ctx.user["id"], "pdf_signe", "certificat", cert["id"], cert["numero"])
    ctx.conn.commit()
    respond(ctx, pdf_bytes, ctype="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="certificat_{cert["numero"]}.pdf"'})


@route("GET", r"/certificats/(\d+)/verify")
def certificat_verify(ctx, cid):
    import hashlib
    cert = ctx.conn.execute("SELECT * FROM certificats WHERE id = ?", (int(cid),)).fetchone()
    if not cert:
        return t.page_erreur(ctx.user, "Certificat introuvable.", "Introuvable"), 404
    d = get_dossier(ctx, cert["dossier_id"])
    if not d or not verifier_acces_dossier(ctx, d):
        return t.page_erreur(ctx.user, "Accès refusé.", "Accès refusé"), 403
    d, candidat, dom_sel, typ_sel, dom_all, lieu, signataire = contexte_certificat(ctx, cert)
    sig = ctx.conn.execute("SELECT * FROM signatures WHERE certificat_id = ?", (cert["id"],)).fetchone()
    _, pub = pdfgen.get_keys()
    unsigned = pdfgen.certificat_pdf_unsigned(cert, d, candidat, charger_mentions(), dom_sel, typ_sel, dom_all, lieu, signataire)
    hash_now = hashlib.sha256(unsigned).hexdigest()
    if sig:
        ok = pdfgen.verifier_hash(unsigned, sig["signature"], pub) and hash_now == sig["pdf_hash"]
        details = [
            ("Certificat", cert["numero"]),
            ("Empreinte SHA-256 recalculée", hash_now),
            ("Empreinte enregistrée", sig["pdf_hash"]),
            ("Correspondance des empreintes", "oui" if hash_now == sig["pdf_hash"] else "NON"),
            ("Signature RSA-2048 vérifiée", "oui" if pdfgen.verifier_hash(unsigned, sig["signature"], pub) else "NON"),
            ("Empreinte de clé publique", sig["key_fingerprint"]),
            ("Signé le", sig["signe_at"]),
        ]
    else:
        ok = False
        details = [("Certificat", cert["numero"]), ("État", "aucune signature enregistrée — téléchargez d'abord le PDF signé")]
    return t.page_verify(ctx.user, cert, ok, details)


@route("GET", r"/api/pubkey", roles=None, csrf=False)
def pubkey(ctx):
    if not ctx.user:
        redirect(ctx, "/login?next=/api/pubkey")
        return
    _, pub = pdfgen.get_keys()
    from cryptography.hazmat.primitives import serialization
    pem = pub.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    respond(ctx, pem, ctype="application/x-pem-file")


@route("POST", r"/certificats/(\d+)/renouveler", roles=["admin", "candidat"])
def cert_renouveler(ctx, cid):
    cert = ctx.conn.execute("SELECT * FROM certificats WHERE id = ?", (int(cid),)).fetchone()
    if not cert:
        return t.page_erreur(ctx.user, "Certificat introuvable.", "Introuvable"), 404
    d = get_dossier(ctx, cert["dossier_id"])
    if not d or not verifier_acces_dossier(ctx, d):
        return t.page_erreur(ctx.user, "Accès refusé.", "Accès refusé"), 403
    existe = ctx.conn.execute("SELECT id FROM dossiers WHERE renouvellement_de = ?", (cert["id"],)).fetchone()
    if existe:
        redirect(ctx, f"/dossiers/{existe['id']}?msg=Dossier de renouvellement déjà créé.")
        return
    numero = db.next_numero(ctx.conn, "DOS", "dossiers", "numero")
    now_s = db.now()
    cur = ctx.conn.execute(
        "INSERT INTO dossiers(numero, candidat_id, type_service, description, statut, renouvellement_de, created_at, updated_at) "
        "VALUES (?,?,?,?, 'brouillon', ?,?,?)",
        (numero, d["candidat_id"], f"Renouvellement certification {cert['numero']}",
         f"Renouvellement de la certification OFDTI {cert['numero']} (expire le {cert['date_expiration'][:10]}).",
         cert["id"], now_s, now_s),
    )
    did = cur.lastrowid
    ctx.conn.execute(
        "INSERT INTO historique(dossier_id, ancien, nouveau, acteur_id, commentaire, at) VALUES (?,?,?,?,?,?)",
        (did, None, "brouillon", ctx.user["id"], f"Renouvellement de {cert['numero']}", now_s),
    )
    db.audit(ctx.conn, ctx.user["id"], "renouvellement_cree", "dossier", did, numero)
    db.notify(ctx.conn, d["candidat_id"], "renouvellement",
              f"Dossier de renouvellement {numero} créé",
              f"Un dossier de renouvellement {numero} pour la certification {cert['numero']} a été créé en brouillon.",
              lien=f"/dossiers/{did}", cle=f"renou_man:{cert['id']}")
    ctx.conn.commit()
    redirect(ctx, f"/dossiers/{did}?msg=Dossier de renouvellement {numero} créé (brouillon à déposer).")


@route("GET", r"/dossiers/(\d+)/rapport-audit.pdf", roles=["admin", "auditeur"])
def rapport_audit_pdf(ctx, did):
    d = get_dossier(ctx, int(did))
    if not d or not verifier_acces_dossier(ctx, d):
        return t.page_erreur(ctx.user, "Accès refusé.", "Accès refusé"), 403
    candidat = ctx.conn.execute("SELECT * FROM users WHERE id = ?", (d["candidat_id"],)).fetchone()
    users = ctx.users_map()
    coms = ctx.conn.execute(
        "SELECT * FROM commentaires WHERE dossier_id = ? AND interne = 1 ORDER BY at, id", (d["id"],)
    ).fetchall()
    lignes = [(users.get(c["auteur_id"], {}).get("nom", "?"), c["at"], c["contenu"]) for c in coms]
    pdf_bytes = pdfgen.build_pdf([pdfgen.page_rapport_audit(d, candidat, lignes)])
    db.audit(ctx.conn, ctx.user["id"], "rapport_audit_pdf", "dossier", d["id"], d["numero"])
    ctx.conn.commit()
    respond(ctx, pdf_bytes, ctype="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="rapport_audit_{d["numero"]}.pdf"'})


@route("GET", r"/stats", roles=["admin", "auditeur"])
def stats(ctx):
    c = ctx.conn
    par_statut = c.execute("SELECT statut, COUNT(*) AS n FROM dossiers GROUP BY statut ORDER BY n DESC").fetchall()
    data_statuts = [(STATUTS.get(r["statut"], r["statut"]), r["n"]) for r in par_statut] or [("aucun dossier", 0)]
    limite_mois = db.iso(db.utcnow() - timedelta(days=365))[:8] + "01"
    mens = c.execute(
        "SELECT substr(created_at, 1, 7) AS m, COUNT(*) AS n FROM dossiers WHERE created_at >= ? GROUP BY m ORDER BY m",
        (limite_mois,),
    ).fetchall()
    data_mensuel = [(r["m"], r["n"]) for r in mens] or [("—", 0)]
    frows = c.execute("SELECT statut, COUNT(*) AS n FROM factures GROUP BY statut").fetchall()
    couleurs = {"payee": "#177245", "emise": "#1a56b0", "en_retard": "#b3261e"}
    data_factures = [(r["statut"], r["n"], couleurs.get(r["statut"], "#5b6b7c")) for r in frows] or [("aucune", 0, "#5b6b7c")]
    decisions = c.execute("SELECT COUNT(*) AS n FROM dossiers WHERE decision_at IS NOT NULL").fetchone()["n"]
    certifies = c.execute("SELECT COUNT(*) AS n FROM dossiers WHERE statut = 'certifie'").fetchone()["n"]
    taux = round(100 * certifies / decisions) if decisions else 0
    delai = c.execute(
        "SELECT AVG(julianday(decision_at) - julianday(depose_at)) AS d FROM dossiers "
        "WHERE decision_at IS NOT NULL AND depose_at IS NOT NULL").fetchone()["d"]
    retard = c.execute("SELECT COUNT(*) AS n, COALESCE(SUM(montant), 0) AS s FROM factures WHERE statut = 'en_retard'").fetchone()
    certs_actifs = c.execute("SELECT COUNT(*) AS n FROM certificats WHERE statut = 'valide'").fetchone()["n"]
    certs_exp90 = c.execute(
        "SELECT COUNT(*) AS n FROM certificats WHERE statut = 'valide' AND date_expiration < ?",
        (db.iso(db.utcnow() + timedelta(days=90)),)).fetchone()["n"]
    kpis = [
        (f"{delai:.0f} j" if delai else "—", "délai moyen dépôt → décision"),
        (f"{taux} %", "taux de certification"),
        (f"{retard['s']:.0f} €", f"en retard ({retard['n']} factures)"),
        (certs_actifs, "certificats valides"),
        (certs_exp90, "expirent < 90 j"),
    ]
    charts_html = {
        "statuts": charts.bar_chart(data_statuts),
        "mensuel": charts.bar_chart(data_mensuel, color="#7fb3ff", label_size=9),
        "factures": charts.donut(data_factures),
    }
    return t.page_stats(ctx.user, kpis, charts_html)


@route("GET", r"/documents")
def documents_liste(ctx):
    fichiers = sorted(os.listdir(DOCS_DIR))
    return t.page_documents(ctx.user, fichiers)


@route("GET", r"/documents/([^/]+)")
def document_download(ctx, name):
    name = os.path.basename(name)
    p = os.path.join(DOCS_DIR, name)
    if not os.path.isfile(p):
        return t.page_erreur(ctx.user, "Document introuvable.", "404"), 404
    ctype = {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
    }.get(os.path.splitext(name)[1].lower(), "application/octet-stream")
    with open(p, "rb") as f:
        data = f.read()
    respond(ctx, data, ctype=ctype, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@route("GET", r"/health", roles=None, csrf=False)
def health(ctx):
    respond(ctx, "ok", ctype="text/plain; charset=utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "CRMLCP/0.1"

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _dispatch(self, method):
        parsed = urlparse(self.path)
        path = parsed.path
        if len(path) > 1:
            path = path.rstrip("/")
        query = parse_qs(parsed.query)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        body = self.rfile.read(length) if length else b""
        ctx = Ctx(self, method, path, query, body)
        try:
            for m, rx, fn, roles, need_csrf in ROUTES:
                if m != method:
                    continue
                match = rx.match(path)
                if not match:
                    continue
                if need_csrf and method == "POST":
                    if not ctx.user or ctx.form.get("csrf") != ctx.csrf:
                        respond(ctx, t.page_erreur(None, "Session expirée ou jeton CSRF invalide, veuillez vous reconnecter.", "Session expirée"), status=403)
                        return
                if roles and (not ctx.user or ctx.user["role"] not in roles):
                    if not ctx.user:
                        redirect(ctx, "/login?next=" + path)
                    else:
                        respond(ctx, t.page_erreur(ctx.user, "Vous n'avez pas les droits pour cette action.", "Accès refusé"), status=403)
                    return
                result = fn(ctx, *match.groups())
                status = 200
                if isinstance(result, tuple):
                    status = result[-1] if isinstance(result[-1], int) else 200
                    result = result[0]
                if result is None:
                    return
                if isinstance(result, str):
                    respond(ctx, result, status=status)
                return
            if not ctx.user:
                redirect(ctx, "/login?next=" + path)
            else:
                respond(ctx, t.page_erreur(ctx.user, "Page introuvable.", "404"), status=404)
        except Redirect as r:
            respond(ctx, "", status=303, headers={"Location": r.location})
        except BrokenPipeError:
            pass
        except Exception as exc:
            import traceback
            traceback.print_exc()
            try:
                respond(ctx, t.page_erreur(ctx.user if ctx.user else None, f"Erreur interne : {exc}", "Erreur"), status=500)
            except Exception:
                pass
        finally:
            try:
                ctx.conn.close()
            except Exception:
                pass


def main():
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "127.0.0.1")
    reset = "--reset" in sys.argv
    db.init_db(reset=reset)
    conn0 = db.connect()
    automations.run_automations(conn0)
    conn0.close()
    automations.start_background(60)
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    print(f"CRM LCP — Certification OFDTI démarré sur http://{host}:{port}")
    print("Comptes de démonstration : admin@lcp.fr/admin123 · auditeur@lcp.fr/audit123 · candidat@exemple.fr/demo123")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
