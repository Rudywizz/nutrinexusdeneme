from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QMessageBox, QFrame
)

from src.services.backup import resolve_backup_root


def _safe_filename_prefix(text: str) -> str:
    # Match the PDF naming used: AdSoyad_YYYY-MM-DD_KlinikOzet_<unique>.pdf
    # Convert to underscores and strip unsafe chars similar to PDF module.
    import re
    if text is None:
        text = ""
    if not isinstance(text, str):
        text = str(text)
    t = (text or "").strip()
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"[\\/:*?\"<>|]+", "-", t)
    t = t.replace(" ", "_")
    return t


@dataclass
class ClinicalPdfItem:
    path: Path
    mtime: float


class ClinicalSummariesScreen(QWidget):
    """
    Danışan bazlı Klinik Özet PDF arşivi.
    Dosya sistemi tarar (offline), DB dokunmaz.
    """
    def __init__(self, client_id: int, client_name: str, parent=None):
        super().__init__(parent)
        self.client_id = client_id
        self.client_name = client_name or ""
        self.setObjectName("ClinicalSummariesScreen")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Klinik Özetler")
        title.setObjectName("SectionTitle")
        title.setStyleSheet("font-weight:700; font-size:14px;")
        header.addWidget(title)
        header.addStretch(1)

        self.btn_refresh = QPushButton("Yenile")
        self.btn_open = QPushButton("Aç")
        self.btn_reveal = QPushButton("Klasörde Göster")
        for b in (self.btn_refresh, self.btn_open, self.btn_reveal):
            b.setMinimumHeight(32)
        header.addWidget(self.btn_refresh)
        header.addWidget(self.btn_open)
        header.addWidget(self.btn_reveal)
        root.addLayout(header)

        card = QFrame()
        card.setObjectName("Card")
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(14, 14, 14, 14)
        card_l.setSpacing(8)

        self.lbl_hint = QLabel(
            "Bu bölüm, oluşturduğun Klinik Özet PDF'lerini otomatik listeler.\n"
            "PDF üretip buraya geçtiğinde 'Yenile' ile güncelleyebilirsin."
        )
        self.lbl_hint.setStyleSheet("color: rgba(255,255,255,0.70);")
        self.lbl_hint.setWordWrap(True)
        card_l.addWidget(self.lbl_hint)

        self.lst = QListWidget()
        self.lst.setObjectName("ClinicalSummaryList")
        self.lst.setAlternatingRowColors(False)
        card_l.addWidget(self.lst, 1)

        root.addWidget(card, 1)

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_open.clicked.connect(self.open_selected)
        self.btn_reveal.clicked.connect(self.reveal_selected)
        self.lst.itemDoubleClicked.connect(lambda *_: self.open_selected())

        self.refresh()

    def showEvent(self, e):
        super().showEvent(e)
        # Auto refresh when tab is shown (avoid "why not visible" confusion)
        self.refresh()

    def _base_dirs(self) -> List[Path]:
        base = resolve_backup_root() / "reports" / "clinical"
        dirs = [base, base / str(self.client_id)]
        return dirs

    def _scan(self) -> List[ClinicalPdfItem]:
        prefix = _safe_filename_prefix(self.client_name)
        items: List[ClinicalPdfItem] = []
        for d in self._base_dirs():
            try:
                if not d.exists():
                    continue
                for p in d.glob("*.pdf"):
                    name = p.name
                    if "KlinikOzet" not in name:
                        continue
                    # Match by client name prefix if possible; if no name, list all.
                    if prefix and not name.startswith(prefix + "_"):
                        continue
                    items.append(ClinicalPdfItem(path=p, mtime=p.stat().st_mtime))
            except Exception:
                continue
        items.sort(key=lambda it: it.mtime, reverse=True)
        return items

    def refresh(self):
        self.lst.clear()
        items = self._scan()
        if not items:
            it = QListWidgetItem("Henüz Klinik Özet PDF bulunamadı.")
            it.setFlags(Qt.NoItemFlags)
            self.lst.addItem(it)
            return
        for itx in items[:50]:
            dt = datetime.fromtimestamp(itx.mtime).strftime("%d.%m.%Y %H:%M")
            item = QListWidgetItem(f"{dt}  —  {itx.path.name}")
            item.setData(Qt.UserRole, str(itx.path))
            self.lst.addItem(item)

    def _selected_path(self) -> Optional[Path]:
        item = self.lst.currentItem()
        if not item:
            return None
        p = item.data(Qt.UserRole)
        if not p:
            return None
        try:
            return Path(p)
        except Exception:
            return None

    def open_selected(self):
        p = self._selected_path()
        if not p or not p.exists():
            QMessageBox.information(self, "Bilgi", "Açılacak PDF bulunamadı.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    def reveal_selected(self):
        p = self._selected_path()
        if not p or not p.exists():
            QMessageBox.information(self, "Bilgi", "Dosya bulunamadı.")
            return
        # Windows: open folder and select file
        try:
            if os.name == "nt":
                os.system(f'explorer /select,"{str(p)}"')
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent)))
        except Exception:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent)))
