"""Stammdaten: Artikel (mit Ordnern, Preishistorie, Import) und Löhne (Stundenverrechnungssätze)."""
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import importer, theme
from .util import (eur, parse_pct, parse_zahl, parse_zahl_opt, pct, to_de, to_iso, today_iso, zahl, zahl_kurz)
from .widgets import FolderTree, TreeList, ask, buttons, fehler, zentrieren

EINHEITEN = ["Stk", "m", "lfm", "m²", "m³", "kg", "t", "l", "h", "Psch", "Pkt", "Satz"]
KEIN_ORDNER = "– kein Ordner –"


def ordner_auswahl(db, bereich):
    """-> (Liste der Anzeigenamen, {Anzeigename: id})"""
    pf = db.ordner_pfade(bereich)
    m = {KEIN_ORDNER: None}
    m.update({p: i for i, p in pf})
    return [KEIN_ORDNER] + [p for _, p in pf], m


def artikel_items(db, such, nur_stamm=True):
    s = f"%{such}%"
    out = []
    for r in db.q("SELECT * FROM artikel WHERE (?=0 OR stamm=1) AND (nr LIKE ? OR bezeichnung LIKE ? OR lieferant LIKE ? "
                  "OR kategorie LIKE ?) ORDER BY bezeichnung COLLATE NOCASE", (1 if nur_stamm else 0, s, s, s, s)):
        p, d = db.preis_at(r["id"], today_iso())
        marke = f"  {theme.S_STERN}" if r["quelle"] == "Leistung" else ""
        out.append((r["id"], r["ordner_id"], r["bezeichnung"] + marke,
                    (r["nr"], r["einheit"], r["lieferant"], pct(r["preisaufschlag"]) if r["preisaufschlag"] is not None else "Standard",
                     f"{zahl(p)} €/{r['einheit']}" if p is not None else "–", to_de(d), r["quelle"]),
                    ("stern",) if r["quelle"] == "Leistung" else ()))
    return out


ARTIKEL_SPALTEN = [("nr", "Artikelnr.", 90, "w"), ("ein", "Einheit", 60, "w"), ("lief", "Lieferant", 140, "w"),
                   ("pa", "Preisaufschl.", 90, "e"), ("preis", "Preis (EK netto)", 120, "e"),
                   ("ab", "Gültig ab", 85, "w"), ("quelle", "Herkunft", 70, "w")]


def artikel_neu(app, parent, ordner_id=None, in_leistung=False):
    """Dialog 'Neuer Artikel'. In der Leistungserstellung mit Option 'Auch in Stammdaten speichern'. -> artikel_id | None"""
    db = app.db
    namen, mp = ordner_auswahl(db, "artikel")
    felder = [("nr", "Artikelnummer (leer = automatisch)"), ("bezeichnung", "Bezeichnung"),
              ("einheit", "Einheit", "combo", EINHEITEN), ("ordner", "Ordner", "choice", namen),
              ("lieferant", "Lieferant"), ("preis", "Preis (EK netto, € je Einheit)"), ("ab", "Preis gültig ab (TT.MM.JJJJ)"),
              ("pa", f"Preisaufschlag % (leer = Standard {db.get_setting('aufschlag')} %)"), ("kategorie", "Kategorie"),
              ("gewicht", "Gewicht (kg je Einheit)"), ("volumen", "Volumen (m³ je Einheit)"), ("lager", "Lagerinformationen")]
    vals = {"einheit": "Stk", "ab": to_de(today_iso()), "ordner": db.ordner_pfad("artikel", ordner_id) or KEIN_ORDNER}
    hint = None
    if in_leistung:
        felder.append(("stamm", f"Auch in den Stammdaten speichern (dort mit {theme.S_STERN} gekennzeichnet)", "check"))
        vals["stamm"] = True
        hint = "Ohne Haken gilt der Artikel nur in dieser Leistung und erscheint nicht in den Stammdaten."
    v = ask(app.root if parent is None else parent, "Neuer Artikel", felder, vals, hint)
    if not v:
        return None
    try:
        stamm = 1 if v.get("stamm", True) else 0
        return db.artikel_anlegen(
            v["nr"], v["bezeichnung"], v["einheit"], v["lieferant"], v["kategorie"], parse_zahl_opt(v["gewicht"]),
            parse_zahl_opt(v["volumen"]), v["lager"], mp.get(v["ordner"]) if stamm else None, parse_pct(v["pa"]),
            parse_zahl(v["preis"]) if v["preis"] else None, to_iso(v["ab"]) or today_iso(), stamm,
            "Leistung" if in_leistung and stamm else "")
    except Exception as e:
        fehler(parent or app.root, e)
        return None


