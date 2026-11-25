"""Leistungen: Ordnerbaum, Editor im WGsystem-Stil (Direktbearbeitung per Mausklick), Analyse, KWP-Export."""
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import datanorm, export, parameter, theme
from .calc import FormelFehler, berechne_leistung, eval_parameter, evaluate
from .ui_stamm import EINHEITEN, KEIN_ORDNER, ArtikelPicker, PreisWindow, artikel_neu, ordner_auswahl
from .util import (eur, fmt_zeit, parse_pct, parse_zahl, parse_zeit, pct, preis_fmt, to_de, today_iso, zahl,
                   zahl_kurz)
from .widgets import CellEditor, FolderTree, ask, buttons, fehler, zentrieren

SPALTEN = [("menge", "Menge", 95, "e"), ("ma", "Mengenaufschl.", 100, "e"), ("ek", "EK netto", 110, "e"),
           ("pa", "Preisaufschl.", 95, "e"), ("vk", "VK netto", 110, "e"), ("pje", "Preis je Einheit", 120, "e"),
           ("zeit", "Gesamtzeit", 105, "e"), ("preis", "Preis (VK netto)", 115, "e")]
SPALTENNAMEN = [s[0] for s in SPALTEN]


def leistung_items(db, such):
    s = f"%{such}%"
    out = []
    for r in db.q("SELECT * FROM leistungen WHERE nr LIKE ? OR bezeichnung LIKE ? ORDER BY bezeichnung COLLATE NOCASE", (s, s)):
        try:
            z = berechne_leistung(db, r["id"], 1.0)
            ek, vk, zt = f"{zahl(z['summe_ek'])} €/{r['einheit']}", f"{zahl(z['summe'])} €/{r['einheit']}", fmt_zeit(z["stunden"])
        except Exception:
            ek = vk = zt = "?"
        out.append((r["id"], r["ordner_id"], r["bezeichnung"], (r["nr"], r["einheit"], ek, vk, zt), ()))
    return out


LEISTUNG_SPALTEN = [("nr", "Leistungsnr.", 95, "w"), ("ein", "Einheit", 65, "w"), ("ek", "EP (EK netto)", 120, "e"),
                    ("vk", "EP (VK netto)", 120, "e"), ("zeit", "Zeit je Einheit", 120, "e")]


class LeistungenTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app
        buttons(self, [(f"{theme.S_NEU} Leistung", self.neu, True), (f"{theme.S_EDIT} Bearbeiten", self.edit),
                       ("Duplizieren", self.dupl), (f"{theme.S_NEU} Ordner", self.ordner_neu),
                       ("Ordner umbenennen", self.ordner_rename), ("In Ordner …", self.verschieben),
                       (f"{theme.S_DEL} Löschen", self.loeschen), (f"{theme.S_EXPORT} CSV-Export (KWP)", self.exportieren)]
                ).pack(anchor="w", pady=(0, 8))
        self.ft = FolderTree(self, app.db, "leistung", LEISTUNG_SPALTEN, lambda s: leistung_items(app.db, s))
        self.ft.pack(fill="both", expand=True)
        self.ft.on_open = lambda i: self.edit()

    def refresh(self):
        self.ft.refresh()

    def neu(self):
        db = self.app.db
        namen, mp = ordner_auswahl(db, "leistung")
        o = db.ordner_pfad("leistung", self.ft.target_folder()) or KEIN_ORDNER
        v = ask(self.app.root, "Neue Leistung", [("nr", "Leistungsnummer"), ("bezeichnung", "Bezeichnung"),
                                                 ("einheit", "Einheit (Bezugsgröße)", "combo", EINHEITEN),
                                                 ("ordner", "Ordner", "choice", namen)],
                {"nr": db.next_leistungsnr(), "einheit": "m²", "ordner": o},
                hint="Material und Lohnanteile fügst du danach im Editor hinzu.")
        if not v:
            return
        try:
            if not v["bezeichnung"]:
                raise ValueError("Bezeichnung fehlt.")
            lid = db.x("INSERT INTO leistungen(nr,bezeichnung,einheit,ordner_id) VALUES(?,?,?,?)",
                       (v["nr"] or db.next_leistungsnr(), v["bezeichnung"], v["einheit"] or "m²", mp.get(v["ordner"])))
        except Exception as e:
            return fehler(self.app.root, e)
        self.app.refresh_all()
        LeistungWindow(self.app, lid)

    def edit(self):
        lid = self.ft.sel_item()
        if lid:
            LeistungWindow(self.app, lid)

    def dupl(self):
        lid = self.ft.sel_item()
        if lid:
            self.app.db.leistung_duplizieren(lid)
            self.app.refresh_all()

    def ordner_neu(self):
        v = ask(self.app.root, "Neuer Ordner", [("name", "Name des Ordners (z. B. Dach)")],
                hint="Der Ordner wird im aktuell gewählten Ordner angelegt (sonst auf oberster Ebene).")
        if v:
            try:
                self.app.db.ordner_anlegen("leistung", v["name"], self.ft.sel_folder() or self.ft.target_folder())
            except Exception as e:
                return fehler(self.app.root, e)
            self.app.refresh_all()

    def ordner_rename(self):
        oid = self.ft.sel_folder()
        if not oid:
            return messagebox.showinfo("Hinweis", "Bitte zuerst einen Ordner auswählen.", parent=self.app.root)
        v = ask(self.app.root, "Ordner umbenennen", [("name", "Neuer Name")], {"name": self.app.db.one("SELECT name FROM ordner WHERE id=?", (oid,))["name"]})
        if v:
            try:
                self.app.db.ordner_umbenennen(oid, v["name"])
            except Exception as e:
                return fehler(self.app.root, e)
            self.app.refresh_all()

    def verschieben(self):
        lid = self.ft.sel_item()
        if not lid:
            return messagebox.showinfo("Hinweis", "Bitte zuerst eine Leistung auswählen.", parent=self.app.root)
        namen, mp = ordner_auswahl(self.app.db, "leistung")
        v = ask(self.app.root, "In Ordner verschieben", [("ordner", "Zielordner", "choice", namen)])
        if v:
            self.app.db.verschieben("leistung", lid, mp.get(v["ordner"]))
            self.app.refresh_all()

    def loeschen(self):
        lid, oid = self.ft.sel_item(), self.ft.sel_folder()
        if lid and messagebox.askyesno("Leistung löschen", "Leistung inkl. Material und Lohnanteilen löschen?", parent=self.app.root):
            try:
                self.app.db.x("DELETE FROM leistungen WHERE id=?", (lid,))
            except Exception as e:
                return fehler(self.app.root, e)
            self.app.refresh_all()
        elif oid and messagebox.askyesno("Ordner löschen", "Ordner samt Unterordnern löschen?\n(Die Leistungen bleiben erhalten.)", parent=self.app.root):
            self.app.db.ordner_loeschen(oid)
            self.app.refresh_all()

    def exportieren(self):
        ExportDialog(self.app, self.ft.sel_item(), self.ft.sel_folder())


