import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from content import *

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, PageBreak, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

NAVY = colors.HexColor("#1F3864")
BLUE = colors.HexColor("#0070C0")
HEAD = colors.HexColor("#DCE6F1")
GREY = colors.HexColor("#5A5A5A")
RULE = colors.HexColor("#BFBFBF")
ZEBRA = colors.HexColor("#F5F7FA")

ss = getSampleStyleSheet()
S = {
    "title": ParagraphStyle("t", parent=ss["Title"], fontName="Helvetica-Bold",
                            fontSize=21, leading=25, textColor=NAVY, alignment=TA_LEFT,
                            spaceAfter=2),
    "sub": ParagraphStyle("s", parent=ss["Normal"], fontSize=11.5, leading=15,
                          textColor=GREY, spaceAfter=14),
    "h1": ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold",
                         fontSize=12.5, leading=15, textColor=BLUE,
                         spaceBefore=15, spaceAfter=6),
    "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold",
                         fontSize=10, leading=13, textColor=NAVY,
                         spaceBefore=9, spaceAfter=3),
    "body": ParagraphStyle("b", parent=ss["Normal"], fontSize=9.2, leading=13.2,
                           spaceAfter=6),
    "note": ParagraphStyle("n", parent=ss["Normal"], fontSize=8.4, leading=12,
                           textColor=GREY, spaceAfter=6),
    "cell": ParagraphStyle("c", parent=ss["Normal"], fontSize=7.9, leading=10.2),
    "cellb": ParagraphStyle("cb", parent=ss["Normal"], fontSize=7.9, leading=10.2,
                            fontName="Helvetica-Bold"),
    "th": ParagraphStyle("th", parent=ss["Normal"], fontSize=7.9, leading=10.2,
                         fontName="Helvetica-Bold", textColor=NAVY),
}


def table(rows, widths, bold_first_col=True):
    body = []
    for i, row in enumerate(rows):
        style = "th" if i == 0 else ("cellb" if bold_first_col else "cell")
        body.append([Paragraph(str(c), S[style if i == 0 or j == 0 else "cell"])
                     for j, c in enumerate(row)])
    t = Table(body, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEAD),
        ("LINEBELOW", (0, 0), (-1, 0), 1.1, NAVY),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ZEBRA]),
    ]))
    return t


def kv(pairs, w1=42*mm):
    rows = [[Paragraph(f"<b>{k}</b>", S["cell"]), Paragraph(v, S["cell"])]
            for k, v in pairs]
    t = Table(rows, colWidths=[w1, 168*mm - w1], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4.5),
        ("BACKGROUND", (0, 0), (0, -1), ZEBRA),
    ]))
    return t


def furniture(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.2)
    canvas.setFillColor(GREY)
    # Short forms only. The full reference and classification are on page 1;
    # repeating them in full here collided in the middle of every footer.
    canvas.drawString(21*mm, 12*mm, "DTG-BR-QMSI-v0.1")
    canvas.drawCentredString(A4[0] / 2, 12*mm, "Internal - Datategy")
    canvas.drawRightString(A4[0] - 21*mm, 12*mm, f"Page {doc.page}")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.4)
    canvas.line(21*mm, 15.5*mm, A4[0] - 21*mm, 15.5*mm)
    canvas.restoreState()


