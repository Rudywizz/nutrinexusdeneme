from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QTextEdit, QComboBox,
    QPushButton, QMessageBox, QScrollArea, QLineEdit
)
from PySide6.QtCore import QTimer, Qt

from src.services.autosave import DraftKey, upsert_draft, fetch_latest_draft, clear_draft
from src.services.clinical_service import ClinicalService, ClinicalProfile
from src.ui.widgets.collapsible import CollapsibleSection


class AnamnezScreen(QWidget):
    """Klinik Kart > Anamnez (Sprint-2A UI Revizyonu)

    - Açılır/kapanır bölümler (QToolBox) ile daha derli toplu.
    - DB'ye kaydedilebilir (clinical_profiles)
    - 10 sn'de bir taslak autosave (drafts)
    """

    def __init__(self, conn, client_id: str, log):
        super().__init__()
        self.conn = conn
        self.client_id = client_id
        self.log = log
        self.svc = ClinicalService(conn)

        self.draft_key = DraftKey(entity_type="clinical_profile", entity_id=None, client_id=client_id)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        card = QFrame(objectName="Card")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(16, 16, 16, 16)
        card_lay.setSpacing(12)

        # Header
        header = QHBoxLayout()
        header.setSpacing(10)

        left = QVBoxLayout()
        left.setSpacing(2)

        title = QLabel("Anamnez", objectName="CardTitle")
        hint = QLabel(
            "Not: Buradaki bilgiler danışan bazlıdır. Uygulama kapanırsa taslak otomatik kurtarılabilir.",
            objectName="Hint",
        )
        hint.setWordWrap(True)

        left.addWidget(title)
        left.addWidget(hint)

        header.addLayout(left)
        header.addStretch(1)

        self.btn_save = QPushButton("Kaydet", objectName="PrimaryBtn")
        self.btn_clear_draft = QPushButton("Taslağı Temizle", objectName="GhostBtn")
        header.addWidget(self.btn_save)
        header.addWidget(self.btn_clear_draft)

        card_lay.addLayout(header)

        # Scroll area for content
        scroll = QScrollArea()
        scroll.setObjectName("AnamnezScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        card_lay.addWidget(scroll, 1)

        container = QWidget()
        container.setObjectName("AnamnezContainer")
        scroll.setWidget(container)
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        # QToolBox bazı tema/palette kombinasyonlarında sekme başlıklarını gizleyebiliyor.
        # O yüzden burada kendi collapsible (accordion) bileşenimizi kullanıyoruz.
        self.sections_wrap = QWidget(objectName="AnamnezSections")
        self.sections_v = QVBoxLayout(self.sections_wrap)
        self.sections_v.setContentsMargins(0, 0, 0, 0)
        self.sections_v.setSpacing(10)
        v.addWidget(self.sections_wrap)

        # İlk bölüm açık gelsin
        self._first_section = True

        # Sections (collapsible)
        self.txt_diseases = self._add_text_section("Hastalıklar / Tanılar", placeholder="Örn: Hipotiroidi, PCOS, insülin direnci...")
        self.txt_allergies = self._add_text_section("Alerjiler", placeholder="Örn: Fıstık, polen, deniz ürünleri...")
        self.txt_intolerances = self._add_text_section("İntoleranslar", placeholder="Örn: Laktoz intoleransı, gluten hassasiyeti...")
        self.txt_meds = self._add_text_section("Kullandığı İlaçlar", placeholder="Örn: Metformin 1000mg, Levotiroksin...")
        self.txt_supp = self._add_text_section("Takviyeler", placeholder="Örn: D vitamini, Omega-3, Magnezyum...")
        self.txt_notes = self._add_text_section("Genel Notlar", placeholder="Hedefler, motivasyon, özel notlar...")

        # Lifestyle section (form-like)
        lifestyle = QWidget()
        lv = QVBoxLayout(lifestyle)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(10)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        row1.addWidget(QLabel("Aktivite Düzeyi", objectName="FormLabel"))
        self.cmb_activity = QComboBox()
        self.cmb_activity.setObjectName("Input")
        self.cmb_activity.addItems(["", "Sedanter", "Hafif aktif", "Orta aktif", "Çok aktif", "Atlet"])
        self.cmb_activity.setMinimumWidth(220)
        row1.addWidget(self.cmb_activity)
        row1.addStretch(1)
        lv.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self.edt_sleep = QLineEdit()
        self.edt_sleep.setObjectName("Input")
        self.edt_sleep.setPlaceholderText("Uyku (saat/gün)")
        self.edt_stress = QLineEdit()
        self.edt_stress.setObjectName("Input")
        self.edt_stress.setPlaceholderText("Stres (düşük/orta/yüksek)")
        row2.addWidget(self.edt_sleep)
        row2.addWidget(self.edt_stress)
        lv.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(10)
        self.edt_smoking = QLineEdit()
        self.edt_smoking.setObjectName("Input")
        self.edt_smoking.setPlaceholderText("Sigara")
        self.edt_alcohol = QLineEdit()
        self.edt_alcohol.setObjectName("Input")
        self.edt_alcohol.setPlaceholderText("Alkol")
        self.edt_water = QLineEdit()
        self.edt_water.setObjectName("Input")
        self.edt_water.setPlaceholderText("Su tüketimi (L/gün)")
        row3.addWidget(self.edt_smoking)
        row3.addWidget(self.edt_alcohol)
        row3.addWidget(self.edt_water)
        lv.addLayout(row3)

        self._add_widget_section("Yaşam Tarzı", lifestyle)

        v.addStretch(1)

        layout.addWidget(card)

        # Actions
        self.btn_save.clicked.connect(self.save)
        self.btn_clear_draft.clicked.connect(self.clear_draft)

        # Autosave timer
        self.timer = QTimer(self)
        self.timer.setInterval(10_000)
        self.timer.timeout.connect(self.autosave_tick)
        self.timer.start()

        self.load_initial()

    def _add_text_section(self, title: str, placeholder: str = "...") -> QTextEdit:
        t = QTextEdit()
        t.setObjectName("Input")
        t.setPlaceholderText(placeholder)
        t.setMinimumHeight(140)
        t.setTabChangesFocus(True)
        self._add_widget_section(title, t)
        return t

    def _add_widget_section(self, title: str, widget: QWidget) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)
        lay.addWidget(widget)
        sec = CollapsibleSection(title, page, expanded=self._first_section)
        self._first_section = False
        self.sections_v.addWidget(sec)

    def _collect(self) -> dict:
        return {
            "diseases": self.txt_diseases.toPlainText().strip(),
            "allergies": self.txt_allergies.toPlainText().strip(),
            "intolerances": self.txt_intolerances.toPlainText().strip(),
            "medications": self.txt_meds.toPlainText().strip(),
            "supplements": self.txt_supp.toPlainText().strip(),
            "lifestyle": self.txt_notes.toPlainText().strip(),
            "activity_level": (self.cmb_activity.currentText() or "").strip(),
            "sleep": (self.edt_sleep.text() or "").strip(),
            "stress": (self.edt_stress.text() or "").strip(),
            "smoking": (self.edt_smoking.text() or "").strip(),
            "alcohol": (self.edt_alcohol.text() or "").strip(),
            "water": (self.edt_water.text() or "").strip(),
        }

    def _apply(self, data: dict) -> None:
        self.txt_diseases.setPlainText(data.get("diseases", "") or "")
        self.txt_allergies.setPlainText(data.get("allergies", "") or "")
        self.txt_intolerances.setPlainText(data.get("intolerances", "") or "")
        self.txt_meds.setPlainText(data.get("medications", "") or "")
        self.txt_supp.setPlainText(data.get("supplements", "") or "")
        self.txt_notes.setPlainText(data.get("lifestyle", "") or "")
        self.cmb_activity.setCurrentText(data.get("activity_level", "") or "")
        self.edt_sleep.setText(data.get("sleep", "") or "")
        self.edt_stress.setText(data.get("stress", "") or "")
        self.edt_smoking.setText(data.get("smoking", "") or "")
        self.edt_alcohol.setText(data.get("alcohol", "") or "")
        self.edt_water.setText(data.get("water", "") or "")

    def load_initial(self) -> None:
        # 1) Taslak var mı?
        draft = fetch_latest_draft(self.conn, self.draft_key)
        if draft:
            msg = QMessageBox(self)
            msg.setWindowTitle("Taslak bulundu")
            msg.setText("Bu danışan için kurtarılabilir taslak bulundu. Yüklemek ister misin?")
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            if msg.exec() == QMessageBox.Yes:
                self._apply(draft)
                return

        # 2) DB'de kayıt var mı?
        prof = self.svc.get_profile(self.client_id)
        if prof:
            self._apply(prof.__dict__)

    def autosave_tick(self) -> None:
        data = self._collect()
        if not any(v for v in data.values() if isinstance(v, str) and v.strip()):
            return
        try:
            upsert_draft(self.conn, self.draft_key, data)
        except Exception as e:
            self.log.error("Autosave failed: %s", e)

    def save(self) -> None:
        data = self._collect()
        prof = ClinicalProfile(client_id=self.client_id, **data)
        self.svc.upsert_profile(prof)
        # kayıt alınca taslağı temizle
        clear_draft(self.conn, self.draft_key)
        QMessageBox.information(self, "Kaydedildi", "Anamnez kaydedildi.")

    def clear_draft(self) -> None:
        clear_draft(self.conn, self.draft_key)
        QMessageBox.information(self, "Temizlendi", "Taslak temizlendi.")
