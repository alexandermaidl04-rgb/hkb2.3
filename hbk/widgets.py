"""Wiederverwendbare UI-Bausteine: Dialoge, Listen, Ordnerbaum, Direkt-Bearbeitung per Mausklick."""
import sqlite3
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

from . import assets, theme


def fehler(parent, e):
    if isinstance(e, sqlite3.IntegrityError):
        txt = ("Das ist nicht möglich: Der Eintrag wird noch verwendet, oder die Nummer/der Name existiert bereits.\n\n"
               f"({e})")
    else:
        txt = str(e)
    messagebox.showerror("Hinweis", txt, parent=parent)


def zentrieren(win, parent):
    try:
        win.update_idletasks()
        x = parent.winfo_rootx() + max(20, (parent.winfo_width() - win.winfo_width()) // 2)
        y = parent.winfo_rooty() + max(20, (parent.winfo_height() - win.winfo_height()) // 3)
        win.geometry(f"+{x}+{y}")
    except Exception:
        pass


class FormDialog(tk.Toplevel):
    """fields: (key, label, kind='text'|'choice'|'combo'|'check'|'password', optionen)"""

    def __init__(self, parent, title, fields, values=None, hint=None, ok_text="OK", extra=None, logo=False):
        super().__init__(parent)
        self.title(title)
        try:
            if parent.winfo_viewable():
                self.transient(parent)
        except Exception:
            pass
        self.resizable(False, False)
        self.configure(bg=theme.BG)
        self.result = None
        self.vars = {}
        self.kinds = {}
        if logo:
            self._img = assets.photo("logo_login.png")
            if self._img is not None:
                kopf = ttk.Frame(self, style="Banner.TFrame", padding=(14, 12))
                kopf.pack(fill="x")
                ttk.Label(kopf, image=self._img, style="Logo.TLabel").pack()
                tk.Frame(self, height=4, bg=theme.ORANGE).pack(fill="x")
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)
        values = values or {}
        first = None
        for i, f in enumerate(fields):
            key, label = f[0], f[1]
            kind = f[2] if len(f) > 2 else "text"
            opts = f[3] if len(f) > 3 else []
            v = values.get(key)
            self.kinds[key] = kind
            if kind == "check":
                var = tk.BooleanVar(value=bool(v))
                ttk.Checkbutton(frm, text=label, variable=var).grid(row=i, column=0, columnspan=2, sticky="w", pady=4)
                self.vars[key] = var
                continue
            var = tk.StringVar(value="" if v is None else str(v))
            ttk.Label(frm, text=label).grid(row=i, column=0, sticky="w", padx=(0, 12), pady=4)
            if kind == "choice":
                w = ttk.Combobox(frm, textvariable=var, values=opts, state="readonly", width=44)
            elif kind == "combo":
                w = ttk.Combobox(frm, textvariable=var, values=opts, width=44)
            elif kind == "password":
                w = ttk.Entry(frm, textvariable=var, width=46, show="•")
            else:
                w = ttk.Entry(frm, textvariable=var, width=46)
            w.grid(row=i, column=1, sticky="ew", pady=4)
            self.vars[key] = var
            first = first or w
        r = len(fields)
        if hint:
            ttk.Label(frm, text=hint, style="Sub.TLabel", wraplength=460, justify="left").grid(
                row=r, column=0, columnspan=2, sticky="w", pady=(8, 0))
            r += 1
        bar = ttk.Frame(frm)
        bar.grid(row=r, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(bar, text="Abbrechen", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(bar, text=ok_text, style="Accent.TButton", command=self.ok).pack(side="right")
        if extra:
            ttk.Button(bar, text=extra, command=self.zusatz).pack(side="left")
        self.bind("<Return>", lambda e: self.ok())
        self.bind("<Escape>", lambda e: self.destroy())
        if first is not None:
            first.focus_set()
        zentrieren(self, parent)
        try:
            self.wait_visibility()
            self.grab_set()
        except Exception:
            pass
        self.lift()
        self.focus_force()
        self.wait_window(self)

    def zusatz(self):
        self.result = {"__extra__": True}
        self.destroy()

    def ok(self):
        self.result = {}
        for k, v in self.vars.items():
            self.result[k] = bool(v.get()) if self.kinds[k] == "check" else v.get().strip()
        self.destroy()


def ask(parent, title, fields, values=None, hint=None, ok_text="OK", extra=None, logo=False):
    return FormDialog(parent, title, fields, values, hint, ok_text, extra, logo).result


def buttons(parent, items):
    """items: (text, command) oder (text, command, True) für hervorgehobenen Knopf."""
    bar = ttk.Frame(parent)
    for it in items:
        ttk.Button(bar, text=it[0], command=it[1], style="Accent.TButton" if len(it) > 2 and it[2] else "TButton"
                   ).pack(side="left", padx=(0, 6))
    return bar


class TreeList(ttk.Frame):
    def __init__(self, parent, columns, height=14):
        """columns: (key, Überschrift, Breite, Ausrichtung)"""
        super().__init__(parent)
        keys = [c[0] for c in columns]
        self.tree = ttk.Treeview(self, columns=keys, show="headings", height=height, selectmode="browse")
        for key, label, width, anchor in columns:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor=anchor, stretch=True)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def fill(self, rows):
        sel = self.selected()
        self.tree.delete(*self.tree.get_children())
        for iid, vals in rows:
            self.tree.insert("", "end", iid=str(iid), values=vals)
        if sel is not None and self.tree.exists(str(sel)):
            self.tree.selection_set(str(sel))

    def selected(self):
        s = self.tree.selection()
        return int(s[0]) if s else None

    def on_double(self, fn):
        self.tree.bind("<Double-1>", lambda e: fn())


class FolderTree(ttk.Frame):
    """Baum aus frei anlegbaren Ordnern und Einträgen (Artikel / Leistungen).
    item_fn(suchtext) -> [(id, ordner_id, text, werte, tags)]"""

    def __init__(self, parent, db, bereich, columns, item_fn, heading="Bezeichnung", height=16, suche=True):
        super().__init__(parent)
        self.db, self.bereich, self.item_fn = db, bereich, item_fn
        self.suche = tk.StringVar()
        self.item_folder = {}
        self.on_open = None
        self._first = True
        if suche:
            bar = ttk.Frame(self)
            bar.pack(fill="x", pady=(0, 6))
            ttk.Entry(bar, textvariable=self.suche, width=26).pack(side="right")
            ttk.Label(bar, text="Suche:").pack(side="right", padx=(0, 6))
            self.suche.trace_add("write", lambda *a: self.refresh())
        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(wrap, columns=[c[0] for c in columns], show="tree headings", selectmode="browse",
                                 height=height)
        self.tree.heading("#0", text=heading, anchor="w")
        self.tree.column("#0", width=330, stretch=True)
        for key, label, width, anchor in columns:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor=anchor, stretch=False)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.tag_configure("folder", foreground=theme.ORANGE_D, font=tkfont.Font(family="Segoe UI", size=10, weight="bold"))
        self.ncols = len(columns)
        self.tree.bind("<Double-1>", self._dbl)

    def refresh(self):
        t = self.tree
        offen = {i for i in self._alle() if str(t.item(i, "open")).lower() in ("1", "true", "yes")}
        sel = t.selection()
        sel = sel[0] if sel else None
        t.delete(*t.get_children())
        such = self.suche.get().strip()
        ordner = self.db.q("SELECT * FROM ordner WHERE bereich=? ORDER BY name COLLATE NOCASE", (self.bereich,))
        ids = {o["id"] for o in ordner}
        items = self.item_fn(such)
        self.item_folder = {i[0]: i[1] for i in items}
        gruppen = {}
        for it in items:
            gruppen.setdefault(it[1] if it[1] in ids else None, []).append(it)

        def add_items(parent, oid):
            for iid, _, text, werte, tags in gruppen.get(oid, []):
                t.insert(parent, "end", iid=f"i{iid}", text=text, values=werte, tags=tags)

        def add_folder(parent, pid):
            n = 0
            for o in ordner:
                if o["parent_id"] == pid or (pid is None and o["parent_id"] not in ids):
                    fid = f"f{o['id']}"
                    t.insert(parent, "end", iid=fid, text=o["name"], values=("",) * self.ncols, tags=("folder",),
                             open=self._first or fid in offen or bool(such))
                    c = add_folder(fid, o["id"])
                    add_items(fid, o["id"])
                    c += len(gruppen.get(o["id"], []))
                    if such and c == 0:
                        t.delete(fid)
                    else:
                        n += c
            return n
        add_folder("", None)
        add_items("", None)
        self._first = False
        if sel and t.exists(sel):
            t.selection_set(sel)

    def _alle(self):
        out, stack = [], list(self.tree.get_children())
        while stack:
            i = stack.pop()
            out.append(i)
            stack += list(self.tree.get_children(i))
        return out

    def _dbl(self, e):
        k, i = self.sel()
        if k == "i" and self.on_open:
            self.on_open(i)

    def sel(self):
        s = self.tree.selection()
        if not s:
            return None, None
        return s[0][0], int(s[0][1:])

    def sel_item(self):
        k, i = self.sel()
        return i if k == "i" else None

    def sel_folder(self):
        k, i = self.sel()
        return i if k == "f" else None

    def target_folder(self):
        """Ordner, in dem Neues angelegt werden soll (gewählter Ordner bzw. Ordner des gewählten Eintrags)."""
        k, i = self.sel()
        if k == "f":
            return i
        if k == "i":
            return self.item_folder.get(i)
        return None

    def select_item(self, iid):
        n = f"i{iid}"
        if self.tree.exists(n):
            self.tree.selection_set(n)
            self.tree.see(n)


class CellEditor:
    """Legt ein Eingabefeld über eine Zelle (Direktbearbeitung per Mausklick). Enter = übernehmen, Esc = abbrechen."""

    def __init__(self, tree, iid, col, text, on_commit):
        self.tree, self.on_commit, self.done = tree, on_commit, False
        box = tree.bbox(iid, col)
        if not box:
            return
        x, y, w, h = box
        self.e = ttk.Entry(tree)
        self.e.place(x=x, y=y, width=max(w, 70), height=h)
        self.e.insert(0, text)
        self.e.select_range(0, "end")
        self.e.focus_set()
        self.e.bind("<Return>", lambda ev: self.commit())
        self.e.bind("<Escape>", lambda ev: self.cancel())
        self.e.bind("<FocusOut>", lambda ev: self.commit())

    def commit(self):
        if self.done:
            return
        self.done = True
        val = self.e.get()
        self.e.destroy()
        self.on_commit(val)

    def cancel(self):
        if not self.done:
            self.done = True
            self.e.destroy()
