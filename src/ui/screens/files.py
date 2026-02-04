from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import os
import uuid
from datetime import datetime

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QMessageBox, QFileDialog,
    QDialog, QLineEdit, QTextEdit, QComboBox, QFormLayout
)

from src.services.files_service import ClientFilesService

CATEGORIES = ["Tahlil", "Diyet", "Fotoğraf", "Rapor", "Diğer"]

def _now_date_folder() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def _safe_name(name: str) -> str:
    # Windows-safe filename
    bad = '<>:/\\|?*"'
    out = "".join("_" if c in bad else c for c in (name or ""))
    out = out.strip().strip(".")
    return out or "dosya"

class AddClientFileDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dosya Ekle")
        self.setModal(True)
        self.resize(520, 320)

        self._picked_path: Path | None = None

        lay = QVBoxLayout(self)

        form = QFormLayout()
        self.edt_title = QLineEdit()
        self.cmb_cat = QComboBox()
        self.cmb_cat.addItems(CATEGORIES)
        self.edt_note = QTextEdit()
        self.edt_note.setFixedHeight(80)

        form.addRow("Başlık (opsiyonel)", self.edt_title)
        form.addRow("Kategori", self.cmb_cat)
        form.addRow("Not", self.edt_note)
        lay.addLayout(form)

        pick_row = QHBoxLayout()
        self.lbl_file = QLabel("Dosya seçilmedi")
        self.lbl_file.setObjectName("Muted")
        btn_pick = QPushButton("Dosya Seç")
        btn_pick.clicked.connect(self._pick_file)
        pick_row.addWidget(self.lbl_file, 1)
        pick_row.addWidget(btn_pick)
        lay.addLayout(pick_row)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QPushButton("Vazgeç")
        self.btn_cancel.setObjectName("SecondaryBtn")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QPushButton("Ekle")
        self.btn_ok.setObjectName("PrimaryBtn")
        self.btn_ok.clicked.connect(self._validate_ok)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        lay.addLayout(btns)

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Dosya Seç", "", "Tüm Dosyalar (*.*)")
        if path:
            self._picked_path = Path(path)
            self.lbl_file.setText(self._picked_path.name)

    def _validate_ok(self):
        if not self._picked_path or not self._picked_path.exists():
            QMessageBox.warning(self, "Eksik", "Lütfen bir dosya seçin.")
            return
        self.accept()

    def result_data(self) -> dict:
        return {
            "title": self.edt_title.text().strip(),
            "category": self.cmb_cat.currentText(),
            "note": self.edt_note.toPlainText().strip(),
            "picked_path": str(self._picked_path) if self._picked_path else "",
        }

