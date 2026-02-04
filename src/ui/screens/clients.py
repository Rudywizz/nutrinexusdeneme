from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, QLineEdit,
    QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from src.services.clients_service import ClientsService
from src.ui.dialogs.client_form_dialog import ClientFormDialog
from src.app.utils.dates import format_tr_date

class ClientsScreen(QWidget):
    def __init__(self, state, log, open_client_detail_cb):
        super().__init__()
        self.state = state
        self.log = log
        self.open_client_detail_cb = open_client_detail_cb

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 18)
        lay.setSpacing(12)

        # Header (Title + actions + subtitle)
        header_box = QVBoxLayout()
        header_top = QHBoxLayout()

        title = QLabel("Danışanlar")
        title.setObjectName("PageTitle")
        header_top.addWidget(title)
        header_top.addStretch(1)

        self.btn_new = QPushButton("+ Yeni Danışan")
        self.btn_new.setObjectName("PrimaryBtn")
        header_top.addWidget(self.btn_new)

        self.btn_edit = QPushButton("Düzenle")
        self.btn_edit.setObjectName("SecondaryBtn")
        self.btn_edit.setEnabled(False)
        header_top.addWidget(self.btn_edit)

        self.btn_deactivate = QPushButton("Pasife Al")
        # Pasife alma görsel olarak uyarı ama "tehlike" kadar sert olmasın: Warning
        self.btn_deactivate.setObjectName("WarningBtn")
        self.btn_deactivate.setEnabled(False)
        header_top.addWidget(self.btn_deactivate)

        header_box.addLayout(header_top)

        subtitle = QLabel("Kayıtlı danışanları görüntüleyin ve yönetin.")
        subtitle.setObjectName("PageSubtitle")
        header_box.addWidget(subtitle)

        lay.addLayout(header_box)

        # Search
        self.search = QLineEdit()
        self.search.setPlaceholderText("Ad, soyad veya telefon ile ara…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        self.search.setObjectName("Input")
        lay.addWidget(self.search)

        card = QFrame()
        card.setObjectName("Card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 12, 12, 12)
        cl.setSpacing(8)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Ad Soyad", "Telefon", "Doğum Tarihi", "Cinsiyet"])
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # Derli toplu kolonlar: Cinsiyet dar, telefon/doğum sabit, ad soyad esner
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 170)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(3, 110)

        vh = self.table.verticalHeader()
        vh.setVisible(False)
        vh.setDefaultSectionSize(42)

        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(self.table.SelectionMode.SingleSelection)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.cellDoubleClicked.connect(self._open_selected)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.setObjectName("Table")

        cl.addWidget(self.table)
        lay.addWidget(card)

        self.btn_new.clicked.connect(self._new_client)
        self.btn_edit.clicked.connect(self._edit_selected)
        self.btn_deactivate.clicked.connect(self._deactivate_selected)

        self.svc = ClientsService(state.conn)
        self._refresh()

    def _refresh(self):
        q = (self.search.text() or "").strip()
        clients = self.svc.list_clients(only_active=True, query=q)
        self._rows = [c.to_ui_dict() for c in clients]
        self._render(self._rows)

    def _render(self, rows):
        self.table.setRowCount(0)
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            it_name = QTableWidgetItem(r["name"])
            f = QFont()
            f.setBold(True)
            it_name.setFont(f)
            self.table.setItem(row, 0, it_name)

            it_phone = QTableWidgetItem(r["phone"])
            it_phone.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 1, it_phone)

            it_dob = QTableWidgetItem(r["dob"])
            it_dob.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, it_dob)

            it_gender = QTableWidgetItem(r["gender"])
            it_gender.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 3, it_gender)
            # store id
            self.table.item(row,0).setData(Qt.UserRole, r["id"])

    def _apply_filter(self, text):
        self._refresh()

    def _open_selected(self, row, col):
        item = self.table.item(row, 0)
        if not item:
            return
        client_id = item.data(Qt.UserRole)
        c = self.svc.get_client(client_id)
        if not c:
            return
        self.open_client_detail_cb(c.to_ui_dict())

    def _selection_changed(self):
        has = len(self.table.selectedItems()) > 0
        self.btn_edit.setEnabled(has)
        self.btn_deactivate.setEnabled(has)

    def _selected_client_id(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        return item.data(Qt.UserRole)

    def _new_client(self):
        dlg = ClientFormDialog(self, title="Yeni Danışan")
        res = dlg.exec()
        accepted = (res == dlg.DialogCode.Accepted)
        self.log.info("ClientFormDialog result=%s accepted=%s has_result_data=%s", res, accepted, bool(dlg.result_data))
        if accepted and dlg.result_data:
            r = dlg.result_data
            try:
                created = self.svc.create_client(
                    full_name=r.full_name,
                    phone=r.phone,
                    birth_date=r.birth_date,
                    gender=r.gender,
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Kayıt Hatası",
                    f"Danışan kaydedilemedi.\n\nHata: {e}",
                )
                return

            # Kullanıcı arama filtresi kullanıyorsa yeni danışan görünmeyebilir.
            # Bu yüzden yeni kayıt sonrası filtreyi temizleyip listeyi yeniliyoruz.
            if (self.search.text() or "").strip():
                self.search.blockSignals(True)
                self.search.setText("")
                self.search.blockSignals(False)

            self._refresh()

            # Yeni eklenen satırı seç (varsa)
            for row in range(self.table.rowCount()):
                it = self.table.item(row, 0)
                if it and it.data(Qt.UserRole) == created.id:
                    self.table.selectRow(row)
                    self.table.scrollToItem(it)
                    break

            try:
                # Filtre açık kalırsa yeni kayıt görünmeyebilir; temizleyelim.
                if hasattr(self, 'search_input'):
                    self.search_input.setText('')
            except Exception:
                pass
            QMessageBox.information(self, "Kayıt Başarılı", "Danışan kaydedildi ve liste güncellendi.")

    def _edit_selected(self):
        cid = self._selected_client_id()
        if not cid:
            return
        c = self.svc.get_client(cid)
        if not c:
            return
        initial = c.to_ui_dict()
        dlg = ClientFormDialog(self, title="Danışan Düzenle", initial=initial)
        if dlg.exec() == dlg.Accepted and dlg.result_data:
            r = dlg.result_data
            self.svc.update_client(cid, full_name=r.full_name, phone=r.phone, birth_date=r.birth_date, gender=r.gender)
            self._refresh()

    def _deactivate_selected(self):
        cid = self._selected_client_id()
        if not cid:
            return
        row = self.table.currentRow()
        name_item = self.table.item(row, 0)
        name = name_item.text() if name_item else ""
        ok = QMessageBox.question(
            self,
            "Danışanı Pasife Al",
            f"{name} danışanını pasife almak istiyor musun?\n\nNot: Silinmez, sadece listeden gizlenir.",
        )
        if ok == QMessageBox.StandardButton.Yes:
            self.svc.deactivate_client(cid)
            self._refresh()