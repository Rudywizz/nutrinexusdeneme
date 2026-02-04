from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable
from reportlab.lib.utils import ImageReader

from src.app.utils.dates import format_tr_date
from src.services.clients_service import ClientsService
from src.services.measurements_service import MeasurementsService


@dataclass(frozen=True)
class CalcSummary:
    bmi: Optional[float]
    bmr: Optional[float]
    tdee: Optional[float]
    target: Optional[float]
    loss: Optional[float]
    maint: Optional[float]
    gain: Optional[float]


def _try_register_arial() -> str:
    """
    TR karakter sorunu yaşamamak için Arial tercih edilir.
    ReportLab PDF içine fontu gömmek için TTF dosyası ister.
    Windows'ta genelde Arial şu yollarda bulunur:
      C:\\Windows\\Fonts\\arial.ttf
    """
    candidates = [
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\Arial.ttf",
    ]
    for p in candidates:
        try:
            if Path(p).exists():
                pdfmetrics.registerFont(TTFont("Arial", p))
                return "Arial"
        except Exception:
            pass

    # Fallback: ReportLab'in temel fontu (TR karakterlerde sorun yaşayabilir).
    return "Helvetica"


def _age_years(birth_iso_yyyy_mm_dd: str) -> int:
    try:
        b = datetime.strptime(birth_iso_yyyy_mm_dd, "%Y-%m-%d").date()
    except Exception:
        return 0
    today = date.today()
    years = today.year - b.year
    if (today.month, today.day) < (b.month, b.day):
        years -= 1
    return max(0, years)


def _calc_summary(*, height_cm: Optional[float], weight_kg: Optional[float], age: int, gender: str,
                  activity_factor: float, adjust_kcal: int) -> CalcSummary:
    bmi = None
    if height_cm and weight_kg and height_cm > 0:
        h_m = height_cm / 100.0
        bmi = weight_kg / (h_m * h_m)

    bmr = None
    if height_cm and weight_kg and age and height_cm > 0 and weight_kg > 0:
        base = 10.0 * weight_kg + 6.25 * height_cm - 5.0 * age
        if gender == "Erkek":
            bmr = base + 5.0
        else:
            bmr = base - 161.0

    tdee = (bmr * activity_factor) if bmr is not None else None
    target = (tdee + adjust_kcal) if tdee is not None else None

    loss = (tdee - 500) if tdee is not None else None
    maint = tdee
    gain = (tdee + 300) if tdee is not None else None

    return CalcSummary(bmi=bmi, bmr=bmr, tdee=tdee, target=target, loss=loss, maint=maint, gain=gain)