class ExportDialog:
    """CSV-Export der Leistungen (Beschreibung, EP, Zeitanteil, Einheit, Material-/Lohnanteile)."""

    def __init__(self, app, lid, oid):
        db = app.db
        umfang = ["Alle Leistungen"]
        if oid:
            umfang.append("Gewählter Ordner (inkl. Unterordner)")
        if lid:
            umfang.append("Nur gewählte Leistung")
        v = ask(app.root, "Export für KWP / ERP", [
            ("format", "Format", "choice", ["Datanorm (Semikolon-Format, Version 4)", "CSV (Tabelle)"]), ("umfang", "Umfang", "choice", umfang), ("trenner", "Trennzeichen", "choice", ["Semikolon ;", "Komma ,", "Tabulator"]),
            ("kod", "Zeichensatz", "choice", ["Windows-1252 (Excel / ERP)", "UTF-8"]),
            ("dez", "Dezimalzeichen", "choice", ["Komma ,", "Punkt ."]),
            ("bst", "Zusätzlich Datei mit Bausteinen (Material / Lohn je Leistung)", "check")],
            {"format": "Datanorm (Semikolon-Format, Version 4)", "umfang": umfang[-1], "trenner": "Semikolon ;", "kod": "Windows-1252 (Excel / ERP)", "dez": "Komma ,", "bst": True},
            hint="Datanorm: Nr., Kurztext, Einheit, Einheitspreis (VK netto). ACHTUNG: Dieses Semikolon-Format ist Datanorm Version 4. KWP muss auf "
                 "Version 4 stehen, bei Version 3 (fester Satzaufbau) wird die Datei nicht gelesen. Trennzeichen/Dezimalzeichen/Zeichensatz gelten nur für CSV.", ok_text="Weiter …")
        if not v:
            return
        if v["umfang"].startswith("Gewählter"):
            ids = [r["id"] for r in db.q(f"SELECT id FROM leistungen WHERE ordner_id IN ({','.join('?' * len(db.ordner_unterbaum(oid)))}) ORDER BY nr", db.ordner_unterbaum(oid))]
        elif v["umfang"].startswith("Nur"):
            ids = [lid]
        else:
            ids = [r["id"] for r in db.q("SELECT id FROM leistungen ORDER BY nr")]
        if not ids:
            return messagebox.showinfo("Export", "Keine Leistungen zum Exportieren.", parent=app.root)
        dn = v["format"].startswith("Datanorm")
        pfad = filedialog.asksaveasfilename(parent=app.root, defaultextension=".001" if dn else ".csv",
                                            filetypes=[("Datanorm", "*.001")] if dn else [("CSV", "*.csv")],
                                            initialfile="DATANORM.001" if dn else f"HBK_Leistungen_{today_iso()}.csv")
        if not pfad:
            return
        try:
            if dn:
                d = datanorm.schreibe_datanorm(db, ids, pfad, today_iso())
                return messagebox.showinfo("Export", f"{len(ids)} Leistung(en) als Datanorm exportiert:\n\n" + "\n".join(d), parent=app.root)
            d = export.export_leistungen(db, ids, pfad, {"S": ";", "K": ",", "T": "\t"}[v["trenner"][0]],
                                         "utf-8-sig" if v["kod"] == "UTF-8" else "cp1252", "," if v["dez"].startswith("K") else ".",
                                         v["bst"], today_iso())
        except Exception as e:
            return fehler(app.root, e)
        messagebox.showinfo("Export", f"{len(ids)} Leistung(en) exportiert:\n\n" + "\n".join(d), parent=app.root)


