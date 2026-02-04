
from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional

from reportlab.platypus import (
    KeepTogether,
    SimpleDocTemplate,
    Paragraph,
    Table,
    TableStyle,
    Spacer,
    Image,
)
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pathlib import Path
import os, re
from xml.sax.saxutils import escape as _xml_escape

_FONT = 'Helvetica'
_BOLD_FONT = 'Helvetica-Bold'

def _register_fonts() -> str:
    """Best-effort font registration (regular + bold) for Turkish characters.

    Priority:
    1) Bundled fonts under src/assets/fonts (so packaged app is deterministic)
    2) System fonts (Windows / Linux)
    3) ReportLab core fonts (Helvetica)
    """
    global _FONT, _BOLD_FONT

    base_dir = Path(__file__).resolve().parents[2]
    bundled_dir = base_dir / "assets" / "fonts"

    candidates = [
        (str(bundled_dir / "DejaVuSans.ttf"), str(bundled_dir / "DejaVuSans-Bold.ttf")),
        (r"C:\\Windows\\Fonts\\DejaVuSans.ttf", r"C:\\Windows\\Fonts\\DejaVuSans-Bold.ttf"),
        (r"C:\\Windows\\Fonts\\arial.ttf", r"C:\\Windows\\Fonts\\arialbd.ttf"),
        (r"C:\\Windows\\Fonts\\calibri.ttf", r"C:\\Windows\\Fonts\\calibrib.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for regular, bold in candidates:
        try:
            if os.path.exists(regular):
                pdfmetrics.registerFont(TTFont("NXBody", regular))
                _FONT = "NXBody"
                if bold and os.path.exists(bold):
                    try:
                        pdfmetrics.registerFont(TTFont("NXBodyBold", bold))
                        _BOLD_FONT = "NXBodyBold"
                    except Exception:
                        _BOLD_FONT = "Helvetica-Bold"
                else:
                    _BOLD_FONT = "Helvetica-Bold"
                return "NXBody"
        except Exception:
            pass

    _FONT = "Helvetica"
    _BOLD_FONT = "Helvetica-Bold"
    return "Helvetica"


def _fmt_tr_date(value: Any) -> str:
    """Format dates as GG.AA.YYYY (Turkish common form).

    Accepts 'YYYY-MM-DD' strings, datetime.date/datetime, or returns
    the original string if parsing fails.
    """
    if value is None:
        return ""
    # datetime/date
    try:
        import datetime as _dt
        if isinstance(value, (_dt.date, _dt.datetime)):
            d = value.date() if isinstance(value, _dt.datetime) else value
            return f"{d.day:02d}.{d.month:02d}.{d.year:04d}"
    except Exception:
        pass

    s = str(value).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        y, mo, da = m.group(1), m.group(2), m.group(3)
        return f"{da}.{mo}.{y}"
    return s


def _resolve_logo_path(payload: Dict[str, Any]) -> str:
    """Return an absolute path for the logo to be used in the PDF header.

    - Uses payload['logo_path'] if provided and exists.
    - Otherwise tries bundled default NutriNexus logo.
    """
    # 1) explicit
    p = (payload or {}).get("logo_path")
    if p and os.path.exists(p):
        return p

    # 2) bundled default
    base_dir = Path(__file__).resolve().parents[2]
    for rel in (
        base_dir / "assets" / "nutrinexus_logo.png",
        base_dir / "assets" / "images" / "nutrinexus_logo.png",
    ):
        if rel.exists():
            return str(rel)
    return ""


def _parse_sections(plan_text: str) -> List[Tuple[str, List[Tuple[str, str]]]]:
    text = (plan_text or "").strip()
    if not text:
        return []

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    sections: List[Tuple[str, List[Tuple[str, str]]]] = []
    cur_title = "Diyet"
    cur_items: List[Tuple[str, str]] = []

    def flush():
        nonlocal cur_items, cur_title
        if cur_items:
            sections.append((cur_title, cur_items))
            cur_items = []

    for ln in lines:
        if ln.endswith(":") and len(ln) < 40:
            flush()
            cur_title = ln[:-1].strip() or "Diyet"
            continue
        # bullets
        ln2 = re.sub(r"^\d+[\).]\s+", "", ln)
        ln2 = ln2.lstrip("•-*").strip()
        if not ln2:
            continue
        # split amount
        food, amt = ln2, ""
        for sep in (" - ", " – ", " : ", ": "):
            if sep in ln2:
                a,b = ln2.split(sep,1)
                food, amt = a.strip(), b.strip()
                break
        cur_items.append((food, amt))
    flush()
    return sections




def _normalize_sections_for_cards(sections: List[Tuple[str, List[Tuple[str, str]]]]) -> List[Tuple[str, List[Tuple[str, str]]]]:
    """Normalize legacy section/item formats into per-meal sections.

    Some older pipelines flatten meals into a single section and use markers like
    '[Kahvaltı]' inside the food column. This function splits those into proper
    sections so we can render meal cards consistently.
    """
    if not sections:
        return sections

    # If already multiple named sections, assume it's fine.
    if len(sections) > 1:
        return sections

    title0, items0 = sections[0]
    if not items0:
        return sections

    # Detect bracket markers like [Kahvaltı]
    marker_re = re.compile(r"^\[(.+?)\]$")
    has_marker = any(marker_re.match((food or "").strip()) for food, _ in items0)
    if not has_marker:
        return sections

    out: List[Tuple[str, List[Tuple[str, str]]]] = []
    cur_title = None
    cur_items: List[Tuple[str, str]] = []

    def flush():
        nonlocal cur_title, cur_items
        if cur_title is None:
            return
        out.append((cur_title, cur_items))
        cur_items = []

    for food, amt in items0:
        f = (food or "").strip()
        m = marker_re.match(f)
        if m:
            # new meal section
            if cur_title is not None:
                flush()
            cur_title = m.group(1).strip() or "Öğün"
            continue
        if cur_title is None:
            # marker-less items before first marker go under original title
            cur_title = (title0 or "Diyet").strip() or "Diyet"
        cur_items.append((food, amt))

    if cur_title is not None:
        flush()

    return out or sections



def _safe_para(text: str) -> str:
    """Escape user/content text for ReportLab Paragraph.

    ReportLab Paragraph treats &, <, > as markup. If a food name contains these
    characters (e.g. 'Omega-3 & 6' or 'Vitamin C < 100mg'), unescaped content
    can appear 'cut' or partially missing. We escape them and preserve newlines.
    """
    s = (text or "").strip()
    if not s:
        return "-"
    # Escape XML markup chars and keep explicit line breaks.
    return _xml_escape(s).replace("\n", "<br/>")

def _meal_card(*, font: str, sec_title: str, items: List[Tuple[str, str]], available_width: float) -> Table:
    """Create a 'card' block for a meal section matching the in-app preview look."""
    green = colors.HexColor("#2f7d32")  # preview accent
    border = colors.HexColor("#d7dde3")
    grid = colors.HexColor("#eef2f5")
    header_bg = colors.HexColor("#F1F4F7")
    th_bg = colors.HexColor("#fafbfc")
    body_text = colors.HexColor("#102A33")
    muted = colors.HexColor("#6b7280")

    stripe_w = 4 * mm
    inner_w = max(1, available_width - stripe_w)

    styles = getSampleStyleSheet()
    # Öğün başlığı: preview'daki gibi ortalı + kalın
    h = ParagraphStyle(
        "nx_meal_h",
        parent=styles["Normal"],
        fontName=_BOLD_FONT,
        fontSize=11.5,
        leading=14,
        textColor=colors.black,
        alignment=TA_CENTER,
        spaceAfter=0,
    )
    th = ParagraphStyle(
        "nx_th",
        parent=styles["Normal"],
        fontName=_BOLD_FONT,
        fontSize=9.4,
        leading=12,
        textColor=colors.HexColor("#445"),
    )
    td_food = ParagraphStyle(
        "nx_food",
        parent=styles["Normal"],
        fontName=_BOLD_FONT,
        fontSize=9.6,
        leading=12.5,
        textColor=body_text,
        wordWrap="CJK",
        splitLongWords=True,  # robust wrapping
    )
    td_amt = ParagraphStyle(
        "nx_amt",
        parent=styles["Normal"],
        fontName=_BOLD_FONT,
        fontSize=9.6,
        leading=12.5,
        textColor=colors.HexColor("#111"),
    )
    empty_style = ParagraphStyle(
        "nx_empty",
        parent=styles["Normal"],
        fontName=font,
        fontSize=9.6,
        leading=12.5,
        textColor=muted,
        wordWrap="CJK",
        splitLongWords=True,
    )

    # Build inner table: title band + table header + rows (or empty message)
    inner_rows = []

    # Title band
    inner_rows.append([Paragraph(f"<b>{sec_title}</b>", h), ""])
    # Table header
    inner_rows.append([Paragraph("<b>Besin</b>", th), Paragraph("<b>Miktar</b>", th)])

    if items:
        for food, amt in items:
            food_p = Paragraph(_safe_para(food), td_food)
            amt_p = Paragraph(_safe_para(amt), td_amt)
            inner_rows.append([food_p, amt_p])
    else:
        # Empty meal message spanning both cols, no table rows
        inner_rows.append([Paragraph("Bu öğün için içerik eklenmemiştir.", empty_style), ""])

    # Column widths: fixed amount column like preview (110px-ish)
    # Keep "Miktar" compact so long food names don't look clipped.
    amt_w = 28 * mm
    food_w = max(1, inner_w - amt_w)

    inner = Table(inner_rows, colWidths=[food_w, amt_w])

    # Style inner
    ts = [
        ("FONTNAME", (0,0), (-1,-1), font),
        # Force wrapping in table cells so long food names never get visually cut.
        ("WORDWRAP", (0,0), (-1,-1), "CJK"),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("RIGHTPADDING", (1, 0), (1, -1), 14),
        ("LEFTPADDING", (1, 0), (1, -1), 6),
        ("LEFTPADDING", (0,0), (-1,-1), 7),
        ("RIGHTPADDING", (0,0), (-1,-1), 7),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),

        # Title band row (0)
        ("SPAN", (0,0), (-1,0)),
        ("ALIGN", (0,0), (-1,0), "CENTER"),
        ("BACKGROUND", (0,0), (-1,0), header_bg),
        ("LINEBELOW", (0,0), (-1,0), 0.75, border),

        # Table header row (1)
        ("BACKGROUND", (0,1), (-1,1), th_bg),
        ("LINEBELOW", (0,1), (-1,1), 0.5, grid),
        ("BOTTOMPADDING", (0,1), (-1,1), 6),
        ("TOPPADDING", (0,1), (-1,1), 6),
    ]

    if items:
        # Data rows start at row 2
        ts += [
            ("LINEBELOW", (0,2), (-1,-1), 0.5, grid),
            ("ALIGN", (1,2), (1,-1), "RIGHT"),
        ]
    else:
        # Empty message row at row 2
        ts += [
            ("SPAN", (0,2), (-1,2)),
            ("BACKGROUND", (0,2), (-1,2), colors.white),
        ]

    inner.setStyle(TableStyle(ts))

    outer = Table([[ "", inner ]], colWidths=[stripe_w, inner_w])
    outer.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,0), green),
        ("BOX", (0,0), (-1,-1), 0.9, border),
        ("INNERGRID", (0,0), (-1,-1), 0, border),
        ("LEFTPADDING", (0,0), (0,0), 0),
        ("RIGHTPADDING", (0,0), (0,0), 0),
        ("TOPPADDING", (0,0), (0,0), 0),
        ("BOTTOMPADDING", (0,0), (0,0), 0),
        ("LEFTPADDING", (1,0), (1,0), 0),
        ("RIGHTPADDING", (1,0), (1,0), 0),
        ("TOPPADDING", (1,0), (1,0), 0),
        ("BOTTOMPADDING", (1,0), (1,0), 0),
    ]))
    return outer




