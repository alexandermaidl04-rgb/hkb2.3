"""Projekte: Liste und Projektfenster (Parameter, Positionen, Kalkulation/Rechenweg, Snapshots)."""
import json
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import parameter, planimport, theme
from .calc import FormelFehler, berechne, eval_parameter, evaluate, rechenweg
from .pdf import erzeuge_pdf
from .util import (eur, fmt_zeit, parse_pct, parse_zahl, to_de, to_de_ts, to_iso, today_iso, validate_name, zahl,
                   zahl_kurz)
from .widgets import TreeList, ask, buttons, fehler, zentrieren

STATUS = ["Entwurf", "Angebot", "Beauftragt", "In Ausführung", "Abgeschlossen", "Archiviert"]
PROJEKT_FELDER = [("nr", "Projektnummer"), ("bezeichnung", "Bezeichnung"), ("kunde", "Kunde"), ("ort", "Ort"),
                  ("status", "Status", "choice", STATUS), ("datum", "Datum (TT.MM.JJJJ)"),
                  ("stichtag", "Preisstichtag (TT.MM.JJJJ)"),
                  ("aufschlag", "Materialaufschlag % für das ganze Projekt (leer = wie in Artikel/Leistung)")]
PROJEKT_HINT = ("Der Preisstichtag bestimmt, welche Materialpreise gelten. Ein Projekt-Aufschlag überschreibt alle "
                "Preisaufschläge aus Artikel und Leistung – leer lassen für die Einzelwerte.")


def pdf_oeffnen(pfad):
    try:
        if sys.platform.startswith("win"):
            os.startfile(pfad)  # noqa
    except Exception:
        pass


class ProjekteTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app
        buttons(self, [(f"{theme.S_NEU} Neues Projekt", self.neu, True), ("Öffnen", self.open), ("Duplizieren", self.dupl),
                       (f"{theme.S_DEL} Löschen", self.loeschen)]).pack(anchor="w", pady=(0, 8))
        self.t = TreeList(self, [("nr", "Projektnr.", 100, "w"), ("bez", "Bezeichnung", 240, "w"), ("kunde", "Kunde", 160, "w"),
                                 ("ort", "Ort", 110, "w"), ("status", "Status", 100, "w"), ("datum", "Datum", 90, "w"),
                                 ("stich", "Preisstichtag", 100, "w")])
        self.t.pack(fill="both", expand=True)
        self.t.on_double(self.open)

    def refresh(self):
        self.t.fill([(r["id"], (r["nr"], r["bezeichnung"], r["kunde"], r["ort"], r["status"], to_de(r["datum"]), to_de(r["stichtag"])))
                     for r in self.app.db.q("SELECT * FROM projekte ORDER BY nr DESC")])

    def neu(self):
        db = self.app.db
        v = ask(self.app.root, "Neues Projekt", PROJEKT_FELDER + [("vorlage", "Parameter-Vorlage", "choice", [parameter.KEINE] + parameter.vorlage_namen())],
                {"nr": db.next_projektnr(), "status": "Entwurf", "datum": to_de(today_iso()), "stichtag": to_de(today_iso()),
                 "vorlage": parameter.KEINE}, PROJEKT_HINT + " Eine Parameter-Vorlage (z. B. Dachstuhl) legt Eingabewerte und Vorschlagswerte an.")
        if not v:
            return
        try:
            pid = db.create_projekt(v["nr"], v["bezeichnung"], v["kunde"], v["status"], v["ort"], to_iso(v["datum"]) or today_iso(),
                                    to_iso(v["stichtag"]) or today_iso(), parse_pct(v["aufschlag"]))
            if v["vorlage"] in parameter.VORLAGEN:
                parameter.einfuegen(db, pid, v["vorlage"])
        except Exception as e:
            return fehler(self.app.root, e)
        self.app.refresh_all()
        self.app.open_projekt(pid)

    def open(self):
        pid = self.t.selected()
        if pid:
            self.app.open_projekt(pid)

    def dupl(self):
        pid = self.t.selected()
        if not pid:
            return
        db = self.app.db
        p = db.one("SELECT * FROM projekte WHERE id=?", (pid,))
        try:
            n = db.create_projekt(db.next_projektnr(), p["bezeichnung"] + " (Kopie)", p["kunde"], "Entwurf", p["ort"], today_iso(),
                                  p["stichtag"], p["aufschlag_override"])
            db.x("DELETE FROM parameter WHERE projekt_id=?", (n,))
            db.x("INSERT INTO parameter(projekt_id,name,wert,einheit) SELECT ?,name,wert,einheit FROM parameter WHERE projekt_id=?", (n, pid))
            db.x("INSERT INTO positionen(projekt_id,leistung_id,menge,bemerkung,sort) SELECT ?,leistung_id,menge,bemerkung,sort "
                 "FROM positionen WHERE projekt_id=?", (n, pid))
        except Exception as e:
            return fehler(self.app.root, e)
        self.app.refresh_all()

    def loeschen(self):
        pid = self.t.selected()
        if pid and messagebox.askyesno("Projekt löschen", "Projekt inkl. Parametern, Positionen und Snapshots unwiderruflich löschen?", parent=self.app.root):
            try:
                self.app.db.x("DELETE FROM projekte WHERE id=?", (pid,))
            except Exception as e:
                return fehler(self.app.root, e)
            self.app.refresh_all()