def build_client_report_pdf(
    *,
    conn,
    client_id: str,
    out_path: str | Path,
    logo_path: str | Path | None = None,
    activity_factor: float = 1.2,
    goal_adjust_kcal: int = -500,
) -> Path:
    """
    Profesyonel danışan raporu üretir (Sprint 3.7).
    - Boy/kilo: son ölçümden otomatik
    - Hesap: Mifflin–St Jeor (UI ile aynı)
    - Tarih: TR format
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    font_name = _try_register_arial()
    styles = getSampleStyleSheet()

    # Kurumsal görünsün diye base stilleri düzenleyelim
    styles.add(ParagraphStyle(
        name="TitleTR",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=14,
        leading=20,
        alignment=TA_LEFT,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="SubTitleTR",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#555555"),
    ))
    styles.add(ParagraphStyle(
        name="H2TR",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=12,
        leading=16,
        spaceBefore=10,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="NormalTR",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=10,
        leading=14,
    ))
    styles.add(ParagraphStyle(
        name="SmallTR",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#666666"),
    ))
    # PDF görsel cilası: bölüm başlıkları, kart stilleri
    styles.add(ParagraphStyle(
        name="SectionTitleTR",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=0,
        spaceAfter=0,
    ))
    styles.add(ParagraphStyle(
        name="CardValueTR",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=16,
        leading=16,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=1,
    ))
    styles.add(ParagraphStyle(
        name="CardLabelTR",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=9,
        leading=11,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#64748B"),
    ))

    client_svc = ClientsService(conn)
    meas_svc = MeasurementsService(conn)

    client = client_svc.get_client(client_id)
    if client is None:
        raise ValueError("Danışan bulunamadı.")

    last = meas_svc.latest_for_client(client_id)

    # Data hazırlığı
    now = datetime.now().replace(microsecond=0)
    report_date_tr = format_tr_date(now.date().isoformat())

    height = getattr(last, "height_cm", None) if last else None
    weight = getattr(last, "weight_kg", None) if last else None
    measured_at = getattr(last, "measured_at", None) if last else None

    age = _age_years(client.birth_date)
    gender = client.gender

    calc = _calc_summary(
        height_cm=height, weight_kg=weight, age=age, gender=gender,
        activity_factor=activity_factor, adjust_kcal=goal_adjust_kcal
    )

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm, topMargin=16*mm, bottomMargin=55*mm,
        title="NutriNexus Danışan Raporu",
        author="NutriNexus",
    )

    story = []

    ACCENT = colors.HexColor("#2F855A")   # NutriNexus hissi: sakin yeşil
    SOFT_BG = colors.HexColor("#F5F7FA")
    BORDER = colors.HexColor("#E3E6EA")

    def _section(title: str):
        """Kurumsal bölüm başlığı (arka plan + sol aksan)."""
        t = Table([[Paragraph(title, styles["SectionTitleTR"])]], colWidths=[172*mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), SOFT_BG),
            ("BOX", (0,0), (-1,-1), 0.25, BORDER),
            ("LINEBEFORE", (0,0), (0,0), 3, ACCENT),
            ("LEFTPADDING", (0,0), (-1,-1), 10),
            ("RIGHTPADDING", (0,0), (-1,-1), 10),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ]))
        return t

    def _card(value: str, label: str):
        c = Table([[Paragraph(value, styles["CardValueTR"])],
                   [Paragraph(label, styles["CardLabelTR"])]], colWidths=[(172*mm-8*mm)/3])
        c.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), colors.white),
            ("BOX", (0,0), (-1,-1), 0.5, BORDER),
            ("LEFTPADDING", (0,0), (-1,-1), 6),
            ("RIGHTPADDING", (0,0), (-1,-1), 6),
            ("TOPPADDING", (0,0), (-1,-1), 8),
            ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ]))
        return c

    # Header: Logo + Başlık
    header_tbl_data = []
    logo_cell = ""
    if logo_path and Path(logo_path).exists():
        try:
            # Logoyu bozmadan (oran koruyarak) kutuya sığdır
            max_w, max_h = 40*mm, 22*mm
            ir = ImageReader(str(logo_path))
            iw, ih = ir.getSize()
            if iw and ih:
                scale = min(max_w/iw, max_h/ih)
                w, h = iw*scale, ih*scale
            else:
                w, h = max_w, max_h
            img = Image(str(logo_path), width=w, height=h)
            img.hAlign = "LEFT"
            logo_cell = img
        except Exception:
            logo_cell = ""
    header_tbl_data.append([logo_cell, Paragraph("Danışan Raporu", styles["TitleTR"])])

    header_tbl = Table(header_tbl_data, colWidths=[44*mm, 128*mm])
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
        ("TOPPADDING", (0,0), (-1,-1), 0),
    ]))
    story.append(header_tbl)

    story.append(Paragraph(f"Rapor Tarihi: <b>{report_date_tr}</b>", styles["SubTitleTR"]))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1.6, color=ACCENT))
    story.append(Spacer(1, 6))

    # Danışan Bilgileri
    story.append(_section("Danışan Bilgileri"))

    client_table = Table([
        ["Ad Soyad", client.full_name],
        ["Telefon", client.phone],
        ["Doğum Tarihi", format_tr_date(client.birth_date) if client.birth_date else ""],
        ["Cinsiyet", client.gender],
        ["Yaş", str(age)],
    ], colWidths=[36*mm, 136*mm])

    client_table.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), font_name),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("TEXTCOLOR", (0,0), (0,-1), colors.HexColor("#444444")),
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#F5F7FA")),
        ("GRID", (0,0), (-1,-1), 0.25, colors.HexColor("#E3E6EA")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(client_table)
    story.append(Spacer(1, 6))

    # Ölçüm Özeti
    story.append(_section("Son Ölçüm Özeti"))

    if last is None:
        story.append(Paragraph("Bu danışan için ölçüm kaydı bulunamadı.", styles["NormalTR"]))
    else:
        story.append(Paragraph(
            f"Ölçüm Tarihi: <b>{format_tr_date(measured_at) if measured_at else ''}</b> • "
            f"Boy/Kilo ölçüm kaydından otomatik alınmıştır.",
            styles["SmallTR"]
        ))
        meas_table = Table([
            ["Boy (cm)", f"{height:.1f}" if height is not None else "-"],
            ["Kilo (kg)", f"{weight:.1f}" if weight is not None else "-"],
            ["Bel (cm)", f"{getattr(last,'waist_cm', None):.1f}" if getattr(last,'waist_cm', None) is not None else "-"],
            ["Kalça (cm)", f"{getattr(last,'hip_cm', None):.1f}" if getattr(last,'hip_cm', None) is not None else "-"],
        ], colWidths=[36*mm, 136*mm])
        meas_table.setStyle(TableStyle([
            ("FONTNAME", (0,0), (-1,-1), font_name),
            ("FONTSIZE", (0,0), (-1,-1), 9),
            ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#F5F7FA")),
            ("GRID", (0,0), (-1,-1), 0.25, colors.HexColor("#E3E6EA")),
            ("LEFTPADDING", (0,0), (-1,-1), 6),
            ("RIGHTPADDING", (0,0), (-1,-1), 8),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ]))
        story.append(meas_table)

    story.append(Spacer(1, 6))

    # Hesaplama Özeti
    story.append(_section("Hesaplama Özeti (Mifflin–St Jeor)"))
    story.append(Paragraph(
        f"Aktivite Çarpanı: <b>{activity_factor:.2f}</b> • Hedef Ayarı: <b>{goal_adjust_kcal:+d} kcal</b>",
        styles["SmallTR"]
    ))
    story.append(Spacer(1, 6))


    # Özet kartlar (danışana premium hissi verir)
    bmi_txt = "-" if calc.bmi is None else f"{calc.bmi:.1f}"
    tdee_txt = "-" if calc.tdee is None else f"{calc.tdee:.0f}"
    target_txt = "-" if calc.target is None else f"{calc.target:.0f}"

    cards = Table([[
        _card(bmi_txt, "BMI"),
        _card(f"{tdee_txt} kcal", "TDEE (Günlük Enerji)"),
        _card(f"{target_txt} kcal", "Hedef Kalori"),
    ]], colWidths=[(172*mm-8*mm)/3]*3)
    cards.setStyle(TableStyle([
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING", (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))
    story.append(cards)
    def _fmt_kcal(v: Optional[float]) -> str:
        return "-" if v is None else f"{v:.0f} kcal/gün"

    calc_table = Table([
        ["BMI", "-" if calc.bmi is None else f"{calc.bmi:.1f}"],
        ["BMR", _fmt_kcal(calc.bmr)],
        ["TDEE", _fmt_kcal(calc.tdee)],
        ["Hedef Kalori", _fmt_kcal(calc.target)],
        ["Kilo Ver (TDEE-500)", _fmt_kcal(calc.loss)],
        ["Koruma (TDEE)", _fmt_kcal(calc.maint)],
        ["Kilo Al (TDEE+300)", _fmt_kcal(calc.gain)],
    ], colWidths=[60*mm, 112*mm])

    calc_table.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), font_name),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#F5F7FA")),
        ("GRID", (0,0), (-1,-1), 0.25, colors.HexColor("#E3E6EA")),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(calc_table)

    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=0.8, color=BORDER))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Not: Bu rapor NutriNexus tarafından danışan verilerine dayanarak oluşturulmuştur. "
        "Hesaplamalar bilgilendirme amaçlıdır; klinik karar yerine geçmez.",
        styles["SmallTR"]
    ))
    # (Tek sayfa için) Rapor sonunda spacer bırakmıyoruz; boş sayfa oluşmasını engeller.
    # Uzman onayı / imza alanı sayfanın altına sabit olarak çizilir (footer).
    def _on_page(canvas, doc_):
        canvas.saveState()
        # --- Uzman Onayı / İmza (tek sayfa garantisi için sabit alana çizilir) ---
        # Bu alan için bottomMargin yukarıda geniş tutulur.
        sig_x = 18*mm
        sig_w = A4[0] - 36*mm
        sig_y_top = 50*mm  # imza bloğunun üst hizası (mm)
        # Başlık
        canvas.setFont(font_name, 10)
        canvas.setFillColor(colors.HexColor("#0F172A"))
        canvas.drawString(sig_x, sig_y_top + 12, "Uzman Onayı")
        # İnce ayraç çizgisi
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.6)
        canvas.line(sig_x, sig_y_top + 8, sig_x + sig_w, sig_y_top + 8)

        canvas.setFont(font_name, 9)
        canvas.setFillColor(colors.HexColor("#334155"))

        row_y1 = sig_y_top - 2
        canvas.drawString(sig_x, row_y1, "Uzman / Diyetisyen:")
        canvas.setStrokeColor(BORDER)
        canvas.line(sig_x + 34*mm, row_y1 - 2, sig_x + sig_w, row_y1 - 2)

        row_y2 = sig_y_top - 14
        canvas.setFillColor(colors.HexColor("#334155"))
        canvas.drawString(sig_x, row_y2, "Tarih:")
        canvas.setFillColor(colors.HexColor("#0F172A"))
        canvas.drawString(sig_x + 12*mm, row_y2, datetime.now().strftime("%d.%m.%Y"))

        row_y3 = sig_y_top - 28
        canvas.setFillColor(colors.HexColor("#334155"))
        canvas.drawString(sig_x, row_y3, "İmza:")
        canvas.setStrokeColor(BORDER)
        canvas.line(sig_x + 12*mm, row_y3 - 2, sig_x + sig_w, row_y3 - 2)
        # Alt bilgi şeridi
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.6)
        canvas.line(18*mm, 14*mm, A4[0]-18*mm, 14*mm)

        canvas.setFont(font_name, 9)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(18*mm, 8*mm, "NutriNexus • Danışan Raporu")
        canvas.drawRightString(A4[0] - 18*mm, 8*mm, f"Sayfa {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return out_path
