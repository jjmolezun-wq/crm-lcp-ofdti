import json
import threading
from datetime import timedelta

import db


def run_automations(conn):
    result = {"factures_en_retard": 0, "relances": 0, "alertes_expiration": 0, "alertes_instruction": 0, "certificats_expires": 0}
    now = db.utcnow()
    today = now.date()

    seuils = json.loads(db.get_param(conn, "seuils_relance_certificat_jours", "[90, 30, 7]"))
    delai_instruction = int(db.get_param(conn, "delai_alerte_instruction_jours", "30"))

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

    limite = db.iso(now - timedelta(days=delai_instruction))
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
