from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, QLineEdit,
    QCalendarWidget, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox
)
from PySide6.QtGui import QTextCharFormat, QFont, QPalette
from PySide6.QtCore import Qt, QDate, QEvent

from PySide6.QtGui import QPainter, QColor, QPen, QBrush
from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QTableView, QToolTip, QStyledItemDelegate, QAbstractItemView
from PySide6.QtWidgets import QStyleOptionViewItem
from PySide6.QtWidgets import QStyle


class _CalendarBadgeDelegate(QStyledItemDelegate):
    """Draw corner badge counts on QCalendarWidget's internal month view table."""

    def __init__(self, cal: 'PremiumCalendar'):
        super().__init__(cal)
        self.cal = cal

    def _index_to_date(self, index) -> QDate | None:
        """Map month-view grid cell to a real QDate.

        We cannot rely on DisplayRole day number alone because the grid includes
        previous/next month overflow days (e.g. the first row can show 29/30/31).
        The reliable mapping is: compute the first visible date in the grid from
        the shown year/month and the calendar's firstDayOfWeek, then add the cell
        offset (row*7+col).
        """

        if not index.isValid():
            return None

        shown = QDate(self.cal.yearShown(), self.cal.monthShown(), 1)
        if not shown.isValid():
            return None

        fdw_enum = self.cal.firstDayOfWeek()  # Qt.DayOfWeek
        try:
            fdw = fdw_enum.value  # PySide6 enum -> 1..7
        except Exception:
            fdw = int(getattr(fdw_enum, 'value', 1))
        # QDate.dayOfWeek(): 1=Mon..7=Sun
        offset = (shown.dayOfWeek() - fdw + 7) % 7
        start = shown.addDays(-offset)
        r = index.row()
        if r == 0:
            return None
        r_adj = r - 1
        return start.addDays(r_adj * 7 + index.column())

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        # Avoid the default blue focus rectangle (Windows style) which looks like a bug.
        opt = QStyleOptionViewItem(option)
        opt.state = opt.state & ~QStyle.State_HasFocus
        super().paint(painter, opt, index)

        try:
            qd = self._index_to_date(index)
        except Exception:
            return super().paint(painter, option, index)
        if not qd or not qd.isValid():
            return

        key = qd.toString("yyyy-MM-dd")
        cnt = int(self.cal._counts.get(key, 0) or 0)

        # Today subtle border
        if qd == QDate.currentDate():
            hl = self.cal.palette().color(QPalette.ColorRole.Highlight)
            pen = QPen(hl)
            pen.setWidth(2)
            painter.save()
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            r = opt.rect.adjusted(2, 2, -2, -2)
            painter.drawRoundedRect(r, 6, 6)
            painter.restore()

        if cnt <= 0:
            return

        # Badge top-right
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        hl = self.cal.palette().color(QPalette.ColorRole.Highlight)
        fill = hl.darker(115)

        size = 18
        x = opt.rect.x() + opt.rect.width() - size - 6
        y = opt.rect.y() + 6
        badge_rect = QRect(x, y, size, size)

        # Border uses Base color for contrast
        border = self.cal.palette().color(QPalette.ColorRole.Base)
        painter.setPen(QPen(border, 1))
        painter.setBrush(QBrush(fill))
        painter.drawEllipse(badge_rect)

        painter.setPen(QPen(QColor(255, 255, 255)))
        f = painter.font()
        f.setPointSize(max(8, f.pointSize() - 1))
        f.setBold(True)
        painter.setFont(f)

        label = str(cnt) if cnt < 10 else "9+"
        painter.drawText(badge_rect, Qt.AlignCenter, label)
        painter.restore()


