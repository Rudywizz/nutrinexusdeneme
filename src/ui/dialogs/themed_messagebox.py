from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QWidget

class ThemedMessageBox(QDialog):
    def __init__(self, parent: QWidget | None, title: str, text: str, kind: str = "info", buttons=("Tamam",)):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(12)

        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.PlainText)
        root.addWidget(lbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        self._result = None
        self._btns = []
        for b in buttons:
            btn = QPushButton(b)
            btn.setMinimumWidth(96)
            btn.clicked.connect(lambda _, t=b: self._on_btn(t))
            self._btns.append(btn)
            btn_row.addWidget(btn)

        root.addLayout(btn_row)

        # light look to avoid OS dark popup
        self.setStyleSheet("""
            QDialog { background: #F5F7FA; }
            QLabel { color: #0F172A; font-size: 12px; }
            QPushButton { padding: 8px 14px; border-radius: 10px; background: #E9EEF5; border: 1px solid #D6DEE8; }
            QPushButton:hover { background: #DDE6F2; }
            QPushButton:pressed { background: #D0DBEA; }
        """)

    def _on_btn(self, text: str):
        self._result = text
        self.accept()

    @staticmethod
    def info(parent, title: str, text: str):
        dlg = ThemedMessageBox(parent, title, text, "info", buttons=("Tamam",))
        dlg.exec()
        return True

    @staticmethod
    def warn(parent, title: str, text: str):
        dlg = ThemedMessageBox(parent, title, text, "warn", buttons=("Tamam",))
        dlg.exec()
        return True

    @staticmethod
    def error(parent, title: str, text: str):
        dlg = ThemedMessageBox(parent, title, text, "error", buttons=("Tamam",))
        dlg.exec()
        return True

    @staticmethod
    def confirm(parent, title: str, text: str, yes_text="Evet", no_text="Vazgeç") -> bool:
        dlg = ThemedMessageBox(parent, title, text, "confirm", buttons=(no_text, yes_text))
        dlg.exec()
        return dlg._result == yes_text
