from __future__ import annotations

import time
from PySide6.QtCore import Qt, QTimer, QEventLoop, QPropertyAnimation, QEasingCurve, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QProgressBar,
    QGraphicsOpacityEffect,
)


class PremiumSplash(QWidget):
    """Stabil, premium his veren açılış splash ekranı.

    Video/GIF gibi codec riskleri yoktur; tamamen Qt widget + animasyon.
    """

    # Emitted after fade-out finishes (so caller can safely show the main window).
    finished = Signal()

    def __init__(
        self,
        logo_path: str,
        title: str = "NutriNexus",
        subtitle: str = "Klinik Beslenme Yönetimi",
        minimum_visible_ms: int = 4500,
        size=(560, 320),
    ):
        super().__init__(None)
        self.minimum_visible_ms = int(minimum_visible_ms)
        self._t_show = None  # type: float | None

        self.setFixedSize(*size)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # Root container
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._card = QWidget(self)
        self._card.setObjectName("PremiumSplashCard")
        root.addWidget(self._card)

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(28, 22, 28, 18)
        card_layout.setSpacing(10)

        # Logo
        self._logo = QLabel(self._card)
        self._logo.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        pix = QPixmap(logo_path)
        if not pix.isNull():
            self._logo.setPixmap(pix.scaled(170, 170, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        card_layout.addWidget(self._logo, 0, Qt.AlignHCenter)

        # Title
        self._title = QLabel(title, self._card)
        self._title.setAlignment(Qt.AlignHCenter)
        self._title.setObjectName("PremiumSplashTitle")
        card_layout.addWidget(self._title)

        # Subtitle
        self._subtitle = QLabel(subtitle, self._card)
        self._subtitle.setAlignment(Qt.AlignHCenter)
        self._subtitle.setObjectName("PremiumSplashSubtitle")
        card_layout.addWidget(self._subtitle)

        card_layout.addSpacing(4)

        # Progress + dots
        self._progress = QProgressBar(self._card)
        self._progress.setObjectName("PremiumSplashProgress")
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setFixedHeight(8)
        card_layout.addWidget(self._progress)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(8)

        self._dots = QLabel("Yükleniyor", self._card)
        self._dots.setObjectName("PremiumSplashDots")
        bottom.addWidget(self._dots)
        bottom.addStretch(1)
        card_layout.addLayout(bottom)

        # Opacity effect for fade
        self._opacity_fx = QGraphicsOpacityEffect(self._card)
        self._opacity_fx.setOpacity(0.0)
        self._card.setGraphicsEffect(self._opacity_fx)

        self._fade_in = QPropertyAnimation(self._opacity_fx, b"opacity")
        self._fade_in.setDuration(420)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)

        self._fade_out = QPropertyAnimation(self._opacity_fx, b"opacity")
        self._fade_out.setDuration(260)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.InCubic)
        def _on_fade_out_done():
            # Notify caller first, then close.
            try:
                self.finished.emit()
            finally:
                self.close()

        self._fade_out.finished.connect(_on_fade_out_done)

        # Dots animation
        self._dots_i = 0
        self._dots_timer = QTimer(self)
        self._dots_timer.setInterval(350)
        self._dots_timer.timeout.connect(self._tick_dots)

        # Local stylesheet (keeps app theme intact)
        self.setStyleSheet(
            """
            QWidget#PremiumSplashCard {
                border-radius: 18px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(14, 116, 144, 220),
                    stop:1 rgba(17, 24, 39, 235)
                );
                border: 1px solid rgba(255,255,255,28);
            }
            QLabel#PremiumSplashTitle {
                color: rgba(255,255,255,235);
                font-size: 18px;
                font-weight: 700;
                letter-spacing: 0.2px;
                padding-top: 2px;
            }
            QLabel#PremiumSplashSubtitle {
                color: rgba(255,255,255,170);
                font-size: 11px;
                font-weight: 600;
                padding-bottom: 2px;
            }
            QProgressBar#PremiumSplashProgress {
                border: 1px solid rgba(255,255,255,40);
                background: rgba(255,255,255,22);
                border-radius: 4px;
            }
            QProgressBar#PremiumSplashProgress::chunk {
                background: rgba(255,255,255,150);
                border-radius: 4px;
            }
            QLabel#PremiumSplashDots {
                color: rgba(255,255,255,160);
                font-size: 10px;
                font-weight: 600;
            }
            """
        )

    def play(self) -> None:
        self._t_show = time.monotonic()
        self._dots_timer.start()
        self._fade_in.start()

    def _tick_dots(self) -> None:
        self._dots_i = (self._dots_i + 1) % 4
        self._dots.setText("Yükleniyor" + ("." * self._dots_i))

    def wait_ms(self, ms: int) -> None:
        """UI donmadan beklet."""
        loop = QEventLoop()
        QTimer.singleShot(int(ms), loop.quit)
        loop.exec()

    def close_with_fade(self) -> None:
        try:
            self._dots_timer.stop()
        except Exception:
            pass
        self._fade_out.start()
