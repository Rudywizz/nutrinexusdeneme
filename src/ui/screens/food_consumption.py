
from __future__ import annotations

import csv
import io
import urllib.request
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, QTimer, QDate, QStringListModel, QObject, QEvent, QSettings
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QMessageBox,
    QComboBox, QLineEdit, QDoubleSpinBox, QDateEdit, QDialog, QFormLayout,
    QSizePolicy, QHeaderView
)
from PySide6.QtGui import QIcon

from src.services.food_consumption_service import FoodConsumptionService
from src.services.templates_service import TemplatesService
from src.ui.dialogs.food_template_dialog import FoodTemplateDialog
from src.app.utils.dates import format_tr_date


MEAL_TYPES = [
    "Kahvaltı",
    "Ara Öğün 1",
    "Öğle",
    "Ara Öğün 2",
    "Akşam",
    "Gece",
]



class RowDragTable(QTableWidget):
    """QTableWidget that supports moving full rows (including cell widgets) via drag & drop."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropOverwriteMode(False)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)

    def dropEvent(self, event):
        try:
            src_row = self.currentRow()
            # Qt6: event.position() gives QPointF
            pos = event.position().toPoint()
            dst_row = self.rowAt(pos.y())
            if dst_row < 0:
                dst_row = self.rowCount() - 1
            if src_row < 0 or dst_row < 0 or src_row == dst_row:
                return super().dropEvent(event)
            # when moving down, insertion index shifts after removing row
            if dst_row > src_row:
                dst_row -= 1
            self._move_row(src_row, dst_row)
            event.accept()
        except Exception:
            super().dropEvent(event)

    def _move_row(self, src: int, dst: int) -> None:
        if src == dst:
            return
        cols = self.columnCount()
        items = []
        widgets = []
        for c in range(cols):
            it = self.takeItem(src, c)
            items.append(it)
            w = self.cellWidget(src, c)
            widgets.append(w)
            if w is not None:
                self.removeCellWidget(src, c)

        self.removeRow(src)
        self.insertRow(dst)

        for c in range(cols):
            it = items[c]
            w = widgets[c]
            if it is not None:
                self.setItem(dst, c, it)
            if w is not None:
                w.setParent(self)
                self.setCellWidget(dst, c, w)

        self.setCurrentCell(dst, 0)


class TemplateManagerDialog(QDialog):
    def __init__(self, parent, service: FoodConsumptionService):
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("Öğün Şablonları")
        self.setMinimumWidth(520)

        lay = QVBoxLayout(self)

        info = QLabel("Şablon; seçtiğin öğün + besin + gram değerlerini tek tıkla ekler.")
        info.setWordWrap(True)
        lay.addWidget(info)

        form = QFormLayout()
        self.edt_name = QLineEdit()
        self.edt_name.setPlaceholderText("Örn: Standart Kahvaltı")
        form.addRow("Şablon Adı", self.edt_name)
        lay.addLayout(form)

        hint = QLabel("Şablon içeriğini aşağıdaki tablodan oluştur: satır ekle, öğün/besin/gram gir.")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Öğün", "Besin", "Gram"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(56)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        lay.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("Satır Ekle")
        self.btn_add.setObjectName("SecondaryBtn")
        self.btn_del = QPushButton("Satır Sil")
        self.btn_del.setObjectName("SecondaryBtn")
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_del)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        self.btn_add.clicked.connect(self._add_row)
        self.btn_del.clicked.connect(self._del_row)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QPushButton("Kapat")
        self.btn_cancel.setObjectName("SecondaryBtn")
        self.btn_save = QPushButton("Kaydet")
        self.btn_save.setObjectName("PrimaryBtn")
        self.btn_save.setMinimumWidth(150)
        self.btn_save.setFixedHeight(38)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_save)
        lay.addLayout(btns)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save.clicked.connect(self._save)

        # start with one row
        self._add_row()

    def _add_row(self):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setRowHeight(r, 56)

        cb = QComboBox()
        cb.addItems(MEAL_TYPES)
        edt_food = QLineEdit()
        edt_food.setPlaceholderText("Besin adı")
        sp = QDoubleSpinBox()
        # Tema nedeniyle inputlar bazı sistemlerde hücre içinde 'kesilmiş' görünebilir.
        # Editör yüksekliklerini sabitleyerek bunu engelliyoruz.
        cb.setFixedHeight(32)
        edt_food.setFixedHeight(32)
        sp.setFixedHeight(32)
        sp.setRange(0, 9999)
        sp.setDecimals(0)
        sp.setValue(100)

        self.table.setCellWidget(r, 0, cb)
        self.table.setCellWidget(r, 1, edt_food)
        self.table.setCellWidget(r, 2, sp)

    def _del_row(self):
        rows = {i.row() for i in self.table.selectionModel().selectedRows()}
        for r in sorted(rows, reverse=True):
            self.table.removeRow(r)

    def _save(self):
        name = self.edt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Eksik Bilgi", "Şablon adı boş olamaz.")
            return

        items = []
        for r in range(self.table.rowCount()):
            meal = self.table.cellWidget(r, 0).currentText()
            food = self.table.cellWidget(r, 1).text().strip()
            gram = float(self.table.cellWidget(r, 2).value() or 0)
            if not food:
                continue
            items.append({"meal_type": meal, "food_name": food, "amount_g": gram})

        if not items:
            QMessageBox.warning(self, "Eksik İçerik", "Şablonda en az 1 besin olmalı.")
            return

        self.service.create_template(name, items)
        QMessageBox.information(self, "Kaydedildi", "Şablon kaydedildi.")
        self.accept()


class CatalogUpdateDialog(QDialog):
    def __init__(self, parent, service: FoodConsumptionService):
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("Besin Verisini Güncelle")
        self.setMinimumWidth(560)

        lay = QVBoxLayout(self)

        lab = QLabel(
            "Bu işlem, internet varsa bir CSV kaynağından mini besin veritabanını indirip günceller.\n"
            "CSV formatı: name,kcal_per_100g  (ilk satır başlık olabilir).\n"
            "Öneri: Kurum içinde paylaşılan bir dosya (intranet / github raw / web sunucu) kullan."
        )
        lab.setWordWrap(True)
        lay.addWidget(lab)

        form = QFormLayout()
        self.edt_url = QLineEdit()
        self.edt_url.setPlaceholderText("https://.../mini_foods.csv")
        self.edt_url.setText(self.service.get_meta("foods_curated_url", ""))
        form.addRow("CSV URL", self.edt_url)
        lay.addLayout(form)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QPushButton("Vazgeç")
        self.btn_cancel.setObjectName("SecondaryBtn")
        self.btn_run = QPushButton("İndir ve Güncelle")
        self.btn_run.setObjectName("PrimaryBtn")
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_run)
        lay.addLayout(btns)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_run.clicked.connect(self._run)

    def _run(self):
        url = self.edt_url.text().strip()
        if not url:
            QMessageBox.warning(self, "Eksik Bilgi", "Lütfen bir CSV URL gir.")
            return

        self.lbl_status.setText("İndiriliyor...")
        self.repaint()

        try:
            with urllib.request.urlopen(url, timeout=12) as resp:
                data = resp.read()
            text = data.decode("utf-8", errors="ignore")
            items = []

            reader = csv.reader(io.StringIO(text))
            for row in reader:
                if not row:
                    continue
                # header support
                if row[0].lower().strip() in ("name", "food", "besin", "besin_adi"):
                    continue
                name = row[0].strip()
                kcal = 0.0
                if len(row) >= 2:
                    try:
                        kcal = float(str(row[1]).strip().replace(",", "."))
                    except Exception:
                        kcal = 0.0
                if name:
                    items.append((name, kcal))

            if not items:
                QMessageBox.warning(self, "Boş Veri", "İndirilen dosyada kayıt bulunamadı.")
                return

            count = self.service.replace_catalog(items)
            self.service.set_meta("foods_curated_url", url)
            QMessageBox.information(self, "Güncellendi", f"Besin kataloğu güncellendi. Kayıt sayısı: {count}")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Güncelleme başarısız:\n{e}")


class FoodConsumptionScreen(QWidget):
    def __init__(self, conn, client_id: str, log=None):
        super().__init__()
        self.conn = conn
        self.client_id = client_id
        self.log = log
        self.svc = FoodConsumptionService(conn)
        self.tpl_svc = TemplatesService(conn, log)
        self.svc.ensure_seed_catalog()
        # UI yardımcıları (son kullanılan besinler + toast)
        self.settings = QSettings('NutriNexus', 'NutriNexus')
        try:
            self._recent_foods = list(self.settings.value('food_recent', []))
        except Exception:
            self._recent_foods = []
        self._active_food_editor: QLineEdit | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 16)
        lay.setSpacing(12)

        title = QLabel("Besin Tüketimi")
        title.setObjectName("PageTitle")
        lay.addWidget(title)

        # Controls card (üst kontrol bandı)
        card = QFrame()
        card.setObjectName("Card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(10)

        # --- Üst kontrol alanı: 2 satırlı grid (daha ferah)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setFixedHeight(34)

        self.btn_copy_yesterday = QPushButton("Dünü Kopyala")
        self.btn_copy_yesterday.setObjectName("SecondaryBtn")
        self.btn_copy_yesterday.setFixedHeight(34)

        self.btn_update_catalog = QPushButton("Besin Verisini Güncelle")
        self.btn_update_catalog.setObjectName("SecondaryBtn")
        self.btn_update_catalog.setFixedHeight(34)

        self.cmb_templates = QComboBox()
        self.cmb_templates.setMinimumWidth(320)
        self.cmb_templates.setFixedHeight(34)

        self.btn_apply_template = QPushButton("Şablondan Ekle")
        self.btn_apply_template.setObjectName("SecondaryBtn")
        self.btn_apply_template.setFixedHeight(34)

        self.btn_new_template = QPushButton("Yeni Besin Şablonu")
        self.btn_new_template.setObjectName("SecondaryBtn")
        self.btn_new_template.setFixedHeight(34)



        # Plan / Tüketim / Fark kartları (Sprint 5.0 - Adım 2)
        def _make_card(title: str, value_label: QLabel, card_name: str) -> QFrame:
            value_label.setObjectName("KcalCardValue")
            value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            card = QFrame()
            card.setObjectName(card_name)
            l = QVBoxLayout(card)
            l.setContentsMargins(12, 10, 12, 10)
            l.setSpacing(2)
            t = QLabel(title)
            t.setObjectName("KcalCardTitle")
            t.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            l.addWidget(t)
            l.addWidget(value_label)
            return card

        self.lbl_plan = QLabel("—")
        self.lbl_plan_hint = QLabel("")
        self.lbl_plan_hint.setObjectName("Hint")
        self.lbl_plan_hint.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_total = QLabel("0 kcal")
        self.lbl_diff = QLabel("—")

        plan_card = _make_card("Plan", self.lbl_plan, "KcalCard")
        try:
            plan_card.layout().addWidget(self.lbl_plan_hint)
        except Exception:
            pass
        cons_card = _make_card("Tüketim", self.lbl_total, "KcalCard")
        diff_card = _make_card("Fark", self.lbl_diff, "KcalCard")

        # Plan kartına tıklayınca hedef kcal ayarla
        plan_card.setCursor(Qt.PointingHandCursor)
        plan_card.mousePressEvent = lambda e: self._open_target_kcal_dialog()

        cards_col = QVBoxLayout()
        cards_col.setSpacing(8)
        cards_col.setContentsMargins(0, 0, 0, 0)
        cards_col.addWidget(plan_card)
        cards_col.addWidget(cons_card)
        cards_col.addWidget(diff_card)

        cards_wrap = QWidget()
        cards_wrap.setLayout(cards_col)

        lab_date = QLabel("Tarih")
        lab_date.setObjectName("FieldLabel")
        lab_tpl = QLabel("Öğün Şablonu")
        lab_tpl.setObjectName("FieldLabel")

        grid.addWidget(lab_date, 0, 0)
        grid.addWidget(self.date_edit, 0, 1)
        grid.addWidget(self.btn_copy_yesterday, 0, 2)
        grid.addWidget(self.btn_update_catalog, 0, 3)

        grid.addWidget(lab_tpl, 1, 0)
        grid.addWidget(self.cmb_templates, 1, 1)
        grid.addWidget(self.btn_apply_template, 1, 2)
        grid.addWidget(self.btn_new_template, 1, 3)

        grid.addWidget(cards_wrap, 0, 4, 2, 1)

        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(4, 0)

        cl.addLayout(grid)

        # Meal subtotals (Sprint 5.0 - Adım 1)
        subt = QHBoxLayout()
        subt.setSpacing(8)
        subt_title = QLabel("Öğün Toplamları")
        subt_title.setObjectName("SubTitle")
        subt.addWidget(subt_title)

        self._meal_total_labels = {}
        for mt in MEAL_TYPES:
            lab = QLabel(f"{mt}: 0")
            lab.setObjectName("Badge")
            lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._meal_total_labels[mt] = lab
            subt.addWidget(lab)

        # Son kullanılan besinler (hızlı ekleme)
        subt.addSpacing(12)
        lab_recent = QLabel('Son Kullanılanlar')
        lab_recent.setObjectName('FieldLabel')
        subt.addWidget(lab_recent)
        self.cmb_recent = QComboBox()
        self.cmb_recent.setMinimumWidth(220)
        self.cmb_recent.setObjectName('Input')
        # GUARD: Bazi eski paketlerde bu metod bulunmadigindan ekran acilisinda crash oluyordu.
        # Metod varsa calistir, yoksa sessizce gec.
        try:
            getattr(self, '_refresh_recent_combo', lambda: None)()
        except Exception:
            pass
        # GUARD: Bazı paket varyantlarında _on_recent_selected metodu bulunmayabiliyor.
        # Metod yoksa ekran asla crash olmasın.
        try:
            cb = getattr(self, '_on_recent_selected', None)
            if cb is not None:
                self.cmb_recent.currentIndexChanged.connect(cb)
        except Exception:
            pass
        subt.addWidget(self.cmb_recent)
        subt.addStretch(1)
        cl.addLayout(subt)

        lay.addWidget(card)

        # Table card
        table_card = QFrame()
        table_card.setObjectName("Card")
        tl = QVBoxLayout(table_card)
        tl.setContentsMargins(14, 12, 14, 12)
        tl.setSpacing(10)

        self.table = RowDragTable(0, 6)
        self.table.setHorizontalHeaderLabels(["Öğün", "Besin", "Gram", "kcal/100g", "Toplam kcal", "Not"])
        self.table.verticalHeader().setVisible(False)
        # Hücre editörleri (QLineEdit/QComboBox/QSpinBox) temada padding'li olduğu için
        # varsayılan satır yüksekliği bazı sistemlerde kısa kalıp içerik "kesilmiş" gibi görünüyordu.
        # Bu yüzden tablo satır yüksekliğini güvenli bir değere sabitliyoruz.
        self.table.verticalHeader().setDefaultSectionSize(56)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)

        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Tablo içi editörler için hafif bir iç boşluk: kenarlara yapışıp 'kırpılmış' görünmesin
        self.table.setStyleSheet(
            "QTableWidget QLineEdit, QTableWidget QComboBox, QTableWidget QDoubleSpinBox { padding: 2px; }"
        )
        tl.addWidget(self.table, 1)
        # Boş tablo ipucu (ekran dolu görünsün ve kullanıcı yönlensin)
        self._empty_hint = QLabel('Henüz kayıt yok. “Satır Ekle” ile başlayın.', self.table.viewport())
        self._empty_hint.setObjectName('EmptyHint')
        self._empty_hint.setAlignment(Qt.AlignCenter)
        self._empty_hint.setWordWrap(True)
        self._empty_hint.setStyleSheet('padding: 18px; color: #6b7785; font-size: 13px;')
        self._empty_hint.hide()

        btns = QHBoxLayout()
        self.btn_add = QPushButton("Satır Ekle")
        self.btn_add.setObjectName("SecondaryBtn")
        self.btn_add.setMinimumWidth(120)
        self.btn_del = QPushButton("Satır Sil")
        self.btn_del.setObjectName("SecondaryBtn")
        self.btn_del.setMinimumWidth(120)
        self.btn_save = QPushButton("Kaydet")
        self.btn_save.setObjectName("PrimaryBtn")
        self.btn_save.setMinimumWidth(140)
        self.btn_save.setFixedHeight(38)
        btns.addWidget(self.btn_add)
        btns.addWidget(self.btn_del)
        btns.addStretch(1)
        btns.addWidget(self.btn_save)
        tl.addLayout(btns)

        lay.addWidget(table_card, 1)

        # Toast (küçük bilgilendirme mesajı)
        self._toast = QLabel('', self)
        self._toast.setObjectName('Toast')
        self._toast.setStyleSheet('background: rgba(0,0,0,0.78); color: white; padding: 8px 12px; border-radius: 10px;')
        self._toast.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._toast.hide)

        # UI polish
        self._apply_local_styles()
        self._configure_table_ui()

        # Hooks
        self.btn_add.clicked.connect(self.add_row)
        self.btn_del.clicked.connect(self.delete_selected)
        self.btn_save.clicked.connect(self.save_day)
        self.btn_copy_yesterday.clicked.connect(self.copy_yesterday)
        self.btn_new_template.clicked.connect(self.new_template)
        self.btn_apply_template.clicked.connect(self.apply_selected_template)
        self.btn_update_catalog.clicked.connect(self.update_catalog)

        self.date_edit.dateChanged.connect(self.load_day)

        # init
        self._reload_templates()
        self.load_day()

    def _apply_local_styles(self) -> None:
        """Bu ekran için lokal (tema ile uyumlu) UI iyileştirmeleri.

        Amaç: ekranı ferahlatmak, 'Toplam kcal' alanını kart gibi göstermek,
        input ve butonlarda minimum yükseklik/padding ile profesyonel görünüm almak.

        Not: Global temayı bozmamak için sadece bu ekrana uygulanır.
        """

        self.setStyleSheet(
            """
            QLabel#FieldLabel { font-weight: 600; }
            QLabel#SubTitle { font-weight: 600; }

            QFrame#KcalCard {
                border-radius: 10px;
                padding: 0px;
            }
            QLabel#KcalCardTitle { font-size: 12px; opacity: 0.85; }
            QLabel#KcalCardValue { font-size: 20px; font-weight: 700; }

            QDateEdit, QComboBox, QLineEdit, QDoubleSpinBox {
                min-height: 34px;
                padding-left: 10px;
                padding-right: 10px;
            }
            QPushButton {
                min-height: 34px;
                padding: 6px 14px;
            }

            /* Tablo içi editörler: biraz daha ferah */
            QTableWidget QLineEdit, QTableWidget QComboBox, QTableWidget QDoubleSpinBox {
                min-height: 32px;
                padding-left: 8px;
                padding-right: 8px;
            }
            """
        )

    def _configure_table_ui(self) -> None:
        """Tabloyu ekranı dolduracak ve okunur olacak şekilde ayarla."""

        self.table.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setShowGrid(True)
        self.table.setWordWrap(False)

        h = self.table.horizontalHeader()
        h.setStretchLastSection(False)
        h.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # Kolonlar: sabit + esnek (Besin ve Not esnek)
        # 0 Öğün, 1 Besin, 2 Gram, 3 kcal/100g, 4 Toplam kcal, 5 Not
        h.setSectionResizeMode(0, QHeaderView.Fixed)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.Fixed)
        h.setSectionResizeMode(3, QHeaderView.Fixed)
        h.setSectionResizeMode(4, QHeaderView.Fixed)
        h.setSectionResizeMode(5, QHeaderView.Stretch)

        self.table.setColumnWidth(0, 120)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 120)

        # Header yüksekliği biraz artsın
        self.table.horizontalHeader().setMinimumHeight(34)
        self.table.horizontalHeader().setDefaultSectionSize(120)

        # Dikey satır yüksekliği zaten 56; boş alanda daha iyi görünür
        self.table.setMinimumHeight(360)

    # ---------- Helpers ----------
    def _iso_date(self) -> str:
        qd = self.date_edit.date()
        return qd.toString("yyyy-MM-dd")

    def _reload_templates(self):
        self.cmb_templates.clear()
        try:
            self._templates = self.tpl_svc.list_food_templates(q="")
        except Exception:
            self._templates = []
        self.cmb_templates.addItem("— Besin Şablonu Seç —", "")
        for t in (self._templates or []):
            # t is FoodTemplate dataclass
            label = f"{t.name}  ·  {t.food_name}  ·  {int(t.amount) if float(t.amount).is_integer() else t.amount} {t.unit}"
            self.cmb_templates.addItem(label, t.id)


    def add_row(self, meal_type: str = "Kahvaltı", food_name: str = "", gram: float = 100, kcal100: float = 0.0, note: str = "", entry_id: str | None = None):
        r = self.table.rowCount()
        self.table.insertRow(r)
        # Tema padding'i nedeniyle satır yüksekliği kısa kalmasın
        self.table.setRowHeight(r, 56)
        

        cb_meal = QComboBox()
        cb_meal.addItems(MEAL_TYPES)
        if meal_type in MEAL_TYPES:
            cb_meal.setCurrentText(meal_type)

        edt_food = QLineEdit()
        edt_food.setPlaceholderText("Besin (autocomplete)")
        edt_food.setText(food_name)

        # aktif editörü takip et (Son Kullanılanlar seçimi için)
        class _FocusTracker(QObject):
            def __init__(self, parent_screen: "FoodConsumptionScreen"):
                super().__init__()
                self._screen = parent_screen

            def eventFilter(self, obj, event):
                if event.type() == QEvent.FocusIn:
                    try:
                        self._screen._active_food_editor = obj
                    except Exception:
                        pass
                return False

        edt_food.installEventFilter(_FocusTracker(self))

        sp_gram = QDoubleSpinBox()
        sp_gram.setRange(0, 9999)
        sp_gram.setDecimals(0)
        sp_gram.setValue(float(gram or 0))

        sp_kcal100 = QDoubleSpinBox()
        sp_kcal100.setRange(0, 2000)
        sp_kcal100.setDecimals(1)
        sp_kcal100.setValue(float(kcal100 or 0))
        sp_kcal100.setEnabled(True)  # kullanıcı isterse manuel düzeltebilir

        item_total = QTableWidgetItem("0")
        item_total.setFlags(item_total.flags() & ~Qt.ItemIsEditable)
        item_total.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

        edt_note = QLineEdit()
        edt_note.setText(note or "")

        # Hücre editörleri: sabit yükseklik (tema/padding kaynaklı görünmezlik sorununu önler)
        cb_meal.setFixedHeight(32)
        edt_food.setFixedHeight(32)
        sp_gram.setFixedHeight(32)
        sp_kcal100.setFixedHeight(32)
        edt_note.setFixedHeight(32)

        # store entry id on first column item (hidden item)
        hidden = QTableWidgetItem("")
        if entry_id:
            hidden.setData(Qt.UserRole, entry_id)
        self.table.setItem(r, 0, hidden)

        self.table.setCellWidget(r, 0, cb_meal)
        self.table.setCellWidget(r, 1, edt_food)
        self.table.setCellWidget(r, 2, sp_gram)
        self.table.setCellWidget(r, 3, sp_kcal100)
        self.table.setItem(r, 4, item_total)
        self.table.setCellWidget(r, 5, edt_note)

        # autocomplete
        model = QStringListModel(self._get_suggestions(food_name or "", limit=30))
        comp = edt_food.completer()
        if comp is None:
            from PySide6.QtWidgets import QCompleter
            comp = QCompleter()
            comp.setCompletionMode(QCompleter.PopupCompletion)
            comp.setMaxVisibleItems(12)
            comp.setCaseSensitivity(Qt.CaseInsensitive)
            comp.setFilterMode(Qt.MatchContains)
            edt_food.setCompleter(comp)
        comp.setModel(model)

        def refresh_suggestions(text: str):
            suggestions = self._get_suggestions(text, limit=30)
            model.setStringList(suggestions)

        debounce_timer = QTimer(self)
        debounce_timer.setSingleShot(True)
        debounce_timer.setInterval(120)
        _last_text = {"v": ""}

        def _fire_refresh():
            refresh_suggestions(_last_text["v"])

        debounce_timer.timeout.connect(_fire_refresh)

        def _schedule_refresh(text: str):
            # avoid hammering DB on every keystroke for big catalogs
            _last_text["v"] = text
            debounce_timer.stop()
            debounce_timer.start()

        edt_food.textEdited.connect(_schedule_refresh)

        def on_food_commit():
            name = edt_food.text().strip()
            if not name:
                self._recalc_row(r)
                return
            item = self.svc.get_catalog_item(name)
            if item and item.get("kcal_per_100g") is not None:
                sp_kcal100.blockSignals(True)
                sp_kcal100.setValue(float(item["kcal_per_100g"] or 0))
                sp_kcal100.blockSignals(False)
                # MRU: son kullanılanlar
                self._push_recent(name)
            self._recalc_row(r)


        # Stabilizasyon: Enter/Return ile öneriyi hızlı kabul et (UI donmadan)
        class _FoodEditFilter(QObject):
            def __init__(self, line_edit: QLineEdit, on_commit_cb):
                super().__init__(line_edit)
                self._le = line_edit
                self._on_commit = on_commit_cb

            def eventFilter(self, obj, event):
                try:
                    if obj is self._le and event.type() == QEvent.KeyPress:
                        key = event.key()
                        if key in (Qt.Key_Return, Qt.Key_Enter):
                            comp = self._le.completer()
                            if comp is not None and comp.popup() is not None and comp.popup().isVisible():
                                # currentCompletion bazen boş gelebilir; completionPrefix üzerinden tamamlamayı al
                                completion = comp.currentCompletion() or comp.completionModel().data(comp.popup().currentIndex())
                                if completion:
                                    self._le.setText(str(completion))
                                comp.popup().hide()
                                # seçimi commit et
                                self._on_commit()
                                return True
                            # popup yoksa normal commit
                            self._on_commit()
                            return True
                except Exception:
                    pass
                return super().eventFilter(obj, event)

        edt_food.editingFinished.connect(on_food_commit)
        _filt = _FoodEditFilter(edt_food, on_food_commit)
        edt_food.installEventFilter(_filt)
        sp_gram.valueChanged.connect(lambda _=None: self._recalc_row(r))
        sp_kcal100.valueChanged.connect(lambda _=None: self._recalc_row(r))
        edt_note.editingFinished.connect(lambda: self._recalc_row(r))

        self._recalc_row(r)
        self._update_empty_hint()
        # Kolonlar her satır eklemede yeniden ölçülmesin (performans/UX)
        # İlk kurulumda sabit/stretched kolon ayarı uygulanıyor.

    def _recalc_row(self, r: int):
        try:
            sp_gram = self.table.cellWidget(r, 2)
            sp_kcal100 = self.table.cellWidget(r, 3)
            gram = float(sp_gram.value() if sp_gram else 0)
            kcal100 = float(sp_kcal100.value() if sp_kcal100 else 0)
            total = self.svc.calc_kcal_total(gram, kcal100)
            item_total = self.table.item(r, 4)
            if item_total:
                item_total.setText(f"{total:.0f}")
        except Exception:
            pass
        self._update_totals()
        self._update_empty_hint()


    def _refresh_plan_card(self):
        plan = self.svc.get_target_kcal(self.client_id)
        if plan is None or plan <= 0:
            self.lbl_plan.setText("—")
            self.lbl_plan_hint.setText("Hedef kcal ayarlamak için tıklayın")
            self.lbl_plan_hint.setVisible(True)
            self.lbl_plan.setToolTip("Günlük hedef kaloriyi ayarlamak için tıklayın.")
        else:
            self.lbl_plan.setText(f"{plan:.0f} kcal")
            self.lbl_plan_hint.setText("Hedefi değiştirmek için tıklayın")
            self.lbl_plan_hint.setVisible(True)
            self.lbl_plan.setToolTip("Hedef kaloriyi değiştirmek için tıklayın.")

    def _update_diff_card(self):
        plan = self.svc.get_target_kcal(self.client_id)
        try:
            total_text = self.lbl_total.text().replace("kcal", "").strip()
            total = float(total_text or 0)
        except Exception:
            total = 0.0
        if plan is None or plan <= 0:
            self.lbl_diff.setText("—")
            return
        diff = total - float(plan)
        sign = "+" if diff > 0 else ""
        self.lbl_diff.setText(f"{sign}{diff:.0f} kcal")

    def _open_target_kcal_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Plan Hedefi (kcal)")
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        info = QLabel("Danışanın günlük hedef kalorisini girin. (Diyet planınızla aynı olabilir)")
        info.setWordWrap(True)
        lay.addWidget(info)

        form = QFormLayout()
        sp = QDoubleSpinBox()
        sp.setDecimals(0)
        sp.setRange(0, 10000)
        sp.setSingleStep(50)
        current = self.svc.get_target_kcal(self.client_id) or 0
        sp.setValue(float(current))
        sp.setObjectName("Input")
        form.addRow("Hedef kcal", sp)
        lay.addLayout(form)

        row = QHBoxLayout()
        row.addStretch(1)
        btn_cancel = QPushButton("Vazgeç")
        btn_cancel.setObjectName("SecondaryBtn")
        btn_ok = QPushButton("Kaydet")
        btn_ok.setObjectName("PrimaryBtn")
        row.addWidget(btn_cancel)
        row.addWidget(btn_ok)
        lay.addLayout(row)

        btn_cancel.clicked.connect(dlg.reject)

        def _save():
            val = float(sp.value())
            self.svc.set_target_kcal(self.client_id, val)
            self._refresh_plan_card()
            self._update_diff_card()
            dlg.accept()

        btn_ok.clicked.connect(_save)
        dlg.exec()

    def _update_totals(self):
        rows = []
        for r in range(self.table.rowCount()):
            cb_meal = self.table.cellWidget(r, 0)
            meal = cb_meal.currentText() if cb_meal else ""
            it = self.table.item(r, 4)
            kcal = 0.0
            if it:
                try:
                    kcal = float(it.text().strip() or 0)
                except Exception:
                    kcal = 0.0
            rows.append({"meal_type": meal, "kcal_total": kcal})

        meal_totals, total = self.svc.compute_meal_totals(rows)
        self.lbl_total.setText(f"{total:.0f} kcal")
        # Plan hedefi (kcal) kartını her gün yüklemede/hesaplamada güncel tut
        self._refresh_plan_card()
        self._update_diff_card()

        # update meal badges
        for mt, lab in (self._meal_total_labels or {}).items():
            v = float(meal_totals.get(mt, 0.0) or 0.0)
            lab.setText(f"{mt}: {v:.0f}")

    # ---------- Actions ----------
    def load_day(self):
        iso = self._iso_date()
        entries = self.svc.list_entries(self.client_id, iso)

        self.table.setRowCount(0)
        if not entries:
            # start with one row for usability
            self.add_row()
            self._update_totals()
            return

        for e in entries:
            self.add_row(
                meal_type=e.meal_type or "Kahvaltı",
                food_name=e.food_name or "",
                gram=float(e.amount_g or 0),
                kcal100=float(e.kcal_per_100g or 0),
                note=e.note or "",
                entry_id=e.id
            )
        self._update_totals()

    def save_day(self):
        iso = self._iso_date()
        # Upsert rows
        saved = 0
        for r in range(self.table.rowCount()):
            cb_meal = self.table.cellWidget(r, 0)
            edt_food = self.table.cellWidget(r, 1)
            sp_gram = self.table.cellWidget(r, 2)
            sp_kcal100 = self.table.cellWidget(r, 3)
            edt_note = self.table.cellWidget(r, 5)

            meal = cb_meal.currentText() if cb_meal else ""
            food = edt_food.text().strip() if edt_food else ""
            gram = float(sp_gram.value() if sp_gram else 0)
            kcal100 = float(sp_kcal100.value() if sp_kcal100 else 0)
            note = edt_note.text().strip() if edt_note else ""

            # ignore empty rows
            if not food and gram == 0 and note == "":
                continue

            entry_id = None
            hidden = self.table.item(r, 0)
            if hidden:
                entry_id = hidden.data(Qt.UserRole)

            new_id = self.svc.upsert_entry(
                entry_id=entry_id,
                client_id=self.client_id,
                entry_date=iso,
                meal_type=meal,
                food_name=food,
                amount_g=gram,
                kcal_per_100g=kcal100,
                note=note,
                display_order=r+1,
            )
            if hidden:
                hidden.setData(Qt.UserRole, new_id)
            saved += 1

        self._toast_show(f"Kaydedildi: {saved} satır")
        self.load_day()

    def delete_selected(self):
        rows = {i.row() for i in self.table.selectionModel().selectedRows()}
        if not rows:
            return
        if QMessageBox.question(self, "Sil", "Seçili satırlar silinsin mi?") != QMessageBox.Yes:
            return
        for r in sorted(rows, reverse=True):
            hidden = self.table.item(r, 0)
            entry_id = hidden.data(Qt.UserRole) if hidden else None
            if entry_id:
                try:
                    self.svc.delete_entry(self.client_id, entry_id)
                except Exception:
                    pass
            self.table.removeRow(r)
        self._update_totals()

    def copy_yesterday(self):
        iso = self._iso_date()
        try:
            d = datetime.strptime(iso, "%Y-%m-%d").date()
        except Exception:
            QMessageBox.warning(self, "Tarih Hatası", "Tarih okunamadı.")
            return
        y = (d - timedelta(days=1)).strftime("%Y-%m-%d")

        if QMessageBox.question(
            self,
            "Dünü Kopyala",
            f"{format_tr_date(y)} günündeki besin kayıtları {format_tr_date(iso)} tarihine kopyalansın mı?\n"
            "Mevcut kayıtlar varsa üzerine yazılır.",
        ) != QMessageBox.Yes:
            return

        n = self.svc.copy_day(self.client_id, y, iso)
        QMessageBox.information(self, "Tamam", f"{n} satır kopyalandı.")
        self.load_day()

    def new_template(self):
        # Besin Şablonu hızlı ekleme: Templates modülüne girmeden, buradan kayıt aç
        dlg = FoodTemplateDialog(self, title="Yeni Besin Şablonu", initial={
            "name": "",
            "food_name": "",
            "amount": 100,
            "unit": "g",
            "note": "",
        })
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.data()
        try:
            self.tpl_svc.upsert_food_template(
                tpl_id=None,
                name=data.get("name", ""),
                food_name=data.get("food_name", ""),
                amount=float(data.get("amount", 0) or 0),
                unit=data.get("unit", "g"),
                note=data.get("note", ""),
            )
            self._reload_templates()
        except Exception as e:
            QMessageBox.warning(self, "Şablon Kaydedilemedi", str(e))

    def apply_selected_template(self):
        tid = self.cmb_templates.currentData()
        if not tid:
            return

        tpl = None
        for t in (self._templates or []):
            # FoodTemplate dataclass
            if getattr(t, "id", None) == tid:
                tpl = t
                break
        if not tpl:
            return

        food_n = (getattr(tpl, "food_name", "") or "").strip()
        cat = self.svc.get_catalog_item(food_n) if food_n else None

        # amount -> gram (en yaygın kullanım). Farklı birimler için şimdilik not düş.
        unit = (getattr(tpl, "unit", "") or "").strip()
        amount = float(getattr(tpl, "amount", 0) or 0)

        gram = amount
        note = (getattr(tpl, "note", "") or "").strip()

        if unit and unit.lower() not in ["g", "gr", "gram"]:
            extra = f"Şablon birimi: {unit} ({amount})"
            note = (note + (" | " if note else "") + extra).strip()

        self.add_row(
            meal_type="Kahvaltı",
            food_name=food_n,
            gram=gram,
            kcal100=float(cat["kcal_per_100g"]) if cat else 0.0,
            note=note
        )
        self._update_totals()

    # ---------- UI helpers ----------
    def _get_suggestions(self, prefix: str, limit: int = 30) -> list[str]:
        p = (prefix or "").strip()
        # recent (prefix filtreli)
        rec = []
        try:
            for n in (self._recent_foods or []):
                if not isinstance(n, str):
                    continue
                if not p or p.casefold() in n.casefold():
                    rec.append(n)
        except Exception:
            rec = []
        base = []
        try:
            base = self.svc.get_suggestions(self.client_id, p, limit=limit)
        except Exception:
            base = []
        out = []
        for n in rec + (base or []):
            if n and n not in out:
                out.append(n)
            if len(out) >= limit:
                break
        return out

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # toast sağ-alt
        try:
            if hasattr(self, '_toast') and self._toast.isVisible():
                m = 18
                self._toast.adjustSize()
                self._toast.move(self.width() - self._toast.width() - m, self.height() - self._toast.height() - m)
        except Exception:
            pass
        self._position_empty_hint()

    def _toast_show(self, message: str, ms: int = 1400):
        try:
            self._toast.setText(message)
            self._toast.adjustSize()
            m = 18
            self._toast.move(self.width() - self._toast.width() - m, self.height() - self._toast.height() - m)
            self._toast.show()
            self._toast.raise_()
            self._toast_timer.stop()
            self._toast_timer.start(ms)
        except Exception:
            pass

    def _position_empty_hint(self):
        try:
            if not hasattr(self, '_empty_hint'):
                return
            vp = self.table.viewport()
            self._empty_hint.setGeometry(0, 0, vp.width(), vp.height())
        except Exception:
            pass

    def _update_empty_hint(self):
        if not hasattr(self, '_empty_hint'):
            return
        has_rows = self.table.rowCount() > 0
        if has_rows:
            self._empty_hint.hide()
        else:
            self._position_empty_hint()
            self._empty_hint.show()

    def _refresh_recent_combo(self):
        # Recent list: en güncel üstte, 25 ile sınırlı
        try:
            rec = [r for r in (self._recent_foods or []) if isinstance(r, str) and r.strip()]
        except Exception:
            rec = []
        rec = rec[:25]
        if not hasattr(self, 'cmb_recent'):
            return
        self.cmb_recent.blockSignals(True)
        self.cmb_recent.clear()
        self.cmb_recent.addItem('— Seç —')
        for r in rec:
            self.cmb_recent.addItem(r)
        self.cmb_recent.setCurrentIndex(0)
        self.cmb_recent.blockSignals(False)

    def _refresh_recent_combo(self):
        """Son kullanılanlar combobox'ını güvenli şekilde yeniler."""
        try:
            if not hasattr(self, 'cmb_recent') or self.cmb_recent is None:
                return
            self.cmb_recent.blockSignals(True)
            self.cmb_recent.clear()
            self.cmb_recent.addItem('— Seç —', None)
            for n in (self._recent_foods or []):
                if isinstance(n, str):
                    n = n.strip()
                    if n:
                        self.cmb_recent.addItem(n, n)
            self.cmb_recent.setCurrentIndex(0)
        finally:
            try:
                self.cmb_recent.blockSignals(False)
            except Exception:
                pass

    def _push_recent(self, name: str):
        n = (name or '').strip()
        if not n:
            return
        # listeyi güncelle (unique + MRU)
        try:
            rec = [x for x in (self._recent_foods or []) if x != n]
        except Exception:
            rec = []
        rec.insert(0, n)
        self._recent_foods = rec[:30]
        try:
            self.settings.setValue('food_recent', self._recent_foods)
        except Exception:
            pass
        self._refresh_recent_combo()

    def _on_recent_selected(self, idx: int):
        if idx <= 0:
            return
        try:
            name = self.cmb_recent.currentText().strip()
            if not name or name == '— Seç —':
                return
            # aktif food editöre yaz
            if self._active_food_editor is not None:
                self._active_food_editor.setText(name)
                # commit tetikle
                self._active_food_editor.editingFinished.emit()
            self.cmb_recent.setCurrentIndex(0)
        except Exception:
            pass

    def update_catalog(self):
        dlg = CatalogUpdateDialog(self, self.svc)
        if dlg.exec() == QDialog.Accepted:
            # refresh completers by reloading current day
            self.load_day()