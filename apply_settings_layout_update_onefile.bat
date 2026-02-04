
@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
set "TARGET_SCREEN_DIR=%SCRIPT_DIR%src\ui\screens"
set "TARGET_THEME_DIR=%SCRIPT_DIR%src\ui\theme"

if not exist "%TARGET_SCREEN_DIR%" (
  echo Missing target folder: %TARGET_SCREEN_DIR%
  exit /b 1
)

if not exist "%TARGET_THEME_DIR%" (
  echo Missing target folder: %TARGET_THEME_DIR%
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$settings = @'
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
        self.chk_appt_notifications.setObjectName("SettingsCheck")
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
        grid.setHorizontalSpacing(22)
        grid.setVerticalSpacing(12)

        # column sizing
        grid.setColumnMinimumWidth(0, 160)
        grid.setColumnMinimumWidth(2, 190)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        def _lbl(text: str) -> QLabel:
            l = QLabel(text)
            l.setObjectName("SettingsLabel")
            l.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
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
        logo_row.setObjectName("SettingsInlineRow")
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

'@
Set-Content -Path '%TARGET_SCREEN_DIR%\settings.py' -Value $settings -Encoding UTF8

$style = @'
/* NutriNexus Modern QSS (Sprint-0.1)
   - Attığın tasarım referansına uygun: koyu teal zemin + yeşil vurgu
*/

* { font-family: "Segoe UI"; font-size: 10.5pt; }

/* Göz yormayan açık zemin (tam beyaz değil) */
QMainWindow { background: #E9EEF2; }

/* Layout blocks */
QFrame#Sidebar {
  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0D5E73, stop:0.55 #0A4258, stop:1 #082C3F);
  border-right: 1px solid rgba(255,255,255,0.10);
}

/* Sidebar brand: sadece logo, daha dolu ve kurumsal */
QFrame#SidebarBrand {
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 14px;
}

QLabel#SidebarLogo { padding: 0px; }

QFrame#Content {
  background: #E9EEF2;
}

QFrame#Topbar {
  /* referans görseldeki gibi hafif yeşil tonlu cam efekti */
  background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                              stop:0 rgba(255,255,255,0.80),
                              stop:1 rgba(233, 245, 236, 0.86));
  border: 1px solid rgba(0,0,0,0.06);
  border-radius: 14px;
}

QLabel#BrandText {
  color: #DFF3F7;
  font-size: 12.5pt;
  font-weight: 800;
}

QLabel#UserChip {
  color: rgba(12, 42, 51, 0.82);
  font-weight: 650;
  background: rgba(12, 42, 51, 0.06);
  border: 1px solid rgba(12, 42, 51, 0.10);
  border-radius: 999px;
  padding: 6px 10px;
  font-weight: 700;
}

QLabel#Breadcrumb {
  color: rgba(12, 42, 51, 0.72);
  font-weight: 700;
}

QLabel#PageTitle {
  color: #0C2A33;
  font-size: 16pt;
  font-weight: 800;
}

QLabel#PageSubtitle {
  color: rgba(12, 42, 51, 0.62);
  font-size: 10.5pt;
  font-weight: 500;
  margin-top: -2px;
  margin-bottom: 6px;
}


QLabel#DialogTitle {
  font-size: 18px;
  font-weight: 700;
  color: #0E2B2E;
}

QLabel#CardTitle {
  font-size: 18px;
  font-weight: 800;
  color: rgba(12, 42, 51, 0.92);
}

QLabel#SubTitle {
  color: rgba(12, 42, 51, 0.60);
}

/* Info chips (client header) */
QLabel[chip="1"] {
  background: rgba(12, 42, 51, 0.06);
  border: 1px solid rgba(12, 42, 51, 0.10);
  border-radius: 999px;
  padding: 6px 10px;
  color: rgba(12, 42, 51, 0.86);
  font-size: 9.6pt;
}

QLabel[chip="1"][tone="info"] {
  background: rgba(37, 99, 235, 0.10);
  border: 1px solid rgba(37, 99, 235, 0.22);
}

QLabel[chip="1"][tone="success"] {
  background: rgba(34, 197, 94, 0.12);
  border: 1px solid rgba(34, 197, 94, 0.22);
}


/* Cards */
QFrame#Card {
  background: #F7FAFC;
  border: 1px solid rgba(12, 42, 51, 0.09);
  border-radius: 16px;
}


[tone="warning"] {
  background: rgba(234, 179, 8, 0.16);
  border: 1px solid rgba(234, 179, 8, 0.40);
  color: rgba(120, 53, 15, 0.92);
}

[tone="danger"] {
  background: rgba(239, 68, 68, 0.14);
  border: 1px solid rgba(239, 68, 68, 0.40);
  color: rgba(127, 29, 29, 0.92);
}

QFrame#Card QLabel { color: rgba(12, 42, 51, 0.86); }

/* Inputs */
QLineEdit#Input, QTextEdit#Input, QPlainTextEdit#Input, QDateEdit#Input, QTimeEdit#Input, QComboBox#Input, QSpinBox#Input {
  background: #FBFDFE;
  border: 1px solid rgba(12, 42, 51, 0.14);
  border-radius: 12px;
  padding: 10px 12px;
  color: rgba(12, 42, 51, 0.92);
}

/* Settings screen: tighten/center text in boxes without affecting other stable screens */
QWidget#SettingsPage QLineEdit#Input,
QWidget#SettingsPage QDateEdit#Input,
QWidget#SettingsPage QComboBox#Input,
QWidget#SettingsPage QSpinBox#Input,
QWidget#SettingsPage QDoubleSpinBox#Input {
  /* Keep compact and vertically centered (do NOT inflate rows) */
  min-height: 30px;
  padding: 6px 10px;
}

QWidget#SettingsPage QTextEdit#Input,
QWidget#SettingsPage QPlainTextEdit#Input {
  padding: 8px 12px;
}

