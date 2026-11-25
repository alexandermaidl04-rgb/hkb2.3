"""PDF-Ausgabe der Kalkulation (inkl. vollständigem Rechenweg)."""
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping
from reportlab.platypus import (Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

from .assets import asset_pfad
from .calc import rechenweg
from .util import eur, fmt_zeit, to_de, to_de_ts, zahl, zahl_kurz

import os

_KANDIDATEN = [
    (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\cour.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
]


def _fonts():
    """Registriert eine Unicode-fähige Schrift (Arial/DejaVu), damit ², €, ä usw. sicher erscheinen."""
    for reg, bold, mono in _KANDIDATEN:
        if os.path.exists(reg) and os.path.exists(bold) and os.path.exists(mono):
            pdfmetrics.registerFont(TTFont("HBK", reg))
            pdfmetrics.registerFont(TTFont("HBK-B", bold))
            pdfmetrics.registerFont(TTFont("HBK-M", mono))
            for b, i in ((0, 0), (1, 0), (0, 1), (1, 1)):
                addMapping("HBK", b, i, "HBK-B" if b else "HBK")
            return "HBK", "HBK-B", "HBK-M"
    return "Helvetica", "Helvetica-Bold", "Courier"


BRAUN = colors.HexColor("#5b3a1e")
HELL = colors.HexColor("#f1e8dc")


def erzeuge_pdf(r, pfad, firma="", adresse=""):
    F, FB, FM = _fonts()
    ss = getSampleStyleSheet()
    for st in ss.byName.values():
        if hasattr(st, "fontName"):
            st.fontName = FB if "Bold" in st.fontName else F
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=BRAUN, fontSize=18, alignment=0)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=BRAUN, fontSize=12, spaceBefore=10)
    n = ParagraphStyle("n", parent=ss["Normal"], fontSize=9, leading=12)
    mono = ParagraphStyle("mono", parent=ss["Normal"], fontName=FM, fontSize=7.5, leading=9.2)
    right = ParagraphStyle("r", parent=n, alignment=2)

    pj, sm, sz = r["projekt"], r["summen"], r["satz"]
    el = []
    logo = asset_pfad("logo.png")
    firmatext = Paragraph(f"<b>{escape(firma)}</b>" + (f"<br/>{escape(adresse)}" if adresse else ""), n) if firma else ""
    if os.path.exists(logo):
        from reportlab.lib.utils import ImageReader
        iw, ih = ImageReader(logo).getSize()
        b = 46 * mm
        kopf_t = Table([[firmatext, Image(logo, width=b, height=b * ih / iw)]], colWidths=[124 * mm, 46 * mm])
        kopf_t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        el.append(kopf_t)
    elif firma:
        el.append(firmatext)
    el.append(Paragraph(f"Kalkulation {escape(pj['nr'])}", h1))
    el.append(Paragraph(escape(pj["bezeichnung"]), ParagraphStyle("sub", parent=n, fontSize=12)))
    el.append(Spacer(1, 6))

    kopf = [["Kunde", pj["kunde"], "Projektnummer", pj["nr"]],
            ["Ort", pj["ort"], "Status", pj["status"]],
            ["Projektdatum", to_de(pj["datum"]), "Preisstichtag", to_de(pj["stichtag"])],
            ["", "", "Berechnet am", to_de_ts(r["erstellt"])]]
    t = Table([[Paragraph(escape(str(c)), n) for c in row] for row in kopf],
              colWidths=[28 * mm, 55 * mm, 32 * mm, 55 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), HELL), ("BOX", (0, 0), (-1, -1), 0.5, BRAUN),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el += [t, Spacer(1, 8)]

    el.append(Paragraph("Projektparameter", h2))
    prm = [["Parameter", "Wert", "Einheit"]] + [[p["name"], zahl_kurz(p["wert"]), p["einheit"]] for p in r["parameter"]]
    el.append(_tabelle(prm, [70 * mm, 40 * mm, 30 * mm], n, rechts=(1,)))

    el.append(Paragraph("Positionen", h2))
    pos = [["Nr.", "Leistung", "Menge", "Material", "Lohn", "Zeit", "Summe"]]
    for x in r["positionen"]:
        pos.append([str(x["pos"]), f"{x['leistung_nr']} {x['bezeichnung']}",
                    f"{zahl_kurz(x['menge'])} {x['einheit']}", eur(x["material_summe"]),
                    eur(x["lohn"]), fmt_zeit(x.get("stunden", 0)), eur(x["summe"])])
    el.append(_tabelle(pos, [11 * mm, 34 * mm, 19 * mm, 25 * mm, 26 * mm, 29 * mm, 26 * mm], n, rechts=(2, 3, 4, 5, 6)))

    el.append(Paragraph("Kostenzusammenstellung", h2))
    ks = ([["Material (EK)", eur(sm["material_ek"])], ["Preisaufschläge", eur(sm["aufschlag"])]]
          if "material_ek" in sm else []) + [
          ["Material" + (" (VK)" if "material_ek" in sm else ""), eur(sm["material"])],
          [f"Lohn ({fmt_zeit(sm['stunden']) if 'material_ek' in sm else zahl_kurz(sm['stunden']) + ' h'})", eur(sm["lohn"])],
          ["Direkte Kosten", eur(sm["direkt"])],
          [f"Gemeinkosten {zahl_kurz(sz['gemeinkosten'])} %", eur(sm["gemeinkosten"])],
          ["Selbstkosten", eur(sm["selbstkosten"])],
          [f"Gewinn {zahl_kurz(sz['gewinn'])} %", eur(sm["gewinn"])],
          ["Nettosumme", eur(sm["netto"])],
          [f"MwSt {zahl_kurz(sz['mwst'])} %", eur(sm["mwst"])],
          ["Bruttosumme", eur(sm["brutto"])]]
    kt = Table([[Paragraph(a, n), Paragraph(b, right)] for a, b in ks], colWidths=[70 * mm, 40 * mm], hAlign="LEFT")
    kt.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                            ("BACKGROUND", (0, -1), (-1, -1), HELL), ("FONTNAME", (0, -1), (-1, -1), FB)]))
    el.append(kt)

    if r["warnungen"]:
        el.append(Paragraph("Warnungen", h2))
        for w in r["warnungen"]:
            el.append(Paragraph("• " + escape(w), n))

    el.append(PageBreak())
    el.append(Paragraph("Rechenweg", h1))
    for line in rechenweg(r):
        if not line.strip():
            el.append(Spacer(1, 4))
            continue
        ind = (len(line) - len(line.lstrip(" "))) * 3.0
        st = ParagraphStyle("m", parent=mono, leftIndent=ind + 10, firstLineIndent=-10)
        txt = escape(line.strip()).replace("  ", "&nbsp;&nbsp;")
        el.append(Paragraph(txt, st))

    def fuss(canvas, doc):
        canvas.saveState()
        canvas.setFont(F, 7.5)
        canvas.setFillColor(colors.grey)
        canvas.drawString(20 * mm, 10 * mm, f"HBK Kalkulation {pj['nr']} – Stichtag {to_de(pj['stichtag'])}")
        canvas.drawRightString(190 * mm, 10 * mm, f"Seite {doc.page}")
        canvas.restoreState()

    SimpleDocTemplate(pfad, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
                      bottomMargin=18 * mm, title=f"Kalkulation {pj['nr']}", author=firma or "HBK"
                      ).build(el, onFirstPage=fuss, onLaterPages=fuss)
    return pfad


def _tabelle(rows, widths, style, rechts=()):
    right = ParagraphStyle("rr", parent=style, alignment=2)
    data = []
    for ri, row in enumerate(rows):
        cells = []
        for ci, c in enumerate(row):
            txt = escape(str(c))
            if ri == 0:
                txt = f"<b>{txt}</b>"
            cells.append(Paragraph(txt, right if ci in rechts else style))
        data.append(cells)
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), HELL), ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t
