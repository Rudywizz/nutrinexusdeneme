from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QHBoxLayout, QGridLayout,
    QDoubleSpinBox, QSpinBox, QPushButton, QMessageBox,
    QLineEdit, QTextEdit, QComboBox, QCheckBox, QFileDialog
)
from PySide6.QtCore import Qt, QObject, QEvent, QTimer

import os
from pathlib import Path

from PySide6.QtGui import QPixmap, QImage, QPainter, QColor

from src.services.settings_service import SettingsService, DEFAULT_CLINICAL_THRESHOLDS


class _NoWheelFilter(QObject):
    """Block mouse wheel so SpinBox/ComboBox values don't change while scrolling pages."""

    def eventFilter(self, obj, event):  # noqa: N802 (Qt naming)
        if event.type() == QEvent.Wheel:
            event.ignore()
            return True
        return super().eventFilter(obj, event)


class SettingsScreen(QWidget):
    def __init__(self, state, log):
        super().__init__()
        # Scope-specific styling hook (avoid impacting other stable screens)
        self.setObjectName("SettingsPage")
        self.state = state
        self.log = log
        self.svc = SettingsService(state.conn)
        # Bildirim varsayılanları (idempotent)
        self.svc.set_default("appointments.notify_enabled", "1")
        self.svc.set_default("appointments.notify_minutes_before", "0")

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Ayarlar")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.lbl_saved = QLabel("")
        self.lbl_saved.setObjectName("HintLabel")
        self.lbl_saved.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        # Ensure the "Kaydedildi" hint is readable on light themes.
        self.lbl_saved.setStyleSheet("color: #2b2b2b; padding-right: 10px;")
        header.addWidget(self.lbl_saved)
        self.btn_save_all = QPushButton("Tümünü Kaydet")
        self.btn_save_all.setObjectName("PrimaryBtn")
        self.btn_save_all.setMinimumHeight(38)
        self.btn_save_all.setMinimumWidth(170)
        self.btn_save_all.setMinimumHeight(40)
        self.btn_save_all.setMinimumWidth(140)
        self.btn_save_all.clicked.connect(self._save_all)
        header.addWidget(self.btn_save_all)
        layout.addLayout(header)
        # General card
        card = QFrame()
        card.setObjectName("Card")
        v = QVBoxLayout(card)

        v.addWidget(QLabel(f"Yedek/DB klasörü: {state.backup_root}"))
        v.addWidget(QLabel("• Kullanıcılar/Roller (Phase-2)"))
        v.addWidget(QLabel("• Tema seçenekleri (Phase-2)"))

        layout.addWidget(card)

        # Clinic / Defaults card (Sprint 5.1)
        self.card_app = QFrame()
        self.card_app.setObjectName("Card")
        app_l = QVBoxLayout(self.card_app)
        app_l.setSpacing(10)

        hdr2 = QLabel("Klinik ve Uygulama")
        hdr2.setObjectName("CardTitle")
        app_l.addWidget(hdr2)

        # Inputs
        self.txt_clinic_name = QLineEdit(); self.txt_clinic_name.setObjectName("Input")
        self.txt_clinic_phone = QLineEdit(); self.txt_clinic_phone.setObjectName("Input")
        self.txt_clinic_email = QLineEdit(); self.txt_clinic_email.setObjectName("Input")

        # Multiline fields: make them visually more "tangible" than single-line inputs.
        # Users expect these to look like dedicated text areas.
        self.txt_clinic_address = QTextEdit(); self.txt_clinic_address.setObjectName("InputStrong")
        self.txt_clinic_address.setFixedHeight(84)
        self.txt_clinic_address.setPlaceholderText("Adres (kısa)")

        self.txt_report_footer = QTextEdit(); self.txt_report_footer.setObjectName("InputStrong")
        self.txt_report_footer.setFixedHeight(72)
        self.txt_report_footer.setPlaceholderText("Rapor alt bilgisi (ör: Klinik adı • Tel • Web)")

        self.sp_default_kcal = QSpinBox()
        self.sp_default_kcal.setObjectName("Input")
        self.sp_default_kcal.setRange(0, 20000)
        self.sp_default_kcal.setSingleStep(50)

        self.cmb_backup_policy = QComboBox()
        self.cmb_backup_policy.setObjectName("Input")
        self.cmb_backup_policy.addItems(["Kapalı", "Günlük", "Haftalık"])

        self.sp_backup_keep = QSpinBox()
        self.sp_backup_keep.setObjectName("Input")
        self.sp_backup_keep.setRange(1, 365)
        self.sp_backup_keep.setSingleStep(1)

        # Appointment notifications
        self.chk_appt_notifications = QCheckBox("Randevu hatırlatmaları (Windows bildirimi)")
        self.chk_appt_notifications.setObjectName("Input")
        self.sp_appt_remind = QSpinBox()
        self.sp_appt_remind.setObjectName("Input")
        self.sp_appt_remind.setRange(0, 240)
        self.sp_appt_remind.setSingleStep(5)
        self.sp_appt_remind.setSuffix(" dk")

        # Form grid (4 columns): label+field | label+field
        # This avoids "centered" widgets, clipping, and section headers stealing width.
        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(26)
        grid.setVerticalSpacing(10)

        # column sizing
        grid.setColumnMinimumWidth(0, 180)
        grid.setColumnMinimumWidth(2, 210)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        def _lbl(text: str) -> QLabel:
            l = QLabel(text)
            l.setObjectName("FieldLabel")
            l.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
            return l

        # Row 0-2: contact + defaults/backup
        grid.addWidget(_lbl("Klinik adı"), 0, 0)
        grid.addWidget(self.txt_clinic_name, 0, 1)
        grid.addWidget(_lbl("Varsayılan günlük kcal"), 0, 2)
        grid.addWidget(self.sp_default_kcal, 0, 3)

        grid.addWidget(_lbl("Telefon"), 1, 0)
        grid.addWidget(self.txt_clinic_phone, 1, 1)
        grid.addWidget(_lbl("Otomatik yedek"), 1, 2)
        grid.addWidget(self.cmb_backup_policy, 1, 3)

        grid.addWidget(_lbl("E-posta"), 2, 0)
        grid.addWidget(self.txt_clinic_email, 2, 1)
        grid.addWidget(_lbl("Saklanacak yedek sayısı"), 2, 2)
        grid.addWidget(self.sp_backup_keep, 2, 3)

        # Row 3-4 (left): appointment notifications
        grid.addWidget(_lbl("Randevu bildirimi"), 3, 0)
        grid.addWidget(self.chk_appt_notifications, 3, 1)
        grid.addWidget(_lbl("Kaç dk önce"), 4, 0)
        grid.addWidget(self.sp_appt_remind, 4, 1)

        # Row 3-4: multiline fields on the right column
        self.txt_clinic_address.setFixedHeight(74)
        self.txt_report_footer.setFixedHeight(64)
        grid.addWidget(_lbl("Adres"), 3, 2)
        grid.addWidget(self.txt_clinic_address, 3, 3)
        grid.addWidget(_lbl("Rapor alt bilgisi (footer)"), 4, 2)
        grid.addWidget(self.txt_report_footer, 4, 3)

        # Row 5: clinic logo (used in reports + diet plan watermark)
        self.lbl_logo_status = QLabel("")
        self.lbl_logo_status.setObjectName("Hint")
        self.btn_logo_choose = QPushButton("Logo Seç…")
        self.btn_logo_choose.setObjectName("SecondaryBtn")
        self.btn_logo_clear = QPushButton("Kaldır")
        self.btn_logo_clear.setObjectName("SecondaryBtn")

        logo_row = QWidget()
        logo_lay = QHBoxLayout(logo_row)
        logo_lay.setContentsMargins(0, 0, 0, 0)
        logo_lay.setSpacing(8)
        logo_lay.addWidget(self.lbl_logo_status, 1)
        logo_lay.addWidget(self.btn_logo_choose, 0)
        logo_lay.addWidget(self.btn_logo_clear, 0)

        # Logo controls live on the right column to avoid distorting the left column widths.
        grid.addWidget(_lbl("Logo"), 5, 2)
        grid.addWidget(logo_row, 5, 3)

        # Save button row (right aligned)
        btns2 = QHBoxLayout()
        btns2.addStretch(1)
        self.btn_save_app = QPushButton("Kaydet")
        self.btn_save_app.setObjectName("PrimaryBtn")
        self.btn_save_app.setMinimumHeight(38)
        self.btn_save_app.setMinimumWidth(130)
        self.btn_save_app.setMinimumHeight(40)
        self.btn_save_app.setMinimumWidth(120)
        self.btn_save_app.clicked.connect(self._save_app)
        btns2.addWidget(self.btn_save_app)

        # Let the container use the full card width. Centering+hard max widths
        # were causing clipping/overlap on smaller windows.
        app_l.addWidget(container)
        app_l.addLayout(btns2)


        layout.addWidget(self.card_app)

        # Clinical thresholds card (Sprint 4.2)
        self.card_thr = QFrame()
        self.card_thr.setObjectName("Card")
        thr_l = QVBoxLayout(self.card_thr)
        thr_l.setSpacing(10)

        hdr = QLabel("Klinik Eşik Ayarları")
        hdr.setObjectName("CardTitle")
        thr_l.addWidget(hdr)

        self._build_threshold_row(thr_l)

        btns = QHBoxLayout()
        btns.addStretch(1)

        self.btn_reset = QPushButton("Varsayılana Dön")
        self.btn_reset.setObjectName("SecondaryButton")
        self.btn_save = QPushButton("Kaydet")
        self.btn_save.setObjectName("PrimaryBtn")
        self.btn_save.setMinimumHeight(38)
        self.btn_save.setMinimumWidth(130)

        self.btn_reset.clicked.connect(self._reset_defaults)
        self.btn_save.clicked.connect(self._save)
        self.btn_logo_choose.clicked.connect(self._pick_logo)
        self.btn_logo_clear.clicked.connect(self._clear_logo)

        btns.addWidget(self.btn_reset)
        btns.addWidget(self.btn_save)
        thr_l.addLayout(btns)

        layout.addWidget(self.card_thr)
        layout.addStretch(1)

        self._load()
        # UX: prevent accidental value changes by mouse wheel while scrolling settings
        self._install_no_wheel_filter()

    def _install_no_wheel_filter(self):
        """Disable mouse-wheel changing values on spinboxes/comboboxes in this screen."""
        self._no_wheel_filter = _NoWheelFilter(self)
        # PySide6 QObject.findChildren() does not accept a tuple of types.
        # Collect widgets type-by-type, then install the filter.
        widgets = []
        widgets.extend(self.findChildren(QSpinBox))
        widgets.extend(self.findChildren(QDoubleSpinBox))
        widgets.extend(self.findChildren(QComboBox))

        for w in widgets:
            w.installEventFilter(self._no_wheel_filter)


    def _make_double(self, minimum: float, maximum: float, step: float, decimals: int = 1):
        w = QDoubleSpinBox()
        w.setObjectName("Input")
        w.setRange(minimum, maximum)
        w.setSingleStep(step)
        w.setDecimals(decimals)
        return w

    def _make_int(self, minimum: int, maximum: int, step: int = 1):
        w = QSpinBox()
        w.setObjectName("Input")
        w.setRange(minimum, maximum)
        w.setSingleStep(step)
        return w

    def _row(self, parent_layout: QVBoxLayout, label: str, widget):
        row = QHBoxLayout()
        row.setSpacing(14)
        row.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label)
        lbl.setObjectName("FieldLabel")
        lbl.setMinimumWidth(240)
        lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        # Keep label vertically aligned with its control
        try:
            lbl.setMinimumHeight(widget.sizeHint().height())
        except Exception:
            pass
        row.addWidget(lbl)
        # Prevent controls from spanning the whole window (keeps the UI tidy)
        try:
            widget.setMaximumWidth(620)
        except Exception:
            pass
        row.addWidget(widget, 1)
        parent_layout.addLayout(row)

    def _row_compact(self, parent_layout: QVBoxLayout, label: str, widget, label_w: int = 190, widget_w: int = 260):
        """A slightly tighter row used for 2-column layouts."""
        row = QHBoxLayout()
        row.setSpacing(10)
        row.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label)
        lbl.setObjectName("FieldLabel")
        lbl.setMinimumWidth(label_w)
        lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        try:
            lbl.setMinimumHeight(widget.sizeHint().height())
        except Exception:
            pass
        row.addWidget(lbl)
        # Give inputs a gentle minimum width but allow them to expand.
        try:
            widget.setMinimumWidth(widget_w)
        except Exception:
            pass
        row.addWidget(widget, 1)
        parent_layout.addLayout(row)

    def _build_threshold_row(self, parent_layout: QVBoxLayout):
        self.sp_weight_info = self._make_double(0.1, 10.0, 0.1, 1)
        self.sp_weight_warn = self._make_double(0.1, 10.0, 0.1, 1)
        self.sp_waist_info = self._make_double(50.0, 200.0, 1.0, 0)
        self.sp_waist_warn = self._make_double(50.0, 200.0, 1.0, 0)

        self.sp_crp_warn = self._make_double(0.1, 200.0, 0.5, 1)
        self.sp_hba1c_warn = self._make_double(3.0, 12.0, 0.1, 2)
        self.sp_hba1c_critical = self._make_double(3.0, 12.0, 0.1, 2)

        self.sp_ldl_warn = self._make_double(50.0, 400.0, 5.0, 0)
        self.sp_ldl_critical = self._make_double(50.0, 400.0, 5.0, 0)

        # Two-column layout for readability (less vertical scrolling)
        cols = QHBoxLayout()
        cols.setSpacing(18)

        left_w = QWidget(); left_v = QVBoxLayout(left_w)
        left_v.setSpacing(8); left_v.setContentsMargins(0, 0, 0, 0)

        right_w = QWidget(); right_v = QVBoxLayout(right_w)
        right_v.setSpacing(8); right_v.setContentsMargins(0, 0, 0, 0)

        # Keep row baselines aligned between columns.
        # Use matching sub-headers on both sides (same style + fixed height)
        # to prevent tiny misalignments on different DPI/font settings.
        sep_left = QLabel("Vücut Ölçüleri")
        sep_left.setObjectName("SectionHeader")
        sep_right = QLabel("Kan Tahlili Eşikleri")
        sep_right.setObjectName("SectionHeader")
        for h in (sep_left, sep_right):
            h.setFixedHeight(24)

        left_v.addWidget(sep_left)

        # Left: anthropometrics
        self._row_compact(left_v, "Kilo • Bilgi (kg/hafta)", self.sp_weight_info)
        self._row_compact(left_v, "Kilo • Uyarı (kg/hafta)", self.sp_weight_warn)
        self._row_compact(left_v, "Bel • Bilgi (cm)", self.sp_waist_info)
        self._row_compact(left_v, "Bel • Uyarı (cm)", self.sp_waist_warn)

        # Right: lab thresholds
        right_v.addWidget(sep_right)
        self._row_compact(right_v, "CRP • Uyarı (mg/L)", self.sp_crp_warn)
        self._row_compact(right_v, "HbA1c • Uyarı (%)", self.sp_hba1c_warn)
        self._row_compact(right_v, "HbA1c • Kritik (%)", self.sp_hba1c_critical)
        self._row_compact(right_v, "LDL • Uyarı (mg/dL)", self.sp_ldl_warn)
        self._row_compact(right_v, "LDL • Kritik (mg/dL)", self.sp_ldl_critical)

        cols.addWidget(left_w, 1)
        cols.addWidget(right_w, 1)

        # Do NOT force a fixed width container here.
        # Fixed/min widths cause clipping and label overlap on smaller windows.
        parent_layout.addLayout(cols)

    
    # --- Clinic logo (reports + diet plan watermark) ---
    def _assets_dir(self) -> Path:
        # src/ui/screens/settings.py -> src
        return Path(__file__).resolve().parents[2] / "assets"

    def _assets_user_dir(self) -> Path:
        d = self._assets_dir() / "user"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _resolve_setting_path(self, rel_or_abs: str) -> str:
        if not rel_or_abs:
            return ""
        p = Path(rel_or_abs)
        if p.is_absolute():
            return str(p)
        # relative paths are relative to src/
        base = Path(__file__).resolve().parents[2]  # src
        return str((base / rel_or_abs).resolve())

    def _update_logo_status(self):
        rel = self.svc.get_value("clinic_logo_path", "") or ""
        abs_path = self._resolve_setting_path(rel)
        if abs_path and Path(abs_path).exists():
            self.lbl_logo_status.setText("Yüklü ✅")
            self.btn_logo_clear.setEnabled(True)
        else:
            self.lbl_logo_status.setText("Yüklü değil (varsayılan NutriNexus kullanılacak)")
            self.btn_logo_clear.setEnabled(False)

    def _pick_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Logo Seç (PNG/JPG)",
            "",
            "Görseller (*.png *.jpg *.jpeg)"
        )
        if not path:
            return

        img = QImage(path)
        if img.isNull():
            QMessageBox.warning(self, "Logo", "Seçilen dosya okunamadı.")
            return

        # Minimum kalite: küçük logolar baskı/filigranda kötü görünür.
        # Hedef: header'da net, filigranda piksellenmeyen logo.
        min_w, min_h = 800, 200
        if img.width() < min_w or img.height() < min_h:
            QMessageBox.warning(
                self,
                "Logo",
                f"Logo çözünürlüğü çok düşük. En az {min_w}x{min_h} px olmalı.\n"
                f"Seçilen: {img.width()}x{img.height()} px"
            )
            return

        user_dir = self._assets_user_dir()
        logo_dst = user_dir / "clinic_logo.png"
        wm_dst = user_dir / "clinic_logo_watermark.png"

        # Copy as PNG (normalize format)
        img.save(str(logo_dst), "PNG")

        # Build watermark: keep aspect, soft opacity via alpha
        target_w = 520
        scaled = img.scaledToWidth(target_w, Qt.SmoothTransformation)
        wm = QImage(scaled.size(), QImage.Format_ARGB32)
        wm.fill(Qt.transparent)

        painter = QPainter(wm)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setOpacity(0.07)
        painter.drawImage(0, 0, scaled)
        painter.end()
        wm.save(str(wm_dst), "PNG")

        # Store relative paths (relative to src/)
        rel_logo = "assets/user/clinic_logo.png"
        rel_wm = "assets/user/clinic_logo_watermark.png"
        self.svc.set_value("clinic_logo_path", rel_logo)
        self.svc.set_value("clinic_logo_watermark_path", rel_wm)

        self._update_logo_status()
        QMessageBox.information(self, "Logo", "Logo kaydedildi. Raporlarda ve diyet planı filigranında kullanılacak.")

    def _clear_logo(self):
        # Remove settings; keep files (optional)
        self.svc.set_value("clinic_logo_path", "")
        self.svc.set_value("clinic_logo_watermark_path", "")
        self._update_logo_status()

    def _load(self):
        # App settings
        self.txt_clinic_name.setText(self.svc.get_value("clinic_name", "") or "")
        self.txt_clinic_phone.setText(self.svc.get_value("clinic_phone", "") or "")
        self.txt_clinic_email.setText(self.svc.get_value("clinic_email", "") or "")
        self.txt_clinic_address.setPlainText(self.svc.get_value("clinic_address", "") or "")
        self.txt_report_footer.setPlainText(self.svc.get_value("report_footer", "") or "")

        self.sp_default_kcal.setValue(self.svc.get_int("default_kcal", 2000))
        pol = (self.svc.get_value("backup_policy", "Kapalı") or "Kapalı").strip()
        idx = self.cmb_backup_policy.findText(pol)
        self.cmb_backup_policy.setCurrentIndex(idx if idx >= 0 else 0)
        self.sp_backup_keep.setValue(self.svc.get_int("backup_keep", 14))

        # Appointment notifications
        self.chk_appt_notifications.setChecked(self.svc.get_int("appointments.notify_enabled", 1) == 1)
        self.sp_appt_remind.setValue(self.svc.get_int("appointments.notify_minutes_before", 0))

        # Clinical thresholds
        th = self.svc.get_clinical_thresholds()
        self.sp_weight_info.setValue(float(th.get("weight_rate_info", DEFAULT_CLINICAL_THRESHOLDS["weight_rate_info"])))
        self.sp_weight_warn.setValue(float(th.get("weight_rate_warn", DEFAULT_CLINICAL_THRESHOLDS["weight_rate_warn"])))
        self.sp_waist_info.setValue(float(th.get("waist_info", DEFAULT_CLINICAL_THRESHOLDS["waist_info"])))
        self.sp_waist_warn.setValue(float(th.get("waist_warn", DEFAULT_CLINICAL_THRESHOLDS["waist_warn"])))

        self.sp_crp_warn.setValue(float(th.get("crp_warn", DEFAULT_CLINICAL_THRESHOLDS["crp_warn"])))
        self.sp_hba1c_warn.setValue(float(th.get("hba1c_warn", DEFAULT_CLINICAL_THRESHOLDS["hba1c_warn"])))
        self.sp_hba1c_critical.setValue(float(th.get("hba1c_critical", DEFAULT_CLINICAL_THRESHOLDS["hba1c_critical"])))

        self.sp_ldl_warn.setValue(float(th.get("ldl_warn", DEFAULT_CLINICAL_THRESHOLDS["ldl_warn"])))
        self.sp_ldl_critical.setValue(float(th.get("ldl_critical", DEFAULT_CLINICAL_THRESHOLDS["ldl_critical"])))

        self._update_logo_status()

    def _reset_defaults(self):
        th = dict(DEFAULT_CLINICAL_THRESHOLDS)
        self.sp_weight_info.setValue(float(th["weight_rate_info"]))
        self.sp_weight_warn.setValue(float(th["weight_rate_warn"]))
        self.sp_waist_info.setValue(float(th["waist_info"]))
        self.sp_waist_warn.setValue(float(th["waist_warn"]))

        self.sp_crp_warn.setValue(float(th["crp_warn"]))
        self.sp_hba1c_warn.setValue(float(th["hba1c_warn"]))
        self.sp_hba1c_critical.setValue(float(th["hba1c_critical"]))

        self.sp_ldl_warn.setValue(float(th["ldl_warn"]))
        self.sp_ldl_critical.setValue(float(th["ldl_critical"]))

    def _save(self, *, show_popup: bool = True):
        th = {
            "weight_rate_info": float(self.sp_weight_info.value()),
            "weight_rate_warn": float(self.sp_weight_warn.value()),
            "waist_info": float(self.sp_waist_info.value()),
            "waist_warn": float(self.sp_waist_warn.value()),
            "crp_warn": float(self.sp_crp_warn.value()),
            "hba1c_warn": float(self.sp_hba1c_warn.value()),
            "hba1c_critical": float(self.sp_hba1c_critical.value()),
            "ldl_warn": float(self.sp_ldl_warn.value()),
            "ldl_critical": float(self.sp_ldl_critical.value()),
        }
        self.svc.save_clinical_thresholds(th)
        if show_popup:
            QMessageBox.information(self, "Kaydedildi", "Klinik eşik ayarları kaydedildi.")

    
    def _save_all(self):
        """Save both clinical thresholds and app settings with a single confirmation."""
        # Save clinical thresholds (existing behavior)
        self._save(show_popup=False)
        # Save app settings (notifications etc.)
        self._save_app(show_popup=False)

        # Small inline feedback (non-blocking)
        try:
            self.lbl_saved.setText("Kaydedildi ✓")
            QTimer.singleShot(2500, lambda: self.lbl_saved.setText(""))
        except Exception:
            # As a fallback, do nothing (never crash settings screen)
            pass

    def _save_app(self, *, show_popup: bool = True):
        self.svc.set_value("clinic_name", self.txt_clinic_name.text().strip())
        self.svc.set_value("clinic_phone", self.txt_clinic_phone.text().strip())
        self.svc.set_value("clinic_email", self.txt_clinic_email.text().strip())
        self.svc.set_value("clinic_address", self.txt_clinic_address.toPlainText().strip())
        self.svc.set_value("report_footer", self.txt_report_footer.toPlainText().strip())
        self.svc.set_int("default_kcal", int(self.sp_default_kcal.value()))
        self.svc.set_value("backup_policy", self.cmb_backup_policy.currentText())
        self.svc.set_int("backup_keep", int(self.sp_backup_keep.value()))

        # Appointment notifications
        self.svc.set_int("appointments.notify_enabled", 1 if self.chk_appt_notifications.isChecked() else 0)
        self.svc.set_int("appointments.notify_minutes_before", int(self.sp_appt_remind.value()))
        if show_popup:
            QMessageBox.information(self, "Kaydedildi", "Ayarlar kaydedildi.")