/* Settings: multiline "memo" fields should look more prominent */
QWidget#SettingsPage QTextEdit#InputStrong,
QWidget#SettingsPage QPlainTextEdit#InputStrong {
  background: #FFFFFF;
  border: 1px solid rgba(12, 42, 51, 0.22);
  border-radius: 12px;
  padding: 10px 12px;
}

QWidget#SettingsPage QTextEdit#InputStrong:focus,
QWidget#SettingsPage QPlainTextEdit#InputStrong:focus {
  border: 1px solid rgba(102,179,90,0.85);
}

QWidget#SettingsPage QComboBox#Input {
  padding-right: 34px; /* keep space for drop-down arrow */
}

/* Settings: clearer labels + inline rows */
QWidget#SettingsPage QLabel#SettingsLabel {
  color: rgba(12, 42, 51, 0.78);
  font-weight: 650;
  padding: 2px 6px 2px 0px;
}

QWidget#SettingsPage QCheckBox#SettingsCheck {
  background: rgba(12, 42, 51, 0.04);
  border: 1px solid rgba(12, 42, 51, 0.12);
  border-radius: 10px;
  padding: 6px 10px;
  color: rgba(12, 42, 51, 0.86);
}

QWidget#SettingsPage QWidget#SettingsInlineRow {
  background: rgba(255,255,255,0.60);
  border: 1px solid rgba(12, 42, 51, 0.12);
  border-radius: 10px;
  padding: 4px 6px;
}

/* Bazı ekranlarda (özellikle Anamnez) input'lar objectName almadan oluşturulabiliyor.
   Qt'nin default palette'i bazı sistemlerde koyu (neredeyse siyah) gelebiliyor.
   Güvenli tarafta kalmak için genel input stilini de uyguluyoruz. */
QLineEdit, QTextEdit, QPlainTextEdit, QDateEdit, QComboBox {
  background: #FBFDFE;
  color: rgba(12, 42, 51, 0.92);
  border: 1px solid rgba(12, 42, 51, 0.14);
  border-radius: 12px;
  padding: 10px 12px;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QDateEdit:focus, QComboBox:focus {
  border: 1px solid rgba(102,179,90,0.85);
}

QLineEdit#Input:focus, QTextEdit#Input:focus, QPlainTextEdit#Input:focus, QDateEdit#Input:focus, QComboBox#Input:focus {
  border: 1px solid rgba(102,179,90,0.85);
}

QComboBox#Input::drop-down {
  border: none;
  width: 26px;
}

QComboBox#Input::down-arrow {
  image: none;
  border-left: 6px solid transparent;
  border-right: 6px solid transparent;
  border-top: 7px solid rgba(12, 42, 51, 0.55);
  margin-right: 10px;
}

QLineEdit#Input:focus, QTextEdit#Input:focus, QPlainTextEdit#Input:focus {
  border: 1px solid #66B35A;
}

/* Nav buttons (ikon üstte, yazı altta, ortalı) */
QToolButton#NavBtn {
  qproperty-toolButtonStyle: ToolButtonTextUnderIcon;
  text-align: center;
  padding: 14px 10px;
  border-radius: 14px;
  color: rgba(255,255,255,0.98);
  background: transparent;
  border: 1px solid transparent;
  font-weight: 750;
  font-size: 14px;
}

QToolButton#NavBtn:hover {
  background: rgba(255,255,255,0.07);
  border: 1px solid rgba(255,255,255,0.10);
  color: rgba(255,255,255,1.0);
}

QToolButton#NavBtn[active="true"] {
  background: rgba(102,179,90,0.18);
  border: 1px solid rgba(102,179,90,0.35);
  color: rgba(255,255,255,0.95);
}

/* Buttons */
QPushButton#PrimaryBtn {
background: #5FAF5B;
color: #0B1F17;
border: 1px solid #4E9F4A;
border-radius: 12px;
padding: 8px 16px;
font-weight: 700;

}


QPushButton#PrimaryBtn:disabled {
  background: #B8D8B5;
  color: #F5F5F5;
}
QPushButton#PrimaryBtn:hover {
  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #7BDA72, stop:1 #57AD53);
}

QPushButton#PrimaryBtn:pressed {
  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #55B14F, stop:1 #3E8E3A);
}
QPushButton#PrimaryBtn:hover { background: #74C468; }

QPushButton#SecondaryBtn {
background: #E7EEF1;
color: #0B1F17;
border: 1px solid #D0DADF;
border-radius: 12px;
padding: 8px 16px;
font-weight: 700;

}

/* --- Action-colored buttons (UX polish) --- */
QPushButton#PrimaryBlueBtn {
  background: #2563EB;
  color: #ffffff;
  border: 1px solid #1D4ED8;
  border-radius: 12px;
  padding: 8px 16px;
  font-weight: 700;
}
QPushButton#PrimaryBlueBtn:hover { background: #1D4ED8; }
QPushButton#PrimaryBlueBtn:pressed { background: #1E40AF; }
QPushButton#PrimaryBlueBtn:disabled { background: #A7C1F7; color: rgba(255,255,255,0.95); border: 1px solid #A7C1F7; }

QPushButton#InfoBtn {
  background: rgba(37, 99, 235, 0.08);
  color: #1E40AF;
  border: 1px solid rgba(37, 99, 235, 0.30);
  border-radius: 12px;
  padding: 8px 16px;
  font-weight: 700;
}
QPushButton#InfoBtn:hover { background: rgba(37, 99, 235, 0.14); }
QPushButton#InfoBtn:disabled { background: rgba(37, 99, 235, 0.05); color: rgba(30,64,175,0.45); border: 1px solid rgba(37, 99, 235, 0.18); }

QPushButton#IndigoBtn {
  background: #6366F1;
  color: #ffffff;
  border: 1px solid #4F46E5;
  border-radius: 12px;
  padding: 8px 16px;
  font-weight: 700;
}
QPushButton#IndigoBtn:hover { background: #4F46E5; }
QPushButton#IndigoBtn:pressed { background: #4338CA; }
QPushButton#IndigoBtn:disabled { background: #C7C8FB; color: rgba(255,255,255,0.95); border: 1px solid #C7C8FB; }

