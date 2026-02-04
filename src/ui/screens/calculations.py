from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QGridLayout,
    QLineEdit, QComboBox, QSpinBox, QPushButton
)

from src.services.clients_service import ClientsService
from src.services.measurements_service import MeasurementsService


@dataclass(frozen=True)
class ActivityPreset:
    label: str
    factor: float


ACTIVITY_PRESETS: list[ActivityPreset] = [
    ActivityPreset("Sedanter (masa başı, çok az hareket)", 1.20),
    ActivityPreset("Hafif aktif (haftada 1-3 gün)", 1.375),
    ActivityPreset("Orta aktif (haftada 3-5 gün)", 1.55),
    ActivityPreset("Yüksek aktif (haftada 6-7 gün)", 1.725),
    ActivityPreset("Çok yüksek (ağır iş / çift antrenman)", 1.90),
]


def _parse_yyyy_mm_dd(s: str) -> date | None:
    try:
        return datetime.strptime((s or "").strip(), "%Y-%m-%d").date()
    except Exception:
        return None



def _fmt_tr_date(iso: str) -> str:
    if not iso:
        return ""
    if "-" in iso:
        try:
            y, m, d = iso.split("-")
            if len(y)==4 and len(m)==2 and len(d)==2:
                return f"{d}/{m}/{y}"
        except Exception:
            pass
    return iso

def _age_years(birth: date, today: date | None = None) -> int:
    t = today or date.today()
    years = t.year - birth.year
    if (t.month, t.day) < (birth.month, birth.day):
        years -= 1
    return max(0, years)


