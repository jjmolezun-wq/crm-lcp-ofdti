import html
from datetime import datetime

from workflow import STATUTS, STATUT_CLASS


def esc(x):
    return html.escape("" if x is None else str(x))


def fmt_date(ts):
    if not ts:
        return "—"
    try:
        return datetime.fromisoformat(ts).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return esc(ts)


def fmt_date_jour(ts):
    if not ts:
        return "—"
    try:
        return datetime.fromisoformat(ts).strftime("%d/%m/%Y")
    except ValueError:
        return esc(ts)


def jours_restants(ts):
    from db import parse, utcnow
    if not ts:
        return None
    return (parse(ts) - utcnow()).days


CSS = """
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f4f6fa; color: #1c2733; }
header { background: #14304f; color: #fff; padding: 0 24px; display: flex; align-items: center; gap: 24px; height: 56px; }
header .brand { font-weight: 700; font-size: 18px; white-space: nowrap; }
header .brand span { color: #7fb3ff; }
header nav { display: flex; gap: 4px; flex: 1; flex-wrap: wrap; }
header nav a { color: #d7e3f4; text-decoration: none; padding: 8px 12px; border-radius: 6px; font-size: 14px; }
header nav a:hover { background: #1f4568; color: #fff; }
header .user { font-size: 13px; color: #bcd2ee; white-space: nowrap; }
header .user b { color: #fff; }
.role { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; background: #2c5d8f; color: #fff; margin-left: 6px; }
main { max-width: 1120px; margin: 24px auto; padding: 0 16px; }
h1 { font-size: 22px; margin: 0 0 16px; }
h2 { font-size: 17px; margin: 24px 0 10px; }
.card { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 18px; margin-bottom: 18px; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #e8edf3; vertical-align: top; }
th { color: #5b6b7c; font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
a { color: #1668c4; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; white-space: nowrap; }
.badge.ok { background: #dcf5e3; color: #177245; }
.badge.warn { background: #fdf0d3; color: #9a6a00; }
.badge.danger { background: #fde2e2; color: #b3261e; }
.badge.info { background: #ddeafd; color: #1a56b0; }
.badge.muted { background: #e8edf3; color: #5b6b7c; }
.btn { display: inline-block; background: #1668c4; color: #fff !important; border: none; border-radius: 7px; padding: 8px 14px; font-size: 14px; cursor: pointer; text-decoration: none; }
.btn:hover { background: #0f52a3; }
.btn.secondary { background: #e8edf3; color: #1c2733 !important; }
.btn.danger { background: #b3261e; }
.btn.small { padding: 5px 10px; font-size: 13px; }
input[type=text], input[type=email], input[type=password], input[type=number], select, textarea {
  width: 100%; padding: 8px 10px; border: 1px solid #c9d4e0; border-radius: 7px; font-size: 14px; background: #fff; }
textarea { min-height: 90px; }
label { display: block; font-size: 13px; font-weight: 600; color: #42566b; margin: 10px 0 4px; }
.flash { background: #dcf5e3; border: 1px solid #9edcb4; color: #177245; padding: 10px 14px; border-radius: 8px; margin-bottom: 14px; font-size: 14px; }
.erreur { background: #fde2e2; border: 1px solid #f3b6b6; color: #b3261e; padding: 10px 14px; border-radius: 8px; margin-bottom: 14px; font-size: 14px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; }
.stat { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px; }
.stat .n { font-size: 26px; font-weight: 700; }
.stat .l { font-size: 12px; color: #5b6b7c; text-transform: uppercase; letter-spacing: .04em; }
.muted { color: #5b6b7c; font-size: 13px; }
.row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.comment { border-left: 3px solid #c9d4e0; padding: 6px 12px; margin: 8px 0; background: #f8fafc; border-radius: 0 8px 8px 0; }
.comment.interne { border-left-color: #b3261e; background: #fdf3f3; }
.login-box { max-width: 380px; margin: 80px auto; }
.certificat { max-width: 760px; margin: 40px auto; background: #fff; border: 3px double #14304f; padding: 48px; text-align: center; }
.certificat h1 { font-size: 28px; }
.certificat .num { font-size: 20px; font-weight: 700; letter-spacing: .08em; margin: 18px 0; }
@media print { header, .no-print { display: none; } body { background: #fff; } .certificat { border: 3px double #000; margin: 0; } }
"""