class LohnDialog:
    """Lohnanteil erzeugen/ändern (Bezeichnung, Zeit, Einheit, Stundensatz, Menge fix) – wie im WGsystem."""

    def __init__(self, app, parent, lid, lohn_id=None):
        db = app.db
        la = db.q("SELECT * FROM lohnarten ORDER BY bezeichnung")
        namen = ["– Standardsatz –"] + [f"{r['bezeichnung']} ({zahl(r['satz'])} €/h)" for r in la]
        vals = {"bez": "Lohnanteil", "zeit": fmt_zeit(1.0), "einheit": db.one("SELECT einheit FROM leistungen WHERE id=?", (lid,))["einheit"],
                "menge": "1", "art": namen[0], "fix": False}
        if lohn_id:
            o = db.one("SELECT * FROM leistung_lohn WHERE id=?", (lohn_id,))
            art = next((n for r, n in zip(la, namen[1:]) if r["id"] == o["lohnart_id"]), namen[0])
            vals = {"bez": o["bezeichnung"], "zeit": fmt_zeit(o["zeit_h"]), "einheit": o["einheit"], "menge": o["menge"],
                    "art": art, "satz": "" if o["satz"] is None else zahl(o["satz"]), "fix": bool(o["menge_fix"])}
        v = ask(parent, "Lohnanteil erzeugen" if not lohn_id else "Lohnanteil ändern", [
            ("bez", "Bezeichnung"), ("zeit", "Zeit je Einheit (z. B. 01 h 30 min)"),
            ("einheit", "Einheit", "combo", EINHEITEN), ("menge", "Menge je Leistungseinheit"),
            ("art", "Lohnart", "choice", namen), ("satz", "Stundensatz € (leer = Satz der Lohnart bzw. Standardsatz)"),
            ("fix", "Menge fix (nicht mit der Leistungsmenge multiplizieren)", "check")], vals,
            hint=f"Standard-Stundenverrechnungssatz: {zahl(parse_zahl(db.get_setting('lohnsatz')))} €/h. "
                 "Beispiel: 0:30 h je m² bedeutet 30 Minuten pro m² Leistung.", ok_text="Speichern")
        self.ok = False
        if not v:
            return
        try:
            zeit = parse_zeit(v["zeit"])
            evaluate(v["menge"], parameter.bekannte_namen(db))
            satz = parse_zahl(v["satz"]) if v["satz"] else None
            art_id = la[namen.index(v["art"]) - 1]["id"] if v["art"] != namen[0] else None
            args = (v["bez"] or "Lohnanteil", art_id, zeit, v["einheit"] or "Stk", v["menge"], satz, 1 if v["fix"] else 0)
            if lohn_id:
                db.x("UPDATE leistung_lohn SET bezeichnung=?,lohnart_id=?,zeit_h=?,einheit=?,menge=?,satz=?,menge_fix=? WHERE id=?", args + (lohn_id,))
            else:
                db.x("INSERT INTO leistung_lohn(bezeichnung,lohnart_id,zeit_h,einheit,menge,satz,menge_fix,leistung_id) VALUES(?,?,?,?,?,?,?,?)", args + (lid,))
            self.ok = True
        except Exception as e:
            fehler(parent, e)


