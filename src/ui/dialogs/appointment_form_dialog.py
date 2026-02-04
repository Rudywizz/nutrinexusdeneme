from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QDateEdit, QTimeEdit, QSpinBox, QTextEdit, QFrame
)
from PySide6.QtCore import Qt, QDate, QTime, QTimer
from PySide6.QtGui import QIcon

from src.ui.theme.win_titlebar import apply_light_titlebar

from src.ui.dialogs.themed_messagebox import ThemedMessageBox


def _ui_get(obj, key: str, default=""):
    """Robust getter for dict/sqlite3.Row/dataclass objects."""
    if obj is None:
        return default
    # dict-like
    if isinstance(obj, dict):
        return obj.get(key, default)
    # sqlite3.Row supports keys() and __getitem__
    try:
        if hasattr(obj, "keys"):
            ks = obj.keys()
            if key in ks:
                v = obj[key]
                return default if v is None else v
    except Exception:
        pass
    # attribute access (dataclass/service models)
    if hasattr(obj, key):
        v = getattr(obj, key, default)
        return default if v is None else v
    # common alias
    if key == "name" and hasattr(obj, "full_name"):
        v = getattr(obj, "full_name", default)
        return default if v is None else v
    if key == "full_name" and hasattr(obj, "name"):
        v = getattr(obj, "name", default)
        return default if v is None else v
    return default

@dataclass
class AppointmentFormResult:
    client_id: str
    starts_at: str           # "YYYY-MM-DD HH:MM:SS"
    duration_min: int
    title: str
    note: str
    phone: str
    status: str


