STATUTS = {
    "brouillon": "Brouillon",
    "depose": "Déposé",
    "en_instruction": "En instruction",
    "en_audit": "En audit",
    "non_conforme": "Non conforme",
    "certifie": "Certifié OFDTI",
    "refuse": "Refusé",
    "suspendu": "Suspendu",
    "retire": "Retiré",
    "expire": "Expiré",
}

STATUT_CLASS = {
    "brouillon": "muted",
    "depose": "info",
    "en_instruction": "warn",
    "en_audit": "warn",
    "non_conforme": "danger",
    "certifie": "ok",
    "refuse": "danger",
    "suspendu": "danger",
    "retire": "muted",
    "expire": "muted",
}

TRANSITIONS = {
    "brouillon": ["depose"],
    "depose": ["en_instruction", "brouillon"],
    "en_instruction": ["en_audit", "non_conforme", "refuse"],
    "en_audit": ["certifie", "non_conforme", "refuse"],
    "non_conforme": ["en_instruction", "refuse"],
    "certifie": ["suspendu", "retire"],
    "suspendu": ["certifie", "retire"],
    "refuse": [],
    "retire": [],
}


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
            if statut in ("en_instruction", "en_audit", "non_conforme") and cible in (
                "en_audit", "certifie", "non_conforme", "refuse", "en_instruction",
            ):
                out.append(cible)
        elif role == "admin":
            out.append(cible)
    return out


def peut_voir_dossier(user, dossier):
    if user["role"] in ("admin", "auditeur"):
        return True
    return dossier["candidat_id"] == user["id"]
