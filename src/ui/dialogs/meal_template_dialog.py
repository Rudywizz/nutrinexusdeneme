from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton
)

from src.ui.dialogs.themed_messagebox import ThemedMessageBox


class MealTemplateDialog(QDialog):
    def __init__(self, parent=None, *, title: str = "Öğün Şablonu", initial: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)

        self._initial = initial or {}

        lay = QVBoxLayout(self)

        header = QLabel(title)
        header.setObjectName("DialogTitle")
        lay.addWidget(header)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Şablon Adı"))
        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("Örn: 'Kahvaltı - Standart' / 'Antrenman Öncesi'")
        row1.addWidget(self.ed_name, 1)
        lay.addLayout(row1)

        lay.addWidget(QLabel("İçerik"))
        self.ed_content = QTextEdit()
        self.ed_content.setPlaceholderText("Örn:\n- 2 yumurta\n- 60g yulaf\n- 1 muz\n\nNot: Sprint 6.1.1'de bunu besin kataloğuna bağlayıp tek tık ekleme yapacağız.")
        self.ed_content.setMinimumHeight(180)
        lay.addWidget(self.ed_content)

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

    def _apply_initial(self):
        self.ed_name.setText(self._initial.get("name", "") or "")
        self.ed_content.setPlainText(self._initial.get("content", "") or "")

    def get_data(self) -> dict:
        return {
            "name": self.ed_name.text().strip(),
            "content": self.ed_content.toPlainText().strip(),
        }

    def _on_save(self):
        data = self.get_data()
        if not data["name"]:
            ThemedMessageBox.warn(self, "Eksik Bilgi", "Şablon adı boş olamaz.")
            return
        self.accept()
