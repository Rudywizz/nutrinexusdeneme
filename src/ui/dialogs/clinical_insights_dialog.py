from __future__ import annotations

from typing import List, Tuple
import html

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QTabWidget, QLineEdit, QTextBrowser, QToolButton, QButtonGroup, QApplication
)

from src.services.clinical_intelligence import ClinicalIntelligence, Insight
from src.ui.widgets.custom_titlebar import CustomTitleBar


_SEV_LABELS = {
    "all": "Hepsi",
    "critical": "Kritik",
    "warn": "Uyarı",
    "info": "Bilgi",
}

_SEV_SCORE = {"critical": 3, "warn": 2, "info": 1}


def _render_cards(items: List[Insight]) -> str:
    # Simple HTML cards inside QTextBrowser (readable, wrapped)
    parts = []
    for it in items:
        title = html.escape(it.title or "")
        detail = html.escape(it.detail or "")
        sev = it.severity or "info"
        if sev == "critical":
            color = "#C0392B"
            badge = "Kritik"
        elif sev == "warn":
            color = "#E67E22"
            badge = "Uyarı"
        else:
            color = "#2E86C1"
            badge = "Bilgi"
        parts.append(
            f"""<div style="border:1px solid #E5E7E9; border-radius:10px; padding:10px 12px; margin:0 0 10px 0;">
                <div style="display:flex; align-items:center; gap:8px;">
                  <span style="color:{color}; font-weight:700;">●</span>
                  <span style="font-weight:700;">{title}</span>
                  <span style="margin-left:auto; color:white; background:{color}; padding:2px 8px; border-radius:999px; font-size:11px;">{badge}</span>
                </div>
                <div style="margin-top:6px; color:#566573; font-size:12px; line-height:1.35;">{detail}</div>
            </div>"""
        )
    if not parts:
        return '<div style="color:#7F8C8D; font-size:12px;">Gösterilecek kayıt yok.</div>'
    return "".join(parts)


def _filter(items: List[Insight], sev: str, q: str) -> List[Insight]:
    qn = (q or "").strip().lower()
    out = []
    for it in items:
        if sev != "all" and (it.severity or "info") != sev:
            continue
        if qn:
            hay = f"{it.title} {it.detail}".lower()
            if qn not in hay:
                continue
        out.append(it)
    return out


def _dedup_sorted(items: List[Insight]) -> List[Insight]:
    seen = set()
    uniq = []
    for it in items:
        key = (it.severity or "", it.title or "", it.detail or "")
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    # score desc
    uniq.sort(key=lambda x: _SEV_SCORE.get(x.severity or "info", 1), reverse=True)
    return uniq