def badge_statut(s):
    return f'<span class="badge {STATUT_CLASS.get(s, "muted")}">{esc(STATUTS.get(s, s))}</span>'


def layout(user, title, body, unread=0):
    if user:
        nav = '<a href="/">Tableau de bord</a><a href="/dossiers">Dossiers</a><a href="/certificats">Certificats OFDTI</a><a href="/factures">Factures</a>'
        if user["role"] in ("admin", "auditeur"):
            nav += '<a href="/stats">Statistiques</a>'
        if user["role"] == "candidat":
            nav += '<a href="/dossiers/nouveau">+ Nouveau dossier</a>'
        if user["role"] == "admin":
            nav += '<a href="/admin">Administration</a>'
        notif = f'<a href="/notifications">Notifications{" (" + str(unread) + ")" if unread else ""}</a>'
        userbox = (f'<span class="user"><b>{esc(user["nom"])}</b>'
                   f'<span class="role">{esc(user["role"])}</span> · {notif} · <a href="/logout">Déconnexion</a></span>')
    else:
        nav = ""
        userbox = ""
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} — CRM LCP</title><style>{CSS}</style></head>
<body><header><div class="brand">CRM <span>LCP</span> · Certification OFDTI</div><nav>{nav}</nav>{userbox}</header>
<main>{body}</main></body></html>"""


def hidden_csrf(csrf):
    return f'<input type="hidden" name="csrf" value="{esc(csrf)}">'


def page_login(error=None):
    err = f'<div class="erreur">{esc(error)}</div>' if error else ""
    body = f"""