QPushButton#NeutralBtn {
  background: rgba(107, 114, 128, 0.10);
  color: rgba(12, 42, 51, 0.82);
  border: 1px solid rgba(107, 114, 128, 0.25);
  border-radius: 12px;
  padding: 8px 16px;
  font-weight: 700;
}
QPushButton#NeutralBtn:hover { background: rgba(107, 114, 128, 0.16); }
QPushButton#NeutralBtn:disabled { background: rgba(107, 114, 128, 0.06); color: rgba(12, 42, 51, 0.35); border: 1px solid rgba(107, 114, 128, 0.16); }

QPushButton#DangerBtn {
  padding: 8px 16px;
  border-radius: 12px;
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #E65A5A, stop:1 #C83A3A);
  color: white;
  font-weight: 700;
  border: 1px solid rgba(0,0,0,0.10);
}
QPushButton#WarningBtn {
  background: #EAF3FF;
  border: 1px solid rgba(37, 99, 235, 0.22);
  color: rgba(12, 42, 51, 0.86);
  border-radius: 12px;
  padding: 9px 14px;
  font-weight: 700;
}
QPushButton#WarningBtn:hover { background: #DDEBFF; }
QPushButton#WarningBtn:disabled { background: rgba(12,42,51,0.05); color: rgba(12,42,51,0.35); border-color: rgba(12,42,51,0.08); }

QPushButton#DangerBtn:hover { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #F06A6A, stop:1 #D14848); }
QPushButton#DangerBtn:disabled { background: #C9CDD1; color: #6B7178; }

QPushButton#SecondaryBtn:hover {
  background: rgba(12, 42, 51, 0.09);
}
QPushButton#SecondaryBtn:hover { background: rgba(255,255,255,0.12); }

QPushButton#GhostBtn {
  background: rgba(12, 42, 51, 0.04);
  color: rgba(12, 42, 51, 0.80);
  border: 1px solid rgba(12, 42, 51, 0.14);
  border-radius: 12px;
  padding: 12px 16px;
  font-weight: 700;
}
QPushButton#GhostBtn:hover {
  background: rgba(12, 42, 51, 0.07);
}

/* Tabs */
QTabWidget#ClientTabs::pane, QTabWidget#InnerTabs::pane {
  border: 1px solid rgba(12, 42, 51, 0.10);
  border-radius: 14px;
  background: #F7FAFC;
}

QTabBar::tab {
  background: rgba(12, 42, 51, 0.06);
  color: rgba(12, 42, 51, 0.78);
  padding: 12px 16px;
  border-top-left-radius: 12px;
  border-top-right-radius: 12px;
  margin-right: 6px;
}


QTabBar::tab:hover {
  background: rgba(12, 42, 51, 0.09);
}

QTabBar::tab:selected {
  background: rgba(102,179,90,0.18);
  color: rgba(12, 42, 51, 0.90);
  border: 1px solid rgba(102,179,90,0.45);
}

/* Table */
QTableWidget#Table {
  background: #FBFDFE;
  color: rgba(12, 42, 51, 0.88);
  gridline-color: rgba(12, 42, 51, 0.08);
  border: 1px solid rgba(12, 42, 51, 0.10);
  border-radius: 12px;
}

/*
  Global Table Theme
  Bazı ekranlarda tablo objectName'i "Table" olmayabiliyor.
  Bu durumda Qt'nin default palette'i (koyu/siyah) devreye giriyor.
  Aşağıdaki stiller tüm QTableWidget/QTableView bileşenlerini NutriNexus temasına zorlar.
*/
QTableWidget, QTableView {
  background: #FBFDFE;
  alternate-background-color: rgba(12, 42, 51, 0.03);
  color: rgba(12, 42, 51, 0.88);
  gridline-color: rgba(12, 42, 51, 0.08);
  border: 1px solid rgba(12, 42, 51, 0.10);
  border-radius: 12px;
}

QTableWidget::item, QTableView::item {
  padding: 8px;
}

QTableWidget::item:selected, QTableView::item:selected {
  background: rgba(102,179,90,0.26);
  color: rgba(12, 42, 51, 0.92);
}

QTableWidget::item:focus, QTableView::item:focus {
  outline: none;
  border: none;
}

/* Measurements Screen - extra readability / "premium" table feel */
QWidget#MeasurementsScreen QHeaderView::section {
  font-weight: 800;
  font-size: 14px;
  color: rgba(9, 29, 36, 0.94);
  padding: 12px 12px;
}

QWidget#MeasurementsScreen QTableWidget#MeasurementsTable::item {
  font-weight: 700;
  font-size: 14px;
  color: rgba(9, 29, 36, 0.96);
}

QWidget#MeasurementsScreen QTableWidget#MeasurementsTable::item:alternate {
  background: rgba(12, 42, 51, 0.035);
}

QWidget#MeasurementsScreen QTableWidget#MeasurementsTable::item:hover {
  background: rgba(102,179,90,0.14);
}

/* Measurements detail panel (right) */
QWidget#MeasurementsScreen QLabel#DetailTitle {
  font-weight: 900;
  font-size: 15px;
  color: rgba(9, 29, 36, 0.96);
}

QWidget#MeasurementsScreen QLabel#DetailChip,
QWidget#MeasurementsScreen QLabel#DetailChipSuccess {
  padding: 6px 10px;
  border-radius: 10px;
  font-weight: 800;
  font-size: 12px;
}

QWidget#MeasurementsScreen QLabel#DetailChip {
  background: rgba(12, 42, 51, 0.06);
  border: 1px solid rgba(12, 42, 51, 0.10);
  color: rgba(9, 29, 36, 0.90);
}

