"""Artikelimport aus Onlineshop-/Lieferantendateien (CSV, Excel)."""
import csv
import io
import os

from . import datanorm
from .util import parse_preis_text, parse_zahl, today_iso

FELDER = [  # (Schlüssel, Anzeige, Pflicht, Spaltenname-Hinweise (klein geschrieben))
    ("nr", "Artikelnummer", False, ["artikelnummer", "artikel-nr", "artikelnr", "art.-nr", "art.nr", "art-nr", "nummer",
                                     "sku", "ean", "bestellnummer", "bestellnr", "materialnummer", "article", "id"]),
    ("bezeichnung", "Bezeichnung", True, ["bezeichnung", "artikelbezeichnung", "kurztext", "name", "titel", "produkt",
                                          "beschreibung", "text", "artikelname", "description"]),
    ("einheit", "Einheit", False, ["einheit", "me", "mengeneinheit", "vpe", "unit"]),
    ("preis", "Preis (netto)", True, ["preis", "nettopreis", "netto", "ek", "ek-preis", "einkaufspreis", "listenpreis",
                                      "preis netto", "price", "vk", "stückpreis"]),
    ("preiseinheit", "Preis je (Preiseinheit, z. B. 100)", False, ["preiseinheit", "preis je", "pe", "preismenge"]),
    ("lieferant", "Lieferant", False, ["lieferant", "hersteller", "marke", "supplier", "brand"]),
    ("kategorie", "Kategorie", False, ["kategorie", "warengruppe", "gruppe", "category", "hauptwarengruppe"]),
    ("gewicht", "Gewicht (kg)", False, ["gewicht", "weight"]),
]


def lese_tabelle(pfad):
    """-> (kopfzeile, zeilen) für .csv/.txt/.xlsx"""
    ext = os.path.splitext(pfad)[1].lower()
    if ext not in (".xlsx", ".xlsm"):
        with open(pfad, "rb") as fh:
            if datanorm.ist_datanorm(fh.read()):
                return datanorm.lese_datanorm(pfad)
    if ext in (".xlsx", ".xlsm"):
        try:
            from openpyxl import load_workbook
        except ImportError:
            raise ValueError("Für Excel-Dateien wird das Paket 'openpyxl' benötigt.")
        ws = load_workbook(pfad, read_only=True, data_only=True).active
        rows = [["" if c is None else str(c) if not isinstance(c, float) else repr(c) for c in r]
                for r in ws.iter_rows(values_only=True)]
    else:
        with open(pfad, "rb") as fh:
            raw = fh.read()
        for enc in ("utf-8-sig", "cp1252"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        try:
            dialect = csv.Sniffer().sniff(text[:5000], delimiters=";,\t|")
        except csv.Error:
            dialect = csv.excel
            dialect.delimiter = ";"
        rows = [r for r in csv.reader(io.StringIO(text), dialect)]
    rows = [r for r in rows if any(c.strip() for c in r)]
    if len(rows) < 2:
        raise ValueError("Die Datei enthält keine Datenzeilen.")
    kopf = [c.strip() or f"Spalte {i + 1}" for i, c in enumerate(rows[0])]
    return kopf, rows[1:]


def vorschlag(kopf):
    """Rät die Spaltenzuordnung anhand der Überschriften -> {feld: spaltenindex}"""
    low = [k.lower() for k in kopf]
    m, benutzt = {}, set()
    for key, _, _, hinweise in FELDER:
        for h in hinweise:
            idx = next((i for i, k in enumerate(low) if k == h and i not in benutzt), None)
            if idx is None:
                idx = next((i for i, k in enumerate(low) if h in k and i not in benutzt and len(h) > 3), None)
            if idx is not None:
                m[key] = idx
                benutzt.add(idx)
                break
    return m


def importiere(db, zeilen, mapping, ordner_id=None, gueltig_ab=None, lieferant="", preisaufschlag=None,
               aktualisieren=True, quelle="Import", rabatt=0.0):
    """mapping: {feld: spaltenindex}. -> {'neu','aktualisiert','unveraendert','fehler':[...]}"""
    if "bezeichnung" not in mapping or "preis" not in mapping:
        raise ValueError("Bitte mindestens Bezeichnung und Preis zuordnen.")
    gueltig_ab = gueltig_ab or today_iso()
    res = {"neu": 0, "aktualisiert": 0, "unveraendert": 0, "fehler": []}

    def zelle(z, key):
        i = mapping.get(key)
        return z[i].strip() if i is not None and i < len(z) else ""
    for n, z in enumerate(zeilen, 2):
        try:
            bez = zelle(z, "bezeichnung")
            if not bez:
                continue
            preis = parse_preis_text(zelle(z, "preis"))
            pe = zelle(z, "preiseinheit")
            if pe:
                preis = preis / (parse_zahl(pe) or 1)
            preis = preis * (1 - (rabatt or 0) / 100)       # z. B. Lieferantenrabatt auf Listenpreise
            nr = zelle(z, "nr")
            vorhanden = db.one("SELECT id FROM artikel WHERE nr=?", (nr,)) if nr else None
            if vorhanden:
                if not aktualisieren:
                    res["unveraendert"] += 1
                    continue
                alt, _ = db.preis_at(vorhanden["id"], gueltig_ab)
                if alt is not None and abs(alt - preis) < 1e-9:
                    res["unveraendert"] += 1
                else:
                    db.preis_setzen(vorhanden["id"], gueltig_ab, round(preis, 4))
                    res["aktualisiert"] += 1
                continue
            g = zelle(z, "gewicht")
            db.artikel_anlegen(nr, bez, zelle(z, "einheit") or "Stk", zelle(z, "lieferant") or lieferant,
                               zelle(z, "kategorie"), parse_zahl(g) if g else None, None, "", ordner_id,
                               preisaufschlag, round(preis, 4), gueltig_ab, 1, quelle)
            res["neu"] += 1
        except Exception as e:  # einzelne Zeile überspringen, Rest weiter importieren
            res["fehler"].append(f"Zeile {n}: {e}")
    return res
