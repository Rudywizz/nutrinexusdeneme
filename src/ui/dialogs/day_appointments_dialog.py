from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, QDate, QTime, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (

    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox, QDateEdit, QDialogButtonBox,
    QScrollArea, QWidget, QFrame, QSizePolicy
)

from src.services.appointments_service import AppointmentsService
from src.services.clients_service import ClientsService
from src.ui.dialogs.appointment_form_dialog import AppointmentFormDialog
from src.ui.dialogs.themed_messagebox import ThemedMessageBox


@dataclass
class _Slot:
    dt: datetime
    label: str


class _ClickableRow(QFrame):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _ApptCard(QFrame):
    clicked = Signal(str)

    def __init__(self, ap: dict, parent=None):
        super().__init__(parent)
        self.ap = ap
        self.setObjectName("ApptCard")
        self.setCursor(Qt.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(8)

        t = QLabel(ap.get("starts_at", "")[11:16])
        t.setObjectName("ApptTime")
        t.setMinimumWidth(52)
        top.addWidget(t)

        name = QLabel(ap.get("client_name", ""))
        name.setObjectName("ApptClient")
        name.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        top.addWidget(name)

        status = QLabel(ap.get("status", ""))
        status.setObjectName("ApptStatus")
        top.addWidget(status)

        lay.addLayout(top)

        title = QLabel(ap.get("title", ""))
        title.setObjectName("ApptTitle")
        lay.addWidget(title)

        note = (ap.get("note") or "").strip()
        if note:
            n = QLabel(note)
            n.setObjectName("ApptNote")
            n.setWordWrap(True)
            lay.addWidget(n)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.ap.get("id"))
        super().mousePressEvent(event)



class _CopyDayDialog(QDialog):
    """Pick a target date to copy the whole day into."""

    def __init__(self, parent=None, *, from_day: QDate):
        super().__init__(parent)
        self.setWindowTitle("Güne Aktar")
        self.setModal(True)
        self.setMinimumWidth(380)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        lbl = QLabel("Hedef günü seç:")
        lbl.setObjectName("Label")
        root.addWidget(lbl)

        self.ed = QDateEdit()
        self.ed.setCalendarPopup(True)
        self.ed.setDisplayFormat("dd/MM/yyyy")
        self.ed.setDate(from_day.addDays(1))
        self.ed.setObjectName("Input")
        root.addWidget(self.ed)

        hint = QLabel("Not: Hedef günün boş olması önerilir.")
        hint.setObjectName("Hint")
        root.addWidget(hint)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Aktar")
        bb.button(QDialogButtonBox.Cancel).setText("Vazgeç")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def target_date(self) -> QDate:
        return self.ed.date()


class _ConfirmDialog(QDialog):
    def __init__(self, parent, title: str, message: str, ok_text: str = "Evet", cancel_text: str = "Vazgeç"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setStyleSheet("QDialog{background:#E9EEF2;} QLabel{color:#0F172A;} QPushButton{min-width:92px; padding:8px 14px; border-radius:10px;} QPushButton#Primary{background:#22C55E; color:#0B1220;} QPushButton#Primary:hover{background:#1FB454;} QPushButton#Ghost{background:#FFFFFF; border:1px solid rgba(15,23,42,0.10);} QPushButton#Ghost:hover{background:rgba(15,23,42,0.04);} ")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16,16,16,16)
        lay.setSpacing(12)
        lbl = QLabel(message)
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        btns = QHBoxLayout()
        btns.addStretch(1)
        b_cancel = QPushButton(cancel_text)
        b_cancel.setObjectName("Ghost")
        b_ok = QPushButton(ok_text)
        b_ok.setObjectName("Primary")
        b_cancel.clicked.connect(self.reject)
        b_ok.clicked.connect(self.accept)
        btns.addWidget(b_cancel)
        btns.addWidget(b_ok)
        lay.addLayout(btns)

def _confirm(parent, title: str, message: str, ok_text: str = "Evet", cancel_text: str = "Vazgeç") -> bool:
    return _ConfirmDialog(parent, title, message, ok_text=ok_text, cancel_text=cancel_text).exec() == QDialog.Accepted