QWidget#MeasurementsScreen QLabel#DetailChipSuccess {
  background: rgba(102,179,90,0.20);
  border: 1px solid rgba(102,179,90,0.55);
  color: rgba(9, 29, 36, 0.92);
}

QWidget#MeasurementsScreen QWidget#KVRow {
  background: rgba(255,255,255,0.72);
  border: 1px solid rgba(12, 42, 51, 0.10);
  border-radius: 12px;
}

QWidget#MeasurementsScreen QLabel#KVKey {
  color: rgba(12, 42, 51, 0.72);
  font-weight: 800;
  font-size: 12px;
}

QWidget#MeasurementsScreen QLabel#KVValue {
  background: rgba(12, 42, 51, 0.06);
  border: 1px solid rgba(12, 42, 51, 0.10);
  border-radius: 10px;
  padding: 5px 10px;
  min-width: 74px;
  qproperty-alignment: 'AlignVCenter|AlignRight';
  color: rgba(9, 29, 36, 0.96);
  font-weight: 900;
  font-size: 13px;
}

QWidget#MeasurementsScreen QLabel#DetailNote {
  background: rgba(255,255,255,0.72);
  border: 1px solid rgba(12, 42, 51, 0.10);
  border-radius: 12px;
  padding: 10px 12px;
  color: rgba(9, 29, 36, 0.92);
  font-weight: 650;
}

QHeaderView::section {
  background: #F0F4F7;
  color: rgba(12, 42, 51, 0.78);
  padding: 10px 10px;
  border: none;
  border-bottom: 1px solid rgba(12, 42, 51, 0.08);
}

QTableCornerButton::section {
  background: #F0F4F7;
  border: none;
  border-bottom: 1px solid rgba(12, 42, 51, 0.08);
  border-right: 1px solid rgba(12, 42, 51, 0.08);
}

QTableWidget#Table::item {
  padding: 8px;
}

QTableWidget#Table::item:alternate {
  background: rgba(12, 42, 51, 0.03);
}

QHeaderView::section {
  background: #F0F4F7;
  color: rgba(12, 42, 51, 0.78);
  padding: 10px 10px;
  border: none;
  border-bottom: 1px solid rgba(12, 42, 51, 0.08);
}

QTableWidget::item:selected {
  background: rgba(102,179,90,0.26);
  color: rgba(12, 42, 51, 0.92);
}

QTableWidget::item:focus {
  outline: none;
  border: none;
}

QLabel#PhonePrefix { color: white; background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.18); border-radius: 10px; padding: 8px 12px; font-weight: 700; min-width: 46px; }

/* Sprint-2A: Anamnez (açılır/kapanır) */
QToolBox#AnamnezToolbox {
  background: transparent;
}
QToolBox#AnamnezToolbox::tab {
  background: rgba(12, 42, 51, 0.06);
  color: #0C2A33;
  padding: 12px 14px;
  border-radius: 12px;
  margin-top: 8px;
  font-weight: 700;
  font-size: 14px;
}

QToolBox#AnamnezToolbox::tab:selected {
  background: rgba(102,179,90,0.18);
  border: 1px solid rgba(102,179,90,0.45);
  color: #0C2A33;
}

/* Form label in content area */
QLabel#FormLabel {
  color: rgba(12, 42, 51, 0.78);
  font-weight: 650;
}

/* Content labels (used in cards) */
QLabel#FieldLabel {
  color: rgba(12, 42, 51, 0.78);
  font-weight: 650;
  margin-top: 8px;
}

QLabel#Hint {
color: rgba(12, 42, 51, 0.92);
font-size: 13px;

}

QToolBox#AnamnezToolbox::pane {
  /* bazı sistemlerde QToolBox pane varsayılanı koyu gelebiliyor (siyah blok).
     Pane'i açık bir "kart" gibi sabitleyip tüm içerik için güvenli zemin veriyoruz. */
  border: 1px solid rgba(12, 42, 51, 0.10);
  background: #F7FAFC;
  border-radius: 16px;
  padding: 10px;
}

/* QToolBox iç sayfalarının da şeffaflık/tema çakışmasıyla kararmasını engelle */
QToolBox#AnamnezToolbox QWidget {
  background: transparent;
}

/* Anamnez scroll viewport'u bazı makinelerde koyu palette'e düşebiliyor */
QScrollArea#AnamnezScroll, QScrollArea#AnamnezScroll QWidget#AnamnezContainer {
  background: transparent;
}


QToolBox::tab {
  color: #0C2A33;
  font-size: 14px;
}



/* --- FIX: QToolBox sekme yazılarının bazı sistemlerde görünmemesi (Qt palette farkı) --- */
QToolBox#AnamnezToolbox QToolButton {
  background: rgba(12, 42, 51, 0.06);
  color: #0C2A33;
  border: 1px solid rgba(12, 42, 51, 0.10);
  border-radius: 12px;
  padding: 12px 14px;
  margin-top: 8px;
  font-weight: 700;
  font-size: 14px;
  text-align: left;
}

/* =====================
   Anamnez Accordion
   ===================== */

QToolButton#AccordionHeader {
    background: #F3F6F8;
    color: #0C2A33;
    border: 1px solid #D8E1E6;
    border-radius: 12px;
    padding: 12px 14px;
    font-weight: 700;
}

QToolButton#AccordionHeader:hover {
    background: #EEF3F6;
}

QToolButton#AccordionHeader:checked {
    background: #EAF6EE;
    border: 1px solid #86C08D;
}

QFrame#AccordionBody {
    background: #FFFFFF;
    border: 1px solid #D8E1E6;
    border-radius: 12px;
}

QToolBox#AnamnezToolbox QToolButton:checked {
  background: rgba(102,179,90,0.18);
  border: 1px solid rgba(102,179,90,0.45);
}

QToolBox#AnamnezToolbox QToolButton:hover {
  background: rgba(12, 42, 51, 0.10);
}


/* =====================
   Hesaplamalar (Sprint-3)
   ===================== */

