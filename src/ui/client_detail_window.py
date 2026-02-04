from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QTabWidget, QFrame, QPushButton,
    QMessageBox
)
from PySide6.QtCore import Qt

from src.ui.widgets.clinical_card import ClinicalCardWidget
from src.ui.dialogs.client_form_dialog import ClientFormDialog
from src.services.clients_service import ClientsService
from src.ui.screens.reports import ReportsScreen
from src.ui.screens.clinical_summaries import ClinicalSummariesScreen
from src.ui.screens.files import ClientFilesScreen
from src.ui.screens.diet_plans import DietPlansScreen
from src.ui.screens.food_consumption import FoodConsumptionScreen
from src.ui.widgets.custom_titlebar import CustomTitleBar

class ClientDetailWindow(QMainWindow):
    def __init__(self, client: dict, state, log):
        super().__init__()
        # Frameless kurumsal üst bar
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowFlag(Qt.Window, True)
        self.client = client
        self.state = state
        self.log = log
        client_id = client.get('id')
        self.setWindowTitle(f"NutriNexus — {client.get('name','Danışan')}")
        self.svc = ClientsService(state.conn)

        root = QWidget()
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)

        # Üst kurumsal bar (logo + başlık + pencere kontrolleri)
        tb = CustomTitleBar(self, title=self.windowTitle(), logo_path="src/assets/logo.png", show_maximize=True)
        lay.addWidget(tb)


        # Başlık + aksiyonlar (kart içinde, daha profesyonel)
        header = QFrame()
        header.setObjectName("Card")
        header_lay = QVBoxLayout(header)
        header_lay.setContentsMargins(16, 14, 16, 14)
        header_lay.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(12)

        title = QLabel(f"{client.get('name','')}")
        title.setObjectName("PageTitle")

        # Info chips (telefon / doğum / cinsiyet) — okunaklı ve modern
        chips_row = QHBoxLayout()
        chips_row.setSpacing(8)

        def _mk_chip(text: str, tone: str = "neutral") -> QLabel:
            lab = QLabel(text)
            lab.setProperty("chip", "1")
            lab.setProperty("tone", tone)
            lab.setAlignment(Qt.AlignVCenter)
            return lab

        self._chip_phone = _mk_chip(f"Tel: {client.get('phone','') or '-'}", "info")
        self._chip_dob = _mk_chip(f"Doğum: {client.get('dob','') or '-'}", "neutral")
        self._chip_gender = _mk_chip(f"Cinsiyet: {client.get('gender','') or '-'}", "neutral")
        chips_row.addWidget(self._chip_phone)
        chips_row.addWidget(self._chip_dob)
        chips_row.addWidget(self._chip_gender)
        chips_row.addStretch(1)

        top_left = QVBoxLayout()
        top_left.setSpacing(4)
        top_left.addWidget(title)
        top_left.addLayout(chips_row)
        top.addLayout(top_left, 1)
        top.addStretch(1)

        btn_edit = QPushButton("Düzenle")
        btn_edit.setObjectName("SecondaryBtn")
        btn_edit.clicked.connect(self._edit_client)
        top.addWidget(btn_edit)

        btn_back = QPushButton("Kapat")
        btn_back.setObjectName("SecondaryBtn")
        btn_back.clicked.connect(self.close)
        top.addWidget(btn_back)

        header_lay.addLayout(top)
        lay.addWidget(header)

        self._title_label = title
        tabs = QTabWidget()
        tabs.setObjectName("ClientTabs")

        tabs.addTab(self._general_info(), "Genel Bilgiler")
        tabs.addTab(ClinicalCardWidget(state=state, log=log, client_id=client_id), "Klinik Kart")
        tabs.addTab(DietPlansScreen(conn=state.conn, client_id=client_id, log=log), "Diyet Planları")
        tabs.addTab(FoodConsumptionScreen(conn=state.conn, client_id=client_id, log=log), "Besin Tüketim")
        tabs.addTab(ClientFilesScreen(conn=state.conn, backup_root=state.backup_root, client_id=client_id, log=log), "Dosyalar")
        tabs.addTab(ClinicalSummariesScreen(client_id=client_id, client_name=client.get("full_name") or client.get("name") or "", parent=self), "Klinik Özetler")
        tabs.addTab(ReportsScreen(conn=state.conn, client_id=client_id, log=log), "Raporlar")

        lay.addWidget(tabs)

        self._title_label = title

    def _placeholder(self, text):
        w = QFrame()
        w.setObjectName("Card")
        l = QVBoxLayout(w)
        lab = QLabel(text)
        lab.setWordWrap(True)
        l.addWidget(lab)
        l.addStretch(1)
        return w

    def _general_info(self):
            # Genel Bilgiler: mini dashboard (2 kolon) — daha dolu ve profesyonel görünüm
            root = QWidget()
            root.setObjectName("ClientGeneralPage")
            hl = QHBoxLayout(root)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(14)
        
            def _card(title_text: str) -> tuple[QFrame, QVBoxLayout]:
                c = QFrame()
                c.setObjectName("Card")
                l = QVBoxLayout(c)
                l.setContentsMargins(16, 14, 16, 14)
                l.setSpacing(10)
                t = QLabel(title_text)
                t.setObjectName("CardTitle")
                l.addWidget(t)
                return c, l
        
            def _kv_grid(rows: list[tuple[str, str]]) -> QWidget:
                w = QWidget()
                g = QGridLayout(w)
                g.setContentsMargins(0, 0, 0, 0)
                g.setHorizontalSpacing(14)
                g.setVerticalSpacing(8)
                r = 0
                for k, v in rows:
                    lk = QLabel(k)
                    lk.setProperty("role", "kv_label")
                    lv = QLabel(v or "-")
                    lv.setProperty("role", "kv_value")
                    lv.setWordWrap(True)
                    g.addWidget(lk, r, 0, 1, 1, Qt.AlignLeft | Qt.AlignVCenter)
                    g.addWidget(lv, r, 1, 1, 1, Qt.AlignLeft | Qt.AlignVCenter)
                    r += 1
                g.setColumnStretch(0, 0)
                g.setColumnStretch(1, 1)
                return w
        
            # Sol kolon (ana içerik)
            left = QVBoxLayout()
            left.setSpacing(14)
        
            c1, c1l = _card("Kimlik")
            c1l.addWidget(_kv_grid([
                ("Ad Soyad", self.client.get("name", "") or "-"),
                ("Telefon", self.client.get("phone", "") or "-"),
                ("Doğum Tarihi", self.client.get("dob", "") or "-"),
                ("Cinsiyet", self.client.get("gender", "") or "-"),
            ]))
            c1l.addStretch(1)
        
            c2, c2l = _card("Plan Durumu")
            info = QLabel("Aktif plan bilgisi bu alanda gösterilir. Henüz aktif plan yoksa, burası yönlendirici bir özet kartı olarak kalır.")
            info.setWordWrap(True)
            info.setObjectName("Muted")
            c2l.addWidget(info)
            c2l.addStretch(1)
        
            left.addWidget(c1, 0)
            left.addWidget(c2, 0)
            left.addStretch(1)
        
            left_wrap = QWidget()
            left_wrap.setLayout(left)
        
            # Sağ kolon (sidebar — dolu görünüm)
            right = QVBoxLayout()
            right.setSpacing(14)
        
            s1, s1l = _card("Hızlı Özet")
            s1l.addWidget(_kv_grid([
                ("Durum", "Aktif"),
                ("Son İşlem", "—"),
            ]))
            s1l.addStretch(1)
        
            s2, s2l = _card("Randevular")
            lab = QLabel("Yaklaşan randevu bilgileri burada listelenir.")
            lab.setWordWrap(True)
            lab.setObjectName("Muted")
            s2l.addWidget(lab)
            s2l.addStretch(1)
        
            s3, s3l = _card("Notlar")
            n = QLabel("Kısa notlar ve hatırlatmalar (ileride).")
            n.setWordWrap(True)
            n.setObjectName("Muted")
            s3l.addWidget(n)
            s3l.addStretch(1)
        
            right.addWidget(s1)
            right.addWidget(s2)
            right.addWidget(s3)
            right.addStretch(1)
        
            right_wrap = QWidget()
            right_wrap.setLayout(right)
        
            hl.addWidget(left_wrap, 3)
            hl.addWidget(right_wrap, 2)
        
            return root


    def _edit_client(self):
        cid = self.client.get("id")
        if not cid:
            return
        fresh = self.svc.get_client(cid)
        if not fresh:
            QMessageBox.warning(self, "Bulunamadı", "Danışan bulunamadı.")
            return
        initial = fresh.to_ui_dict()
        dlg = ClientFormDialog(self, title="Danışan Düzenle", initial=initial)
        if dlg.exec() == dlg.DialogCode.Accepted and dlg.result_data:
            r = dlg.result_data
            try:
                self.svc.update_client(cid, full_name=r.full_name, phone=r.phone, birth_date=r.birth_date, gender=r.gender)
                updated = self.svc.get_client(cid).to_ui_dict()
                self.client = updated
                # üst başlıkları güncelle
                self._title_label.setText(updated.get("name", ""))
                self._chip_phone.setText(f"Tel: {updated.get('phone','') or '-'}")
                self._chip_dob.setText(f"Doğum: {updated.get('dob','') or '-'}")
                self._chip_gender.setText(f"Cinsiyet: {updated.get('gender','') or '-'}")
                QMessageBox.information(self, "Güncellendi", "Danışan bilgileri güncellendi.")
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Güncelleme başarısız.\n\nHata: {e}")