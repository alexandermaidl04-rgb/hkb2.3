"""Parameter aus Eingabeplänen (PDF mit auswählbarem Text) einlesen.

Erkannt werden beschriftete Angaben wie „Dachneigung: 38°“, „Firstlänge 12,00 m“, „Sparrenabstand 80 cm“,
„Dachfläche 135,4 m²“ (Einheiten werden umgerechnet). Alle Funde werden vor der Übernahme angezeigt und lassen sich
ändern; nicht eindeutig beschriftete Maße erscheinen als Kandidaten ohne Zuordnung.
Nicht möglich: gescannte Pläne (nur Bild, keine Texterkennung) und Maße, die nur als Zahl an einer Maßlinie stehen."""
import math
import re
import unicodedata

from .util import parse_zahl, validate_name, zahl_kurz

NUM = r"\d+(?:[.,]\d+)*"
UNIT = r"(°|grad|gr\b|m²|m2|qm|m\b|cm\b|mm\b|%)"
SEP = r"[^\d\n]{0,25}?(?:\n[^\d\n]{0,10})?"
U = r"(?:ü|ue)"
A = r"(?:ä|ae)"
O = r"(?:ö|oe)"

# (Parametername, Einheit, Typ, Beschriftung als Regex) – spezifische Regeln zuerst
REGELN = [
    ("Dachneigung", "°", "winkel", r"dachneigung|dachwinkel|\bDN\b|\bneigung\b"),
    ("Dachfläche", "m²", "flaeche", rf"dachfl{A}che[n]?|dachfl\."),
    ("Grundfläche", "m²", "flaeche", rf"bebaute\s+fl{A}che|(?:geb{A}ude)?grundfl{A}che|grundfl\."),
    ("Wohnfläche", "m²", "flaeche", rf"wohnfl{A}che"),
    ("Nutzfläche", "m²", "flaeche", rf"nutzfl{A}che"),
    ("Firstlänge", "m", "laenge", rf"firstl{A}nge|firstl\."),
    ("Firsthöhe", "m", "laenge", rf"firsth{O}he|\bFH\b"),
    ("Traufhöhe", "m", "laenge", rf"traufh{O}he|\bTH\b"),
    ("Gebäudehöhe", "m", "laenge", rf"geb{A}udeh{O}he"),
    ("Traufenlänge", "m", "laenge", rf"traufenl{A}nge|traufl{A}nge"),
    ("Ortganglänge", "m", "laenge", rf"ortgangl{A}nge"),
    ("Gebäudelänge", "m", "laenge", rf"geb{A}udel{A}nge|hausl{A}nge"),
    ("Gebäudebreite", "m", "laenge", rf"geb{A}udebreite|hausbreite|geb{A}udetiefe"),
    ("Überstand_Ortgang", "m", "laenge", rf"ortgang{U}berstand|dach{U}berstand\s+ortgang|{U}berstand\s+ortgang"),
    ("Überstand_Traufe", "m", "laenge", rf"trauf(?:en)?{U}berstand|dach{U}berstand\s+traufe|{U}berstand\s+traufe"),
    ("Überstand_Traufe", "m", "laenge", rf"dach{U}berstand"),          # unspezifisch: Traufe annehmen, Hinweis anzeigen
    ("Sparrenabstand", "m", "laenge", r"sparrenabstand|sparrenabst\."),
    ("Sparrenlänge", "m", "laenge", rf"sparrenl{A}nge"),
]
CM_WENN_OHNE_EINHEIT = {"Sparrenabstand", "Überstand_Traufe", "Überstand_Ortgang"}


def lese_pdf_text(pfad):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ValueError("Für das Einlesen von PDF-Plänen wird das Paket 'pypdf' benötigt.")
    r = PdfReader(pfad)
    return unicodedata.normalize("NFC", "\n".join((p.extract_text() or "") for p in r.pages))


def _zahl(s):
    return parse_zahl(s.strip())


def _stelle(text, a, b):
    """Ganze Textzeile, in der der Fund steht."""
    start = text.rfind("\n", 0, a) + 1
    ende = text.find("\n", b)
    zeile = re.sub(r"\s+", " ", text[start:len(text) if ende < 0 else ende]).strip()
    return zeile[:110]