QFrame#InnerCard {
  background: rgba(255,255,255,0.78);
  border: 1px solid rgba(12, 42, 51, 0.10);
  border-radius: 16px;
}

QLabel#SectionTitle {
  font-size: 12pt;
  font-weight: 800;
  color: rgba(12, 42, 51, 0.86);
}

QLabel#SectionHeader {
  font-size: 10pt;
  font-weight: 800;
  color: rgba(12, 42, 51, 0.72);
  padding: 2px 0px 2px 0px;
}

QFrame#InfoBox {
  background: rgba(233, 245, 236, 0.80);
  border: 1px solid rgba(102,179,90,0.25);
  border-radius: 14px;
}

QLabel#FieldValue {
  font-weight: 800;
  font-size: 12pt;
  color: rgba(12, 42, 51, 0.92);
}

QLabel#Muted {
  color: rgba(12, 42, 51, 0.55);
}

QFrame#MetricBox {
  background: rgba(255,255,255,0.86);
  border: 1px solid rgba(12, 42, 51, 0.10);
  border-radius: 16px;
}

QLabel#MetricTitle {
  color: rgba(12, 42, 51, 0.60);
  font-weight: 800;
  font-size: 10.5pt;
}

QLabel#MetricValue {
  color: rgba(12, 42, 51, 0.92);
  font-weight: 900;
  font-size: 16pt;
}



/* Lists (Archive / history) */
QListWidget {
  background: #FBFDFE;
  border: 1px solid rgba(12, 42, 51, 0.12);
  border-radius: 12px;
  padding: 6px;
  color: rgba(12, 42, 51, 0.86);
}

QListWidget::item {
  padding: 8px 10px;
  margin: 2px 0px;
  border-radius: 8px;
}

QListWidget::item:selected {
  background: rgba(19, 116, 109, 0.16); /* NutriNexus accent tint */
  color: rgba(12, 42, 51, 0.92);
}

QListWidget::item:hover {
  background: rgba(19, 116, 109, 0.08);
}


/* Splitter handle (Kan Tahlili gibi iki bölmeli ekranlarda siyah çizgi kalmasın) */
QSplitter::handle {
  background: rgba(12, 42, 51, 0.10);
}
QSplitter::handle:horizontal { width: 6px; margin: 0px 6px; border-radius: 3px; }
QSplitter::handle:vertical { height: 6px; margin: 6px 0px; border-radius: 3px; }

/* Scrollbar - açık tema uyumu */
QScrollBar:vertical {
  background: rgba(12, 42, 51, 0.05);
  width: 12px;
  margin: 2px;
  border-radius: 6px;
}
QScrollBar::handle:vertical {
  background: rgba(12, 42, 51, 0.18);
  min-height: 24px;
  border-radius: 6px;
}
QScrollBar::handle:vertical:hover { background: rgba(12, 42, 51, 0.26); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }

QScrollBar:horizontal {
  background: rgba(12, 42, 51, 0.05);
  height: 12px;
  margin: 2px;
  border-radius: 6px;
}
QScrollBar::handle:horizontal {
  background: rgba(12, 42, 51, 0.18);
  min-width: 24px;
  border-radius: 6px;
}
QScrollBar::handle:horizontal:hover { background: rgba(12, 42, 51, 0.26); }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }

/* TabWidget pane border (Kritikler sekmelerinde koyu çerçeve kalmasın) */
QTabWidget::pane {
  border: 1px solid rgba(12, 42, 51, 0.10);
  border-radius: 12px;
  top: -1px;
  background: #FBFDFE;
}



/* Spin boxes (kcal vb.) */
QSpinBox#Input, QDoubleSpinBox#Input, QAbstractSpinBox#Input,
QSpinBox, QDoubleSpinBox, QAbstractSpinBox {
  background: #FBFDFE;
  color: rgba(12, 42, 51, 0.92);
  border: 1px solid rgba(12, 42, 51, 0.14);
  border-radius: 12px;
  padding: 8px 10px;
}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
  width: 18px;
  background: transparent;
  border: none;
}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {
  background: rgba(12, 42, 51, 0.06);
  border-radius: 8px;
}

/* Combo popup list - karanlık tema sızıntısını engelle */
QComboBox QAbstractItemView, QListView, QTableView {
  background: #FFFFFF;
  color: rgba(12, 42, 51, 0.92);
  selection-background-color: rgba(102,179,90,0.25);
  selection-color: rgba(12, 42, 51, 0.98);
  border: 1px solid rgba(12, 42, 51, 0.14);
  outline: 0;
}

/* Date picker calendar */
QCalendarWidget QWidget {
  background: #FFFFFF;
  color: rgba(12, 42, 51, 0.92);
}
QCalendarWidget QToolButton {
  background: rgba(102,179,90,0.18);
  color: rgba(12, 42, 51, 0.92);
  border: 1px solid rgba(12, 42, 51, 0.10);
  border-radius: 10px;
  padding: 6px 10px;
}
QCalendarWidget QMenu {
  background: #FFFFFF;
  color: rgba(12, 42, 51, 0.92);
  border: 1px solid rgba(12, 42, 51, 0.14);
}
QCalendarWidget QAbstractItemView {
  background: #FFFFFF;
  color: rgba(12, 42, 51, 0.92);
  selection-background-color: rgba(102,179,90,0.25);
  selection-color: rgba(12, 42, 51, 0.98);
  outline: 0;
}

/* Compare checkbox görünürlüğü */
QCheckBox#CompareCheck {
  padding: 6px 10px;
  border-radius: 10px;
  border: 1px solid rgba(12, 42, 51, 0.12);
  background: rgba(255,255,255,0.65);
  color: rgba(12, 42, 51, 0.92);
  font-weight: 700;
}
QCheckBox#CompareCheck:hover {
  background: rgba(102,179,90,0.12);
  border: 1px solid rgba(102,179,90,0.35);
}
QCheckBox::indicator {
  width: 18px;
  height: 18px;
}
QCheckBox::indicator:unchecked {
  border: 1px solid rgba(12, 42, 51, 0.22);
  border-radius: 6px;
  background: #FFFFFF;
}
QCheckBox::indicator:checked {
  border: 1px solid rgba(102,179,90,0.55);
  border-radius: 6px;
  background: rgba(102,179,90,0.55);
}


