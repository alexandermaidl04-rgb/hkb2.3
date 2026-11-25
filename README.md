# HBK – Holzbau Kalkulation (Version 2.3)

Lokale Windows-Anwendung (Python/Tkinter + SQLite + ReportLab). Keine Cloud, kein Server.

## Neu in Version 2
- Passwortabfrage bei jedem Start (Einrichtung beim ersten Start; änderbar unter *Datei → Passwort ändern*)
- Orange Oberfläche mit schlichten Symbolen
- **Stammdaten** → *Artikel* und *Löhne*
  - Artikel in frei anlegbaren Ordnern/Unterordnern (z. B. Holz → KVH), Preishistorie, Preisaufschlag je Artikel
  - Import aus Onlineshop-/Lieferantendateien (CSV, Excel) mit Spaltenzuordnung, Zielordner und Preisstand
  - Löhne = Stundenverrechnungssätze (Lohnarten) + Standard-Stundenverrechnungssatz
- **Leistungen** in Ordnern; Editor im WGsystem-Stil: Menge, Mengenaufschlag, EK, Preisaufschlag, VK, Preis je Einheit,
  Gesamtzeit, Preis. Ein Klick auf Zahl oder Namen ändert direkt (Enter = übernehmen, Esc = abbrechen).
- Artikel direkt in der Leistung anlegen (wahlweise auch in die Stammdaten übernehmen, dort mit ★ gekennzeichnet)
- Lohnanteile (Bezeichnung, Zeit, Einheit, Stundensatz, Menge fix) – Satz folgt Lohnart bzw. Standardsatz
- Reiter **Analyse** mit Gesamtzeitaufwand und Kennzahlen
- **Parameter aus Plänen (PDF)**: Reiter Parameter → „Aus Plan (PDF) einlesen …“. Erkannt werden beschriftete Angaben
  (Dachneigung, Dachfläche, Firstlänge, Gebäudelänge/-breite, Überstände, Sparrenabstand, Grundfläche, Traufhöhe …) inkl. Umrechnung
  cm/mm → m. Vor der Übernahme prüfen/ändern; danach sind es normale Parameter und jederzeit manuell änderbar.
  Funktioniert nur bei PDFs mit auswählbarem Text (aus CAD), nicht bei gescannten Plänen.
- **Passwort vergessen**: Auf dem Anmeldebildschirm „Passwort vergessen …“ → Masterkey eingeben → neues Passwort festlegen.
- **Logo** in Kopfleiste, Anmeldefenster, Fenster-/Programm-Icon und im PDF (Dateien in `hbk/assets`).
- **Menge fix** auch bei Material (wie bei Lohnanteilen): Menge wird nicht mit der Leistungsmenge multipliziert
  (Knopf „Menge fix an/aus“ im Leistungs-Editor).
- **Parameter-Vorlagen Dachstuhl** (beim neuen Projekt oder im Reiter Parameter → „Vorlage einfügen“):
  gegebene Werte (z. B. Dachfläche, Dachneigung) eintragen, HBK schlägt Firstlänge, Sparrenlänge, Traufen-/Ortganglänge,
  Firsthöhe, Sparrenanzahl vor. Vorschläge sind Formeln und lassen sich durch einen Messwert überschreiben.
  Die Parameter stehen in den Mengenformeln der Leistungen zur Verfügung (Winkel in Grad; sin/cos/tan/atan/wurzel/pi).
- **Datanorm 4 (Semikolon-Format)** (Standardformat des Großhandels):
  - *Import:* Datanorm-Dateien von Lieferanten/Großhandel werden automatisch erkannt (Artikelsätze, Preiseinheit, DOS-Umlaute);
    optional Rabatt % auf die Dateipreise (z. B. Lieferantenrabatt auf Listenpreise).
  - *Export für KWP:* Leistungen als Datanorm-Artikel (Nr., Kurztext, Einheit, Einheitspreis VK netto). Der Export schreibt Datanorm
    Version 4. KWP muss auf Version 4 stehen; bei Version 3 (fester Satzaufbau) wird die Datei nicht gelesen. Datanorm kennt kein Feld für Zeitanteil/Langtext.
- **CSV-Export für KWP/ERP** (Beschreibung, EP, Zeitanteil, Einheit, Material/Lohn, optional Bausteine)

## Rechenmodell
- Material: Menge je Einheit (Zahl oder Formel) × Leistungsmenge × (1 + Mengenaufschlag) × EK-Preis zum Stichtag
  → + Preisaufschlag → VK. Aufschlag-Rangfolge: Projekt (falls gesetzt) → Leistung → Artikel → Standard.
- Lohn: Zeit je Einheit × Menge × (Leistungsmenge, außer „Menge fix“) × Stundensatz.
- Preis der Leistung = Material (VK) + Lohn. Projekt: + Gemeinkosten, + Gewinn (beide optional, Standard 0 %), + MwSt.
- Snapshots frieren Parameter, Formeln, Preise, Aufschläge und Zeiten ein.

## Installer bauen
Siehe `build_installer.bat` (Python 3.10+ und Inno Setup 6 nötig) oder GitHub-Workflow `.github/workflows/build-installer.yml`.
Daten: `%APPDATA%\HBK\hbk.db` (bleibt bei Deinstallation erhalten). Bestehende Version-1-Daten werden automatisch übernommen.

## Hinweis zum Passwort
Das Passwort schützt den Programmstart. Die Datenbankdatei selbst ist nicht verschlüsselt.
Ein vergessenes Passwort kann nicht wiederhergestellt werden.

## Tests
`python -m unittest discover -s tests`
