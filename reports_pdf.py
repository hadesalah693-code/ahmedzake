import io
from datetime import date
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

BASE_DIR = str(Path(__file__).resolve().parent)
FONT_DIR = Path(BASE_DIR) / "static" / "fonts" / "noto"
FONT_REGULAR = str(FONT_DIR / "NotoNaskhArabic-Regular.ttf")
FONT_BOLD = str(FONT_DIR / "NotoNaskhArabic-Bold.ttf")

_reshaped = arabic_reshaper.ArabicReshaper(configuration={
    "delete_harakat": False,
    "support_ligatures": True,
})


def ar(text):
    return get_display(_reshaped.reshape(str(text)))


def _register_fonts():
    try:
        pdfmetrics.getFont("NotoNaskh")
    except Exception:
        pdfmetrics.registerFont(TTFont("NotoNaskh", FONT_REGULAR))
        pdfmetrics.registerFont(TTFont("NotoNaskh-Bold", FONT_BOLD))


PRIMARY = colors.HexColor("#1a3d66")
ACCENT = colors.HexColor("#c9a227")
DARK_TEXT = colors.HexColor("#1f2937")
MUTED = colors.HexColor("#6b7280")
SOFT_BG = colors.HexColor("#eef2f7")
ROW_ALT = colors.HexColor("#f8fafc")
GREEN_BG = colors.HexColor("#ecfdf5")
GREEN_BORDER = colors.HexColor("#a7f3d0")
RED_BG = colors.HexColor("#fef2f2")
RED_BORDER = colors.HexColor("#fecaca")

MONTHS_AR = [
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
]


def fmt_amount(value, currency):
    return f"{fmt_num(value)} {currency}"


def fmt_num(value):
    try:
        n = float(value or 0)
    except (TypeError, ValueError):
        n = 0.0
    if n == int(n):
        return f"{int(n):,}"
    return f"{n:,.2f}"


def fmt_month(month):
    try:
        y, m = month.split("-")
        return f"{MONTHS_AR[int(m) - 1]} {y}"
    except Exception:
        return month


def fmt_day(day):
    try:
        d = date.fromisoformat(day)
        return f"{d.day}-{d.month}-{d.year}"
    except Exception:
        return day


PAYMENT_LABELS = {"cash": "كاش", "card": "ماكينة", "transfer": "تحويل بنكي"}


class _Styles:
    def __init__(self):
        self.title = ParagraphStyle(
            "title", fontName="NotoNaskh-Bold", fontSize=17, leading=22,
            alignment=TA_CENTER, textColor=PRIMARY, spaceAfter=2,
        )
        self.subtitle = ParagraphStyle(
            "subtitle", fontName="NotoNaskh", fontSize=9.5, leading=13,
            alignment=TA_CENTER, textColor=MUTED, spaceAfter=2,
        )
        self.report_title = ParagraphStyle(
            "report_title", fontName="NotoNaskh-Bold", fontSize=13, leading=18,
            alignment=TA_CENTER, textColor=DARK_TEXT, spaceBefore=6, spaceAfter=2,
        )
        self.meta = ParagraphStyle(
            "meta", fontName="NotoNaskh", fontSize=9, leading=12,
            alignment=TA_CENTER, textColor=MUTED, spaceAfter=2,
        )
        self.banner = ParagraphStyle(
            "banner", fontName="NotoNaskh-Bold", fontSize=12, leading=16,
            alignment=TA_CENTER, textColor=DARK_TEXT,
        )
        self.section = ParagraphStyle(
            "section", fontName="NotoNaskh-Bold", fontSize=11, leading=15,
            textColor=PRIMARY, spaceBefore=10, spaceAfter=6,
        )
        self.cell = ParagraphStyle(
            "cell", fontName="NotoNaskh", fontSize=8.8, leading=12,
            alignment=TA_RIGHT, textColor=DARK_TEXT,
        )
        self.cell_bold = ParagraphStyle(
            "cell_bold", fontName="NotoNaskh-Bold", fontSize=8.8, leading=12,
            alignment=TA_RIGHT, textColor=DARK_TEXT,
        )
        self.header_cell = ParagraphStyle(
            "header_cell", fontName="NotoNaskh-Bold", fontSize=9, leading=12,
            alignment=TA_CENTER, textColor=colors.white,
        )


def _header_story(story, office, title, period, exported_on):
    _register_fonts()
    s = _Styles()
    story.append(Paragraph(ar(office or "الوسام للخدمات الجامعية"), s.title))
    story.append(Paragraph(ar("نظام الإيرادات والمصاريف والأرشفة"), s.subtitle))
    story.append(Paragraph(ar(f"{title} — {period}"), s.report_title))
    story.append(Paragraph(ar(f"تاريخ التصدير: {exported_on}"), s.meta))
    story.append(Spacer(1, 4))


def _banner(story, profit, is_profit):
    s = _Styles()
    label = "✅ ربح" if is_profit else "❌ خسارة"
    text = ar(f"{label}: {fmt_num(profit)}")
    t = Table([[Paragraph(text, s.banner)]], colWidths=[170 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GREEN_BG if is_profit else RED_BG),
        ("BOX", (0, 0), (-1, -1), 1, GREEN_BORDER if is_profit else RED_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 6))