/* --- Dialogs: force light theme (avoid OS dark dialog background) --- */
QDialog {
  background: #E9EEF2;
  color: rgba(12, 42, 51, 0.92);
}
QDialog QWidget {
  background: transparent;
  color: rgba(12, 42, 51, 0.92);
}

/* --- Date/Calendar widgets: ensure numbers are visible --- */
QDateEdit, QDateTimeEdit {
  background: #FFFFFF;
  color: rgba(12, 42, 51, 0.92);
}
QCalendarWidget {
  background: #FFFFFF;
  color: rgba(12, 42, 51, 0.92);
  border: 1px solid rgba(12,42,51,0.18);
  border-radius: 10px;
}
QCalendarWidget QToolButton {
  background: rgba(82, 159, 215, 0.12);
  color: rgba(12, 42, 51, 0.92);
  border: 1px solid rgba(12,42,51,0.12);
  border-radius: 8px;
  padding: 6px 10px;
}
QCalendarWidget QToolButton:hover {
  background: rgba(82, 159, 215, 0.18);
}
QCalendarWidget QMenu {
  background: #FFFFFF;
  color: rgba(12, 42, 51, 0.92);
  border: 1px solid rgba(12,42,51,0.18);
}
QCalendarWidget QSpinBox {
  background: #FFFFFF;
  color: rgba(12, 42, 51, 0.92);
  border: 1px solid rgba(12,42,51,0.18);
  border-radius: 8px;
  padding: 4px 8px;
}
QCalendarWidget QAbstractItemView {
  background: #FFFFFF;
  color: rgba(12, 42, 51, 0.92);
  selection-background-color: rgba(126, 191, 126, 0.55);
  selection-color: rgba(12, 42, 51, 0.92);
  outline: 0;
}


/* --- Calendar navigation bar fixes (FIX4) --- */
QCalendarWidget QToolButton {
  color: rgba(12, 42, 51, 0.95);
  background: #F3F6F8;
  border: 1px solid #D6DEE5;
  border-radius: 8px;
  padding: 4px 10px;
  margin: 4px;
}
QCalendarWidget QToolButton:hover {
  background: #E8EEF3;
}
QCalendarWidget QToolButton:pressed {
  background: #DEE7EE;
}

QCalendarWidget QMenu {
  background: #FFFFFF;
  color: rgba(12, 42, 51, 0.95);
  border: 1px solid #D6DEE5;
}

QCalendarWidget QSpinBox, 
QCalendarWidget QComboBox {
  background: #FFFFFF;
  color: rgba(12, 42, 51, 0.95);
  border: 1px solid #D6DEE5;
  border-radius: 8px;
  padding: 4px 8px;
  min-width: 90px;
}

/* =====================
   Global UI polish (2024)
   ===================== */

QPushButton {
  background: #EAF1F5;
  color: rgba(12, 42, 51, 0.92);
  border: 1px solid rgba(12, 42, 51, 0.14);
  border-radius: 12px;
  padding: 8px 14px;
  font-weight: 700;
}

QPushButton:hover {
  background: #E1EBF1;
}

QPushButton:pressed {
  background: #D7E3EA;
}

QPushButton:disabled {
  background: rgba(12, 42, 51, 0.06);
  color: rgba(12, 42, 51, 0.35);
  border: 1px solid rgba(12, 42, 51, 0.10);
}

QPushButton:checked {
  background: rgba(102,179,90,0.20);
  border: 1px solid rgba(102,179,90,0.40);
}

QToolButton {
  background: rgba(12, 42, 51, 0.04);
  color: rgba(12, 42, 51, 0.82);
  border: 1px solid rgba(12, 42, 51, 0.14);
  border-radius: 10px;
  padding: 6px 10px;
}

QToolButton:hover {
  background: rgba(12, 42, 51, 0.10);
}

QToolButton:checked {
  background: rgba(102,179,90,0.20);
  border: 1px solid rgba(102,179,90,0.40);
}

QGroupBox {
  border: 1px solid rgba(12, 42, 51, 0.10);
  border-radius: 12px;
  margin-top: 16px;
  padding: 14px 12px 12px 12px;
  background: #F7FAFC;
}

QGroupBox::title {
  subcontrol-origin: margin;
  subcontrol-position: top left;
  padding: 0 6px;
  color: rgba(12, 42, 51, 0.80);
  font-weight: 800;
}

QProgressBar {
  border: 1px solid rgba(12, 42, 51, 0.14);
  border-radius: 10px;
  background: rgba(12, 42, 51, 0.06);
  text-align: center;
  padding: 2px;
  color: rgba(12, 42, 51, 0.82);
}

QProgressBar::chunk {
  background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                              stop:0 rgba(102,179,90,0.70),
                              stop:1 rgba(37, 99, 235, 0.55));
  border-radius: 8px;
}

QStatusBar {
  background: #EEF3F6;
  border-top: 1px solid rgba(12, 42, 51, 0.10);
  color: rgba(12, 42, 51, 0.70);
}

QStatusBar QLabel {
  color: rgba(12, 42, 51, 0.70);
}

QMenu {
  background: #FFFFFF;
  color: rgba(12, 42, 51, 0.92);
  border: 1px solid rgba(12, 42, 51, 0.14);
  border-radius: 10px;
  padding: 6px;
}

QMenu::item {
  padding: 6px 12px;
  border-radius: 8px;
}

QMenu::item:selected {
  background: rgba(102,179,90,0.22);
}

QMenu::separator {
  height: 1px;
  background: rgba(12, 42, 51, 0.10);
  margin: 4px 0px;
}