class ProjektWindow(tk.Toplevel):
    def __init__(self, app, pid):
        super().__init__(app.root)
        self.app, self.pid, self.result = app, pid, None
        self.geometry("1080x700")
        self.configure(bg=theme.BG)
        top = ttk.Frame(self, padding=(12, 8))
        top.pack(fill="x")
        self.kopf = ttk.Label(top, font=("Segoe UI", 13, "bold"))
        self.kopf.pack(side="left")
        ttk.Button(top, text=f"{theme.S_EDIT} Stammdaten ändern", command=self.stamm).pack(side="right")
        self.info = ttk.Label(self, style="Sub.TLabel", padding=(12, 0))
        self.info.pack(anchor="w")
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)
        self.nb = nb
        fp = ttk.Frame(nb, padding=8)
        nb.add(fp, text="Parameter")
        buttons(fp, [(f"{theme.S_NEU} Hinzufügen", self.p_add, True), ("Vorlage einfügen …", self.p_vorlage, True), ("Aus Plan (PDF) einlesen …", self.p_plan, True),
                     (f"{theme.S_EDIT} Ändern", self.p_edit),
                     (f"{theme.S_DEL} Löschen", self.p_del)]).pack(anchor="w", pady=(0, 6))
        self.tp = TreeList(fp, [("name", "Parameter", 150, "w"), ("wert", "Wert / Formel", 250, "w"), ("erg", "Ergebnis", 80, "e"), ("ein", "Einheit", 50, "w"),
                                ("art", "Art", 110, "w"), ("hinweis", "Hinweis", 330, "w")])
        self.tp.pack(fill="both", expand=True)
        self.tp.on_double(self.p_edit)
        ttk.Label(fp, text="Trage die gegebenen Werte ein (z. B. Dachfläche, Dachneigung). Felder mit „Vorschlag (Formel)“ rechnet HBK aus den Eingaben – "
                           "einfach eine gemessene Zahl eintragen, um den Vorschlag zu überschreiben. Diese Parameter nutzt du in den Mengenformeln der Leistungen "
                           "(Winkel in Grad). Gemeinkosten, Gewinnaufschlag und MwSt (%) wirken auf Projektebene; ein Parameter „Lohnsatz“ ersetzt den Standardsatz.",
                  style="Sub.TLabel", wraplength=980).pack(anchor="w", pady=(6, 0))
        fo = ttk.Frame(nb, padding=8)
        nb.add(fo, text="Positionen")
        buttons(fo, [(f"{theme.S_NEU} Hinzufügen", self.o_add, True), (f"{theme.S_EDIT} Ändern", self.o_edit), (f"{theme.S_DEL} Löschen", self.o_del),
                     ("▲", lambda: self.o_move(-1)), ("▼", lambda: self.o_move(1))]).pack(anchor="w", pady=(0, 6))
        self.to = TreeList(fo, [("nr", "Nr.", 40, "w"), ("lei", "Leistung", 280, "w"), ("menge", "Menge (Formel)", 140, "w"),
                                ("erg", "Menge", 90, "e"), ("ein", "Einheit", 60, "w"), ("ep", "EP (VK netto)", 110, "e"),
                                ("zeit", "Gesamtzeit", 100, "e"), ("preis", "Preis (VK netto)", 120, "e")])
        self.to.pack(fill="both", expand=True)
        self.to.on_double(self.o_edit)
        fk = ttk.Frame(nb, padding=8)
        nb.add(fk, text="Kalkulation & Rechenweg")
        bar = ttk.Frame(fk)
        bar.pack(fill="x", pady=(0, 6))
        buttons(bar, [(f"{theme.S_REFRESH} Neu berechnen", self.calc), ("Snapshot speichern", self.snap, True), ("Als PDF exportieren", self.pdf)]).pack(side="left")
        self.l_sum = ttk.Label(bar, style="Big.TLabel")
        self.l_sum.pack(side="right")
        tf = ttk.Frame(fk)
        tf.pack(fill="both", expand=True)
        self.txt = tk.Text(tf, font=("Consolas", 10), wrap="none", state="disabled", relief="solid", borderwidth=1)
        sy = ttk.Scrollbar(tf, command=self.txt.yview)
        sx = ttk.Scrollbar(fk, orient="horizontal", command=self.txt.xview)
        self.txt.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        sy.pack(side="right", fill="y")
        self.txt.pack(side="left", fill="both", expand=True)
        sx.pack(fill="x")
        fs = ttk.Frame(nb, padding=8)
        nb.add(fs, text="Snapshots (Historie)")
        buttons(fs, [("Anzeigen", self.s_show), ("PDF exportieren", self.s_pdf), (f"{theme.S_DEL} Löschen", self.s_del)]).pack(anchor="w", pady=(0, 6))
        self.ts = TreeList(fs, [("erstellt", "Erstellt", 130, "w"), ("titel", "Titel", 260, "w"), ("stich", "Stichtag", 90, "w"),
                                ("netto", "Netto", 110, "e"), ("brutto", "Brutto", 110, "e")])
        self.ts.pack(fill="both", expand=True)
        self.ts.on_double(self.s_show)
        ttk.Label(fs, text="Ein Snapshot friert Parameter, Formeln, Preise, Aufschläge, Zeiten und Rechenweg ein und ändert sich nie – auch nicht, "
                           "wenn sich Preise oder Stammdaten später ändern.", style="Sub.TLabel", wraplength=980).pack(anchor="w", pady=(6, 0))
        self.refresh()
        zentrieren(self, app.root)

    def refresh(self):
        db = self.app.db
        p = db.one("SELECT * FROM projekte WHERE id=?", (self.pid,))
        if not p:
            self.destroy()
            return
        self.title(f"Projekt {p['nr']}")
        self.kopf.config(text=f"{p['nr']} – {p['bezeichnung']}")
        auf = f"   |   Projekt-Aufschlag: {zahl_kurz(p['aufschlag_override'])} %" if p["aufschlag_override"] is not None else ""
        self.info.config(text=f"Kunde: {p['kunde']}   |   Ort: {p['ort']}   |   Status: {p['status']}   |   Preisstichtag: {to_de(p['stichtag'])}{auf}")
        prm = db.q("SELECT * FROM parameter WHERE projekt_id=? ORDER BY id", (self.pid,))
        werte, _ = eval_parameter([(r["name"], r["wert"]) for r in prm])
        self.tp.fill([(r["id"], (r["name"], r["wert"], zahl_kurz(werte.get(r["name"], 0)), r["einheit"],
                                 "Eingabe" if _plain(r["wert"]) else "Vorschlag (Formel)", r["hinweis"] or "")) for r in prm])
        self.calc()
        pos = {x["id"]: x for x in (self.result["positionen"] if self.result else [])}
        rows = []
        for i, r in enumerate(db.q("SELECT po.*, l.nr l_nr, l.bezeichnung, l.einheit FROM positionen po JOIN leistungen l ON l.id=po.leistung_id "
                                   "WHERE po.projekt_id=? ORDER BY po.sort, po.id", (self.pid,)), 1):
            x = pos.get(r["id"])
            rows.append((r["id"], (i, f"{r['l_nr']} {r['bezeichnung']}", r["menge"], zahl_kurz(x["menge"]) if x else "?", r["einheit"],
                                   f"{zahl(x['ep_vk'])} €" if x else "", fmt_zeit(x["stunden"]) if x else "", eur(x["summe"]) if x else "")))
        self.to.fill(rows)
        self.ts.fill([(r["id"], (to_de_ts(r["erstellt"]), r["titel"], to_de(json.loads(r["daten"])["projekt"]["stichtag"]),
                                 eur(json.loads(r["daten"])["summen"]["netto"]), eur(json.loads(r["daten"])["summen"]["brutto"])))
                      for r in db.q("SELECT * FROM snapshots WHERE projekt_id=? ORDER BY erstellt DESC, id DESC", (self.pid,))])

    def changed(self):
        self.app.db.touch(self.pid)
        self.refresh()
        self.app.refresh_all()

    def stamm(self):
        p = dict(self.app.db.one("SELECT * FROM projekte WHERE id=?", (self.pid,)))
        p["datum"], p["stichtag"] = to_de(p["datum"]), to_de(p["stichtag"])
        p["aufschlag"] = "" if p["aufschlag_override"] is None else zahl_kurz(p["aufschlag_override"])
        v = ask(self, "Projekt bearbeiten", PROJEKT_FELDER, p, PROJEKT_HINT)
        if v:
            try:
                self.app.db.x("UPDATE projekte SET nr=?,bezeichnung=?,kunde=?,ort=?,status=?,datum=?,stichtag=?,aufschlag_override=? WHERE id=?",
                              (v["nr"], v["bezeichnung"], v["kunde"], v["ort"], v["status"], to_iso(v["datum"]), to_iso(v["stichtag"]) or today_iso(),
                               parse_pct(v["aufschlag"]), self.pid))
            except Exception as e:
                return fehler(self, e)
            self.changed()

    # -- Parameter
    def p_vorlage(self):
        v = ask(self, "Parameter-Vorlage einfügen", [("vorlage", "Vorlage", "choice", parameter.vorlage_namen())],
                {"vorlage": parameter.vorlage_namen()[0]}, "Vorhandene Parameter mit gleichem Namen bleiben unverändert.")
        if v:
            n = parameter.einfuegen(self.app.db, self.pid, v["vorlage"])
            self.changed()
            messagebox.showinfo("Vorlage", f"{n} Parameter hinzugefügt.", parent=self)

    def p_plan(self):
        pfad = filedialog.askopenfilename(parent=self, title="Eingabeplan (PDF) wählen", filetypes=[("PDF-Plan", "*.pdf"), ("Alle Dateien", "*.*")])
        if not pfad:
            return
        try:
            funde = planimport.analysiere_pdf(pfad)
            if not funde:
                return messagebox.showinfo("Plan einlesen", "Im Plan wurden keine passenden Angaben erkannt.\nBitte die Werte manuell eintragen.", parent=self)
        except Exception as e:
            return fehler(self, e)
        dlg = PlanImportDialog(self.app, self, self.pid, funde, os.path.basename(pfad))
        if dlg.ok:
            self.changed()

    def p_add(self):
        self._p_dialog(None)

    def p_edit(self):
        i = self.tp.selected()
        if i:
            self._p_dialog(i)

    def _p_dialog(self, prm_id):
        db = self.app.db
        vals = dict(db.one("SELECT * FROM parameter WHERE id=?", (prm_id,))) if prm_id else {"einheit": "m²"}
        v = ask(self, "Parameter", [("name", "Name (z. B. Dachfläche)"), ("wert", "Wert oder Formel (Winkel in Grad)"), ("einheit", "Einheit"),
                                    ("hinweis", "Hinweis")], vals)
        if not v:
            return
        try:
            name = validate_name(v["name"])
            others = {r["name"]: 1 for r in db.q("SELECT name FROM parameter WHERE projekt_id=? AND id IS NOT ?", (self.pid, prm_id))}
            evaluate(v["wert"], others)
            if prm_id:
                db.x("UPDATE parameter SET name=?,wert=?,einheit=?,hinweis=? WHERE id=?", (name, v["wert"], v["einheit"], v["hinweis"], prm_id))
            else:
                db.x("INSERT INTO parameter(projekt_id,name,wert,einheit,hinweis) VALUES(?,?,?,?,?)", (self.pid, name, v["wert"], v["einheit"], v["hinweis"]))
        except Exception as e:
            return fehler(self, e)
        self.changed()

    def p_del(self):
        i = self.tp.selected()
        if i and messagebox.askyesno("Löschen", "Parameter löschen?", parent=self):
            self.app.db.x("DELETE FROM parameter WHERE id=?", (i,))
            self.changed()

    # -- Positionen
    def _o_dialog(self, oid):
        db = self.app.db
        rows = db.q("SELECT l.*, o.name ordner FROM leistungen l LEFT JOIN ordner o ON o.id=l.ordner_id ORDER BY l.nr")
        if not rows:
            return messagebox.showinfo("Hinweis", "Bitte zuerst Leistungen anlegen.", parent=self)
        pf = dict(db.ordner_pfade("leistung"))
        lei = [f"{l['nr']} – {l['bezeichnung']} ({l['einheit']})" + (f"   [{pf.get(l['ordner_id'], '')}]" if l["ordner_id"] else "") for l in rows]
        vals = {}
        if oid:
            o = db.one("SELECT po.*, l.nr FROM positionen po JOIN leistungen l ON l.id=po.leistung_id WHERE po.id=?", (oid,))
            vals = {"lei": next(x for x, l in zip(lei, rows) if l["nr"] == o["nr"]), "menge": o["menge"], "bem": o["bemerkung"]}
        v = ask(self, "Position", [("lei", "Leistung", "choice", lei), ("menge", "Menge (Zahl oder Formel, z. B. Dachfläche)"), ("bem", "Bemerkung")],
                vals, "Die Einheit der Menge ist die Einheit der Leistung.")
        if not v:
            return
        try:
            werte, _ = eval_parameter([(r["name"], r["wert"]) for r in db.q("SELECT name,wert FROM parameter WHERE projekt_id=?", (self.pid,))])
            evaluate(v["menge"], werte)
            lid = rows[lei.index(v["lei"])]["id"]
            if oid:
                db.x("UPDATE positionen SET leistung_id=?,menge=?,bemerkung=? WHERE id=?", (lid, v["menge"], v["bem"], oid))
            else:
                n = db.one("SELECT COALESCE(MAX(sort),0)+1 n FROM positionen WHERE projekt_id=?", (self.pid,))["n"]
                db.x("INSERT INTO positionen(projekt_id,leistung_id,menge,bemerkung,sort) VALUES(?,?,?,?,?)", (self.pid, lid, v["menge"], v["bem"], n))
        except Exception as e:
            return fehler(self, e)
        self.changed()

    def o_add(self):
        self._o_dialog(None)

    def o_edit(self):
        i = self.to.selected()
        if i:
            self._o_dialog(i)

    def o_del(self):
        i = self.to.selected()
        if i and messagebox.askyesno("Löschen", "Position löschen?", parent=self):
            self.app.db.x("DELETE FROM positionen WHERE id=?", (i,))
            self.changed()

    def o_move(self, d):
        i = self.to.selected()
        if not i:
            return
        db = self.app.db
        rows = [r["id"] for r in db.q("SELECT id FROM positionen WHERE projekt_id=? ORDER BY sort,id", (self.pid,))]
        k = rows.index(i)
        if 0 <= k + d < len(rows):
            rows[k], rows[k + d] = rows[k + d], rows[k]
            for n, rid in enumerate(rows):
                db.x("UPDATE positionen SET sort=? WHERE id=?", (n, rid))
            self.changed()

    # -- Kalkulation
    def _show(self, text):
        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", text)
        self.txt.config(state="disabled")

    def calc(self):
        try:
            self.result = berechne(self.app.db, self.pid)
            self._show("\n".join(rechenweg(self.result)))
            s = self.result["summen"]
            self.l_sum.config(text=f"Netto {eur(s['netto'])}   ·   {fmt_zeit(s['stunden'])}")
        except Exception as e:
            self.result = None
            self._show(f"Fehler bei der Berechnung:\n{e}")
            self.l_sum.config(text="")

    def snap(self):
        self.calc()
        if not self.result:
            return
        v = ask(self, "Snapshot speichern", [("titel", "Titel (z. B. Angebot v1)")], {"titel": f"Stand {to_de(today_iso())}"})
        if v:
            self.app.db.snapshot_speichern(self.pid, v["titel"], self.result)
            self.refresh()
            self.app.refresh_all()
            messagebox.showinfo("Gespeichert", "Snapshot wurde gespeichert.", parent=self)

    def _pdf(self, result):
        pfad = filedialog.asksaveasfilename(parent=self, defaultextension=".pdf", filetypes=[("PDF", "*.pdf")],
                                            initialfile=f"{result['projekt']['nr']}_Kalkulation.pdf")
        if pfad:
            try:
                s = self.app.db.settings()
                erzeuge_pdf(result, pfad, s.get("firma", ""), s.get("adresse", ""))
            except Exception as e:
                return fehler(self, e)
            pdf_oeffnen(pfad)

    def pdf(self):
        self.calc()
        if self.result:
            self._pdf(self.result)

    def s_show(self):
        sid = self.ts.selected()
        if sid:
            self._show("\n".join(rechenweg(self.app.db.snapshot_laden(sid))))
            self.nb.select(2)

    def s_pdf(self):
        sid = self.ts.selected()
        if sid:
            self._pdf(self.app.db.snapshot_laden(sid))

    def s_del(self):
        sid = self.ts.selected()
        if sid and messagebox.askyesno("Löschen", "Snapshot unwiderruflich löschen?", parent=self):
            self.app.db.x("DELETE FROM snapshots WHERE id=?", (sid,))
            self.refresh()
            self.app.refresh_all()


