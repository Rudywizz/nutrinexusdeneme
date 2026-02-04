from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from uuid import uuid4
import re

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

from src.app.utils.dates import format_tr_date
from src.services.backup import resolve_backup_root
from src.services.clinical_intelligence import ClinicalIntelligence, Insight
from src.services.clients_service import ClientsService

# Reuse Arial registration helper from main PDF report module
from src.reports.pdf_report import _try_register_arial


def _safe_filename(text) -> str:
    """Windows-safe filename.
    Accepts str; if dict/object is passed accidentally, tries to extract a usable name."""
    if isinstance(text, dict):
        for k in ("full_name", "name", "title", "value", "label"):
            v = text.get(k)
            if isinstance(v, str) and v.strip():
                text = v
                break
        else:
            text = str(text)
    elif text is None:
        text = ""
    elif not isinstance(text, str):
        text = str(text)

    t = (text or "").strip()
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"[\\/:*?\"<>|]+", "-", t)
    t = t.replace(" ", "_")
    return t or "Danisan"



def _as_text(v) -> str:
    """Coerce possibly-dict values to a clean string."""
    if v is None:
        return ""
    if isinstance(v, dict):
        # common shapes
        for k in ("text", "title", "name", "value", "label", "detail", "message"):
            vv = v.get(k)
            if isinstance(vv, str) and vv.strip():
                return vv.strip()
        return str(v)
    if not isinstance(v, str):
        return str(v)
    return v.strip()

def _bmi(height_cm: Optional[float], weight_kg: Optional[float]) -> Optional[float]:
    if not height_cm or not weight_kg:
        return None
    if height_cm <= 0:
        return None
    m = height_cm / 100.0
    return weight_kg / (m * m)


def build_clinical_summary_pdf(*, conn, client_id: str, out_dir: str | Path | None = None, logo_path: str | Path | None = None) -> Path:
    """Sprint 4.3: Tek sayfa Klinik Özet PDF.
    Dosya adı: AdSoyad_YYYY-MM-DD_KlinikOzet_<unique>.pdf
    Varsayılan klasör: backup_root/reports/clinical
    """
    out_base = Path(out_dir) if out_dir else (resolve_backup_root() / "reports" / "clinical")
    out_base.mkdir(parents=True, exist_ok=True)

    cs = ClientsService(conn)
    client = cs.get_client(client_id)
    full_name = getattr(client, 'full_name', None) if client else 'Danışan'
    if isinstance(full_name, dict):
        full_name = full_name.get('full_name') or full_name.get('name') or 'Danışan'

    today_iso = datetime.now().date().isoformat()
    unique = uuid4().hex[:6].upper()
    fname = f"{_safe_filename(full_name)}_{today_iso}_KlinikOzet_{unique}.pdf"
    out_path = out_base / fname

    # data
    engine = ClinicalIntelligence(conn)
    meas_alerts: List[Insight] = engine.measurement_alerts(client_id) or []
    lab_taken_at, lab_rows = engine.latest_labs(client_id)
    lab_ins = engine.lab_insights(lab_rows) if lab_rows else []

    # latest measurement
    row = conn.execute(
        """SELECT measured_at, height_cm, weight_kg, waist_cm
           FROM measurements WHERE client_id=? ORDER BY measured_at DESC LIMIT 1""",
        (client_id,),
    ).fetchone()
    m_date = row[0] if row else ""
    height_cm = float(row[1]) if row and row[1] is not None else None
    weight_kg = float(row[2]) if row and row[2] is not None else None
    waist_cm = float(row[3]) if row and row[3] is not None else None
    bmi = _bmi(height_cm, weight_kg)

    font_name = _try_register_arial()
    styles = getSampleStyleSheet()
    base = ParagraphStyle(
        "base", parent=styles["Normal"], fontName=font_name, fontSize=10, leading=13, textColor=colors.HexColor("#1f2d3d")
    )
    h1 = ParagraphStyle(
        "h1", parent=base, fontSize=16, leading=18, spaceAfter=6, textColor=colors.HexColor("#0B1F2A")
    )
    h2 = ParagraphStyle(
        "h2", parent=base, fontSize=12, leading=14, spaceBefore=8, spaceAfter=6, textColor=colors.HexColor("#0B1F2A")
    )
    muted = ParagraphStyle(
        "muted", parent=base, fontSize=9, leading=12, textColor=colors.HexColor("#6B7785")
    )

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="Klinik Özet",
        author="NutriNexus",
    )

    story = []
    story.append(Paragraph("Klinik Özet", h1))
    story.append(Paragraph(f"<b>Danışan:</b> {full_name}  &nbsp;&nbsp; <b>Tarih:</b> {format_tr_date(today_iso)}", base))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#D7DEE6")))
    story.append(Spacer(1, 8))

    # Measurement card table
    story.append(Paragraph("Son Ölçüm", h2))
    meas_tbl = [
        ["Ölçüm Tarihi", format_tr_date(m_date) if m_date else "-"],
        ["Boy / Kilo", f"{height_cm:.0f} cm / {weight_kg:.1f} kg" if height_cm and weight_kg else "-"],
        ["BMI", f"{bmi:.1f}" if bmi else "-"],
        ["Bel", f"{waist_cm:.0f} cm" if waist_cm else "-"],
    ]
    t = Table(meas_tbl, colWidths=[35*mm, 145*mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), font_name),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("TEXTCOLOR", (0,0), (0,-1), colors.HexColor("#425466")),
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#F7F9FC")),
        ("BOX", (0,0), (-1,-1), 0.6, colors.HexColor("#D7DEE6")),
        ("INNERGRID", (0,0), (-1,-1), 0.3, colors.HexColor("#D7DEE6")),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(t)

    # Clinical summary
    story.append(Paragraph("Klinik Zeka • Tek Bakış", h2))

    def _sev_color(sev: str) -> str:
        return {"critical":"#E74C3C", "warn":"#F39C12", "info":"#3498DB"}.get(sev or "info", "#3498DB")

    combined: List[Insight] = []
    combined.extend(meas_alerts)
    combined.extend(lab_ins)

    # sort by severity score then keep first 6 to fit one page
    sev_score = {"critical":3, "warn":2, "info":1}
    combined.sort(key=lambda x: (sev_score.get(x.severity or "info",1), x.title or ""), reverse=True)
    top = combined[:6]

    if not top:
        story.append(Paragraph("Henüz klinik öneri yok.", muted))
    else:
        # build bullets as Paragraphs
        for it in top:
            title = _as_text(getattr(it, 'title', None))
            detail = _as_text(getattr(it, 'detail', None))
            sev = _as_text(getattr(it, 'severity', None)) or "info"
            dot = f"<font color='{_sev_color(sev)}'>●</font>"
            body = f"{dot} <b>{title}</b>"
            if detail:
                body += f"<br/><font color='#566573'>{detail}</font>"
            story.append(Paragraph(body, base))
            story.append(Spacer(1, 4))

    # Lab taken at info
    if lab_taken_at:
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"<font color='#6B7785'>Not: Son kan tahlili tarihi: {format_tr_date(lab_taken_at)}</font>", muted))

    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#D7DEE6")))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Bu çıktı kural tabanlı öneriler içerir; klinik karar yerine geçmez.", muted))

    doc.build(story)
    return out_path