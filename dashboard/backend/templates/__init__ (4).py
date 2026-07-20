"""
Parst einfache Dauer-Angaben wie in vielen Discord-Bots üblich:
    "30s" -> 30 Sekunden
    "10m" -> 10 Minuten
    "2h"  -> 2 Stunden
    "1d"  -> 1 Tag
Kombinierbar nicht nötig für Phase 2 — bewusst einfach gehalten.
"""
import datetime as dt
import re

UNITS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
}

PATTERN = re.compile(r"^(\d+)([smhd])$")


class InvalidDurationError(ValueError):
    pass


def parse_duration(value: str) -> dt.timedelta:
    match = PATTERN.match(value.strip().lower())
    if not match:
        raise InvalidDurationError(
            f"Ungültiges Format: '{value}'. Beispiele: 30s, 10m, 2h, 1d"
        )
    amount, unit = match.groups()
    seconds = int(amount) * UNITS[unit]
    return dt.timedelta(seconds=seconds)
