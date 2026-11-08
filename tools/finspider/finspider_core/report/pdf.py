"""PDF renderer (fpdf2). Uses a system Unicode font when available, else core Helvetica."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from fpdf import FPDF
from fpdf.fonts import FontFace

from .content import ReportContent, money_unit

log = logging.getLogger(__name__)

FONT_CANDIDATES = [
    ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/Library/Fonts/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
]

INK = (11, 11, 11)
INK_2 = (82, 81, 78)
MUTED = (137, 135, 129)
HAIRLINE = (225, 224, 217)
FLAG_FILL = {"good": (214, 240, 214), "ok": (253, 236, 196), "bad": (248, 214, 214),
             "unverified": (236, 236, 240)}
VERDICT_FILL = {"Strong Accumulate": (214, 240, 214), "Accumulate": (226, 240, 220),
                "Hold": (253, 236, 196), "Avoid": (248, 214, 214)}


class _PDF(FPDF):
    footer_text = ""
    family = "Helvetica"

    def footer(self):
        self.set_y(-12)
        self.set_font(self.family, size=7.5)
        self.set_text_color(*MUTED)
        self.cell(0, 5, f"{self.footer_text}  \u00b7  Not investment advice  \u00b7  page {self.page_no()}"
                  if self.family != "Helvetica" else
                  f"{self.footer_text} - Not investment advice - page {self.page_no()}", align="C")


def _setup_font(pdf: _PDF) -> bool:
    for regular, bold in FONT_CANDIDATES:
        if Path(regular).exists() and Path(bold).exists():
            try:
                pdf.add_font("Body", "", regular)
                pdf.add_font("Body", "B", bold)
                pdf.family = "Body"
                return True
            except Exception as e:
                log.debug("font %s failed: %s", regular, e)
    pdf.family = "Helvetica"
    return False


def _strip_md(s: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", s).replace("*", "")


def render(rc: ReportContent, out_path: Path, currency: str) -> Path:
    pdf = _PDF(format="A4")
    pdf.set_auto_page_break(True, margin=16)
    pdf.set_margins(15, 15, 15)
    unicode_ok = _setup_font(pdf)
    pdf.footer_text = rc.title
    F = pdf.family

    def T(s: str) -> str:
        """Make text safe for the core font if no Unicode font was found."""
        s = str(s)
        if unicode_ok:
            # emoji are not in these fonts
            return re.sub("[\U0001F300-\U0001FAFF\u2600-\u27BF\ufe0f]", "", s)
        rep = {"\u20b9": "Rs.", "\u2014": "-", "\u2013": "-", "\u00b7": "-", "\u2019": "'", "\u20ac": "EUR",
               "\u00a5": "JPY", "\u26d4": "", "\u26a0": ""}
        for k, v in rep.items():
            s = s.replace(k, v)
        return s.encode("latin-1", "replace").decode("latin-1")

    def h1(text):
        pdf.set_font(F, "B", 17)
        pdf.set_text_color(*INK)
        pdf.multi_cell(0, 8, T(text), new_x="LMARGIN", new_y="NEXT")

    def h2(text):
        if pdf.get_y() > 235:   # keep a heading together with some of its content
            pdf.add_page()
        pdf.ln(3)
        pdf.set_font(F, "B", 12.5)
        pdf.set_text_color(*INK)
        pdf.cell(0, 8, T(text), new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(*HAIRLINE)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(2)

    def para(text, size=9.5, color=INK_2, bold=False):
        pdf.set_font(F, "B" if bold else "", size)
        pdf.set_text_color(*color)
        pdf.multi_cell(0, size * 0.5, T(_strip_md(text)), new_x="LMARGIN", new_y="NEXT")

    def bullets(items, size=9.5):
        pdf.set_font(F, "", size)
        pdf.set_text_color(*INK_2)
        for it in items:
            pdf.set_x(pdf.l_margin + 2)
            pdf.multi_cell(0, size * 0.5, T("\u2022 " if unicode_ok else "- ") + T(_strip_md(it)),
                           new_x="LMARGIN", new_y="NEXT")
            pdf.ln(0.8)

    # ---- page 1: title + verdict ----
    pdf.add_page()
    h1(rc.title)
    para(f"{rc.subtitle}  \u00b7  generated {rc.generated}", size=9, color=MUTED)
    para("Not investment advice. Automated analysis of public data - see the disclaimer at the end.",
         size=8.5, color=MUTED)
    pdf.ln(4)

    fill = VERDICT_FILL.get(rc.verdict, (240, 239, 236))
    pdf.set_fill_color(*fill)
    pdf.set_font(F, "B", 15)
    pdf.set_text_color(*INK)
    pdf.cell(0, 12, T(f"  {rc.verdict}   \u2014   overall score {rc.overall}"), fill=True,
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_fill_color(255, 255, 255)   # don't let the banner colour leak into tables
    if rc.verdict_note:
        para(f"Note: {rc.verdict_note}.", size=8.5, color=MUTED)
    pdf.ln(2)
    para("Top reasons", size=10, color=INK, bold=True)
    bullets(rc.strengths or ["No metric scored in the 'good' band."])
    para("Red flags", size=10, color=INK, bold=True)
    bullets([f"{'CRITICAL' if s == 'critical' else 'Warning'}: {t}" for s, t in rc.red_flags] or ["None triggered."])
    if rc.weaknesses:
        para("Weak spots", size=10, color=INK, bold=True)
        bullets(rc.weaknesses)

    h2("Scorecard")
    pdf.set_font(F, "", 9)
    with pdf.table(col_widths=(70, 30, 30, 40), text_align=("LEFT", "RIGHT", "RIGHT", "LEFT"),
                   headings_style=FontFace(emphasis="BOLD", color=INK, fill_color=(240, 239, 236)),
                   line_height=6, borders_layout="HORIZONTAL_LINES") as t:
        r = t.row()
        for hdr in ("Category", "Weight", "Score /10", "Rating"):
            r.cell(hdr)
        for row in rc.scorecard:
            r = t.row()
            for v in row:
                r.cell(T(v))

    h2("Health summary")
    bullets(rc.health)

    # ---- overview ----
    h2("Business overview")
    para(rc.overview_text, size=9)
    pdf.ln(2)
    pdf.set_font(F, "", 8.5)
    with pdf.table(col_widths=(45, 135), text_align=("LEFT", "LEFT"), first_row_as_headings=False,
                   line_height=5.5, borders_layout="HORIZONTAL_LINES") as t:
        for k, v in rc.facts:
            r = t.row()
            r.cell(T(k), style=FontFace(emphasis="BOLD", color=INK))
            r.cell(T(v))

    # ---- ratios ----
    h2("Key ratios")
    pdf.set_font(F, "", 8)
    with pdf.table(col_widths=(52, 22, 46, 20, 16, 14), text_align=("LEFT", "RIGHT", "LEFT", "LEFT", "LEFT", "RIGHT"),
                   headings_style=FontFace(emphasis="BOLD", color=INK, fill_color=(240, 239, 236)),
                   line_height=5, borders_layout="HORIZONTAL_LINES") as t:
        r = t.row()
        for hdr in ("Metric", "Value", "Detail", "3y trend", "Flag", "Score"):
            r.cell(hdr)
        last_cat = None
        for row in rc.ratio_rows:
            if row["category"] and row["category"] != last_cat:
                r = t.row()
                r.cell(T(row["category"]), colspan=6, style=FontFace(emphasis="BOLD", color=INK_2,
                                                                     fill_color=(249, 249, 247)))
                last_cat = row["category"]
            r = t.row()
            r.cell(T(row["metric"]))
            r.cell(T(row["value"]))
            r.cell(T(row["note"]))
            r.cell(T(row["trend"]))
            fl = row["flag"]
            r.cell(fl if fl != "n/a" else "-", style=FontFace(fill_color=FLAG_FILL.get(fl)) if fl in FLAG_FILL else None)
            r.cell(T(row["score"]))

    # ---- charts ----
    h2("Trends")
    for title, p in rc.charts:
        if not Path(p).exists():
            continue
        w = pdf.w - pdf.l_margin - pdf.r_margin
        h = w * 0.46
        if pdf.get_y() + h > pdf.h - 18:
            pdf.add_page()
        pdf.image(str(p), w=w)
        pdf.ln(3)

    # ---- history ----
    h2(f"Financial history ({money_unit(currency)} unless stated)")
    n = len(rc.history_header)
    first = 38
    rest = (pdf.w - pdf.l_margin - pdf.r_margin - first) / max(1, n - 1)
    pdf.set_font(F, "", 7.2)
    with pdf.table(col_widths=(first, *([rest] * (n - 1))), text_align=("LEFT", *(["RIGHT"] * (n - 1))),
                   headings_style=FontFace(emphasis="BOLD", color=INK, fill_color=(240, 239, 236)),
                   line_height=5, borders_layout="HORIZONTAL_LINES") as t:
        r = t.row()
        for hdr in rc.history_header:
            r.cell(T(hdr))
        for row in rc.history_rows:
            r = t.row()
            for v in row:
                r.cell(T(v))

    h2("Data & method notes")
    para("Sources by field", size=9, color=INK, bold=True)
    bullets([f"{s}: {f}" for s, f in rc.sources], size=8.5)
    if rc.warnings:
        para("Data warnings", size=9, color=INK, bold=True)
        bullets(rc.warnings, size=8.5)
    para("Method", size=9, color=INK, bold=True)
    bullets(rc.method_notes, size=8.5)

    h2("Disclaimer")
    para(rc.disclaimer, size=8.5)
    pdf.output(str(out_path))
    return out_path