def build(path):
    doc = BaseDocTemplate(path, pagesize=A4,
                          leftMargin=21*mm, rightMargin=21*mm,
                          topMargin=18*mm, bottomMargin=20*mm,
                          title=f'{META["title"]} - Business Requirements',
                          author="Datategy", subject="Business Requirements")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=furniture)])

    f = []
    P = lambda t, s="body": Paragraph(t, S[s])

    f.append(P("DELIVERY METHODOLOGY", "note"))
    f.append(P(META["title"], "title"))
    f.append(P(META["subtitle"], "sub"))
    f.append(kv([
        ("Reference", META["reference"]), ("Version", META["version"]),
        ("Owner", META["owner"]), ("Prepared for", META["prepared_for"]),
        ("Requesting entity", META["requesting"]), ("Date", META["date"]),
        ("Methodology", META["methodology"]),
        ("Classification", META["classification"]),
    ]))
    f.append(Spacer(1, 10))
    f.append(P(NAMING_NOTE, "note"))

    for h, t in INTRO:
        f.append(P(h, "h2")); f.append(P(t))

    f.append(P("1. Context and objective", "h1")); f.append(kv(CONTEXT))
    f.append(P("2. Primary persona", "h1")); f.append(kv(PERSONA))

    f.append(P("3. Process: As-Is to To-Be", "h1"))
    f.append(P("As-Is", "h2"))
    f.append(table(AS_IS, [46*mm, 22*mm, 24*mm, 22*mm, 54*mm]))
    f.append(P("Timings are indicative and marked [to confirm] pending a client walkthrough.", "note"))
    f.append(P("To-Be (system + human)", "h2"))
    f.append(table(TO_BE, [56*mm, 24*mm, 34*mm, 54*mm]))

    f.append(P("4. Business outcomes", "h1"))
    f.append(table(OUTCOMES, [12*mm, 38*mm, 68*mm, 50*mm]))

    f.append(P("5. Functional business requirements", "h1"))
    f.append(P("Priority: M must, S should, C could, W won't (this phase).", "note"))
    f.append(table(FUNCTIONAL, [12*mm, 118*mm, 10*mm, 28*mm]))

    f.append(P("6. Non-functional requirements", "h1"))
    f.append(table(NFR, [40*mm, 18*mm, 110*mm]))

    f.append(P("7. Data and knowledge sources", "h1"))
    f.append(P("Read this section first if you are estimating. The licensing position "
               "decides the shape of the build, and one half of it may not be "
               "purchasable at all.", "note"))
    f.append(table(SOURCES, [10*mm, 40*mm, 26*mm, 34*mm, 58*mm]))

    f.append(P("8. Decisions the system makes", "h1"))
    f.append(table(DECISIONS, [10*mm, 32*mm, 30*mm, 28*mm, 34*mm, 34*mm]))

    f.append(P("9. Business rules and guardrails", "h1"))
    f.append(P("Business rules (IF / THEN)", "h2"))
    f.append(table(RULES, [11*mm, 89*mm, 68*mm]))
    f.append(P("Never do this", "h2"))
    f.append(table(NEVER, [11*mm, 157*mm]))

    f.append(P("10. Success metrics (KPIs)", "h1"))
    f.append(table(KPIS, [36*mm, 60*mm, 36*mm, 36*mm]))

    f.append(P("11. Constraints and assumptions", "h1"))
    f.append(table(CONSTRAINTS, [13*mm, 155*mm]))

    f.append(P("12. Out of scope", "h1"))
    f.append(table(OUT_OF_SCOPE, [13*mm, 155*mm]))

    f.append(P("13. Traceability", "h1"))
    f.append(P("Each business outcome traces to functional requirements, to the "
               "decisions and rules that implement them, and to the acceptance "
               "evidence. BO-1 to FR-1..FR-5, FR-11, FR-24. BO-2 to FR-12, FR-14. "
               "BO-3 to FR-18, FR-19 and D1..D4. BO-4 to FR-20..FR-22 and D5..D7. "
               "BO-5 to FR-13, FR-15, R1, R2 and the reconciliation tests. BO-6 to "
               "FR-6, FR-7, N5."))
    f.append(P("Acceptance evidence for the register capabilities already exists as an "
               "automated suite of 154 checks that runs without network access, "
               "asserting that every cut and every segment reconciles to the snapshot "
               "it came from. Extend it; do not replace it."))

    f.append(P("14. Requirements acceptance", "h1"))
    f.append(table([["Role", "Name", "Date", "Signature"],
                    ["Business owner", "", "", ""],
                    ["Process SME", "", "", ""],
                    ["Client IT / Security", "", "", ""],
                    ["Datategy - Delivery", "", "", ""]],
                   [42*mm, 50*mm, 30*mm, 46*mm]))

    # On its own page: the table is twelve rows and spilled a single orphan row
    # onto a page of its own otherwise.
    f.append(PageBreak())
    f.append(P("Appendix A. Prototype inventory", "h1"))
    f.append(P("What exists today, and how much of it survives into production.", "note"))
    f.append(table(APPENDIX, [46*mm, 26*mm, 18*mm, 78*mm]))

    doc.build(f)


OUT = Path(__file__).resolve().parent.parent / "BRD-Qatar-Market-Intelligence-v0.1.pdf"
build(str(OUT))
print("built", OUT)