<div class="card login-box"><h1>Connexion</h1>{err}
<form method="post" action="/login">
<label>Email</label><input type="email" name="email" required autofocus>
<label>Mot de passe</label><input type="password" name="password" required>
<div style="margin-top:14px"><button class="btn" type="submit">Se connecter</button></div>
</form><p class="muted">Comptes de démonstration : admin@lcp.fr / admin123 · auditeur@lcp.fr / audit123 · candidat@exemple.fr / demo123</p></div>"""
    return layout(None, "Connexion", body)


def page_dashboard(user, stats, dossiers_recents, alertes, mes_dossiers=None, mes_factures=None, mes_certs=None):
    cards = "".join(f'<div class="stat"><div class="n">{esc(v[0])}</div><div class="l">{esc(v[1])}</div></div>' for v in stats)
    alerte_html = ""
    if alertes:
        items = "".join(f'<li>{a}</li>' for a in alertes)
        alerte_html = f'<div class="card"><h2>Alertes automatiques</h2><ul>{items}</ul></div>'
    recents = ""
    rows = "".join(
        f'<tr><td><a href="/dossiers/{d["id"]}">{esc(d["numero"])}</a></td><td>{esc(d["organisme"] or d["nom"])}</td>'
        f'<td>{esc(d["type_service"])}</td><td>{badge_statut(d["statut"])}</td><td class="muted">{fmt_date(d["updated_at"])}</td></tr>'
        for d in dossiers_recents)
    recents = f'<div class="card"><h2>Dossiers récents</h2><table><tr><th>Numéro</th><th>Organisme</th><th>Service</th><th>Statut</th><th>Maj</th></tr>{rows}</table></div>' if rows else ""
    extra = ""
    if mes_dossiers is not None:
        rows = "".join(
            f'<tr><td><a href="/dossiers/{d["id"]}">{esc(d["numero"])}</a></td><td>{esc(d["type_service"])}</td>'
            f'<td>{badge_statut(d["statut"])}</td><td class="muted">{fmt_date(d["updated_at"])}</td></tr>'
            for d in mes_dossiers)
        extra += f'<div class="card"><h2>Mes dossiers</h2><table><tr><th>Numéro</th><th>Service</th><th>Statut</th><th>Maj</th></tr>{rows}</table></div>' if rows else ""
    if mes_factures:
        rows = "".join(
            f'<tr><td>{esc(f["numero"])}</td><td><a href="/dossiers/{f["dossier_id"]}">{esc(f["dossier_numero"])}</a></td>'
            f'<td>{f["montant"]:.2f} €</td><td>{badge_statut("danger" if f["statut"] == "en_retard" else ("ok" if f["statut"] == "payee" else "info"))} {esc(f["statut"])}</td>'
            f'<td class="muted">{fmt_date_jour(f["echeance"])}</td></tr>'
            for f in mes_factures)
        extra += f'<div class="card"><h2>Mes factures impayées</h2><table><tr><th>Numéro</th><th>Dossier</th><th>Montant</th><th>Statut</th><th>Échéance</th></tr>{rows}</table></div>'
    if mes_certs:
        rows = "".join(
            f'<tr><td><a href="/certificats/{c["id"]}/print">{esc(c["numero"])}</a></td><td>{esc(c["dossier_numero"])}</td>'
            f'<td>{badge_statut("ok" if c["statut"] == "valide" else "muted")} {esc(c["statut"])}</td>'
            f'<td class="muted">{fmt_date_jour(c["date_expiration"])} ({jours_restants(c["date_expiration"])} j)</td></tr>'
            for c in mes_certs)
        extra += f'<div class="card"><h2>Mes certifications OFDTI actives</h2><table><tr><th>Numéro</th><th>Dossier</th><th>Statut</th><th>Expiration</th></tr>{rows}</table></div>'
    body = f'<h1>Tableau de bord</h1><div class="grid">{cards}</div>{alerte_html}{extra}{recents}'
    return layout(user, "Tableau de bord", body)


def page_dossiers(user, dossiers, filtre_statut, q):
    options = '<option value="">Tous les statuts</option>' + "".join(
        f'<option value="{esc(s)}"{" selected" if filtre_statut == s else ""}>{esc(l)}</option>'
        for s, l in STATUTS.items())
    rows = "".join(
        f'<tr><td><a href="/dossiers/{d["id"]}">{esc(d["numero"])}</a></td><td>{esc(d["organisme"] or d["nom"])}</td>'
        f'<td>{esc(d["type_service"])}</td><td>{badge_statut(d["statut"])}</td><td class="muted">{fmt_date(d["updated_at"])}</td></tr>'
        for d in dossiers)
    body = f"""
<h1>Dossiers de certification OFDTI</h1>
<div class="card"><form method="get" action="/dossiers" class="row">
<select name="statut" style="width:auto">{options}</select>
<input type="text" name="q" value="{esc(q)}" placeholder="Rechercher n° ou organisme" style="width:260px">
<button class="btn secondary" type="submit">Filtrer</button>
{"<a class='btn' href='/dossiers/nouveau'>+ Nouveau dossier</a>" if user["role"] == "candidat" else ""}
</form></div>
<div class="card"><table><tr><th>Numéro</th><th>Organisme</th><th>Service</th><th>Statut</th><th>Dernière maj</th></tr>{rows}</table>
{"<p class='muted'>Aucun dossier.</p>" if not rows else ""}</div>"""
    return layout(user, "Dossiers", body)


def page_dossier_new(user, csrf, error=None):
    err = f'<div class="erreur">{esc(error)}</div>' if error else ""
    body = f"""
