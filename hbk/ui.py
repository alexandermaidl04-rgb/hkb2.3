"""Hauptfenster, Passwort-Abfrage und Dashboard."""
import json
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME, __version__, assets, auth, theme
from .db import DB, seed_demo
from .ui_leistung import LeistungenTab
from .ui_projekt import ProjektWindow, ProjekteTab
from .ui_stamm import StammdatenTab
from .util import eur, parse_zahl, to_de, to_de_ts, today_iso, zahl
from .widgets import TreeList, ask, fehler, zentrieren


class DashboardTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=12)
        self.app = app
        self.cards = {}
        top = ttk.Frame(self)
        top.pack(fill="x")
        for key, label in (("projekte", "Projekte"), ("artikel", "Artikel"), ("leistungen", "Leistungen")):
            f = ttk.LabelFrame(top, text=label, padding=(26, 8))
            f.pack(side="left", padx=(0, 12))
            lbl = ttk.Label(f, text="0", style="Big.TLabel")
            lbl.pack()
            self.cards[key] = lbl
        grid = ttk.Frame(self)
        grid.pack(fill="both", expand=True, pady=(12, 0))
        grid.columnconfigure((0, 1), weight=1)
        grid.rowconfigure((0, 1), weight=1)
        self.t_proj = self._box(grid, 0, 0, "Kürzlich bearbeitete Projekte", [("nr", "Nr.", 90, "w"), ("bez", "Bezeichnung", 180, "w"), ("kunde", "Kunde", 120, "w"), ("geaendert", "Geändert", 110, "w")])
        self.t_calc = self._box(grid, 0, 1, "Letzte Kalkulationen (Snapshots)", [("nr", "Projekt", 90, "w"), ("titel", "Titel", 160, "w"), ("erstellt", "Erstellt", 110, "w"), ("brutto", "Brutto", 100, "e")])
        self.t_preis = self._box(grid, 1, 0, "Preisänderungen", [("nr", "Artikel", 70, "w"), ("bez", "Bezeichnung", 150, "w"), ("ab", "Gültig ab", 80, "w"), ("alt", "Vorher", 70, "e"), ("neu", "Neu", 70, "e"), ("diff", "Änderung", 70, "e")])
        wf = ttk.LabelFrame(grid, text="Warnungen", padding=6)
        wf.grid(row=1, column=1, sticky="nsew", padx=4, pady=4)
        self.warn = tk.Listbox(wf, height=8, activestyle="none", relief="flat", highlightthickness=0, bg="white", selectbackground=theme.ORANGE_L, selectforeground=theme.FG)
        self.warn.pack(fill="both", expand=True)
        self.t_proj.on_double(lambda: self.t_proj.selected() and app.open_projekt(self.t_proj.selected()))

    def _box(self, grid, r, c, title, cols):
        lf = ttk.LabelFrame(grid, text=title, padding=6)
        lf.grid(row=r, column=c, sticky="nsew", padx=4, pady=4)
        t = TreeList(lf, cols, height=6)
        t.pack(fill="both", expand=True)
        return t

    def refresh(self):
        db = self.app.db
        for key, sql in (("projekte", "SELECT COUNT(*) c FROM projekte"), ("artikel", "SELECT COUNT(*) c FROM artikel WHERE stamm=1"),
                         ("leistungen", "SELECT COUNT(*) c FROM leistungen")):
            self.cards[key].config(text=str(db.one(sql)["c"]))
        self.t_proj.fill([(r["id"], (r["nr"], r["bezeichnung"], r["kunde"], to_de_ts(r["geaendert"]))) for r in db.q(
            "SELECT id,nr,bezeichnung,kunde,geaendert FROM projekte ORDER BY geaendert DESC LIMIT 8")])
        rows = []
        for r in db.q("SELECT s.id,s.erstellt,s.titel,s.daten,p.nr FROM snapshots s JOIN projekte p ON p.id=s.projekt_id ORDER BY s.erstellt DESC, s.id DESC LIMIT 8"):
            rows.append((r["id"], (r["nr"], r["titel"], to_de_ts(r["erstellt"]), eur(json.loads(r["daten"])["summen"]["brutto"]))))
        self.t_calc.fill(rows)
        rows = []
        for r in db.q("SELECT p.id, a.nr, a.bezeichnung, p.gueltig_ab, p.preis, (SELECT preis FROM preise p2 WHERE p2.artikel_id=p.artikel_id AND "
                      "p2.gueltig_ab<p.gueltig_ab ORDER BY p2.gueltig_ab DESC LIMIT 1) vorher FROM preise p JOIN artikel a ON a.id=p.artikel_id "
                      "WHERE a.stamm=1 ORDER BY p.gueltig_ab DESC, p.id DESC LIMIT 8"):
            alt = r["vorher"]
            diff = "" if not alt else f"{(r['preis'] / alt - 1) * 100:+.1f} %".replace(".", ",")
            rows.append((r["id"], (r["nr"], r["bezeichnung"], to_de(r["gueltig_ab"]), zahl(alt) if alt else "–", zahl(r["preis"]), diff)))
        self.t_preis.fill(rows)
        self.warn.delete(0, "end")
        for t in db.warnungen() or ["Keine Warnungen."]:
            self.warn.insert("end", t)


