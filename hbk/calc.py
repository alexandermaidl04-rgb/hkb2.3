"""Kalkulationskern: sichere Formelberechnung, Kalkulation, Rechenweg."""
import ast
import math
import operator
import unicodedata

from .util import (eur, fmt_zeit, now_iso, parse_zahl, preis_fmt, to_de, to_de_ts, today_iso, zahl,
                   zahl_kurz)


class FormelFehler(Exception):
    pass


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
        ast.FloorDiv: operator.floordiv}
_FUNCS = {"round": lambda x, nd=0: round(x, int(nd)), "min": min, "max": max, "sqrt": math.sqrt,
          "ceil": math.ceil, "floor": math.floor, "abs": abs,
          # Winkel in Grad (Dachneigung!)
          "sin": lambda x: math.sin(math.radians(x)), "cos": lambda x: math.cos(math.radians(x)),
          "tan": lambda x: math.tan(math.radians(x)), "atan": lambda x: math.degrees(math.atan(x))}
_FUNCS.update({"wurzel": _FUNCS["sqrt"], "runden": _FUNCS["round"], "aufrunden": _FUNCS["ceil"],
               "abrunden": _FUNCS["floor"]})


def _key(name):
    return unicodedata.normalize("NFKC", str(name)).lower()


def evaluate(expr, variables=None):
    """Wertet eine Formel sicher aus (nur Zahlen, + - * / ^, Klammern, Parameter,
    round/min/max/sqrt/ceil/floor/abs). Dezimalkomma erlaubt, Funktionsargumente mit ';'."""
    s = str(expr if expr is not None else "").strip()
    if not s:
        raise FormelFehler("Formel ist leer")
    s = (s.replace(",", ".").replace(";", ",").replace("×", "*").replace("·", "*")
          .replace("−", "-").replace("^", "**"))
    try:
        tree = ast.parse(s, mode="eval")
    except SyntaxError:
        raise FormelFehler(f"Ungültige Formel: {expr}")
    vars_l = {_key(k): v for k, v in (variables or {}).items()}

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return float(n.value)
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(b) > 50:
                raise FormelFehler("Exponent zu groß")
            try:
                return float(_OPS[type(n.op)](a, b))
            except ZeroDivisionError:
                raise FormelFehler("Division durch 0")
            except (TypeError, ValueError, OverflowError):
                raise FormelFehler("Rechenfehler in Formel")
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = ev(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.Name):
            k = _key(n.id)
            if k in vars_l:
                return float(vars_l[k])
            if k == "pi":
                return math.pi
            raise FormelFehler(f"Unbekannter Parameter '{n.id}'")
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id.lower() in _FUNCS and not n.keywords):
            try:
                return float(_FUNCS[n.func.id.lower()](*[ev(a) for a in n.args]))
            except FormelFehler:
                raise
            except (TypeError, ValueError, OverflowError):
                raise FormelFehler("Rechenfehler in Funktion")
        raise FormelFehler(f"Nicht erlaubter Ausdruck in Formel: {expr}")

    return ev(tree)


def eval_parameter(paare):
    """paare: [(name, formel)]. Parameter dürfen sich aufeinander beziehen.
    -> (werte {name: float}, fehler {name: text})"""
    werte, offen = {}, list(paare)
    fehler = {}
    while offen:
        rest = []
        for name, formel in offen:
            try:
                werte[name] = evaluate(formel, werte)
            except FormelFehler as e:
                rest.append((name, formel))
                fehler[name] = str(e)
        if len(rest) == len(offen):
            break
        for name, _ in offen:
            if name in werte:
                fehler.pop(name, None)
        offen = rest
    for name, _ in offen:
        werte.setdefault(name, 0.0)
    return werte, {n: m for n, m in fehler.items() if n in {x for x, _ in offen}}


def _lookup(werte, name):
    k = _key(name)
    for n, v in werte.items():
        if _key(n) == k:
            return v
    return None


class Ctx:
    """Rechenkontext: Parameterwerte, Stichtag, Standardwerte, optionaler Projekt-Aufschlag."""

    def __init__(self, db, werte=None, stichtag=None, override=None):
        s = db.settings()
        self.db = db
        self.werte = werte or {}
        self.stichtag = stichtag or today_iso()
        self.override = override
        self.std_lohn = parse_zahl(s.get("lohnsatz", "50"))
        self.std_auf = parse_zahl(s.get("aufschlag", "8"))
        v = _lookup(self.werte, "Lohnsatz")
        self.projekt_lohn = v