def _stat_row(story, cells):
    s = _Styles()
    data = []
    for label, value in cells:
        inner = [[Paragraph(ar(label), s.cell),
                  Paragraph(ar(value), s.cell_bold)]]
        t = Table(inner, colWidths=[52 * mm], hAlign="CENTER")
        t.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ("BACKGROUND", (0, 0), (-1, -1), SOFT_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dbe3ee")),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        data.append(t)
    row = Table([data], colWidths=[56 * mm] * 3, hAlign="CENTER")
    row.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(row)
    story.append(Spacer(1, 4))


def _data_table(story, headers, rows):
    s = _Styles()
    table_rows = [[Paragraph(ar(h), s.header_cell) for h in headers]]
    for r in rows:
        table_rows.append([Paragraph(ar(str(c)), s.cell) for c in r])
    if not rows:
        table_rows.append([Paragraph(ar("لا توجد بيانات"), s.cell)] * len(headers))
    widths = [170 * mm / len(headers)] * len(headers)
    t = Table(table_rows, colWidths=widths, repeatRows=1, hAlign="CENTER")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 1), (-1, -1), "RIGHT"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cfd8e4")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for i in range(2, len(table_rows), 2):
        style.append(("BACKGROUND", (0, i), (-1, i), ROW_ALT))
    t.setStyle(TableStyle(style))
    story.append(t)
    story.append(Spacer(1, 4))


def _service_rows(items, currency):
    rows = []
    for it in items:
        rows.append([it.get("service_type") or "-", str(it.get("count", 0)),
                     fmt_amount(it.get("total", 0), currency)])
    return rows


def _payment_rows(items, currency):
    rows = []
    for it in items:
        label = PAYMENT_LABELS.get(it.get("payment_method"), it.get("payment_method") or "-")
        rows.append([label, str(it.get("count", 0)), fmt_amount(it.get("total", 0), currency)])
    return rows


def build_daily_pdf(data, office, currency):
    _register_fonts()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, rightMargin=20 * mm, leftMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title="تقرير يومي", author=office or "الوسام",
    )
    story = []
    _header_story(story, office, "تقرير يومي", fmt_day(data.get("date", "")),
                  date.today().isoformat())
    _banner(story, data.get("profit", 0), data.get("is_profit", True))

    rev = data.get("revenue", {})
    exp = data.get("expenses", {})
    _stat_row(story, [
        (f"إيرادات اليوم ({rev.get('count', 0)} طلب)", fmt_amount(rev.get("total", 0), currency)),
        (f"مصاريف اليوم ({exp.get('count', 0)} مصروف)", fmt_amount(exp.get("total", 0), currency)),
        ("صافي اليوم", fmt_amount(data.get("net", 0), currency)),
    ])

    s = _Styles()
    story.append(Paragraph(ar("الإيرادات حسب الخدمة"), s.section))
    _data_table(story, ["الخدمة", "عدد", "المبلغ"], _service_rows(data.get("services", []), currency))

    story.append(Paragraph(ar("طلبات اليوم"), s.section))
    order_rows = []
    for o in data.get("orders", []):
        order_rows.append([
            o.get("invoice_number") or "-",
            o.get("customer_name") or "-",
            o.get("service_type") or "-",
            fmt_amount(o.get("amount", 0), currency),
            PAYMENT_LABELS.get(o.get("payment_method"), o.get("payment_method") or "-"),
        ])
    _data_table(story, ["الفاتورة", "الزبون", "الخدمة", "المبلغ", "الدفع"], order_rows)

    story.append(Paragraph(ar("مصاريف اليوم"), s.section))
    expense_rows = []
    for e in data.get("expense_list", []):
        expense_rows.append([e.get("title") or "-", e.get("category") or "-", fmt_amount(e.get("amount", 0), currency)])
    _data_table(story, ["العنوان", "التصنيف", "المبلغ"], expense_rows)

    doc.build(story)
    buf.seek(0)
    return buf


def build_monthly_pdf(data, office, currency):
    _register_fonts()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, rightMargin=20 * mm, leftMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title="تقرير شهري", author=office or "الوسام",
    )
    story = []
    _header_story(story, office, "تقرير شهري", fmt_month(data.get("period", "")),
                  date.today().isoformat())
    _banner(story, data.get("profit", 0), data.get("is_profit", True))

    rev = data.get("revenue", {})
    exp = data.get("expenses", {})
    _stat_row(story, [
        (f"إجمالي الإيرادات ({rev.get('count', 0)} طلب)", fmt_amount(rev.get("total", 0), currency)),
        (f"إجمالي المصاريف ({exp.get('count', 0)} مصروف)", fmt_amount(exp.get("total", 0), currency)),
        ("صافي الربح", fmt_amount(data.get("profit", 0), currency)),
    ])

    s = _Styles()
    story.append(Paragraph(ar("الإيرادات حسب نوع الخدمة"), s.section))
    _data_table(story, ["الخدمة", "عدد", "المبلغ"], _service_rows(data.get("services", []), currency))

    story.append(Paragraph(ar("المصاريف حسب التصنيف"), s.section))
    cat_rows = []
    for c in exp.get("by_category", []):
        cat_rows.append([c.get("category") or "-", str(c.get("count", 0)),
                         fmt_amount(c.get("total", 0), currency)])
    _data_table(story, ["التصنيف", "عدد", "المبلغ"], cat_rows)

    story.append(Paragraph(ar("الإيرادات اليومية خلال الشهر"), s.section))
    daily_rows = []
    for d in data.get("daily_revenue", []):
        daily_rows.append([fmt_day(d.get("day", "")), fmt_amount(d.get("revenue", 0), currency)])
    _data_table(story, ["اليوم", "الإيراد"], daily_rows)

    story.append(Paragraph(ar("الإيرادات حسب طريقة الدفع"), s.section))
    _data_table(story, ["طريقة الدفع", "عدد", "المبلغ"],
                _payment_rows(rev.get("by_payment", []), currency))

    doc.build(story)
    buf.seek(0)
    return buf