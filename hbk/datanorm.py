"""DATANORM 4.0 (Semikolon-Format): Lesen für den Artikelimport, Schreiben für den Leistungs-Export.

Lesen: Satzart A (Artikelsatz). Preis in Cent (2 Nachkommastellen), Preiseinheit 0/1/2/3 = je 1/10/100/1000.
Die Erkennung der Felder nach dem Kurztext ist bewusst tolerant (Preiskennzeichen, Preiseinheit und Preis sind
die ersten drei reinen Zahlenfelder; die Mengeneinheit das erste Textfeld), damit unterschiedliche Feldreihenfolgen
verschiedener Lieferanten funktionieren.
Schreiben: ANNAHME zum Feldaufbau (Datanorm-4.0-Artikelsatz), noch nicht gegen KWP geprüft.
"""
from datetime import date

from .calc import berechne_leistung

FAKTOR = {"0": 1, "1": 10, "2": 100, "3": 1000}
KOPF = ["Artikelnummer", "Bezeichnung", "Einheit", "Preis", "Preiskennzeichen", "Rabattgruppe", "Warengruppe"]
PREISKZ = {"1": "Brutto (Listenpreis)", "2": "Netto"}


def ist_datanorm(raw):
    """Erkennt Datanorm-Dateien am Aufbau der A-Sätze (A;N;Artikelnr;...)."""
    n = 0
    for zeile in raw.split(b"\n")[:600]:
        z = zeile.strip()
        if z[:1] == b"A" and z[1:2] == b";" and z[2:3] in (b"N", b"A", b"L", b"X") and z[3:4] == b";" and z.count(b";") >= 8:
            n += 1
            if n >= 2:
                return True
    return n >= 1


def dekodieren(raw):
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp850", errors="replace")      # DOS-Zeichensatz, üblich bei Datanorm


def lese_datanorm(pfad):
    with open(pfad, "rb") as fh:
        raw = fh.read()
    zeilen = []
    for line in dekodieren(raw).splitlines():
        f = line.strip().split(";")
        if len(f) < 9 or f[0] != "A" or f[1] in ("L", "X"):          # L/X = Löschsatz
            continue
        nr, kt1, kt2 = f[2].strip(), f[4].strip(), f[5].strip()
        rest = [t.strip() for t in f[6:] if t.strip() != ""]
        zahlen, nach, idx = [], [], None
        for i, t in enumerate(rest):
            if t.isdigit() and len(zahlen) < 3:
                zahlen.append(t)
                if len(zahlen) == 3:
                    idx = i
        if len(zahlen) < 3 or not nr:
            continue
        pkz, pe, preis = zahlen
        me = next((t for t in rest if not t.isdigit()), "")
        nach = list(rest[idx + 1:])
        if me in nach:                      # Mengeneinheit steht bei manchen Lieferanten hinter dem Preis
            nach.remove(me)
        wert = int(preis) / 100 / FAKTOR.get(pe, 1)
        zeilen.append([nr, (kt1 + " " + kt2).strip(), me, f"{wert:.4f}".replace(".", ","), PREISKZ.get(pkz, pkz),
                       nach[0] if len(nach) > 0 else "", nach[1] if len(nach) > 1 else ""])
    if not zeilen:
        raise ValueError("In der Datanorm-Datei wurden keine Artikelsätze (Satzart A) gefunden.")
    return list(KOPF), zeilen


def _t(s, n):
    return (s or "").replace(";", ",").replace("\r", " ").replace("\n", " ").strip()[:n]


def _me(e):
    return _t((e or "").replace("²", "2").replace("³", "3"), 3)


def schreibe_datanorm(db, lids, pfad, stichtag=None, preiskz="2", kodierung="cp850"):
    """Schreibt Leistungen als Datanorm-4.0-Artikelsätze (Preis = Einheitspreis VK netto je Einheit der Leistung)."""
    heute = date.today().strftime("%d%m%y")
    zeilen = [f"V;{heute};001;HBK Leistungen;EUR"]
    for lid in lids:
        r = berechne_leistung(db, lid, 1.0, stichtag)
        l = r["leistung"]
        ordner = db.ordner_pfad("leistung", l["ordner_id"]) if l["ordner_id"] else ""
        kt2 = _t(l["beschreibung"], 40) or _t(ordner, 40)
        cent = int(round(r["summe"] * 100))
        zeilen.append(";".join(["A", "N", _t(l["nr"], 15), "1", _t(l["bezeichnung"], 40), kt2, preiskz, "0", _me(l["einheit"]),
                                str(cent), "", _t(ordner.split(" / ")[0], 10), "0"]))
    with open(pfad, "w", newline="", encoding=kodierung, errors="replace") as f:
        f.write("\r\n".join(zeilen) + "\r\n")
    return [pfad]
