"""CSV-Export der Leistungen (z. B. für KWP / andere ERP-Programme)."""
import csv

from .calc import berechne_leistung
from .util import zahl_kurz

KOPF = ["Leistungsnr", "Ordner", "Kurztext", "Beschreibung", "Einheit", "EP_EK", "EP_VK", "Material_EK",
        "Material_VK", "Lohn", "Zeit_Stunden", "Zeit_Minuten", "Zeit_hhmm", "Durchschnitt_Stundensatz",
        "Anteil_Lohn_Prozent", "Stichtag"]
KOPF_BAUSTEINE = ["Leistungsnr", "Typ", "Bezeichnung", "Artikelnr", "Menge_je_Einheit", "Einheit", "Mengenaufschlag_Prozent",
                  "Preisaufschlag_Prozent", "EK_je_Einheit", "VK_je_Einheit", "Zeit_Minuten", "Stundensatz", "Summe_VK"]


def _z(x, dezimal, nd=2):
    s = f"{x:.{nd}f}"
    return s.replace(".", ",") if dezimal == "," else s


def export_leistungen(db, lids, pfad, trenner=";", kodierung="cp1252", dezimal=",", mit_bausteinen=True, stichtag=None):
    """Schreibt <pfad> (Leistungen) und optional <pfad>_Bausteine.csv. -> Liste der geschriebenen Dateien."""
    zeilen, bausteine = [], []
    for lid in lids:
        r = berechne_leistung(db, lid, 1.0, stichtag)
        l = r["leistung"]
        h = r["stunden"]
        minuten = int(round(h * 60))
        ordner = db.ordner_pfad("leistung", l["ordner_id"]) if l["ordner_id"] else ""
        ep = r["summe"]
        zeilen.append([l["nr"], ordner, l["bezeichnung"], (l["beschreibung"] or "").replace("\r", " ").replace("\n", " "),
                       l["einheit"], _z(r["summe_ek"], dezimal), _z(ep, dezimal), _z(r["material_ek"], dezimal),
                       _z(r["material_vk"], dezimal), _z(r["lohn_summe"], dezimal), _z(h, dezimal, 4), minuten,
                       f"{minuten // 60:02d}:{minuten % 60:02d}", _z(r["lohn_summe"] / h if h else 0, dezimal),
                       _z(r["lohn_summe"] / ep * 100 if ep else 0, dezimal, 1), stichtag or ""])
        for m in r["material"]:
            bausteine.append([l["nr"], "Material", m["bezeichnung"], m["artikel_nr"], zahl_kurz(m["menge_je_einheit"]).replace(",", dezimal),
                              m["einheit"], _z(m["verschnitt"], dezimal, 1), _z(m["aufschlag"], dezimal, 1),
                              _z(m["ek"], dezimal, 4), _z(m["vk"], dezimal, 4), "", "", _z(m["summe"], dezimal)])
        for o in r["lohn"]:
            bausteine.append([l["nr"], "Lohn", o["bezeichnung"], "", zahl_kurz(o["menge"]).replace(",", dezimal), o["einheit"], "", "",
                              "", "", int(round(o["stunden"] * 60)), _z(o["satz"], dezimal), _z(o["summe"], dezimal)])
    def schreibe(p, kopf, rows):
        with open(p, "w", newline="", encoding=kodierung, errors="replace") as f:
            w = csv.writer(f, delimiter=trenner)
            w.writerow(kopf)
            w.writerows(rows)
    dateien = [pfad]
    schreibe(pfad, KOPF, zeilen)
    if mit_bausteinen:
        p2 = pfad[:-4] + "_Bausteine.csv" if pfad.lower().endswith(".csv") else pfad + "_Bausteine.csv"
        schreibe(p2, KOPF_BAUSTEINE, bausteine)
        dateien.append(p2)
    return dateien
