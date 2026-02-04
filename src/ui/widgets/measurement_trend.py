from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QComboBox
)

from src.services.measurements_service import MeasurementsService

# Matplotlib (Qt backend)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas


class MeasurementTrendPanel(QFrame):
    """Klinik Kart içinde kilo trend grafiği paneli."""

    def __init__(self, conn, client_id: str, log):
        super().__init__()
        self.setObjectName("Card")
        self.conn = conn
        self.client_id = client_id
        self.log = log
        self.svc = MeasurementsService(conn)

        root = QVBoxLayout(self)

        header = QHBoxLayout()
        title = QLabel("Ölçüm Trend", objectName="SectionTitle")
        header.addWidget(title)

        self.cmb_range = QComboBox()
        self.cmb_range.setObjectName("ComboBox")
        self.cmb_range.addItem("30 gün", 30)
        self.cmb_range.addItem("90 gün", 90)
        self.cmb_range.addItem("180 gün", 180)
        self.cmb_range.addItem("Tümü", None)
        self.cmb_range.currentIndexChanged.connect(self.refresh)

        header.addStretch(1)
        header.addWidget(self.cmb_range)
        root.addLayout(header)

        self.lbl_hint = QLabel("", objectName="FieldLabel")
        self.lbl_hint.setWordWrap(True)
        root.addWidget(self.lbl_hint)

        self.figure = Figure(figsize=(5, 2.2), dpi=100)
        self.figure.patch.set_facecolor("white")
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setMinimumHeight(180)
        root.addWidget(self.canvas)

        self.refresh()

    def refresh(self):
        try:
            days = self.cmb_range.currentData()
            points = self.svc.trend_points(self.client_id, days=days)
            self._render(points)
        except Exception as e:
            try:
                self.log.exception("Trend render failed: %s", e)
            except Exception:
                pass
            self.lbl_hint.setText("Trend çizimi sırasında hata oluştu.")
            self.figure.clear()
            self.canvas.draw_idle()

    def _render(self, points: list[tuple[str, float]]):
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        if len(points) < 2:
            self.lbl_hint.setText("Trend görüntülemek için en az 2 ölçüm gereklidir.")
            ax.axis("off")
            self.canvas.draw_idle()
            return

        self.lbl_hint.setText("")

        dates = []
        weights = []
        for d, w in points:
            try:
                dt = datetime.strptime(d, "%Y-%m-%d")
            except Exception:
                continue
            dates.append(dt)
            weights.append(w)

        # Basit çizim: çizgi + nokta
        ax.plot(dates, weights, marker="o", linewidth=2)

        ax.set_ylabel("Kilo (kg)")
        ax.grid(True, alpha=0.15)

        # X label format: DD.MM
        ax.tick_params(axis="x", rotation=0)
        labels = [dt.strftime("%d.%m") for dt in dates]
        ax.set_xticks(dates)
        ax.set_xticklabels(labels, fontsize=8)

        # Daha ferah görünsün
        self.figure.tight_layout(pad=1.0)
        self.canvas.draw_idle()
