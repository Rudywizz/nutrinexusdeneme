from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView,
    QSplitter, QFormLayout, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont

from src.services.measurements_service import MeasurementsService
from src.ui.dialogs.measurement_dialog import MeasurementDialog
from src.app.utils.dates import format_tr_date


class MeasurementsScreen(QWidget):
    measurements_changed = Signal()

    def __init__(self, conn, client_id: str, log):
        super().__init__()
        # Used for QSS scoping (so we can make this table more readable without affecting other tables)
        self.setObjectName("MeasurementsScreen")
        self.conn = conn
        self.client_id = client_id
        self.log = log
        self.svc = MeasurementsService(conn)
        # cached during refresh() so we can show "Son ölçüm" chip in the detail panel
        self._latest_id = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame(objectName="Card")
        v = QVBoxLayout(card)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(10)

        # Header
        header = QHBoxLayout()
        title = QLabel("Ölçümler", objectName="CardTitle")
        header.addWidget(title)
        header.addStretch(1)

        self.btn_add = QPushButton("+ Ölçüm Ekle", objectName="PrimaryBtn")
        self.btn_edit = QPushButton("Düzenle", objectName="SecondaryBtn")
        self.btn_delete = QPushButton("Sil", objectName="DangerBtn")

        header.addWidget(self.btn_add)
        header.addWidget(self.btn_edit)
        header.addWidget(self.btn_delete)
        v.addLayout(header)

        # Split view: table (left) + detail (right)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        # --- Table ---
        self.table = QTableWidget(0, 12)
        self.table.setObjectName("MeasurementsTable")
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(self.table.SelectionMode.SingleSelection)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(38)

        self.table.setHorizontalHeaderLabels([
            "Tarih", "Boy", "Kilo", "BMI", "Bel", "Kalça",
            "Boyun", "Yağ %", "Kas (kg)", "Su %", "V. Yağ", "Not"
        ])

        hdr = self.table.horizontalHeader()
        hdr.setDefaultAlignment(Qt.AlignVCenter | Qt.AlignCenter)
        # Readability-first sizing: fixed comfortable widths + horizontal scroll
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        widths = {
            0: 100,  # Tarih
            1: 60,   # Boy
            2: 70,   # Kilo
            3: 60,   # BMI
            4: 55,   # Bel
            5: 55,   # Kalça
            6: 70,   # Boyun (ensure header fully fits)
            7: 60,   # Yağ %
            8: 70,   # Kas
            9: 55,   # Su %
            10: 60,  # V. Yağ
            11: 260  # Not
        }
        for c, w in widths.items():
            self.table.setColumnWidth(c, w)
        hdr.setStretchLastSection(True)

        # Make the table expand (so more rows are visible)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Action state follows selection
        self.table.currentCellChanged.connect(lambda *_: self._update_action_state())
        self.table.currentCellChanged.connect(lambda *_: self._sync_detail())

        # --- Left: measurements table inside a card (premium look) ---
        self.table_card = QFrame()
        self.table_card.setObjectName("TableCard")
        tl = QVBoxLayout(self.table_card)
        tl.setContentsMargins(14, 12, 14, 14)
        tl.setSpacing(10)

        header = QHBoxLayout()
        t_title = QLabel("Tüm Ölçümler")
        t_title.setObjectName("TableTitle")
        header.addWidget(t_title)
        header.addStretch(1)

        self.chip_count = QLabel("0 kayıt")
        self.chip_count.setObjectName("DetailChip")
        header.addWidget(self.chip_count)

        self.chip_last = QLabel("—")
        self.chip_last.setObjectName("DetailChip")
        header.addWidget(self.chip_last)

        tl.addLayout(header)
        tl.addWidget(self.table)

        self.splitter.addWidget(self.table_card)

        # --- Detail panel ---
        self.detail = QFrame()
        self.detail.setObjectName("Card")
        self.detail.setMinimumWidth(280)

        dv = QVBoxLayout(self.detail)
        dv.setContentsMargins(14, 14, 14, 14)
        dv.setSpacing(8)

        # Header bar (title + chips)
        header_bar = QHBoxLayout()
        title = QLabel("Ölçüm Bilgileri")
        title.setObjectName("DetailTitle")
        header_bar.addWidget(title)
        header_bar.addStretch(1)

        self.chip_latest = QLabel("Son ölçüm")
        self.chip_latest.setObjectName("DetailChipSuccess")
        self.chip_latest.setVisible(False)
        header_bar.addWidget(self.chip_latest)

        self.chip_date = QLabel("—")
        self.chip_date.setObjectName("DetailChip")
        header_bar.addWidget(self.chip_date)

        dv.addLayout(header_bar)

        # Key/Value rows in a compact list
        self._detail_labels = {}
        self._kv_rows = []

        def add_kv(label: str, key: str):
            row = QWidget()
            row.setObjectName("KVRow")
            hl = QHBoxLayout(row)
            hl.setContentsMargins(10, 8, 10, 8)
            hl.setSpacing(10)
            k = QLabel(label)
            k.setObjectName("KVKey")
            v = QLabel("—")
            v.setObjectName("KVValue")
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            hl.addWidget(k)
            hl.addStretch(1)
            hl.addWidget(v)
            self._detail_labels[key] = v
            self._kv_rows.append(row)
            dv.addWidget(row)

        add_kv("Tarih", "measured_at")
        add_kv("Boy", "height_cm")
        add_kv("Kilo", "weight_kg")
        add_kv("BMI", "bmi")
        add_kv("Bel", "waist_cm")
        add_kv("Kalça", "hip_cm")
        add_kv("Boyun", "neck_cm")
        add_kv("Yağ %", "body_fat_percent")
        add_kv("Kas (kg)", "muscle_kg")
        add_kv("Su %", "water_percent")
        add_kv("Visseral Yağ", "visceral_fat")

        dv.addStretch(1)



        self.splitter.addWidget(self.detail)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)

        v.addWidget(self.splitter, 1)
        layout.addWidget(card, 1)

        # Actions
        self.btn_add.clicked.connect(self.add_measurement)
        self.btn_edit.clicked.connect(self.edit_measurement)
        self.btn_delete.clicked.connect(self.delete_measurement)

        self.refresh()

    def _update_action_state(self):
        has_sel = self.table.currentRow() >= 0
        self.btn_edit.setEnabled(has_sel)
        self.btn_delete.setEnabled(has_sel)

    def _fmt(self, v, fmt: str = None):
        if v is None or v == "":
            return "—"
        if fmt:
            try:
                return fmt.format(v)
            except Exception:
                pass
        return str(v)

    def _make_badge_icon(self, text: str = "SON") -> QIcon:
        """Create a tiny rounded 'badge' icon (no external assets)."""
        w, h = 42, 18
        pm = QPixmap(w, h)
        pm.fill(Qt.transparent)

        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)

        bg = QColor(102, 179, 90)      # theme green
        fg = QColor(12, 42, 51)        # deep text

        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(0, 0, w, h, 9, 9)

        f = QFont()
        f.setBold(True)
        f.setPointSize(9)
        p.setFont(f)
        p.setPen(fg)
        p.drawText(pm.rect(), Qt.AlignCenter, text)
        p.end()

        return QIcon(pm)

    def _sync_detail(self):
        r = self.table.currentRow()
        if r < 0:
            for k, lbl in self._detail_labels.items():
                lbl.setText("—")
            self.chip_date.setText("—")
            self.chip_latest.setVisible(False)
            return

        # Determine if selected measurement is the latest
        sel_id = None
        it0 = self.table.item(r, 0)
        if it0 is not None:
            sel_id = it0.data(Qt.UserRole)
        is_latest = (self._latest_id is not None and sel_id == self._latest_id)
        self.chip_latest.setVisible(bool(is_latest))

        # Read values from the selected row (fast, no extra DB)
        def item_text(col):
            it = self.table.item(r, col)
            return it.text() if it else ""

        self._detail_labels["measured_at"].setText(item_text(0) or "—")
        self.chip_date.setText(item_text(0) or "—")
        self._detail_labels["height_cm"].setText(self._fmt(item_text(1)))
        self._detail_labels["weight_kg"].setText(self._fmt(item_text(2)))
        self._detail_labels["bmi"].setText(self._fmt(item_text(3)))
        self._detail_labels["waist_cm"].setText(self._fmt(item_text(4)))
        self._detail_labels["hip_cm"].setText(self._fmt(item_text(5)))
        self._detail_labels["neck_cm"].setText(self._fmt(item_text(6)))
        self._detail_labels["body_fat_percent"].setText(self._fmt(item_text(7)))
        self._detail_labels["muscle_kg"].setText(self._fmt(item_text(8)))
        self._detail_labels["water_percent"].setText(self._fmt(item_text(9)))
        self._detail_labels["visceral_fat"].setText(self._fmt(item_text(10)))

    def refresh(self):
        rows = self.svc.list_for_client(self.client_id)
        self.table.setRowCount(0)

        # Identify the latest measurement ("Son ölçüm") so we can visually highlight it.
        latest_id = None
        try:
            if rows:
                latest_id = max(rows, key=lambda x: x.measured_at).id
        except Exception:
            latest_id = None

        # cache for detail panel chips
        self._latest_id = latest_id

        badge_icon = self._make_badge_icon("SON") if latest_id is not None else None

        for m in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)

            date_txt = format_tr_date(m.measured_at)
            it0 = QTableWidgetItem(date_txt)
            it0.setData(Qt.UserRole, m.id)
            it0.setTextAlignment(Qt.AlignVCenter | Qt.AlignCenter)
            if date_txt:
                it0.setToolTip(date_txt)

            # Highlight latest measurement row with a badge + slightly stronger typography.
            is_latest = (latest_id is not None and m.id == latest_id)
            if is_latest and badge_icon is not None:
                it0.setIcon(badge_icon)
                it0.setToolTip(f"Son ölçüm • {date_txt}")

            self.table.setItem(r, 0, it0)

            # Fill all measurement fields
            def setc(col, val, align=Qt.AlignVCenter | Qt.AlignRight):
                s = "" if val is None else str(val)
                it = QTableWidgetItem(s)
                it.setTextAlignment(align)
                if s:
                    it.setToolTip(s)
                # Apply the same highlight styling across the entire row for the latest measurement.
                if latest_id is not None and m.id == latest_id:
                    # slightly stronger text for the "Son ölçüm" row
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                    it.setBackground(QColor(46, 125, 50, 24))  # subtle green tint
                self.table.setItem(r, col, it)

            setc(1, "" if m.height_cm is None else f"{m.height_cm:.0f}")
            setc(2, "" if m.weight_kg is None else f"{m.weight_kg:.1f}")

            bmi = m.bmi()
            setc(3, "" if bmi is None else f"{bmi:.1f}")

            setc(4, "" if m.waist_cm is None else f"{m.waist_cm:.0f}")
            setc(5, "" if m.hip_cm is None else f"{m.hip_cm:.0f}")
            setc(6, "" if m.neck_cm is None else f"{m.neck_cm:.0f}")

            setc(7, "" if m.body_fat_percent is None else f"{m.body_fat_percent:.1f}")
            setc(8, "" if m.muscle_kg is None else f"{m.muscle_kg:.1f}")
            setc(9, "" if m.water_percent is None else f"{m.water_percent:.1f}")
            setc(10, "" if m.visceral_fat is None else f"{m.visceral_fat:.1f}" if isinstance(m.visceral_fat, (int,float)) else str(m.visceral_fat))

            setc(11, m.notes or "", align=Qt.AlignVCenter | Qt.AlignLeft)

            # Make the date cell also carry the row background if it's the latest.
            if latest_id is not None and m.id == latest_id:
                it0.setBackground(QColor(46, 125, 50, 24))
                f0 = it0.font()
                f0.setBold(True)
                it0.setFont(f0)

                # Update table header chips
        self.chip_count.setText(f"{len(rows)} kayıt" if rows is not None else "0 kayıt")
        if rows:
            try:
                last_dt = max(rows, key=lambda x: x.measured_at).measured_at
                self.chip_last.setText(format_tr_date(last_dt) or "—")
            except Exception:
                self.chip_last.setText("—")
        else:
            self.chip_last.setText("—")

