"""Zugriff auf mitgelieferte Dateien (Logo, Icons) – funktioniert im Entwicklungsordner und im PyInstaller-Programm."""
import os
import sys


def asset_pfad(name):
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "hbk", "assets", name)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", name)


def photo(name):
    """tk.PhotoImage der Datei oder None. (Die Referenz muss vom Aufrufer gehalten werden.)"""
    import tkinter as tk
    p = asset_pfad(name)
    if not os.path.exists(p):
        return None
    try:
        return tk.PhotoImage(file=p)
    except Exception:
        return None