class PremiumCalendar(QCalendarWidget):
    """Kurumsal, vitrin takvim.

    - Gün köşesinde randevu sayısı badge
    - Bugün için ince vurgu çerçevesi
    - Hover tooltip: o günün ilk birkaç randevusu
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._counts: dict[str, int] = {}   # key: yyyy-MM-dd -> count
        self._tooltips: dict[str, str] = {} # key: yyyy-MM-dd -> tooltip text

        # Calendar içindeki tabloyu yakalayıp tooltip/hovers için eventFilter bağlarız
        # QCalendarWidget's internal month view is a QTableView in most Qt builds.
        # Some styles/builds nest it deeper or use different class names; we search robustly.
        self._table: QTableView | None = self.findChild(QTableView, "qt_calendar_calendarview")
        if not self._table:
            views = self.findChildren(QTableView)
            self._table = views[0] if views else None
        if not self._table:
            # Last resort
            views2 = self.findChildren(QAbstractItemView)
            self._table = views2[0] if views2 else None
        
        if self._table:
            self._table.setMouseTracking(True)
            self._table.viewport().setMouseTracking(True)
            self._table.viewport().installEventFilter(self)
            # Badge painting via delegate (reliable across styles)
            self._table.setItemDelegate(_CalendarBadgeDelegate(self))
        

    def set_month_data(self, *, counts: dict[str, int], tooltips: dict[str, str]):
        self._counts = counts or {}
        self._tooltips = tooltips or {}
        self.updateCells()

    def _key(self, date: QDate) -> str:
        return date.toString("yyyy-MM-dd")

    def _index_to_date(self, index) -> QDate | None:
        """Map month-view grid cell to a real QDate (used for tooltips)."""
        if not index or not index.isValid():
            return None

        shown = QDate(self.yearShown(), self.monthShown(), 1)
        if not shown.isValid():
            return None

        fdw_enum = self.firstDayOfWeek()
        try:
            fdw = fdw_enum.value
        except Exception:
            fdw = int(getattr(fdw_enum, 'value', 1))
        offset = (shown.dayOfWeek() - fdw + 7) % 7
        start = shown.addDays(-offset)
        r = index.row()
        if r == 0:
            return None
        r_adj = r - 1
        return start.addDays(r_adj * 7 + index.column())
    def eventFilter(self, obj, event):
        if event.type() == QEvent.ToolTip and self._table and obj is self._table.viewport():
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            idx = self._table.indexAt(pos)
            if idx.isValid():
                qd = self._index_to_date(idx)
                if qd and qd.isValid():
                    key = self._key(qd)
                    tip = self._tooltips.get(key, "")
                    if tip:
                        QToolTip.showText(event.globalPos(), tip, self)
                        return True
            QToolTip.hideText()
            return True
        return super().eventFilter(obj, event)

    def paintCell(self, painter: QPainter, rect, date: QDate):
        """Keep default cell paint.

        We draw badges via a delegate on the internal month view table. This avoids
        style-specific rendering issues and prevents double-painting.
        """
        super().paintCell(painter, rect, date)
        return


from src.services.appointments_service import AppointmentsService
from src.ui.dialogs.themed_messagebox import ThemedMessageBox
from src.ui.dialogs.appointment_form_dialog import AppointmentFormDialog
from src.ui.dialogs.day_appointments_dialog import DayAppointmentsDialog


class AppointmentsScreen(QWidget):
    """Sprint 6.0.1 — Randevularım (Takvim Vitrini)

    - Ana görünüm: Ay takvimi + sağ panel (seçili gün randevuları)
    - Güne çift tık: Gün detayı ekranı (timeline / CRUD)
    - Çalışan modüllere dokunmadan sadece randevu vitrini güçlendirilir.
    """

    def __init__(self, *, conn, log):
        super().__init__()
        self.conn = conn
        self.log = log
        self.svc = AppointmentsService(conn)

        root = QVBoxLayout(self)

        # Title row
        title_row = QHBoxLayout()
        title = QLabel("Randevularım")
        title.setObjectName("PageTitle")
        title_row.addWidget(title)
        title_row.addStretch(1)

        self.btn_new = QPushButton("+ Yeni Randevu")
        self.btn_new.setObjectName("PrimaryButton")
        title_row.addWidget(self.btn_new)

        root.addLayout(title_row)

        # Main body
        body = QHBoxLayout()
        root.addLayout(body, 1)

        # Left: Calendar panel
        left = QFrame()
        left.setObjectName("Card")
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(14, 14, 14, 14)
        left_lay.setSpacing(10)

        self.calendar = PremiumCalendar()
        self.calendar.setGridVisible(True)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.calendar.setNavigationBarVisible(True)
        self.calendar.setFirstDayOfWeek(Qt.Monday)
        left_lay.addWidget(self.calendar, 1)

        hint = QLabel("İpucu: Bir güne tıkla → sağda o günün randevuları gelir. Güne çift tıkla → Gün Detayı.")
        hint.setObjectName("HintText")
        hint.setWordWrap(True)
        left_lay.addWidget(hint)

        body.addWidget(left, 3)

        # Right: Day detail panel
        right = QFrame()
        right.setObjectName("Card")
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(14, 14, 14, 14)
        right_lay.setSpacing(10)

        header = QHBoxLayout()
        self.lbl_day = QLabel("")
        self.lbl_day.setObjectName("SectionTitle")
        header.addWidget(self.lbl_day)
        header.addStretch(1)

        self.btn_day_detail = QPushButton("Gün Detayı")
        header.addWidget(self.btn_day_detail)
        right_lay.addLayout(header)

        # Search within the day (title/note/client)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Bu gün içinde ara… (danışan / başlık / not)")
        self.search.setObjectName("Input")
        right_lay.addWidget(self.search)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Saat", "Danışan", "Başlık", "Süre", "Durum"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setAlternatingRowColors(True)
        right_lay.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.btn_edit = QPushButton("Düzenle")
        self.btn_del = QPushButton("Sil")
        self.btn_del.setObjectName("DangerButton")
        actions.addWidget(self.btn_edit)
        actions.addWidget(self.btn_del)
        actions.addStretch(1)
        right_lay.addLayout(actions)

        body.addWidget(right, 4)

        # Signals
        self.btn_new.clicked.connect(self._new)
        self.btn_day_detail.clicked.connect(self._open_day_detail)
        self.calendar.selectionChanged.connect(self._refresh_day_panel)
        self.calendar.currentPageChanged.connect(lambda y, m: self._refresh_month_marks(y, m))
        self.search.textChanged.connect(lambda _: self._refresh_day_panel())
        self.btn_edit.clicked.connect(self._edit)
        self.btn_del.clicked.connect(self._delete)
        self.table.itemDoubleClicked.connect(lambda *_: self._edit())
        self.calendar.activated.connect(lambda d: self._open_day_detail())  # double click/enter
        # Also handle a true double click on the calendar cells:
        self.calendar.clicked.connect(lambda *_: None)

        # Initial load
        today = QDate.currentDate()
        self.calendar.setSelectedDate(today)
        self._refresh_month_marks(today.year(), today.month())
        self._refresh_day_panel()

    def _selected_id(self) -> str | None:
        r = self.table.currentRow()
        if r < 0:
            return None
        it = self.table.item(r, 0)
        return it.data(Qt.UserRole) if it else None

    def _day_key(self) -> str:
        return self.calendar.selectedDate().toString("yyyy-MM-dd")

    def _fmt_day_title(self, d: QDate) -> str:
        # Turkish-ish, consistent UI
        py = datetime(d.year(), d.month(), d.day())
        months = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        weekdays = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
        return f"{py.day} {months[py.month]} {py.year} • {weekdays[py.weekday()]}"

    def _refresh_month_marks(self, year: int, month: int):
        """Update premium calendar decorations for the visible month."""
        counts = self.svc.counts_by_day(year=year, month=month)
        tooltips = self.svc.tooltips_by_day(year=year, month=month, max_items=5)
        self.calendar.set_month_data(counts=counts, tooltips=tooltips)

    def _refresh_day_panel(self):
        d = self.calendar.selectedDate()
        self.lbl_day.setText(self._fmt_day_title(d))

        date_key = d.toString("yyyy-MM-dd")
        q = (self.search.text() or "").strip()

        items = self.svc.list_appointments(date_from=date_key, date_to=date_key, query=q)

        self.table.setRowCount(0)
        for ap in items:
            r = self.table.rowCount()
            self.table.insertRow(r)

            time_txt = (ap.get("starts_at") or "")[11:16]
            it0 = QTableWidgetItem(time_txt)
            it0.setData(Qt.UserRole, ap.get("id"))
            self.table.setItem(r, 0, it0)
            self.table.setItem(r, 1, QTableWidgetItem(ap.get("client_name") or ""))
            self.table.setItem(r, 2, QTableWidgetItem(ap.get("title") or ""))
            self.table.setItem(r, 3, QTableWidgetItem(str(ap.get("duration_min") or "")))
            self.table.setItem(r, 4, QTableWidgetItem(ap.get("status") or ""))

        has = self.table.rowCount() > 0
        self.btn_edit.setEnabled(has)
        self.btn_del.setEnabled(has)
        self.btn_day_detail.setEnabled(True)

    def _new(self):
        # Load clients and create via service (UI should not write DB directly)
        from src.services.clients_service import ClientsService
        clients_ui = [c.to_ui_dict() for c in ClientsService(self.conn).list_clients(only_active=True)]

        sel = self.calendar.selectedDate()
        init = {"starts_at": f"{sel.toString('yyyy-MM-dd')} {datetime.now().strftime('%H:%M')}:00"}
        dlg = AppointmentFormDialog(parent=self, title="Yeni Randevu", clients=clients_ui, initial=init)
        if dlg.exec() and dlg.result_data:
            self.svc.create_appointment(
                client_id=dlg.result_data.client_id,
                starts_at=dlg.result_data.starts_at,
                duration_min=dlg.result_data.duration_min,
                title=dlg.result_data.title,
                note=dlg.result_data.note,
                phone=dlg.result_data.phone,
                status=dlg.result_data.status,
            )
            self._refresh_month_marks(sel.year(), sel.month())
            self._refresh_day_panel()

    def _edit(self):
        appt_id = self._selected_id()
        if not appt_id:
            return
        ap = self.svc.get_appointment(appt_id)
        if not ap:
            QMessageBox.warning(self, "Randevu", "Randevu bulunamadı.")
            return

        from src.services.clients_service import ClientsService
        clients_ui = [c.to_ui_dict() for c in ClientsService(self.conn).list_clients(only_active=True)]
        init = {
            "client_id": ap.client_id,
            "starts_at": ap.starts_at,
            "duration_min": ap.duration_min,
            "title": ap.title,
            "note": ap.note,
            "phone": getattr(ap, "phone", ""),
            "status": ap.status,
        }
        dlg = AppointmentFormDialog(parent=self, title="Randevu Düzenle", clients=clients_ui, initial=init)
        if dlg.exec() and dlg.result_data:
            self.svc.update_appointment(
                appt_id,
                client_id=dlg.result_data.client_id,
                starts_at=dlg.result_data.starts_at,
                duration_min=dlg.result_data.duration_min,
                title=dlg.result_data.title,
                note=dlg.result_data.note,
                phone=dlg.result_data.phone,
                status=dlg.result_data.status,
            )
            sel = self.calendar.selectedDate()
            self._refresh_month_marks(sel.year(), sel.month())
            self._refresh_day_panel()

    def _delete(self):
        appt_id = self._selected_id()
        if not appt_id:
            return
        if ThemedMessageBox.confirm(self, "Sil", "Bu randevuyu silmek istiyor musun?") != QMessageBox.Yes:
            return
        self.svc.deactivate_appointment(appt_id)
        sel = self.calendar.selectedDate()
        self._refresh_month_marks(sel.year(), sel.month())
        self._refresh_day_panel()

    def _open_day_detail(self):
        d = self.calendar.selectedDate()
        dlg = DayAppointmentsDialog(conn=self.conn, log=self.log, day=d, parent=self)
        if dlg.exec():
            self._refresh_month_marks(d.year(), d.month())
            self._refresh_day_panel()