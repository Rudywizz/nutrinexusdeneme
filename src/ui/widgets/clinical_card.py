from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QFrame, QLabel, QHBoxLayout
)
from PySide6.QtCore import Qt

from src.ui.screens.labs import LabsScreen
from src.ui.screens.anamnez import AnamnezScreen
from src.ui.screens.measurements import MeasurementsScreen
from src.ui.screens.calculations import CalculationsScreen
from src.services.measurements_service import MeasurementsService
from src.services.labs_service import LabsService
from src.ui.widgets.measurement_trend import MeasurementTrendPanel
from src.ui.widgets.clinical_intelligence_compact import ClinicalIntelligenceCompactPanel


class ClinicalCardWidget(QWidget):
    def __init__(self, state, log, client_id: str):
        super().__init__()
        self.state = state
        self.log = log
        self.client_id = client_id

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        lay.addWidget(self._header_bar())

        tabs = QTabWidget()
        tabs.setObjectName("InnerTabs")

        tabs.addTab(self._summary(), "Özet")
        self.measurements_screen = MeasurementsScreen(conn=state.conn, client_id=client_id, log=log)
        tabs.addTab(self.measurements_screen, "Ölçümler")
        self.calculations_screen = self._calculations()
        tabs.addTab(self.calculations_screen, "Hesaplamalar")
        tabs.addTab(AnamnezScreen(conn=state.conn, client_id=client_id, log=log), "Anamnez")
        self.labs_screen = LabsScreen(conn=state.conn, client_id=client_id, log=log)
        try:
            self.labs_screen.labs_changed.connect(lambda: getattr(self, 'intel_panel', None) and self.intel_panel.refresh())
        except Exception:
            pass
        tabs.addTab(self.labs_screen, "Kan Tahlili")

        
        # Ölçüm eklenince Hesaplamalar sekmesi anında güncellensin (ekrandan çık-gir gereksinimi olmasın)
        try:
            self.measurements_screen.measurements_changed.connect(lambda: self.calculations_screen.refresh_from_latest(force=True))
            self.measurements_screen.measurements_changed.connect(lambda: getattr(self, 'trend_panel', None) and self.trend_panel.refresh())
            self.measurements_screen.measurements_changed.connect(lambda: getattr(self, 'intel_panel', None) and self.intel_panel.refresh())
        except Exception:
            pass

        lay.addWidget(tabs)


    def _header_bar(self) -> QWidget:
        """Klinik Kart üst başlık alanı (tasarımsal). İşlev değiştirmez."""
        bar = QFrame()
        bar.setObjectName("Card")  # mevcut kart stilini kullan
        h = QHBoxLayout(bar)
        h.setContentsMargins(14, 12, 14, 12)
        h.setSpacing(10)

        left = QVBoxLayout()
        left.setSpacing(2)
        title = QLabel("Klinik Kart")
        title.setObjectName("Title")
        left.addWidget(title)

        h.addLayout(left, 1)

        # Sağ tarafta küçük durum chip'leri
        chips_wrap = QHBoxLayout()
        chips_wrap.setSpacing(8)

        def _chip(text: str, tone: str = "") -> QLabel:
            lbl = QLabel(text)
            lbl.setObjectName("Chip")
            if tone:
                lbl.setProperty("tone", tone)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setMinimumHeight(26)
            lbl.setContentsMargins(10, 2, 10, 2)
            return lbl

        # Son ölçüm / BMI
        try:
            msvc = MeasurementsService(self.state.conn)
            latest = msvc.latest_for_client(self.client_id)
        except Exception:
            latest = None

        if latest:
            chips_wrap.addWidget(_chip(f"Son ölçüm: {latest.measured_at}", "neutral"))
            bmi = None
            try:
                bmi = latest.bmi()
            except Exception:
                bmi = None
            if bmi is None:
                chips_wrap.addWidget(_chip("BMI: —", "neutral"))
            else:
                tone = "success" if 18.5 <= bmi <= 24.9 else ("warning" if 17.0 <= bmi <= 29.9 else "danger")
                chips_wrap.addWidget(_chip(f"BMI: {bmi:.1f}", tone))
        else:
            chips_wrap.addWidget(_chip("Son ölçüm yok", "warning"))
            chips_wrap.addWidget(_chip("BMI: —", "neutral"))

        # Tahlil var/yok
        try:
            lsvc = LabsService(self.state.conn)
            has_labs = bool(lsvc.latest_import_id(self.client_id))
        except Exception:
            has_labs = False
        chips_wrap.addWidget(_chip("Tahlil: Var" if has_labs else "Tahlil: Yok", "success" if has_labs else "neutral"))

        h.addLayout(chips_wrap)

        return bar

    def _summary(self) -> QWidget:
        root = QFrame()
        root.setObjectName("Card")
        l = QVBoxLayout(root)

        l.addWidget(QLabel("Klinik Özet", objectName="Title"))

        # Son ölçüm kartı
        l.addWidget(self._latest_measurement_card())

        # Son kan tahlili bilgisi
        l.addWidget(self._latest_labs_card())

        # Ölçüm trend paneli (Sprint 3.8)
        self.trend_panel = MeasurementTrendPanel(conn=self.state.conn, client_id=self.client_id, log=self.log)
        l.addWidget(self.trend_panel)

        # Grafik paneli çok sıkışmasın
        self.trend_panel.setMinimumHeight(260)

        self.intel_panel = ClinicalIntelligenceCompactPanel(conn=self.state.conn, client_id=self.client_id, log=self.log)
        l.addWidget(self.intel_panel)

        l.addStretch(1)
        return root


    def _latest_labs_card(self) -> QWidget:
        w = QFrame()
        w.setObjectName("Card")
        l = QVBoxLayout(w)
        l.addWidget(QLabel("Son Kan Tahlili", objectName="SectionTitle"))

        svc = LabsService(self.state.conn)
        imp_id = svc.latest_import_id(self.client_id)
        if not imp_id:
            l.addWidget(QLabel("Henüz tahlil yüklenmedi.", objectName="FieldLabel"))
            return w

        imp = self.state.conn.execute("SELECT * FROM lab_imports WHERE id=?", (imp_id,)).fetchone()
        if imp:
            imported_at = imp["imported_at"]
            src_name = imp["source_filename"]
            l.addWidget(QLabel(f"Yükleme: {imported_at}", objectName="FieldLabel"))
            l.addWidget(QLabel(f"Dosya: {src_name}", objectName="SubTitle"))
        else:
            l.addWidget(QLabel("Son tahlil kaydı bulundu fakat detay okunamadı.", objectName="FieldLabel"))
        return w


    def _latest_measurement_card(self) -> QWidget:
        w = QFrame()
        w.setObjectName("Card")
        l = QVBoxLayout(w)

        l.addWidget(QLabel("Son Ölçüm", objectName="SectionTitle"))

        svc = MeasurementsService(self.state.conn)
        latest = svc.latest_for_client(self.client_id)

        if latest:
            bmi = latest.bmi()
            l.addWidget(QLabel(f"Son Ölçüm Tarihi: {latest.measured_at}", objectName="FieldLabel"))
            l.addWidget(QLabel(f"Boy: {'' if latest.height_cm is None else f'{latest.height_cm:.0f} cm'}", objectName="SubTitle"))
            l.addWidget(QLabel(f"Kilo: {'' if latest.weight_kg is None else f'{latest.weight_kg:.1f} kg'}", objectName="SubTitle"))
            l.addWidget(QLabel(f"BMI: {'' if bmi is None else f'{bmi:.1f}'}", objectName="SubTitle"))
        else:
            l.addWidget(QLabel("Henüz ölçüm eklenmedi. (Trend için en az 2 ölçüm gerekir.)", objectName="FieldLabel"))

        return w

    def _calculations(self):
        return CalculationsScreen(conn=self.state.conn, client_id=self.client_id, log=self.log)