def passwort_zuruecksetzen(root, db):
    """Zurücksetzen mit dem Masterkey. -> True, wenn ein neues Passwort gesetzt wurde."""
    v = ask(root, "HBK – Passwort zurücksetzen", [("mk", "Masterkey", "password"), ("pw1", "Neues Passwort", "password"),
                                                  ("pw2", "Neues Passwort wiederholen", "password")],
            hint="Mit dem Masterkey legst du ein neues Passwort fest. Deine Daten bleiben unverändert.", ok_text="Zurücksetzen", logo=True)
    if not v:
        return False
    try:
        if v["pw1"] != v["pw2"]:
            raise ValueError("Die beiden neuen Passwörter stimmen nicht überein.")
        auth.reset_password(db, v["mk"], v["pw1"])
    except Exception as e:
        fehler(root, e)
        return False
    messagebox.showinfo("Passwort", "Das Passwort wurde zurückgesetzt.", parent=root)
    return True


def passwort_dialog(root, db):
    """Beim Start: erstmalige Einrichtung oder Anmeldung. -> True bei Erfolg."""
    if not auth.has_password(db):
        while True:
            v = ask(root, "HBK – Erstmalige Einrichtung", [("pw1", "Neues Passwort", "password"), ("pw2", "Passwort wiederholen", "password")],
                    hint="Dieses Passwort wird bei jedem Programmstart abgefragt. Falls du es vergisst, kannst du es mit dem Masterkey zurücksetzen.",
                    ok_text="Passwort festlegen", logo=True)
            if not v:
                return False
            try:
                if v["pw1"] != v["pw2"]:
                    raise ValueError("Die beiden Passwörter stimmen nicht überein.")
                auth.set_password(db, v["pw1"])
                return True
            except Exception as e:
                fehler(root, e)
    for _ in range(50):
        v = ask(root, "HBK – Anmeldung", [("pw", "Passwort", "password")], ok_text="Anmelden", extra="Passwort vergessen …", logo=True)
        if not v:
            return False
        if v.get("__extra__"):
            if passwort_zuruecksetzen(root, db):
                return True
            continue
        if auth.check_password(db, v["pw"]):
            return True
        messagebox.showerror("Anmeldung", "Falsches Passwort.", parent=root)
    return False