class ClinicalInsightsDialog(QDialog):
    def __init__(self, conn, client_id: str, log=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowFlag(Qt.Window, True)
        self.conn = conn
        self.client_id = client_id
        self.log = log
        self.engine = ClinicalIntelligence(conn)

        self._sev = "all"  # current filter
        self.setMinimumSize(820, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Titlebar
        tb = CustomTitleBar(self, title="Klinik Zeka • Tüm Öneriler", logo_path="src/assets/nutrinexus_logo.png")
        root.addWidget(tb)

        body = QFrame()
        body.setObjectName("DialogBody")
        b = QVBoxLayout(body)
        b.setContentsMargins(14, 14, 14, 14)
        b.setSpacing(10)

        # Controls row
        ctrl = QHBoxLayout()

        # Filter chips (frameless-safe, no popup)
        self._chip_group = QButtonGroup(self)
        self._chip_group.setExclusive(True)

        def _mk_chip(text: str, key: str, checked: bool = False) -> QToolButton:
            btn = QToolButton()
            btn.setObjectName("FilterChip")
            btn.setText(text)
            btn.setCheckable(True)
            btn.setChecked(checked)
            btn.clicked.connect(lambda _=False, k=key: self._on_filter_changed(k))
            self._chip_group.addButton(btn)
            return btn

        self.chip_all = _mk_chip("Hepsi", "all", True)
        self.chip_critical = _mk_chip("Kritik", "critical")
        self.chip_warn = _mk_chip("Uyarı", "warn")
        self.chip_info = _mk_chip("Bilgi", "info")

        self.edt_q = QLineEdit()
        self.edt_q.setPlaceholderText("Ara (başlık / detay içinde)…")
        self.edt_q.textChanged.connect(self._apply)

        self.btn_copy = QPushButton("Panoya Kopyala")
        self.btn_copy.clicked.connect(self._copy_current)

        # toast / info label
        self.lbl_toast = QLabel("")
        self.lbl_toast.setObjectName("ToastLabel")
        self.lbl_toast.setVisible(False)

        self.btn_close = QPushButton("Kapat")
        self.btn_close.clicked.connect(self.close)

        ctrl.addWidget(QLabel("Filtre:", objectName="FieldLabel"))
        ctrl.addWidget(self.chip_all)
        ctrl.addWidget(self.chip_critical)
        ctrl.addWidget(self.chip_warn)
        ctrl.addWidget(self.chip_info)
        ctrl.addWidget(self.edt_q, 1)
        ctrl.addWidget(self.btn_copy)
        ctrl.addWidget(self.btn_close)

        b.addLayout(ctrl)
        b.addWidget(self.lbl_toast)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setObjectName("InnerTabs")

        self.txt_meas = QTextBrowser()
        self.txt_meas.setOpenExternalLinks(False)
        self.txt_meas.setObjectName("InsightBrowser")

        self.txt_lab = QTextBrowser()
        self.txt_lab.setOpenExternalLinks(False)
        self.txt_lab.setObjectName("InsightBrowser")

        self.tabs.addTab(self.txt_meas, "Ölçüm Trend Uyarıları")
        self.tabs.addTab(self.txt_lab, "Kan Tahlili Yorumları")
        self.tabs.currentChanged.connect(lambda _i: self._apply())

        b.addWidget(self.tabs, 1)

        root.addWidget(body, 1)

        self.refresh()

    def _on_filter_changed(self, key: str):
        if key not in _SEV_LABELS:
            return
        self._sev = key
        # keep chips in sync (in case changed programmatically)
        mapping = {
            'all': self.chip_all,
            'critical': self.chip_critical,
            'warn': self.chip_warn,
            'info': self.chip_info,
        }
        btn = mapping.get(key)
        if btn is not None:
            btn.setChecked(True)
        self._apply()

    def _current_items(self) -> List[Insight]:
        if self.tabs.currentIndex() == 0:
            return self._meas_items
        return self._lab_items

    def refresh(self):
        try:
            self._meas_items = self.engine.measurement_alerts(self.client_id)
            _, lab_rows = self.engine.latest_labs(self.client_id)
            self._lab_items = self.engine.lab_insights(lab_rows) if lab_rows else []
            # Apply initial render
            self._apply()
        except Exception as e:
            if self.log:
                self.log.exception("ClinicalInsightsDialog refresh failed", exc_info=e)
            self.txt_meas.setPlainText("Veriler yüklenemedi.")
            self.txt_lab.setPlainText("Veriler yüklenemedi.")

    def _apply(self):
        sev = self._sev
        q = self.edt_q.text()
        meas_items = _filter(self._meas_items, sev, q)
        lab_items = _filter(self._lab_items, sev, q)
        self.txt_meas.setHtml(_render_cards(meas_items))
        self.txt_lab.setHtml(_render_cards(lab_items))

    def _show_toast(self, text: str, ok: bool = True):
        # Simple inline toast under controls
        self.lbl_toast.setText(text)
        self.lbl_toast.setProperty("ok", ok)
        self.lbl_toast.style().unpolish(self.lbl_toast)
        self.lbl_toast.style().polish(self.lbl_toast)
        self.lbl_toast.setVisible(True)
        QTimer.singleShot(1600, lambda: self.lbl_toast.setVisible(False))

    def _copy_current(self):
        sev = self._sev
        q = self.edt_q.text()
        items = _filter(self._current_items(), sev, q)

        if not items:
            self._show_toast("Kopyalanacak içerik yok.", ok=False)
            return

        # Plain text copy
        out_lines = []
        for it in items:
            badge = "Kritik" if it.severity == "critical" else ("Uyarı" if it.severity == "warn" else "Bilgi")
            out_lines.append(f"[{badge}] {it.title}")
            if it.detail:
                out_lines.append(f"- {it.detail}")
            out_lines.append("")
        txt = "\n".join(out_lines).strip()

        QApplication.clipboard().setText(txt)
        self._show_toast("Kopyalandı ✅")