# Select first row so the detail is populated
        if self.table.rowCount() > 0:
            self.table.selectRow(0)
        self._update_action_state()
        self._sync_detail()

    def _selected_measurement_id(self):
        r = self.table.currentRow()
        if r < 0:
            return None
        it = self.table.item(r, 0)
        if not it:
            return None
        return it.data(Qt.UserRole)

    def add_measurement(self):
        dlg = MeasurementDialog(self)
        if dlg.exec() == dlg.DialogCode.Accepted and dlg.result_data:
            r = dlg.result_data
            try:
                self.svc.create(
                    client_id=self.client_id,
                    measured_at=r.measured_at,
                    height_cm=r.height_cm,
                    weight_kg=r.weight_kg,
                    waist_cm=r.waist_cm,
                    hip_cm=r.hip_cm,
                    neck_cm=r.neck_cm,
                    body_fat_percent=r.body_fat_percent,
                    muscle_kg=r.muscle_kg,
                    water_percent=r.water_percent,
                    visceral_fat=r.visceral_fat,
                    notes=r.notes,
                )
                self.refresh()
                self.measurements_changed.emit()
            except Exception as e:
                QMessageBox.critical(self, "Kayıt Hatası", f"Ölçüm kaydedilemedi.\n\nHata: {e}")

    def edit_measurement(self):
        mid = self._selected_measurement_id()
        if not mid:
            QMessageBox.information(self, "Seçim", "Lütfen düzenlemek için bir ölçüm seçin.")
            return
        m = self.svc.get(str(mid))
        if not m:
            QMessageBox.warning(self, "Bulunamadı", "Seçilen ölçüm bulunamadı.")
            return

        dlg = MeasurementDialog(self, existing=m)
        if dlg.exec() == dlg.DialogCode.Accepted and dlg.result_data:
            r = dlg.result_data
            try:
                self.svc.update(
                    measurement_id=str(mid),
                    measured_at=r.measured_at,
                    height_cm=r.height_cm,
                    weight_kg=r.weight_kg,
                    waist_cm=r.waist_cm,
                    hip_cm=r.hip_cm,
                    neck_cm=r.neck_cm,
                    body_fat_percent=r.body_fat_percent,
                    muscle_kg=r.muscle_kg,
                    water_percent=r.water_percent,
                    visceral_fat=r.visceral_fat,
                    notes=r.notes,
                )
                self.refresh()
                self.measurements_changed.emit()
            except Exception as e:
                QMessageBox.critical(self, "Güncelleme Hatası", f"Ölçüm güncellenemedi.\n\nHata: {e}")

    def delete_measurement(self):
        mid = self._selected_measurement_id()
        if not mid:
            QMessageBox.information(self, "Seçim", "Lütfen silmek için bir ölçüm seçin.")
            return
        ok = QMessageBox.question(
            self,
            "Silme Onayı",
            "Seçilen ölçüm silinsin mi? Bu işlem geri alınamaz.",
        )
        if ok != QMessageBox.StandardButton.Yes:
            return
        try:
            self.svc.delete(str(mid))
            self.refresh()
            self.measurements_changed.emit()
        except Exception as e:
            QMessageBox.critical(self, "Silme Hatası", f"Ölçüm silinemedi.\n\nHata: {e}")