QRadioButton, QCheckBox {
  color: rgba(12, 42, 51, 0.82);
  spacing: 8px;
}

QRadioButton::indicator {
  width: 16px;
  height: 16px;
  border-radius: 8px;
  border: 1px solid rgba(12, 42, 51, 0.22);
  background: #FFFFFF;
}

QRadioButton::indicator:checked {
  background: rgba(102,179,90,0.70);
  border: 1px solid rgba(102,179,90,0.55);
}

QToolTip {
  background: #0C2A33;
  color: #FFFFFF;
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 8px;
  padding: 6px 8px;
}
QCalendarWidget QSpinBox::up-button, QCalendarWidget QSpinBox::down-button {
  width: 14px;
}
QCalendarWidget QAbstractItemView:enabled {
  background: #FFFFFF;
  selection-background-color: rgba(102,179,90,0.25);
  selection-color: rgba(12, 42, 51, 0.95);
}

QLabel#BreadcrumbIcon { margin-right: 6px; }

/* Frameless Custom Title Bar */
QFrame#CustomTitleBar { background: #F7FAFC; border-bottom: 1px solid rgba(12,42,51,0.10); }
QLabel#TitleText { color: rgba(12,42,51,0.88); font-weight: 700; }
QToolButton#TitleBtnMin, QToolButton#TitleBtnMax, QToolButton#TitleBtnClose {
  background: transparent; border: none; color: rgba(12,42,51,0.70);
  min-width: 34px; min-height: 28px; border-radius: 8px; font-size: 12pt;
}
QToolButton#TitleBtnMin:hover, QToolButton#TitleBtnMax:hover { background: rgba(13,94,115,0.10); }
QToolButton#TitleBtnClose:hover { background: rgba(220,53,69,0.15); color: rgba(220,53,69,1.0); }


/* Message boxes (kurumsal tema uyumu) */
QMessageBox { background: #F7FAFC; }
QMessageBox QLabel { color: rgba(12,42,51,0.90); }
QMessageBox QPushButton {
  background: #FFFFFF;
  border: 1px solid rgba(12,42,51,0.16);
  padding: 6px 12px;
  border-radius: 8px;
}
QMessageBox QPushButton:hover { background: #F1F5F8; }
QMessageBox QPushButton#primary {
  background: #2FBF71;
  color: #FFFFFF;
  border: 1px solid rgba(0,0,0,0.06);
}
QMessageBox QPushButton#primary:hover { background: #27A861; }


/* --- Clinical Insights dialog controls --- */
QToolButton#FilterButton {
    padding: 6px 10px;
    border: 1px solid rgba(20, 28, 36, 0.12);
    border-radius: 10px;
    background: rgba(255,255,255,0.65);
}
QToolButton#FilterButton:hover {
    border: 1px solid rgba(20, 28, 36, 0.22);
    background: rgba(255,255,255,0.85);
}

QToolButton#FilterChip {
    padding: 6px 10px;
    border: 1px solid rgba(20, 28, 36, 0.12);
    border-radius: 999px;
    background: rgba(255,255,255,0.55);
}
QToolButton#FilterChip:hover {
    border: 1px solid rgba(20, 28, 36, 0.22);
    background: rgba(255,255,255,0.80);
}
QToolButton#FilterChip:checked {
    background: rgba(47, 191, 113, 0.22);
    border: 1px solid rgba(47, 191, 113, 0.45);
    color: #1B2631;
}
QLabel#ToastLabel {
    padding: 6px 10px;
    border-radius: 10px;
    font-size: 13px;
    color: #1B2631;
    background: rgba(46, 204, 113, 0.38);
    border: 1px solid rgba(46, 204, 113, 0.75);
}
QLabel#ToastLabel[ok="false"] {
    background: rgba(231, 76, 60, 0.14);
    border: 1px solid rgba(231, 76, 60, 0.30);
}

/* Toast with action buttons (Diet Plans) */
QFrame#ToastBox {
    padding: 0px;
    border-radius: 10px;
    background: rgba(46, 204, 113, 0.38);
    border: 1px solid rgba(46, 204, 113, 0.75);
}
QFrame#ToastBox[ok="false"] {
    background: rgba(231, 76, 60, 0.14);
    border: 1px solid rgba(231, 76, 60, 0.30);
}
QLabel#ToastBoxLabel {
    font-size: 13px;
    font-weight: 700;
    color: #1B2631;
}
QPushButton#ToastActionPrimary {
    padding: 5px 10px;
    border-radius: 9px;
    color: #ffffff;
    background: #2563EB;
    border: 1px solid rgba(37, 99, 235, 0.90);
}
QPushButton#ToastActionPrimary:hover {
    background: #1D4ED8;
}
QPushButton#ToastAction {
    padding: 5px 10px;
    border-radius: 9px;
    color: #1B2631;
    background: rgba(37, 99, 235, 0.10);
    border: 1px solid rgba(37, 99, 235, 0.25);
}
QPushButton#ToastAction:hover {
    background: rgba(37, 99, 235, 0.16);
}



/* --- Appointments Timeline (Sprint 6.0.4) --- */
QFrame#TimeRow {
  background: #F7FAFC;
  border: 1px solid rgba(12, 42, 51, 0.08);
  border-radius: 14px;
}

QLabel#TimeLabel {
  color: rgba(12, 42, 51, 0.78);
  font-weight: 700;
}

QLabel#TimeEmpty {
  color: rgba(12, 42, 51, 0.35);
}

QFrame#ApptCard {
  background: rgba(16, 122, 101, 0.08);
  border: 1px solid rgba(16, 122, 101, 0.20);
  border-radius: 12px;
}

QFrame#ApptCard[selected="true"] {
  background: rgba(16, 122, 101, 0.14);
  border: 2px solid rgba(16, 122, 101, 0.38);
}

