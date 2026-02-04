from __future__ import annotations

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QToolButton, QFrame


class CustomTitleBar(QFrame):
    """
    Frameless window title bar (logo + title + window controls).
    Works for both QMainWindow and QDialog.
    """
    def __init__(self, window: QWidget, title: str = "", logo_path: str | None = None, show_maximize: bool = True):
        super().__init__(window)
        self._window = window
        self._drag_pos: QPoint | None = None
        self.setObjectName("CustomTitleBar")
        # Slightly taller bar so the logo/title feel less cramped and never look "cropped"
        self.setFixedHeight(48)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 10, 0)
        lay.setSpacing(8)

        self.lbl_logo = QLabel()
        self.lbl_logo.setObjectName("TitleLogo")
        # Keep the logo crisp: scale with aspect ratio and center it.
        self.lbl_logo.setFixedSize(34, 34)
        self.lbl_logo.setAlignment(Qt.AlignCenter)
        self.lbl_logo.setScaledContents(False)
        if logo_path:
            try:
                pix = QPixmap(logo_path)
                if not pix.isNull():
                    self.lbl_logo.setPixmap(
                        pix.scaled(
                            self.lbl_logo.size(),
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation,
                        )
                    )
            except Exception:
                pass

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("TitleText")
        self.lbl_title.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        lay.addWidget(self.lbl_logo)
        lay.addWidget(self.lbl_title, 1)

        self.btn_min = QToolButton()
        self.btn_min.setObjectName("TitleBtnMin")
        self.btn_min.setText("–")
        self.btn_min.clicked.connect(self._window.showMinimized)
        lay.addWidget(self.btn_min)

        self.btn_max = QToolButton()
        self.btn_max.setObjectName("TitleBtnMax")
        self.btn_max.setText("□")
        self.btn_max.clicked.connect(self._toggle_max_restore)
        self.btn_max.setVisible(show_maximize)
        lay.addWidget(self.btn_max)

        self.btn_close = QToolButton()
        self.btn_close.setObjectName("TitleBtnClose")
        self.btn_close.setText("✕")
        self.btn_close.clicked.connect(self._window.close)
        lay.addWidget(self.btn_close)

    def _toggle_max_restore(self):
        # QDialog may not support maximize; ignore safely
        try:
            if self._window.isMaximized():
                self._window.showNormal()
            else:
                self._window.showMaximized()
        except Exception:
            return

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        # double-click to maximize/restore (like native title bar)
        if event.button() == Qt.LeftButton and self.btn_max.isVisible():
            self._toggle_max_restore()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)
