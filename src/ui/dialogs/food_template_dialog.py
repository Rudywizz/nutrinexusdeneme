from PySide6.QtCore import Qt, QStringListModel
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QDoubleSpinBox, QComboBox, QWidget, QCompleter
)

from src.ui.dialogs.themed_messagebox import ThemedMessageBox


class FoodTemplateDialog(QDialog):
    def __init__(self, parent=None, *, title: str = "Besin Şablonu", initial: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)

        self._initial = initial or {}

        lay = QVBoxLayout(self)

        header = QLabel(title)
        header.setObjectName("DialogTitle")
        lay.addWidget(header)

        # Name
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Şablon Adı"))
        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("Örn: 'Kahve + Süt' / 'Protein Bar'")
        row1.addWidget(self.ed_name, 1)
        lay.addLayout(row1)

        # Food name
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Besin Adı"))
        self.ed_food = QLineEdit()
        self.ed_food.setPlaceholderText("Örn: Süt, Yulaf, Muz...")
        self._setup_food_autocomplete()
        row2.addWidget(self.ed_food, 1)
        lay.addLayout(row2)

        # Amount + unit
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Miktar"))
        self.sp_amount = QDoubleSpinBox()
        self.sp_amount.setRange(0, 99999)
        self.sp_amount.setDecimals(1)
        self.sp_amount.setSingleStep(10.0)
        row3.addWidget(self.sp_amount)

        self.cb_unit = QComboBox()
        self.cb_unit.addItems(["g", "ml", "adet", "porsiyon"])
        row3.addWidget(self.cb_unit)
        row3.addStretch(1)
        lay.addLayout(row3)

        # Note
        lay.addWidget(QLabel("Not"))
        self.ed_note = QTextEdit()
        self.ed_note.setPlaceholderText("Opsiyonel: kısa not / tarif / hatırlatma")
        self.ed_note.setMinimumHeight(90)
        lay.addWidget(self.ed_note)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        self.btn_cancel = QPushButton("Vazgeç")
        self.btn_cancel.setObjectName("SecondaryBtn")
        self.btn_save = QPushButton("Kaydet")
        self.btn_save.setObjectName("PrimaryBtn")

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save.clicked.connect(self._on_save)

        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_save)
        lay.addLayout(btn_row)

        self._apply_initial()


    def _setup_food_autocomplete(self):
        """Besin Adı alanında, hazır besin kataloğundan otomatik tamamlama."""
        try:
            svc = getattr(self.parent(), 'svc', None)
            if not svc or not hasattr(svc, 'list_catalog_food_names'):
                return
            names = svc.list_catalog_food_names()
            if not names:
                return
            model = QStringListModel(names, self)
            comp = QCompleter(model, self)
            comp.setCaseSensitivity(Qt.CaseInsensitive)
            comp.setFilterMode(Qt.MatchContains)
            comp.setCompletionMode(QCompleter.PopupCompletion)
            self.ed_food.setCompleter(comp)
        except Exception:
            # Autocomplete hiçbir zaman dialogu bozmasın
            return

    def _apply_initial(self):
        self.ed_name.setText(self._initial.get("name", "") or "")
        self.ed_food.setText(self._initial.get("food_name", "") or "")
        try:
            self.sp_amount.setValue(float(self._initial.get("amount", 0) or 0))
        except Exception:
            self.sp_amount.setValue(0)
        unit = (self._initial.get("unit", "g") or "g")
        idx = self.cb_unit.findText(unit)
        if idx >= 0:
            self.cb_unit.setCurrentIndex(idx)
        self.ed_note.setPlainText(self._initial.get("note", "") or "")

    def get_data(self) -> dict:
        return {
            "name": self.ed_name.text().strip(),
            "food_name": self.ed_food.text().strip(),
            "amount": float(self.sp_amount.value()),
            "unit": self.cb_unit.currentText().strip(),
            "note": self.ed_note.toPlainText().strip(),
        }

    def _on_save(self):
        data = self.get_data()
        if not data["name"]:
            ThemedMessageBox.warn(self, "Eksik Bilgi", "Şablon adı boş olamaz.")
            return
        self.accept()