class AppointmentFormDialog(QDialog):
    def __init__(self, parent=None, *, conn=None, log=None, appt_id=None, title: str = "Yeni Randevu", clients: list[dict] | None = None, initial: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        # Keep dialog background consistent with app (avoid black frameless backdrop).
        self.setStyleSheet("QDialog{background:#E9EEF2;}")
        self.setWindowIcon(QIcon('src/assets/icons/calendar.png'))
        QTimer.singleShot(0, lambda: apply_light_titlebar(self))
        self.setModal(True)
        self.setMinimumWidth(560)

        self.clients = clients or []
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

        # Danışan
        row_client = QVBoxLayout()
        row_client.addWidget(QLabel("Danışan"))
        self.cb_client = QComboBox()
        self.cb_client.setObjectName("Input")
        # store client_id in userData
        for c in self.clients:
            self.cb_client.addItem(_ui_get(c, "full_name", _ui_get(c, "name", "")), _ui_get(c, "id", ""))
        # initial
        init_cid = initial.get("client_id", "")
        if init_cid:
            idx = self.cb_client.findData(init_cid)
            if idx >= 0:
                self.cb_client.setCurrentIndex(idx)
        row_client.addWidget(self.cb_client)
        form.addLayout(row_client)

        # Tarih + Saat + Süre
        row_dt = QHBoxLayout()

        left = QVBoxLayout()
        left.addWidget(QLabel("Tarih"))
        self.ed_date = QDateEdit()
        self.ed_date.setObjectName("Input")
        self.ed_date.setCalendarPopup(True)
        self.ed_date.setDisplayFormat("dd/MM/yyyy")
        # Fix popup calendar header visibility + day names (theme sometimes hides it)
        try:
            cal = self.ed_date.calendarWidget()
            cal.setHorizontalHeaderFormat(cal.ShortDayNames)
            cal.setVerticalHeaderFormat(cal.NoVerticalHeader)
            # Light, consistent styling
            cal.setStyleSheet("""
                QCalendarWidget QWidget { background: #FFFFFF; color: #0F172A; }
                QCalendarWidget QToolButton { color: #0F172A; background: transparent; padding: 4px 8px; border-radius: 6px; }
                QCalendarWidget QToolButton:hover { background: rgba(15,23,42,0.06); }
                QCalendarWidget QAbstractItemView { selection-background-color: rgba(34,197,94,0.25); selection-color: #0F172A; }
                QCalendarWidget QHeaderView::section { color: #475569; background: #F8FAFC; border: 0px; padding: 4px; }
            """)
        except Exception:
            pass

        left.addWidget(self.ed_date)

        mid = QVBoxLayout()
        mid.addWidget(QLabel("Saat"))
        self.ed_time = QTimeEdit()
        self.ed_time.setObjectName("Input")
        self.ed_time.setDisplayFormat("HH:mm")
        self.ed_time.setTime(QTime.currentTime())
        mid.addWidget(self.ed_time)

        right = QVBoxLayout()
        right.addWidget(QLabel("Süre (dk)"))
        self.sp_duration = QSpinBox()
        self.sp_duration.setObjectName("Input")
        self.sp_duration.setRange(10, 240)
        self.sp_duration.setSingleStep(10)
        self.sp_duration.setValue(int(initial.get("duration_min") or 30))
        right.addWidget(self.sp_duration)

        row_dt.addLayout(left, 2)
        row_dt.addLayout(mid, 1)
        row_dt.addLayout(right, 1)
        form.addLayout(row_dt)

        # initial starts_at
        starts_at = (initial.get("starts_at") or "").strip()
        if starts_at:
            try:
                dt = datetime.strptime(starts_at, "%Y-%m-%d %H:%M:%S")
            except Exception:
                try:
                    dt = datetime.strptime(starts_at, "%Y-%m-%d %H:%M")
                except Exception:
                    dt = datetime.now()
            self.ed_date.setDate(QDate(dt.year, dt.month, dt.day))
            self.ed_time.setTime(QTime(dt.hour, dt.minute))
        else:
            self.ed_date.setDate(QDate.currentDate())

        # Başlık
        row_title = QVBoxLayout()
        row_title.addWidget(QLabel("Başlık / Konu"))
        self.ed_title = QLineEdit()
        self.ed_title.setObjectName("Input")
        self.ed_title.setPlaceholderText("Örn: Kontrol randevusu")
        self.ed_title.setText(initial.get("title",""))
        row_title.addWidget(self.ed_title)
        form.addLayout(row_title)

        # Telefon
        row_phone = QVBoxLayout()
        row_phone.addWidget(QLabel("Telefon"))
        self.ed_phone = QLineEdit()
        self.ed_phone.setObjectName("Input")
        row_phone.addWidget(self.ed_phone)
        # Mask: (05)xx xxx xx xx
        self.ed_phone.setInputMask("(\\0\\5)00 000 00 00;_")
        self.ed_phone.setPlaceholderText("(05)xx xxx xx xx")
        # prefill from initial or selected client
        init_phone = (initial.get("phone") or "").strip()
        if init_phone:
            # editing existing appointment
            self.ed_phone.setText(init_phone)
        else:
            # new appointment: prefix is literal in mask; start empty after (05)
            self.ed_phone.clear()
            self.ed_phone.setCursorPosition(4)

        form.addLayout(row_phone)



        # Durum
        row_status = QVBoxLayout()
        row_status.addWidget(QLabel("Durum"))
        self.cb_status = QComboBox()
        self.cb_status.setObjectName("Input")
        self.cb_status.addItems(["Planlandı", "Tamamlandı", "İptal"])
        init_status = initial.get("status","Planlandı")
        idxs = self.cb_status.findText(init_status)
        if idxs >= 0:
            self.cb_status.setCurrentIndex(idxs)
        row_status.addWidget(self.cb_status)
        form.addLayout(row_status)

        # Not
        row_note = QVBoxLayout()
        row_note.addWidget(QLabel("Not"))
        self.ed_note = QTextEdit()
        self.ed_note.setObjectName("Input")
        self.ed_note.setPlaceholderText("Kısa notlar (opsiyonel)...")
        self.ed_note.setPlainText(initial.get("note",""))
        self.ed_note.setFixedHeight(110)
        row_note.addWidget(self.ed_note)
        form.addLayout(row_note)

        root.addWidget(card)

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

        self.result_data: AppointmentFormResult | None = None

        self.ed_title.textChanged.connect(self._validate_form)
        self._validate_form()

    def _validate_form(self):
        # Client required + title at least 2 chars (can be empty? but better required)
        cid = self.cb_client.currentData()
        title = (self.ed_title.text() or "").strip()
        ok = bool(cid) and (len(title) >= 2)
        self.btn_save.setEnabled(ok)

    def _on_save(self):
        cid = self.cb_client.currentData()
        if not cid:
            ThemedMessageBox.warn(self, "Eksik Bilgi", "Lütfen bir danışan seçin.")
            return

        title = (self.ed_title.text() or "").strip()
        if len(title) < 2:
            ThemedMessageBox.warn(self, "Eksik Bilgi", "Lütfen başlık/konu girin (en az 2 karakter).")
            self.ed_title.setFocus()
            return

        qd = self.ed_date.date()
        qt = self.ed_time.time()
        starts_at = f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d} {qt.hour():02d}:{qt.minute():02d}:00"

        self.result_data = AppointmentFormResult(
            client_id=str(cid),
            starts_at=starts_at,
            duration_min=int(self.sp_duration.value()),
            title=title,
            note=(self.ed_note.toPlainText() or "").strip(),
            phone=(self.ed_phone.text() or "").strip(),
            status=self.cb_status.currentText(),
        )
        self.accept()