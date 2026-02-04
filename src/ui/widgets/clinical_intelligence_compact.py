from __future__ import annotations
from PySide6.QtGui import QDesktopServices

from typing import List
import html

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QTextBrowser, QMessageBox

from src.services.clinical_intelligence import ClinicalIntelligence, Insight
from src.ui.dialogs.clinical_insights_dialog import ClinicalInsightsDialog
from src.reports.clinical_summary_pdf import build_clinical_summary_pdf
from src.services.backup import resolve_backup_root


_SEV_SCORE = {"critical": 3, "warn": 2, "info": 1}

def _sev_dot(sev: str) -> str:
    if sev == "critical":
        return "#C0392B"
    if sev == "warn":
        return "#E67E22"
    return "#2E86C1"

def _dedup(items: List[Insight]) -> List[Insight]:
    seen=set()
    out=[]
    for it in items:
        key=(it.severity or "", it.title or "", it.detail or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out

def _top3_combined(meas: List[Insight], labs: List[Insight]) -> List[Insight]:
    # Prefix category into title (tek bakışta anlaşılır)
    combined=[]
    for it in meas:
        combined.append(Insight(it.severity, f"Trend: {it.title}", it.detail))
    for it in labs:
        combined.append(Insight(it.severity, f"Tahlil: {it.title}", it.detail))
    combined=_dedup(combined)
    combined.sort(key=lambda x: _SEV_SCORE.get(x.severity or "info", 1), reverse=True)
    return combined[:3]

def _render(items: List[Insight]) -> str:
    if not items:
        return '<div style="color:#7F8C8D; font-size:12px;">Henüz öneri yok.</div>'
    lis=[]
    for it in items:
        title = html.escape(it.title or "")
        detail = html.escape(it.detail or "")
        color=_sev_dot(it.severity or "info")
        body = f"<b>{title}</b>"
        if detail:
            body += f"<br><span style='color:#566573'>{detail}</span>"
        lis.append(
            f"<li style='margin:0 0 10px 0;'><span style='color:{color}'>●</span> {body}</li>"
        )
    return "<ul style='margin:0; padding-left:18px;'>" + "".join(lis) + "</ul>"

class ClinicalIntelligenceCompactPanel(QFrame):
    """Özet ekranı için: En Kritik 3 + Tümünü Gör."""
    def __init__(self, conn, client_id: str, log=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.conn=conn
        self.client_id=client_id
        self.log=log
        self.engine=ClinicalIntelligence(conn)

        root=QVBoxLayout(self)
        root.setContentsMargins(12,12,12,12)
        root.setSpacing(10)

        header=QHBoxLayout()
        header.addWidget(QLabel("Klinik Zeka • Tek Bakış", objectName="CardTitle"), 1)

        self.btn_pdf=QPushButton("PDF")
        self.btn_pdf.setObjectName("LinkButton")
        self.btn_pdf.setFlat(True)
        self.btn_pdf.setCursor(Qt.PointingHandCursor)
        # UIFIX: görünür ve link gibi dursun (tema bağımsız)
        self.btn_pdf.setStyleSheet("QPushButton{color:#1a73e8;background:transparent;border:none;padding:2px 6px;font-weight:600;}""QPushButton:hover{text-decoration:underline;}""QPushButton:pressed{color:#1558b0;}")
        self.btn_pdf.clicked.connect(self._export_pdf)

        self.btn_all=QPushButton("Tümünü Gör")
        self.btn_all.setObjectName("LinkButton")
        self.btn_all.setFlat(True)
        self.btn_all.setFocusPolicy(Qt.NoFocus)
        self.btn_all.setStyleSheet(
            "QPushButton#LinkButton{color:#2D7FF9; background:transparent; border:none; padding:4px 8px;}"
            "QPushButton#LinkButton:hover{text-decoration:underline;}"
            "QPushButton#LinkButton:pressed{opacity:0.7;}"
        )
        self.btn_all.setToolTip("Tüm klinik içgörüleri görüntüle")
        self.btn_all.setCursor(Qt.PointingHandCursor)
        self.btn_all.clicked.connect(self._open_all)
        header.addWidget(self.btn_pdf)
        header.addWidget(self.btn_all)
        root.addLayout(header)

        self.txt=QTextBrowser()
        self.txt.setObjectName("IntelText")
        self.txt.setOpenExternalLinks(False)
        self.txt.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.txt.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.txt.setReadOnly(True)
        root.addWidget(self.txt, 1)

        self.refresh()

    def refresh(self):
        try:
            meas=self.engine.measurement_alerts(self.client_id)
            _, lab_rows=self.engine.latest_labs(self.client_id)
            labs=self.engine.lab_insights(lab_rows) if lab_rows else []
            top=_top3_combined(meas, labs)
            self.txt.setHtml(_render(top))
        except Exception as e:
            if self.log:
                self.log.exception("ClinicalIntelligenceCompactPanel refresh failed", exc_info=e)
            self.txt.setPlainText("Klinik Zeka yüklenemedi.")

    def _export_pdf(self):
        """Tek sayfa Klinik Özet PDF üretir ve açar."""
        try:
            out_path = build_clinical_summary_pdf(conn=self.conn, client_id=str(self.client_id), out_dir=(resolve_backup_root() / 'reports' / 'clinical' / str(self.client_id)))
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(out_path)))
        except Exception as e:
            if self.log:
                try:
                    self.log.exception(e)
                except Exception:
                    pass
            QMessageBox.warning(self, "PDF", f"PDF oluşturulamadı: {e}")

    def _open_all(self):
        dlg=ClinicalInsightsDialog(conn=self.conn, client_id=self.client_id, log=self.log, parent=self)
        dlg.exec()