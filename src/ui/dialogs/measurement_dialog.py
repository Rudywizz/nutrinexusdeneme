from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from PySide6.QtCore import Qt, QTimer, QDate
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QDateEdit, QCalendarWidget, QMessageBox, QFrame
)

from src.ui.theme.win_titlebar import apply_light_titlebar
from src.ui.widgets.custom_titlebar import CustomTitleBar


def _to_float(text: str) -> float | None:
    t = (text or "").strip().replace(",", ".")
    if not t:
        return None
    try:
        return float(t)
    except Exception:
        return None


@dataclass
class MeasurementInput:
    measured_at: date
    height_cm: float | None
    weight_kg: float | None
    waist_cm: float | None
    hip_cm: float | None
    neck_cm: float | None
    body_fat_percent: float | None
    muscle_kg: float | None
    water_percent: float | None
    visceral_fat: float | None
    notes: str


class MeasurementDialog(QDialog):
    def __init__(self, parent=None, existing=None):
        super().__init__(parent)
        self._existing = existing
        self.result_data: MeasurementInput | None = None

        self.setWindowTitle("Ölçüm Düzenle" if existing else "Ölçüm Ekle")
        try:
            self.setWindowFlag(Qt.FramelessWindowHint, True)
        except Exception:
            pass

        # Window icon (optional)
        try:
            import os
            base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets"))
            ico_path = os.path.join(base, "icons", "calendar.png")
            if os.path.exists(ico_path):
                self.setWindowIcon(QIcon(ico_path))
        except Exception:
            pass

        # Titlebar (best-effort)
        QTimer.singleShot(0, lambda: apply_light_titlebar(self))

        self.setModal(True)
        self.setMinimumWidth(760)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        # Header
        header = QVBoxLayout()
        title = QLabel("Ölçüm Bilgileri")
        title.setObjectName("DialogTitle")
        subtitle = QLabel("Danışanın ölçüm değerlerini girin. Boş bırakılan alanlar kaydedilmez.")
        subtitle.setObjectName("SubTitle")
        header.addWidget(title)
        header.addWidget(subtitle)
        root.addLayout(header)

        # Main card
        card = QFrame()
        card.setObjectName("InnerCard")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(16, 14, 16, 14)
        card_lay.setSpacing(10)

        # Two-column form grid
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)

        def _mk_label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setFont(QFont("Arial", 9, QFont.Bold))
            lbl.setStyleSheet("color: rgba(12, 42, 51, 0.68);")
            return lbl

        # Date
        self.ed_date = QDateEdit()
        self.ed_date.setCalendarPopup(True)
        self.ed_date.setDisplayFormat("dd.MM.yyyy")
        self.ed_date.setDate(QDate.currentDate())
        self.ed_date.setMinimumWidth(160)

        # Make calendar readable & avoid ellipses
        try:
            cal = self.ed_date.calendarWidget()
            if isinstance(cal, QCalendarWidget):
                cal.setMinimumSize(360, 260)
                cal.setFont(QFont("Arial", 9))
        except Exception:
            pass

        # Numeric inputs (keep naming expected by screens)
        self.ed_height = QLineEdit(); self.ed_height.setPlaceholderText("cm")
        self.ed_weight = QLineEdit(); self.ed_weight.setPlaceholderText("kg")
        self.ed_waist  = QLineEdit(); self.ed_waist.setPlaceholderText("cm")
        self.ed_hip    = QLineEdit(); self.ed_hip.setPlaceholderText("cm")
        self.ed_neck   = QLineEdit(); self.ed_neck.setPlaceholderText("cm")
        self.ed_bfp    = QLineEdit(); self.ed_bfp.setPlaceholderText("%")
        self.ed_muscle = QLineEdit(); self.ed_muscle.setPlaceholderText("kg")
        self.ed_water  = QLineEdit(); self.ed_water.setPlaceholderText("%")
        self.ed_visceral = QLineEdit(); self.ed_visceral.setPlaceholderText("")
        self.ed_notes  = QTextEdit()
        self.ed_notes.setPlaceholderText("Not (opsiyonel)")
        self.ed_notes.setFixedHeight(74)

        # Left column
        r = 0
        grid.addWidget(_mk_label("Tarih"), r, 0); grid.addWidget(self.ed_date, r, 1); r += 1
        grid.addWidget(_mk_label("Boy"), r, 0); grid.addWidget(self.ed_height, r, 1); r += 1
        grid.addWidget(_mk_label("Kilo"), r, 0); grid.addWidget(self.ed_weight, r, 1); r += 1
        grid.addWidget(_mk_label("Bel"), r, 0); grid.addWidget(self.ed_waist, r, 1); r += 1
        grid.addWidget(_mk_label("Kalça"), r, 0); grid.addWidget(self.ed_hip, r, 1); r += 1

        # Right column
        r = 0
        grid.addWidget(_mk_label("Boyun"), r, 2); grid.addWidget(self.ed_neck, r, 3); r += 1
        grid.addWidget(_mk_label("Yağ %"), r, 2); grid.addWidget(self.ed_bfp, r, 3); r += 1
        grid.addWidget(_mk_label("Kas (kg)"), r, 2); grid.addWidget(self.ed_muscle, r, 3); r += 1
        grid.addWidget(_mk_label("Su %"), r, 2); grid.addWidget(self.ed_water, r, 3); r += 1
        grid.addWidget(_mk_label("Visseral Yağ"), r, 2); grid.addWidget(self.ed_visceral, r, 3); r += 1

        # Notes spans full width
        grid.addWidget(_mk_label("Not"), 5, 0, 1, 1)
        grid.addWidget(self.ed_notes, 5, 1, 1, 3)

        card_lay.addLayout(grid)
        root.addWidget(card)

        # Buttons
        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QPushButton("İptal")
        self.btn_save = QPushButton("Kaydet")
        self.btn_save.setObjectName("primary")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save.clicked.connect(self._on_save)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_save)
        root.addLayout(btns)