class ArtikelView(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app
        buttons(self, [(f"{theme.S_NEU} Artikel", self.neu, True), (f"{theme.S_EDIT} Bearbeiten", self.edit),
                       ("Preise / Historie", self.preise), (f"{theme.S_NEU} Ordner", self.ordner_neu),
                       ("Ordner umbenennen", self.ordner_rename), ("In Ordner …", self.verschieben),
                       (f"{theme.S_DEL} Löschen", self.loeschen), (f"{theme.S_IMPORT} Import", self.importieren)]
                ).pack(anchor="w", pady=(0, 8))
        self.ft = FolderTree(self, app.db, "artikel", ARTIKEL_SPALTEN, lambda s: artikel_items(app.db, s))
        self.ft.pack(fill="both", expand=True)
        self.ft.on_open = lambda i: self.preise()
        ttk.Label(self, text=f"{theme.S_STERN} = aus einer Leistung heraus angelegt.   Doppelklick: Preise und Historie.",
                  style="Sub.TLabel").pack(anchor="w", pady=(6, 0))

    def refresh(self):
        self.ft.refresh()

    def neu(self):
        aid = artikel_neu(self.app, None, self.ft.target_folder())
        if aid:
            self.app.refresh_all()
            self.ft.select_item(aid)

    def edit(self):
        aid = self.ft.sel_item()
        if not aid:
            return
        db = self.app.db
        r = db.one("SELECT * FROM artikel WHERE id=?", (aid,))
        namen, mp = ordner_auswahl(db, "artikel")
        vals = dict(r)
        vals.update(ordner=db.ordner_pfad("artikel", r["ordner_id"]) or KEIN_ORDNER, pa=zahl_kurz(r["preisaufschlag"]) if r["preisaufschlag"] is not None else "",
                    gewicht=zahl_kurz(r["gewicht"]) if r["gewicht"] is not None else "",
                    volumen=zahl_kurz(r["volumen"]) if r["volumen"] is not None else "")
        v = ask(self.app.root, "Artikel bearbeiten", [
            ("nr", "Artikelnummer"), ("bezeichnung", "Bezeichnung"), ("einheit", "Einheit", "combo", EINHEITEN),
            ("ordner", "Ordner", "choice", namen), ("lieferant", "Lieferant"), ("kategorie", "Kategorie"),
            ("pa", f"Preisaufschlag % (leer = Standard {db.get_setting('aufschlag')} %)"),
            ("gewicht", "Gewicht (kg je Einheit)"), ("volumen", "Volumen (m³ je Einheit)"), ("lager", "Lagerinformationen")], vals)
        if v:
            try:
                db.x("UPDATE artikel SET nr=?,bezeichnung=?,einheit=?,ordner_id=?,lieferant=?,kategorie=?,preisaufschlag=?,"
                     "gewicht=?,volumen=?,lager=? WHERE id=?",
                     (v["nr"], v["bezeichnung"], v["einheit"], mp.get(v["ordner"]), v["lieferant"], v["kategorie"],
                      parse_pct(v["pa"]), parse_zahl_opt(v["gewicht"]), parse_zahl_opt(v["volumen"]), v["lager"], aid))
            except Exception as e:
                return fehler(self.app.root, e)
            self.app.refresh_all()

    def preise(self):
        aid = self.ft.sel_item()
        if aid:
            PreisWindow(self.app, aid)

    def ordner_neu(self):
        v = ask(self.app.root, "Neuer Ordner", [("name", "Name des Ordners (z. B. Holz)")],
                hint="Der Ordner wird in dem aktuell gewählten Ordner angelegt (sonst auf oberster Ebene).")
        if v:
            try:
                self.app.db.ordner_anlegen("artikel", v["name"], self.ft.sel_folder() or (self.ft.target_folder()))
            except Exception as e:
                return fehler(self.app.root, e)
            self.app.refresh_all()

    def ordner_rename(self):
        oid = self.ft.sel_folder()
        if not oid:
            return messagebox.showinfo("Hinweis", "Bitte zuerst einen Ordner auswählen.", parent=self.app.root)
        o = self.app.db.one("SELECT name FROM ordner WHERE id=?", (oid,))
        v = ask(self.app.root, "Ordner umbenennen", [("name", "Neuer Name")], {"name": o["name"]})
        if v:
            try:
                self.app.db.ordner_umbenennen(oid, v["name"])
            except Exception as e:
                return fehler(self.app.root, e)
            self.app.refresh_all()

    def verschieben(self):
        aid = self.ft.sel_item()
        if not aid:
            return messagebox.showinfo("Hinweis", "Bitte zuerst einen Artikel auswählen.", parent=self.app.root)
        namen, mp = ordner_auswahl(self.app.db, "artikel")
        v = ask(self.app.root, "In Ordner verschieben", [("ordner", "Zielordner", "choice", namen)])
        if v:
            self.app.db.verschieben("artikel", aid, mp.get(v["ordner"]))
            self.app.refresh_all()

    def loeschen(self):
        aid, oid = self.ft.sel_item(), self.ft.sel_folder()
        if aid and messagebox.askyesno("Artikel löschen", "Artikel inkl. Preishistorie löschen?", parent=self.app.root):
            try:
                self.app.db.x("DELETE FROM artikel WHERE id=?", (aid,))
            except Exception as e:
                return fehler(self.app.root, e)
            self.app.refresh_all()
        elif oid and messagebox.askyesno("Ordner löschen", "Ordner samt Unterordnern löschen?\n(Die Artikel bleiben erhalten "
                                         "und liegen danach auf der obersten Ebene.)", parent=self.app.root):
            self.app.db.ordner_loeschen(oid)
            self.app.refresh_all()

    def importieren(self):
        ImportDialog(self.app)


class PreisWindow(tk.Toplevel):
    def __init__(self, app, aid):
        super().__init__(app.root)
        self.app, self.aid = app, aid
        a = app.db.one("SELECT * FROM artikel WHERE id=?", (aid,))
        self.title(f"Preishistorie – {a['nr']} {a['bezeichnung']}")
        self.geometry("540x400")
        self.configure(bg=theme.BG)
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text=f"EK-Preise in € je {a['einheit']}. Kalkulationen rechnen mit dem Preis, der zu ihrem "
                          "Preisstichtag galt.", wraplength=500, style="Sub.TLabel").pack(anchor="w", pady=(0, 8))
        buttons(f, [(f"{theme.S_NEU} Neuer Preisstand", self.neu, True), (f"{theme.S_EDIT} Ändern", self.edit),
                    (f"{theme.S_DEL} Löschen", self.loeschen)]).pack(anchor="w", pady=(0, 6))
        self.t = TreeList(f, [("ab", "Gültig ab", 120, "w"), ("preis", "Preis", 110, "e"), ("diff", "Änderung", 100, "e")], height=10)
        self.t.pack(fill="both", expand=True)
        self.refresh()

    def refresh(self):
        rows, prev = [], None
        for r in self.app.db.q("SELECT * FROM preise WHERE artikel_id=? ORDER BY gueltig_ab", (self.aid,)):
            diff = "" if not prev else f"{(r['preis'] / prev - 1) * 100:+.1f} %".replace(".", ",")
            rows.append((r["id"], (to_de(r["gueltig_ab"]), zahl(r["preis"]) + " €", diff)))
            prev = r["preis"]
        self.t.fill(list(reversed(rows)))

    def _ask(self, vals=None):
        v = ask(self, "Preisstand", [("ab", "Gültig ab (TT.MM.JJJJ)"), ("preis", "Preis (€)")], vals)
        if not v:
            return None
        try:
            return to_iso(v["ab"]) or today_iso(), parse_zahl(v["preis"])
        except Exception as e:
            fehler(self, e)

    def neu(self):
        r = self._ask({"ab": to_de(today_iso())})
        if r:
            try:
                self.app.db.preis_setzen(self.aid, r[0], r[1])
            except Exception as e:
                return fehler(self, e)
            self.refresh()
            self.app.refresh_all()

    def edit(self):
        pid = self.t.selected()
        if not pid:
            return
        o = self.app.db.one("SELECT * FROM preise WHERE id=?", (pid,))
        r = self._ask({"ab": to_de(o["gueltig_ab"]), "preis": zahl(o["preis"])})
        if r:
            try:
                self.app.db.x("UPDATE preise SET gueltig_ab=?,preis=? WHERE id=?", (r[0], r[1], pid))
            except Exception as e:
                return fehler(self, e)
            self.refresh()
            self.app.refresh_all()

    def loeschen(self):
        pid = self.t.selected()
        if pid and messagebox.askyesno("Löschen", "Preisstand löschen?", parent=self):
            self.app.db.x("DELETE FROM preise WHERE id=?", (pid,))
            self.refresh()
            self.app.refresh_all()


