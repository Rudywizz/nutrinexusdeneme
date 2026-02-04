from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QFrame
)

from src.services.templates_service import TemplatesService, MealTemplate


class SelectMealTemplateDialog(QDialog):
    """Pick an existing meal template.

    Returns selected template via get_selected().
    """
    def __init__(self, parent=None, *, conn, title: str = "Öğün Şablonu Seç"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(720, 460)

        self._svc = TemplatesService(conn)
        self._selected: MealTemplate | None = None

        root = QVBoxLayout(self)

        card = QFrame()
        card.setObjectName("Card")
        lay = QVBoxLayout(card)

        header = QHBoxLayout()
        header.addWidget(QLabel(title, objectName="CardTitle"))
        header.addStretch(1)

        self.ed_q = QLineEdit()
        self.ed_q.setPlaceholderText("Ara: şablon adı / içerik...")
        self.ed_q.textChanged.connect(self._refresh)
        header.addWidget(self.ed_q)

        lay.addLayout(header)

        self.tbl = QTableWidget(0, 2)
        self.tbl.setHorizontalHeaderLabels(["Şablon", "Önizleme"])
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setColumnWidth(0, 240)
        self.tbl.setColumnWidth(1, 440)
        self.tbl.doubleClicked.connect(self._accept_selected)
        lay.addWidget(self.tbl)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QPushButton("Vazgeç")
        self.btn_cancel.setObjectName("SecondaryBtn")
        self.btn_ok = QPushButton("Ekle")
        self.btn_ok.setObjectName("PrimaryBtn")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._accept_selected)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        lay.addLayout(btns)

        root.addWidget(card)

        self._refresh()

    def _refresh(self):
        q = (self.ed_q.text() or "").strip()
        templates = self._svc.list_meal_templates(q)

        self.tbl.setRowCount(0)
        for t in templates:
            row = self.tbl.rowCount()
            self.tbl.insertRow(row)

            it0 = QTableWidgetItem(t.name)
            it0.setData(Qt.UserRole, t.id)
            self.tbl.setItem(row, 0, it0)

            preview = (t.content or "").strip().splitlines()
            prev_line = preview[0] if preview else ""
            if len(prev_line) > 80:
                prev_line = prev_line[:77] + "..."
            self.tbl.setItem(row, 1, QTableWidgetItem(prev_line))

        if self.tbl.rowCount() > 0:
            self.tbl.selectRow(0)

    def _accept_selected(self):
        r = self.tbl.currentRow()
        if r < 0:
            return
        it = self.tbl.item(r, 0)
        tid = it.data(Qt.UserRole) if it else None
        if not tid:
            return
        # load full template (we already have list; fetch by id via list)
        # simple: find in refreshed list again
        q = (self.ed_q.text() or "").strip()
        for t in self._svc.list_meal_templates(q):
            if t.id == tid:
                self._selected = t
                break
        if not self._selected:
            return
        self.accept()

    def get_selected(self) -> MealTemplate | None:
        return self._selected