class DayAppointmentsDialog(QDialog):
    """Seçili günün randevularını 'timeline' gibi gösteren detay ekranı."""

    def __init__(self, *, conn, log, day: QDate, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.log = log
        self.day = day
        self._changed = False
        self._selected_id: str | None = None

        self.svc = AppointmentsService(conn)
        self.clients_svc = ClientsService(conn)

        self.setWindowTitle("Günlük Randevular")
        self.setModal(True)
        self.resize(980, 620)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        # Header
        hdr = QHBoxLayout()
        self.lbl_title = QLabel(self._day_title())
        self.lbl_title.setObjectName("SectionTitle")
        hdr.addWidget(self.lbl_title)
        hdr.addStretch(1)

        self.btn_new = QPushButton("+ Yeni")
        self.btn_new.setObjectName("PrimaryButton")
        hdr.addWidget(self.btn_new)

        self.btn_edit = QPushButton("Düzenle")
        self.btn_edit.setEnabled(False)
        hdr.addWidget(self.btn_edit)

        self.btn_del = QPushButton("Sil")
        self.btn_del.setObjectName("DangerButton")
        self.btn_del.setEnabled(False)
        hdr.addWidget(self.btn_del)

        self.btn_del_all = QPushButton("Tümünü Sil")
        self.btn_del_all.setObjectName("DangerButton")
        hdr.addWidget(self.btn_del_all)

        self.btn_copy_day = QPushButton("Güne Taşı")
        hdr.addWidget(self.btn_copy_day)

        root.addLayout(hdr)

        # Timeline scroll
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)

        self.canvas = QWidget()
        self.canvas_lay = QVBoxLayout(self.canvas)
        self.canvas_lay.setContentsMargins(6, 6, 6, 6)
        self.canvas_lay.setSpacing(8)

        self.scroll.setWidget(self.canvas)
        root.addWidget(self.scroll, 1)

        # hint
        hint = QLabel("İpucu: Boş bir saat satırına tıkla → o saate yeni randevu. Kartı tıkla → seç. Çift tık → düzenle.")
        hint.setObjectName("Hint")
        root.addWidget(hint)

        # Wire
        self.btn_new.clicked.connect(lambda: self._new(prefill=None))
        self.btn_edit.clicked.connect(self._edit)
        self.btn_del.clicked.connect(self._delete)
        self.btn_del_all.clicked.connect(self._delete_day_all)
        self.btn_copy_day.clicked.connect(self._copy_day)

        self.refresh()

    def closeEvent(self, event):
        # If user performed CRUD operations, return Accepted so caller can refresh marks.
        try:
            if self._changed:
                self.accept()
        except Exception:
            pass
        super().closeEvent(event)

    def _day_title(self) -> str:
        py = datetime(self.day.year(), self.day.month(), self.day.day())
        months = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        weekdays = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
        return f"{py.day} {months[py.month]} {py.year} • {weekdays[py.weekday()]}"

    def _slots(self) -> list[_Slot]:
        # default clinic day window
        start_h, end_h = 8, 20
        step_min = 30
        base = datetime(self.day.year(), self.day.month(), self.day.day(), start_h, 0, 0)
        out: list[_Slot] = []
        t = base
        while t.hour < end_h or (t.hour == end_h and t.minute == 0):
            out.append(_Slot(dt=t, label=t.strftime("%H:%M")))
            t = t + timedelta(minutes=step_min)
        return out

    def _set_selected(self, appt_id: str | None):
        self._selected_id = appt_id
        ok = bool(appt_id)
        self.btn_edit.setEnabled(ok)
        self.btn_del.setEnabled(ok)

        # visual selection
        for i in range(self.canvas_lay.count()):
            w = self.canvas_lay.itemAt(i).widget()
            if not w:
                continue
            # rows are frames with children; mark cards
            for c in w.findChildren(QFrame, "ApptCard"):
                try:
                    if getattr(c, "ap", {}).get("id") == appt_id:
                        c.setProperty("selected", True)
                    else:
                        c.setProperty("selected", False)
                    c.style().unpolish(c)
                    c.style().polish(c)
                except Exception:
                    pass

    def refresh(self):
        d = self.day.toString("yyyy-MM-dd")
        items = self.svc.list_appointments(date_from=d, date_to=d)
        # group by HH:MM slot
        by_hm: dict[str, list[dict]] = {}
        for ap in items:
            hm = (ap.get("starts_at") or "")[11:16]
            by_hm.setdefault(hm, []).append(ap)

        # clear canvas
        while self.canvas_lay.count():
            it = self.canvas_lay.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

        self._set_selected(None)

        for slot in self._slots():
            row = _ClickableRow()
            row.setObjectName("TimeRow")
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(10, 8, 10, 8)
            row_lay.setSpacing(10)

            lbl = QLabel(slot.label)
            lbl.setObjectName("TimeLabel")
            lbl.setMinimumWidth(60)
            row_lay.addWidget(lbl)

            col = QVBoxLayout()
            col.setSpacing(6)

            # add cards for this slot
            aps = by_hm.get(slot.label, [])
            if aps:
                for ap in aps:
                    card = _ApptCard(ap)
                    card.clicked.connect(lambda apid, _=None: self._set_selected(apid))
                    # double click edit
                    card.mouseDoubleClickEvent = lambda ev, apid=ap.get("id"): (self._set_selected(apid), self._edit())
                    col.addWidget(card)
            else:
                empty = QLabel("—")
                empty.setObjectName("TimeEmpty")
                empty.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                col.addWidget(empty)

            row_lay.addLayout(col, 1)

            # click empty area creates appt
            row.clicked.connect(lambda s=slot.dt: self._new(prefill=s))
            self.canvas_lay.addWidget(row)

        self.canvas_lay.addStretch(1)

    def _load_clients(self) -> list[dict]:
        try:
            return self.clients_svc.list_clients(active_only=True)
        except Exception:
            return self.clients_svc.list_clients()

    def _new(self, prefill: datetime | None):
        clients = self._load_clients()
        if not clients:
            ThemedMessageBox.info(self, "Bilgi", "Önce en az 1 danışan eklemelisin.")
            return

        initial = {}
        if prefill:
            initial = {
                "starts_at": prefill.strftime("%Y-%m-%d %H:%M:%S"),
                "duration_min": 30,
                "status": "Planlandı",
            }

        dlg = AppointmentFormDialog(self, conn=self.conn, log=self.log, title="Yeni Randevu", clients=clients, initial=initial)
        if dlg.exec() != QDialog.Accepted:
            return

        try:
            data = dlg.result_data  # AppointmentFormResult
            self.svc.create_appointment(
                client_id=data.client_id,
                starts_at=data.starts_at,
                duration_min=data.duration_min,
                title=data.title,
                note=data.note,
                phone=data.phone,
                status=data.status,
            )
            self._changed = True
            self.refresh()
        except Exception as e:
            ThemedMessageBox.error(self, "Hata", f"Randevu eklenemedi.\n\n{e}")

    def _edit(self):
        appt_id = self._selected_id
        if not appt_id:
            return

        clients = self._load_clients()
        # fetch full record
        ap = self.svc.get_appointment(appt_id)
        if not ap:
            ThemedMessageBox.warn(self, "Uyarı", "Kayıt bulunamadı.")
            return

        # initial
        try:
            dt = datetime.strptime(ap.get("starts_at"), "%Y-%m-%d %H:%M:%S")
        except Exception:
            try:
                dt = datetime.strptime(ap.get("starts_at"), "%Y-%m-%d %H:%M")
            except Exception:
                dt = None

        initial = {
            "client_id": ap.get("client_id"),
            "date": QDate(dt.year, dt.month, dt.day) if dt else self.day,
            "time": QTime(dt.hour, dt.minute) if dt else QTime(9, 0),
            "duration_min": int(ap.get("duration_min") or 30),
            "status": ap.get("status") or "Planlandı",
            "title": ap.get("title") or "",
            "note": ap.get("note") or "",
            "phone": ap.get("phone") or "",
        }

        dlg = AppointmentFormDialog(self, conn=self.conn, log=self.log, title="Randevuyu Düzenle", clients=clients, initial=initial)
        if dlg.exec() != QDialog.Accepted:
            return

        try:
            data = dlg.result_data
            self.svc.update_appointment(
                appt_id,
                client_id=data.client_id,
                starts_at=data.starts_at,
                duration_min=data.duration_min,
                title=data.title,
                note=data.note,
                phone=data.phone,
                status=data.status,
            )
            self._changed = True
            self.refresh()
        except Exception as e:
            ThemedMessageBox.error(self, "Hata", f"Randevu güncellenemedi.\n\n{e}")

    def _delete(self):
        appt_id = self._selected_id
        if not appt_id:
            return

        if not _confirm(self, "Sil", "Seçili randevu silinsin mi?"):
            return

        try:
            self.svc.deactivate_appointment(appt_id)
            self._changed = True
            self.refresh()
        except Exception as e:
            ThemedMessageBox.error(self, "Hata", f"Randevu silinemedi.\n\n{e}")


    def _delete_day_all(self):
        date_iso = self.day.toString("yyyy-MM-dd")
        if not ThemedMessageBox.confirm(
            self,
            "Tümünü Sil",
            "Bu günün TÜM randevuları silinsin mi?\n\nBu işlem geri alınamaz (soft delete).",
            yes_text="Evet",
            no_text="Vazgeç",
        ):
            return
        try:
            n = self.svc.deactivate_day(date_iso)
            self._changed = True
            self.refresh()
            ThemedMessageBox.info(self, "Tamam", f"{n} randevu silindi.")
        except Exception as e:
            ThemedMessageBox.error(self, "Hata", f"Silme işlemi başarısız.\n\n{e}")

    def _copy_day(self):
        from_iso = self.day.toString("yyyy-MM-dd")
        # pick target date
        dlg = _CopyDayDialog(self, from_day=self.day)
        if dlg.exec() != QDialog.Accepted:
            return
        to_qd = dlg.target_date()
        to_iso = to_qd.toString("yyyy-MM-dd")
        if to_iso == from_iso:
            ThemedMessageBox.info(self, "Bilgi", "Hedef gün, kaynak gün ile aynı olamaz.")
            return

        # enforce empty target day
        existing = self.svc.list_appointments(date_from=to_iso, date_to=to_iso, query="")
        if existing:
            ThemedMessageBox.warn(
                self,
                "Hedef Gün Dolu",
                "Seçtiğin hedef günde zaten randevu var.\n\nLütfen boş bir gün seç.",
            )
            return

        try:
            moved = self.svc.move_day(from_date=from_iso, to_date=to_iso)
            self._changed = True
            self.refresh()
            ThemedMessageBox.info(self, "Tamam", f"{moved} randevu {to_qd.toString('dd/MM/yyyy')} gününe taşındı.")
        except Exception as e:
            ThemedMessageBox.error(self, "Hata", f"Aktarma işlemi başarısız.\n\n{e}")
