"""
Passwort-Hashing für den Admin-Panel-Login. KOMPLETT getrennt vom normalen
Discord-OAuth-Login der User-Dashboards.

Wichtig: Passwörter werden NIE im Klartext gespeichert oder angezeigt --
auch nicht für andere Admins einsehbar. bcrypt ist ein etablierter,
absichtlich langsamer Hash-Algorithmus speziell für Passwörter (schützt
gegen Brute-Force-Angriffe, falls die Datenbank je kompromittiert würde).
"""
import bcrypt


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Ungültiger/beschädigter Hash -- sicherheitshalber ablehnen statt Fehler werfen.
        return False
