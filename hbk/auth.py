"""Programm-Passwort (PBKDF2-HMAC-SHA256, nur Hash wird gespeichert)."""
import hashlib
import hmac
import os

ITER = 200_000


def _hash(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, ITER).hex()


def has_password(db):
    return bool(db.one("SELECT value FROM settings WHERE key='pw_hash'"))


def set_password(db, pw):
    if len(pw) < 4:
        raise ValueError("Das Passwort muss mindestens 4 Zeichen lang sein.")
    salt = os.urandom(16)
    db.set_setting("pw_salt", salt.hex())
    db.set_setting("pw_hash", _hash(pw, salt))


def check_password(db, pw):
    h = db.one("SELECT value FROM settings WHERE key='pw_hash'")
    s = db.one("SELECT value FROM settings WHERE key='pw_salt'")
    if not h or not s:
        return False
    return hmac.compare_digest(h["value"], _hash(pw, bytes.fromhex(s["value"])))


# --- Masterkey zum Zurücksetzen des Passworts -------------------------------------------
# Der Masterkey ist im Programm hinterlegt (nur als Hash). Er schützt vor zufälligem Zugriff, nicht vor jemandem,
# der das Programm selbst untersucht – die Datenbankdatei ist ohnehin nicht verschlüsselt.
_MASTER_SALT = b"HBK-masterkey-v1"
_MASTER_HASH = "214ec13a83226148e54800f1a524089b17f3aeddb4acfaa1417a4e631d92e90e"


def check_master(key):
    return hmac.compare_digest(_hash((key or "").strip().lower(), _MASTER_SALT), _MASTER_HASH)


def reset_password(db, masterkey, neues_passwort):
    if not check_master(masterkey):
        raise ValueError("Der Masterkey ist falsch.")
    set_password(db, neues_passwort)
