"""Parameter-Vorlagen (z. B. Dachstuhl): Eingabewerte plus Vorschlagswerte als Formeln.
Alle Vorschläge lassen sich im Projekt durch einen gemessenen Wert überschreiben (Wert einfach neu eintragen)."""
from .calc import eval_parameter

# (Name, Wert/Formel, Einheit, Hinweis)
SATTELDACH = [
    ("Gebäudelänge", "10", "m", "Eingabe: Länge des Hauses (in Firstrichtung)"),
    ("Gebäudebreite", "8", "m", "Eingabe: Breite des Hauses, Traufe zu Traufe ohne Überstand"),
    ("Dachneigung", "35", "°", "Eingabe: Neigung in Grad"),
    ("Überstand_Traufe", "0,5", "m", "Eingabe: Dachüberstand an der Traufe"),
    ("Überstand_Ortgang", "0,5", "m", "Eingabe: Dachüberstand am Ortgang"),
    ("Sparrenabstand", "0,8", "m", "Eingabe: Achsabstand der Sparren"),
    ("Sparrenlänge", "(Gebäudebreite/2+Überstand_Traufe)/cos(Dachneigung)", "m", "Vorschlag: Länge entlang der Dachfläche"),
    ("Firstlänge", "Gebäudelänge+2*Überstand_Ortgang", "m", "Vorschlag: Länge des Firstes"),
    ("Traufenlänge", "2*Firstlänge", "m", "Vorschlag: beide Traufen"),
    ("Ortganglänge", "4*Sparrenlänge", "m", "Vorschlag: vier Ortgangkanten"),
    ("Dachfläche", "2*Sparrenlänge*Firstlänge", "m²", "Vorschlag: beide Dachflächen"),
    ("Firsthöhe", "Gebäudebreite/2*tan(Dachneigung)", "m", "Vorschlag: Höhe des Firstes über der Traufe"),
    ("Sparrenanzahl", "2*(ceil(Firstlänge/Sparrenabstand)+1)", "Stk", "Vorschlag: beide Dachseiten"),
    ("Gratlänge", "0", "m", "Eingabe: nur bei Walm-/Krüppelwalmdach"),
    ("Kehllänge", "0", "m", "Eingabe: bei Dachanschlüssen/Gauben"),
]
AUS_DACHFLAECHE = [
    ("Dachfläche", "160", "m²", "Gegeben: gesamte Dachfläche"),
    ("Dachneigung", "35", "°", "Gegeben: Neigung in Grad"),
    ("Firstlänge", "wurzel(1,25*Dachfläche*cos(Dachneigung))", "m",
     "Vorschlag (Haus ca. 1 : 1,25) – mit Messwert überschreiben, dann rechnet alles damit weiter"),
    ("Sparrenlänge", "Dachfläche/(2*Firstlänge)", "m", "Vorschlag aus Dachfläche und Firstlänge"),
    ("Traufenlänge", "2*Firstlänge", "m", "Vorschlag: beide Traufen"),
    ("Ortganglänge", "4*Sparrenlänge", "m", "Vorschlag: vier Ortgangkanten"),
    ("Gebäudebreite", "2*Sparrenlänge*cos(Dachneigung)", "m", "Vorschlag (ohne Überstand)"),
    ("Firsthöhe", "Gebäudebreite/2*tan(Dachneigung)", "m", "Vorschlag"),
    ("Sparrenabstand", "0,8", "m", "Eingabe: Achsabstand der Sparren"),
    ("Sparrenanzahl", "2*(ceil(Firstlänge/Sparrenabstand)+1)", "Stk", "Vorschlag"),
    ("Gratlänge", "0", "m", "Eingabe: nur bei Walm-/Krüppelwalmdach"),
    ("Kehllänge", "0", "m", "Eingabe: bei Dachanschlüssen/Gauben"),
]
VORLAGEN = {"Dachstuhl – Satteldach aus Gebäudemaßen": SATTELDACH,
            "Dachstuhl – aus gegebener Dachfläche": AUS_DACHFLAECHE}
KEINE = "– keine –"


def vorlage_namen():
    return list(VORLAGEN)


def einfuegen(db, pid, vorlage):
    """Fügt die Parameter einer Vorlage ein (bereits vorhandene Namen bleiben unverändert). -> Anzahl neu."""
    n = 0
    vorhanden = {r["name"].lower() for r in db.q("SELECT name FROM parameter WHERE projekt_id=?", (pid,))}
    for name, wert, einheit, hinweis in VORLAGEN[vorlage]:
        if name.lower() not in vorhanden:
            db.x("INSERT INTO parameter(projekt_id,name,wert,einheit,hinweis) VALUES(?,?,?,?,?)", (pid, name, wert, einheit, hinweis))
            n += 1
    return n


def bekannte_namen(db):
    """Alle Parameternamen, die in Formeln der Leistungen verwendet werden dürfen (Vorlagen + vorhandene Projekte)."""
    d = {name: 1 for v in VORLAGEN.values() for name, *_ in v}
    d.update({r["name"]: 1 for r in db.q("SELECT DISTINCT name FROM parameter")})
    return d


def namen_text():
    return ", ".join(sorted({name for v in VORLAGEN.values() for name, *_ in v}, key=str.lower))


def beispielwerte(vorlage=None):
    werte, _ = eval_parameter([(n, w) for n, w, *_ in VORLAGEN[vorlage or next(iter(VORLAGEN))]])
    return werte

# weitere Namen, die aus Plänen übernommen werden können und in Mengenformeln erlaubt sind
WEITERE = [("Grundfläche", "m²"), ("Wohnfläche", "m²"), ("Nutzfläche", "m²"), ("Traufhöhe", "m"), ("Gebäudehöhe", "m")]
_bekannte_alt = bekannte_namen
_namen_text_alt = namen_text


def bekannte_namen(db):  # noqa: F811
    d = _bekannte_alt(db)
    d.update({n: 1 for n, _ in WEITERE})
    return d


def namen_text():  # noqa: F811
    return ", ".join(sorted({n for n in _namen_text_alt().split(", ")} | {n for n, _ in WEITERE}, key=str.lower))