class ClientFilesScreen(QWidget):
    def __init__(self, conn, backup_root: Path, client_id: str, log):
        super().__init__()
        self.conn = conn
        self.backup_root = Path(backup_root)
        self.client_id = client_id
        self.log = log
        self.svc = ClientFilesService(conn)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)

        card = QFrame()
        card.setObjectName("Card")
        lay = QVBoxLayout(card)

        header = QHBoxLayout()
        header.addWidget(QLabel("Dosyalar", objectName="CardTitle"))
        header.addStretch(1)

        self.btn_add = QPushButton("Dosya Ekle")
        self.btn_add.setObjectName("PrimaryBtn")
        self.btn_add.clicked.connect(self._add_file)
        header.addWidget(self.btn_add)

        self.btn_refresh = QPushButton("Yenile")
        self.btn_refresh.setObjectName("SecondaryBtn")
        self.btn_refresh.clicked.connect(self.refresh)
        header.addWidget(self.btn_refresh)

        lay.addLayout(header)

        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(["Tarih", "Kategori", "Başlık", "Dosya", "Not"])
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.itemDoubleClicked.connect(self._open_selected)
        lay.addWidget(self.tbl)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.btn_open = QPushButton("Aç")
        self.btn_open.setObjectName("SecondaryBtn")
        self.btn_open.clicked.connect(self._open_selected)
        actions.addWidget(self.btn_open)

        self.btn_reveal = QPushButton("Klasörde Göster")
        self.btn_reveal.setObjectName("SecondaryBtn")
        self.btn_reveal.clicked.connect(self._reveal_selected)
        actions.addWidget(self.btn_reveal)

        self.btn_del = QPushButton("Sil")
        self.btn_del.setObjectName("DangerBtn")
        self.btn_del.clicked.connect(self._delete_selected)
        actions.addWidget(self.btn_del)

        lay.addLayout(actions)

        root.addWidget(card)

        self.refresh()

    def showEvent(self, e):
        super().showEvent(e)
        # sekmeye geçince otomatik güncelle
        self.refresh()

    def _selected_file_id(self) -> str | None:
        r = self.tbl.currentRow()
        if r < 0:
            return None
        item = self.tbl.item(r, 0)
        return item.data(Qt.UserRole) if item else None

    def refresh(self):
        files = self.svc.list_files(self.client_id)
        self.tbl.setRowCount(0)
        for f in files:
            row = self.tbl.rowCount()
            self.tbl.insertRow(row)

            it0 = QTableWidgetItem(f.created_at)
            it0.setData(Qt.UserRole, f.id)
            self.tbl.setItem(row, 0, it0)
            self.tbl.setItem(row, 1, QTableWidgetItem(f.category))
            self.tbl.setItem(row, 2, QTableWidgetItem(f.title or ""))
            self.tbl.setItem(row, 3, QTableWidgetItem(Path(f.orig_name).name))
            self.tbl.setItem(row, 4, QTableWidgetItem((f.note or "")[:120]))

        self.tbl.resizeColumnsToContents()

    def _add_file(self):
        dlg = AddClientFileDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.result_data()
        src_path = Path(data["picked_path"])
        category = data["category"]
        title = data.get("title", "")
        note = data.get("note", "")

        # hedef klasör
        dest_dir = self.backup_root / "clients" / str(self.client_id) / "files" / _now_date_folder()
        dest_dir.mkdir(parents=True, exist_ok=True)

        unique = str(uuid.uuid4())[:8]
        safe_orig = _safe_name(src_path.name)
        dest_name = f"{unique}_{safe_orig}"
        dest_path = dest_dir / dest_name

        try:
            shutil.copy2(src_path, dest_path)
        except Exception as ex:
            QMessageBox.critical(self, "Hata", f"Dosya kopyalanamadı: {ex}")
            return

        try:
            self.svc.add_file(
                client_id=str(self.client_id),
                category=category,
                title=title,
                orig_name=src_path.name,
                stored_path=str(dest_path),
                note=note,
            )
        except Exception as ex:
            # kopyalanan dosyayı geri al
            try:
                dest_path.unlink(missing_ok=True)
            except Exception:
                pass
            QMessageBox.critical(self, "Hata", f"Kayıt eklenemedi: {ex}")
            return

        self.refresh()
        QMessageBox.information(self, "Tamam", "Dosya eklendi.")

    def _open_selected(self, *args):
        fid = self._selected_file_id()
        if not fid:
            return
        # row data -> stored path
        row = self.tbl.currentRow()
        # stored path is not in table; fetch from db
        cur = self.conn.execute("SELECT stored_path FROM client_files WHERE id=?", (fid,))
        r = cur.fetchone()
        if not r:
            QMessageBox.warning(self, "Bulunamadı", "Kayıt bulunamadı.")
            return
        p = Path(r[0])
        if not p.exists():
            QMessageBox.warning(self, "Bulunamadı", f"Dosya bulunamadı: {p}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    def _reveal_selected(self):
        fid = self._selected_file_id()
        if not fid:
            return
        cur = self.conn.execute("SELECT stored_path FROM client_files WHERE id=?", (fid,))
        r = cur.fetchone()
        if not r:
            return
        p = Path(r[0])
        if p.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent)))

    def _delete_selected(self):
        fid = self._selected_file_id()
        if not fid:
            return
        if QMessageBox.question(self, "Sil", "Seçili dosya kaydı silinsin mi?") != QMessageBox.Yes:
            return
        # fetch path
        cur = self.conn.execute("SELECT stored_path FROM client_files WHERE id=?", (fid,))
        r = cur.fetchone()
        stored = Path(r[0]) if r and r[0] else None

        try:
            self.svc.soft_delete(fid)
        except Exception as ex:
            QMessageBox.critical(self, "Hata", f"Kayıt silinemedi: {ex}")
            return

        # dosyayı da silmeye çalış (opsiyonel)
        if stored and stored.exists():
            try:
                stored.unlink()
            except Exception:
                # fiziksel silme başarısızsa sorun değil
                pass

        self.refresh()
        QMessageBox.information(self, "Tamam", "Dosya silindi.")
