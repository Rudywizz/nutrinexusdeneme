from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem, QSplitter,
    QComboBox, QTabWidget, QListWidget, QListWidgetItem, QCheckBox
)

from src.services.labs_importer import parse_enabiz_pdf
from src.services.labs_service import LabsService
from src.services.clinical_intelligence import ClinicalIntelligence, Insight


_STATUS_LABEL = {
    "high": "Yüksek",
    "low": "Düşük",
    "borderline": "Sınırda",
    "normal": "Normal",
    "unknown": "Bilinmiyor",
}

_STATUS_COLOR = {
    "high": QColor("#d9534f"),
    "low": QColor("#0275d8"),
    "borderline": QColor("#f0ad4e"),
    "normal": QColor("#2f6f4e"),
    "unknown": QColor("#6c757d"),
}

_STATUS_BG = {
    "high": QColor("#FDECEC"),
    "low": QColor("#EAF3FF"),
    "borderline": QColor("#FFF4E5"),
    "normal": QColor("#F4FAF6"),
    "unknown": QColor("#F3F4F6"),
}
_STATUS_RANK = {
    "normal": 0,
    "borderline": 1,
    "low": 2,
    "high": 2,
    "unknown": 99,
}


COL_TEST = 0
COL_RESULT = 1
COL_PREV = 2
COL_DELTA = 3
COL_UNIT = 4
COL_REF = 5
COL_STATUS = 6
COL_TAKEN = 7

# Karşılaştırmada çok küçük değişimleri filtrelemek için eşikler
MIN_ABS_DELTA = 0.01  # mutlak fark
MIN_REL_DELTA = 0.01  # göreli fark (1%)


def _norm_key(name: str) -> str:
    """Test adı eşleştirme anahtarı.
    Amaç: aynı test farklı yazılsa bile (noktalama, Türkçe karakter, çoklu boşluk, kısaltma)
    karşılaştırmada yakalayabilmek.
    """
    s = (name or "").strip().casefold()
    # Türkçe karakterleri sadeleştir (casefold bazılarını çözer ama garanti olsun)
    tr_map = str.maketrans({"ı":"i","İ":"i","ş":"s","Ş":"s","ğ":"g","Ğ":"g","ü":"u","Ü":"u","ö":"o","Ö":"o","ç":"c","Ç":"c"})
    s = s.translate(tr_map)
    # Noktalama/özel karakterleri boşluğa çevir
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Çok görülen eş anlamlı/kısaltma örnekleri (genişletilebilir)
    synonyms = {
        "c reaktif protein": "crp",
        "c reaktif protein crp": "crp",
        "crp turbidimetrik": "crp",
        "glukoz aclik kan sekeri": "glukoz aclik",
        "aclik kan sekeri": "glukoz aclik",
        "homa ir": "homa ir",
        "vitamin d": "25 oh vitamin d",
        "25 oh vitamin d": "25 oh vitamin d",
        "tsh": "tsh",
    }
    return synonyms.get(s, s)

def _fmt_delta(x: Optional[float]) -> str:
    if x is None:
        return ""
    # + işaretini özellikle göster
    if abs(x) < 1e-12:
        return "0"
    return f"{x:+.2f}"