def _ev(formel, werte, warn, wo):
    try:
        return evaluate(formel, werte)
    except FormelFehler as e:
        warn.append(f"{wo}: {e}")
        return 0.0


def leistung_zeilen(db, lid, menge, ctx, warn, label=""):
    """Berechnet eine Leistung für die gegebene Menge: Material (EK -> Aufschlag -> VK) und Lohnanteile."""
    mats, lohn = [], []
    for m in db.q(
            "SELECT lm.id, lm.menge, lm.verschnitt, lm.menge_fix, lm.bezeichnung lm_bez, lm.preisaufschlag lm_pa, "
            "a.id aid, a.nr, a.bezeichnung, a.einheit, a.preisaufschlag a_pa "
            "FROM leistung_material lm JOIN artikel a ON a.id=lm.artikel_id WHERE lm.leistung_id=? ORDER BY lm.id", (lid,)):
        je = _ev(m["menge"], ctx.werte, warn, f"{label}Artikel {m['nr']}: Menge")
        ma = m["verschnitt"] or 0.0
        mfix = bool(m["menge_fix"])
        gesamt = je * (1.0 if mfix else menge) * (1 + ma / 100)
        ek, pdat = db.preis_at(m["aid"], ctx.stichtag)
        if ek is None:
            warn.append(f"{label}Artikel {m['nr']} hat zum {to_de(ctx.stichtag)} keinen Preis (mit 0 € gerechnet).")
            ek = 0.0
        if ctx.override is not None:
            pa, quelle = ctx.override, "Projekt"
        elif m["lm_pa"] is not None:
            pa, quelle = m["lm_pa"], "Leistung"
        elif m["a_pa"] is not None:
            pa, quelle = m["a_pa"], "Artikel"
        else:
            pa, quelle = ctx.std_auf, "Standard"
        vk = ek * (1 + pa / 100)
        mats.append({"id": m["id"], "artikel_nr": m["nr"], "bezeichnung": m["lm_bez"] or m["bezeichnung"],
                     "einheit": m["einheit"], "formel": m["menge"], "menge_je_einheit": je, "verschnitt": ma, "menge_fix": mfix,
                     "menge_gesamt": gesamt, "ek": ek, "preis_datum": pdat or "", "aufschlag": pa,
                     "aufschlag_quelle": quelle, "aufschlag_eigen": m["lm_pa"] is not None, "vk": vk,
                     "summe_ek": round(gesamt * ek, 2), "summe": round(gesamt * vk, 2)})
    for r in db.q("SELECT lo.*, la.satz la_satz, la.bezeichnung la_bez FROM leistung_lohn lo "
                  "LEFT JOIN lohnarten la ON la.id=lo.lohnart_id WHERE lo.leistung_id=? ORDER BY lo.id", (lid,)):
        je = _ev(r["menge"], ctx.werte, warn, f"{label}Lohnanteil {r['bezeichnung']}: Menge")
        fix = bool(r["menge_fix"])
        faktor = je if fix else je * menge
        stunden = r["zeit_h"] * faktor
        if r["satz"] is not None:
            satz, quelle = r["satz"], "Lohnanteil"
        elif r["la_satz"] is not None:
            satz, quelle = r["la_satz"], r["la_bez"] or "Lohnart"
        elif ctx.projekt_lohn is not None:
            satz, quelle = ctx.projekt_lohn, "Projekt"
        else:
            satz, quelle = ctx.std_lohn, "Standard"
        lohn.append({"id": r["id"], "bezeichnung": r["bezeichnung"], "einheit": r["einheit"], "zeit_h": r["zeit_h"],
                     "menge_formel": r["menge"], "menge": je, "menge_fix": fix, "faktor": faktor, "stunden": stunden,
                     "satz": satz, "satz_quelle": quelle, "summe": round(stunden * satz, 2)})
    mek = round(sum(x["summe_ek"] for x in mats), 2)
    mvk = round(sum(x["summe"] for x in mats), 2)
    lsum = round(sum(x["summe"] for x in lohn), 2)
    std = sum(x["stunden"] for x in lohn)
    return {"material": mats, "lohn": lohn, "material_ek": mek, "material_vk": mvk, "lohn_summe": lsum,
            "stunden": std, "summe": round(mvk + lsum, 2), "summe_ek": round(mek + lsum, 2)}


