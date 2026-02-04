from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFrame,
    QMessageBox,
)

from src.services.foods_catalog_service import FoodsCatalogService


class FoodsScreen(QWidget):
    """Besin Kataloğu (Offline / Türkçe odaklı, Sprint 4.9.4)

    Tasarım kararı:
    - Donma/crash yaşamamak için bu ekranda *thread yok*.
    - Offline hazır katalog küçük bir CSV'dir ve hızlı import edilir.
    - Büyük katalog güncellemeleri CSV ile içe aktarılır.
    """

    def __init__(self, conn, log=None):
        super().__init__()
        self.conn = conn
        self.log = log
        self.svc = FoodsCatalogService(conn)

        # Kurumsal TR çekirdek katalog (assets) otomatik uygulanır (tek kaynak: foods_curated)
        core_csv = Path(__file__).resolve().parents[2] / "assets" / "data" / "kurumsal_tr_cekirdek_catalog.csv"
        self.svc.ensure_tr_core_seeded(core_csv, force=True, log=self.log)

        self._debounce = QTimer(self)
        self._debounce.setInterval(200)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._do_search)

        self._build_ui()
        self.refresh_meta()

        # paging state (prevents "30 item" feeling while keeping UI snappy)
        self._page_size = 200
        self._offset = 0
        self._active_query = ""
        self._loading = False

        self._reset_and_load()

    # ---------------- UI ----------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        title = QLabel("Besin Kataloğu")
        title.setObjectName("h1")
        root.addWidget(title)

        # Meta card
        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(6)

        self.lbl_meta = QLabel("")
        self.lbl_meta.setWordWrap(True)
        cl.addWidget(self.lbl_meta)

        warn = QLabel(
            "<b>Not:</b> Bu ekran offline çalışır. Profesyonel kullanım için kurum onaylı Türkçe CSV kataloğu içe aktarınız."
        )
        warn.setObjectName("muted")
        warn.setWordWrap(True)
        cl.addWidget(warn)

        root.addWidget(card)

        # Actions
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch(1)

        self.edt_search = QLineEdit()
        self.edt_search.setPlaceholderText("Ara… (örn: ayran, elma)")
        self.edt_search.textChanged.connect(lambda _t: self._debounce.start())
        row.addWidget(self.edt_search, 1)

        root.addLayout(row)

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("muted")
        root.addWidget(self.lbl_status)

        # Table
        self.tbl = QTableWidget(0, 2)
        self.tbl.setHorizontalHeaderLabels(["Besin", "kcal/100g"])
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        # infinite scroll
        self.tbl.verticalScrollBar().valueChanged.connect(self._on_scroll)
        root.addWidget(self.tbl, 1)

    # ---------------- data / actions ----------------
    def refresh_meta(self):
        meta = self.svc.get_meta()
        count = self.svc.get_count()
        parts = [f"Aktif ürün: <b>{count}</b>"]
        if meta.source_name:
            parts.append(f"Kaynak: <b>{meta.source_name}</b>")
        if meta.source_version:
            parts.append(f"Sürüm: <b>{meta.source_version}</b>")
        if meta.imported_at:
            parts.append(f"Güncelleme: <b>{meta.imported_at}</b>")
        if meta.file_hash:
            parts.append(f"Hash: <span style='font-family: Consolas, monospace;'>{meta.file_hash[:12]}…</span>")
        self.lbl_meta.setText(" · ".join(parts))

    def _do_search(self):
        # debounce target
        self._reset_and_load()

    def _reset_and_load(self):
        self._active_query = (self.edt_search.text() if self.edt_search else "").strip()
        self._offset = 0
        self.tbl.setRowCount(0)
        self._load_next_page()

    def _load_next_page(self):
        if self._loading:
            return
        self._loading = True
        try:
            rows = self.svc.search_page(self._active_query, limit=self._page_size, offset=self._offset)
            if rows:
                for r in rows:
                    i = self.tbl.rowCount()
                    self.tbl.insertRow(i)
                    self.tbl.setItem(i, 0, QTableWidgetItem(r["name"]))
                    self.tbl.setItem(i, 1, QTableWidgetItem(f"{float(r.get('kcal_per_100g', 0) or 0):.0f}"))
                self._offset += len(rows)

            # status
            total = self.svc.get_count()
            shown = self.tbl.rowCount()
            if self._active_query:
                # we don't compute full "found" count for perf; show what is loaded
                self.lbl_status.setText(f"Gösterilen: <b>{shown}</b> · Filtre: <b>{self._active_query}</b>")
            else:
                self.lbl_status.setText(f"Gösterilen: <b>{shown}</b> / <b>{total}</b>")

            # keep row heights reasonable
            self.tbl.resizeRowsToContents()
        finally:
            self._loading = False

    def _on_scroll(self, _value: int):
        # Load more when user scrolls near the bottom.
        sb = self.tbl.verticalScrollBar()
        if sb.maximum() <= 0:
            return
        # within ~10% of bottom
        if sb.value() >= int(sb.maximum() * 0.90):
            self._load_next_page()