def _client_info_boxes(*, font: str, client: dict, plan: dict, date_range: str, available_width: float) -> Table:
    """Two side-by-side boxes: Danışan Bilgileri (left) and Plan Özeti (right), preview-like."""
    border = colors.HexColor("#D9E2EA")
    grid = colors.HexColor("#E3EAF1")
    header_bg = colors.HexColor("#F4F6F8")
    label = colors.HexColor("#334155")
    textc = colors.HexColor("#0f172a")

    styles = getSampleStyleSheet()
    h = ParagraphStyle("nx_box_h", parent=styles["Normal"], fontName=font, fontSize=9.6, leading=12,
                       textColor=textc, spaceAfter=0)
    l = ParagraphStyle("nx_box_l", parent=styles["Normal"], fontName=font, fontSize=8.8, leading=11,
                       textColor=label)
    v = ParagraphStyle("nx_box_v", parent=styles["Normal"], fontName=font, fontSize=8.8, leading=11,
                       textColor=textc)

    # values
    full_name = client.get("full_name") or client.get("name") or ""
    phone = client.get("phone") or client.get("phone_number") or ""
    gender = client.get("gender") or client.get("sex") or ""
    birth = _fmt_tr_date(client.get("birth_date") or client.get("dob") or "")

    title = (plan.get("title") or "").strip()
    period = date_range or ""
    created = plan.get("created_at_ui") or plan.get("created_at") or ""

    # Left box: 2-column label/value rows
    left_rows = [
        [Paragraph("<b>Danışan Bilgileri</b>", h), ""],
        [Paragraph("Ad Soyad", l), Paragraph(str(full_name), v)],
        [Paragraph("Telefon", l), Paragraph(str(phone), v)],
        [Paragraph("Cinsiyet", l), Paragraph(str(gender), v)],
        [Paragraph("Doğum Tarihi", l), Paragraph(str(birth), v)],
    ]
    left = Table(left_rows, colWidths=[28*mm, None])
    left.setStyle(TableStyle([
        ("SPAN", (0,0), (-1,0)),
        ("BACKGROUND", (0,0), (-1,0), header_bg),
        ("BOX", (0,0), (-1,-1), 0.9, border),
        ("INNERGRID", (0,1), (-1,-1), 0.4, grid),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))

    right_rows = [
        [Paragraph("<b>Plan Özeti</b>", h), ""],
        [Paragraph("Plan", l), Paragraph(str(title), v)],
        [Paragraph("Dönem", l), Paragraph(str(period), v)],
    ]
    if created:
        right_rows.append([Paragraph("Oluşturma", l), Paragraph(str(created), v)])

    right = Table(right_rows, colWidths=[24*mm, None])
    right.setStyle(TableStyle([
        ("SPAN", (0,0), (-1,0)),
        ("BACKGROUND", (0,0), (-1,0), header_bg),
        ("BOX", (0,0), (-1,-1), 0.9, border),
        ("INNERGRID", (0,1), (-1,-1), 0.4, grid),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))

    gap = 6*mm
    col_w = (available_width - gap) / 2.0
    outer = Table([[left, right]], colWidths=[col_w, col_w])
    outer.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("RIGHTPADDING", (1, 0), (1, -1), 14),
        ("LEFTPADDING", (1, 0), (1, -1), 6),
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING", (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ]))
    return outer




def _apply_empty_row_style(t: Table, row_index: int):
    try:
        t.setStyle(TableStyle([
            ("TOPPADDING", (0, row_index), (-1, row_index), 8),
            ("BOTTOMPADDING", (0, row_index), (-1, row_index), 8),
        ]))
    except Exception:
        pass


def _header_divider(width: float) -> Table:
    """A subtle horizontal divider line."""
    border = colors.HexColor("#D9E2EA")
    t = Table([[""]], colWidths=[width])
    t.setStyle(TableStyle([
        ("LINEBELOW", (0,0), (-1,-1), 0.8, border),
        ("TOPPADDING", (0,0), (-1,-1), 2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
    ]))
    return t






def draw_page_frame(canvas, doc):
    """Draws a preview-like frame on every page + header logo + footer texts."""
    canvas.saveState()
    try:
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.platypus import Image

        # Content box (margins)
        x = getattr(doc, "leftMargin", 12 * mm)
        y = getattr(doc, "bottomMargin", 12 * mm)
        w = getattr(doc, "width", doc.pagesize[0] - 2 * x)
        h = getattr(doc, "height", doc.pagesize[1] - 2 * y)

        # Frame
        canvas.setStrokeColor(colors.HexColor("#CBD5E1"))
        canvas.setLineWidth(1.5)  # slightly thicker like preview
        r = 3.5 * mm
        try:
            canvas.roundRect(x, y, w, h, r, stroke=1, fill=0)
        except Exception:
            canvas.rect(x, y, w, h, stroke=1, fill=0)

        # Header logo area (top-left inside frame)
        logo_path = getattr(doc, "_nx_logo_path", None)
        if logo_path:
            try:
                # Keep logo in a small box; aspect preserved
                max_h = 14 * mm
                max_w = 32 * mm
                img = Image(logo_path)
                iw, ih = img.imageWidth, img.imageHeight
                if iw and ih:
                    scale = min(max_w / iw, max_h / ih)
                    dw, dh = iw * scale, ih * scale
                else:
                    dw, dh = max_w, max_h
                # position: inside frame with small padding
                canvas.drawImage(logo_path, x + 6*mm, y + h - 6*mm - dh, width=dw, height=dh, preserveAspectRatio=True, mask='auto')
            except Exception:
                pass

        # Footer (every page): left info + right brand
        footer_left = getattr(doc, "_nx_footer_left", "")
        footer_right = getattr(doc, "_nx_footer_right", "NutriNexus")
        canvas.setFont(_FONT, 8)
        canvas.setFillColor(colors.HexColor("#6B7280"))
        fy = y + 5 * mm
        if footer_left:
            canvas.drawString(x + 6 * mm, fy, footer_left)
        if footer_right:
            # right aligned inside frame
            tw = canvas.stringWidth(footer_right, "Helvetica", 8)
            canvas.drawString(x + w - 6 * mm - tw, fy, footer_right)
    finally:
        canvas.restoreState()

def build_diet_plan_pdf(path: str, payload: Dict[str, Any]) -> None:
    font = _register_fonts()
    doc = SimpleDocTemplate(
        path,
        pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=15*mm
    )

    # Runtime assets for page callback
    doc._nx_logo_path = _resolve_logo_path(payload)
    doc._nx_footer_left = "Bu plan, danışanın kişisel hedefleri ve değerlendirmesi temel alınarak hazırlanmıştır."
    doc._nx_footer_right = "NutriNexus"

    
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("nx_title", parent=styles["Title"], fontName=font, fontSize=16, leading=18, spaceAfter=6, alignment=TA_CENTER)
    small_style = ParagraphStyle("nx_small", parent=styles["Normal"], fontName=font, fontSize=9, leading=12, textColor=colors.HexColor('#6B7280'))
    h_style = ParagraphStyle("nx_h", parent=styles["Heading2"], fontName=font, fontSize=11, leading=14, spaceBefore=10, spaceAfter=6)
    n_style = ParagraphStyle("nx_n", parent=styles["Normal"], fontName=font, fontSize=10, leading=14)

    client = payload.get("client", {}) or {}
    plan = payload.get("plan", {}) or {}

    title = (plan.get("title") or "Diyet Planı").strip()
    date_range = (payload.get("date_range") or "").strip()

    
    el = []

    logo = ""
    title_p = Paragraph(f"<font name='{_BOLD_FONT}'>Kişiye Özel Beslenme Planı</font>", title_style)

    header_tbl = Table([[logo, title_p, ""]], colWidths=[28*mm, doc.width - 56*mm, 28*mm])
    header_tbl.setStyle(TableStyle([
    ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ("ALIGN", (0,0), (0,0), "LEFT"),
    ("ALIGN", (1,0), (1,0), "CENTER"),
    ("LEFTPADDING", (0,0), (-1,-1), 0),
    ("RIGHTPADDING", (0,0), (-1,-1), 0),
    ("TOPPADDING", (0,0), (-1,-1), 0),
    ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ]))
    el.append(header_tbl)

    if date_range:
        # Date range should not collide with the logo area; align it to the right.
        small_right = ParagraphStyle('small_right', parent=small_style, alignment=TA_RIGHT)
        date_tbl = Table([["", Paragraph(date_range, small_right)]], colWidths=[28*mm, doc.width - 28*mm])
        date_tbl.setStyle(TableStyle([
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (1,0), (1,0), 6),  # shift date slightly left
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        el.append(date_tbl)
        el.append(Spacer(1, 6))
    el.append(_header_divider(doc.width))
    el.append(_client_info_boxes(font=font, client=client, plan=plan, date_range=date_range, available_width=doc.width))
    el.append(Spacer(1, 6))
    el.append(Spacer(1, 6))

    full_name = (client.get("full_name") or "").strip() or "---"
    phone = (client.get("phone") or "").strip() or "-"
    birth = _fmt_tr_date((client.get("birth_date") or "").strip()) or "-"
    gender = (client.get("gender") or "").strip() or "-"

    sections = payload.get("sections")
    if sections is None:
        sections = _parse_sections(plan.get("plan_text") or "")

    sections = _normalize_sections_for_cards(sections)

    if not sections:
        txt = (plan.get("plan_text") or "").strip()
        if txt:
            el.append(Paragraph("Plan", h_style))
            for ln in txt.splitlines():
                if ln.strip():
                    el.append(Paragraph(ln.strip(), n_style))
    
    else:
        # Render each meal as a 'card' block to match the in-app preview.
        available_width = doc.width  # inside margins
        for sec_title, items in sections:
            card = _meal_card(font=font, sec_title=sec_title, items=items, available_width=available_width)
            el.append(KeepTogether([card, Spacer(1, 6)]))

    notes = (plan.get("notes") or "").strip()
    if notes:
        el.append(Spacer(1, 6))
        el.append(Paragraph("Notlar", h_style))
        for ln in notes.splitlines():
            if ln.strip():
                el.append(Paragraph(ln.strip(), n_style))

    doc.build(el, onFirstPage=draw_page_frame, onLaterPages=draw_page_frame)