def berechne_leistung(db, lid, menge=1.0, stichtag=None, werte=None):
    """Einzelberechnung einer Leistung (Stammdaten-Editor, Analyse, Export)."""
    l = db.one("SELECT * FROM leistungen WHERE id=?", (lid,))
    warn = []
    z = leistung_zeilen(db, lid, menge, Ctx(db, werte, stichtag), warn)
    z["warnungen"] = warn
    z["leistung"] = dict(l)
    z["menge"] = menge
    return z


def berechne(db, projekt_id):
    """Berechnet ein Projekt vollständig (selbsterklärendes Ergebnis, als Snapshot speicherbar)."""
    p = db.one("SELECT * FROM projekte WHERE id=?", (projekt_id,))
    if not p:
        raise ValueError("Projekt nicht gefunden")
    stichtag = p["stichtag"] or today_iso()
    warn = []
    prow = db.q("SELECT name,wert,einheit FROM parameter WHERE projekt_id=? ORDER BY id", (projekt_id,))
    werte, fehler = eval_parameter([(r["name"], r["wert"]) for r in prow])
    for n, m in fehler.items():
        warn.append(f"Parameter '{n}': {m}")
    params = [{"name": r["name"], "formel": r["wert"], "wert": werte.get(r["name"], 0.0),
               "einheit": r["einheit"] or ""} for r in prow]
    ctx = Ctx(db, werte, stichtag, p["aufschlag_override"])

    def sysw(name, key):
        v = _lookup(werte, name)
        return v if v is not None else parse_zahl(db.get_setting(key))
    gk_pct, gew_pct, mwst_pct = sysw("Gemeinkosten", "gemeinkosten"), sysw("Gewinnaufschlag", "gewinn"), sysw("MwSt", "mwst")

    positionen = []
    for i, pos in enumerate(db.q(
            "SELECT po.id, po.menge, po.bemerkung, l.id lid, l.nr l_nr, l.bezeichnung, l.einheit FROM positionen po "
            "JOIN leistungen l ON l.id=po.leistung_id WHERE po.projekt_id=? ORDER BY po.sort, po.id", (projekt_id,)), 1):
        menge = _ev(pos["menge"], werte, warn, f"Position {i} ({pos['bezeichnung']}): Menge")
        z = leistung_zeilen(db, pos["lid"], menge, ctx, warn, label=f"Position {i}: ")
        positionen.append({
            "pos": i, "id": pos["id"], "leistung_id": pos["lid"], "leistung_nr": pos["l_nr"],
            "bezeichnung": pos["bezeichnung"], "einheit": pos["einheit"], "menge_formel": pos["menge"], "menge": menge,
            "material": z["material"], "lohn_zeilen": z["lohn"], "material_ek": z["material_ek"],
            "material_summe": z["material_vk"], "lohn": z["lohn_summe"], "stunden": z["stunden"],
            "summe": z["summe"], "ep_vk": round(z["summe"] / menge, 4) if menge else 0.0,
            "bemerkung": pos["bemerkung"] or ""})

    mek = round(sum(x["material_ek"] for x in positionen), 2)
    mvk = round(sum(x["material_summe"] for x in positionen), 2)
    lohn = round(sum(x["lohn"] for x in positionen), 2)
    stunden = sum(x["stunden"] for x in positionen)
    direkt = round(mvk + lohn, 2)
    gk = round(direkt * gk_pct / 100, 2)
    selbst = round(direkt + gk, 2)
    gewinn = round(selbst * gew_pct / 100, 2)
    netto = round(selbst + gewinn, 2)
    mwst = round(netto * mwst_pct / 100, 2)
    return {
        "version": 2, "erstellt": now_iso(),
        "projekt": {"nr": p["nr"], "bezeichnung": p["bezeichnung"], "kunde": p["kunde"] or "", "ort": p["ort"] or "",
                    "status": p["status"] or "", "datum": p["datum"] or "", "stichtag": stichtag},
        "parameter": params,
        "satz": {"lohnsatz": ctx.std_lohn, "aufschlag": ctx.std_auf, "aufschlag_projekt": p["aufschlag_override"],
                 "gemeinkosten": gk_pct, "gewinn": gew_pct, "mwst": mwst_pct},
        "positionen": positionen,
        "summen": {"material_ek": mek, "aufschlag": round(mvk - mek, 2), "material": mvk, "lohn": lohn,
                   "stunden": stunden, "direkt": direkt, "gemeinkosten": gk, "selbstkosten": selbst,
                   "gewinn": gewinn, "netto": netto, "mwst": mwst, "brutto": round(netto + mwst, 2)},
        "warnungen": warn,
    }


