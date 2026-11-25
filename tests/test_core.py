import csv, os, sys, tempfile, unittest, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from hbk.db import DB, seed_demo
from hbk.calc import berechne, berechne_leistung, rechenweg, evaluate, FormelFehler
from hbk.pdf import erzeuge_pdf
from hbk import auth, importer, export
from hbk.util import parse_zeit, fmt_zeit


class Core(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = DB(os.path.join(self.tmp, "t.db"))
        seed_demo(self.db)
        self.pid = self.db.one("SELECT id FROM projekte")["id"]

    def test_berechnung_unabhaengig_nachgerechnet(self):
        r = berechne(self.db, self.pid)           # Stichtag 15.10.2025; Standardaufschlag 8 %, Zellulose 6 % (Artikel)
        kvh_ek = round(0.045 * 120 * 1.08 * 695, 2)
        kvh_vk = round(0.045 * 120 * 1.08 * 695 * 1.08, 2)
        zel_vk = round(0.16 * 40 * 120 * 1.03 * 0.92 * 1.06, 2)
        sch_vk = round(25 * 120 * 0.12 * 1.08, 2)
        lohn1 = round(120 * 1.8 * 55, 2)
        p1 = r["positionen"][0]
        self.assertAlmostEqual(p1["material_summe"], round(kvh_vk + zel_vk + sch_vk, 2), 1)
        self.assertAlmostEqual(p1["lohn"], lohn1, 2)
        self.assertAlmostEqual(p1["stunden"], 216, 6)
        hf_vk = round(85 * 1.05 * 19.9 * 1.08, 2)
        self.assertAlmostEqual(r["positionen"][1]["material_summe"], hf_vk, 1)
        netto = round(p1["material_summe"] + lohn1 + hf_vk + round(85 * .6 * 55, 2) + round(16 * 55, 2), 2)
        self.assertAlmostEqual(r["summen"]["netto"], netto, 1)       # Gemeinkosten/Gewinn = 0 %
        self.assertAlmostEqual(r["summen"]["brutto"], round(netto * 1.19, 2), 1)
        self.assertAlmostEqual(r["summen"]["stunden"], 216 + 51 + 16, 6)
        self.assertEqual(r["warnungen"], [])
        self.assertAlmostEqual(r["summen"]["aufschlag"], r["summen"]["material"] - r["summen"]["material_ek"], 2)

    def test_projekt_aufschlag_ueberschreibt(self):
        a = berechne(self.db, self.pid)["summen"]["material"]
        self.db.x("UPDATE projekte SET aufschlag_override=20 WHERE id=?", (self.pid,))
        r = berechne(self.db, self.pid)
        self.assertGreater(r["summen"]["material"], a)
        self.assertAlmostEqual(r["summen"]["material"], round(r["summen"]["material_ek"] * 1.2, 0), -1)
        self.assertIn("Projekt", "\n".join(rechenweg(r)))

    def test_lohn_fix_und_satzhierarchie(self):
        lid = self.db.x("INSERT INTO leistungen(nr,bezeichnung,einheit) VALUES('L-T','Test','m²')")
        self.db.x("INSERT INTO leistung_lohn(leistung_id,bezeichnung,zeit_h,einheit,menge,satz,menge_fix) VALUES(?,?,?,?,?,?,1)",
                  (lid, "Einrichten", 2.0, "Psch", "1", 60))
        self.db.x("INSERT INTO leistung_lohn(leistung_id,bezeichnung,zeit_h,einheit,menge) VALUES(?,?,?,?,?)",
                  (lid, "Arbeit", 0.5, "m²", "2"))      # kein Satz -> Standard 50 €/h
        z = berechne_leistung(self.db, lid, 10)
        self.assertAlmostEqual(z["lohn"][0]["stunden"], 2.0); self.assertAlmostEqual(z["lohn"][0]["summe"], 120.0)
        self.assertAlmostEqual(z["lohn"][1]["stunden"], 0.5 * 2 * 10); self.assertAlmostEqual(z["lohn"][1]["summe"], 500.0)
        self.assertAlmostEqual(z["stunden"], 12.0)
        la = self.db.one("SELECT id FROM lohnarten WHERE nr='LA-1'")["id"]
        self.db.x("UPDATE leistung_lohn SET lohnart_id=? WHERE bezeichnung='Arbeit'", (la,))
        self.assertAlmostEqual(berechne_leistung(self.db, lid, 10)["lohn"][1]["summe"], 550.0)   # Zimmerer 55 €/h

    def test_historisierung_reproduzierbar(self):
        r_alt = berechne(self.db, self.pid)
        sid = self.db.snapshot_speichern(self.pid, "Stand Okt", r_alt)
        aid = self.db.one("SELECT id FROM artikel WHERE nr='A-001'")["id"]
        self.db.preis_setzen(aid, "2025-10-10", 900.0)
        self.assertGreater(berechne(self.db, self.pid)["summen"]["brutto"], r_alt["summen"]["brutto"])
        self.assertEqual(self.db.snapshot_laden(sid)["summen"], r_alt["summen"])
        self.db.x("UPDATE projekte SET stichtag='2025-04-01' WHERE id=?", (self.pid,))
        self.assertLess(berechne(self.db, self.pid)["summen"]["brutto"], r_alt["summen"]["brutto"])

    def test_fehlender_preis_warnt(self):
        self.db.x("UPDATE projekte SET stichtag='2024-01-01' WHERE id=?", (self.pid,))
        self.assertTrue(berechne(self.db, self.pid)["warnungen"])

    def test_rechenweg_und_pdf(self):
        r = berechne(self.db, self.pid)
        txt = "\n".join(rechenweg(r))
        for s in ("Mengenaufschlag", "Preisaufschlag", "BRUTTO", "Lohn Abbund"):
            self.assertIn(s, txt)
        pfad = erzeuge_pdf(r, os.path.join(self.tmp, "t.pdf"), "Test GmbH", "Musterstr. 1")
        self.assertGreater(os.path.getsize(pfad), 3000)

    def test_formeln_sicher(self):
        for bad in ['__import__("os")', "(1).__class__", "2**999", "1/0", "x"]:
            with self.assertRaises(FormelFehler):
                evaluate(bad, {})
        self.assertAlmostEqual(evaluate("round(2,5*3;1)+max(1;2)"), 9.5)

    def test_ordner_loeschschutz_backup(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.x("DELETE FROM leistungen WHERE nr='L-001'")
        holz = self.db.ordner_id_per_pfad("artikel", "Holz")
        sub = self.db.ordner_anlegen("artikel", "Konstruktionsholz", holz)
        self.assertIn("Holz / Konstruktionsholz", dict((p, i) for i, p in self.db.ordner_pfade("artikel")))
        aid = self.db.one("SELECT id FROM artikel WHERE nr='A-001'")["id"]
        self.db.verschieben("artikel", aid, sub)
        self.db.ordner_loeschen(holz)                      # Unterordner mit weg, Artikel bleibt erhalten
        self.assertIsNone(self.db.one("SELECT ordner_id FROM artikel WHERE id=?", (aid,))["ordner_id"])
        self.assertEqual(self.db.one("SELECT COUNT(*) c FROM ordner WHERE name IN ('Holz','Konstruktionsholz')")["c"], 0)
        ziel = os.path.join(self.tmp, "b.db"); self.db.backup(ziel)
        self.assertEqual(DB(ziel).one("SELECT COUNT(*) c FROM artikel")["c"], 4)

    def test_passwort(self):
        self.assertFalse(auth.has_password(self.db))
        with self.assertRaises(ValueError): auth.set_password(self.db, "abc")
        auth.set_password(self.db, "Holz2026!")
        self.assertTrue(auth.has_password(self.db))
        self.assertTrue(auth.check_password(self.db, "Holz2026!"))
        self.assertFalse(auth.check_password(self.db, "falsch"))
        self.assertNotIn("Holz2026", str(self.db.q("SELECT * FROM settings")[0:] and [tuple(r) for r in self.db.q("SELECT * FROM settings")]))
        self.assertNotIn("pw_hash", self.db.settings())

    def test_masterkey_reset(self):
        auth.set_password(self.db, "alt123")
        self.assertTrue(auth.check_master("maidl")); self.assertTrue(auth.check_master("  Maidl ")); self.assertFalse(auth.check_master("maidl1"))
        self.assertFalse(auth.check_master(""))
        with self.assertRaises(ValueError): auth.reset_password(self.db, "falsch", "neu456")
        self.assertTrue(auth.check_password(self.db, "alt123"))                         # Fehlversuch ändert nichts
        with self.assertRaises(ValueError): auth.reset_password(self.db, "maidl", "abc")   # zu kurz
        auth.reset_password(self.db, "maidl", "neu456")
        self.assertTrue(auth.check_password(self.db, "neu456")); self.assertFalse(auth.check_password(self.db, "alt123"))
        self.assertEqual(self.db.one("SELECT COUNT(*) c FROM artikel")["c"], 4)          # Daten unverändert

    def test_assets_vorhanden(self):
        from hbk.assets import asset_pfad
        for n in ("logo.png", "logo_header.png", "logo_login.png", "icon.png", "HBK.ico"):
            self.assertTrue(os.path.getsize(asset_pfad(n)) > 1000, n)

    def _plan_pdf(self, zeilen, name="plan.pdf"):
        from reportlab.pdfgen import canvas
        from hbk.pdf import _fonts
        F, _, _ = _fonts()
        p = os.path.join(self.tmp, name); c = canvas.Canvas(p); c.setFont(F, 11); y = 800
        for z in zeilen:
            c.drawString(60, y, z); y -= 18
        c.save(); return p

    def test_plan_import(self):
        from hbk import planimport
        p = self._plan_pdf(["Eingabeplan EFH M 1:100", "Dachneigung: 38°", "Dachfläche gesamt 135,40 m²", "Firstlänge 12,00 m", "Gebäudelänge 12,00 m",
                            "Gebäudebreite 9,50 m", "Dachüberstand Traufe 0,60 m", "Ortgangüberstand 0,50 m", "Sparrenabstand 80 cm", "bebaute Fläche 118,75 m²",
                            "Wohnfläche EG: 98,2 m²", "Terrasse 24,50 m²", "Traufhöhe 5,80 m", "Pultdach DN 12°", "Maßstab 1:100"])
        f = planimport.analysiere_pdf(p)
        w = {x["name"]: x for x in f if x["name"] and x["use"]}
        soll = {"Dachneigung": 38, "Dachfläche": 135.4, "Firstlänge": 12, "Gebäudelänge": 12, "Gebäudebreite": 9.5, "Überstand_Traufe": 0.6,
                "Überstand_Ortgang": 0.5, "Sparrenabstand": 0.8, "Grundfläche": 118.75, "Wohnfläche": 98.2, "Traufhöhe": 5.8}
        for k, v in soll.items(): self.assertAlmostEqual(w[k]["wert"], v, 3, k)
        zweite = [x for x in f if x["name"] == "Dachneigung" and not x["use"]]
        self.assertEqual(len(zweite), 1); self.assertEqual(zweite[0]["wert"], 12.0)        # zweiter Fund nicht automatisch gewählt
        self.assertTrue(any(x["name"] == "" and x["wert"] == 24.5 for x in f))             # Terrasse: Kandidat ohne Zuordnung
        self.assertIn("Dachneigung: 38°", w["Dachneigung"]["stelle"])
        # Übernahme ins Projekt; vorhandene Formel (Vorschlag) wird durch den Planwert ersetzt, danach manuell änderbar
        from hbk import parameter
        pid = self.db.create_projekt("P-PLAN", "Plan"); parameter.einfuegen(self.db, pid, parameter.vorlage_namen()[1])
        neu, akt = planimport.uebernehmen(self.db, pid, f, "plan.pdf")
        self.assertGreater(neu, 3); self.assertGreaterEqual(akt, 3)
        r = self.db.one("SELECT wert,einheit,hinweis FROM parameter WHERE projekt_id=? AND name='Firstlänge'", (pid,))
        self.assertEqual((r["wert"], r["einheit"]), ("12", "m")); self.assertIn("plan.pdf", r["hinweis"])
        self.assertEqual(self.db.one("SELECT wert FROM parameter WHERE projekt_id=? AND name='Dachfläche'", (pid,))["wert"], "135,4")
        self.assertEqual(self.db.one("SELECT wert FROM parameter WHERE projekt_id=? AND name='Sparrenlänge'", (pid,))["wert"], "Dachfläche/(2*Firstlänge)")  # Formel bleibt
        res = berechne(self.db, pid); self.assertEqual(res["warnungen"], [])
        wv = {x["name"]: x["wert"] for x in res["parameter"]}
        self.assertAlmostEqual(wv["Sparrenlänge"], 135.4 / 24, 4)                           # rechnet mit den Planwerten weiter
        self.db.x("UPDATE parameter SET wert='13' WHERE projekt_id=? AND name='Firstlänge'", (pid,))   # manuell geändert
        self.assertAlmostEqual({x["name"]: x["wert"] for x in berechne(self.db, pid)["parameter"]}["Firstlänge"], 13)

    def test_plan_import_sonderfaelle(self):
        from hbk import planimport
        f = planimport.analysiere_text("Dachneigung 70 %\nSparrenabstand 80\nDachüberstand 0,5 m\nFirstlänge 1200 cm\nDachfläche 99,5")
        w = {x["name"]: x for x in f if x["name"]}
        self.assertAlmostEqual(w["Dachneigung"]["wert"], 34.99, 1); self.assertIn("%", w["Dachneigung"]["stelle"] or "%")
        self.assertAlmostEqual(w["Sparrenabstand"]["wert"], 0.8); self.assertIn("cm angenommen", w["Sparrenabstand"]["stelle"])
        self.assertIn("allgemeiner Dachüberstand", w["Überstand_Traufe"]["stelle"])
        self.assertAlmostEqual(w["Firstlänge"]["wert"], 12.0); self.assertIn("m² angenommen", w["Dachfläche"]["stelle"])
        # Plan ohne Text (gescannt) -> verständliche Meldung
        from reportlab.pdfgen import canvas
        p = os.path.join(self.tmp, "leer.pdf"); c = canvas.Canvas(p); c.rect(50, 50, 100, 100); c.save()
        with self.assertRaises(ValueError) as cm: planimport.analysiere_pdf(p)
        self.assertIn("gescannt", str(cm.exception))

    def test_import_csv(self):
        p = os.path.join(self.tmp, "shop.csv")
        with open(p, "w", encoding="cp1252", newline="") as f:
            f.write("Artikelnr;Artikelbezeichnung;ME;Preis netto;Hersteller\n"
                    "S-1;Lattung 30x50 ;lfm;1.234,50 €;Sägewerk A\nS-2;Dachlatte;lfm;0,95;\nA-004;Schrauben;Stk;0,15;\n;;;;\nS-3;Defekt;Stk;abc;\n")
        kopf, zeilen = importiere_lesen = importer.lese_tabelle(p)
        m = importer.vorschlag(kopf)
        self.assertEqual(m["nr"], 0); self.assertEqual(m["bezeichnung"], 1); self.assertEqual(m["preis"], 3); self.assertEqual(m["einheit"], 2)
        o = self.db.ordner_id_per_pfad("artikel", "Holz / Latten")
        res = importer.importiere(self.db, zeilen, m, ordner_id=o, gueltig_ab="2025-11-01", lieferant="Shop")
        self.assertEqual((res["neu"], res["aktualisiert"]), (2, 1)); self.assertEqual(len(res["fehler"]), 1)
        a = self.db.one("SELECT * FROM artikel WHERE nr='S-1'")
        self.assertEqual(a["ordner_id"], o); self.assertEqual(a["quelle"], "Import")
        self.assertAlmostEqual(self.db.preis_at(a["id"], "2025-12-01")[0], 1234.5)
        a4 = self.db.one("SELECT id FROM artikel WHERE nr='A-004'")["id"]
        self.assertEqual(self.db.preis_at(a4, "2025-10-31")[0], 0.12)       # alter Stand bleibt erhalten
        self.assertEqual(self.db.preis_at(a4, "2025-11-01")[0], 0.15)

    def test_kwp_export(self):
        lids = [r["id"] for r in self.db.q("SELECT id FROM leistungen ORDER BY nr")]
        pfad = os.path.join(self.tmp, "l.csv")
        d = export.export_leistungen(self.db, lids, pfad, stichtag="2025-10-15")
        self.assertEqual(len(d), 2)
        rows = list(csv.reader(open(pfad, encoding="cp1252"), delimiter=";"))
        self.assertEqual(rows[0], export.KOPF); self.assertEqual(len(rows), 4)
        r1 = dict(zip(rows[0], rows[1]))
        self.assertEqual(r1["Leistungsnr"], "L-001"); self.assertEqual(r1["Ordner"], "Wand")
        self.assertEqual(r1["Zeit_hhmm"], "01:48"); self.assertEqual(r1["Zeit_Minuten"], "108")
        z = berechne_leistung(self.db, lids[0], 1.0, "2025-10-15")
        self.assertEqual(r1["EP_VK"], f"{z['summe']:.2f}".replace(".", ","))
        self.assertGreater(len(list(csv.reader(open(d[1], encoding="cp1252"), delimiter=";"))), 5)

    def test_datanorm_lesen_und_import(self):
        from hbk import datanorm
        zeilen = ["V;250101;001;Muster Holzhandel;EUR",
                  "A;N;KVH-6012;1;Konstruktionsvollholz 60x120;Fichte C24 NSi;1;2;M;1250;R1;05;0",       # 12,50 je 100 m
                  "A;N;4711;1;Schraube 4x40 Edelstahl;;2;0;1250;ST;R2;07;0",                           # andere Feldreihenfolge, 12,50 je Stück
                  "A;L;9999;1;Gelöschter Artikel;;1;0;100;ST;;;0",
                  "A;N;D-100;1;Dämmplatte Größe 10 cm;;1;1;M2;5990;R3;09;0",                            # 59,90 je 10 m²
                  "T;N;1;Langtext wird ignoriert"]
        p = os.path.join(self.tmp, "DATANORM.001")
        with open(p, "wb") as f: f.write(("\r\n".join(zeilen) + "\r\n").encode("cp850"))
        with open(p, "rb") as f: self.assertTrue(datanorm.ist_datanorm(f.read()))
        kopf, rows = importer.lese_tabelle(p)                    # Erkennung läuft automatisch über lese_tabelle
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0][:4], ["KVH-6012", "Konstruktionsvollholz 60x120 Fichte C24 NSi", "M", "0,1250"])
        self.assertEqual(rows[1][:4], ["4711", "Schraube 4x40 Edelstahl", "ST", "12,5000"])
        self.assertEqual(rows[2][1], "Dämmplatte Größe 10 cm"); self.assertEqual(rows[2][3], "5,9900"); self.assertEqual(rows[0][4], "Brutto (Listenpreis)")
        m = importer.vorschlag(kopf)
        self.assertEqual((m["nr"], m["bezeichnung"], m["einheit"], m["preis"], m["kategorie"]), (0, 1, 2, 3, 6))
        res = importer.importiere(self.db, rows, m, None, "2025-11-01", "Muster", rabatt=30.0)
        self.assertEqual(res["neu"], 3, res)
        a = self.db.one("SELECT id,kategorie,lieferant FROM artikel WHERE nr='4711'")
        self.assertAlmostEqual(self.db.preis_at(a["id"], "2025-11-02")[0], 12.5 * 0.7, 4)           # 30 % Rabatt
        self.assertEqual((a["kategorie"], a["lieferant"]), ("07", "Muster"))
        csvp = os.path.join(self.tmp, "x.csv"); open(csvp, "w").write("A;N;B\n1;2;3\n")
        self.assertEqual(importer.lese_tabelle.__name__, "lese_tabelle")
        with open(csvp, "rb") as f: self.assertFalse(datanorm.ist_datanorm(f.read()))

    def test_datanorm_schreiben_roundtrip(self):
        from hbk import datanorm
        lids = [r["id"] for r in self.db.q("SELECT id FROM leistungen ORDER BY nr")]
        p = os.path.join(self.tmp, "out.001")
        datanorm.schreibe_datanorm(self.db, lids, p, "2025-10-15")
        txt = open(p, "rb").read().decode("cp850").splitlines()
        self.assertTrue(txt[0].startswith("V;")); self.assertEqual(len([t for t in txt if t.startswith("A;")]), 3)
        kopf, rows = importer.lese_tabelle(p)                    # vom eigenen Leser wieder lesbar
        ep = berechne_leistung(self.db, lids[0], 1.0, "2025-10-15")["summe"]
        self.assertEqual((rows[0][0], rows[0][2]), ("L-001", "m2")); self.assertTrue(rows[0][1].startswith("Holzrahmenwand"))
        self.assertAlmostEqual(float(rows[0][3].replace(",", ".")), round(ep, 2), 2)
        self.assertEqual(rows[2][2], "h")

    def test_material_menge_fix(self):
        lid = self.db.x("INSERT INTO leistungen(nr,bezeichnung,einheit) VALUES('L-F','Fix','m²')")
        a = self.db.one("SELECT id FROM artikel WHERE nr='A-004'")["id"]          # Schrauben 0,12 €, Standardaufschlag 8 %
        self.db.x("INSERT INTO leistung_material(leistung_id,artikel_id,menge,verschnitt,menge_fix) VALUES(?,?,'100',10,1)", (lid, a))
        self.db.x("INSERT INTO leistung_material(leistung_id,artikel_id,menge,verschnitt,menge_fix) VALUES(?,?,'100',10,0)", (lid, a))
        z = berechne_leistung(self.db, lid, 5, "2025-10-15")
        self.assertAlmostEqual(z["material"][0]["menge_gesamt"], 100 * 1.1)         # fix: unabhängig von der Menge 5
        self.assertAlmostEqual(z["material"][1]["menge_gesamt"], 100 * 5 * 1.1)
        self.assertAlmostEqual(z["material"][0]["summe"], round(110 * 0.12 * 1.08, 2))
        self.db.x("UPDATE projekte SET stichtag='2025-10-15'")
        pid = self.pid; self.db.x("INSERT INTO positionen(projekt_id,leistung_id,menge,sort) VALUES(?,?,'5',9)", (pid, lid))
        self.assertIn("Menge fix", "\n".join(rechenweg(berechne(self.db, pid))))

    def test_parameter_vorlagen_und_ueberschreiben(self):
        from hbk import parameter
        pid = self.db.create_projekt("P-V", "Dach")
        for v in parameter.vorlage_namen():
            n = self.db.x("DELETE FROM parameter WHERE projekt_id=? AND name NOT IN ('MwSt','Gemeinkosten','Gewinnaufschlag')", (pid,))
            self.assertGreater(parameter.einfuegen(self.db, pid, v), 10)
            r = berechne(self.db, pid); self.assertEqual(r["warnungen"], [])             # alle Formeln rechnen fehlerfrei
        w = {p["name"]: p["wert"] for p in r["parameter"]}                               # zuletzt: Vorlage "aus gegebener Dachfläche"
        self.assertAlmostEqual(w["Dachfläche"], 160); self.assertAlmostEqual(w["Firstlänge"], 12.8, 1); self.assertAlmostEqual(w["Sparrenlänge"], 6.25, 1)
        self.assertAlmostEqual(w["Ortganglänge"], 4 * w["Sparrenlänge"]); self.assertAlmostEqual(w["Traufenlänge"], 2 * w["Firstlänge"])
        self.db.x("UPDATE parameter SET wert='14' WHERE projekt_id=? AND name='Firstlänge'", (pid,))   # gemessenen Wert eintragen
        w2 = {p["name"]: p["wert"] for p in berechne(self.db, pid)["parameter"]}
        self.assertAlmostEqual(w2["Firstlänge"], 14); self.assertAlmostEqual(w2["Sparrenlänge"], 160 / 28)
        self.assertEqual(parameter.einfuegen(self.db, pid, parameter.vorlage_namen()[1]), 0)   # keine Duplikate
        a = parameter.beispielwerte(parameter.vorlage_namen()[0])
        self.assertAlmostEqual(a["Dachfläche"], 2 * a["Sparrenlänge"] * a["Firstlänge"]); self.assertAlmostEqual(a["Sparrenlänge"], 4.5 / 0.819152, 3)
        self.assertAlmostEqual(evaluate("cos(60)"), 0.5); self.assertAlmostEqual(evaluate("wurzel(16)+tan(45)"), 5.0)
        self.assertAlmostEqual(evaluate("atan(1)"), 45.0)

    def test_migration_v1(self):
        p = os.path.join(self.tmp, "v1.db")
        con = sqlite3.connect(p)
        con.executescript("""CREATE TABLE artikel(id INTEGER PRIMARY KEY AUTOINCREMENT,nr TEXT UNIQUE NOT NULL,bezeichnung TEXT NOT NULL,
          einheit TEXT NOT NULL DEFAULT 'Stk',lieferant TEXT DEFAULT '',kategorie TEXT DEFAULT '',gewicht REAL,volumen REAL,lager TEXT DEFAULT '');
          CREATE TABLE leistungen(id INTEGER PRIMARY KEY AUTOINCREMENT,nr TEXT UNIQUE NOT NULL,bezeichnung TEXT NOT NULL,
          einheit TEXT NOT NULL DEFAULT 'm²',zeit_h REAL NOT NULL DEFAULT 0,beschreibung TEXT DEFAULT '');
          CREATE TABLE projekte(id INTEGER PRIMARY KEY AUTOINCREMENT,nr TEXT UNIQUE NOT NULL,bezeichnung TEXT NOT NULL,kunde TEXT DEFAULT '',
          status TEXT DEFAULT 'Entwurf',ort TEXT DEFAULT '',datum TEXT,stichtag TEXT,geaendert TEXT);
          INSERT INTO artikel(nr,bezeichnung) VALUES('X','alt'); INSERT INTO leistungen(nr,bezeichnung,zeit_h) VALUES('L-1','alt',1.5);""")
        con.commit(); con.close()
        d = DB(p)
        o = d.one("SELECT * FROM leistung_lohn"); self.assertEqual(o["zeit_h"], 1.5)
        self.assertEqual(d.one("SELECT stamm FROM artikel")["stamm"], 1)

    def test_zeit(self):
        for t, v in (("01 h 30 min", 1.5), ("1:30", 1.5), ("90 min", 1.5), ("1,5", 1.5), ("2h", 2.0)):
            self.assertAlmostEqual(parse_zeit(t), v)
        self.assertEqual(fmt_zeit(11.5), "11 h 30 min")


if __name__ == "__main__":
    unittest.main()
