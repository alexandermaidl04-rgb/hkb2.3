"""Datenbank (SQLite) v2: Schema, Migration, Ordner, Preise, Beispieldaten."""
import json
import os
import sqlite3
from datetime import date, timedelta

from .util import now_iso, today_iso

DEFAULT_SETTINGS = {
    "firma": "Meine Zimmerei GmbH", "adresse": "",
    "lohnsatz": "50",          # Standard-Stundenverrechnungssatz (€/h)
    "aufschlag": "8",          # Standard-Preisaufschlag auf Material (%)
    "gemeinkosten": "0", "gewinn": "0", "mwst": "19",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS ordner(
  id INTEGER PRIMARY KEY AUTOINCREMENT, bereich TEXT NOT NULL,
  parent_id INTEGER, name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lohnarten(
  id INTEGER PRIMARY KEY AUTOINCREMENT, nr TEXT DEFAULT '', bezeichnung TEXT NOT NULL, satz REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS artikel(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nr TEXT UNIQUE NOT NULL, bezeichnung TEXT NOT NULL, einheit TEXT NOT NULL DEFAULT 'Stk',
  lieferant TEXT DEFAULT '', kategorie TEXT DEFAULT '', gewicht REAL, volumen REAL, lager TEXT DEFAULT '',
  ordner_id INTEGER, preisaufschlag REAL, stamm INTEGER NOT NULL DEFAULT 1, quelle TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS preise(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  artikel_id INTEGER NOT NULL REFERENCES artikel(id) ON DELETE CASCADE,
  gueltig_ab TEXT NOT NULL, preis REAL NOT NULL, UNIQUE(artikel_id, gueltig_ab)
);
CREATE TABLE IF NOT EXISTS leistungen(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nr TEXT UNIQUE NOT NULL, bezeichnung TEXT NOT NULL, einheit TEXT NOT NULL DEFAULT 'm²',
  zeit_h REAL NOT NULL DEFAULT 0, beschreibung TEXT DEFAULT '', ordner_id INTEGER
);
CREATE TABLE IF NOT EXISTS leistung_material(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  leistung_id INTEGER NOT NULL REFERENCES leistungen(id) ON DELETE CASCADE,
  artikel_id INTEGER NOT NULL REFERENCES artikel(id) ON DELETE RESTRICT,
  menge TEXT NOT NULL DEFAULT '1', verschnitt REAL NOT NULL DEFAULT 0,
  bezeichnung TEXT, preisaufschlag REAL, menge_fix INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS leistung_lohn(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  leistung_id INTEGER NOT NULL REFERENCES leistungen(id) ON DELETE CASCADE,
  bezeichnung TEXT NOT NULL DEFAULT 'Lohnanteil', lohnart_id INTEGER,
  zeit_h REAL NOT NULL DEFAULT 0, einheit TEXT NOT NULL DEFAULT 'Stk',
  menge TEXT NOT NULL DEFAULT '1', satz REAL, menge_fix INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS projekte(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nr TEXT UNIQUE NOT NULL, bezeichnung TEXT NOT NULL, kunde TEXT DEFAULT '', status TEXT DEFAULT 'Entwurf',
  ort TEXT DEFAULT '', datum TEXT, stichtag TEXT, geaendert TEXT, aufschlag_override REAL
);
CREATE TABLE IF NOT EXISTS parameter(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  projekt_id INTEGER NOT NULL REFERENCES projekte(id) ON DELETE CASCADE,
  name TEXT NOT NULL, wert TEXT NOT NULL, einheit TEXT DEFAULT '', hinweis TEXT DEFAULT '', UNIQUE(projekt_id, name)
);
CREATE TABLE IF NOT EXISTS positionen(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  projekt_id INTEGER NOT NULL REFERENCES projekte(id) ON DELETE CASCADE,
  leistung_id INTEGER NOT NULL REFERENCES leistungen(id) ON DELETE RESTRICT,
  menge TEXT NOT NULL, bemerkung TEXT DEFAULT '', sort INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS snapshots(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  projekt_id INTEGER NOT NULL REFERENCES projekte(id) ON DELETE CASCADE,
  erstellt TEXT NOT NULL, titel TEXT DEFAULT '', daten TEXT NOT NULL
);
"""

# Spalten, die in v1-Datenbanken fehlen
NEUE_SPALTEN = [
    ("artikel", "ordner_id", "INTEGER"), ("artikel", "preisaufschlag", "REAL"),
    ("artikel", "stamm", "INTEGER NOT NULL DEFAULT 1"), ("artikel", "quelle", "TEXT DEFAULT ''"),
    ("leistungen", "ordner_id", "INTEGER"),
    ("leistung_material", "bezeichnung", "TEXT"), ("leistung_material", "preisaufschlag", "REAL"),
    ("projekte", "aufschlag_override", "REAL"),
    ("leistung_material", "menge_fix", "INTEGER NOT NULL DEFAULT 0"), ("parameter", "hinweis", "TEXT DEFAULT ''"),
]
TABELLE = {"artikel": "artikel", "leistung": "leistungen"}


def data_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    p = os.path.join(base, "HBK")
    os.makedirs(p, exist_ok=True)
    return p


def default_db_path():
    return os.environ.get("HBK_DB") or os.path.join(data_dir(), "hbk.db")


class DB:
    def __init__(self, path=None):
        self.path = path or default_db_path()
        self.con = sqlite3.connect(self.path)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.executescript(SCHEMA)
        for tab, col, ddl in NEUE_SPALTEN:
            if col not in {r[1] for r in self.con.execute(f"PRAGMA table_info({tab})")}:
                self.con.execute(f"ALTER TABLE {tab} ADD COLUMN {col} {ddl}")
        for k, v in DEFAULT_SETTINGS.items():
            self.con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
        if self.con.execute("PRAGMA user_version").fetchone()[0] < 2:
            # v1 -> v2: Zeitansatz der Leistung wird zu einem Lohnanteil
            for r in self.con.execute("SELECT id,einheit,zeit_h FROM leistungen WHERE zeit_h>0 AND NOT EXISTS("
                                      "SELECT 1 FROM leistung_lohn WHERE leistung_id=leistungen.id)").fetchall():
                self.con.execute("INSERT INTO leistung_lohn(leistung_id,bezeichnung,zeit_h,einheit,menge) "
                                 "VALUES(?,?,?,?,'1')", (r["id"], "Lohnanteil", r["zeit_h"], r["einheit"]))
            self.con.execute("UPDATE leistungen SET zeit_h=0")
            self.con.execute("PRAGMA user_version=2")
        self.con.commit()

    # --- Basis ---------------------------------------------------------
    def q(self, sql, args=()):
        return self.con.execute(sql, args).fetchall()

    def one(self, sql, args=()):
        return self.con.execute(sql, args).fetchone()

    def x(self, sql, args=()):
        try:
            cur = self.con.execute(sql, args)
            self.con.commit()
            return cur.lastrowid
        except Exception:
            self.con.rollback()
            raise

    def close(self):
        self.con.close()

    def backup(self, ziel):
        self.con.commit()
        dst = sqlite3.connect(ziel)
        with dst:
            self.con.backup(dst)
        dst.close()

    # --- Einstellungen -------------------------------------------------
    def get_setting(self, key, default=None):
        r = self.one("SELECT value FROM settings WHERE key=?", (key,))
        return r["value"] if r else DEFAULT_SETTINGS.get(key, default)

    def set_setting(self, key, value):
        self.x("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (key, str(value)))

    def settings(self):
        return {r["key"]: r["value"] for r in self.q("SELECT key,value FROM settings")
                if not r["key"].startswith("pw_")}

    # --- Ordner (frei anlegbare Unterordner für Artikel und Leistungen) -----------------
    def ordner_pfade(self, bereich):
        """-> [(id, 'Holz / KVH'), ...] sortiert."""
        rows = {r["id"]: r for r in self.q("SELECT * FROM ordner WHERE bereich=?", (bereich,))}

        def pfad(i):
            teile, seen = [], set()
            while i and i in rows and i not in seen:
                seen.add(i)
                teile.append(rows[i]["name"])
                i = rows[i]["parent_id"]
            return " / ".join(reversed(teile))
        return sorted(((i, pfad(i)) for i in rows), key=lambda t: t[1].lower())

    def ordner_pfad(self, bereich, oid):
        return dict(self.ordner_pfade(bereich)).get(oid, "")

    def ordner_anlegen(self, bereich, name, parent_id=None):
        name = (name or "").strip()
        if not name:
            raise ValueError("Ordnername fehlt.")
        return self.x("INSERT INTO ordner(bereich,parent_id,name) VALUES(?,?,?)", (bereich, parent_id, name))

    def ordner_umbenennen(self, oid, name):
        if not (name or "").strip():
            raise ValueError("Ordnername fehlt.")
        self.x("UPDATE ordner SET name=? WHERE id=?", (name.strip(), oid))

    def ordner_loeschen(self, oid):
        """Löscht den Ordner samt Unterordnern; enthaltene Einträge wandern in die oberste Ebene."""
        o = self.one("SELECT * FROM ordner WHERE id=?", (oid,))
        if not o:
            return
        ids, stack = [], [oid]
        while stack:
            i = stack.pop()
            ids.append(i)
            stack += [r["id"] for r in self.q("SELECT id FROM ordner WHERE parent_id=?", (i,))]
        ph = ",".join("?" * len(ids))
        self.x(f"UPDATE {TABELLE[o['bereich']]} SET ordner_id=NULL WHERE ordner_id IN ({ph})", ids)
        self.x(f"DELETE FROM ordner WHERE id IN ({ph})", ids)

    def ordner_unterbaum(self, oid):
        """IDs des Ordners und aller Unterordner."""
        ids, stack = [], [oid]
        while stack:
            i = stack.pop()
            ids.append(i)
            stack += [r["id"] for r in self.q("SELECT id FROM ordner WHERE parent_id=?", (i,))]
        return ids

    def ordner_id_per_pfad(self, bereich, pfad):
        """Findet oder erzeugt einen Ordner anhand 'Holz / KVH'."""
        parent = None
        for teil in [t.strip() for t in pfad.split("/") if t.strip()]:
            r = self.one("SELECT id FROM ordner WHERE bereich=? AND name=? AND parent_id IS ?", (bereich, teil, parent))
            parent = r["id"] if r else self.ordner_anlegen(bereich, teil, parent)
        return parent

    def verschieben(self, bereich, item_id, ordner_id):
        self.x(f"UPDATE {TABELLE[bereich]} SET ordner_id=? WHERE id=?", (ordner_id, item_id))

    # --- Artikel / Preise ---------------------------------------------------
    def next_artikelnr(self):
        n = 0
        for r in self.q("SELECT nr FROM artikel WHERE nr LIKE 'A-%'"):
            t = r["nr"][2:]
            if t.isdigit():
                n = max(n, int(t))
        return f"A-{n + 1:04d}"

    def artikel_anlegen(self, nr, bezeichnung, einheit="Stk", lieferant="", kategorie="", gewicht=None,
                        volumen=None, lager="", ordner_id=None, preisaufschlag=None, preis=None,
                        gueltig_ab=None, stamm=1, quelle=""):
        if not (bezeichnung or "").strip():
            raise ValueError("Bezeichnung fehlt.")
        aid = self.x("INSERT INTO artikel(nr,bezeichnung,einheit,lieferant,kategorie,gewicht,volumen,lager,"
                     "ordner_id,preisaufschlag,stamm,quelle) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                     ((nr or "").strip() or self.next_artikelnr(), bezeichnung.strip(), einheit or "Stk", lieferant,
                      kategorie, gewicht, volumen, lager, ordner_id, preisaufschlag, stamm, quelle))
        if preis is not None:
            self.preis_setzen(aid, gueltig_ab or today_iso(), preis)
        return aid

    def preis_setzen(self, aid, gueltig_ab, preis):
        self.x("INSERT INTO preise(artikel_id,gueltig_ab,preis) VALUES(?,?,?) "
               "ON CONFLICT(artikel_id,gueltig_ab) DO UPDATE SET preis=excluded.preis", (aid, gueltig_ab, preis))

    def preis_at(self, artikel_id, stichtag):
        """Gültiger Preis zum Stichtag -> (preis, gueltig_ab) oder (None, None)."""
        r = self.one("SELECT preis, gueltig_ab FROM preise WHERE artikel_id=? AND gueltig_ab<=? "
                     "ORDER BY gueltig_ab DESC LIMIT 1", (artikel_id, stichtag or today_iso()))
        return (r["preis"], r["gueltig_ab"]) if r else (None, None)

    # --- Leistungen ---------------------------------------------------------
    def next_leistungsnr(self):
        n = 0
        for r in self.q("SELECT nr FROM leistungen WHERE nr LIKE 'L-%'"):
            t = r["nr"][2:]
            if t.isdigit():
                n = max(n, int(t))
        return f"L-{n + 1:03d}"

    def leistung_duplizieren(self, lid):
        l = self.one("SELECT * FROM leistungen WHERE id=?", (lid,))
        nid = self.x("INSERT INTO leistungen(nr,bezeichnung,einheit,zeit_h,beschreibung,ordner_id) VALUES(?,?,?,?,?,?)",
                     (self.next_leistungsnr(), l["bezeichnung"] + " (Kopie)", l["einheit"], 0, l["beschreibung"], l["ordner_id"]))
        self.x("INSERT INTO leistung_material(leistung_id,artikel_id,menge,verschnitt,bezeichnung,preisaufschlag,menge_fix) "
               "SELECT ?,artikel_id,menge,verschnitt,bezeichnung,preisaufschlag,menge_fix FROM leistung_material WHERE leistung_id=?",
               (nid, lid))
        self.x("INSERT INTO leistung_lohn(leistung_id,bezeichnung,lohnart_id,zeit_h,einheit,menge,satz,menge_fix) "
               "SELECT ?,bezeichnung,lohnart_id,zeit_h,einheit,menge,satz,menge_fix FROM leistung_lohn WHERE leistung_id=?",
               (nid, lid))
        return nid

    # --- Projekte ------------------------------------------------------
    def next_projektnr(self):
        pre = f"P-{date.today().year}-"
        r = self.one("SELECT nr FROM projekte WHERE nr LIKE ? ORDER BY nr DESC LIMIT 1", (pre + "%",))
        n = int(r["nr"].split("-")[-1]) + 1 if r and r["nr"].split("-")[-1].isdigit() else 1
        return f"{pre}{n:03d}"

    def create_projekt(self, nr, bezeichnung, kunde="", status="Entwurf", ort="", datum=None, stichtag=None,
                       aufschlag_override=None):
        pid = self.x("INSERT INTO projekte(nr,bezeichnung,kunde,status,ort,datum,stichtag,geaendert,aufschlag_override) "
                     "VALUES(?,?,?,?,?,?,?,?,?)", (nr, bezeichnung, kunde, status, ort, datum or today_iso(),
                                                   stichtag or today_iso(), now_iso(), aufschlag_override))
        s = self.settings()
        for name, key in (("Gemeinkosten", "gemeinkosten"), ("Gewinnaufschlag", "gewinn"), ("MwSt", "mwst")):
            self.x("INSERT INTO parameter(projekt_id,name,wert,einheit) VALUES(?,?,?,?)",
                   (pid, name, s.get(key, DEFAULT_SETTINGS[key]), "%"))
        return pid

    def touch(self, pid):
        self.x("UPDATE projekte SET geaendert=? WHERE id=?", (now_iso(), pid))

    # --- Snapshots -----------------------------------------------------
    def snapshot_speichern(self, pid, titel, result):
        sid = self.x("INSERT INTO snapshots(projekt_id,erstellt,titel,daten) VALUES(?,?,?,?)",
                     (pid, now_iso(), titel, json.dumps(result, ensure_ascii=False)))
        self.touch(pid)
        return sid

    def snapshot_laden(self, sid):
        r = self.one("SELECT daten FROM snapshots WHERE id=?", (sid,))
        return json.loads(r["daten"]) if r else None

    # --- Dashboard -----------------------------------------------------
    def warnungen(self):
        w = []
        for r in self.q("SELECT a.nr,a.bezeichnung FROM artikel a WHERE NOT EXISTS("
                        "SELECT 1 FROM preise p WHERE p.artikel_id=a.id)"):
            w.append(f"Artikel {r['nr']} ({r['bezeichnung']}) hat keinen Preis.")
        grenze = (date.today() - timedelta(days=365)).isoformat()
        for r in self.q("SELECT a.nr,a.bezeichnung,MAX(p.gueltig_ab) d FROM artikel a JOIN preise p ON p.artikel_id=a.id "
                        "WHERE a.stamm=1 GROUP BY a.id HAVING d < ?", (grenze,)):
            w.append(f"Preis von {r['nr']} ({r['bezeichnung']}) ist älter als 12 Monate.")
        for r in self.q("SELECT l.nr,l.bezeichnung FROM leistungen l WHERE "
                        "NOT EXISTS(SELECT 1 FROM leistung_material m WHERE m.leistung_id=l.id) AND "
                        "NOT EXISTS(SELECT 1 FROM leistung_lohn o WHERE o.leistung_id=l.id)"):
            w.append(f"Leistung {r['nr']} ({r['bezeichnung']}) ist leer (weder Material noch Lohn).")
        return w


# --- Beispieldaten -----------------------------------------------------------------
def seed_demo(db):
    """Legt Beispieldaten an (nur wenn noch keine Artikel existieren)."""
    if db.one("SELECT 1 FROM artikel LIMIT 1"):
        return False
    holz = db.ordner_id_per_pfad("artikel", "Holz")
    daem = db.ordner_id_per_pfad("artikel", "Dämmung")
    bef = db.ordner_id_per_pfad("artikel", "Befestigung")

    def art(nr, bez, ein, lief, ordner, preise, pa=None):
        aid = db.artikel_anlegen(nr, bez, ein, lief, "", ordner_id=ordner, preisaufschlag=pa)
        for d, p in preise:
            db.preis_setzen(aid, d, p)
        return aid
    kvh = art("A-001", "KVH C24 60x120", "m³", "Holzhandel Müller", holz,
              [("2025-01-01", 650.0), ("2025-05-01", 720.0), ("2025-10-01", 695.0)])
    zel = art("A-002", "Zellulosedämmung", "kg", "Dämmstoffe Bayer", daem, [("2025-01-01", 0.85), ("2025-07-01", 0.92)], 6)
    hf = art("A-003", "Holzfaserdämmplatte 100 mm", "m²", "Dämmstoffe Bayer", daem, [("2025-01-01", 18.5), ("2025-09-01", 19.9)])
    sch = art("A-004", "Konstruktionsschrauben", "Stk", "Schraubenhandel Huber", bef, [("2025-01-01", 0.12)])
    zim = db.x("INSERT INTO lohnarten(nr,bezeichnung,satz) VALUES('LA-1','Zimmerer',55)")
    db.x("INSERT INTO lohnarten(nr,bezeichnung,satz) VALUES('LA-2','Helfer',38)")
    o_wand = db.ordner_id_per_pfad("leistung", "Wand")
    o_dach = db.ordner_id_per_pfad("leistung", "Dach")

    def leist(nr, bez, ein, ordner, mats, lohn, text=""):
        lid = db.x("INSERT INTO leistungen(nr,bezeichnung,einheit,beschreibung,ordner_id) VALUES(?,?,?,?,?)",
                   (nr, bez, ein, text, ordner))
        for aid, menge, vs in mats:
            db.x("INSERT INTO leistung_material(leistung_id,artikel_id,menge,verschnitt) VALUES(?,?,?,?)",
                 (lid, aid, menge, vs))
        for bez2, zeit, e2, menge, la in lohn:
            db.x("INSERT INTO leistung_lohn(leistung_id,bezeichnung,lohnart_id,zeit_h,einheit,menge) VALUES(?,?,?,?,?,?)",
                 (lid, bez2, la, zeit, e2, menge))
        return lid
    l1 = leist("L-001", "Holzrahmenwand", "m²", o_wand, [(kvh, "0,045", 8), (zel, "Dämmstärke*40", 3), (sch, "25", 0)],
               [("Abbund und Montage", 1.8, "m²", "1", zim)], "Wandelement inkl. Dämmung")
    l2 = leist("L-002", "Dachdämmung", "m²", o_dach, [(hf, "1", 5)], [("Verlegen", 0.6, "m²", "1", zim)],
               "Aufsparrendämmung Holzfaser")
    l3 = leist("L-003", "Montage nach Aufwand", "h", None, [], [("Montage", 1.0, "h", "1", zim)])
    pid = db.create_projekt("P-DEMO-001", "Einfamilienhaus Beispiel", "Familie Mustermann", "Entwurf", "Straubing",
                            "2025-10-15", "2025-10-15")
    for n, w, e in (("Wandfläche", "120", "m²"), ("Dachfläche", "85", "m²"), ("Dämmstärke", "0,16", "m")):
        db.x("INSERT INTO parameter(projekt_id,name,wert,einheit) VALUES(?,?,?,?)", (pid, n, w, e))
    for i, (lid, m) in enumerate(((l1, "Wandfläche"), (l2, "Dachfläche"), (l3, "16"))):
        db.x("INSERT INTO positionen(projekt_id,leistung_id,menge,sort) VALUES(?,?,?,?)", (pid, lid, m, i))
    return True