def _plain(wert):
    try:
        parse_zahl(str(wert))
        return True
    except (ValueError, TypeError):
        return False


class PlanImportDialog(tk.Toplevel):
    """Prüfen und übernehmen: Werte aus dem Plan (jederzeit nachträglich im Reiter Parameter änderbar)."""

    def __init__(self, app, parent, pid, funde, dateiname):
        super().__init__(parent)
        self.app, self.pid, self.items, self.datei, self.ok = app, pid, funde, dateiname, False
        self.title(f"Werte aus Plan übernehmen – {dateiname}")
        self.geometry("980x560")
        self.configure(bg=theme.BG)
        try:
            self.transient(parent)
        except Exception:
            pass
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Diese Angaben wurden im Plan erkannt. Mit Klick auf ✓ wählst du aus, was übernommen wird. Doppelklick: Zuordnung oder Wert ändern. "
                          "Zeilen ohne Parameter sind unbeschriftete Maße – gib ihnen bei Bedarf einen Parameternamen.",
                  style="Sub.TLabel", wraplength=930).pack(anchor="w", pady=(0, 8))
        self.t = TreeList(f, [("use", "Übernehmen", 90, "center"), ("name", "Parameter", 150, "w"), ("wert", "Wert", 90, "e"),
                              ("ein", "Einheit", 60, "w"), ("stelle", "Fundstelle im Plan", 540, "w")], height=16)
        self.t.pack(fill="both", expand=True)
        self.t.tree.bind("<ButtonRelease-1>", self._klick)
        self.t.on_double(self.aendern)
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(10, 0))
        buttons(bar, [("Alle zugeordneten wählen", lambda: self.alle(True)), ("Keine", lambda: self.alle(False)), (f"{theme.S_EDIT} Zuordnung ändern", self.aendern)]).pack(side="left")
        ttk.Button(bar, text="Abbrechen", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(bar, text=f"{theme.S_OK} Ausgewählte übernehmen", style="Accent.TButton", command=self.uebernehmen).pack(side="right")
        self.refresh()
        zentrieren(self, parent)
        try:
            self.wait_visibility()
            self.grab_set()
        except Exception:
            pass
        self.wait_window(self)

    def refresh(self):
        self.t.fill([(i, ("✓" if x["use"] and x["name"] else "", x["name"], zahl_kurz(x["wert"], 4), x["einheit"], x["stelle"]))
                     for i, x in enumerate(self.items)])

    def _klick(self, ev):
        t = self.t.tree
        if t.identify_region(ev.x, ev.y) == "cell" and t.identify_column(ev.x) == "#1":
            i = self.t.selected()
            if i is not None:
                self.toggle(i)

    def toggle(self, i):
        x = self.items[i]
        if x["name"]:
            x["use"] = not x["use"]
            self.refresh()

    def alle(self, an):
        for x in self.items:
            x["use"] = an and bool(x["name"])
        self.refresh()

    def aendern(self):
        i = self.t.selected()
        if i is None:
            return
        x = self.items[i]
        v = ask(self, "Zuordnung ändern", [("name", "Parameter", "combo", sorted(parameter.bekannte_namen(self.app.db), key=str.lower)),
                                           ("wert", "Wert")], {"name": x["name"], "wert": zahl_kurz(x["wert"], 4)},
                "Leer lassen, wenn der Wert nicht übernommen werden soll.")
        if not v:
            return
        try:
            x["wert"] = parse_zahl(v["wert"])
            x["name"] = validate_name(v["name"]) if v["name"] else ""
            x["use"] = bool(x["name"])
        except Exception as e:
            return fehler(self, e)
        self.refresh()

    def uebernehmen(self):
        if not any(x["use"] and x["name"] for x in self.items):
            return messagebox.showinfo("Hinweis", "Es ist nichts zur Übernahme ausgewählt.", parent=self)
        try:
            neu, akt = planimport.uebernehmen(self.app.db, self.pid, self.items, self.datei)
        except Exception as e:
            return fehler(self, e)
        self.ok = True
        messagebox.showinfo("Plan eingelesen", f"{neu} Parameter neu angelegt, {akt} aktualisiert.\nDie Werte kannst du im Reiter Parameter jederzeit ändern.", parent=self)
        self.destroy()