<h1>Nouveau dossier de certification OFDTI</h1>
<div class="card"><form method="post" action="/dossiers">
{hidden_csrf(csrf)}{err}
<label>Type de service à certifier</label><input type="text" name="type_service" required placeholder="ex : Conseil stratégique">
<label>Description de la demande</label><textarea name="description" required placeholder="Périmètre, volumétrie, organisation..."></textarea>
<div style="margin-top:14px"><button class="btn" type="submit">Créer le brouillon</button> <a class="btn secondary" href="/dossiers">Annuler</a></div>
</form></div>"""
    return layout(user, "Nouveau dossier", body)


def page_dossier_detail(user, d, hist, pieces, commentaires, users, cert, facture, trans, csrf, msg=None, erreur=None):
    flash = f'<div class="flash">{esc(msg)}</div>' if msg else ""
    err = f'<div class="erreur">{esc(erreur)}</div>' if erreur else ""
    hist_rows = "".join(
        f'<tr><td class="muted">{fmt_date(h["at"])}</td><td>{esc(users.get(h["acteur_id"], {}).get("nom", "?"))}</td>'
        f'<td>{badge_statut(h["ancien"]) if h["ancien"] else "—"} → {badge_statut(h["nouveau"])}</td><td>{esc(h["commentaire"] or "")}</td></tr>'
        for h in hist)
    pieces_rows = "".join(
        f'<tr><td><a href="/pieces/{p["id"]}">{esc(p["nom"])}</a></td><td class="muted">{p["taille"]} o</td>'
        f'<td class="muted">{esc(users.get(p["uploader_id"], {}).get("nom", "?"))}</td><td class="muted">{fmt_date(p["at"])}</td>'
        f'<td><form method="post" action="/pieces/{p["id"]}/supprimer" style="display:inline">{hidden_csrf(csrf)}<button class="btn small danger">Supprimer</button></form></td></tr>'
        for p in pieces)
    com_rows = "".join(
        f'<div class="comment{" interne" if c["interne"] else ""}"><b>{esc(users.get(c["auteur_id"], {}).get("nom", "?"))}</b>'
        f'{" <span class=\"badge danger\">interne</span>" if c["interne"] else ""} <span class="muted">{fmt_date(c["at"])}</span><br>{esc(c["contenu"])}</div>'
        for c in commentaires)
    interne_check = '<label style="display:inline;font-weight:400"><input type="checkbox" name="interne" value="1" style="width:auto"> commentaire interne (visible staff LCP uniquement)</label>' if user["role"] in ("admin", "auditeur") else ""
    trans_options = "".join(f'<option value="{esc(t)}">{esc(STATUTS[t])}</option>' for t in trans)
    action_html = ""
    if user["role"] in ("admin", "auditeur"):
        action_html += f'<div class="card"><h2>Rapport d\'audit</h2><p><a class="btn small secondary" href="/dossiers/{d["id"]}/rapport-audit.pdf">Télécharger le rapport d\'audit (PDF)</a></p></div>'
    if trans:
        action_html = f"""
<div class="card"><h2>Changer le statut</h2><form method="post" action="/dossiers/{d["id"]}/statut" class="row">
{hidden_csrf(csrf)}<select name="statut" style="width:auto">{trans_options}</select>
<input type="text" name="commentaire" placeholder="Commentaire / motif (obligatoire si refus)" style="width:320px">
<button class="btn" type="submit">Appliquer</button></form></div>"""
    cert_html = ""
    if cert:
        jr = jours_restants(cert["date_expiration"])
        renouveler = ""
        if user["role"] == "admin" or (user["role"] == "candidat" and d["candidat_id"] == user["id"]):
            renouveler = f' <form method="post" action="/certificats/{cert["id"]}/renouveler" style="display:inline">{hidden_csrf(csrf)}<button class="btn small secondary">Demander le renouvellement</button></form>'
        cert_html = f"""
<div class="card"><h2>Certificat OFDTI</h2>
<table><tr><th>Numéro</th><td><b>{esc(cert["numero"])}</b></td></tr>
<tr><th>Délivré le</th><td>{fmt_date_jour(cert["date_delivrance"])}</td></tr>
<tr><th>Expire le</th><td>{fmt_date_jour(cert["date_expiration"])} ({jr} j restants)</td></tr>
<tr><th>Statut</th><td>{badge_statut("ok" if cert["statut"] == "valide" else "muted")} {esc(cert["statut"])}</td></tr>
<tr><th>Documents</th><td><a class="btn small" href="/certificats/{cert["id"]}/print" target="_blank">Certificat (aperçu)</a> <a class="btn small" href="/certificats/{cert["id"]}/pdf">PDF signé</a> <a class="btn small secondary" href="/certificats/{cert["id"]}/verify" target="_blank">Vérifier la signature</a>{renouveler}</td></tr></table></div>"""
    fac_html = ""
    if facture:
        payer = f'<form method="post" action="/factures/{facture["id"]}/payer" style="display:inline">{hidden_csrf(csrf)}<button class="btn small">Marquer payée</button></form>' if user["role"] == "admin" and facture["statut"] != "payee" else ""
        fac_html = f"""
