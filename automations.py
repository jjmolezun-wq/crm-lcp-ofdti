import json
import threading
from datetime import timedelta

import db


def run_automations(conn):
    result = {"factures_en_retard": 0, "relances": 0, "alertes_expiration": 0, "alertes_instruction": 0,
              "certificats_expires": 0, "renouvellements": 0, "recevabilite_hors_delai": 0,
              "decision_hors_delai": 0, "abandons": 0}
    now = db.utcnow()
    today = now.date()

    seuils = json.loads(db.get_param(conn, "seuils_relance_certificat_jours", "[360, 90, 30, 7]"))
    delai_instruction = int(db.get_param(conn, "delai_alerte_instruction_jours", "30"))
    seuil_renou = int(db.get_param(conn, "seuil_renouvellement_jours", "360"))
    delai_recev = int(db.get_param(conn, "delai_recevabilite_jours", "15"))
    delai_dec = int(db.get_param(conn, "delai_decision_mois", "9")) * 30
    delai_compl = int(db.get_param(conn, "delai_complement_mois", "4")) * 30

    factures = conn.execute(
        "SELECT f.*, d.numero AS dossier_numero, d.candidat_id, u.email AS candidat_email, u.nom AS candidat_nom "
        "FROM factures f JOIN dossiers d ON d.id = f.dossier_id JOIN users u ON u.id = d.candidat_id "
        "WHERE f.statut IN ('emise', 'en_retard')"
    ).fetchall()
    for f in factures:
        echeance = db.parse(f["echeance"])
        if echeance < now and f["statut"] == "emise":
            conn.execute("UPDATE factures SET statut = 'en_retard' WHERE id = ?", (f["id"],))
            result["factures_en_retard"] += 1
            db.notify(conn, f["candidat_id"], "facture_retard",
                      f"Facture {f['numero']} en retard",
                      f"La facture {f['numero']} ({f['montant']:.2f} €) pour le dossier {f['dossier_numero']} est en retard de paiement.",
                      lien=f"/dossiers/{f['dossier_id']}", cle=f"retard:{f['id']}")
            db.notify_role(conn, "admin", "facture_retard",
                           f"Facture {f['numero']} en retard",
                           f"Le candidat {f['candidat_nom']} ({f['candidat_email']}) n'a pas payé la facture {f['numero']} du dossier {f['dossier_numero']}.",
                           lien=f"/dossiers/{f['dossier_id']}", cle=f"retard:{f['id']}")
            db.send_email(conn, f["candidat_email"],
                          f"[LCP] Relance — facture {f['numero']} en retard",
                          f"Bonjour,\n\nLa facture {f['numero']} ({f['montant']:.2f} €), échéance du {f['echeance'][:10]}, est en retard de paiement.\n\nMerci de régulariser dans les meilleurs délais.\n\nLCP — Certification OFDTI",
                          dossier_id=f["dossier_id"])
        if f["statut"] == "en_retard":
            derniere = db.parse(f["derniere_relance"]) if f["derniere_relance"] else None
            if derniere is None or derniere.date() < today - timedelta(days=1):
                conn.execute(
                    "UPDATE factures SET nb_relances = nb_relances + 1, derniere_relance = ? WHERE id = ?",
                    (db.iso(now), f["id"]),
                )
                result["relances"] += 1
                db.notify(conn, f["candidat_id"], "facture_relance",
                          f"Relance n°{f['nb_relances'] + 1} — facture {f['numero']}",
                          f"Rappel : la facture {f['numero']} ({f['montant']:.2f} €) du dossier {f['dossier_numero']} reste impayée.",
                          lien=f"/dossiers/{f['dossier_id']}", cle=f"relance:{f['id']}:{f['nb_relances'] + 1}")
                db.send_email(conn, f["candidat_email"],
                              f"[LCP] Relance n°{f['nb_relances'] + 1} — facture {f['numero']}",
                              f"Bonjour,\n\nNous vous rappelons que la facture {f['numero']} ({f['montant']:.2f} €) est toujours impayée.\n\nLCP — Certification OFDTI",
                              dossier_id=f["dossier_id"])

    certs = conn.execute(
        "SELECT c.*, d.numero AS dossier_numero, d.candidat_id, u.email AS candidat_email, u.nom AS candidat_nom "
        "FROM certificats c JOIN dossiers d ON d.id = c.dossier_id JOIN users u ON u.id = d.candidat_id "
        "WHERE c.statut = 'valide'"
    ).fetchall()
    for c in certs:
        expiration = db.parse(c["date_expiration"])
        jours_restants = (expiration - now).days
        if expiration < now:
            conn.execute("UPDATE certificats SET statut = 'expire' WHERE id = ?", (c["id"],))
            conn.execute("UPDATE dossiers SET statut = 'expire' WHERE id = ?", (c["dossier_id"],))
            result["certificats_expires"] += 1
            db.notify(conn, c["candidat_id"], "cert_expire",
                      f"Certificat {c['numero']} expiré",
                      f"Votre certification OFDTI {c['numero']} a expiré le {c['date_expiration'][:10]}.",
                      lien=f"/certificats/{c['id']}/print", cle=f"expire:{c['id']}")
            continue
        for seuil in seuils:
            if 0 <= jours_restants <= seuil:
                db.notify(conn, c["candidat_id"], "cert_expiration",
                          f"Certificat {c['numero']} — expiration dans {jours_restants} jour(s)",
                          f"Votre certification OFDTI {c['numero']} expire le {c['date_expiration'][:10]} (dans {jours_restants} jour(s)). Pensez à déposer un dossier de renouvellement.",
                          lien=f"/certificats/{c['id']}/print", cle=f"cert:{c['id']}:exp:{seuil}")
                db.notify_role(conn, "admin", "cert_expiration",
                               f"Certificat {c['numero']} expire dans {jours_restants} jour(s)",
                               f"Le certificat OFDTI {c['numero']} ({c['candidat_nom']}) expire le {c['date_expiration'][:10]}.",
                               lien=f"/certificats/{c['id']}/print", cle=f"cert:{c['id']}:exp:{seuil}")
                result["alertes_expiration"] += 1
                db.send_email(conn, c["candidat_email"],
                              f"[LCP] Votre certification OFDTI {c['numero']} expire le {c['date_expiration'][:10]}",
                              f"Bonjour,\n\nVotre certification OFDTI {c['numero']} expire le {c['date_expiration'][:10]} (dans {jours_restants} jour(s)).\nDéposez un dossier de renouvellement depuis votre CRM LCP.\n\nLCP — Certification OFDTI",
                              dossier_id=c["dossier_id"])
                break
        if 0 <= jours_restants <= seuil_renou:
            existe = conn.execute("SELECT id FROM dossiers WHERE renouvellement_de = ?", (c["id"],)).fetchone()
            if not existe:
                numero = db.next_numero(conn, "DOS", "dossiers", "numero")
                now_s = db.now()
                cur = conn.execute(
                    "INSERT INTO dossiers(numero, candidat_id, type_service, description, statut, renouvellement_de, created_at, updated_at) "
                    "VALUES (?,?,?,?, 'brouillon', ?,?,?)",
                    (numero, c["candidat_id"], f"Renouvellement certification {c['numero']}",
                     f"Dossier de renouvellement automatique de la certification OFDTI {c['numero']} (expire le {c['date_expiration'][:10]}).",
                     c["id"], now_s, now_s),
                )
                did = cur.lastrowid
                admin_sys = conn.execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()
                conn.execute(
                    "INSERT INTO historique(dossier_id, ancien, nouveau, acteur_id, commentaire, at) VALUES (?,?,?,?,?,?)",
                    (did, None, "brouillon", admin_sys["id"] if admin_sys else c["candidat_id"],
                     f"Renouvellement automatique de {c['numero']}", now_s),
                )
                db.notify(conn, c["candidat_id"], "renouvellement",
                          f"Renouvellement de {c['numero']} à préparer",
                          f"Votre certification OFDTI {c['numero']} expire le {c['date_expiration'][:10]}. Un dossier de renouvellement {numero} a été créé automatiquement en brouillon : complétez-le et déposez-le.",
                          lien=f"/dossiers/{did}", cle=f"renou:{c['id']}")
                db.send_email(conn, c["candidat_email"],
                              f"[LCP] Renouvellement de votre certification OFDTI {c['numero']}",
                              f"Bonjour,\n\nVotre certification OFDTI {c['numero']} expire le {c['date_expiration'][:10]}.\nUn dossier de renouvellement {numero} a été créé automatiquement dans votre CRM LCP : déposez-le pour renouveler.\n\nLCP — Certification OFDTI",
                              dossier_id=did)
                result["renouvellements"] += 1

    limite = db.iso(now - timedelta(days=delai_instruction))
    dossiers = conn.execute(
        "SELECT d.*, u.nom AS candidat_nom, u.organisme FROM dossiers d JOIN users u ON u.id = d.candidat_id "
        "WHERE d.statut IN ('depose', 'en_recevabilite') AND d.updated_at < ?",
        (db.iso(now - timedelta(days=delai_recev)),),
    ).fetchall()
    for d in dossiers:
        db.notify_role(conn, "admin", "recevabilite_hors_delai",
                       f"Recevabilité hors délai ({delai_recev} j) — {d['numero']}",
                       f"La demande {d['numero']} ({d['organisme'] or d['candidat_nom']}) est en attente de revue de recevabilité depuis le {d['updated_at'][:10]} (délai réglementaire : {delai_recev} jours).",
                       lien=f"/dossiers/{d['id']}", cle=f"recev:{d['id']}:{delai_recev}")
        result["recevabilite_hors_delai"] += 1

    dossiers = conn.execute(
        "SELECT d.*, u.nom AS candidat_nom, u.organisme FROM dossiers d JOIN users u ON u.id = d.candidat_id "
        "WHERE d.statut IN ('recevable', 'en_audit', 'non_conforme') AND d.updated_at < ?",
        (db.iso(now - timedelta(days=delai_dec)),),
    ).fetchall()
    for d in dossiers:
        db.notify_role(conn, "admin", "decision_hors_delai",
                       f"Décision hors délai ({delai_dec // 30} mois) — {d['numero']}",
                       f"Le dossier {d['numero']} ({d['organisme'] or d['candidat_nom']}) attend une décision depuis le {d['updated_at'][:10]} (délai réglementaire : {delai_dec // 30} mois après recevabilité).",
                       lien=f"/dossiers/{d['id']}", cle=f"dec:{d['id']}:{delai_dec // 30}")
        result["decision_hors_delai"] += 1

    dossiers = conn.execute(
        "SELECT d.*, u.nom AS candidat_nom, u.organisme, u.email AS candidat_email FROM dossiers d JOIN users u ON u.id = d.candidat_id "
        "WHERE d.statut = 'non_recevable' AND d.updated_at < ?",
        (db.iso(now - timedelta(days=delai_compl)),),
    ).fetchall()
    for d in dossiers:
        conn.execute("UPDATE dossiers SET statut = 'abandonne', updated_at = ? WHERE id = ?", (db.iso(now), d["id"]))
        admin_sys = conn.execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()
        conn.execute(
            "INSERT INTO historique(dossier_id, ancien, nouveau, acteur_id, commentaire, at) VALUES (?,?,?,?,?,?)",
            (d["id"], "non_recevable", "abandonne", admin_sys["id"] if admin_sys else d["candidat_id"],
             f"Abandon après {delai_compl // 30} mois sans pièces complémentaires (procédure V016)", db.iso(now)),
        )
        db.notify(conn, d["candidat_id"], "abandon", f"Dossier {d['numero']} abandonné",
                  f"Faute de pièces complémentaires dans les {delai_compl // 30} mois, la procédure de certification {d['numero']} est abandonnée (conformément à la procédure de certification).",
                  lien=f"/dossiers/{d['id']}", cle=f"abandon:{d['id']}")
        db.send_email(conn, d["candidat_email"], f"[LCP] Abandon de la procédure — {d['numero']}",
                      f"Bonjour,\n\nSans réception des pièces complémentaires dans les {delai_compl // 30} mois, la procédure de certification {d['numero']} est abandonnée et le dossier détruit.\n\nLCP — Certification OFDTI",
                      dossier_id=d["id"])
        result["abandons"] += 1

    dossiers = conn.execute(
        "SELECT d.*, u.nom AS candidat_nom, u.organisme FROM dossiers d JOIN users u ON u.id = d.candidat_id "
        "WHERE d.statut = 'en_instruction' AND d.updated_at < ?",
        (limite,),
    ).fetchall()
    for d in dossiers:
        db.notify_role(conn, "auditeur", "dossier_attente",
                       f"Dossier {d['numero']} en instruction depuis plus de {delai_instruction} jours",
                       f"Le dossier {d['numero']} ({d['organisme'] or d['candidat_nom']}) attend une instruction depuis le {d['updated_at'][:10]}.",
                       lien=f"/dossiers/{d['id']}", cle=f"instr:{d['id']}:{delai_instruction}")
        db.notify_role(conn, "admin", "dossier_attente",
                       f"Dossier {d['numero']} en instruction depuis plus de {delai_instruction} jours",
                       f"Le dossier {d['numero']} ({d['organisme'] or d['candidat_nom']}) attend une instruction depuis le {d['updated_at'][:10]}.",
                       lien=f"/dossiers/{d['id']}", cle=f"instr:{d['id']}:{delai_instruction}")
        result["alertes_instruction"] += 1

    db.audit(conn, None, "automations", "system", None, json.dumps(result, ensure_ascii=False))
    conn.commit()
    return result


def start_background(intervalle_secondes=60):
    def loop():
        while True:
            conn = None
            try:
                conn = db.connect()
                run_automations(conn)
            except Exception:
                pass
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
            threading.Event().wait(intervalle_secondes)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t
