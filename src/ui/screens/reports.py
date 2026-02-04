from __future__ import annotations

from pathlib import Path

from src.services.settings_service import SettingsService
from datetime import datetime
import re

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QFileDialog, QMessageBox, QComboBox, QListWidget, QListWidgetItem, QAbstractItemView
)

from src.reports.pdf_report import build_client_report_pdf
from src.app.utils.dates import format_tr_date
from src.services.backup import resolve_backup_root


class ReportsScreen(QWidget):
    """
    Sprint 3.7: Danışan raporu (PDF) ekranı.
    Profesyonel ve kurumsal görünüm hedeflenir.
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
        lay.setSpacing(12)

        title = QLabel("Raporlar")
        title.setObjectName("Title")
        lay.addWidget(title)

        subtitle = QLabel("Danışana verilebilecek profesyonel PDF raporu oluştur.")
        subtitle.setObjectName("SubTitle")
        lay.addWidget(subtitle)

        # Options row
        opt = QFrame()
        opt.setObjectName("InnerCard")
        opt_l = QHBoxLayout(opt)
        opt_l.setContentsMargins(14, 14, 14, 14)
        opt_l.setSpacing(12)

        lbl1 = QLabel("Aktivite")
        lbl1.setObjectName("FieldLabel")
        opt_l.addWidget(lbl1)

        self.cmb_activity = QComboBox()
        self.cmb_activity.setObjectName("Input")
        self.cmb_activity.addItem("Sedanter (1.20)", 1.20)
        self.cmb_activity.addItem("Hafif Aktif (1.375)", 1.375)
        self.cmb_activity.addItem("Orta Aktif (1.55)", 1.55)
        self.cmb_activity.addItem("Çok Aktif (1.725)", 1.725)
        self.cmb_activity.addItem("Ekstra Aktif (1.90)", 1.90)
        opt_l.addWidget(self.cmb_activity, 1)

        lbl2 = QLabel("Hedef")
        lbl2.setObjectName("FieldLabel")
        opt_l.addWidget(lbl2)

        self.cmb_goal = QComboBox()
        self.cmb_goal.setObjectName("Input")
        self.cmb_goal.addItem("Kilo Ver (-500 kcal)", -500)
        self.cmb_goal.addItem("Koruma (0 kcal)", 0)
        self.cmb_goal.addItem("Kilo Al (+300 kcal)", 300)
        opt_l.addWidget(self.cmb_goal, 1)

        lay.addWidget(opt)

        # Button row
        row = QHBoxLayout()
        row.addStretch(1)

        # Tema: style.qss içinde buton stilleri objectName ile uygulanır.
        # Bu yüzden PrimaryBtn kullanıyoruz (QPushButton#PrimaryBtn).
        self.btn_pdf = QPushButton("PDF Rapor Oluştur", objectName="PrimaryBtn")
        self.btn_pdf.clicked.connect(self._export_pdf)
        row.addWidget(self.btn_pdf)

        lay.addLayout(row)

        hint = QLabel("Not: PDF çıktısı Arial font ile üretilir. Windows'ta Arial otomatik bulunur.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)


        # Hızlı görüntüleme / yeniden çıktı: son raporlar
        lbl_arc = QLabel("Son Raporlar")
        lbl_arc.setObjectName("SubTitle")
        lay.addWidget(lbl_arc)

        self.lst_archive = QListWidget()
        self.lst_archive.setSelectionMode(QAbstractItemView.SingleSelection)
        self.lst_archive.itemDoubleClicked.connect(self._open_selected_report)
        lay.addWidget(self.lst_archive, 1)

        arc_row = QHBoxLayout()
        self.btn_open = QPushButton("Aç")
        self.btn_open.clicked.connect(self._open_selected_report)
        self.btn_show = QPushButton("Klasörde Göster")
        self.btn_show.clicked.connect(self._reveal_selected_report)
        self.btn_refresh = QPushButton("Yenile")
        self.btn_refresh.clicked.connect(self._refresh_archive)
        arc_row.addWidget(self.btn_open)
        arc_row.addWidget(self.btn_show)
        arc_row.addStretch(1)
        arc_row.addWidget(self.btn_refresh)
        lay.addLayout(arc_row)

        # Klinik özet arşivi (Sprint 4.4)
        lbl_cl = QLabel("Klinik Özetler")
        lbl_cl.setObjectName("SubTitle")
        lay.addWidget(lbl_cl)

        self.lst_clinical = QListWidget()
        self.lst_clinical.setSelectionMode(QAbstractItemView.SingleSelection)
        self.lst_clinical.itemDoubleClicked.connect(self._open_selected_clinical_report)
        lay.addWidget(self.lst_clinical, 1)

        cl_row = QHBoxLayout()
        self.btn_cl_open = QPushButton("Aç")
        self.btn_cl_open.clicked.connect(self._open_selected_clinical_report)
        self.btn_cl_show = QPushButton("Klasörde Göster")
        self.btn_cl_show.clicked.connect(self._reveal_selected_clinical_report)
        self.btn_cl_refresh = QPushButton("Yenile")
        self.btn_cl_refresh.clicked.connect(self._refresh_clinical_archive)
        cl_row.addWidget(self.btn_cl_open)
        cl_row.addWidget(self.btn_cl_show)
        cl_row.addStretch(1)
        cl_row.addWidget(self.btn_cl_refresh)
        lay.addLayout(cl_row)

        self._refresh_archive()
        self._refresh_clinical_archive()

        lay.addStretch(1)

    
    def _client_full_name(self) -> str:
        cur = self.conn.cursor()
        row = cur.execute("SELECT full_name FROM clients WHERE id = ?", (self.client_id,)).fetchone()
        return (row[0] if row else "Danisan").strip()

    def _slugify(self, text: str) -> str:
        # Dosya adı için güvenli hale getir (TR harfleri sadeleştir)
        mapping = str.maketrans({
            "ç":"c","Ç":"C","ğ":"g","Ğ":"G","ı":"i","İ":"I","ö":"o","Ö":"O","ş":"s","Ş":"S","ü":"u","Ü":"U",
        })
        t = text.translate(mapping)
        t = "".join(ch if ch.isalnum() or ch in [" ", "-", "_"] else " " for ch in t)
        t = re.sub(r"\s+", " ", t).strip()
        t = t.replace(" ", "_")
        return t or "Danisan"

    def _next_report_seq(self, yyyymmdd: str) -> int:
        key = f"report_seq_{yyyymmdd}"
        cur = self.conn.cursor()
        row = cur.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
        n = int(row[0]) if row else 0
        n += 1
        if row:
            cur.execute("UPDATE app_meta SET value = ? WHERE key = ?", (str(n), key))
        else:
            cur.execute("INSERT INTO app_meta(key, value) VALUES(?, ?)", (key, str(n)))
        self.conn.commit()
        return n

    def _archive_dir(self) -> Path:
        root = resolve_backup_root()
        d = root / "reports" / str(self.client_id)
        d.mkdir(parents=True, exist_ok=True)
        return d


    def _clinical_dir(self) -> Path:
        root = resolve_backup_root()
        d = root / "reports" / "clinical" / str(self.client_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _refresh_clinical_archive(self):
        if not hasattr(self, 'lst_clinical'):
            return
        self.lst_clinical.clear()
        d = self._clinical_dir()
        items = sorted(d.glob('*.pdf'), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in items[:50]:
            it = QListWidgetItem(p.name)
            it.setData(Qt.UserRole, str(p))
            self.lst_clinical.addItem(it)

    def _selected_clinical_report_path(self) -> Path | None:
        it = getattr(self, 'lst_clinical', None).currentItem() if hasattr(self, 'lst_clinical') else None
        if not it:
            return None
        p = it.data(Qt.UserRole)
        if not p:
            return None
        try:
            path = Path(str(p))
            return path if path.exists() else None
        except Exception:
            return None

    def _open_selected_clinical_report(self, *args):
        path = self._selected_clinical_report_path()
        if not path:
            QMessageBox.information(self, 'Klinik Özet', 'Lütfen listeden bir klinik özet seçin.')
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _reveal_selected_clinical_report(self):
        path = self._selected_clinical_report_path()
        if not path:
            QMessageBox.information(self, 'Klinik Özet', 'Lütfen listeden bir klinik özet seçin.')
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
    def _refresh_archive(self):
        self.lst_archive.clear()
        d = self._archive_dir()
        items = sorted(d.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in items[:50]:
            it = QListWidgetItem(p.name)
            it.setData(Qt.UserRole, str(p))
            self.lst_archive.addItem(it)


    def _selected_report_path(self) -> Path | None:
        it = self.lst_archive.currentItem()
        if not it:
            return None
        p = it.data(Qt.UserRole)
        if not p:
            return None
        try:
            path = Path(str(p))
            return path if path.exists() else None
        except Exception:
            return None

    def _open_selected_report(self, *args):
        path = self._selected_report_path()
        if not path:
            QMessageBox.information(self, "Rapor", "Lütfen listeden bir rapor seçin.")
            return
        # Varsayılan PDF görüntüleyici ile aç
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _reveal_selected_report(self, *args):
        path = self._selected_report_path()
        if not path:
            QMessageBox.information(self, "Rapor", "Lütfen listeden bir rapor seçin.")
            return
        # Windows: dosyayı klasörde seçili göster
        try:
            import subprocess
            subprocess.run(["explorer", "/select,", str(path)], check=False)
        except Exception:
            # En kötü ihtimal: klasörü aç
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    def _default_filename(self) -> str:
        ymd = datetime.now().date().strftime("%Y%m%d")
        seq = self._next_report_seq(ymd)
        name = self._slugify(self._client_full_name())
        return f"{name}_{ymd}_{seq:03d}_NutriNexus_Rapor.pdf"
    def _get_logo_path(self) -> Path:
        """Return Path to clinic logo if configured, otherwise NutriNexus logo."""
        svc = SettingsService(self.conn)
        rel = (svc.get_value("clinic_logo_path", "") or "").strip()

        def _resolve(rel_or_abs: str) -> Path:
            p = Path(rel_or_abs)
            if p.is_absolute():
                return p
            base = Path(__file__).resolve().parents[2]  # src
            return (base / rel_or_abs).resolve()

        if rel:
            p = _resolve(rel)
            if p.exists():
                return p

        # fallback
        base = Path(__file__).resolve().parents[2]
        fallback = (base / "assets" / "nutrinexus_logo.png").resolve()
        return fallback


    def _export_pdf(self):
        try:
            default = self._default_filename()
            path, _ = QFileDialog.getSaveFileName(self, "PDF Kaydet", default, "PDF Files (*.pdf)")
            if not path:
                return

            activity = float(self.cmb_activity.currentData())
            adjust = int(self.cmb_goal.currentData())

            logo_path = self._get_logo_path()
            out = build_client_report_pdf(
                conn=self.conn,
                client_id=self.client_id,
                out_path=path,
                logo_path=str(logo_path) if logo_path.exists() else None,
                activity_factor=activity,
                goal_adjust_kcal=adjust,
            )

            # Arşive kopyala (hızlı görüntüleme için)
            try:
                out_p = Path(out)
                arc_dir = self._archive_dir()
                arc_p = arc_dir / out_p.name
                if out_p.resolve() != arc_p.resolve():
                    import shutil
                    shutil.copy2(out_p, arc_p)
                self._refresh_archive()
            except Exception:
                # Arşivleme kritik değil; sessiz geç
                pass

            QMessageBox.information(self, "Rapor Hazır", f"PDF rapor oluşturuldu:\n{out}")
        except Exception as e:
            self.log.exception("PDF raporu oluşturulamadı: %s", e)
            QMessageBox.critical(self, "Hata", f"PDF raporu oluşturulamadı.\n\nDetay: {e}")