"""Hilfsfunktionen: Datum, Zahlen, Formatierung (deutsches Format)."""
from datetime import date, datetime


def today_iso():
    return date.today().isoformat()


def now_iso():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def to_iso(text):
    """TT.MM.JJJJ oder JJJJ-MM-TT -> JJJJ-MM-TT. Leer -> ''."""
    t = (text or "").strip()
    if not t:
        return ""
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y"):
        try:
            return datetime.strptime(t, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Ungültiges Datum: '{text}' (erwartet TT.MM.JJJJ)")


def to_de(iso):
    if not iso:
        return ""
    try:
        return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return iso


def to_de_ts(ts):
    if not ts:
        return ""
    try:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return ts


def parse_zahl(s):
    """'1.234,5' / '1234,5' / '1234.5' -> float."""
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s).strip().replace(" ", "")
    if not t:
        raise ValueError("Zahl fehlt")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    return float(t)


def parse_zahl_opt(s):
    return None if str(s or "").strip() == "" else parse_zahl(s)


def zahl(x, nd=2):
    if x is None:
        return ""
    s = f"{x:,.{nd}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def zahl_kurz(x, maxnd=4):
    """Zahl ohne überflüssige Nachkommastellen (Minimum 0, Maximum maxnd)."""
    s = zahl(x, maxnd)
    if "," in s:
        s = s.rstrip("0").rstrip(",")
    return s


def eur(x):
    return f"{zahl(x, 2)} €"


def validate_name(name):
    n = (name or "").strip().replace(" ", "_")
    if not n or not n.isidentifier():
        raise ValueError(
            "Parametername ungültig. Erlaubt: Buchstaben, Ziffern, Unterstrich; "
            "nicht mit einer Ziffer beginnen (z. B. Dachfläche, Wandfläche_Nord)."
        )
    return n


# --- v2: Zeit, Prozent, Preisformat -------------------------------------------
import re as _re


def fmt_zeit(h):
    """Dezimalstunden -> '11 h 30 min'."""
    if h is None:
        return ""
    total = int(round(abs(h) * 60))
    return f"{'-' if h < 0 else ''}{total // 60:02d} h {total % 60:02d} min"


def parse_zeit(text):
    """'01 h 30 min' | '1:30' | '1h30' | '90 min' | '1,5' (Dezimalstunden) -> Stunden (float)."""
    t = str(text).strip().lower()
    if not t:
        raise ValueError("Zeit fehlt")
    m = _re.fullmatch(r"(\d+)\s*:\s*(\d{1,2})", t)
    if m:
        return int(m[1]) + int(m[2]) / 60
    m = _re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*h\s*(?:(\d+(?:[.,]\d+)?)\s*(?:min|m)?)?", t)
    if m:
        return parse_zahl(m[1]) + (parse_zahl(m[2]) / 60 if m[2] else 0)
    m = _re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(?:min|m)", t)
    if m:
        return parse_zahl(m[1]) / 60
    return parse_zahl(t)


def parse_pct(text):
    """'8', '8 %', '8,5%' -> 8.0 ; leer -> None."""
    t = str(text or "").replace("%", "").strip()
    return None if t == "" else parse_zahl(t)


def pct(x):
    return "" if x is None else f"{zahl_kurz(x)} %"


def preis_fmt(x, maxnd=4):
    """Preis mit mind. 2, höchstens 4 Nachkommastellen (wie 1,3824)."""
    s = zahl(x, maxnd)
    if "," in s:
        head, tail = s.split(",")
        tail = tail.rstrip("0")
        s = head + "," + tail.ljust(2, "0")
    return s


def parse_preis_text(text):
    """Tolerant für Importe: '1.234,56 €', '12,5', '12.50 EUR' -> float."""
    t = _re.sub(r"[^\d,.\-]", "", str(text or ""))
    if not t or t in "-.,":
        raise ValueError("kein Preis")
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    return float(t)
