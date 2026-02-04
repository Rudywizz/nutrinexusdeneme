from __future__ import annotations

from typing import List
import html

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QHBoxLayout, QTextBrowser

from src.services.clinical_intelligence import Insight, ClinicalIntelligence


def _sev_color_hex(sev: str) -> str:
    if sev == "critical":
        return "#C0392B"  # red
    if sev == "warn":
        return "#D68910"  # amber
    return "#2E86C1"      # blue


def _render_insights(items: List[Insight]) -> str:
    """Render as compact, wrapped HTML so long texts are readable."""
    lis = []
    for it in items:
        title = html.escape(it.title or "")
        detail = html.escape(it.detail or "")
        color = _sev_color_hex(it.severity)
        if detail:
            body = f"<b>{title}</b><br><span style='color:#566573'>{detail}</span>"
        else:
            body = f"<b>{title}</b>"
        lis.append(
            f"<li style='margin:0 0 8px 0;'>"
            f"<span style='color:{color}'>●</span> {body}</li>"
        )
    return "<ul style='margin:0; padding-left:18px;'>" + "".join(lis) + "</ul>"


class ClinicalIntelligencePanel(QFrame):
    """UI panel that shows rule-based clinical suggestions for a client (offline)."""

    def __init__(self, conn, client_id: str, log=None):
        super().__init__()
        self.setObjectName("Card")
        self.conn = conn
        self.client_id = client_id
        self.log = log
        self.engine = ClinicalIntelligence(conn)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        root.addWidget(QLabel("Klinik Zeka", objectName="CardTitle"))

        row = QHBoxLayout()
        row.setSpacing(12)

        # Ölçüm Trend
        self.box_meas = QFrame()
        self.box_meas.setObjectName("Card")
        mv = QVBoxLayout(self.box_meas)
        mv.setContentsMargins(12, 12, 12, 12)
        mv.setSpacing(8)
        mv.addWidget(QLabel("Ölçüm Trend Uyarıları", objectName="CardTitle"))

        self.txt_meas = QTextBrowser()
        self.txt_meas.setObjectName("IntelText")
        self._setup_text(self.txt_meas)
        mv.addWidget(self.txt_meas, 1)

        # Kan tahlili
        self.box_lab = QFrame()
        self.box_lab.setObjectName("Card")
        lv = QVBoxLayout(self.box_lab)
        lv.setContentsMargins(12, 12, 12, 12)
        lv.setSpacing(8)
        lv.addWidget(QLabel("Kan Tahlili Yorum Önerileri", objectName="CardTitle"))

        self.txt_lab = QTextBrowser()
        self.txt_lab.setObjectName("IntelText")
        self._setup_text(self.txt_lab)
        lv.addWidget(self.txt_lab, 1)

        row.addWidget(self.box_meas, 1)
        row.addWidget(self.box_lab, 1)
        root.addLayout(row)

        hint = QLabel(
            "Not: Bu öneriler kural tabanlıdır, klinik karar yerine geçmez. "
            "Danışan öyküsü ve hekim/diyetisyen değerlendirmesi ile birlikte yorumlayın."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#6B7B88; font-size:11px;")
        root.addWidget(hint)

        self.refresh()

    def _setup_text(self, w: QTextBrowser):
        w.setOpenExternalLinks(False)
        w.setReadOnly(True)
        w.setFrameShape(QFrame.NoFrame)
        w.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        w.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        w.setStyleSheet(
            "QTextBrowser#IntelText {"
            " background: transparent;"
            " border: none;"
            " padding: 0px;"
            " font-size: 12px;"
            "}"
        )

    def refresh(self):
        try:
            meas = self.engine.measurement_alerts(self.client_id)

            _, labs = self.engine.latest_labs(self.client_id)
            if labs:
                lab_ins = self.engine.lab_insights(labs)
            else:
                lab_ins = [
                    Insight(
                        "info",
                        "Henüz kan tahlili yok.",
                        "PDF yükledikten sonra otomatik yorumlar burada oluşur."
                    )
                ]

            if not meas:
                meas = [
                    Insight(
                        "info",
                        "Ölçüm trendi için daha fazla veri gerekiyor.",
                        "En az 2 ölçüm olduğunda trend uyarıları oluşur."
                    )
                ]

            self.txt_meas.setHtml(_render_insights(meas))
            self.txt_lab.setHtml(_render_insights(lab_ins))

        except Exception as e:
            if self.log:
                self.log.exception("ClinicalIntelligencePanel refresh failed", exc_info=e)
            self.txt_meas.setPlainText("Klinik Zeka yüklenemedi.")
            self.txt_lab.setPlainText("Klinik Zeka yüklenemedi.")