# Prefill if editing
        if existing:
            def _set(w: QLineEdit, v):
                if v is None:
                    w.setText("")
                else:
                    w.setText(str(v).replace(".", ","))
            try:
                if getattr(existing, "measured_at", None):
                    self.ed_date.setDate(QDate(existing.measured_at.year, existing.measured_at.month, existing.measured_at.day))
            except Exception:
                pass
            _set(self.ed_height, getattr(existing, "height_cm", None))
            _set(self.ed_weight, getattr(existing, "weight_kg", None))
            _set(self.ed_waist, getattr(existing, "waist_cm", None))
            _set(self.ed_hip, getattr(existing, "hip_cm", None))
            _set(self.ed_neck, getattr(existing, "neck_cm", None))
            _set(self.ed_bfp, getattr(existing, "body_fat_percent", None))
            _set(self.ed_muscle, getattr(existing, "muscle_kg", None))
            _set(self.ed_water, getattr(existing, "water_percent", None))
            _set(self.ed_visceral, getattr(existing, "visceral_fat", None))
            try:
                self.ed_notes.setPlainText(getattr(existing, "notes", "") or "")
            except Exception:
                pass

    def _on_save(self):
        # validate numeric fields
        vals = {
            "height": _to_float(self.ed_height.text()),
            "weight": _to_float(self.ed_weight.text()),
            "waist": _to_float(self.ed_waist.text()),
            "hip": _to_float(self.ed_hip.text()),
            "neck": _to_float(self.ed_neck.text()),
            "bfp": _to_float(self.ed_bfp.text()),
            "muscle": _to_float(self.ed_muscle.text()),
            "water": _to_float(self.ed_water.text()),
            "visceral": _to_float(self.ed_visceral.text()),
        }
        for key, raw in [
            ("height", self.ed_height.text()),
            ("weight", self.ed_weight.text()),
            ("waist", self.ed_waist.text()),
            ("hip", self.ed_hip.text()),
            ("neck", self.ed_neck.text()),
            ("bfp", self.ed_bfp.text()),
            ("muscle", self.ed_muscle.text()),
            ("water", self.ed_water.text()),
            ("visceral", self.ed_visceral.text()),
        ]:
            if (raw or "").strip() and vals[key] is None:
                QMessageBox.warning(self, "Hatalı değer", "Sayısal alanlara sadece sayı girilmelidir (örn: 72.5).")
                return

        qd = self.ed_date.date()
        measured_at = date(qd.year(), qd.month(), qd.day())

        self.result_data = MeasurementInput(
            measured_at=measured_at,
            height_cm=vals["height"],
            weight_kg=vals["weight"],
            waist_cm=vals["waist"],
            hip_cm=vals["hip"],
            neck_cm=vals["neck"],
            body_fat_percent=vals["bfp"],
            muscle_kg=vals["muscle"],
            water_percent=vals["water"],
            visceral_fat=vals["visceral"],
            notes=(self.ed_notes.toPlainText() or "").strip(),
        )
        self.accept()