class CalculationsScreen(QWidget):
    """
    Sprint-3: BMI / BMR / TDEE ekranı (okunaklı ve güvenilir).
    - Boy/Kilo: son ölçümden otomatik gelir; yoksa manuel girilebilir.
    - Cinsiyet & Yaş: danışan kaydından otomatik gelir (cinsiyet gerektiğinde değiştirilebilir).
    - Aktivite seviyesi: PAL (çarpan) seçimi.
    """
    def __init__(self, conn, client_id: str, log):
        super().__init__()
        self.conn = conn
        self.client_id = client_id
        self.log = log

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("Card")
        root.addWidget(card)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)

        title = QLabel("Hesaplamalar")
        title.setObjectName("Title")
        lay.addWidget(title)

        subtitle = QLabel("BMI / BMR / TDEE (Mifflin–St Jeor) • Değerler değiştikçe otomatik güncellenir.")
        subtitle.setObjectName("SubTitle")
        lay.addWidget(subtitle)

        row = QHBoxLayout()
        row.setSpacing(14)
        lay.addLayout(row, 1)

        # Left: Inputs
        left = QFrame()
        left.setObjectName("InnerCard")
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(14, 14, 14, 14)
        left_l.setSpacing(10)
        row.addWidget(left, 2)

        left_l.addWidget(QLabel("Girdi Bilgileri", objectName="SectionTitle"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        left_l.addLayout(grid)

        # Name (readonly)
        self.lbl_name = QLabel("-", objectName="FieldValue")
        self.lbl_meta = QLabel("-", objectName="Muted")
        name_wrap = QVBoxLayout()
        name_wrap.addWidget(self.lbl_name)
        name_wrap.addWidget(self.lbl_meta)

        name_box = QFrame()
        name_box.setObjectName("InfoBox")
        nb = QVBoxLayout(name_box)
        nb.setContentsMargins(12, 10, 12, 10)
        nb.addLayout(name_wrap)
        grid.addWidget(name_box, 0, 0, 1, 2)

        # Gender
        grid.addWidget(QLabel("Cinsiyet", objectName="FieldLabel"), 1, 0)
        self.cmb_gender = QComboBox()
        self.cmb_gender.setObjectName("Input")
        self.cmb_gender.addItems(["Kadın", "Erkek", "Diğer"])
        grid.addWidget(self.cmb_gender, 1, 1)

        # Age
        grid.addWidget(QLabel("Yaş", objectName="FieldLabel"), 2, 0)
        self.txt_age = QLineEdit()
        self.txt_age.setObjectName("Input")
        self.txt_age.setReadOnly(True)
        grid.addWidget(self.txt_age, 2, 1)

        # Height
        grid.addWidget(QLabel("Boy (cm)", objectName="FieldLabel"), 3, 0)
        self.txt_height = QLineEdit()
        self.txt_height.setObjectName("Input")
        self.txt_height.setPlaceholderText("Örn: 170")
        grid.addWidget(self.txt_height, 3, 1)

        # Weight
        grid.addWidget(QLabel("Kilo (kg)", objectName="FieldLabel"), 4, 0)
        self.txt_weight = QLineEdit()
        self.txt_weight.setObjectName("Input")
        self.txt_weight.setPlaceholderText("Örn: 72.5")
        grid.addWidget(self.txt_weight, 4, 1)

        # Activity
        grid.addWidget(QLabel("Aktivite seviyesi", objectName="FieldLabel"), 5, 0)
        self.cmb_activity = QComboBox()
        self.cmb_activity.setObjectName("Input")
        for p in ACTIVITY_PRESETS:
            self.cmb_activity.addItem(p.label, p.factor)
        self.cmb_activity.setCurrentIndex(2)  # Orta aktif
        grid.addWidget(self.cmb_activity, 5, 1)

        # Goal adjustment
        grid.addWidget(QLabel("Hedef ayarı", objectName="FieldLabel"), 6, 0)
        goal_row = QHBoxLayout()
        goal_row.setSpacing(8)

        self.cmb_goal = QComboBox()
        self.cmb_goal.setObjectName("Input")
        self.cmb_goal.addItem("Koruma (0 kcal)", 0)
        self.cmb_goal.addItem("Kilo ver (-500 kcal)", -500)
        self.cmb_goal.addItem("Kilo al (+300 kcal)", 300)
        self.cmb_goal.addItem("Özel", 999999)
        goal_row.addWidget(self.cmb_goal, 2)

        self.spin_adjust = QSpinBox()
        self.spin_adjust.setObjectName("Input")
        self.spin_adjust.setRange(-1000, 1000)
        self.spin_adjust.setSingleStep(50)
        self.spin_adjust.setValue(0)
        self.spin_adjust.setSuffix(" kcal")
        goal_row.addWidget(self.spin_adjust, 1)

        goal_wrap = QWidget()
        goal_wrap.setLayout(goal_row)
        grid.addWidget(goal_wrap, 6, 1)

        # Boy/Kilo tek kaynaktan yönetilsin: Ölçümler sekmesi.
        # Hesaplamalar ekranı sadece en son ölçümü *gösterir* ve sonuç üretir.
        info = QLabel("Boy/Kilo bilgisi Ölçümler sekmesinden otomatik alınır.")
        info.setObjectName("Muted")
        info.setWordWrap(True)
        left_l.addWidget(info)

        note = QLabel("Not: BMR formülü Mifflin–St Jeor’dur. TDEE = BMR × Aktivite çarpanı. Hedef ayarı TDEE’ye eklenir/çıkarılır.")
        note.setWordWrap(True)
        note.setObjectName("Muted")
        left_l.addWidget(note)

        left_l.addStretch(1)

        # Right: Results
        right = QFrame()
        right.setObjectName("InnerCard")
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(14, 14, 14, 14)
        right_l.setSpacing(10)
        row.addWidget(right, 3)

        right_l.addWidget(QLabel("Sonuçlar", objectName="SectionTitle"))

        self.res_bmi = self._metric_box("BMI", "-")
        self.res_bmr = self._metric_box("BMR", "- kcal/gün")
        self.res_tdee = self._metric_box("TDEE", "- kcal/gün")
        self.res_target = self._metric_box("Hedef Kalori", "- kcal/gün")
        self.res_loss = self._metric_box("Kilo Ver (-500)", "- kcal/gün")
        self.res_maint = self._metric_box("Koruma (0)", "- kcal/gün")
        self.res_gain = self._metric_box("Kilo Al (+300)", "- kcal/gün")

        right_l.addWidget(self.res_bmi)
        right_l.addWidget(self.res_bmr)
        right_l.addWidget(self.res_tdee)
        right_l.addWidget(self.res_target)
        right_l.addWidget(self.res_loss)
        right_l.addWidget(self.res_maint)
        right_l.addWidget(self.res_gain)

        self.lbl_hint = QLabel("Boy/kilo bilgisi yoksa önce Ölçümler sekmesinden ölçüm ekleyin.")
        self.lbl_hint.setObjectName("Muted")
        right_l.addWidget(self.lbl_hint)

        right_l.addStretch(1)

        # Load data and wire signals
        self._load_from_db()

        # Read-only: values come from measurements.
        self.txt_height.setReadOnly(True)
        self.txt_weight.setReadOnly(True)

        self.txt_height.textChanged.connect(self._recalc)
        self.txt_weight.textChanged.connect(self._recalc)
        self.cmb_gender.currentIndexChanged.connect(self._recalc)
        self.cmb_activity.currentIndexChanged.connect(self._recalc)
        self.cmb_goal.currentIndexChanged.connect(self._on_goal_changed)
        self.spin_adjust.valueChanged.connect(self._on_adjust_changed)

        self._recalc()

    def _metric_box(self, title: str, value: str) -> QFrame:
        box = QFrame()
        box.setObjectName("MetricBox")
        l = QVBoxLayout(box)
        l.setContentsMargins(14, 12, 14, 12)
        l.setSpacing(4)
        t = QLabel(title)
        t.setObjectName("MetricTitle")
        v = QLabel(value)
        v.setObjectName("MetricValue")
        v.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        l.addWidget(t)
        l.addWidget(v)
        box._metric_value = v  # type: ignore[attr-defined]
        return box

    def _set_metric(self, box: QFrame, text: str):
        lbl = getattr(box, "_metric_value", None)
        if lbl is not None:
            lbl.setText(text)

    def _load_from_db(self):
        # Client basic
        c = ClientsService(self.conn).get_client(self.client_id)
        if c:
            self.lbl_name.setText(c.full_name)
            self.lbl_meta.setText(f"Telefon: {c.phone}  •  Doğum: {_fmt_tr_date(c.birth_date)}")
            # Gender
            g = (c.gender or "").strip()
            if g in ["Kadın", "Erkek", "Diğer"]:
                self.cmb_gender.setCurrentText(g)
            # Age
            bd = _parse_yyyy_mm_dd(c.birth_date)
            if bd:
                self.txt_age.setText(str(_age_years(bd)))
        # Pull latest measurement into inputs (if available)
        self.refresh_from_latest(force=True)

    def refresh_from_latest(self, force: bool = False):
        """Refresh height/weight from latest measurement.

        Tasarım kararı: Boy/Kilo tek kaynaktan yönetilir (Ölçümler sekmesi).
        Bu ekran sadece en son ölçümü gösterir ve hesaplar.
        """
        svc = MeasurementsService(self.conn)
        m = svc.latest_for_client(self.client_id)

        if not m:
            # No measurement yet
            with QSignalBlocker(self.txt_height):
                self.txt_height.setText("")
            with QSignalBlocker(self.txt_weight):
                self.txt_weight.setText("")
            self.lbl_hint.setText("Boy/kilo bilgisi yok. Önce Ölçümler sekmesinden ölçüm ekleyin.")
            self._recalc()
            return

        if m.height_cm is not None:
            with QSignalBlocker(self.txt_height):
                self.txt_height.setText(f"{m.height_cm:.0f}")
        if m.weight_kg is not None:
            with QSignalBlocker(self.txt_weight):
                self.txt_weight.setText(f"{m.weight_kg:.1f}")

        self.lbl_hint.setText("Boy/Kilo bilgisi Ölçümler sekmesinden otomatik alınır.")
        self._recalc()

    def _on_goal_changed(self):
        val = self.cmb_goal.currentData()
        if val == 999999:
            self.spin_adjust.setEnabled(True)
        else:
            self.spin_adjust.setEnabled(False)
            with QSignalBlocker(self.spin_adjust):
                self.spin_adjust.setValue(int(val))
        self._recalc()

    def _on_adjust_changed(self):
        if self.cmb_goal.currentData() == 999999:
            self._recalc()

    def _read_float(self, s: str) -> float | None:
        t = (s or "").strip().replace(",", ".")
        if not t:
            return None
        try:
            return float(t)
        except Exception:
            return None

    def _recalc(self):
        height = self._read_float(self.txt_height.text())
        weight = self._read_float(self.txt_weight.text())

        age = self._read_float(self.txt_age.text())
        age_i = int(age) if age is not None else None

        gender = self.cmb_gender.currentText()
        factor = float(self.cmb_activity.currentData())
        adjust = int(self.spin_adjust.value()) if (self.cmb_goal.currentData() == 999999) else int(self.cmb_goal.currentData())

        # BMI
        bmi = None
        if height and weight and height > 0:
            h_m = height / 100.0
            bmi = weight / (h_m * h_m)

        # BMR (Mifflin–St Jeor)
        bmr = None
        if height and weight and age_i is not None and height > 0 and weight > 0:
            base = 10.0 * weight + 6.25 * height - 5.0 * age_i
            if gender == "Erkek":
                bmr = base + 5.0
            else:
                # Kadın/Diğer default to -161
                bmr = base - 161.0

        # TDEE
        tdee = None
        if bmr is not None:
            tdee = bmr * factor

        # Target
        target = None
        if tdee is not None:
            target = tdee + adjust

        # Update UI
        self._set_metric(self.res_bmi, "-" if bmi is None else f"{bmi:.1f}")
        self._set_metric(self.res_bmr, "-" if bmr is None else f"{bmr:.0f} kcal/gün")
        self._set_metric(self.res_tdee, "-" if tdee is None else f"{tdee:.0f} kcal/gün")
        self._set_metric(self.res_target, "-" if target is None else f"{target:.0f} kcal/gün")

        # Preset hedef kartları (UI): TDEE bazlı sabit senaryolar
        self._set_metric(self.res_loss, "-" if tdee is None else f"{(tdee - 500):.0f} kcal/gün")
        self._set_metric(self.res_maint, "-" if tdee is None else f"{tdee:.0f} kcal/gün")
        self._set_metric(self.res_gain, "-" if tdee is None else f"{(tdee + 300):.0f} kcal/gün")

        if bmi is None or bmr is None or tdee is None:
            self.lbl_hint.setText("Hesaplama için boy, kilo ve doğum tarihi gerekli. Eksik olanı tamamla.")
        else:
            self.lbl_hint.setText("Değerler güncellendi. İstersen aktivite ve hedef ayarını değiştir.")