class App:
    def __init__(self):
        self.db = DB()
        self.root = tk.Tk()
        theme.setup(self.root)
        self.root.withdraw()
        self.ok = passwort_dialog(self.root, self.db)
        if not self.ok:
            self.root.destroy()
            return
        self.root.title(f"{APP_NAME} {__version__}")
        self.root.geometry("1180x740")
        m = tk.Menu(self.root)
        d = tk.Menu(m, tearoff=0)
        d.add_command(label="Einstellungen …", command=self.einstellungen)
        d.add_command(label="Passwort ändern …", command=self.passwort_aendern)
        d.add_command(label="Datenbank sichern …", command=self.sichern)
        d.add_command(label="Beispieldaten laden", command=self.demo)
        d.add_separator()
        d.add_command(label="Beenden", command=self.root.destroy)
        m.add_cascade(label="Datei", menu=d)
        h = tk.Menu(m, tearoff=0)
        h.add_command(label="Speicherort der Datenbank", command=lambda: messagebox.showinfo("Datenbank", self.db.path))
        h.add_command(label="Über HBK", command=lambda: messagebox.showinfo("Über HBK", f"{APP_NAME}\nVersion {__version__}\nLokale Einzelplatzlösung (SQLite)"))
        m.add_cascade(label="Hilfe", menu=h)
        self.root.config(menu=m)
        try:
            self._icon = assets.photo("icon.png")
            if self._icon is not None:
                self.root.iconphoto(True, self._icon)
            if sys.platform.startswith("win"):
                self.root.iconbitmap(assets.asset_pfad("HBK.ico"))
        except Exception:
            pass
        banner = ttk.Frame(self.root, style="Banner.TFrame", padding=(16, 8))
        banner.pack(fill="x")
        self._logo = assets.photo("logo_header.png")
        if self._logo is not None:
            ttk.Label(banner, image=self._logo, style="Logo.TLabel").pack(side="left")
        else:
            ttk.Label(banner, text="HBK", style="Banner.TLabel").pack(side="left")
        ttk.Label(banner, text="   Holzbau Kalkulation", style="Banner.TLabel").pack(side="left")
        ttk.Label(banner, text=f"Version {__version__}", style="BannerSub.TLabel").pack(side="right", anchor="s")
        tk.Frame(self.root, height=4, bg=theme.ORANGE).pack(fill="x")
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.tabs = []
        for cls, name in ((DashboardTab, "⌂  Dashboard"), (ProjekteTab, "▤  Projekte"), (StammdatenTab, "▦  Stammdaten"), (LeistungenTab, "≡  Leistungen")):
            t = cls(self.nb, self)
            self.nb.add(t, text=name)
            self.tabs.append(t)
        self.refresh_all()
        self.root.deiconify()

    def refresh_all(self):
        for t in self.tabs:
            t.refresh()

    def open_projekt(self, pid):
        ProjektWindow(self, pid)

    def einstellungen(self):
        v = ask(self.root, "Einstellungen", [
            ("firma", "Firmenname (für PDF)"), ("adresse", "Adresse (für PDF)"),
            ("lohnsatz", "Standard-Stundenverrechnungssatz (€/h)"), ("aufschlag", "Standard-Preisaufschlag auf Material (%)"),
            ("gemeinkosten", "Standard-Gemeinkosten (%)"), ("gewinn", "Standard-Gewinnaufschlag (%)"), ("mwst", "Standard-MwSt (%)")],
            self.db.settings(), "Die Standardwerte gelten für neue Projekte bzw. überall dort, wo kein eigener Wert hinterlegt ist.")
        if v:
            try:
                for k in ("lohnsatz", "aufschlag", "gemeinkosten", "gewinn", "mwst"):
                    parse_zahl(v[k])
                for k, val in v.items():
                    self.db.set_setting(k, val.replace(",", ".") if k in ("lohnsatz", "aufschlag", "gemeinkosten", "gewinn", "mwst") else val)
            except Exception as e:
                return fehler(self.root, e)
            self.refresh_all()

    def passwort_aendern(self):
        v = ask(self.root, "Passwort ändern", [("alt", "Aktuelles Passwort", "password"), ("neu", "Neues Passwort", "password"),
                                               ("neu2", "Neues Passwort wiederholen", "password")], ok_text="Ändern")
        if not v:
            return
        try:
            if not auth.check_password(self.db, v["alt"]):
                raise ValueError("Das aktuelle Passwort ist falsch.")
            if v["neu"] != v["neu2"]:
                raise ValueError("Die neuen Passwörter stimmen nicht überein.")
            auth.set_password(self.db, v["neu"])
        except Exception as e:
            return fehler(self.root, e)
        messagebox.showinfo("Passwort", "Passwort wurde geändert.")

    def sichern(self):
        p = filedialog.asksaveasfilename(defaultextension=".db", initialfile=f"HBK_Sicherung_{today_iso()}.db", filetypes=[("HBK-Datenbank", "*.db")])
        if p:
            self.db.backup(p)
            messagebox.showinfo("Sicherung", "Datenbank wurde gesichert.")

    def demo(self):
        if seed_demo(self.db):
            self.refresh_all()
            messagebox.showinfo("Beispieldaten", "Beispieldaten wurden angelegt (Projekt P-DEMO-001).")
        else:
            messagebox.showinfo("Beispieldaten", "Es sind bereits Artikel vorhanden – Beispieldaten wurden nicht geladen.")

    def run(self):
        if self.ok:
            self.root.mainloop()
