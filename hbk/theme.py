"""Optik: schlichtes helles Design mit orangen Akzenten."""
from tkinter import ttk

ORANGE = "#E8731A"
ORANGE_D = "#C25A0C"
ORANGE_L = "#FDE3CC"
BG = "#FBF8F4"
PANEL = "#F1E9E0"
FG = "#2B2B2B"
GREY = "#7A7A7A"

# schlichte Symbole (alle im Windows-Standardfont Segoe UI / Segoe UI Symbol vorhanden)
S_NEU, S_EDIT, S_DEL, S_IMPORT, S_EXPORT = "＋", "✎", "✕", "⇩", "⇧"
S_REFRESH, S_OK, S_STERN, S_ORDNER, S_MAT, S_LOHN = "⟳", "✓", "★", "▸", "▪", "◷"


def setup(root):
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except Exception:
        pass
    root.configure(bg=BG)
    st.configure(".", background=BG, foreground=FG, font=("Segoe UI", 10), bordercolor="#D8CFC5", focuscolor=ORANGE)
    st.configure("TFrame", background=BG)
    st.configure("TLabel", background=BG, foreground=FG)
    st.configure("Sub.TLabel", foreground=GREY)
    st.configure("Big.TLabel", font=("Segoe UI", 22, "bold"), foreground=ORANGE_D)
    st.configure("Zeit.TLabel", font=("Segoe UI", 20, "bold"), foreground=ORANGE_D)
    st.configure("Banner.TFrame", background="white")
    st.configure("Banner.TLabel", background="white", foreground=FG, font=("Segoe UI", 14, "bold"))
    st.configure("BannerSub.TLabel", background="white", foreground=GREY, font=("Segoe UI", 9))
    st.configure("Logo.TLabel", background="white")
    st.configure("TLabelframe", background=BG, bordercolor="#E0D5C8")
    st.configure("TLabelframe.Label", background=BG, foreground=ORANGE_D, font=("Segoe UI", 10, "bold"))
    st.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(2, 4, 2, 0))
    st.configure("TNotebook.Tab", padding=(16, 7), background=PANEL, foreground=FG, borderwidth=0)
    st.map("TNotebook.Tab", background=[("selected", ORANGE), ("active", ORANGE_L)],
           foreground=[("selected", "white")])
    st.configure("TButton", padding=(10, 4), background=PANEL, foreground=FG, borderwidth=1, relief="flat")
    st.map("TButton", background=[("active", ORANGE_L), ("pressed", ORANGE)])
    st.configure("Accent.TButton", background=ORANGE, foreground="white", font=("Segoe UI", 10, "bold"))
    st.map("Accent.TButton", background=[("active", ORANGE_D), ("pressed", ORANGE_D)])
    st.configure("TEntry", fieldbackground="white", padding=3)
    st.configure("TCombobox", fieldbackground="white", padding=3)
    st.configure("TCheckbutton", background=BG)
    st.configure("Treeview", background="white", fieldbackground="white", rowheight=26, bordercolor="#D8CFC5")
    st.map("Treeview", background=[("selected", ORANGE_L)], foreground=[("selected", FG)])
    st.configure("Treeview.Heading", background=PANEL, foreground=FG, font=("Segoe UI", 9, "bold"), relief="flat",
                 padding=(4, 5))
    st.map("Treeview.Heading", background=[("active", ORANGE_L)])
    return st