class LabsScreen(QWidget):
    labs_changed = Signal()  # PDF import sonrası diğer ekranları tetiklemek için
    """Kan tahlili: PDF içe aktar, referansa göre renklendir, kritikler ve (opsiyonel) karşılaştırma."""

    def __init__(self, conn, client_id: str, log):
        super().__init__()
        self.conn = conn
        self.client_id = client_id
        self.log = log
        self.svc = LabsService(conn)
        self.engine = ClinicalIntelligence(conn)

        self._row_index_by_key: Dict[str, int] = {}

        root = QVBoxLayout(self)

        # Header card
        header = QFrame(objectName="Card")
        hv = QVBoxLayout(header)
        hv.addWidget(QLabel("Kan Tahlili", objectName="CardTitle"))

        desc = QLabel("PDF yükleyerek (e-Nabız vb.) ölçülen değerleri otomatik ayıkla ve referans aralığına göre renklendir.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color:#6B7B88;")
        hv.addWidget(desc)

        actions = QHBoxLayout()
        actions.addWidget(QLabel("Son Yüklemeler:"))
        self.cmb_imports = QComboBox()
        self.cmb_imports.setMinimumWidth(320)

        self.chk_compare = QCheckBox("Önceki tahlille karşılaştır")
        self.chk_compare.setObjectName("CompareCheck")
        self.chk_compare.setToolTip("Seçili tahlili, önceki bir tahlille karşılaştır (Önceki / Δ / Değişimler).")

        self.cmb_compare = QComboBox()
        self.cmb_compare.setMinimumWidth(300)
        self.cmb_compare.setEnabled(False)

        self.btn_refresh = QPushButton("Yenile", objectName="SecondaryBtn")
        self.btn_upload = QPushButton("PDF Yükle", objectName="PrimaryBtn")

        actions.addWidget(self.cmb_imports)
        actions.addSpacing(8)
        actions.addWidget(self.chk_compare)
        actions.addWidget(self.cmb_compare)
        actions.addWidget(self.btn_refresh)
        actions.addStretch(1)
        actions.addWidget(self.btn_upload)

        hv.addLayout(actions)
        root.addWidget(header)

        # Main area split
        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        # Left: table
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)

        self.tbl = QTableWidget(0, 8)
        self.tbl.setHorizontalHeaderLabels(["Tetkik", "Sonuç", "Önceki", "Δ", "Birim", "Referans", "Durum", "Tarih/Saat"])
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        lv.addWidget(self.tbl)
        splitter.addWidget(left)

        # Right: tabs (Kritikler / Değişimler)
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)

        self.right_tabs = QTabWidget()

        # Kritikler tab
        crit = QWidget()
        cv = QVBoxLayout(crit)
        cv.setContentsMargins(0, 0, 0, 0)

        cv.addWidget(QLabel("Kritikler", objectName="CardTitle"))
        self.tabs_crit = QTabWidget()
        self.lst_high = QListWidget()
        self.lst_low = QListWidget()
        self.lst_border = QListWidget()
        for w in (self.lst_high, self.lst_low, self.lst_border):
            w.itemClicked.connect(self._jump_to_row)

        self.tabs_crit.addTab(self.lst_high, "Yüksek (0)")
        self.tabs_crit.addTab(self.lst_low, "Düşük (0)")
        self.tabs_crit.addTab(self.lst_border, "Sınırda (0)")
        cv.addWidget(self.tabs_crit)

        hint = QLabel("İpucu: Kritikteki bir değere tıklayınca soldaki tabloda ilgili satıra gider.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#6B7B88; font-size:11px;")
        cv.addWidget(hint)
        cv.addStretch(1)

        # Değişimler tab
        changes = QWidget()
        chv = QVBoxLayout(changes)
        chv.setContentsMargins(0, 0, 0, 0)

        chv.addWidget(QLabel("Değişimler", objectName="CardTitle"))
        self.tabs_changes = QTabWidget()

        self.lst_norm = QListWidget()
        self.lst_worse = QListWidget()
        self.lst_up = QListWidget()
        self.lst_down = QListWidget()
        for w in (self.lst_norm, self.lst_worse, self.lst_up, self.lst_down):
            w.itemClicked.connect(self._jump_to_row)

        self.tabs_changes.addTab(self.lst_norm, "Normalleşen (0)")
        self.tabs_changes.addTab(self.lst_worse, "Kötüleşen (0)")
        self.tabs_changes.addTab(self.lst_up, "Artan (0)")
        self.tabs_changes.addTab(self.lst_down, "Azalan (0)")
        chv.addWidget(self.tabs_changes)

        hint2 = QLabel("Not: Değişimler yalnızca 'Karşılaştır' açıkken ve önceki tahlil seçiliyken hesaplanır.")
        hint2.setWordWrap(True)
        hint2.setStyleSheet("color:#6B7B88; font-size:11px;")
        chv.addWidget(hint2)
        chv.addStretch(1)


        # Yorum Önerileri tab (Sprint 4.0)
        sugg = QWidget()
        sv = QVBoxLayout(sugg)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.addWidget(QLabel("Yorum Önerileri", objectName="CardTitle"))
        self.lst_suggestions = QListWidget()
        self.lst_suggestions.setObjectName("IntelList")
        sv.addWidget(self.lst_suggestions)
        hint3 = QLabel("İpucu: Öneriler seçili tahlile göre otomatik üretilir. Klinik karar yerine geçmez.")
        hint3.setWordWrap(True)
        hint3.setStyleSheet("color:#6B7B88; font-size:11px;")
        sv.addWidget(hint3)
        sv.addStretch(1)

        self.right_tabs.addTab(crit, "Kritikler")
        self.right_tabs.addTab(changes, "Değişimler")
        self.right_tabs.addTab(sugg, "Yorum Önerileri")
        rv.addWidget(self.right_tabs)

        splitter.addWidget(right)
        splitter.setSizes([800, 380])

        # signals
        self.btn_refresh.clicked.connect(lambda: self._refresh_imports())
        self.btn_upload.clicked.connect(self._load_pdf)
        self.cmb_imports.currentIndexChanged.connect(self._load_selected_import)
        self.chk_compare.toggled.connect(self._on_toggle_compare)
        self.cmb_compare.currentIndexChanged.connect(self._on_change_compare)

        self._refresh_imports(initial=True)

    def _refresh_imports(self, initial: bool = False):
        self.cmb_imports.blockSignals(True)
        self.cmb_imports.clear()

        imports = self.svc.list_imports(self.client_id, limit=50)
        for imp in imports:
            label = f"{imp['imported_at']} • {imp['source_filename']}"
            self.cmb_imports.addItem(label, imp["id"])

        self.cmb_imports.blockSignals(False)

        if initial:
            # varsayılan: en son yükleme
            if self.cmb_imports.count() > 0:
                self.cmb_imports.setCurrentIndex(0)

        self._refresh_compare_choices()
        self._load_selected_import()

    def _refresh_compare_choices(self):
        """Karşılaştırma listesi: mevcut seçilinin dışındaki importlar."""
        current_id = self.cmb_imports.currentData()
        prev_selected = self.cmb_compare.currentData()

        self.cmb_compare.blockSignals(True)
        self.cmb_compare.clear()

        imports = self.svc.list_imports(self.client_id, limit=50)
        for imp in imports:
            if current_id and imp["id"] == current_id:
                continue
            label = f"{imp['imported_at']} • {imp['source_filename']}"
            self.cmb_compare.addItem(label, imp["id"])

        # mümkünse önceki seçimi koru
        if prev_selected:
            idx = self.cmb_compare.findData(prev_selected)
            if idx >= 0:
                self.cmb_compare.setCurrentIndex(idx)

        self.cmb_compare.blockSignals(False)

        # compare açık ama seçenek yoksa kapat
        if self.chk_compare.isChecked() and self.cmb_compare.count() == 0:
            self.chk_compare.blockSignals(True)
            self.chk_compare.setChecked(False)
            self.chk_compare.blockSignals(False)
            self.cmb_compare.setEnabled(False)

    def _on_toggle_compare(self, checked: bool):
        self.cmb_compare.setEnabled(bool(checked))
        self._refresh_compare_choices()
        self._load_selected_import()

    def _on_change_compare(self, _idx: int):
        if not self.chk_compare.isChecked():
            return
        self._load_selected_import()

    def _load_selected_import(self):
        import_id = self.cmb_imports.currentData()
        if not import_id:
            self._clear_view()
            return

        # current rows
        rows = self.svc.list_results_for_import(import_id)
        # Sprint 4.0: yorum önerileri
        try:
            self._update_suggestions(rows)
        except Exception:
            pass

        # compare rows (optional)
        base_rows = None
        base_id = None
        if self.chk_compare.isChecked():
            base_id = self.cmb_compare.currentData()
            if base_id:
                base_rows = self.svc.list_results_for_import(base_id)

        self._render_rows(rows, base_rows=base_rows)

        # current import değişince compare seçeneklerini güncelle
        self._refresh_compare_choices()

    def _clear_view(self):
        self._row_index_by_key = {}
        self.tbl.setRowCount(0)
        for lst in (self.lst_high, self.lst_low, self.lst_border, self.lst_norm, self.lst_worse, self.lst_up, self.lst_down):
            lst.clear()

        self.tabs_crit.setTabText(0, "Yüksek (0)")
        self.tabs_crit.setTabText(1, "Düşük (0)")
        self.tabs_crit.setTabText(2, "Sınırda (0)")

        self.tabs_changes.setTabText(0, "Normalleşen (0)")
        self.tabs_changes.setTabText(1, "Kötüleşen (0)")
        self.tabs_changes.setTabText(2, "Artan (0)")
        self.tabs_changes.setTabText(3, "Azalan (0)")

    def _load_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "PDF Seç", "", "PDF Files (*.pdf)")
        if not path:
            return

        try:
            parsed = parse_enabiz_pdf(path)
            if not parsed:
                QMessageBox.warning(self, "Uyarı", "PDF'den sonuç bulunamadı.")
                return

            import_id = self.svc.create_import(self.client_id, path)
            self.svc.save_rows(import_id, self.client_id, parsed)

            self._refresh_imports()
            # select newly created import
            idx = self.cmb_imports.findData(import_id)
            if idx >= 0:
                self.cmb_imports.setCurrentIndex(idx)
            self._load_selected_import()
            try:
                self.labs_changed.emit()
            except Exception:
                pass

            QMessageBox.information(self, "Başarılı", f"{len(parsed)} satır tahlil sonucu eklendi.")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"PDF raporu içe aktarılamadı.\n\nDetay: {e}")

    def _render_rows(self, rows, base_rows=None):
        self._clear_view()
        self.tbl.setRowCount(len(rows))

        compare_on = bool(self.chk_compare.isChecked() and base_rows)
        # show/hide columns
        self.tbl.setColumnHidden(COL_PREV, not compare_on)
        self.tbl.setColumnHidden(COL_DELTA, not compare_on)

        base_by_key: Dict[str, object] = {}
        if compare_on:
            for br in base_rows:
                base_by_key[_norm_key(br["test_name"])] = br

        high_items: List[Tuple[str, int]] = []
        low_items: List[Tuple[str, int]] = []
        border_items: List[Tuple[str, int]] = []

        # changes
        norm_items: List[Tuple[str, int]] = []
        worse_items: List[Tuple[str, int]] = []
        up_items_tmp: List[Tuple[float, str, int]] = []
        down_items_tmp: List[Tuple[float, str, int]] = []

        for r_i, r in enumerate(rows):
            test = r["test_name"]
            result = r["result_text"]
            unit = r["unit"]
            ref = r["ref_text"]
            status = r["status"]
            taken_at = r["taken_at"]

            prev_text = ""
            delta_text = ""
            if compare_on:
                br = base_by_key.get(_norm_key(test))
                if br:
                    prev_text = str(br["result_text"])
                    # numeric delta
                    cur_v = r["result_value"]
                    prev_v = br["result_value"]
                    try:
                        cur_f = float(cur_v) if cur_v is not None else None
                    except Exception:
                        cur_f = None
                    try:
                        prev_f = float(prev_v) if prev_v is not None else None
                    except Exception:
                        prev_f = None
                    if cur_f is not None and prev_f is not None:
                        d = cur_f - prev_f
                        delta_text = _fmt_delta(d)

                        # up/down lists (küçük dalgalanmaları filtrele)
                        thr = max(MIN_ABS_DELTA, (abs(prev_f) * MIN_REL_DELTA) if prev_f is not None else MIN_ABS_DELTA)
                        if abs(d) >= thr:
                            label_ud = f"{test} • {prev_f:g} → {cur_f:g} • Δ {delta_text}"
                            if d > 0:
                                up_items_tmp.append((d, label_ud, r_i))
                            elif d < 0:
                                down_items_tmp.append((d, label_ud, r_i))

                    # normalleşen / kötüleşen (durum şiddetine göre)
                    prev_status = br["status"]
                    prev_rank = _STATUS_RANK.get(prev_status, 99)
                    cur_rank = _STATUS_RANK.get(status, 99)
                    if prev_rank > cur_rank:
                        # iyileşme
                        norm_items.append((f"{test} • {_STATUS_LABEL.get(prev_status, prev_status)} → {_STATUS_LABEL.get(status, status)}", r_i))
                    elif prev_rank < cur_rank:
                        # kötüleşme
                        worse_items.append((f"{test} • {_STATUS_LABEL.get(prev_status, prev_status)} → {_STATUS_LABEL.get(status, status)}", r_i))

            # table items
            self.tbl.setItem(r_i, COL_TEST, QTableWidgetItem(str(test)))
            self.tbl.setItem(r_i, COL_RESULT, QTableWidgetItem(str(result)))
            self.tbl.setItem(r_i, COL_PREV, QTableWidgetItem(prev_text))
            self.tbl.setItem(r_i, COL_DELTA, QTableWidgetItem(delta_text))
            self.tbl.setItem(r_i, COL_UNIT, QTableWidgetItem(str(unit)))
            self.tbl.setItem(r_i, COL_REF, QTableWidgetItem(str(ref)))

            st_item = QTableWidgetItem(_STATUS_LABEL.get(status, status))
            st_item.setForeground(_STATUS_COLOR.get(status, _STATUS_COLOR["unknown"]))
            self.tbl.setItem(r_i, COL_STATUS, st_item)
            self.tbl.setItem(r_i, COL_TAKEN, QTableWidgetItem(str(taken_at)))

            # row background by status
            bg = _STATUS_BG.get(status, _STATUS_BG["unknown"])
            for c in range(self.tbl.columnCount()):
                it = self.tbl.item(r_i, c)
                if it is not None:
                    it.setBackground(bg)

            # right panel groupings
            label = f"{test} • {result} {unit} • {ref}"
            if status == "high":
                high_items.append((label, r_i))
            elif status == "low":
                low_items.append((label, r_i))
            elif status == "borderline":
                border_items.append((label, r_i))

            # row index by key for jump
            self._row_index_by_key[_norm_key(test)] = r_i

        # fill criticals
        self._fill_list(self.lst_high, high_items)
        self._fill_list(self.lst_low, low_items)
        self._fill_list(self.lst_border, border_items)

        self.tabs_crit.setTabText(0, f"Yüksek ({len(high_items)})")
        self.tabs_crit.setTabText(1, f"Düşük ({len(low_items)})")
        self.tabs_crit.setTabText(2, f"Sınırda ({len(border_items)})")

        # fill changes
        if compare_on:
            # sort by magnitude, show top 10
            up_items_tmp.sort(key=lambda x: x[0], reverse=True)
            down_items_tmp.sort(key=lambda x: x[0])  # most negative first

            up_items = [(t, idx) for _d, t, idx in up_items_tmp[:10]]
            down_items = [(t, idx) for _d, t, idx in down_items_tmp[:10]]
        else:
            up_items, down_items = [], []

        self._fill_list(self.lst_norm, norm_items)
        self._fill_list(self.lst_worse, worse_items)
        self._fill_list(self.lst_up, up_items)
        self._fill_list(self.lst_down, down_items)

        self.tabs_changes.setTabText(0, f"Normalleşen ({len(norm_items)})")
        self.tabs_changes.setTabText(1, f"Kötüleşen ({len(worse_items)})")
        self.tabs_changes.setTabText(2, f"Artan ({len(up_items)})")
        self.tabs_changes.setTabText(3, f"Azalan ({len(down_items)})")

        self.tbl.resizeColumnsToContents()

    def _fill_list(self, lst: QListWidget, items: List[Tuple[str, int]]):
        lst.clear()
        for text, row_idx in items:
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, row_idx)
            lst.addItem(it)


    def _update_suggestions(self, rows):
        try:
            insights = self.engine.lab_insights([dict(r) for r in rows])
        except Exception:
            insights = [Insight("info", "Yorum oluşturulamadı.", "Tahlil verileri eksik veya beklenmedik formatta olabilir.")]
        self.lst_suggestions.clear()
        for ins in insights:
            txt = ins.title if not ins.detail else f"{ins.title}  —  {ins.detail}"
            it = QListWidgetItem(txt)
            if ins.severity == "critical":
                it.setForeground(QColor("#C0392B"))
            elif ins.severity == "warn":
                it.setForeground(QColor("#D68910"))
            else:
                it.setForeground(QColor("#2E86C1"))
            it.setToolTip(txt)
            self.lst_suggestions.addItem(it)


    def _jump_to_row(self, item: QListWidgetItem):
        row_idx = item.data(Qt.UserRole)
        if row_idx is None:
            return
        self.tbl.selectRow(int(row_idx))
        self.tbl.scrollToItem(self.tbl.item(int(row_idx), 0), QTableWidget.PositionAtCenter)