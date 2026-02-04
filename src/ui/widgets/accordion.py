from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QToolButton, QFrame


class AccordionSection(QWidget):
    """Basit, sağlam accordion bölümü.

    QToolBox bazı Windows/Qt tema kombinasyonlarında başlık metnini göstermeyebiliyor.
    Bu widget, tamamen bizim kontrolümüzde olan QToolButton + içerik frame ile çalışır.

    - Başlık butonu: checkable
    - İçerik: QFrame içinde, aç/kapa ile görünürlük değişir
    """

    def __init__(self, title: str, content: QWidget, *, expanded: bool = False, parent: QWidget | None = None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self.btn = QToolButton()
        self.btn.setObjectName("AccHeader")
        self.btn.setText(title)
        self.btn.setCheckable(True)
        self.btn.setChecked(expanded)
        self.btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)

        self.content_frame = QFrame()
        self.content_frame.setObjectName("AccContent")
        self.content_frame.setFrameShape(QFrame.NoFrame)

        c_lay = QVBoxLayout(self.content_frame)
        c_lay.setContentsMargins(12, 12, 12, 12)
        c_lay.setSpacing(10)
        c_lay.addWidget(content)

        self.content_frame.setVisible(expanded)

        root.addWidget(self.btn)
        root.addWidget(self.content_frame)

        self.btn.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool) -> None:
        self.content_frame.setVisible(checked)
        self.btn.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