def analysiere_text(text):
    """-> Liste von Funden {name, wert, einheit, stelle, use}"""
    text = unicodedata.normalize("NFC", text)
    belegt, funde, schon = [], [], set()
    for name, einheit, typ, label in REGELN:
        rx = re.compile(rf"(?P<label>{label})(?P<sep>{SEP})(?P<num>{NUM})\s*(?P<unit>{UNIT})?", re.I)
        for m in rx.finditer(text):
            ns, ne = m.span("num")
            if any(not (ne <= a or ns >= b) for a, b in belegt):
                continue
            try:
                v = _zahl(m.group("num"))
            except ValueError:
                continue
            u = (m.group("unit") or "").lower()
            note = ""
            if typ == "winkel":
                if u == "%":
                    v, note = math.degrees(math.atan(v / 100)), " (aus % umgerechnet)"
                elif u not in ("°", "grad", "gr") and not (3 <= v <= 75):
                    continue
                if not 1 <= v <= 80:
                    continue
            elif typ == "flaeche":
                if u not in ("m²", "m2", "qm", ""):
                    continue
                note = "" if u else " (ohne Einheit, m² angenommen)"
            else:
                if u in ("m²", "m2", "qm", "°", "grad", "gr", "%"):
                    continue
                if u == "cm":
                    v /= 100
                elif u == "mm":
                    v /= 1000
                elif not u and name in CM_WENN_OHNE_EINHEIT and v > 5:
                    v, note = v / 100, " (ohne Einheit, cm angenommen)"
                if name == "Überstand_Traufe" and "ortgang" not in m.group("label").lower() and re.search(r"dach.?berstand$", m.group("label"), re.I):
                    note += " (allgemeiner Dachüberstand – prüfen, ob auch für den Ortgang)"
            belegt.append((ns, ne))
            funde.append({"name": name, "wert": round(v, 4), "einheit": einheit, "stelle": _stelle(text, m.start(), m.end()) + note,
                          "use": name not in schon})
            schon.add(name)
    # Kandidaten ohne eindeutige Beschriftung
    kand = []
    ctx = r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß .\-/()]{2,40}?"
    muster = [(rf"(?P<ctx>{ctx})[:=\s]*(?P<num>{NUM})\s*(?:m²|m2|qm)", "m²"),
              (rf"(?P<ctx>{ctx})[:=\s]*(?P<num>\d{{1,2}}(?:[.,]\d+)?)\s*(?:°|grad)", "°"),
              (rf"(?P<ctx>{ctx})\s*[:=]\s*(?P<num>{NUM})\s*m\b(?!²)", "m")]
    gesehen = set()
    for pat, einheit in muster:
        for m in re.finditer(pat, text, re.I):
            ns, ne = m.span("num")
            if any(not (ne <= a or ns >= b) for a, b in belegt):
                continue
            try:
                v = _zahl(m.group("num"))
            except ValueError:
                continue
            key = (m.group("ctx").strip().lower(), round(v, 3), einheit)
            if key in gesehen:
                continue
            gesehen.add(key)
            kand.append({"name": "", "wert": round(v, 4), "einheit": einheit, "stelle": _stelle(text, m.start(), m.end()), "use": False})
            if len(kand) >= 40:
                break
    return funde + kand


def analysiere_pdf(pfad):
    text = lese_pdf_text(pfad)
    if len(text.strip()) < 40:
        raise ValueError("Der Plan enthält keinen auswählbaren Text (vermutlich gescannt oder als Bild gespeichert). "
                         "Texterkennung (OCR) ist nicht eingebaut. Bitte die Werte manuell eintragen oder eine PDF "
                         "direkt aus der CAD-Software verwenden.")
    return analysiere_text(text)


def uebernehmen(db, pid, funde, quelle=""):
    """Schreibt die markierten Funde als Parameter ins Projekt (vorhandene werden überschrieben).
    Die Werte sind danach normale Eingabewerte und lassen sich jederzeit manuell ändern. -> (neu, aktualisiert)"""
    neu = akt = 0
    hinweis = f"aus Plan: {quelle}" if quelle else "aus Plan"
    for f in funde:
        if not f.get("use") or not (f.get("name") or "").strip():
            continue
        name = validate_name(f["name"])
        wert = zahl_kurz(float(f["wert"]), 4)
        r = db.one("SELECT id FROM parameter WHERE projekt_id=? AND lower(name)=lower(?)", (pid, name))
        if r:
            db.x("UPDATE parameter SET wert=?, einheit=?, hinweis=? WHERE id=?", (wert, f["einheit"], hinweis, r["id"]))
            akt += 1
        else:
            db.x("INSERT INTO parameter(projekt_id,name,wert,einheit,hinweis) VALUES(?,?,?,?,?)", (pid, name, wert, f["einheit"], hinweis))
            neu += 1
    if neu or akt:
        db.touch(pid)
    return neu, akt
