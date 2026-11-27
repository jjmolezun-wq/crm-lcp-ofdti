STATUTS = {
    "brouillon": "Brouillon",
    "depose": "Demande déposée",
    "en_recevabilite": "Revue de recevabilité",
    "recevable": "Recevable",
    "non_recevable": "Non recevable",
    "en_audit": "Audit initial",
    "non_conforme": "Non conforme",
    "certifie": "Certifié OFDTI",
    "en_surveillance": "En surveillance",
    "en_renouvellement": "En renouvellement",
    "suspendu": "Suspendu",
    "retire": "Retiré",
    "refuse": "Refusé",
    "abandonne": "Abandonné",
    "expire": "Expiré",
}

STATUT_CLASS = {
    "brouillon": "muted",
    "depose": "info",
    "en_recevabilite": "warn",
    "recevable": "ok",
    "non_recevable": "danger",
    "en_audit": "warn",
    "non_conforme": "danger",
    "certifie": "ok",
    "en_surveillance": "info",
    "en_renouvellement": "warn",
    "suspendu": "danger",
    "retire": "muted",
    "refuse": "danger",
    "abandonne": "muted",
    "expire": "muted",
}

TRANSITIONS = {
    "brouillon": ["depose"],
    "depose": ["en_recevabilite", "brouillon"],
    "en_recevabilite": ["recevable", "non_recevable", "depose"],
    "recevable": ["en_audit", "refuse"],
    "non_recevable": ["depose", "refuse", "abandonne"],
    "en_audit": ["certifie", "non_conforme", "refuse"],
    "non_conforme": ["en_audit", "en_recevabilite", "refuse"],
    "certifie": ["en_surveillance", "suspendu", "retire"],
    "en_surveillance": ["certifie", "en_renouvellement", "suspendu", "retire"],
    "en_renouvellement": ["certifie", "refuse", "suspendu"],
    "suspendu": ["certifie", "retire"],
    "refuse": [],
    "retire": [],
    "abandonne": [],
    "expire": [],
}

STATUTS_AUDITABLES = {"en_audit", "non_conforme", "en_surveillance", "en_renouvellement"}
CIBLES_AUDITEUR = {"en_audit", "certifie", "non_conforme", "refuse", "en_surveillance", "en_renouvellement"}


def transitions_possibles(user, dossier):
    if not user or not dossier:
        return []
    statut = dossier["statut"]
    cibles = TRANSITIONS.get(statut, [])
    role = user["role"]
    out = []
    for cible in cibles:
        if role == "candidat":
            if dossier["candidat_id"] == user["id"] and statut == "brouillon" and cible == "depose":
                out.append(cible)
        elif role == "auditeur":
            if statut in STATUTS_AUDITABLES and cible in CIBLES_AUDITEUR:
                out.append(cible)
        elif role == "admin":
            out.append(cible)
    return out


def peut_voir_dossier(user, dossier):
    if user["role"] in ("admin", "auditeur"):
        return True
    return dossier["candidat_id"] == user["id"]