class LeistungWindow(tk.Toplevel):
    def __init__(self, app, lid):
        super().__init__(app.root)
        self.app, self.lid = app, lid
        self.geometry("1180x680")
        self.configure(bg=theme.BG)
        self.dummy = lambda: parameter.bekannte_namen(self.app.db)
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)
        # --- Aufbau
        fa = ttk.Frame(nb, padding=8)
        nb.add(fa, text="Aufbau")
        buttons(fa, [(f"{theme.S_NEU} Material", self.mat_add, True), (f"{theme.S_NEU} Neuer Artikel …", self.mat_neu),
                     (f"{theme.S_NEU} Lohnanteil", self.lohn_add, True), (f"{theme.S_EDIT} Lohnanteil-Details", self.lohn_details),
                     ("Menge fix an/aus", self.fix_umschalten), ("Preise zum Artikel", self.preise),
                     (f"{theme.S_DEL} Entfernen", self.entfernen)]).pack(anchor="w", pady=(0, 6))
        wrap = ttk.Frame(fa)
        wrap.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(wrap, columns=SPALTENNAMEN, show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Bezeichnung", anchor="w")
        self.tree.column("#0", width=300, stretch=True)
        for key, label, w, anchor in SPALTEN:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=w, anchor=anchor, stretch=False)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.tag_configure("head", background=theme.ORANGE_L, foreground=theme.FG)
        self.tree.tag_configure("lohn", foreground="#555555")
        self.tree.bind("<ButtonRelease-1>", self._klick)
        ttk.Label(fa, text=f"Ein Klick auf eine Zahl oder einen Namen ändert den Wert direkt (Enter = übernehmen, Esc = abbrechen).   "
                           f"* = Preisaufschlag in dieser Leistung abweichend vom Artikel.   Preisaufschlag leeren = Wert aus dem Artikel.   "
                           f"„(fix)“ = Menge wird nicht mit der Leistungsmenge multipliziert.\n"
                           f"Mengen dürfen Formeln mit Projektparametern sein, z. B. Firstlänge*2 oder Sparrenanzahl*4 (Winkel in Grad; ƒ = Formel). "
                           f"Verfügbar: {parameter.namen_text()}", style="Sub.TLabel", wraplength=1100).pack(anchor="w", pady=(6, 0))
        # --- Analyse
        fz = ttk.Frame(nb, padding=12)
        nb.add(fz, text="Analyse")
        top = ttk.Frame(fz)
        top.pack(fill="x")
        ttk.Label(top, text="Berechnet für Menge:").pack(side="left")
        self.v_menge = tk.StringVar(value="1")
        e = ttk.Entry(top, textvariable=self.v_menge, width=10)
        e.pack(side="left", padx=6)
        e.bind("<Return>", lambda ev: self.analyse())
        e.bind("<FocusOut>", lambda ev: self.analyse())
        self.l_einheit = ttk.Label(top, text="")
        self.l_einheit.pack(side="left")
        ttk.Label(top, text="   Parameterwerte aus:").pack(side="left")
        self.beispiel = "Beispielwerte (Vorlage Dachstuhl)"
        self.v_param = tk.StringVar(value=self.beispiel)
        cb = ttk.Combobox(top, textvariable=self.v_param, state="readonly", width=34,
                          values=[self.beispiel] + [f"Projekt {r['nr']}" for r in self.app.db.q("SELECT nr FROM projekte ORDER BY nr DESC")])
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda ev: self.analyse())
        ttk.Button(top, text=f"{theme.S_REFRESH} Berechnen", command=self.analyse).pack(side="left", padx=10)
        box = ttk.LabelFrame(fz, text="Gesamtzeitaufwand", padding=12)
        box.pack(fill="x", pady=10)
        self.l_zeit = ttk.Label(box, text="", style="Zeit.TLabel")
        self.l_zeit.pack(anchor="w")
        self.l_zeit2 = ttk.Label(box, text="", style="Sub.TLabel")
        self.l_zeit2.pack(anchor="w")
        self.kz = ttk.Treeview(fz, columns=("wert",), show="tree headings", height=14)
        self.kz.heading("#0", text="Kennzahl", anchor="w")
        self.kz.heading("wert", text="Wert", anchor="e")
        self.kz.column("#0", width=380)
        self.kz.column("wert", width=220, anchor="e")
        self.kz.pack(fill="both", expand=True)
        self.l_warn = ttk.Label(fz, text="", foreground="#B00020", wraplength=900)
        self.l_warn.pack(anchor="w", pady=(6, 0))
        # --- Beschreibung
        fb = ttk.Frame(nb, padding=8)
        nb.add(fb, text="Beschreibung (Langtext)")
        ttk.Label(fb, text="Dieser Text wird beim CSV-Export als Beschreibung übergeben.", style="Sub.TLabel").pack(anchor="w")
        self.txt = tk.Text(fb, wrap="word", font=("Segoe UI", 10), height=18, relief="solid", borderwidth=1)
        self.txt.pack(fill="both", expand=True, pady=6)
        self.txt.bind("<FocusOut>", lambda ev: self.text_speichern())
        ttk.Button(fb, text=f"{theme.S_OK} Beschreibung speichern", command=self.text_speichern).pack(anchor="e")
        self.protocol("WM_DELETE_WINDOW", self._close)
        nb.bind("<<NotebookTabChanged>>", lambda e: self.analyse())
        self.refresh()
        zentrieren(self, app.root)

    def _close(self):
        self.text_speichern()
        self.destroy()

    # --- Anzeige ---------------------------------------------------------------
    def refresh(self):
        db = self.app.db
        l = db.one("SELECT * FROM leistungen WHERE id=?", (self.lid,))
        if not l:
            self.destroy()
            return
        z = berechne_leistung(db, self.lid, 1.0)
        E = l["einheit"]
        self.title(f"Leistung {l['nr']} – {l['bezeichnung']}")
        if not self.txt.get("1.0", "end").strip():
            self.txt.insert("1.0", l["beschreibung"] or "")
        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        self.tree.insert("", "end", iid="L", text=l["bezeichnung"], open=True, tags=("head",), values=(
            f"1 {E}", "", f"{preis_fmt(z['summe_ek'])} €/{E}", "", f"{preis_fmt(z['summe'])} €/{E}", "", fmt_zeit(z["stunden"]), eur(z["summe"])))
        for m in z["material"]:
            je = zahl_kurz(m["menge_je_einheit"]) if _plain(m["formel"]) else m["formel"] + " ƒ"
            self.tree.insert("L", "end", iid=f"m{m['id']}", text=f"{theme.S_MAT} {m['bezeichnung']}" + ("  (fix)" if m["menge_fix"] else ""), values=(
                f"{je} {m['einheit']}", pct(m["verschnitt"] or 0), f"{preis_fmt(m['ek'])} €/{m['einheit']}",
                pct(m["aufschlag"]) + ("*" if m["aufschlag_eigen"] else ""), f"{preis_fmt(m['vk'])} €/{m['einheit']}",
                f"{zahl(m['summe'])} €/{E}", "", eur(m["summe"])))
        for o in z["lohn"]:
            self.tree.insert("L", "end", iid=f"l{o['id']}", text=f"{theme.S_LOHN} {o['bezeichnung']}" + ("  (fix)" if o["menge_fix"] else ""),
                             tags=("lohn",), values=(f"{zahl_kurz(o['menge'])} {o['einheit']}", "", f"{zahl(o['satz'])} €/h", "",
                                                     f"{zahl(o['satz'])} €/h", f"{zahl(o['summe'])} €/{E}", fmt_zeit(o["stunden"]), eur(o["summe"])))
        if sel and self.tree.exists(sel[0]):
            self.tree.selection_set(sel[0])
        self.l_einheit.config(text=E)
        self.analyse()

    def analyse(self):
        db = self.app.db
        try:
            menge = parse_zahl(self.v_menge.get() or "1")
        except ValueError:
            menge = 1.0
        z = berechne_leistung(db, self.lid, menge, None, self._werte())
        E = z["leistung"]["einheit"]
        fix = sum(o["stunden"] for o in z["lohn"] if o["menge_fix"])
        var = z["stunden"] - fix
        je = var / menge if menge else 0
        self.l_zeit.config(text=fmt_zeit(z["stunden"]))
        self.l_zeit2.config(text=f"für {zahl_kurz(menge)} {E}  =  {zahl(z['stunden'], 2)} Stunden  =  {int(round(z['stunden'] * 60))} Minuten")
        pe = z["summe"] / menge if menge else 0
        rows = [("Zeit je Einheit (ohne feste Zeiten)", f"{fmt_zeit(je)} je {E}"), ("Feste Zeiten (Menge fix)", fmt_zeit(fix)),
                ("Leistung pro Stunde", f"{zahl(1 / je if je else 0, 2)} {E}/h" if je else "–"),
                ("Lohnkosten", eur(z["lohn_summe"])), ("Ø Verrechnungssatz", f"{zahl(z['lohn_summe'] / z['stunden'] if z['stunden'] else 0)} €/h"),
                ("Material (EK)", eur(z["material_ek"])), ("Preisaufschläge auf Material", eur(z["material_vk"] - z["material_ek"])),
                ("Material (VK)", eur(z["material_vk"])), ("Preis EK gesamt", eur(z["summe_ek"])), ("Preis VK gesamt", eur(z["summe"])),
                (f"Einheitspreis (VK) je {E}", f"{zahl(pe)} €"),
                ("Anteil Lohn am Preis", f"{zahl(z['lohn_summe'] / z['summe'] * 100 if z['summe'] else 0, 1)} %"),
                ("Anteil Material am Preis", f"{zahl(z['material_vk'] / z['summe'] * 100 if z['summe'] else 0, 1)} %"),
                ("Umsatz je Arbeitsstunde (VK)", f"{zahl(z['summe'] / z['stunden'] if z['stunden'] else 0)} €/h"),
                ("Materialpositionen / Lohnanteile", f"{len(z['material'])} / {len(z['lohn'])}")]
        self.kz.delete(*self.kz.get_children())
        for i, (k, v) in enumerate(rows):
            self.kz.insert("", "end", iid=str(i), text=k, values=(v,))
        self.l_warn.config(text="\n".join(z["warnungen"]))

    def _werte(self):
        """Parameterwerte für Formeln: Projekt oder Beispielwerte der Dachstuhl-Vorlage."""
        wahl = self.v_param.get()
        if wahl.startswith("Projekt "):
            r = self.app.db.one("SELECT id FROM projekte WHERE nr=?", (wahl[8:],))
            if r:
                werte, _ = eval_parameter([(x["name"], x["wert"]) for x in self.app.db.q("SELECT name,wert FROM parameter WHERE projekt_id=?", (r["id"],))])
                return werte
        return parameter.beispielwerte()

    # --- Direktbearbeitung ------------------------------------------------------------
    def _klick(self, ev):
        t = self.tree
        if t.identify_region(ev.x, ev.y) not in ("cell", "tree") or "indicator" in str(t.identify_element(ev.x, ev.y)):
            return
        iid = t.identify_row(ev.y)
        col = t.identify_column(ev.x)
        if not iid:
            return
        name = "#0" if col == "#0" else SPALTENNAMEN[int(col[1:]) - 1]
        text = self._rohwert(iid, name)
        if text is None:
            return
        CellEditor(t, iid, name if name == "#0" else name, text, lambda val: self._commit(iid, name, val))

    def _rohwert(self, iid, col):
        db = self.app.db
        z = None
        if iid == "L":
            l = db.one("SELECT * FROM leistungen WHERE id=?", (self.lid,))
            return {"#0": l["bezeichnung"], "menge": l["einheit"]}.get(col)
        z = berechne_leistung(db, self.lid, 1.0)
        if iid[0] == "m":
            m = next(x for x in z["material"] if x["id"] == int(iid[1:]))
            raw = db.one("SELECT bezeichnung FROM leistung_material WHERE id=?", (m["id"],))
            return {"#0": m["bezeichnung"], "menge": m["formel"], "ma": zahl_kurz(m["verschnitt"] or 0),
                    "pa": zahl_kurz(m["aufschlag"])}.get(col)
        o = next(x for x in z["lohn"] if x["id"] == int(iid[1:]))
        return {"#0": o["bezeichnung"], "menge": o["menge_formel"], "ek": zahl(o["satz"]), "vk": zahl(o["satz"]),
                "zeit": fmt_zeit(o["stunden"])}.get(col)

    def _commit(self, iid, col, text):
        db = self.app.db
        text = text.strip()
        try:
            if iid == "L":
                if col == "#0":
                    if not text:
                        raise ValueError("Bezeichnung darf nicht leer sein.")
                    db.x("UPDATE leistungen SET bezeichnung=? WHERE id=?", (text, self.lid))
                elif col == "menge":
                    if not text:
                        raise ValueError("Einheit darf nicht leer sein.")
                    db.x("UPDATE leistungen SET einheit=? WHERE id=?", (text, self.lid))
            elif iid[0] == "m":
                i = int(iid[1:])
                if col == "#0":
                    db.x("UPDATE leistung_material SET bezeichnung=? WHERE id=?", (text or None, i))
                elif col == "menge":
                    evaluate(text, self.dummy())
                    db.x("UPDATE leistung_material SET menge=? WHERE id=?", (text, i))
                elif col == "ma":
                    db.x("UPDATE leistung_material SET verschnitt=? WHERE id=?", (parse_pct(text) or 0.0, i))
                elif col == "pa":
                    db.x("UPDATE leistung_material SET preisaufschlag=? WHERE id=?", (parse_pct(text), i))
            else:
                i = int(iid[1:])
                o = db.one("SELECT * FROM leistung_lohn WHERE id=?", (i,))
                if col == "#0":
                    db.x("UPDATE leistung_lohn SET bezeichnung=? WHERE id=?", (text or "Lohnanteil", i))
                elif col == "menge":
                    evaluate(text, self.dummy())
                    db.x("UPDATE leistung_lohn SET menge=? WHERE id=?", (text, i))
                elif col in ("ek", "vk"):
                    db.x("UPDATE leistung_lohn SET satz=? WHERE id=?", (parse_zahl(text) if text else None, i))
                elif col == "zeit":
                    gesamt = parse_zeit(text)
                    je = evaluate(o["menge"], self.dummy()) or 1.0
                    db.x("UPDATE leistung_lohn SET zeit_h=? WHERE id=?", (gesamt / je, i))
        except Exception as e:
            fehler(self, e)
        self.refresh()
        self.app.refresh_all()

    # --- Aktionen --------------------------------------------------------------------
    def _material_einfuegen(self, aid):
        if aid:
            self.app.db.x("INSERT INTO leistung_material(leistung_id,artikel_id,menge,verschnitt) VALUES(?,?,'1',0)", (self.lid, aid))
            self.refresh()
            self.app.refresh_all()

    def mat_add(self):
        self._material_einfuegen(ArtikelPicker(self.app, self).result)

    def mat_neu(self):
        self._material_einfuegen(artikel_neu(self.app, self, None, in_leistung=True))

    def lohn_add(self):
        if LohnDialog(self.app, self, self.lid).ok:
            self.refresh()
            self.app.refresh_all()

    def _sel(self):
        s = self.tree.selection()
        return s[0] if s else None

    def lohn_details(self):
        s = self._sel()
        if not s or s[0] != "l":
            return messagebox.showinfo("Hinweis", "Bitte zuerst eine Lohnzeile auswählen.", parent=self)
        if LohnDialog(self.app, self, self.lid, int(s[1:])).ok:
            self.refresh()
            self.app.refresh_all()

    def preise(self):
        s = self._sel()
        if not s or s[0] != "m":
            return messagebox.showinfo("Hinweis", "Bitte zuerst eine Materialzeile auswählen.", parent=self)
        aid = self.app.db.one("SELECT artikel_id FROM leistung_material WHERE id=?", (int(s[1:]),))["artikel_id"]
        PreisWindow(self.app, aid)

    def fix_umschalten(self):
        s = self._sel()
        if not s or s[0] not in "ml":
            return messagebox.showinfo("Hinweis", "Bitte zuerst eine Material- oder Lohnzeile auswählen.", parent=self)
        tab = "leistung_material" if s[0] == "m" else "leistung_lohn"
        self.app.db.x(f"UPDATE {tab} SET menge_fix=1-menge_fix WHERE id=?", (int(s[1:]),))
        self.refresh()
        self.app.refresh_all()

    def entfernen(self):
        s = self._sel()
        if s and s[0] in "ml":
            self.app.db.x(f"DELETE FROM {'leistung_material' if s[0] == 'm' else 'leistung_lohn'} WHERE id=?", (int(s[1:]),))
            self.refresh()
            self.app.refresh_all()

    def text_speichern(self):
        try:
            self.app.db.x("UPDATE leistungen SET beschreibung=? WHERE id=?", (self.txt.get("1.0", "end").strip(), self.lid))
        except Exception:
            pass


def _plain(formel):
    try:
        parse_zahl(str(formel))
        return True
    except (ValueError, TypeError):
        return False
