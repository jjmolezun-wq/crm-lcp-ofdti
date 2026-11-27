import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("CRM_LCP_DB", os.path.join(BASE_DIR, "crm_lcp.db"))

DEFAULT_PARAMS = {
    "nom_organisme": "LCP — Certification OFDTI",
    "duree_certification_mois": "36",
    "montant_frais_euros": "1500.00",
    "delai_paiement_jours": "30",
    "seuils_relance_certificat_jours": "[90, 30, 7]",
    "delai_alerte_instruction_jours": "30",
    "seuil_renouvellement_jours": "90",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    nom TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'auditeur', 'candidat')),
    organisme TEXT,
    siret TEXT,
    adresse TEXT,
    actif INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    csrf TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dossiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero TEXT NOT NULL UNIQUE,
    candidat_id INTEGER NOT NULL REFERENCES users(id),
    type_service TEXT NOT NULL,
    description TEXT NOT NULL,
    statut TEXT NOT NULL DEFAULT 'brouillon',
    motif TEXT,
    decision TEXT,
    decideur_id INTEGER REFERENCES users(id),
    decision_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    depose_at TEXT
);
CREATE TABLE IF NOT EXISTS historique (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dossier_id INTEGER NOT NULL REFERENCES dossiers(id),
    ancien TEXT,
    nouveau TEXT NOT NULL,
    acteur_id INTEGER NOT NULL REFERENCES users(id),
    commentaire TEXT,
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pieces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dossier_id INTEGER NOT NULL REFERENCES dossiers(id),
    nom TEXT NOT NULL,
    content_type TEXT,
    taille INTEGER NOT NULL DEFAULT 0,
    contenu BLOB,
    uploader_id INTEGER NOT NULL REFERENCES users(id),
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS commentaires (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dossier_id INTEGER NOT NULL REFERENCES dossiers(id),
    auteur_id INTEGER NOT NULL REFERENCES users(id),
    interne INTEGER NOT NULL DEFAULT 0,
    contenu TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS certificats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dossier_id INTEGER NOT NULL UNIQUE REFERENCES dossiers(id),
    numero TEXT NOT NULL UNIQUE,
    date_delivrance TEXT NOT NULL,
    date_expiration TEXT NOT NULL,
    statut TEXT NOT NULL DEFAULT 'valide',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS factures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dossier_id INTEGER NOT NULL REFERENCES dossiers(id),
    numero TEXT NOT NULL UNIQUE,
    montant REAL NOT NULL,
    statut TEXT NOT NULL DEFAULT 'emise',
    emise_at TEXT NOT NULL,
    echeance TEXT NOT NULL,
    payee_at TEXT,
    nb_relances INTEGER NOT NULL DEFAULT 0,
    derniere_relance TEXT
);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    type TEXT NOT NULL,
    cle TEXT,
    titre TEXT NOT NULL,
    message TEXT NOT NULL,
    lu INTEGER NOT NULL DEFAULT 0,
    lien TEXT,
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    destinataire TEXT NOT NULL,
    sujet TEXT NOT NULL,
    contenu TEXT NOT NULL,
    dossier_id INTEGER,
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    entite TEXT NOT NULL,
    entite_id INTEGER,
    detail TEXT,
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS parametres (
    cle TEXT PRIMARY KEY,
    valeur TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signatures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    certificat_id INTEGER NOT NULL UNIQUE REFERENCES certificats(id),
    pdf_hash TEXT NOT NULL,
    signature TEXT NOT NULL,
    key_fingerprint TEXT NOT NULL,
    signe_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dossiers_statut ON dossiers(statut);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, lu);
"""


def utcnow():
    return datetime.now(timezone.utc)


def now():
    return iso(utcnow())


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse(ts):
    return datetime.fromisoformat(ts)


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return f"{salt}${digest}"


def verify_password(password, stored):
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return secrets.compare_digest(check, digest)


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def get_param(conn, cle, default=""):
    row = conn.execute("SELECT valeur FROM parametres WHERE cle = ?", (cle,)).fetchone()
    return row["valeur"] if row else default


def set_param(conn, cle, valeur):
    conn.execute(
        "INSERT INTO parametres(cle, valeur) VALUES (?, ?) "
        "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur",
        (cle, str(valeur)),
    )


def next_numero(conn, prefix, table, colonne):
    annee = utcnow().year
    p = f"{prefix}-{annee}-"
    row = conn.execute(
        f"SELECT MAX(CAST(SUBSTR({colonne}, ?) AS INTEGER)) AS m FROM {table} WHERE {colonne} LIKE ?",
        (len(p) + 1, p + "%"),
    ).fetchone()
    n = (row["m"] or 0) + 1
    return f"{p}{n:04d}"


def audit(conn, user_id, action, entite, entite_id=None, detail=None):
    conn.execute(
        "INSERT INTO audit_log(user_id, action, entite, entite_id, detail, at) VALUES (?,?,?,?,?,?)",
        (user_id, action, entite, entite_id, detail, now()),
    )


def notify(conn, user_id, type_, titre, message, lien=None, cle=None):
    if cle:
        row = conn.execute(
            "SELECT id FROM notifications WHERE user_id = ? AND cle = ?", (user_id, cle)
        ).fetchone()
        if row:
            return
    conn.execute(
        "INSERT INTO notifications(user_id, type, cle, titre, message, lu, lien, at) VALUES (?,?,?,?,?,0,?,?)",
        (user_id, type_, cle, titre, message, lien, now()),
    )


def notify_role(conn, role, type_, titre, message, lien=None, cle=None):
    for u in conn.execute("SELECT id FROM users WHERE role = ? AND actif = 1", (role,)).fetchall():
        notify(conn, u["id"], type_, titre, message, lien, cle if cle is None else f"{cle}:{u['id']}")


def send_email(conn, destinataire, sujet, contenu, dossier_id=None):
    import emailer
    envoye = False
    try:
        envoye = emailer.send(destinataire, sujet, contenu)
    except Exception:
        envoye = False
    conn.execute(
        "INSERT INTO outbox(destinataire, sujet, contenu, dossier_id, at, envoye) VALUES (?,?,?,?,?,?)",
        (destinataire, sujet, contenu, dossier_id, now(), 1 if envoye else 0),
    )


def migrate(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(outbox)").fetchall()}
    if "envoye" not in cols:
        conn.execute("ALTER TABLE outbox ADD COLUMN envoye INTEGER NOT NULL DEFAULT 0")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(dossiers)").fetchall()}
    if "renouvellement_de" not in cols:
        conn.execute("ALTER TABLE dossiers ADD COLUMN renouvellement_de INTEGER REFERENCES certificats(id)")


def seed(conn):
    if conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] > 0:
        return
    t = now()
    users = [
        ("admin@lcp.fr", hash_password("admin123"), "Administrateur LCP", "admin", "LCP", "00000000000000", "1 rue de la Certification, 75001 Paris", t),
        ("auditeur@lcp.fr", hash_password("audit123"), "Marie Auditrice", "auditeur", "LCP", "00000000000000", "1 rue de la Certification, 75001 Paris", t),
        ("candidat@exemple.fr", hash_password("demo123"), "Jean Dupont", "candidat", "Société Exemple SARL", "12345678900012", "10 avenue des Services, 69001 Lyon", t),
        ("candidat@novaservices.fr", hash_password("demo123"), "Claire Martin", "candidat", "Nova Services SAS", "98765432100034", "5 rue de l'Innovation, 31000 Toulouse", t),
    ]
    for u in users:
        conn.execute(
            "INSERT INTO users(email, password_hash, nom, role, organisme, siret, adresse, actif, created_at) "
            "VALUES (?,?,?,?,?,?,?,1,?)",
            u,
        )
    for cle, valeur in DEFAULT_PARAMS.items():
        set_param(conn, cle, valeur)

    admin = conn.execute("SELECT id FROM users WHERE email='admin@lcp.fr'").fetchone()["id"]
    auditeur = conn.execute("SELECT id FROM users WHERE email='auditeur@lcp.fr'").fetchone()["id"]
    c1 = conn.execute("SELECT id FROM users WHERE email='candidat@exemple.fr'").fetchone()["id"]
    c2 = conn.execute("SELECT id FROM users WHERE email='candidat@novaservices.fr'").fetchone()["id"]

    from datetime import timedelta
    j20 = iso(utcnow() + timedelta(days=20))
    j2a = iso(utcnow() + timedelta(days=730))
    moins5 = iso(utcnow() - timedelta(days=5))
    plus30 = iso(utcnow() + timedelta(days=30))

    dossiers = [
        ("DOS", c2, "Audit interne", "Demande de certification OFDTI pour nos prestations d'audit interne.", "certifie", t, t, t),
        ("DOS", c1, "Conseil stratégique", "Certification OFDTI du pôle conseil stratégique.", "en_audit", t, t, t),
        ("DOS", c1, "Formation digitale", "Certification OFDTI des formations en ligne.", "depose", t, t, t),
        ("DOS", c2, "Support client", "Certification OFDTI du service support 24/7.", "brouillon", t, t, None),
        ("DOS", c1, "Maintenance applicative", "Certification OFDTI de la maintenance applicative (expirera bientôt, facture en retard).", "certifie", t, t, t),
    ]
    for i, (pref, cid, type_s, desc, statut, created, updated, depose) in enumerate(dossiers, start=1):
        numero = f"DOS-{utcnow().year}-{i:04d}"
        conn.execute(
            "INSERT INTO dossiers(numero, candidat_id, type_service, description, statut, created_at, updated_at, depose_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (numero, cid, type_s, desc, statut, created, updated, depose),
        )
        did = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        conn.execute(
            "INSERT INTO historique(dossier_id, ancien, nouveau, acteur_id, commentaire, at) VALUES (?,?,?,?,?,?)",
            (did, None, statut, cid, "Création du dossier (donnée de démonstration)", t),
        )
        conn.execute(
            "INSERT INTO pieces(dossier_id, nom, content_type, taille, contenu, uploader_id, at) VALUES (?,?,?,?,?,?,?)",
            (did, "presentation.pdf", "application/pdf", 12, b"%PDF-1.4 demo", cid, t),
        )
        conn.execute(
            "INSERT INTO commentaires(dossier_id, auteur_id, interne, contenu, at) VALUES (?,?,?,?,?)",
            (did, cid, 0, "Bonjour, voici notre dossier de candidature OFDTI.", t),
        )
        if statut == "certifie":
            exp = j2a if i == 1 else j20
            exp = j2a if numero.endswith("0001") else j20
            conn.execute(
                "INSERT INTO certificats(dossier_id, numero, date_delivrance, date_expiration, statut, created_at) VALUES (?,?,?,?,?,?)",
                (did, f"OFDTI-{utcnow().year}-{i:04d}", t, exp, "valide", t),
            )
            conn.execute(
                "INSERT INTO factures(dossier_id, numero, montant, statut, emise_at, echeance, payee_at, nb_relances, derniere_relance) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (did, f"FAC-{utcnow().year}-{i:04d}", 1500.0, "payee" if numero.endswith("0001") else "emise",
                 t, plus30 if numero.endswith("0001") else moins5,
                 t if numero.endswith("0001") else None, 0, None),
            )
    conn.execute(
        "INSERT INTO commentaires(dossier_id, auteur_id, interne, contenu, at) SELECT id, ?, 1, 'Dossier conforme, passage en audit.', ? FROM dossiers WHERE numero LIKE '%0002'",
        (auditeur, t),
    )
    db_audit = audit
    db_audit(conn, admin, "seed", "system", None, "Données de démonstration créées")


def init_db(reset=False):
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = connect()
    conn.executescript(SCHEMA)
    migrate(conn)
    seed(conn)
    conn.commit()
    conn.close()
