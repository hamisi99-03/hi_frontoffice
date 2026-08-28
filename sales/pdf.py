from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

DARK = colors.HexColor("#1e3f73")
ACCENT = colors.HexColor("#2c5aa0")
GREY = colors.HexColor("#555555")
LIGHT = colors.HexColor("#eef2f7")
RED = colors.HexColor("#a12727")


def _kes(value):
    return f"KES {Decimal(value or 0):,.2f}"


def _weight(value):
    if value is None:
        return "-"
    return f"{value:,.3f}"


def build_invoice_pdf(invoice, sales, total, total_paid, balance):
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Invoice {invoice.number} - {invoice.customer_name}",
        author=settings.COMPANY_NAME,
    )

    styles = getSampleStyleSheet()
    name_style = ParagraphStyle(
        "CompanyName", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=20, textColor=DARK, alignment=TA_CENTER, spaceAfter=2,
    )
    motto_style = ParagraphStyle(
        "Motto", parent=styles["Normal"], fontName="Helvetica-Oblique",
        fontSize=10, textColor=ACCENT, alignment=TA_CENTER, spaceAfter=6,
    )
    contact_style = ParagraphStyle(
        "Contact", parent=styles["Normal"], fontSize=8.5, textColor=GREY,
        alignment=TA_CENTER, leading=12,
    )
    invoice_title = ParagraphStyle(
        "InvoiceTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=15, textColor=colors.white, alignment=TA_CENTER,
    )
    meta_label = ParagraphStyle(
        "MetaLabel", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=8.5, textColor=DARK,
    )
    meta_value = ParagraphStyle(
        "MetaValue", parent=styles["Normal"], fontSize=8.5, textColor=GREY,
    )
    th_style = ParagraphStyle(
        "TH", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9,
        textColor=colors.white, alignment=TA_LEFT,
    )
    td_style = ParagraphStyle(
        "TD", parent=styles["Normal"], fontSize=9, textColor=colors.black,
    )
    td_right = ParagraphStyle(
        "TDRight", parent=td_style, alignment=TA_RIGHT,
    )

    story = []

    story.append(Paragraph(settings.COMPANY_NAME, name_style))
    story.append(Paragraph(f'"{settings.COMPANY_MOTTO}"', motto_style))
    story.append(Paragraph(
        f"{settings.COMPANY_ADDRESS}<br/>Tel: {settings.COMPANY_PHONE}",
        contact_style,
    ))
    story.append(Spacer(1, 6 * mm))

    # Invoice title band
    band = Table([[Paragraph("INVOICE", invoice_title)]], colWidths=[doc.width])
    band.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), DARK),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(band)
    story.append(Spacer(1, 5 * mm))

    meta = Table([
        [
            Paragraph("BILL TO", meta_label),
            Paragraph("INVOICE NO", meta_label),
            Paragraph("DATE", meta_label),
        ],
        [
            Paragraph(invoice.customer_name, meta_value),
            Paragraph(invoice.number, meta_value),
            Paragraph(invoice.date.strftime("%d %b %Y"), meta_value),
        ],
    ], colWidths=[doc.width * 0.45, doc.width * 0.3, doc.width * 0.25])
    meta.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(meta)
    story.append(Spacer(1, 6 * mm))

    header = [
        Paragraph("#", th_style),
        Paragraph("Date", th_style),
        Paragraph("Description", th_style),
        Paragraph("Qty (kg)", th_style),
        Paragraph("Unit Price", th_style),
        Paragraph("Amount", th_style),
    ]
    rows = [header]
    for i, s in enumerate(sales, 1):
        rows.append([
            Paragraph(str(i), td_style),
            Paragraph(s.date.strftime("%d/%m/%Y"), td_style),
            Paragraph(s.item.name, td_style),
            Paragraph(_weight(s.weight_kg), td_style),
            Paragraph(_kes(s.item.price_per_kg), td_right),
            Paragraph(_kes(s.gross), td_right),
        ])

    col_widths = [
        doc.width * 0.06,
        doc.width * 0.14,
        doc.width * 0.30,
        doc.width * 0.14,
        doc.width * 0.18,
        doc.width * 0.18,
    ]
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LIGHT),
        ("GRID", (0, 0), (-1, 0), 0.4, ACCENT),
    ]))
    story.append(table)
    story.append(Spacer(1, 4 * mm))

    totals = [
        ["", "", "", "", "Subtotal", _kes(total)],
        ["", "", "", "", "Amount Paid", _kes(total_paid)],
        ["", "", "", "", "Balance Due", _kes(balance)],
    ]
    total_table = Table(totals, colWidths=col_widths)
    total_table.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 2), (-1, 2), RED),
    ]))
    story.append(total_table)
    story.append(Spacer(1, 14 * mm))

    footer_style = ParagraphStyle(
        "Footer", parent=styles["Normal"], fontSize=9, textColor=GREY,
        alignment=TA_CENTER, leading=13,
    )
    story.append(Paragraph(
        "Goods once sold cannot be re-accepted.", footer_style,
    ))
    story.append(Paragraph(
        f"Thank you for shopping with {settings.COMPANY_NAME}.", footer_style,
    ))

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="invoice_{invoice.number}_{invoice.customer_name}.pdf"'
    )
    return response