<div class="card"><h2>Facture</h2>
<table><tr><th>Numéro</th><td>{esc(facture["numero"])}</td></tr>
<tr><th>Montant</th><td>{facture["montant"]:.2f} €</td></tr>
<tr><th>Statut</th><td>{esc(facture["statut"])} ({facture["nb_relances"]} relance(s))</td></tr>
<tr><th>Échéance</th><td>{fmt_date_jour(facture["echeance"])}</td></tr>
<tr><th>Actions</th><td>{payer}</td></tr></table></div>"""
    body = f"""
<h1>Dossier {esc(d["numero"])} {badge_statut(d["statut"])}</h1>
{flash}{err}
<div class="card"><h2>Informations</h2>
<table><tr><th>Organisme</th><td>{esc(d["organisme"] or users.get(d["candidat_id"], {}).get("organisme", ""))}</td></tr>
<tr><th>Contact</th><td>{esc(users.get(d["candidat_id"], {}).get("nom", ""))} — {esc(users.get(d["candidat_id"], {}).get("email", ""))}</td></tr>
<tr><th>Type de service</th><td>{esc(d["type_service"])}</td></tr>
<tr><th>Description</th><td>{esc(d["description"])}</td></tr>
<tr><th>Créé le</th><td class="muted">{fmt_date(d["created_at"])}</td></tr>
<tr><th>Déposé le</th><td class="muted">{fmt_date(d["depose_at"])}</td></tr>
{"<tr><th>Décision</th><td>" + esc(d["decision"] or "") + " le " + fmt_date(d["decision_at"]) + (" — motif : " + esc(d["motif"] or "") if d["motif"] else "") + "</td></tr>" if d["decision_at"] else ""}
</table></div>
{action_html}
{cert_html}{fac_html}
<div class="card"><h2>Pièces justificatives</h2>
<table><tr><th>Fichier</th><th>Taille</th><th>Déposé par</th><th>Date</th><th></th></tr>{pieces_rows}</table>
{"<p class='muted'>Aucune pièce.</p>" if not pieces_rows else ""}
<form method="post" action="/dossiers/{{d_id}}/pieces" enctype="multipart/form-data" style="margin-top:10px" class="row">
{hidden_csrf(csrf)}<input type="file" name="fichier" required style="width:auto">
<button class="btn small" type="submit">Téléverser</button></form></div>
<div class="card"><h2>Échanges</h2>{com_rows}{"<p class='muted'>Aucun message.</p>" if not com_rows else ""}
<form method="post" action="/dossiers/{d["id"]}/commentaires" style="margin-top:10px">{hidden_csrf(csrf)}
<textarea name="contenu" required placeholder="Votre message..."></textarea>{interne_check}
<div style="margin-top:8px"><button class="btn small" type="submit">Envoyer</button></div></form></div>
<div class="card"><h2>Historique</h2>
<table><tr><th>Date</th><th>Acteur</th><th>Transition</th><th>Commentaire</th></tr>{hist_rows}</table></div>""".replace("{d_id}", str(d["id"]))
    return layout(user, f"Dossier {d['numero']}", body)


def page_certificats(user, certs):
    rows = "".join(
        f'<tr><td><a href="/certificats/{c["id"]}/print">{esc(c["numero"])}</a></td><td><a href="/dossiers/{c["dossier_id"]}">{esc(c["dossier_numero"])}</a></td>'
        f'<td>{esc(c["organisme"] or c["nom"])}</td><td>{esc(c["type_service"])}</td>'
        f'<td>{badge_statut("ok" if c["statut"] == "valide" else "muted")} {esc(c["statut"])}</td>'
        f'<td class="muted">{fmt_date_jour(c["date_delivrance"])}</td><td class="muted">{fmt_date_jour(c["date_expiration"])} ({jours_restants(c["date_expiration"])} j)</td></tr>'
        for c in certs)
    body = f"""
