from __future__ import annotations

from PySide6.QtCore import Qt, QPropertyAnimation
from PySide6.QtWidgets import QWidget, QVBoxLayout, QToolButton, QFrame, QSizePolicy


class CollapsibleSection(QWidget):
    """Basit, sağlam bir 'accordion' (açılır/kapanır) bölüm bileşeni."""

    def __init__(self, title: str, content: QWidget, *, expanded: bool = False, parent: QWidget | None = None):
        super().__init__(parent)

        self._btn = QToolButton()
        self._btn.setObjectName('AccordionHeader')
        self._btn.setText(title)
        self._btn.setCheckable(True)
        self._btn.setChecked(expanded)
        self._btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._btn.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self._btn.clicked.connect(self._on_toggled)

        self._content = QFrame()
        self._content.setObjectName('AccordionBody')
        self._content.setFrameShape(QFrame.NoFrame)
        self._content_lay = QVBoxLayout(self._content)
        self._content_lay.setContentsMargins(12, 12, 12, 12)
        self._content_lay.setSpacing(10)
        self._content_lay.addWidget(content)

        self._content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._content.setMaximumHeight(0 if not expanded else self._content.sizeHint().height())

        self._anim = QPropertyAnimation(self._content, b'maximumHeight', self)
        self._anim.setDuration(180)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(self._btn)
        lay.addWidget(self._content)

    def _on_toggled(self, checked: bool):
        self._btn.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        start = self._content.maximumHeight()
        end = self._content.sizeHint().height() if checked else 0
        self._anim.stop()
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.start()
