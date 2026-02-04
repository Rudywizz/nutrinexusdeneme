from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Optional, List, Dict, Tuple

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QBrush, QFont, QPainter, QPen, QKeySequence, QShortcut, QPolygonF
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, QComboBox,
    QLineEdit, QGridLayout, QListWidget, QListWidgetItem, QSizePolicy, QSpacerItem, QTabWidget,
    QProgressBar
)

# NOTE:
# - Bu ekran sadece Dashboard modülüdür.
# - Mevcut stabil modüllere dokunmadan, state.conn üzerinden salt-okuma sorgular çalışır.
# - open_client_detail_cb verildiyse "Hızlı Aksiyon" ile danışan detay penceresi açılır.


@dataclass
class DashboardMetrics:
    client_id: str
    client_name: str
    status_label: str          # "Stabil" / "Dikkat" / "Risk"
    status_hint: str           # kısa açıklama
    status_action: str        # kısa öneri

    target_kcal: float
    intake_kcal_today: float
    intake_kcal_7d_avg: Optional[float]
    energy_near_days_7d: int
    energy_window_days: int
    kcal_diff_today: float
    energy_dev_series_7d: List[Optional[float]]

    weight_series: List[float]
    waist_series: List[float]
    weight_last: Optional[float]
    waist_last: Optional[float]
    weight_delta_30d: Optional[float]
    waist_delta_30d: Optional[float]

    # Trend güncelliği (vitrin hissi için)
    last_meas_date: Optional[date]
    last_meas_age_days: Optional[int]

    adherence_7d: Optional[float]   # 0-100
    adherence_hint: str

    # alerts: List[(level, text)] level: "risk" | "dikkat" | "info"
    alerts: List[Tuple[str, str]]


_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def _safe_float(x) -> Optional[float]:
    try:
        if x is None:
            return None
        v = float(x)
        if v != v:  # NaN
            return None
        return v
    except Exception:
        return None


def _sparkline(values: List[float]) -> str:
    vals = [v for v in values if v is not None]
    if not vals:
        return "—"
    if len(vals) == 1:
        return "▇"
    mn, mx = min(vals), max(vals)
    if mx - mn < 1e-9:
        return "▇" * min(12, len(vals))
    out = []
    for v in vals[-24:]:  # son 24 nokta, UI'da temiz dursun
        idx = int((v - mn) / (mx - mn) * (len(_SPARK_CHARS) - 1))
        idx = max(0, min(len(_SPARK_CHARS) - 1, idx))
        out.append(_SPARK_CHARS[idx])
    return "".join(out)

class SparklineWidget(QWidget):
    """Basit, stabil mini trend çizimi (sparkline).
    - values: float listesi (None filtrelenir)
    - Tek nokta varsa küçük bir nokta olarak gösterilir (siyah blok yok).
    """

    def __init__(self, *, line_alpha: float = 0.55, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._values: List[float] = []
        self._line_alpha = line_alpha
        self._ref_value: Optional[float] = None
        self.setMinimumHeight(26)
        self.setMaximumHeight(26)

        # UI görünümü: label'daki premium kutu hissi
        self.setStyleSheet(
            "background: rgba(0,0,0,0.03);"
            "border:1px solid rgba(0,0,0,0.08);"
            "border-radius:10px;"
            "padding:6px 10px;"
        )

    def set_values(self, values: List[float]):
        vals = [v for v in (values or []) if v is not None]
        # UI'da temiz dursun: son 30 nokta yeter
        self._values = vals[-30:]
        self.update()

    def set_reference(self, value: Optional[float]):
        """Sparkline için referans çizgisi (örn. 0 çizgisi). None -> kapat."""
        self._ref_value = _safe_float(value)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)

        rect = self.rect().adjusted(10, 8, -10, -8)  # padding'e uygun çizim alanı
        if rect.width() <= 0 or rect.height() <= 0:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        vals = self._values
        if not vals:
            # boş durumda ince bir çizgi (çok belli olmayan)
            pen = QPen(QColor(0, 0, 0, int(255 * 0.10)))
            pen.setWidthF(1.0)
            p.setPen(pen)
            y = rect.center().y()
            p.drawLine(rect.left(), y, rect.right(), y)
            return

        mn, mx = min(vals), max(vals)

        ref = self._ref_value
        if ref is not None:
            mn = min(mn, ref)
            mx = max(mx, ref)
        if abs(mx - mn) < 1e-9:
            # sabit seri: düz çizgi
            y = rect.center().y()
            pen = QPen(QColor(0, 0, 0, int(255 * self._line_alpha)))
            pen.setWidthF(1.6)
            p.setPen(pen)
            p.drawLine(rect.left(), y, rect.right(), y)
            # son noktayı minik vurgula
            dot_pen = QPen(QColor(0, 0, 0, int(255 * 0.70)))
            dot_pen.setWidthF(3.6)
            p.setPen(dot_pen)
            p.drawPoint(rect.right(), y)
            return

        # Noktaları x ekseninde eşit dağıt
        n = len(vals)
        if n == 1:
            # tek nokta: kare blok yerine küçük nokta
            pen = QPen(QColor(0, 0, 0, int(255 * 0.70)))
            pen.setWidthF(4.0)
            p.setPen(pen)
            p.drawPoint(rect.center())
            return

        def map_point(i: int, v: float):
            x = rect.left() + (rect.width() * i / (n - 1))
            # yüksek değer üstte görünsün diye tersle
            y = rect.bottom() - (rect.height() * (v - mn) / (mx - mn))
            return x, y

        # Referans çizgisi (örn. hedef çizgisi / 0 çizgisi)
        if self._ref_value is not None and abs(mx - mn) >= 1e-9:
            _, yref = map_point(0, self._ref_value)
            pen_ref = QPen(QColor(0, 0, 0, int(255 * 0.18)))
            pen_ref.setWidthF(1.0)
            pen_ref.setStyle(Qt.DashLine)
            p.setPen(pen_ref)
            p.drawLine(rect.left(), yref, rect.right(), yref)

        
        # Hafif pozitif/negatif dolgu (yalnızca referans çizgisi varken; karar destek için)
        if self._ref_value is not None and n >= 2 and abs(mx - mn) >= 1e-9:
            # ref çizgisine karşılaştırma: v > ref => "üstte" (pozitif), v < ref => "altta" (negatif)
            # Çok düşük alfa ile kurumsal ve göz yormayan bir vurgu
            pos_brush = QBrush(QColor(0, 120, 0, 28))   # çok hafif yeşil
            neg_brush = QBrush(QColor(180, 0, 0, 24))   # çok hafif kırmızı

            # Önce tüm noktaları hesapla
            pts = [map_point(i, vals[i]) for i in range(n)]
            vref = self._ref_value
            _, yref = map_point(0, vref)

            def _interp(x1, y1, v1, x2, y2, v2):
                # v1 ile v2 arasında ref kesişimi (lineer)
                if abs(v2 - v1) < 1e-9:
                    return x1, yref
                t = (vref - v1) / (v2 - v1)
                t = max(0.0, min(1.0, t))
                xi = x1 + (x2 - x1) * t
                yi = y1 + (y2 - y1) * t
                return xi, yi

            p.setPen(Qt.NoPen)

            for i in range(n - 1):
                x1, y1 = pts[i]
                x2, y2 = pts[i + 1]
                v1 = vals[i]
                v2 = vals[i + 1]

                # Segment tamamen üstte / altta
                if (v1 >= vref and v2 >= vref):
                    p.setBrush(pos_brush)
                    poly = QPolygonF([QPointF(x1, y1)(x2, y2)(x2, yref)(x1, yref)])
                    p.drawPolygon(poly)
                elif (v1 <= vref and v2 <= vref):
                    p.setBrush(neg_brush)
                    poly = QPolygonF([QPointF(x1, y1)(x2, y2)(x2, yref)(x1, yref)])
                    p.drawPolygon(poly)
                else:
                    # ref çizgisini kesiyor: iki parçaya böl
                    xi, yi = _interp(x1, y1, v1, x2, y2, v2)
                    if v1 > vref:
                        # ilk parça pozitif
                        p.setBrush(pos_brush)
                        poly1 = QPolygonF([QPointF(x1, y1)(xi, yi)(xi, yref)(x1, yref)])
                        p.drawPolygon(poly1)
                        # ikinci parça negatif
                        p.setBrush(neg_brush)
                        poly2 = QPolygonF([QPointF(xi, yi)(x2, y2)(x2, yref)(xi, yref)])
                        p.drawPolygon(poly2)
                    else:
                        # ilk parça negatif
                        p.setBrush(neg_brush)
                        poly1 = QPolygonF([QPointF(x1, y1)(xi, yi)(xi, yref)(x1, yref)])
                        p.drawPolygon(poly1)
                        # ikinci parça pozitif
                        p.setBrush(pos_brush)
                        poly2 = QPolygonF([QPointF(xi, yi)(x2, y2)(x2, yref)(xi, yref)])
                        p.drawPolygon(poly2)

            # Çizgi tekrar görünürken pen'i geri verilecek