class ArtikelPicker(tk.Toplevel):
    """Auswahl eines Artikels über die Ordnerstruktur (z. B. Ordner 'Holz' -> 'KVH')."""

    def __init__(self, app, parent):
        super().__init__(parent)
        self.app, self.result = app, None
        self.title("Artikel auswählen")
        self.geometry("920x520")
        self.configure(bg=theme.BG)
        self.transient(parent)
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Ordner öffnen und Artikel wählen (Doppelklick oder „Übernehmen“).", style="Sub.TLabel").pack(anchor="w")
        self.ft = FolderTree(f, app.db, "artikel", ARTIKEL_SPALTEN, lambda s: artikel_items(app.db, s))
        self.ft.pack(fill="both", expand=True, pady=6)
        self.ft.on_open = lambda i: self.ok()
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        ttk.Button(bar, text=f"{theme.S_NEU} Neuer Artikel …", command=self.neu).pack(side="left")
        ttk.Button(bar, text="Abbrechen", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(bar, text="Übernehmen", style="Accent.TButton", command=self.ok).pack(side="right")
        self.ft.refresh()
        zentrieren(self, parent)
        try:
            self.wait_visibility()
            self.grab_set()
        except Exception:
            pass
        self.wait_window(self)

    def ok(self):
        self.result = self.ft.sel_item()
        if self.result:
            self.destroy()

    def neu(self):
        aid = artikel_neu(self.app, self, self.ft.target_folder(), in_leistung=True)
        if aid:
            self.result = aid
            self.destroy()


class LoehneView(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app
        top = ttk.LabelFrame(self, text="Standard-Stundenverrechnungssatz", padding=10)
        top.pack(fill="x", pady=(0, 10))
        self.std = ttk.Label(top, style="Big.TLabel")
        self.std.pack(side="left")
        ttk.Button(top, text=f"{theme.S_EDIT} ändern", command=self.std_aendern).pack(side="left", padx=14)
        ttk.Label(top, text="Gilt für Lohnanteile ohne eigenen Satz und ohne Lohnart.", style="Sub.TLabel").pack(side="left")
        buttons(self, [(f"{theme.S_NEU} Lohnart", self.neu, True), (f"{theme.S_EDIT} Bearbeiten", self.edit),
                       (f"{theme.S_DEL} Löschen", self.loeschen)]).pack(anchor="w", pady=(0, 8))
        self.t = TreeList(self, [("nr", "Nr.", 80, "w"), ("bez", "Lohnart / Qualifikation", 320, "w"),
                                 ("satz", "Stundenverrechnungssatz", 180, "e"), ("verw", "Verwendet in", 120, "e")])
        self.t.pack(fill="both", expand=True)
        self.t.on_double(self.edit)
        ttk.Label(self, text="Ändert sich ein Satz, rechnen alle Leistungen mit dieser Lohnart künftig automatisch mit dem neuen Satz. "
                             "Bereits gespeicherte Snapshots bleiben unverändert.", style="Sub.TLabel", wraplength=900
                  ).pack(anchor="w", pady=(6, 0))

    def refresh(self):
        self.std.config(text=f"{zahl(parse_zahl(self.app.db.get_setting('lohnsatz')))} €/h")
        self.t.fill([(r["id"], (r["nr"], r["bezeichnung"], f"{zahl(r['satz'])} €/h", r["n"])) for r in self.app.db.q(
            "SELECT l.*, (SELECT COUNT(*) FROM leistung_lohn o WHERE o.lohnart_id=l.id) n FROM lohnarten l ORDER BY l.bezeichnung")])

    def std_aendern(self):
        v = ask(self.app.root, "Standard-Stundenverrechnungssatz", [("satz", "Satz (€/h)")],
                {"satz": zahl(parse_zahl(self.app.db.get_setting("lohnsatz")))})
        if v:
            try:
                self.app.db.set_setting("lohnsatz", parse_zahl(v["satz"]))
            except Exception as e:
                return fehler(self.app.root, e)
            self.app.refresh_all()

    def _dlg(self, vals):
        return ask(self.app.root, "Lohnart", [("nr", "Nr."), ("bez", "Bezeichnung (z. B. Zimmerer)"), ("satz", "Stundenverrechnungssatz (€/h)")], vals)

    def neu(self):
        v = self._dlg({"satz": zahl(parse_zahl(self.app.db.get_setting("lohnsatz")))})
        if v:
            try:
                if not v["bez"]:
                    raise ValueError("Bezeichnung fehlt.")
                self.app.db.x("INSERT INTO lohnarten(nr,bezeichnung,satz) VALUES(?,?,?)", (v["nr"], v["bez"], parse_zahl(v["satz"])))
            except Exception as e:
                return fehler(self.app.root, e)
            self.app.refresh_all()

    def edit(self):
        i = self.t.selected()
        if not i:
            return
        r = self.app.db.one("SELECT * FROM lohnarten WHERE id=?", (i,))
        v = self._dlg({"nr": r["nr"], "bez": r["bezeichnung"], "satz": zahl(r["satz"])})
        if v:
            try:
                self.app.db.x("UPDATE lohnarten SET nr=?,bezeichnung=?,satz=? WHERE id=?", (v["nr"], v["bez"], parse_zahl(v["satz"]), i))
            except Exception as e:
                return fehler(self.app.root, e)
            self.app.refresh_all()

    def loeschen(self):
        i = self.t.selected()
        if i and messagebox.askyesno("Löschen", "Lohnart löschen? Leistungen mit dieser Lohnart rechnen danach mit dem Standardsatz.", parent=self.app.root):
            self.app.db.x("UPDATE leistung_lohn SET lohnart_id=NULL WHERE lohnart_id=?", (i,))
            self.app.db.x("DELETE FROM lohnarten WHERE id=?", (i,))
            self.app.refresh_all()


class StammdatenTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=6)
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        self.artikel = ArtikelView(nb, app)
        self.loehne = LoehneView(nb, app)
        nb.add(self.artikel, text="Artikel")
        nb.add(self.loehne, text="Löhne")

    def refresh(self):
        self.artikel.refresh()
        self.loehne.refresh()


class ImportDialog(tk.Toplevel):
    """Artikelimport aus Onlineshop-/Lieferantendateien (CSV, Excel) mit Spaltenzuordnung."""

    def __init__(self, app):
        super().__init__(app.root)
        self.app, self.kopf, self.zeilen = app, [], []
        self.title("Artikel importieren")
        self.geometry("860x640")
        self.configure(bg=theme.BG)
        self.transient(app.root)
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="1. Datei wählen (Datanorm, CSV oder Excel aus Onlineshop / Lieferant)", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=6)
        ttk.Button(row, text=f"{theme.S_IMPORT} Datei öffnen …", style="Accent.TButton", command=self.datei).pack(side="left")
        self.dname = ttk.Label(row, text="  noch keine Datei", style="Sub.TLabel")
        self.dname.pack(side="left")
        ttk.Label(f, text="2. Spalten zuordnen", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 0))
        self.map_frame = ttk.Frame(f)
        self.map_frame.pack(fill="x", pady=4)
        self.vorschau = ttk.Frame(f)
        self.vorschau.pack(fill="both", expand=True, pady=6)
        ttk.Label(f, text="3. Optionen", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        o = ttk.Frame(f)
        o.pack(fill="x", pady=4)
        namen, self.ordner_map = ordner_auswahl(app.db, "artikel")
        self.v_ordner = tk.StringVar(value=KEIN_ORDNER)
        self.v_neu = tk.StringVar()
        self.v_ab = tk.StringVar(value=to_de(today_iso()))
        self.v_lief = tk.StringVar()
        self.v_pa = tk.StringVar()
        self.v_rab = tk.StringVar()
        self.v_upd = tk.BooleanVar(value=True)
        for i, (lab, w) in enumerate((
                ("Zielordner", ttk.Combobox(o, textvariable=self.v_ordner, values=namen, state="readonly", width=34)),
                ("oder neuer Ordner (z. B. Holz / Latten)", ttk.Entry(o, textvariable=self.v_neu, width=36)),
                ("Preise gültig ab", ttk.Entry(o, textvariable=self.v_ab, width=14)),
                ("Lieferant (falls nicht in Datei)", ttk.Entry(o, textvariable=self.v_lief, width=24)),
                ("Preisaufschlag % für alle (leer = Standard)", ttk.Entry(o, textvariable=self.v_pa, width=10)),
                ("Rabatt % auf die Dateipreise (z. B. Lieferantenrabatt auf Listenpreise)", ttk.Entry(o, textvariable=self.v_rab, width=10)))):
            ttk.Label(o, text=lab).grid(row=i, column=0, sticky="w", padx=(0, 10), pady=2)
            w.grid(row=i, column=1, sticky="w", pady=2)
        ttk.Checkbutton(o, text="Vorhandene Artikel (gleiche Artikelnr.) aktualisieren: neuer Preisstand, alte Stände bleiben erhalten",
                        variable=self.v_upd).grid(row=6, column=0, columnspan=2, sticky="w", pady=4)
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(8, 0))
        ttk.Button(bar, text="Schließen", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(bar, text="Import starten", style="Accent.TButton", command=self.start).pack(side="right")
        self.combos = {}
        zentrieren(self, app.root)

    def datei(self):
        p = filedialog.askopenfilename(parent=self, filetypes=[("Tabellen und Datanorm", "*.csv *.txt *.xlsx *.xlsm *.001 *.002 *.003 *.dat *.asc"), ("Alle Dateien", "*.*")])
        if not p:
            return
        try:
            self.kopf, self.zeilen = importer.lese_tabelle(p)
        except Exception as e:
            return fehler(self, e)
        self.dname.config(text=f"  {p}  ({len(self.zeilen)} Zeilen)")
        for w in self.map_frame.winfo_children():
            w.destroy()
        vor = importer.vorschlag(self.kopf)
        opts = ["– nicht importieren –"] + self.kopf
        self.combos = {}
        for i, (key, label, pflicht, _) in enumerate(importer.FELDER):
            ttk.Label(self.map_frame, text=label + (" *" if pflicht else "")).grid(row=i // 2, column=(i % 2) * 2, sticky="w", padx=(0, 8), pady=2)
            var = tk.StringVar(value=self.kopf[vor[key]] if key in vor else opts[0])
            ttk.Combobox(self.map_frame, textvariable=var, values=opts, state="readonly", width=28).grid(
                row=i // 2, column=(i % 2) * 2 + 1, sticky="w", padx=(0, 18), pady=2)
            self.combos[key] = var
        for w in self.vorschau.winfo_children():
            w.destroy()
        cols = [(f"c{i}", k, 110, "w") for i, k in enumerate(self.kopf[:8])]
        t = TreeList(self.vorschau, cols, height=5)
        t.pack(fill="both", expand=True)
        for n, z in enumerate(self.zeilen[:6]):
            t.tree.insert("", "end", iid=str(n), values=[c for c in z[:8]])

    def start(self):
        if not self.zeilen:
            return messagebox.showinfo("Hinweis", "Bitte zuerst eine Datei öffnen.", parent=self)
        mapping = {k: self.kopf.index(v.get()) for k, v in self.combos.items() if v.get() in self.kopf}
        try:
            db = self.app.db
            oid = db.ordner_id_per_pfad("artikel", self.v_neu.get()) if self.v_neu.get().strip() else self.ordner_map.get(self.v_ordner.get())
            res = importer.importiere(db, self.zeilen, mapping, oid, to_iso(self.v_ab.get()) or today_iso(),
                                      self.v_lief.get().strip(), parse_pct(self.v_pa.get()), self.v_upd.get(),
                                      rabatt=parse_pct(self.v_rab.get()) or 0.0)
        except Exception as e:
            return fehler(self, e)
        self.app.refresh_all()
        txt = (f"Neu angelegt: {res['neu']}\nPreis aktualisiert: {res['aktualisiert']}\nUnverändert/übersprungen: {res['unveraendert']}\n"
               f"Fehlerhafte Zeilen: {len(res['fehler'])}")
        if res["fehler"]:
            txt += "\n\n" + "\n".join(res["fehler"][:8])
        messagebox.showinfo("Import abgeschlossen", txt, parent=self)