<h1>Registre des certifications OFDTI</h1>
<div class="card"><table><tr><th>Numéro</th><th>Dossier</th><th>Organisme</th><th>Service</th><th>Statut</th><th>Délivrance</th><th>Expiration</th></tr>{rows}</table>
{"<p class='muted'>Aucune certification.</p>" if not rows else ""}</div>
<p><a href="/exports/certifies.csv">Exporter le registre (CSV)</a></p>"""
    return layout(user, "Certificats OFDTI", body)


def page_certificat_print(cert, d, candidat, organisme_nom):
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>Certificat OFDTI {esc(cert["numero"])}</title><style>{CSS}</style></head>
<body><div class="certificat">
<p class="no-print"><a class="btn" href="javascript:window.print()">Imprimer</a> <a class="btn secondary" href="/certificats/{cert['id']}/pdf">Télécharger le PDF signé</a> <a class="btn secondary" href="/certificats/{cert['id']}/verify">Vérifier la signature</a> <a class="btn secondary" href="/certificats">Retour</a></p>
<h1>CERTIFICAT DE CONFORMITÉ OFDTI</h1>
<p class="muted">délivré par LCP — Certification OFDTI</p>
<p>Nous certifions que</p>
<p style="font-size:22px;font-weight:700">{esc(organisme_nom)}</p>
<p>est certifié conforme au référentiel <b>OFDTI</b> pour le service :</p>
<p style="font-size:18px"><b>{esc(d["type_service"])}</b></p>
<div class="num">N° {esc(cert["numero"])}</div>
<table style="margin:0 auto;width:70%"><tr><th>Délivré le</th><td>{fmt_date_jour(cert["date_delivrance"])}</td></tr>
<tr><th>Valable jusqu'au</th><td>{fmt_date_jour(cert["date_expiration"])}</td></tr>
<tr><th>Statut</th><td>{esc(cert["statut"])}</td></tr></table>
<p class="muted" style="margin-top:32px">Document généré automatiquement par le CRM LCP — dossier {esc(d["numero"])}</p>
</div></body></html>"""


def page_factures(user, factures):
    rows = "".join(
        f'<tr><td>{esc(f["numero"])}</td><td><a href="/dossiers/{f["dossier_id"]}">{esc(f["dossier_numero"])}</a></td>'
        f'<td>{esc(f["organisme"] or f["nom"])}</td><td>{f["montant"]:.2f} €</td>'
        f'<td>{badge_statut("danger" if f["statut"] == "en_retard" else ("ok" if f["statut"] == "payee" else "info"))} {esc(f["statut"])}</td>'
        f'<td class="muted">{fmt_date_jour(f["emise_at"])}</td><td class="muted">{fmt_date_jour(f["echeance"])}</td><td class="muted">{f["nb_relances"]}</td></tr>'
        for f in factures)
    body = f"""
<h1>Factures de certification</h1>
<div class="card"><table><tr><th>Numéro</th><th>Dossier</th><th>Organisme</th><th>Montant</th><th>Statut</th><th>Émise le</th><th>Échéance</th><th>Relances</th></tr>{rows}</table>
{"<p class='muted'>Aucune facture.</p>" if not rows else ""}</div>
<p><a href="/exports/factures.csv">Exporter (CSV)</a></p>"""
    return layout(user, "Factures", body)


def page_notifications(user, notifs, csrf):
    rows = "".join(
        f'<tr><td class="muted">{fmt_date(n["at"])}</td>'
        f'<td>{"<b>" if not n["lu"] else ""}<a href="/notifications/{n["id"]}/lire">{esc(n["titre"])}</a>{"</b>" if not n["lu"] else ""}</td>'
        f'<td>{esc(n["message"])}</td></tr>'
        for n in notifs)
    body = f"""
<h1>Notifications</h1>
<form method="post" action="/notifications/tout_lire">{hidden_csrf(csrf)}<button class="btn small secondary">Tout marquer comme lu</button></form>
<div class="card" style="margin-top:10px"><table><tr><th>Date</th><th>Titre</th><th>Message</th></tr>{rows}</table>
{"<p class='muted'>Aucune notification.</p>" if not rows else ""}</div>"""
    return layout(user, "Notifications", body)