def rechenweg(r):
    """Rechenweg als Textzeilen (aus Ergebnis/Snapshot; erkennt ältere Snapshot-Versionen)."""
    if r.get("version", 1) < 2:
        return _rechenweg_v1(r)
    pj, sz, sm = r["projekt"], r["satz"], r["summen"]
    L = [f"RECHENWEG – {pj['nr']} {pj['bezeichnung']}",
         f"Preisstichtag: {to_de(pj['stichtag'])}   |   Berechnet am: {to_de_ts(r['erstellt'])}"]
    if sz.get("aufschlag_projekt") is not None:
        L.append(f"Materialaufschlag für dieses Projekt fest vorgegeben: {zahl_kurz(sz['aufschlag_projekt'])} %")
    L += ["", "PARAMETER"]
    for p in r["parameter"]:
        f = "" if _is_plain(p["formel"], p["wert"]) else f"   [{p['formel']}]"
        L.append(f"  {p['name']} = {zahl_kurz(p['wert'])} {p['einheit']}{f}")
    L.append("")
    for x in r["positionen"]:
        L.append(f"POSITION {x['pos']}: {x['leistung_nr']} {x['bezeichnung']}")
        fm = "" if _is_plain(x["menge_formel"], x["menge"]) else f" [{x['menge_formel']}]"
        L.append(f"  Menge: {zahl_kurz(x['menge'])} {x['einheit']}{fm}")
        for m in x["material"]:
            fm2 = "" if _is_plain(m["formel"], m["menge_je_einheit"]) else f" [{m['formel']}]"
            ma = f" × (1 + {zahl_kurz(m['verschnitt'])} % Mengenaufschlag)" if m["verschnitt"] else ""
            L.append(f"  Material {m['artikel_nr']} {m['bezeichnung']}:")
            if m.get("menge_fix"):
                L.append(f"    {zahl_kurz(m['menge_je_einheit'])} {m['einheit']}{fm2} (Menge fix, nicht mit der Leistungsmenge multipliziert){ma}"
                         f" = {zahl_kurz(m['menge_gesamt'])} {m['einheit']}")
            else:
                L.append(f"    {zahl_kurz(m['menge_je_einheit'])} {m['einheit']}/{x['einheit']}{fm2} × {zahl_kurz(x['menge'])}{ma}"
                         f" = {zahl_kurz(m['menge_gesamt'])} {m['einheit']}")
            pd = f" (Preis gültig ab {to_de(m['preis_datum'])})" if m["preis_datum"] else " (kein Preis!)"
            L.append(f"    EK: {zahl_kurz(m['menge_gesamt'])} × {preis_fmt(m['ek'])} €/{m['einheit']}{pd} = {eur(m['summe_ek'])}")
            L.append(f"    VK: EK-Preis + {zahl_kurz(m['aufschlag'])} % Preisaufschlag ({m['aufschlag_quelle']}) = "
                     f"{preis_fmt(m['vk'])} €/{m['einheit']} → {eur(m['summe'])}")
        for o in x["lohn_zeilen"]:
            fix = " (Menge fix)" if o["menge_fix"] else f" × {zahl_kurz(x['menge'])} {x['einheit']}"
            L.append(f"  Lohn {o['bezeichnung']}:")
            L.append(f"    {fmt_zeit(o['zeit_h'])} je {o['einheit']} × {zahl_kurz(o['menge'])}{fix} = {fmt_zeit(o['stunden'])}"
                     f" × {zahl(o['satz'])} €/h ({o['satz_quelle']}) = {eur(o['summe'])}")
        L.append(f"  Positionssumme: Material {eur(x['material_summe'])} + Lohn {eur(x['lohn'])} = {eur(x['summe'])}"
                 f"   |   Zeit {fmt_zeit(x['stunden'])}   |   EP {zahl(x['ep_vk'])} €/{x['einheit']}")
        L.append("")
    def zeile(t, v, bold=False):
        return "  " + t.ljust(34) + f"{eur(v):>16}"
    L += ["KOSTENZUSAMMENSTELLUNG",
          zeile("Material (EK)", sm["material_ek"]), zeile("+ Preisaufschläge", sm["aufschlag"]),
          zeile("Material (VK)", sm["material"]), zeile(f"Lohn ({fmt_zeit(sm['stunden'])})", sm["lohn"]),
          zeile("Direkte Kosten", sm["direkt"]),
          zeile(f"Gemeinkosten {zahl_kurz(sz['gemeinkosten'])} %", sm["gemeinkosten"]),
          zeile("Selbstkosten", sm["selbstkosten"]), zeile(f"Gewinn {zahl_kurz(sz['gewinn'])} %", sm["gewinn"]),
          zeile("Netto", sm["netto"]), zeile(f"MwSt {zahl_kurz(sz['mwst'])} %", sm["mwst"]),
          zeile("BRUTTO", sm["brutto"])]
    if r["warnungen"]:
        L += ["", "WARNUNGEN"] + [f"  ! {w}" for w in r["warnungen"]]
    return L