QLabel#ApptTime { font-weight: 800; color: rgba(12, 42, 51, 0.90); }
QLabel#ApptClient { font-weight: 800; color: rgba(12, 42, 51, 0.90); }
QLabel#ApptTitle { color: rgba(12, 42, 51, 0.80); }
QLabel#ApptNote { color: rgba(12, 42, 51, 0.62); }
QLabel#ApptStatus {
  color: rgba(12, 42, 51, 0.70);
  background: rgba(255,255,255,0.55);
  border: 1px solid rgba(12, 42, 51, 0.10);
  border-radius: 999px;
  padding: 2px 8px;
  font-weight: 700;
}

QLabel#Hint {
color: rgba(12, 42, 51, 0.92);
font-size: 13px;

}


/* Diet Plans Vitrin (Sprint 6.2.0) */
QFrame#DietPlanPreviewCard {
  background: rgba(255,255,255,0.72);
  border: 1px solid rgba(12, 42, 51, 0.10);
  border-radius: 16px;
}

QTextBrowser#DietPlanPreviewBrowser {
  background: transparent;
  border: none;
  padding: 0px;
}

QLabel#PreviewTitle {
  font-size: 16px;
  font-weight: 900;
  color: rgba(12, 42, 51, 0.88);
}



/* --- Diet Plans (Sprint 6.2 UI Revamp) --------------------------------- */
QFrame#DietPlansLeftPane {
  background: rgba(255,255,255,0.55);
  border: 1px solid rgba(12, 42, 51, 0.10);
  border-radius: 16px;
  padding: 10px;
}

QFrame#DietPlansPreviewPane {
  background: transparent;
}

QTableWidget#DietPlansTable {
  background: rgba(255,255,255,0.70);
  border: 1px solid rgba(12, 42, 51, 0.10);
  border-radius: 14px;
  gridline-color: transparent;
}

QTableWidget#DietPlansTable::item {
  padding: 10px 10px;
}

QTableWidget#DietPlansTable::item:selected {
  background: rgba(17, 170, 191, 0.16);
  color: #082C3F;
}

QLabel#HintLabel {
  color: rgba(8, 44, 63, 0.70);
  font-size: 9.7pt;
}

QLabel#PreviewTitle {
  font-size: 16pt;
  font-weight: 800;
  color: #082C3F;
}

QLabel#SubTitle {
  color: rgba(8, 44, 63, 0.70);
}


/* Diet Plans - status chip */
QLabel#StatusChip {
  padding: 3px 10px;
  border-radius: 10px;
  font-size: 9pt;
  font-weight: 800;
}

QLabel#StatusChip[state="active"] {
  background: rgba(46, 204, 113, 0.38);
  color: #0B6A3A;
  border: 1px solid rgba(46, 204, 113, 0.75);
}

QLabel#StatusChip[state="draft"] {
  background: rgba(108, 117, 125, 0.14);
  color: rgba(8, 44, 63, 0.78);
  border: 1px solid rgba(108, 117, 125, 0.22);
}



/* Diet Plans - left plan list polish (scoped) */
QTableWidget#PlansListTable {
  background: transparent;
  border: none;
  selection-background-color: rgba(127, 127, 127, 0.10);
  selection-color: inherit;
}

QTableWidget#PlansListTable::item {
  padding-left: 8px;
  padding-right: 8px;
}

QTableWidget#PlansListTable::item:hover {
  background: rgba(127, 127, 127, 0.08);
}

QTableWidget#PlansListTable::item:selected {
  background: rgba(127, 127, 127, 0.10);
}


/* Key-Value grid (Client Detail / General) */
QWidget#ClientGeneralPage QLabel[role="kv_label"] {
  color: rgba(12, 42, 51, 0.62);
  font-weight: 650;
}
QWidget#ClientGeneralPage QLabel[role="kv_value"] {
  color: rgba(12, 42, 51, 0.90);
  font-weight: 600;
}

/* Make general page feel layered (reduce "silik" look) */
QWidget#ClientGeneralPage {
  background: transparent;
}


/* Measurements - table card header (left) */
QWidget#MeasurementsScreen QFrame#TableCard {
  background: #F7FBFD;
  border: 1px solid rgba(12, 42, 51, 0.10);
  border-radius: 14px;
}

QWidget#MeasurementsScreen QLabel#TableTitle {
  font-weight: 900;
  font-size: 15px;
  color: rgba(9, 29, 36, 0.96);
}

/* Measurements table: reduce "excel" feel */
QWidget#MeasurementsScreen QTableWidget#MeasurementsTable {
  background: #FFFFFF;
  border: 1px solid rgba(12, 42, 51, 0.12);
  border-radius: 12px;
  gridline-color: rgba(12, 42, 51, 0.0);
}

QWidget#MeasurementsScreen QTableWidget#MeasurementsTable::item {
  padding: 10px 10px;
  font-weight: 750;
  font-size: 14px;
  color: rgba(8, 28, 35, 0.96);
}

QWidget#MeasurementsScreen QTableWidget#MeasurementsTable::item:alternate {
  background: rgba(12, 42, 51, 0.030);
}

QWidget#MeasurementsScreen QTableWidget#MeasurementsTable::item:hover {
  background: rgba(102,179,90,0.14);
}

QWidget#MeasurementsScreen QTableWidget#MeasurementsTable::item:selected {
  background: rgba(102,179,90,0.30);
  color: rgba(8, 28, 35, 0.98);
}

QWidget#MeasurementsScreen QHeaderView::section {
  background: rgba(12, 42, 51, 0.06);
  border: none;
  border-bottom: 1px solid rgba(12, 42, 51, 0.12);
  font-weight: 900;
  font-size: 14px;
  padding: 12px 12px;
}

'@
Set-Content -Path '%TARGET_THEME_DIR%\style.qss' -Value $style -Encoding UTF8

if ($LASTEXITCODE -ne 0) { exit 1 }
"^

if %ERRORLEVEL% NEQ 0 (
  echo Failed to write update files.
  exit /b 1
)

echo Settings layout updates applied successfully.
exit /b 0