def page_admin_users(user, users, csrf, msg=None):
    flash = f'<div class="flash">{esc(msg)}</div>' if msg else ""
    rows = "".join(
        f'<tr><td>{esc(u["email"])}</td><td>{esc(u["nom"])}</td><td>{esc(u["role"])}</td><td>{esc(u["organisme"] or "")}</td>'
        f'<td>{badge_statut("ok" if u["actif"] else "danger")} {"actif" if u["actif"] else "inactif"}</td>'
        f'<td><form method="post" action="/admin/users/{u["id"]}/toggle" style="display:inline">{hidden_csrf(csrf)}<button class="btn small secondary">{"Désactiver" if u["actif"] else "Activer"}</button></form></td></tr>'
        for u in users)
    body = f"""
<h1>Administration</h1>
<div class="row" style="margin-bottom:14px">
<a class="btn secondary small" href="/admin/users">Utilisateurs</a>
<a class="btn secondary small" href="/admin/parametres">Paramètres</a>
<a class="btn secondary small" href="/admin/outbox">Boîte d'envoi (e-mails simulés)</a>
<a class="btn secondary small" href="/admin/audit">Journal d'audit</a>
</div>
{flash}
<div class="card"><h2>Créer un utilisateur</h2>
<form method="post" action="/admin/users" class="grid" style="grid-template-columns:repeat(auto-fit,minmax(200px,1fr))">
{hidden_csrf(csrf)}
<div><label>Email</label><input type="email" name="email" required></div>
<div><label>Mot de passe</label><input type="password" name="password" required></div>
<div><label>Nom</label><input type="text" name="nom" required></div>
<div><label>Rôle</label><select name="role"><option value="candidat">candidat</option><option value="auditeur">auditeur</option><option value="admin">admin</option></select></div>
<div><label>Organisme</label><input type="text" name="organisme"></div>
<div><label>SIRET</label><input type="text" name="siret"></div>
<div style="align-self:end"><button class="btn" type="submit">Créer</button></div></form></div>
<div class="card"><h2>Utilisateurs</h2><table><tr><th>Email</th><th>Nom</th><th>Rôle</th><th>Organisme</th><th>État</th><th></th></tr>{rows}</table></div>"""
    return layout(user, "Administration", body)


def page_admin_params(user, params, csrf, msg=None):
    flash = f'<div class="flash">{esc(msg)}</div>' if msg else ""
    fields = "".join(
        f'<div><label>{esc(cle)}</label><input type="text" name="{esc(cle)}" value="{esc(v)}"></div>'
        for cle, v in params.items())
    body = f"""
<h1>Paramètres de la certification OFDTI</h1>
<div class="row" style="margin-bottom:14px">
<a class="btn secondary small" href="/admin/users">Utilisateurs</a>
<a class="btn secondary small" href="/admin/parametres">Paramètres</a>
<a class="btn secondary small" href="/admin/outbox">Boîte d'envoi</a>
<a class="btn secondary small" href="/admin/audit">Journal d'audit</a>
</div>
{flash}
<div class="card"><form method="post" action="/admin/parametres" class="grid" style="grid-template-columns:repeat(auto-fit,minmax(220px,1fr))">
{hidden_csrf(csrf)}{fields}
<div style="align-self:end"><button class="btn" type="submit">Enregistrer</button></div></form></div>
<div class="card"><h2>Automatisations</h2>
<p class="muted">Les automatisations tournent toutes les 60 secondes : passage des factures en retard, relances quotidiennes, alertes d'expiration des certificats (seuils configurables), alertes de dossiers en instruction trop longtemps.</p>
<form method="post" action="/admin/automations/run">{hidden_csrf(csrf)}<button class="btn secondary">Exécuter maintenant</button></form></div>"""
    return layout(user, "Paramètres", body)