def _rechenweg_v1(r):
    """Vollständig nachvollziehbarer Rechenweg als Textzeilen (aus dem Ergebnis/Snapshot)."""
    pj, sz, sm = r["projekt"], r["satz"], r["summen"]
    L = [f"RECHENWEG – {pj['nr']} {pj['bezeichnung']}",
         f"Preisstichtag: {to_de(pj['stichtag'])}   |   Berechnet am: {to_de_ts(r['erstellt'])}", ""]
    L.append("PARAMETER")
    for p in r["parameter"]:
        f = "" if _is_plain(p["formel"], p["wert"]) else f"   [{p['formel']}]"
        L.append(f"  {p['name']} = {zahl_kurz(p['wert'])} {p['einheit']}{f}")
    L.append("")
    for x in r["positionen"]:
        L.append(f"POSITION {x['pos']}: {x['leistung_nr']} {x['bezeichnung']}")
        fm = "" if _is_plain(x["menge_formel"], x["menge"]) else f" [{x['menge_formel']}]"
        L.append(f"  Menge: {zahl_kurz(x['menge'])} {x['einheit']}{fm}")
        L.append(f"  Lohn: {zahl_kurz(x['menge'])} {x['einheit']} × {zahl_kurz(x['zeit_h_je_einheit'])} h/{x['einheit']}"
                 f" = {zahl_kurz(x['stunden'])} h × {zahl(sz['lohnsatz'])} €/h = {eur(x['lohn'])}")
        for m in x["material"]:
            vs = f" × (1 + {zahl_kurz(m['verschnitt'])} % Verschnitt)" if m["verschnitt"] else ""
            fm2 = "" if _is_plain(m["formel"], m["menge_je_einheit"]) else f" [{m['formel']}]"
            L.append(f"  Material {m['artikel_nr']} {m['bezeichnung']}:")
            L.append(f"    {zahl_kurz(m['menge_je_einheit'])} {m['einheit']}/{x['einheit']}{fm2} × {zahl_kurz(x['menge'])}{vs}"
                     f" = {zahl_kurz(m['menge_gesamt'])} {m['einheit']}")
            pd = f" (Preis gültig ab {to_de(m['preis_datum'])})" if m["preis_datum"] else " (kein Preis!)"
            L.append(f"    {zahl_kurz(m['menge_gesamt'])} {m['einheit']} × {zahl(m['preis'])} €/{m['einheit']}{pd} = {eur(m['summe'])}")
        L.append(f"  Positionssumme: Material {eur(x['material_summe'])} + Lohn {eur(x['lohn'])} = {eur(x['summe'])}")
        L.append("")
    L += ["KOSTENZUSAMMENSTELLUNG",
          f"  Material                       {eur(sm['material']):>16}",
          f"  Lohn ({zahl_kurz(sm['stunden'])} h)".ljust(33) + f"{eur(sm['lohn']):>16}",
          f"  Direkte Kosten                 {eur(sm['direkt']):>16}",
          f"  Gemeinkosten {zahl_kurz(sz['gemeinkosten'])} %".ljust(33) + f"{eur(sm['gemeinkosten']):>16}",
          f"  Selbstkosten                   {eur(sm['selbstkosten']):>16}",
          f"  Gewinn {zahl_kurz(sz['gewinn'])} %".ljust(33) + f"{eur(sm['gewinn']):>16}",
          f"  Netto                          {eur(sm['netto']):>16}",
          f"  MwSt {zahl_kurz(sz['mwst'])} %".ljust(33) + f"{eur(sm['mwst']):>16}",
          f"  BRUTTO                         {eur(sm['brutto']):>16}"]
    if r["warnungen"]:
        L += ["", "WARNUNGEN"] + [f"  ! {w}" for w in r["warnungen"]]
    return L


def _is_plain(formel, wert):
    """True, wenn die Formel nur eine einfache Zahl ist (keine Anzeige nötig)."""
    try:
        return abs(parse_zahl(str(formel)) - wert) < 1e-12
    except (ValueError, TypeError):
        return False
