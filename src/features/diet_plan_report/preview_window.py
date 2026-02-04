
from __future__ import annotations

import os
import tempfile
from typing import Optional

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QMessageBox
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtPdf import QPdfDocument

from src.reports.diet_plan_pdf.builder import build_diet_plan_pdf
from .service import build_payload


class DietPlanPdfPreviewWindow(QDialog):
    def __init__(self, parent, *, client: dict, plan, fmt_date_ui):
        super().__init__(parent)
        self.setWindowTitle("Diyet Planı Önizleme (PDF)")
        self.setMinimumSize(900, 700)

        self._client = client
        self._plan = plan
        self._fmt_date_ui = fmt_date_ui

        root = QVBoxLayout(self)

        bar = QHBoxLayout()
        self.btn_save = QPushButton("PDF Kaydet…")
        self.btn_close = QPushButton("Kapat")
        bar.addWidget(self.btn_save)
        bar.addStretch(1)
        bar.addWidget(self.btn_close)
        root.addLayout(bar)

        self._doc = QPdfDocument(self)
        self._view = QPdfView(self)
        self._view.setDocument(self._doc)
        self._view.setZoomMode(QPdfView.ZoomMode.FitInView)
        self._view.setPageMode(QPdfView.PageMode.MultiPage)
        root.addWidget(self._view, 1)

        self.btn_close.clicked.connect(self.close)
        self.btn_save.clicked.connect(self._save_as)

        self._tmp_pdf = self._render_to_temp()
        if self._tmp_pdf:
            self._doc.load(self._tmp_pdf)

    def _render_to_temp(self) -> Optional[str]:
        try:
            payload = build_payload(client=self._client, plan=self._plan, fmt_date_ui=self._fmt_date_ui)
            out_dir = os.path.join(tempfile.gettempdir(), "NutriNexus")
            os.makedirs(out_dir, exist_ok=True)
            plan_id = getattr(self._plan, "id", "x")
            client_name = (self._client.get("full_name") or "client").strip().replace(" ", "_")
            tmp_path = os.path.join(out_dir, f"diet_plan_preview_{client_name}_{plan_id}.pdf")
            build_diet_plan_pdf(tmp_path, payload)
            return tmp_path
        except Exception as e:
            QMessageBox.warning(self, "Önizleme", f"PDF oluşturulamadı:\n{e}")
            return None

    def _save_as(self):
        if not self._tmp_pdf or not os.path.exists(self._tmp_pdf):
            QMessageBox.warning(self, "PDF", "Önce PDF üretilemedi.")
            return

        default_name = "diyet_plani.pdf"
        title = getattr(self._plan, "title", "") or ""
        if title.strip():
            safe = "".join(ch for ch in title if ch.isalnum() or ch in (" ", "-", "_")).strip().replace(" ", "_")
            if safe:
                default_name = f"{safe}.pdf"

        target, _ = QFileDialog.getSaveFileName(self, "PDF Kaydet", default_name, "PDF Files (*.pdf)")
        if not target:
            return
        if not target.lower().endswith(".pdf"):
            target += ".pdf"

        try:
            payload = build_payload(client=self._client, plan=self._plan, fmt_date_ui=self._fmt_date_ui)
            build_diet_plan_pdf(target, payload)
            QMessageBox.information(self, "Başarılı", "PDF kaydedildi.")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"PDF kaydedilemedi:\n{e}")


def show_diet_plan_preview(parent, *, client: dict, plan, fmt_date_ui):
    win = DietPlanPdfPreviewWindow(parent, client=client, plan=plan, fmt_date_ui=fmt_date_ui)
    win.exec()