def page_admin_outbox(user, emails):
    rows = "".join(
        f'<tr><td class="muted">{fmt_date(e["at"])}</td><td>{esc(e["destinataire"])}</td><td>{esc(e["sujet"])}</td><td>{esc(e["contenu"][:120])}…</td>'
        f'<td>{badge_statut("ok" if e["envoye"] else "info")} {"envoyé (SMTP)" if e["envoye"] else "simulé"}</td></tr>'
        for e in emails)
    body = f"""
<h1>Boîte d'envoi</h1>
<div class="row" style="margin-bottom:14px">
<a class="btn secondary small" href="/admin/users">Utilisateurs</a>
<a class="btn secondary small" href="/admin/parametres">Paramètres</a>
<a class="btn secondary small" href="/admin/outbox">Boîte d'envoi</a>
<a class="btn secondary small" href="/admin/audit">Journal d'audit</a>
</div>
<div class="card"><p class="muted">En production, ces e-mails partiraient par SMTP. Ici ils sont journalisés (table <code>outbox</code>).</p>
<table><tr><th>Date</th><th>Destinataire</th><th>Sujet</th><th>Aperçu</th><th>Envoi</th></tr>{rows}</table>
{"<p class='muted'>Aucun e-mail.</p>" if not rows else ""}</div>
<p class="muted">Sans configuration SMTP (variables SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM — voir deploy/.env.example), les e-mails sont simulés et journalisés ici. Avec SMTP configuré, ils sont réellement envoyés et marqués « envoyé (SMTP) ».</p>"""
    return layout(user, "Boîte d'envoi", body)


def page_admin_audit(user, logs, users):
    rows = "".join(
        f'<tr><td class="muted">{fmt_date(l["at"])}</td><td>{esc(users.get(l["user_id"], "système"))}</td>'
        f'<td>{esc(l["action"])}</td><td>{esc(l["entite"])}{" #" + str(l["entite_id"]) if l["entite_id"] else ""}</td><td>{esc(l["detail"] or "")}</td></tr>'
        for l in logs)
    body = f"""
<h1>Journal d'audit</h1>
<div class="row" style="margin-bottom:14px">
<a class="btn secondary small" href="/admin/users">Utilisateurs</a>
<a class="btn secondary small" href="/admin/parametres">Paramètres</a>
<a class="btn secondary small" href="/admin/outbox">Boîte d'envoi</a>
<a class="btn secondary small" href="/admin/audit">Journal d'audit</a>
</div>
<div class="card"><table><tr><th>Date</th><th>Acteur</th><th>Action</th><th>Entité</th><th>Détail</th></tr>{rows}</table></div>"""
    return layout(user, "Journal d'audit", body)


def page_stats(user, kpis, charts):
    cards = "".join(f'<div class="stat"><div class="n">{esc(v[0])}</div><div class="l">{esc(v[1])}</div></div>' for v in kpis)
    body = f"""
<h1>Statistiques</h1>
<div class="grid">{cards}</div>
<div class="card"><h2>Dossiers par statut</h2>{charts["statuts"]}</div>
<div class="card"><h2>Dossiers créés par mois (12 derniers mois)</h2>{charts["mensuel"]}</div>
<div class="card"><h2>Factures par statut</h2>{charts["factures"]}</div>"""
    return layout(user, "Statistiques", body)


def page_verify(user, cert, ok, details):
    badge = badge_statut("ok" if ok else "danger")
    rows = "".join(f'<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>' for k, v in details)
    body = f"""
<h1>Vérification de signature — {esc(cert["numero"])}</h1>
<div class="card"><p>Résultat : {badge} {"signature valide" if ok else "SIGNATURE INVALIDE"}</p>
<table>{rows}</table></div>
<p><a href="/certificats/{cert["id"]}/pdf">Télécharger le PDF signé</a> · <a href="/api/pubkey">Clé publique</a></p>"""
    return layout(user, f"Vérification {cert['numero']}", body)


def page_erreur(user, message, status="Erreur"):
    return layout(user, status, f'<div class="card"><div class="erreur">{esc(message)}</div><p><a href="/">Retour au tableau de bord</a></p></div>')
