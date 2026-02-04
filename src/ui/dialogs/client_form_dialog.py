from __future__ import annotations
from src.ui.theme.win_titlebar import apply_light_titlebar
from src.ui.widgets.custom_titlebar import CustomTitleBar

from dataclasses import dataclass
from datetime import date
import re

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QDateEdit, QCalendarWidget, QFrame, QMessageBox
)
from PySide6.QtCore import Qt, QDate, QRegularExpression, QTimer
from PySide6.QtGui import QRegularExpressionValidator, QFont, QPixmap, QIcon


@dataclass
class ClientFormResult:
    full_name: str
    phone: str
    birth_date: str  # YYYY-MM-DD
    gender: str


class ClientFormDialog(QDialog):
    def __init__(self, parent=None, *, title: str = "Yeni Danışan", initial: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        try:
            self.setWindowFlag(Qt.FramelessWindowHint, True)
        except Exception:
            pass
        self.setWindowIcon(QIcon('src/assets/icons/clients.png'))
        QTimer.singleShot(0, lambda: apply_light_titlebar(self))
        self.setModal(True)
        self.setMinimumWidth(520)

        initial = initial or {}

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        header = QLabel(title)
        header.setObjectName("DialogTitle")
        root.addWidget(header)

        card = QFrame()
        card.setObjectName("Card")
        form = QVBoxLayout(card)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(10)

        # Ad Soyad
        row1 = QVBoxLayout()
        row1.addWidget(QLabel("Ad Soyad"))
        self.ed_name = QLineEdit()
        self.ed_name.setObjectName("Input")
        self.ed_name.setPlaceholderText("Örn: Ayşe Yılmaz")
        self.ed_name.setText(initial.get("name", ""))
        row1.addWidget(self.ed_name)
        form.addLayout(row1)
        # Telefon (TR GSM) — "05" sabit + 9 rakam
        row2 = QVBoxLayout()
        row2.addWidget(QLabel("Telefon"))

        phone_row = QHBoxLayout()

        self.lbl_phone_prefix = QLabel("05")
        self.lbl_phone_prefix.setObjectName("PhonePrefix")
        self.lbl_phone_prefix.setAlignment(Qt.AlignCenter)
        phone_row.addWidget(self.lbl_phone_prefix)

        self.ed_phone_rest = QLineEdit()
        self.ed_phone_rest.setObjectName("Input")
        # 9 rakam: xx xxx xx xx (2+3+2+2)
        self.ed_phone_rest.setInputMask("00 000 00 00;_")
        self.ed_phone_rest.setPlaceholderText("__ ___ __ __")
        phone_row.addWidget(self.ed_phone_rest, 1)

        row2.addLayout(phone_row)

        # initial phone
        initial_phone = (initial.get("phone", "") or "").strip()
        digits = "".join([c for c in initial_phone if c.isdigit()])
        if digits.startswith("05") and len(digits) >= 2:
            rest = digits[2:11]
        else:
            rest = digits[:9]
        rest = (rest or "")[:9]
        self.ed_phone_rest.setText(rest)

        self.ed_phone_rest.textChanged.connect(self._validate_form)

        form.addLayout(row2)


        # Doğum Tarihi + Cinsiyet
        row3 = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel("Doğum Tarihi"))
        self.dt_birth = QDateEdit()
        self.dt_birth.setObjectName("Input")
        self.dt_birth.setCalendarPopup(True)
        self.dt_birth.setDisplayFormat("dd/MM/yyyy")
        # Calendar popup görünümü: bazı Windows tema/font kombinasyonlarında gün rakamları '...' gibi elide olabiliyor.
        # Popup takvimi yeterli minimum boyuta çekip fontu sabitleyelim.
        try:
            cal = self.dt_birth.calendarWidget()
            cal.setObjectName("CalendarPopup")
            cal.setGridVisible(True)
            cal.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
            cal.setHorizontalHeaderFormat(QCalendarWidget.ShortDayNames)
            cal.setMinimumSize(340, 260)
            cal.setFont(QFont("Arial", 9))
        except Exception:
            pass


        # initial birth date
        b = initial.get("dob")
        if b:
            try:
                y, m, d = [int(x) for x in b.split("-")]
                self.dt_birth.setDate(QDate(y, m, d))
            except Exception:
                self.dt_birth.setDate(QDate.currentDate())
        else:
            self.dt_birth.setDate(QDate.currentDate())
        left.addWidget(self.dt_birth)

        right = QVBoxLayout()
        right.addWidget(QLabel("Cinsiyet"))
        self.cb_gender = QComboBox()
        self.cb_gender.setObjectName("Input")
        self.cb_gender.addItems(["Kadın", "Erkek", "Diğer"])
        g = initial.get("gender")
        if g:
            idx = self.cb_gender.findText(g)
            if idx >= 0:
                self.cb_gender.setCurrentIndex(idx)
        right.addWidget(self.cb_gender)

        row3.addLayout(left, 2)
        row3.addLayout(right, 1)
        form.addLayout(row3)

        root.addWidget(card)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_cancel = QPushButton("Vazgeç")
        self.btn_cancel.setObjectName("SecondaryBtn")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton("Kaydet")
        self.btn_save.setObjectName("PrimaryBtn")
        self.btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_save)
        root.addLayout(btn_row)

        self.result_data: ClientFormResult | None = None

        # Live validation
        self.ed_name.textChanged.connect(self._validate_form)
        self.ed_phone_rest.textChanged.connect(self._validate_form)
        self._validate_form()


    def _validate_form(self):
        name = (self.ed_name.text() or "").strip()
        rest = (self.ed_phone_rest.text() or "")
        rest_digits = "".join([c for c in rest if c.isdigit()])
        phone = "05" + rest_digits
        # Not: raw string içinde "\\d" yazarsak regex'e kelimesi kelimesine "\d" gider.
        # Bizim istediğimiz 05 + 9 rakam olduğu için doğru desen: r"05\d{9}".
        ok = (len(name) >= 3) and bool(re.fullmatch(r"05\d{9}", phone))
        self.btn_save.setEnabled(ok)

    def _on_save(self):
        """Form doğrulaması + sonucu üst pencereye döndür."""
        name = (self.ed_name.text() or "").strip()
        rest = (self.ed_phone_rest.text() or "")
        rest_digits = "".join([c for c in rest if c.isdigit()])
        phone = "05" + rest_digits
        gender = self.cb_gender.currentText()

        qd = self.dt_birth.date()
        birth_date = f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"

        if len(name) < 3:
            QMessageBox.warning(self, "Eksik Bilgi", "Lütfen Ad Soyad alanını doldurun (en az 3 karakter).")
            self.ed_name.setFocus()
            return

        if not re.fullmatch(r"05\d{9}", phone):
            QMessageBox.warning(self, "Geçersiz Telefon", "Telefon 05XXXXXXXXX formatında olmalıdır (11 hane).")
            self.ed_phone_rest.setFocus()
            return

        self.result_data = ClientFormResult(
            full_name=name,
            phone=phone,
            birth_date=birth_date,
            gender=gender,
        )
        self.accept()