# Çizgi
        pen = QPen(QColor(0, 0, 0, int(255 * self._line_alpha)))
        pen.setWidthF(1.7)
        p.setPen(pen)

        prev_x, prev_y = map_point(0, vals[0])
        for i in range(1, n):
            x, y = map_point(i, vals[i])
            p.drawLine(prev_x, prev_y, x, y)
            prev_x, prev_y = x, y

        # son nokta vurgusu
        pen2 = QPen(QColor(0, 0, 0, int(255 * 0.75)))
        pen2.setWidthF(3.8)
        p.setPen(pen2)
        p.drawPoint(prev_x, prev_y)


def _iso(d: date) -> str:
    return d.isoformat()


class DashboardScreen(QWidget):
    def __init__(
        self,
        state=None,
        log=None,
        open_client_detail_cb: Optional[Callable[[dict], None]] = None
    ):
        super().__init__()
        self.state = state
        self.log = log
        self.open_client_detail_cb = open_client_detail_cb

        self._client_id: Optional[str] = None
        self._clients: List[Tuple[str, str]] = []  # (id, name)

        # Trend penceresi (Dashboard'a özel): 7g / 30g
        # Sadece sparkline veri aralığını etkiler; diğer metrikler/30g delta sabit kalır.
        self._trend_window_days: int = 30

        # Basit metrik cache: aynı danışan + aynı trend penceresi için tekrar DB okumayı azaltır.
        # Not: 'Yenile' butonu cache'i temizler.
        self._metrics_cache: Dict[Tuple[str, int], DashboardMetrics] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        # Header
        header = QHBoxLayout()
        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")
        header.addWidget(title)

        header.addStretch(1)

        self.search = QLineEdit()
        self.search.setObjectName("Input")
        self.search.setPlaceholderText("Danışan ara…")
        self.search.setFixedWidth(260)
        header.addWidget(self.search)

        self.cbo_clients = QComboBox()
        self.cbo_clients.setObjectName("Input")
        self.cbo_clients.setFixedWidth(320)
        header.addWidget(self.cbo_clients)

        self.btn_refresh = QPushButton("Yenile")
        self.btn_refresh.setObjectName("SecondaryBtn")
        header.addWidget(self.btn_refresh)

        self.lbl_updated = QLabel("")
        self.lbl_updated.setTextFormat(Qt.PlainText)
        self.lbl_updated.setStyleSheet("color: rgba(0,0,0,0.55); padding-left:8px;")
        header.addWidget(self.lbl_updated)

        root.addLayout(header)

        # Kısayollar: hızlı kullanım
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self._focus_search)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._focus_search)
        QShortcut(QKeySequence("F5"), self, activated=self.hard_refresh)

        # Content grid (cards)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        root.addLayout(grid, 1)

        # Status card (wide)
        self.card_status = self._card("Durum Özeti")
        self.lbl_status_badge = QLabel("—")
        self._apply_badge_style(self.lbl_status_badge, "stabil")
        self.lbl_status_badge.setAlignment(Qt.AlignCenter)
        self.lbl_status_badge.setFixedHeight(34)
        self.lbl_status_badge.setMinimumWidth(110)

        self.lbl_status_hint = QLabel("Danışan seçildiğinde özet burada görünecek.")
        self.lbl_status_hint.setWordWrap(True)

        status_row = QHBoxLayout()
        status_row.addWidget(self.lbl_status_badge, 0, Qt.AlignLeft)
        status_row.addSpacing(10)
        status_row.addWidget(self.lbl_status_hint, 1)

        self.card_status.body.addLayout(status_row)

        # Energy card
        self.card_energy = self._card("Günlük Enerji Dengesi")
        self.lbl_target = QLabel("Hedef: — kcal")
        self.lbl_intake = QLabel("Alınan: — kcal")
        self.lbl_intake_7d = QLabel("7g ortalama: — kcal")
        self.lbl_energy_near = QLabel("Hedefe yakın: —/7")
        self.lbl_diff = QLabel("Fark: — kcal")
        for lbl in (self.lbl_target, self.lbl_intake, self.lbl_diff):
            lbl.setStyleSheet("font-size: 12pt; font-weight: 700;")
        self.lbl_intake_7d.setStyleSheet("font-size: 10.5pt; font-weight: 700; color: rgba(0,0,0,0.65);")
        self.lbl_energy_near.setStyleSheet("font-size: 10.5pt; font-weight: 650; color: rgba(0,0,0,0.60);")
        self.card_energy.body.addWidget(self.lbl_target)
        self.card_energy.body.addWidget(self.lbl_intake)
        self.card_energy.body.addWidget(self.lbl_intake_7d)
        self.card_energy.body.addWidget(self.lbl_energy_near)

        # 7g sapma mini trend (sparkline)
        self.lbl_energy_trend = QLabel("7g sapma trendi")
        self.lbl_energy_trend.setStyleSheet("font-size: 10pt; font-weight: 650; color: rgba(0,0,0,0.55);")
        self.energy_spark = SparklineWidget(line_alpha=0.45)
        self.card_energy.body.addWidget(self.lbl_energy_trend)
        self.card_energy.body.addWidget(self.energy_spark)

        # Mini progress bar (hedefe yaklaşma)
        self.pb_energy = QProgressBar()
        self.pb_energy.setTextVisible(False)
        self.pb_energy.setFixedHeight(10)
        self.pb_energy.setRange(0, 100)
        self.pb_energy.setValue(0)
        self.pb_energy.setObjectName("EnergyProgress")
        self.pb_energy.setStyleSheet(
            "QProgressBar{background: rgba(0,0,0,0.06); border: 1px solid rgba(0,0,0,0.10); "
            "border-radius: 5px; }"
            "QProgressBar::chunk{border-radius: 5px; background: rgba(28,170,108,0.75);}"
        )
        self.lbl_energy_note = QLabel("")
        self.lbl_energy_note.setWordWrap(True)
        self.lbl_energy_note.setStyleSheet("font-size: 10.5pt; font-weight: 650; color: rgba(0,0,0,0.65);")
        self.card_energy.body.addWidget(self.pb_energy)
        self.card_energy.body.addWidget(self.lbl_energy_note)

        self.card_energy.body.addWidget(self.lbl_diff)

        # Trend card
        self.card_trend = self._card("Kilo & Bel Trendleri")

        # Üst sağ: trend penceresi seçimi + son ölçüm etiketi
        self.btn_trend_7 = QPushButton("7g")
        self.btn_trend_30 = QPushButton("30g")
        for b in (self.btn_trend_7, self.btn_trend_30):
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(28)
            b.setFixedWidth(48)
            b.setObjectName("SegBtn")

        self.btn_trend_30.setChecked(True)

        # mini etiket: son ölçüm tarihi (GG.AA.YYYY)
        self.lbl_last_meas = QLabel("Son ölçüm: —")
        self.lbl_last_meas.setStyleSheet(
            "font-size: 10pt; font-weight: 700; color: rgba(0,0,0,0.60);"
            "background: rgba(0,0,0,0.03); border:1px solid rgba(0,0,0,0.08);"
            "border-radius:10px; padding:4px 8px;"
        )
        meas_row = QHBoxLayout()
        meas_row.addStretch(1)
        meas_row.addWidget(self.btn_trend_7, 0, Qt.AlignRight)
        meas_row.addWidget(self.btn_trend_30, 0, Qt.AlignRight)
        meas_row.addWidget(self.lbl_last_meas, 0, Qt.AlignRight)
        self.card_trend.body.addLayout(meas_row)

        self.lbl_weight = QLabel("Kilo: —")
        self.lbl_weight = QLabel("Kilo: —")
        self.weight_spark = SparklineWidget()
        self.lbl_waist = QLabel("Bel: —")
        self.waist_spark = SparklineWidget()
        for lbl in (self.lbl_weight, self.lbl_waist):
            lbl.setStyleSheet("font-size: 11.5pt; font-weight: 750;")
        self.card_trend.body.addWidget(self.lbl_weight)
        self.card_trend.body.addWidget(self.weight_spark)
        self.card_trend.body.addSpacing(8)
        self.card_trend.body.addWidget(self.lbl_waist)
        self.card_trend.body.addWidget(self.waist_spark)

        self.lbl_trend_meta = QLabel("")
        self.lbl_trend_meta.setWordWrap(True)
        self.lbl_trend_meta.setStyleSheet("font-size: 10pt; color: rgba(0,0,0,0.60);")
        self.card_trend.body.addWidget(self.lbl_trend_meta)

        # Adherence card
        self.card_adherence = self._card("Plan / Takip Uyum Oranı")
        self.lbl_adherence = QLabel("—")
        self.lbl_adherence.setStyleSheet("font-size: 18pt; font-weight: 900;")
        self.lbl_adherence_hint = QLabel("")
        self.lbl_adherence_hint.setWordWrap(True)
        self.card_adherence.body.addWidget(self.lbl_adherence)
        self.card_adherence.body.addWidget(self.lbl_adherence_hint)

        # Alerts card
        self.card_alerts = self._card("Otomatik Uyarılar")
        self.list_alerts = QListWidget()
        self.list_alerts.setObjectName("Input")
        self.list_alerts.setStyleSheet("QListWidget{padding:6px;} QListWidget::item{padding:6px;}")
        self.list_alerts.itemClicked.connect(self._on_alert_clicked)
        self.card_alerts.body.addWidget(self.list_alerts)

        # Actions card
        self.card_actions = self._card("Hızlı Aksiyonlar")
        actions_row = QHBoxLayout()
        self.btn_open_measure = QPushButton("Ölçüm")
        self.btn_open_cons = QPushButton("Tüketim")
        self.btn_open_plan = QPushButton("Plan")
        self.btn_open_pdf = QPushButton("PDF")

        self.btn_open_measure.setToolTip("Danışan detayında Klinik Kart sekmesini açar")
        self.btn_open_cons.setToolTip("Danışan detayında Besin Tüketim sekmesini açar")
        self.btn_open_plan.setToolTip("Danışan detayında Diyet Planları sekmesini açar")
        self.btn_open_pdf.setToolTip("Danışan detayında Raporlar sekmesini açar")

        for b in (self.btn_open_measure, self.btn_open_cons, self.btn_open_plan, self.btn_open_pdf):
            b.setObjectName("PrimaryBtn")
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        actions_row.addWidget(self.btn_open_measure)
        actions_row.addWidget(self.btn_open_cons)
        actions_row.addWidget(self.btn_open_plan)
        actions_row.addWidget(self.btn_open_pdf)
        self.card_actions.body.addLayout(actions_row)

        # Place cards in grid
        # Grid düzeni: vitrin hissi için hizalama + minimum yükseklikler
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        # Aynı satırdaki kartları aynı minimum yükseklikte tutarak daha kurumsal görünüm
        self.card_energy.frame.setMinimumHeight(240)
        self.card_trend.frame.setMinimumHeight(240)
        self.card_adherence.frame.setMinimumHeight(220)
        self.card_alerts.frame.setMinimumHeight(220)
        self.card_status.frame.setMinimumHeight(140)
        self.card_actions.frame.setMinimumHeight(110)

        for fr in (
            self.card_status.frame, self.card_energy.frame, self.card_trend.frame,
            self.card_adherence.frame, self.card_alerts.frame, self.card_actions.frame
        ):
            fr.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        grid.addWidget(self.card_status.frame, 0, 0, 1, 2)
        grid.addWidget(self.card_energy.frame, 1, 0)
        grid.addWidget(self.card_trend.frame, 1, 1)
        grid.addWidget(self.card_adherence.frame, 2, 0)
        grid.addWidget(self.card_alerts.frame, 2, 1)
        grid.addWidget(self.card_actions.frame, 3, 0, 1, 2)

        # bottom stretch
        root.addItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))

        # Signals
        self.btn_refresh.clicked.connect(self.hard_refresh)
        self.cbo_clients.currentIndexChanged.connect(self._on_client_changed)
        self.search.textChanged.connect(self._apply_search_filter)

        # Trend penceresi (sparkline): 7g / 30g
        self.btn_trend_7.clicked.connect(lambda: self._set_trend_window(7))
        self.btn_trend_30.clicked.connect(lambda: self._set_trend_window(30))
        self._apply_segment_styles()

        # Actions: şimdilik danışan detay ekranını açar; ilgili sekmeye kullanıcı geçer.
        self.btn_open_measure.clicked.connect(lambda: self._open_client_detail("Klinik Kart"))
        self.btn_open_cons.clicked.connect(lambda: self._open_client_detail("Besin Tüketim"))
        self.btn_open_plan.clicked.connect(lambda: self._open_client_detail("Diyet Planları"))
        self.btn_open_pdf.clicked.connect(lambda: self._open_client_detail("Raporlar"))

        self._load_clients()
        self._apply_search_filter()

    # ---------- UI helpers ----------

    class _Card:
        def __init__(self, frame: QFrame, body: QVBoxLayout):
            self.frame = frame
            self.body = body

    def _card(self, title: str) -> _Card:
        frame = QFrame()
        frame.setObjectName("Card")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        t = QLabel(title)
        t.setObjectName("SectionTitle")
        lay.addWidget(t)

        body = QVBoxLayout()
        body.setSpacing(8)
        lay.addLayout(body)

        return self._Card(frame, body)

    def _apply_badge_style(self, lbl: QLabel, level: str) -> None:
        # level: stabil / dikkat / risk
        if level == "risk":
            bg = "rgba(188, 35, 60, 0.12)"
            bd = "rgba(188, 35, 60, 0.30)"
            fg = "rgba(120, 10, 28, 0.95)"
        elif level == "dikkat":
            bg = "rgba(245, 163, 26, 0.16)"
            bd = "rgba(245, 163, 26, 0.40)"
            fg = "rgba(120, 72, 0, 0.95)"
        else:
            bg = "rgba(28, 170, 108, 0.14)"
            bd = "rgba(28, 170, 108, 0.34)"
            fg = "rgba(0, 76, 42, 0.95)"

        lbl.setStyleSheet(
            f"QLabel{{background:{bg}; border:1px solid {bd}; border-radius:16px; "
            f"padding:6px 12px; color:{fg}; font-weight:900; font-size:11.5pt; letter-spacing:0.3px;}}"
        )

    def _apply_segment_styles(self) -> None:
        """7g/30g segment butonlarının stilini seçime göre uygular."""
        def style_for(checked: bool) -> str:
            if checked:
                return (
                    "QPushButton{background: rgba(0,0,0,0.10); border:1px solid rgba(0,0,0,0.18);"
                    "border-radius:10px; font-weight:900; color: rgba(0,0,0,0.85);}"
                    "QPushButton:hover{background: rgba(0,0,0,0.12);}"
                )
            return (
                "QPushButton{background: rgba(0,0,0,0.03); border:1px solid rgba(0,0,0,0.10);"
                "border-radius:10px; font-weight:800; color: rgba(0,0,0,0.60);}"
                "QPushButton:hover{background: rgba(0,0,0,0.06);}"
            )

        self.btn_trend_7.setStyleSheet(style_for(self.btn_trend_7.isChecked()))
        self.btn_trend_30.setStyleSheet(style_for(self.btn_trend_30.isChecked()))

    def _set_trend_window(self, days: int) -> None:
        days = 7 if int(days) == 7 else 30
        self._trend_window_days = days
        self.btn_trend_7.setChecked(days == 7)
        self.btn_trend_30.setChecked(days == 30)
        self._apply_segment_styles()
        self.refresh()

    # ---------- Data loading ----------

    def _load_clients(self) -> None:
        self.cbo_clients.blockSignals(True)
        self.cbo_clients.clear()
        self._clients = []

        if not self.state or not getattr(self.state, "conn", None):
            self.cbo_clients.addItem("DB bağlantısı yok", "")
            self.cbo_clients.blockSignals(False)
            return

        try:
            cur = self.state.conn.cursor()
            cur.execute(
                "SELECT id, full_name FROM clients WHERE is_active=1 ORDER BY full_name COLLATE NOCASE"
            )
            rows = cur.fetchall() or []
            self._clients = [(r[0], r[1]) for r in rows]
        except Exception:
            self._clients = []

        if not self._clients:
            self.cbo_clients.addItem("Aktif danışan yok", "")
            self._client_id = None
        else:
            for cid, name in self._clients:
                self.cbo_clients.addItem(name, cid)
            # default: ilk danışan
            self._client_id = self.cbo_clients.currentData()

        self.cbo_clients.blockSignals(False)
        self.refresh()

    def _apply_search_filter(self) -> None:
        text = (self.search.text() or "").strip().lower()
        current_id = self._client_id

        self.cbo_clients.blockSignals(True)
        self.cbo_clients.clear()

        filtered = []
        for cid, name in self._clients:
            if not text or text in (name or "").lower():
                filtered.append((cid, name))

        if not filtered:
            self.cbo_clients.addItem("Sonuç yok", "")
            self._client_id = None
        else:
            for cid, name in filtered:
                self.cbo_clients.addItem(name, cid)
            # eski seçim varsa koru
            if current_id:
                idx = self.cbo_clients.findData(current_id)
                if idx >= 0:
                    self.cbo_clients.setCurrentIndex(idx)
                    self._client_id = current_id
                else:
                    self._client_id = self.cbo_clients.currentData()
            else:
                self._client_id = self.cbo_clients.currentData()

        self.cbo_clients.blockSignals(False)
        self.refresh()


    def _focus_search(self) -> None:
        try:
            self.search.setFocus(Qt.ShortcutFocusReason)
            self.search.selectAll()
        except Exception:
            pass

    def hard_refresh(self) -> None:
        """UI + cache yenile. Danışan listesini tekrar okur, seçimi mümkünse korur."""
        prev_id = self._client_id
        self._metrics_cache.clear()
        try:
            # client list reload
            self._load_clients()
            if prev_id:
                idx = self.cbo_clients.findData(prev_id)
                if idx >= 0:
                    self.cbo_clients.setCurrentIndex(idx)
                    self._client_id = prev_id
        except Exception:
            pass
        self.refresh()
    def _on_client_changed(self, _idx: int) -> None:
        self._client_id = self.cbo_clients.currentData()
        self.refresh()

    def _open_client_detail(self, tab_text: str | None = None) -> None:
        if not self._client_id or not self.open_client_detail_cb or not self.state:
            return
        try:
            cur = self.state.conn.cursor()
            cur.execute("SELECT id, full_name, phone, birth_date, gender, is_active FROM clients WHERE id=?", (self._client_id,))
            row = cur.fetchone()
            if not row:
                return
            client = {
                "id": row[0],
                "full_name": row[1],
                "phone": row[2],
                "birth_date": row[3],
                "gender": row[4],
                "is_active": row[5],
            }
            win = self.open_client_detail_cb(client)
            try:
                if tab_text and win is not None:
                    tabs = win.findChild(QTabWidget, "ClientTabs")
                    if tabs is not None:
                        for i in range(tabs.count()):
                            if tabs.tabText(i).strip() == tab_text:
                                tabs.setCurrentIndex(i)
                                break
            except Exception:
                pass
        except Exception:
            return

    def _on_alert_clicked(self, item: QListWidgetItem) -> None:
        """Uyarıya tıklanınca ilgili sekmeye odaklanır.
        Stabil modüllere dokunmadan, sadece mevcut danışan detayı penceresini açıp tab seçer.
        """
        if not item:
            return

        # Öncelik: item içine koyduğumuz hedef sekme
        tab_text = item.data(Qt.UserRole)
        if isinstance(tab_text, str) and tab_text.strip():
            self._open_client_detail(tab_text.strip())
            return

        # Fallback: metinden sezgisel eşleştirme
        t = (item.text() or "").lower()
        if any(k in t for k in ["ölçüm", "kilo", "bel"]):
            self._open_client_detail("Klinik Kart")
        elif any(k in t for k in ["tüketim", "kcal", "enerji", "hedef"]):
            self._open_client_detail("Besin Tüketim")
        elif "plan" in t:
            self._open_client_detail("Diyet Planları")
        elif any(k in t for k in ["pdf", "rapor"]):
            self._open_client_detail("Raporlar")

    # ---------- Metrics computation ----------

    def refresh(self) -> None:
        if not self._client_id or not self.state or not getattr(self.state, "conn", None):
            self._render_empty()
            try:
                self.lbl_updated.setText("")
            except Exception:
                pass
            return

        try:
            key = (self._client_id, int(getattr(self, "_trend_window_days", 30) or 30))
            if key in self._metrics_cache:
                metrics = self._metrics_cache[key]
            else:
                metrics = self._compute_metrics(self._client_id)
                self._metrics_cache[key] = metrics
            self._render(metrics)
            # küçük güncelleme etiketi
            try:
                self.lbl_updated.setText(datetime.now().strftime("Güncellendi: %H:%M"))
            except Exception:
                pass
        except Exception:
            self._render_empty(error=True)
            try:
                self.lbl_updated.setText("")
            except Exception:
                pass
    def _render_empty(self, error: bool = False) -> None:
        self.lbl_status_badge.setText("—")
        self._apply_badge_style(self.lbl_status_badge, "dikkat" if error else "stabil")
        self.lbl_status_hint.setText("Danışan seçiniz." if not error else "Dashboard verileri okunamadı (DB / veri).")

        self.lbl_target.setText("Hedef: — kcal")
        self.lbl_intake.setText("Alınan: — kcal")
        if hasattr(self, "lbl_intake_7d"):
            self.lbl_intake_7d.setText("7g ortalama: — kcal")
        if hasattr(self, "lbl_energy_near"):
            self.lbl_energy_near.setText("Hedefe yakın: —/7")
        self.lbl_diff.setText("Fark: — kcal")
        self.pb_energy.setValue(0)
        self.pb_energy.setVisible(False)
        self.lbl_energy_note.setText("")
        if hasattr(self, "energy_spark"):
            self.energy_spark.set_values([])
            self.energy_spark.set_reference(None)

        # 7g sapma sparkline (hedef varsa kcal farkı, yoksa alınan kcal)
        if hasattr(self, "energy_spark"):
            self.energy_spark.set_values(m.energy_dev_series_7d or [])
            # Hedef varsa sapma serisi 0 çizgisine göre okunmalı
            if getattr(m, 'target_kcal', 0) and m.target_kcal > 0:
                self.energy_spark.set_reference(0.0)
            else:
                self.energy_spark.set_reference(None)

        self.lbl_weight.setText("Kilo: —")
        self.weight_spark.set_values([])
        self.lbl_waist.setText("Bel: —")
        self.waist_spark.set_values([])

        if hasattr(self, "lbl_last_meas"):
            self.lbl_last_meas.setText("Son ölçüm: —")


        if hasattr(self, "lbl_trend_meta"):
            self.lbl_trend_meta.setText("")

        self.lbl_adherence.setText("—")
        self.lbl_adherence_hint.setText("")

        self.list_alerts.clear()
        it = QListWidgetItem("Henüz veri yok.")
        self.list_alerts.addItem(it)

    def _render(self, m: DashboardMetrics) -> None:
        self.lbl_status_badge.setText(m.status_label)
        lvl = "stabil" if m.status_label == "Stabil" else ("dikkat" if m.status_label == "Dikkat" else "risk")
        self._apply_badge_style(self.lbl_status_badge, lvl)
        self.lbl_status_hint.setText(f"{m.status_hint}<br><span style='color:rgba(0,0,0,0.65); font-weight:650;'>Öneri:</span> {m.status_action}")
        self.lbl_status_hint.setTextFormat(Qt.RichText)

        self.lbl_target.setText(f"Hedef: {m.target_kcal:.0f} kcal" if m.target_kcal > 0 else "Hedef: tanımlı değil")
        self.lbl_intake.setText(f"Alınan: {m.intake_kcal_today:.0f} kcal")
        if hasattr(self, "lbl_intake_7d"):
            if m.intake_kcal_7d_avg is None:
                self.lbl_intake_7d.setText("7g ortalama: — kcal")
            else:
                self.lbl_intake_7d.setText(f"7g ortalama: {m.intake_kcal_7d_avg:.0f} kcal")
        if hasattr(self, "lbl_energy_near"):
            if m.target_kcal > 0:
                self.lbl_energy_near.setText(f"Hedefe yakın: {m.energy_near_days_7d}/{m.energy_window_days}")
            else:
                self.lbl_energy_near.setText(f"Kayıt: {m.energy_near_days_7d}/{m.energy_window_days}")
        sign = "+" if m.kcal_diff_today > 0 else ""
        self.lbl_diff.setText(f"Fark: {sign}{m.kcal_diff_today:.0f} kcal")

        # progress bar only if target exists
        if m.target_kcal > 0:
            pct = (m.intake_kcal_today / m.target_kcal) * 100.0 if m.target_kcal > 0 else 0.0
            pct = max(0.0, min(200.0, pct))
            self.pb_energy.setVisible(True)
            self.pb_energy.setValue(int(min(100.0, pct)))

            # chunk color based on deviation
            dev = abs(m.kcal_diff_today) / m.target_kcal
            if dev <= 0.10:
                chunk = "rgba(28,170,108,0.75)"  # green
                note = "Hedefe yakın."
            elif dev <= 0.20:
                chunk = "rgba(245,163,26,0.78)"  # orange
                note = "Hedeften sapma var, hızlı kontrol önerilir."
            else:
                chunk = "rgba(188,35,60,0.70)"   # red
                note = "Sapma yüksek, gün/plan kontrolü önerilir."

            self.pb_energy.setStyleSheet(
                "QProgressBar{background: rgba(0,0,0,0.06); border: 1px solid rgba(0,0,0,0.10); "
                "border-radius: 5px; }"
                f"QProgressBar::chunk{{border-radius: 5px; background: {chunk};}}"
            )
            self.lbl_energy_note.setText(f"%{(m.intake_kcal_today / m.target_kcal) * 100.0:.0f} • {note}")
        else:
            self.pb_energy.setVisible(False)
            self.lbl_energy_note.setText("Hedef kcal tanımlı değil: progress gösterilmez.")

        if m.weight_last is not None:
            if m.weight_delta_30d is None:
                d = ""
            else:
                arrow = "▲" if m.weight_delta_30d > 0 else ("▼" if m.weight_delta_30d < 0 else "→")
                d = f" (30g: {arrow} {m.weight_delta_30d:+.1f} kg)"
            self.lbl_weight.setText(f"Kilo: {m.weight_last:.1f} kg{d}")
        else:
            self.lbl_weight.setText("Kilo: —")
        self.weight_spark.set_values(m.weight_series)

        # Güncellik etiketi
        if hasattr(self, "lbl_last_meas"):
            if m.last_meas_date is None or m.last_meas_age_days is None:
                self.lbl_last_meas.setText("Son ölçüm: —")
            else:
                self.lbl_last_meas.setText(f"Son ölçüm: {m.last_meas_date.strftime('%d.%m.%Y')} • {m.last_meas_age_days}g")

        if m.waist_last is not None:
            if m.waist_delta_30d is None:
                d = ""
            else:
                arrow = "▲" if m.waist_delta_30d > 0 else ("▼" if m.waist_delta_30d < 0 else "→")
                d = f" (30g: {arrow} {m.waist_delta_30d:+.1f} cm)"
            self.lbl_waist.setText(f"Bel: {m.waist_last:.1f} cm{d}")
        else:
            self.lbl_waist.setText("Bel: —")
        self.waist_spark.set_values(m.waist_series)


        # Trend meta (başlangıç→bitiş, min/max) - pencere: 7g/30g
        if hasattr(self, "lbl_trend_meta"):
            wd = getattr(self, "_trend_window_days", 30) or 30
            wd = 7 if int(wd) == 7 else 30

            def _meta(vals: List[float], unit: str) -> str:
                if not vals:
                    return "—"
                start, end = vals[0], vals[-1]
                mn, mx = min(vals), max(vals)
                delta = end - start
                arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "→")
                return f"{start:.1f}→{end:.1f}{unit} ({arrow} {delta:+.1f}{unit}) • min/max {mn:.1f}/{mx:.1f}{unit}"

            w_meta = _meta(m.weight_series, " kg")
            wa_meta = _meta(m.waist_series, " cm")
            self.lbl_trend_meta.setText(f"Pencere: {wd}g • Kilo: {w_meta}<br>Bel: {wa_meta}")
            self.lbl_trend_meta.setTextFormat(Qt.RichText)

        if m.adherence_7d is None:
            self.lbl_adherence.setText("—")
        else:
            self.lbl_adherence.setText(f"%{m.adherence_7d:.0f}")
        self.lbl_adherence_hint.setText(m.adherence_hint)

        self.list_alerts.clear()
        if not m.alerts:
            self.list_alerts.addItem(QListWidgetItem("Uyarı yok."))
        else:
            # Öncelik: risk -> dikkat -> info
            order = {"risk": 0, "dikkat": 1, "info": 2}
            for lvl2, text in sorted(m.alerts, key=lambda x: (order.get(x[0], 9), x[1]))[:12]:
                prefix = "⛔" if lvl2 == "risk" else ("⚠" if lvl2 == "dikkat" else "ℹ")
                item = QListWidgetItem(f"{prefix}  {text}")

                # Uyarıdan hedef sekme türet (tıklanınca hızlı aksiyon)
                t = (text or "").lower()
                target_tab = ""
                if any(k in t for k in ["ölçüm", "kilo", "bel"]):
                    target_tab = "Klinik Kart"
                elif any(k in t for k in ["tüketim", "kcal", "enerji", "hedef"]):
                    target_tab = "Besin Tüketim"
                elif "plan" in t:
                    target_tab = "Diyet Planları"
                elif any(k in t for k in ["pdf", "rapor"]):
                    target_tab = "Raporlar"
                if target_tab:
                    item.setData(Qt.UserRole, target_tab)
                    item.setToolTip(f"Tıkla: {target_tab} sekmesine git")
                    item.setForeground(QBrush(QColor(0, 0, 0, 200)))

                if lvl2 == "risk":
                    item.setForeground(QBrush(QColor(120, 10, 28)))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                elif lvl2 == "dikkat":
                    item.setForeground(QBrush(QColor(120, 72, 0)))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                else:
                    item.setForeground(QBrush(QColor(60, 60, 60)))

                self.list_alerts.addItem(item)

    def _compute_metrics(self, client_id: str) -> DashboardMetrics:
        cur = self.state.conn.cursor()
        cur.execute("SELECT full_name FROM clients WHERE id=?", (client_id,))
        row = cur.fetchone()
        client_name = (row[0] if row else "") or ""

        today = date.today()
        today_s = _iso(today)

        # Target kcal
        target_kcal = 0.0
        try:
            cur.execute("SELECT target_kcal FROM client_kcal_targets WHERE client_id=?", (client_id,))
            r = cur.fetchone()
            if r and r[0] is not None:
                target_kcal = float(r[0])
        except Exception:
            target_kcal = 0.0

        # Intake today
        cur.execute(
            "SELECT COALESCE(SUM(kcal_total),0) FROM food_consumption_entries WHERE client_id=? AND entry_date=?",
            (client_id, today_s)
        )
        intake_today = float(cur.fetchone()[0] or 0.0)

        diff_today = intake_today - target_kcal if target_kcal > 0 else intake_today

        # Measurements series (sparkline penceresi): son 7/30 gün
        window_days = getattr(self, "_trend_window_days", 30) or 30
        window_days = 7 if int(window_days) == 7 else 30
        since_window = today - timedelta(days=window_days)

        cur.execute(
            "SELECT measured_at, weight_kg, waist_cm FROM measurements "
            "WHERE client_id=? AND measured_at>=? ORDER BY measured_at ASC",
            (client_id, _iso(since_window))
        )
        rows = cur.fetchall() or []
        weight_series = [_safe_float(r[1]) for r in rows if _safe_float(r[1]) is not None]
        waist_series = [_safe_float(r[2]) for r in rows if _safe_float(r[2]) is not None]
        weight_last = weight_series[-1] if weight_series else None
        waist_last = waist_series[-1] if waist_series else None

        # latest measurement date (genel - pencere bağımsız)
        last_meas_date: Optional[date] = None
        try:
            cur.execute(
                "SELECT measured_at FROM measurements WHERE client_id=? ORDER BY measured_at DESC LIMIT 1",
                (client_id,)
            )
            rlast = cur.fetchone()
            if rlast and rlast[0]:
                last_meas_date = datetime.strptime(rlast[0], "%Y-%m-%d").date()
        except Exception:
            last_meas_date = None

        # 30d delta (use first/last within 30 days)
        since_30 = today - timedelta(days=30)
        cur.execute(
            "SELECT measured_at, weight_kg, waist_cm FROM measurements "
            "WHERE client_id=? AND measured_at>=? ORDER BY measured_at ASC",
            (client_id, _iso(since_30))
        )
        r30 = cur.fetchall() or []
        w30 = [_safe_float(r[1]) for r in r30 if _safe_float(r[1]) is not None]
        wa30 = [_safe_float(r[2]) for r in r30 if _safe_float(r[2]) is not None]
        weight_delta_30d = (w30[-1] - w30[0]) if len(w30) >= 2 else None
        waist_delta_30d = (wa30[-1] - wa30[0]) if len(wa30) >= 2 else None

        # Adherence 7d: kcal within ±10% target, else fallback "logged"
        days = [today - timedelta(days=i) for i in range(6, -1, -1)]
        good = 0
        logged = 0
        kcal_days: List[float] = []
        for d in days:
            ds = _iso(d)
            cur.execute(
                "SELECT COALESCE(SUM(kcal_total),0) FROM food_consumption_entries WHERE client_id=? AND entry_date=?",
                (client_id, ds)
            )
            kc = float(cur.fetchone()[0] or 0.0)
            kcal_days.append(kc)
            if kc > 0:
                logged += 1
            if target_kcal > 0 and kc > 0:
                if abs(kc - target_kcal) <= 0.10 * target_kcal:
                    good += 1

        # 7g sapma serisi (sparkline): hedef varsa kcal farkı, yoksa alınan kcal
        energy_dev_series_7d: List[Optional[float]] = []
        for kc in kcal_days:
            if kc <= 0:
                energy_dev_series_7d.append(None)
            else:
                energy_dev_series_7d.append((kc - target_kcal) if target_kcal > 0 else kc)

        # 7g ortalama alınan kcal (sadece kayıt olan günler üzerinden)
        kcal_nonzero = [v for v in kcal_days if v > 0]
        intake_7d_avg = (sum(kcal_nonzero) / len(kcal_nonzero)) if kcal_nonzero else None

        energy_window_days = 7
        energy_near_days_7d = (good if target_kcal > 0 else logged)

        if target_kcal > 0:
            adherence = (good / 7.0) * 100.0
            adherence_hint = "Son 7 gün: hedef kcal ±%10 aralığında kalınan gün sayısı üzerinden hesaplanır."
        else:
            adherence = (logged / 7.0) * 100.0
            adherence_hint = "Hedef kcal tanımlı değil: Son 7 gün kayıt girilen gün oranı gösterilir."

        # Alerts + status scoring
        alerts: List[Tuple[str, str]] = []
        score = 0

        def add_alert(level: str, text: str) -> None:
            # level: risk / dikkat / info
            alerts.append((level, text))

        # measurement staleness
        if last_meas_date is None:
            add_alert("risk", "Ölçüm kaydı yok.")
            score += 2
        else:
            age = (today - last_meas_date).days
            if age >= 30:
                add_alert("risk", f"Son ölçüm {age} gün önce (30+).")
                score += 3
            elif age >= 14:
                add_alert("dikkat", f"Son ölçüm {age} gün önce (14+).")
                score += 2

        last_meas_age = (today - last_meas_date).days if last_meas_date is not None else None

        # kcal diff today
        if target_kcal > 0:
            if diff_today >= 500:
                add_alert("dikkat", f"Bugün hedefin üzerinde: +{diff_today:.0f} kcal.")
                score += 2
            elif diff_today <= -500:
                add_alert("dikkat", f"Bugün hedefin altında: {diff_today:.0f} kcal.")
                score += 2

        # adherence
        if adherence < 50:
            add_alert("risk", f"Uyum düşük: %{adherence:.0f} (7 gün).")
            score += 3
        elif adherence < 70:
            add_alert("dikkat", f"Uyum orta: %{adherence:.0f} (7 gün).")
            score += 1

        # weight delta
        if weight_delta_30d is not None:
            if weight_delta_30d >= 2.0:
                add_alert("risk", f"Kilo artışı (30 gün): {weight_delta_30d:+.1f} kg.")
                score += 3
            elif weight_delta_30d >= 1.0:
                add_alert("dikkat", f"Kilo artışı (30 gün): {weight_delta_30d:+.1f} kg.")
                score += 1
            elif weight_delta_30d <= -2.0:
                add_alert("info", f"Kilo düşüşü (30 gün): {weight_delta_30d:+.1f} kg.")
                score += 1

        # active plan existence
        try:
            cur.execute("SELECT COUNT(1) FROM diet_plans WHERE client_id=? AND is_active_plan=1 AND is_active=1", (client_id,))
            cnt = int(cur.fetchone()[0] or 0)
            if cnt == 0:
                add_alert("dikkat", "Aktif diyet planı işaretli değil.")
                score += 1
        except Exception:
            pass

        if score >= 6:
            status = "Risk"
            status_hint = "Birden fazla eşik tetiklenmiş görünüyor. Öncelik: ölçüm güncelliği, enerji sapması ve uyum."
        elif score >= 3:
            status = "Dikkat"
            status_hint = "Bazı eşikler tetiklenmiş. Kısa kontrol önerilir: ölçüm, enerji dengesi, uyum."
        else:
            status = "Stabil"
            status_hint = "Kritik eşik tetiklenmedi. Genel gidişat stabil görünüyor."

        # kısa aksiyon önerisi
        if status == "Risk":
            status_action = "Ölçümü güncelle, bugünkü tüketimi kontrol et ve gerekiyorsa planı revize et."
        elif status == "Dikkat":
            status_action = "Enerji sapmasını ve son 7 gün uyumu hızlıca kontrol et."
        else:
            status_action = "Takibi sürdür; plan uyumu ve ölçüm güncelliğini koru."

        return DashboardMetrics(
            client_id=client_id,
            client_name=client_name,
            status_label=status,
            status_hint=f"{client_name} • {status_hint}",
            status_action=status_action,
            target_kcal=target_kcal,
            intake_kcal_today=intake_today,
            intake_kcal_7d_avg=intake_7d_avg,
            energy_near_days_7d=energy_near_days_7d,
            energy_window_days=energy_window_days,
            kcal_diff_today=diff_today,
            energy_dev_series_7d=energy_dev_series_7d,
            weight_series=weight_series,
            waist_series=waist_series,
            weight_last=weight_last,
            waist_last=waist_last,
            weight_delta_30d=weight_delta_30d,
            waist_delta_30d=waist_delta_30d,

            last_meas_date=last_meas_date,
            last_meas_age_days=last_meas_age,
            adherence_7d=adherence,
            adherence_hint=adherence_hint,
            alerts=alerts
        )