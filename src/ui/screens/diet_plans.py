from __future__ import annotations

import re
from src.reports.diet_plan_pdf.builder import build_diet_plan_pdf
import html
from datetime import datetime, date
from pathlib import Path
from PySide6.QtCore import Qt, QDate, QRect, QRectF, QPoint, QStringListModel, QObject, QEvent, QUrl, QTimer
from src.features.diet_plan_report import show_diet_plan_preview
from src.services.settings_service import SettingsService
from PySide6.QtGui import QPainter, QAbstractTextDocumentLayout, QColor, QTextCursor, QImage, QBrush, QPixmap, QIcon, QAction, QPalette, QPageSize, QPageLayout, QTextDocument, QFont
from PySide6.QtCore import QMarginsF
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QMessageBox,
    QDialog, QLineEdit, QDateEdit, QTextEdit, QTextBrowser, QFormLayout, QCalendarWidget, QSizePolicy, QHeaderView, QStyledItemDelegate, QTabWidget, QInputDialog, QComboBox, QCompleter, QListWidget, QMenu, QFileDialog, QGraphicsDropShadowEffect
)

from src.services.diet_plans_service import DietPlansService
from src.services.foods_catalog_service import FoodsCatalogService
from src.ui.dialogs.select_meal_template_dialog import SelectMealTemplateDialog


# Roles for plan list table
ACTIVE_ROLE = int(Qt.UserRole) + 101

def tr_title(text: str) -> str:
    """Turkish-friendly title-case for UI rendering.
    Keeps spacing, capitalizes first letter of each token with TR i/ı rules.
    """
    s = (text or "").strip()
    if not s:
        return ""
    def _title_word(w: str) -> str:
        if not w:
            return w
        first = w[0]
        rest = w[1:]
        if first == "i":
            first_u = "İ"
        elif first == "ı":
            first_u = "I"
        else:
            first_u = first.upper()
        rest_l = []
        for ch in rest:
            if ch == "I":
                rest_l.append("ı")
            elif ch == "İ":
                rest_l.append("i")
            else:
                rest_l.append(ch.lower())
        return first_u + "".join(rest_l)

    parts = re.split(r"(\s+)", s)
    out: list[str] = []
    for p in parts:
        if not p:
            continue
        if p.isspace():
            out.append(p)
        else:
            out.append(_title_word(p))
    return "".join(out)


class PlansListDelegate(QStyledItemDelegate):
    """Paints an accent bar for the active plan row without changing data/model."""

    def paint(self, painter: QPainter, option, index):
        super().paint(painter, option, index)

        try:
            active = bool(index.model().index(index.row(), 0).data(ACTIVE_ROLE))
        except Exception:
            active = False

        if not active:
            return

        # Draw the accent only on the first column to avoid visual noise
        if index.column() != 0:
            return

        painter.save()
        rect = option.rect

        # A thin accent bar on the left, with safe insets to look "premium"
        bar_w = 3
        x = rect.x() + 4
        y = rect.y() + 8
        h = max(0, rect.height() - 16)

        # Use palette highlight so it fits both light/dark themes
        c = QColor(46, 204, 113)
        c.setAlpha(90)
        painter.setPen(Qt.NoPen)
        painter.setBrush(c)
        painter.drawRoundedRect(QRect(x, y, bar_w, h), 2, 2)
        painter.restore()


class DietPlanDialog(QDialog):
    def __init__(self, parent=None, *, conn, title="", start_date="", end_date="", plan_text="", notes="", mode: str = "edit"):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle("Diyet Planı")
        self.setModal(True)
        self.resize(720, 520)

        lay = QVBoxLayout(self)

        form = QFormLayout()
        self.edt_title = QLineEdit(title)
        self._install_tr_context_menu(self.edt_title)
        self.edt_title.setPlaceholderText("Örn: 1200 kcal / İnsülin direnci planı")
        # Tarih alanları: takvimli seçim + GG.AA.YYYY görünüm.
        # DB tarafında yine YYYY-MM-DD saklanır (get_data içinde dönüştürülür).
        self.edt_start = QDateEdit()
        self.edt_start.setCalendarPopup(True)
        self.edt_start.setDisplayFormat("dd.MM.yyyy")
        self.edt_start.calendarWidget().setHorizontalHeaderFormat(QCalendarWidget.ShortDayNames)

        self.edt_end = QDateEdit()
        self.edt_end.setCalendarPopup(True)
        self.edt_end.setDisplayFormat("dd.MM.yyyy")
        self.edt_end.calendarWidget().setHorizontalHeaderFormat(QCalendarWidget.ShortDayNames)
        # Bitiş tarihi opsiyonel: minimum tarihte "boş" göster, DB'ye None yaz.
        # 1900 gibi tarihleri asla göstermeyelim: minimum tarihi başlangıç tarihine eşitliyoruz.
        self.edt_end.setSpecialValueText(" ")

        # Başlangıç/Bitiş tarihlerini yükle (DB: YYYY-MM-DD, UI: dd.MM.yyyy)
        sd = QDate.fromString((start_date or "").strip(), "yyyy-MM-dd")
        if not sd.isValid():
            sd = QDate.fromString((start_date or "").strip(), "dd.MM.yyyy")
        self.edt_start.setDate(sd if sd.isValid() else QDate.currentDate())

        # End-date minimum = start-date (hem mantıklı, hem de boş görünüm için güvenli).
        self._end_min = self.edt_start.date()
        self.edt_end.setMinimumDate(self._end_min)

        ed = QDate.fromString((end_date or "").strip(), "yyyy-MM-dd")
        if not ed.isValid():
            ed = QDate.fromString((end_date or "").strip(), "dd.MM.yyyy")
        self.edt_end.setDate(ed if ed.isValid() else self._end_min)

        # Start date değişirse end-date minimum'u senkron tut.
        self.edt_start.dateChanged.connect(self._sync_end_min)
        # Plan content: professional meal-based entry (DB model unchanged).
        # We keep DB/storage as a single plan_text, but UI lets dietitians enter by meal.
        self.tabs = QTabWidget()
        self.tabs.setObjectName("DietPlanMealTabs")

        def _mk_edit(ph: str) -> QTextEdit:
            te = QTextEdit()
            te.setAcceptRichText(False)
            te.setPlaceholderText(ph)
            return te

        self.meal_edits = {
            "kahvalti": _mk_edit("Kahvaltı içeriği (besinler, miktarlar, alternatifler...)"),
            "ogle": _mk_edit("Öğle içeriği (besinler, miktarlar, alternatifler...)"),
            "aksam": _mk_edit("Akşam içeriği (besinler, miktarlar, alternatifler...)"),
            "ara": _mk_edit("Ara öğünler (atıştırmalıklar, ara öğün seçenekleri...)"),
        }
        self._tab_keys = ["kahvalti", "ogle", "aksam", "ara"]
        self.tabs.addTab(self.meal_edits["kahvalti"], "Kahvaltı")
        self.tabs.addTab(self.meal_edits["ogle"], "Öğle")
        self.tabs.addTab(self.meal_edits["aksam"], "Akşam")
        self.tabs.addTab(self.meal_edits["ara"], "Ara Öğünler")

        # Fill tabs from existing plan_text (supports legacy free-text with headings).
        sections = self._split_plan_text(plan_text or "")
        for k, te in self.meal_edits.items():
            te.setPlainText((sections.get(k) or "").strip())

        self.txt_notes = QTextEdit(notes or "")
        self.txt_notes.setPlaceholderText("Ek notlar (danışana özel uyarılar, takip planı...)")

        form.addRow("Başlık", self.edt_title)
        form.addRow("Başlangıç Tarihi", self.edt_start)
        form.addRow("Bitiş Tarihi", self.edt_end)

        plan_hdr = QWidget()
        plan_hdr_lay = QHBoxLayout(plan_hdr)
        plan_hdr_lay.setContentsMargins(0, 0, 0, 0)
        plan_hdr_lay.addWidget(QLabel("Plan İçeriği"))
        plan_hdr_lay.addStretch(1)
        self.btn_add_meal_tpl = QPushButton("Öğün Şablonu Ekle")
        self.btn_add_meal_tpl.setObjectName("SecondaryBtn")
        self.btn_add_meal_tpl.clicked.connect(self._insert_meal_template)
        plan_hdr_lay.addWidget(self.btn_add_meal_tpl)

        
        # Quick Add (dietitian workflow): Meal + Food + Amount -> appends formatted line.
        quick = QWidget()
        quick.setObjectName("DietPlanQuickAdd")
        ql = QHBoxLayout(quick)
        ql.setContentsMargins(0, 0, 0, 0)
        ql.setSpacing(8)

        lbl_quick = QLabel("Hızlı Ekle:")
        lbl_quick.setObjectName("MutedLabel")
        self.cmb_meal = QComboBox()
        self.cmb_meal.addItems(["Kahvaltı", "Öğle", "Akşam", "Ara Öğünler"])
        self.cmb_meal.setFixedWidth(150)
        # Fix transparent popup on some themes (QComboBox uses a QListView popup)
        try:
            self.cmb_meal.view().setStyleSheet(
                "QAbstractItemView { background: #FFFFFF; color: #082C3F; "
                "selection-background-color: rgba(58, 157, 114, 0.25); "
                "selection-color: #082C3F; border: 1px solid rgba(8,44,63,0.18); }"
            )
        except Exception:
            pass

        self.edt_food = QLineEdit()
        self._install_tr_context_menu(self.edt_food)
        self.edt_food.setPlaceholderText("Besin adı")

        # Autocomplete (robust): custom popup list anchored to the input.
        # QCompleter popups can become transparent/hidden under heavy QSS on some machines.
        # This popup is a small QListWidget inside a QFrame that we fully control.
        try:
            cat = FoodsCatalogService(self.conn)
            rows = cat.search_page(query="", limit=5000, offset=0)
            names = [r.get("name", "").strip() for r in rows if (r.get("name") or "").strip()]
        except Exception:
            names = []
        self._food_names = sorted(set(names), key=lambda s: s.lower()) if names else []

        self._food_popup = QFrame(self)
        self._food_popup.setWindowFlags(Qt.ToolTip)
        self._food_popup.setObjectName("FoodSuggestPopup")
        self._food_popup.setStyleSheet(
            "QFrame#FoodSuggestPopup { background: #FFFFFF; border: 1px solid rgba(8,44,63,0.18); border-radius: 8px; }"
            "QListWidget { border: none; background: transparent; padding: 6px; }"
            "QListWidget::item { padding: 6px 8px; border-radius: 6px; }"
            "QListWidget::item:selected { background: rgba(58, 157, 114, 0.20); color: #082C3F; }"
        )
        self._food_list = QListWidget(self._food_popup)
        # Prevent tooltip popup from stealing focus (otherwise it hides instantly)
        self._food_popup.setFocusPolicy(Qt.NoFocus)
        self._food_list.setFocusPolicy(Qt.NoFocus)
        self._food_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._food_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._food_list.setSelectionMode(QListWidget.SingleSelection)

        pop_lay = QVBoxLayout(self._food_popup)
        pop_lay.setContentsMargins(0, 0, 0, 0)
        pop_lay.addWidget(self._food_list)

        def _hide_popup():
            if self._food_popup.isVisible():
                self._food_popup.hide()

        def _apply_choice(item):
            if not item:
                return
            self.edt_food.setText(item.text())
            _hide_popup()
            self.edt_amt.setFocus()

        self._food_list.itemClicked.connect(_apply_choice)

        # Hide popup when user clicks anywhere outside the food input/popup
        class _FoodPopupFilter(QObject):
            def __init__(self, parent):
                super().__init__(parent)
                self._parent = parent

            def eventFilter(self, obj, event):
                if event.type() == QEvent.MouseButtonPress and self._parent._food_popup.isVisible():
                    w = QApplication.widgetAt(event.globalPosition().toPoint()) if hasattr(event, 'globalPosition') else QApplication.widgetAt(event.globalPos())
                    # If click is not on the line edit nor inside the popup, hide it
                    if w is not None:
                        inside_popup = (w is self._parent._food_popup) or self._parent._food_popup.isAncestorOf(w)
                        inside_edit = (w is self._parent.edt_food)
                        if (not inside_popup) and (not inside_edit):
                            self._parent._food_popup.hide()
                    else:
                        self._parent._food_popup.hide()
                return False

        # Install filter on the whole app (needed because popup is a tooltip window)
        self._food_popup_filter = _FoodPopupFilter(self)
        QApplication.instance().installEventFilter(self._food_popup_filter)
        self.destroyed.connect(lambda *_: QApplication.instance().removeEventFilter(self._food_popup_filter))


        def _show_food_popup():
            if not self._food_names:
                return
            q = (self.edt_food.text() or "").strip()
            if len(q) < 2:
                _hide_popup()
                return
            qlow = q.lower()
            hits = [n for n in self._food_names if qlow in n.lower()]
            if not hits:
                _hide_popup()
                return
            hits = hits[:10]
            self._food_list.clear()
            self._food_list.addItems(hits)
            self._food_list.setCurrentRow(0)

            # Position popup right under the input
            g = self.edt_food.mapToGlobal(QPoint(0, self.edt_food.height() + 2))
            w = max(self.edt_food.width(), 320)
            self._food_popup.setGeometry(g.x(), g.y(), w, min(280, 32 + 28 * len(hits)))
            self._food_popup.show()

        def _food_keypress(e):
            if self._food_popup.isVisible():
                if e.key() in (Qt.Key_Down, Qt.Key_Up):
                    row = self._food_list.currentRow()
                    if e.key() == Qt.Key_Down:
                        row = min(row + 1, self._food_list.count() - 1)
                    else:
                        row = max(row - 1, 0)
                    self._food_list.setCurrentRow(row)
                    return
                if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
                    # If user is typing a non-catalog item, don't force-pick the first suggestion.
                    typed = (self.edt_food.text() or '').strip()
                    it = self._food_list.currentItem()
                    if it is not None and typed and it.text().strip().lower() == typed.lower():
                        _apply_choice(it)
                    else:
                        _hide_popup()
                        self.edt_amt.setFocus()
                    return
                if e.key() == Qt.Key_Escape:
                    _hide_popup()
                    return
            return QLineEdit.keyPressEvent(self.edt_food, e)

        # Monkey patch keyPressEvent for this input only (safe and localized)
        self.edt_food.keyPressEvent = _food_keypress

        self.edt_food.textEdited.connect(lambda _t: _show_food_popup())
        # self.edt_food.editingFinished.connect(_hide_popup)  # hide handled by Esc/selection

        self.edt_amt = QLineEdit()
        self._install_tr_context_menu(self.edt_amt)
        self.edt_amt.setPlaceholderText("Miktar")
        self.edt_amt.setFixedWidth(90)

        self.cmb_unit = QComboBox()
        self.cmb_unit.addItems(["g", "adet", "dilim", "kase", "bardak", "y.k.", "ç.k.", "ml"])
        self.cmb_unit.setFixedWidth(80)
        try:
            self.cmb_unit.view().setStyleSheet(
                "QAbstractItemView { background: #FFFFFF; color: #082C3F; "
                "selection-background-color: rgba(58, 157, 114, 0.25); "
                "selection-color: #082C3F; border: 1px solid rgba(8,44,63,0.18); }"
            )
        except Exception:
            pass

        self.btn_quick_add = QPushButton("Ekle")
        self.btn_quick_add.setObjectName("PrimaryBtn")
        self.btn_quick_add.clicked.connect(self._quick_add_line)

        ql.addWidget(lbl_quick)
        ql.addWidget(self.cmb_meal)
        ql.addWidget(self.edt_food, 2)
        ql.addWidget(self.edt_amt, 0)
        ql.addWidget(self.cmb_unit, 0)
        ql.addWidget(self.btn_quick_add)

        # Keep meal selector in sync with tabs (and vice-versa)
        def _sync_combo_from_tab(i: int):
            try:
                self.cmb_meal.blockSignals(True)
                self.cmb_meal.setCurrentIndex(i)
            finally:
                self.cmb_meal.blockSignals(False)

        self.tabs.currentChanged.connect(_sync_combo_from_tab)
        self.cmb_meal.currentIndexChanged.connect(lambda i: self.tabs.setCurrentIndex(i))

        form.addRow("", quick)

        form.addRow(plan_hdr, self.tabs)
        form.addRow("Not", self.txt_notes)
        lay.addLayout(form)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QPushButton("Vazgeç")
        self.btn_ok = QPushButton("Kaydet")
        self.btn_ok.setObjectName("PrimaryBtn")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._validate_and_accept)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        lay.addLayout(btns)

        # View mode: read-only document preview (no edits).
        if (mode or '').lower() == 'view':
            for w in (self.edt_title, self.edt_start, self.edt_end, self.tabs, self.txt_notes, *self.meal_edits.values()):
                w.setEnabled(False)
            self.btn_add_meal_tpl.setVisible(False)
            self.btn_cancel.setVisible(False)
            self.btn_ok.setText('Kapat')

    
    def _install_tr_context_menu(self, w: QLineEdit):
        """TR/opaque context menu for QLineEdit in this dialog.
        Uses parent's installer if available; otherwise installs locally."""
        try:
            p = self.parent()
            if p is not None and hasattr(p, "_install_tr_context_menu"):
                p._install_tr_context_menu(w)  # type: ignore[attr-defined]
                return
        except Exception:
            pass

        # Local fallback (Qt-safe)
        try:
            w.setContextMenuPolicy(Qt.CustomContextMenu)

            def _show_menu(pos):
                menu = QMenu(w)
                menu.setStyleSheet(
                    "QMenu { background-color: #ffffff; color: #222; border: 1px solid #cfcfcf; }"
                    "QMenu::item { padding: 6px 18px; }"
                    "QMenu::item:selected { background-color: #e9f3ec; }"
                    "QMenu::separator { height: 1px; background: #e5e5e5; margin: 4px 8px; }"
                )

                a_undo = menu.addAction("Geri Al")
                a_redo = menu.addAction("Yinele")
                menu.addSeparator()
                a_cut = menu.addAction("Kes")
                a_copy = menu.addAction("Kopyala")
                a_paste = menu.addAction("Yapıştır")
                a_del = menu.addAction("Sil")
                menu.addSeparator()
                a_all = menu.addAction("Tümünü Seç")

                a_undo.setEnabled(w.isUndoAvailable())
                a_redo.setEnabled(w.isRedoAvailable())
                a_cut.setEnabled(w.hasSelectedText() and not w.isReadOnly())
                a_copy.setEnabled(w.hasSelectedText())
                a_paste.setEnabled(bool(QApplication.clipboard().text()) and not w.isReadOnly())
                a_del.setEnabled(w.hasSelectedText() and not w.isReadOnly())

                act = menu.exec(w.mapToGlobal(pos))
                if act == a_undo:
                    w.undo()
                elif act == a_redo:
                    w.redo()
                elif act == a_cut:
                    w.cut()
                elif act == a_copy:
                    w.copy()
                elif act == a_paste:
                    w.paste()
                elif act == a_del:
                    w.del_()
                elif act == a_all:
                    w.selectAll()

            w.customContextMenuRequested.connect(_show_menu)
        except Exception:
            pass

    def _split_plan_text(self, plan_text: str) -> dict:
        """Parse legacy/free plan_text into meal sections.
        Supports headings like [Kahvaltı], Kahvaltı:, etc.
        Returns keys: kahvalti, ogle, aksam, ara.
        """
        txt = (plan_text or "").replace("\r\n", "\n")
        keys = {"kahvalti": [], "ogle": [], "aksam": [], "ara": []}
        current = None

        def key_from_heading(h: str):
            s = (h or "").strip().lower()
            if "kahvalt" in s:
                return "kahvalti"
            if "öğle" in s or "ogle" in s:
                return "ogle"
            if "akşam" in s or "aksam" in s:
                return "aksam"
            if "ara" in s or "snack" in s:
                return "ara"
            return None

        heading_re = re.compile(r"^\s*(?:\[(?P<br>[^\]]+)\]|(?P<co>[^:]{2,}):)\s*$")

        for raw in txt.splitlines():
            line = raw.rstrip()
            m = heading_re.match(line.strip())
            if m:
                h = (m.group("br") or m.group("co") or "").strip()
                k = key_from_heading(h)
                if k:
                    current = k
                continue

            if not line.strip():
                if current and keys[current] and keys[current][-1] != "":
                    keys[current].append("")
                continue

            if current is None:
                # If no heading at all, default to Ara Öğünler (safe bucket)
                current = "ara"
            keys[current].append(line)

        return {k: "\n".join(v).strip() for k, v in keys.items()}

    def _merge_plan_text(self) -> str:
        """Build canonical plan_text from meal tabs (DB model unchanged)."""
        order = [
            ("kahvalti", "Kahvaltı"),
            ("ogle", "Öğle"),
            ("aksam", "Akşam"),
            ("ara", "Ara Öğünler"),
        ]
        parts = []
        for k, title in order:
            body = (self.meal_edits[k].toPlainText() or "").strip()
            parts.append(f"[{title}]")
            parts.append(body)
            parts.append("")  # spacing between sections
        return "\n".join(parts).strip() + "\n"
    
    def _quick_add_line(self):
        try:
            if hasattr(self, '_food_popup') and self._food_popup.isVisible():
                self._food_popup.hide()
        except Exception:
            pass
        food = (self.edt_food.text() or "").strip()
        food = tr_title(food)
        amt = (self.edt_amt.text() or "").strip()
        unit = ""
        try:
            unit = (self.cmb_unit.currentText() or "").strip()
        except Exception:
            unit = ""
        if amt:
            amt = amt.strip()
        if not food:
            self.edt_food.setFocus()
            return
        amt_full = ""
        if amt:
            amt_full = amt if not unit else f"{amt} {unit}"
        line = food if not amt_full else f"{food} - {amt_full}"

        idx = int(self.cmb_meal.currentIndex())
        idx = max(0, min(idx, len(self._tab_keys) - 1))
        key = self._tab_keys[idx]
        te = self.meal_edits.get(key)
        if te is None:
            return

        self.tabs.setCurrentIndex(idx)
        self._append_line(te, line)

        self.edt_food.clear()
        self.edt_amt.clear()
        self.edt_food.setFocus()

    @staticmethod
    def _append_line(te: QTextEdit, line: str):
        line = (line or "").strip()
        if not line:
            return
        cur = te.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        te.setTextCursor(cur)

        existing = te.toPlainText()
        sep = "" if not existing.strip() else ("" if existing.endswith("\n") else "\n")
        te.insertPlainText(f"{sep}{line}\n")


    def _insert_meal_template(self):
        dlg = SelectMealTemplateDialog(self, conn=self.conn)
        if dlg.exec() != QDialog.Accepted:
            return
        tpl = dlg.get_selected()
        if not tpl:
            return

        block_name = (tpl.name or "").strip()
        block_body = (tpl.content or "").strip()
        if not block_body:
            QMessageBox.information(self, "Bilgi", "Seçilen şablonun içeriği boş.")
            return

        def key_from_name(name: str):
            s = (name or "").strip().lower()
            if "kahvalt" in s:
                return "kahvalti"
            if "öğle" in s or "ogle" in s:
                return "ogle"
            if "akşam" in s or "aksam" in s:
                return "aksam"
            if "ara" in s or "snack" in s:
                return "ara"
            return None

        k = key_from_name(block_name)
        if k and k in self.meal_edits:
            # Switch to the relevant meal tab for a consistent dietitian workflow
            self.tabs.setCurrentIndex(self._tab_keys.index(k))
            te = self.meal_edits[k]
        else:
            # If we cannot infer the meal from template name, ask the user (dietitian-friendly).
            meal_labels = [
                ("kahvalti", "Kahvaltı"),
                ("ogle", "Öğle"),
                ("aksam", "Akşam"),
                ("ara", "Ara Öğünler"),
            ]
            current_key = self._tab_keys[self.tabs.currentIndex()]
            keys = [k for k, _ in meal_labels]
            labels = [lbl for _, lbl in meal_labels]
            default_idx = keys.index(current_key) if current_key in keys else 0

            choice, ok = QInputDialog.getItem(
                self, "Öğün Seç", "Şablon hangi öğüne eklensin?", labels, default_idx, False
            )
            if not ok:
                return
            chosen_key = next((k for k, lbl in meal_labels if lbl == choice), current_key)
            self.tabs.setCurrentIndex(self._tab_keys.index(chosen_key))
            te = self.meal_edits[chosen_key]

        cursor = te.textCursor()
        sep = "" if cursor.position() == 0 else ("\n" if te.toPlainText().endswith("\n") else "\n\n")

        # If template name is not one of core meals, add a small subheading for clarity
        if not k:
            insert_text = f"{sep}{block_name}:\n{block_body}\n"
        else:
            insert_text = f"{sep}{block_body}\n"

        cursor.insertText(insert_text)
        te.setFocus()

    def _validate_and_accept(self):
        title = (self.edt_title.text() or "").strip()
        if not title:
            QMessageBox.warning(self, "Uyarı", "Başlık boş olamaz.")
            return

        # QDateEdit sayesinde format hatası olmaz; yine de geçerlilik kontrolü yapalım.
        sd = self.edt_start.date()
        if not sd.isValid():
            QMessageBox.warning(self, "Uyarı", "Başlangıç tarihi seçiniz.")
            return

        self.accept()


    def _sync_end_min(self, qdate: QDate):
        """Bitiş tarihi minimumunu başlangıç tarihine kilitler."""
        self._end_min = qdate
        self.edt_end.setMinimumDate(qdate)
        # End-date, start-date'den küçükse yukarı çek (boş görünüm = min date).
        if self.edt_end.date() < qdate:
            self.edt_end.setDate(qdate)

    def get_data(self) -> dict:
        return {
            "title": (self.edt_title.text() or "").strip(),
            "start_date": self.edt_start.date().toString("yyyy-MM-dd"),
            "end_date": (None if self.edt_end.date() == self._end_min else self.edt_end.date().toString("yyyy-MM-dd")),
            "plan_text": self._merge_plan_text(),
            "notes": self.txt_notes.toPlainText() or "",
        }


class DietPlansScreen(QWidget):
    def __init__(self, conn, client_id: str, log=None, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.client_id = client_id
        self.log = log
        self.svc = DietPlansService(conn)

        self._plans_cache: dict[str, object] = {}
        self._client_cache: dict[str, str] | None = None

        # Keep last rendered HTML so PDF export can match the preview 1:1
        self._last_preview_html: str = ""
        self._last_preview_plan_id: str | None = None

        root = QVBoxLayout(self)

        card = QFrame()
        self._card_frame = card
        card.setObjectName("Card")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(12)

        # Header
        header = QHBoxLayout()
        header.addWidget(QLabel("Diyet Planları", objectName="CardTitle"))
        header.addStretch(1)

        self.btn_add = QPushButton("Yeni Plan")
        self.btn_add.setObjectName("PrimaryBtn")
        self.btn_add.clicked.connect(self._add)
        header.addWidget(self.btn_add)

        self.btn_edit = QPushButton("Düzenle")
        self.btn_edit.setObjectName("InfoBtn")
        self.btn_edit.clicked.connect(self._edit)
        header.addWidget(self.btn_edit)

        self.btn_active = QPushButton("Aktif Yap")
        self.btn_active.setObjectName("IndigoBtn")
        self.btn_active.clicked.connect(self._set_active)
        header.addWidget(self.btn_active)

        self.btn_del = QPushButton("Sil")
        self.btn_del.setObjectName("DangerBtn")
        self.btn_del.clicked.connect(self._delete)
        header.addWidget(self.btn_del)

        self.btn_refresh = QPushButton("Yenile")
        self.btn_refresh.setObjectName("NeutralBtn")
        self.btn_refresh.clicked.connect(self.refresh)
        header.addWidget(self.btn_refresh)

        # Export / Print (preview == PDF hedefi)
        self.btn_pdf = QPushButton("PDF / Çıktı")
        self.btn_preview = QPushButton("Önizle")
        self.btn_pdf.setObjectName("PrimaryBlueBtn")
        self.btn_pdf.setToolTip("Seçili plan için PDF indir veya yazdır")
        self.btn_pdf.clicked.connect(self._open_export_menu)
        header.addWidget(self.btn_pdf)

        for _b in (self.btn_edit, self.btn_active, self.btn_del, self.btn_pdf):
            _b.setEnabled(False)

        lay.addLayout(header)

        # Toast (küçük, kurumsal bilgilendirme) — modal olmayan bildirim
        # Toast (küçük, kurumsal bilgilendirme) — modal olmayan bildirim
        # Bu toast; metin + (opsiyonel) aksiyon butonları (PDF Aç / Klasörde Göster) destekler.
        self._toast_box = QFrame(card)
        self._toast_box.setObjectName("ToastBox")
        self._toast_box.setProperty("ok", True)
        # Subtle shadow for visibility (pro feel)
        try:
            _shadow = QGraphicsDropShadowEffect(self._toast_box)
            _shadow.setBlurRadius(18)
            _shadow.setOffset(0, 4)
            _shadow.setColor(QColor(0, 0, 0, 80))
            self._toast_box.setGraphicsEffect(_shadow)
        except Exception:
            pass
        self._toast_box.hide()
        _tl = QHBoxLayout(self._toast_box)
        _tl.setContentsMargins(10, 6, 10, 6)
        _tl.setSpacing(8)
        self._toast_label = QLabel("", self._toast_box)
        self._toast_label.setObjectName("ToastBoxLabel")
        _tl.addWidget(self._toast_label, 1)
        self._toast_btn_open = QPushButton("PDF’i Aç", self._toast_box)
        self._toast_btn_open.setObjectName("ToastActionPrimary")
        self._toast_btn_open.hide()
        _tl.addWidget(self._toast_btn_open)
        self._toast_btn_folder = QPushButton("Klasörde Göster", self._toast_box)
        self._toast_btn_folder.setObjectName("ToastAction")
        self._toast_btn_folder.hide()
        _tl.addWidget(self._toast_btn_folder)
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._toast_box.hide)

        # Inline status bar row (no overlay): keeps actions visible and feels pro
        _status_row = QHBoxLayout()
        _status_row.setContentsMargins(0, 0, 0, 0)
        _status_row.setSpacing(0)
        _status_row.addStretch(1)
        _status_row.addWidget(self._toast_box, 0, Qt.AlignCenter)
        _status_row.addStretch(1)
        lay.addLayout(_status_row)

        # Keep original PDF button label to restore after busy state
        self._pdf_btn_default_text = self.btn_pdf.text()

        # Body: Left list + Right preview
        body = QHBoxLayout()
        body.setSpacing(14)

        # Left panel
        left = QFrame()
        left.setObjectName("DietPlansLeftPane")
        left.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        left.setMaximumWidth(460)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(10)

        self.tbl = QTableWidget(0, 3)
        self.tbl.setObjectName("PlansListTable")
        self.tbl.setHorizontalHeaderLabels(["Tarih", "Başlık", "Durum"])
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.doubleClicked.connect(self._open_view)
        self.tbl.itemSelectionChanged.connect(self._on_selection_changed)

        # Compact sizing
        self.tbl.verticalHeader().setDefaultSectionSize(52)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setShowGrid(False)

        # Prevent horizontal scrolling; keep a clean, "product" list feel
        self.tbl.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.tbl.setMouseTracking(True)
        self.tbl.viewport().setMouseTracking(True)
        self.tbl.setItemDelegate(PlansListDelegate(self.tbl))

        hdr = self.tbl.horizontalHeader()
        hdr.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hdr.setStretchLastSection(False)

        # Column sizing: compact date range, title stretches, status chip fixed
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)    # Tarih
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)  # Başlık
        hdr.setSectionResizeMode(2, QHeaderView.Fixed)    # Durum
        self.tbl.setColumnWidth(0, 135)
        self.tbl.setColumnWidth(2, 104)

        left_lay.addWidget(self.tbl)

        hint = QLabel("İpucu: Aktif plan, Klinik Özet ve danışan ekranında varsayılan olarak kullanılabilir.")
        hint.setObjectName("HintLabel")
        hint.setWordWrap(True)
        left_lay.addWidget(hint)

        # Right panel (preview)
        right = QFrame()
        right.setObjectName("DietPlansPreviewPane")
        right.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(10)

        self.preview_card = QFrame()
        self.preview_card.setObjectName("DietPlanPreviewCard")
        self.preview_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        pc_lay = QVBoxLayout(self.preview_card)
        pc_lay.setContentsMargins(18, 18, 18, 18)
        pc_lay.setSpacing(12)

        # Empty state
        self.empty_wrap = QWidget()
        ew = QVBoxLayout(self.empty_wrap)
        ew.setContentsMargins(0, 0, 0, 0)
        ew.setSpacing(10)
        ew.addStretch(1)

        self.empty_title = QLabel("Diyet Planı Önizleme")
        self.empty_title.setObjectName("PreviewTitle")
        ew.addWidget(self.empty_title, alignment=Qt.AlignHCenter)

        self.empty_sub = QLabel("Soldan bir plan seçin ya da yeni bir plan oluşturun.\nSeçtiğiniz plan burada danışana verilecek bir doküman gibi önizlenecek.")
        self.empty_sub.setObjectName("SubTitle")
        self.empty_sub.setWordWrap(True)
        self.empty_sub.setAlignment(Qt.AlignHCenter)
        ew.addWidget(self.empty_sub)

        self.empty_btn = QPushButton("Yeni Plan Oluştur")
        self.empty_btn.setObjectName("PrimaryBtn")
        self.empty_btn.clicked.connect(self._add)
        ew.addWidget(self.empty_btn, alignment=Qt.AlignHCenter)
        ew.addStretch(1)

        # Preview browser
        self.preview = QTextBrowser()
        self.preview.setObjectName("DietPlanPreviewBrowser")
        self.preview.setOpenExternalLinks(False)
        self.preview.setStyleSheet(
            "QTextBrowser#DietPlanPreviewBrowser {"
            " background: #E9EEF2;"
            " border: none;"
            " padding: 0px;"
            " }"
        )
        self.preview.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)


        # Stacked behavior (manual)
        pc_lay.addWidget(self.empty_wrap)
        pc_lay.addWidget(self.preview)
        self.preview.hide()

        right_lay.addWidget(self.preview_card)

        body.addWidget(left, 3)
        body.addWidget(right, 7)

        lay.addLayout(body, 1)

        root.addWidget(card, 1)

        self.refresh()

    def _get_client_info(self) -> dict[str, str]:
        if self._client_cache is not None:
            return self._client_cache
        info = {"full_name": "", "phone": "", "birth_date": "", "gender": ""}
        try:
            cur = self.conn.execute(
                "SELECT full_name, phone, birth_date, gender FROM clients WHERE id=? AND is_active=1",
                (self.client_id,),
            )
            row = cur.fetchone()
            if row:
                info["full_name"] = row[0] or ""
                info["phone"] = row[1] or ""
                info["birth_date"] = row[2] or ""
                info["gender"] = row[3] or ""
        except Exception:
            pass
        self._client_cache = info
        return info


    @staticmethod
    def _fmt_date_compact(iso_yyyy_mm_dd: str) -> str:
        """UI compact date (dd.MM)."""
        if not iso_yyyy_mm_dd:
            return ""
        try:
            d = QDate.fromString(iso_yyyy_mm_dd, "yyyy-MM-dd")
            if d.isValid():
                return d.toString("dd.MM")
        except Exception:
            pass
        return iso_yyyy_mm_dd

    def _fmt_range_compact(self, start_iso: str, end_iso: str) -> tuple[str, str]:
        """Return (display, tooltip_full) for date ranges."""
        s_full = self._fmt_date_ui(start_iso)
        e_full = self._fmt_date_ui(end_iso)
        s = self._fmt_date_compact(start_iso)
        e = self._fmt_date_compact(end_iso)

        if s and e and s != e:
            disp = f"{s} → {e}"
            tip = f"{s_full} – {e_full}".strip(" –")
            return disp, tip

        disp = s_full or e_full or ""
        return disp, disp

    @staticmethod
    def _fmt_date_ui(iso_yyyy_mm_dd: str) -> str:
        if not iso_yyyy_mm_dd:
            return ""
        try:
            d = QDate.fromString(iso_yyyy_mm_dd, "yyyy-MM-dd")
            if d.isValid():
                return d.toString("dd.MM.yyyy")
        except Exception:
            pass
        return iso_yyyy_mm_dd


    def _get_watermark_path(self) -> str:
        """Return an absolute path to a PNG watermark (pre-alpha), creating fallback if needed."""
        svc = SettingsService(self.conn)
        rel = svc.get_value("clinic_logo_watermark_path", "") or ""
        def _resolve(rel_or_abs: str) -> Path:
            p = Path(rel_or_abs)
            if p.is_absolute():
                return p
            base = Path(__file__).resolve().parents[2]  # src
            return (base / rel_or_abs).resolve()

        if rel:
            p = _resolve(rel)
            if p.exists():
                return str(p)

        # fallback: ensure a soft watermark from NutriNexus logo
        base = Path(__file__).resolve().parents[2]
        user_dir = base / "assets" / "user"
        user_dir.mkdir(parents=True, exist_ok=True)
        fallback = user_dir / "nutrinexus_logo_watermark.png"
        if not fallback.exists():
            src_logo = base / "assets" / "nutrinexus_logo.png"
            img = QImage(str(src_logo))
            if not img.isNull():
                scaled = img.scaledToWidth(520, Qt.SmoothTransformation)
                wm = QImage(scaled.size(), QImage.Format_ARGB32)
                wm.fill(Qt.transparent)
                painter = QPainter(wm)
                painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                painter.setOpacity(0.06)
                painter.drawImage(0, 0, scaled)
                painter.end()
                wm.save(str(fallback), "PNG")
        return str(fallback)
    def _get_header_logo_url(self) -> str:
        """Return a file URL for header logo (clinic if set, otherwise NutriNexus)."""
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
                return QUrl.fromLocalFile(str(p)).toString()

        base = Path(__file__).resolve().parents[2]
        fallback = (base / "assets" / "nutrinexus_logo.png").resolve()
        if fallback.exists():
            return QUrl.fromLocalFile(str(fallback)).toString()
        return ""


    def _selected_plan_id(self) -> str | None:
        r = self.tbl.currentRow()
        if r < 0:
            return None
        item = self.tbl.item(r, 0)
        return item.data(Qt.UserRole) if item else None

    def _on_selection_changed(self):
        pid = self._selected_plan_id()
        has = pid is not None
        for _b in (self.btn_edit, self.btn_active, self.btn_del, self.btn_pdf):
            _b.setEnabled(has)

        if not pid:
            self._show_empty_preview()
            return

        plan = self._plans_cache.get(pid)
        if not plan:
            plan = self.svc.get(pid)
            if plan:
                self._plans_cache[pid] = plan

        if plan:
            self._render_preview(plan)
        else:
            self._show_empty_preview()

    def _show_empty_preview(self):
        self.preview.hide()
        self.empty_wrap.show()

    # ---------- UX helpers ----------
    def _show_toast(self, text: str, ok: bool = True, ms: int = 2400) -> None:
        """Show a small, non-modal toast message.

        Toast; metin + opsiyonel aksiyon butonlarını destekler. Varsayılan durumda
        butonlar gizlenir.
        """
        try:
            # Hide action buttons by default for plain messages
            try:
                self._toast_btn_open.hide()
                self._toast_btn_folder.hide()
            except Exception:
                pass

            self._toast_label.setText(text)
            self._toast_box.setProperty("ok", bool(ok))
            # Force style refresh when dynamic property changes
            try:
                self._toast_box.style().unpolish(self._toast_box)
                self._toast_box.style().polish(self._toast_box)
            except Exception:
                pass
            self._toast_box.show()
            self._toast_timer.start(ms)
        except Exception:
            # If toast fails for any reason, fall back silently (don't break flow).
            pass

    def _show_pdf_toast_actions(self, pdf_path: str) -> None:
        """PDF oluşturulduktan sonra: PDF Aç / Klasörde Göster aksiyonları."""
        try:
            import os
            import subprocess
            from pathlib import Path

            p = (pdf_path or "").strip()
            if not p:
                self._show_toast("PDF oluşturuldu.", ok=True)
                return

            p = str(Path(p))

            # Set message and show buttons
            self._toast_label.setText("PDF oluşturuldu.")
            self._toast_box.setProperty("ok", True)
            try:
                self._toast_box.style().unpolish(self._toast_box)
                self._toast_box.style().polish(self._toast_box)
            except Exception:
                pass

            # Safely reset connections (avoid stacking)
            try:
                self._toast_btn_open.clicked.disconnect()
            except Exception:
                pass
            try:
                self._toast_btn_folder.clicked.disconnect()
            except Exception:
                pass

            def _open_pdf():
                try:
                    if os.name == "nt":
                        os.startfile(p)  # type: ignore[attr-defined]
                    else:
                        # Fallback for non-Windows
                        subprocess.Popen(["xdg-open", p])
                except Exception:
                    self._show_toast("PDF açılamadı.", ok=False)

            def _show_in_folder():
                try:
                    if os.name == "nt":
                        subprocess.Popen(["explorer", "/select,", p])
                    else:
                        subprocess.Popen(["xdg-open", str(Path(p).parent)])
                except Exception:
                    self._show_toast("Klasör açılamadı.", ok=False)

            self._toast_btn_open.clicked.connect(_open_pdf)
            self._toast_btn_folder.clicked.connect(_show_in_folder)
            self._toast_btn_open.show()
            self._toast_btn_folder.show()

            # Show toast longer (user may need time)
            self._toast_box.show()
            self._toast_timer.start(6500)
        except Exception:
            self._show_toast("PDF oluşturuldu.", ok=True)

    
    def _position_toast(self) -> None:
        """Deprecated: toast is now inline (in layout), so positioning is unnecessary.

        Kept for backward-compatibility to avoid breaking older calls.
        """
        return

    def _set_pdf_busy(self, busy: bool, label: str | None = None) -> None:
        """Disable export button and show a busy label while generating/printing."""
        try:
            if busy:
                self.btn_pdf.setEnabled(False)
                self.btn_pdf.setText(label or "İşleniyor...")
                try:
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                except Exception:
                    pass
            else:
                self.btn_pdf.setText(self._pdf_btn_default_text)
                # Re-enable according to selection state
                self.btn_pdf.setEnabled(self._selected_plan_id() is not None)
                try:
                    QApplication.restoreOverrideCursor()
                except Exception:
                    pass
        except Exception:
            pass

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._position_toast()

    
    def _open_export_menu(self):
        """Open export menu for selected plan."""
        pid = self._selected_plan_id()
        if not pid:
            QMessageBox.information(self, "Bilgi", "Önce bir diyet planı seçin.")
            return

        menu = QMenu(self)

        # More vivid, product-like menu
        menu.setStyleSheet(
            "QMenu { background-color: #ffffff; color: #111827; border: 1px solid #d1d5db; border-radius: 10px; }"
            "QMenu::item { padding: 9px 20px; font-weight: 600; }"
            "QMenu::item:selected { background-color: #2563EB; color: #ffffff; }"
            "QMenu::separator { height: 1px; background: #e5e7eb; margin: 6px 10px; }"
            "QMenu::icon { padding-left: 10px; }"
        )

        # Color icons (small squares) for quick visual parsing
        def _color_icon(hex_color: str):
            try:
                pm = QPixmap(14, 14)
                pm.fill(QColor(hex_color))
                return QIcon(pm)
            except Exception:
                return QIcon()

        act_pdf = QAction(_color_icon("#16A34A"), "PDF İndir", menu)
        act_print = QAction(_color_icon("#6366F1"), "Yazdır", menu)
        menu.addAction(act_pdf)
        menu.addAction(act_print)

        chosen = menu.exec_(self.btn_pdf.mapToGlobal(QPoint(0, self.btn_pdf.height() + 4)))
        if chosen == act_pdf:
            self._export_selected_pdf()
        elif chosen == act_print:
            self._print_selected_plan()


    def _adapt_preview_html_for_a4(self, html: str) -> str:
        """Adapt preview HTML for A4 PDF/print so it fills the printable area.

        On-screen preview uses a fixed 'paper' width (880px) and an outer grey wrapper.
        When printing to PDF, Qt may scale that fixed-width layout down, making it look
        like a small box centered on the page.

        Strategy: for print/PDF we keep the *layout proportions* but make the outer paper
        expand to the printable width, remove the grey wrapper, and drop extra paddings.
        Actual A4 sizing is handled by QPrinter + our scaled paint routine.
        """
        if not html:
            return html

        out = html

        # Clean white page for print
        out = out.replace("background:#F5F7FA;", "background:#ffffff;")

        # Remove the outer grey wrapper for print (keep only the paper)
        out = out.replace("background:#E9EEF4; border:1px solid #d0d7df;", "background:#ffffff; border:none;", 1)

        # Remove wrapper paddings used for on-screen preview
        out = out.replace('padding:18px 12px 22px 12px;', 'padding:0;', 1)
        out = out.replace('style="padding:6px;"', 'style="padding:0;"', 1)

        # Let the two fixed-width paper tables fill available width
        out = out.replace('width="892"', 'width="100%"', 1)
        out = out.replace('width="880"', 'width="100%"', 1)

        return out

    def _print_html_document(self, printer: QPrinter, html: str) -> None:
        """Print HTML to the given QPrinter as real text/vector output.

        Critical points:
        - Use QTextDocument.print_ (not painting widgets) to avoid rasterized output.
        - Set the QTextDocument page size from the printer's *printable* rect.
        - Use a higher printer resolution for crisp PDFs.

        This keeps the PDF output consistent with the on-screen preview, because
        both are produced from the same HTML generator.
        """
        doc = QTextDocument()
        try:
            doc.setDefaultFont(self.font())
        except Exception:
            pass
        doc.setHtml(html)

        # PySide6 quirk: pageRect() requires a unit argument on some builds.
        try:
            page_rect = printer.pageRect(QPrinter.Unit.Point)
        except Exception:
            try:
                from PySide6.QtGui import QPageLayout
                page_rect = printer.pageLayout().paintRect(QPageLayout.Unit.Point)
            except Exception:
                page_rect = printer.pageRect()

        try:
            doc.setPageSize(QSizeF(page_rect.width(), page_rect.height()))
            doc.setTextWidth(page_rect.width())
        except Exception:
            pass

        doc.print_(printer)


    def _print_html_to_printer(self, printer: 'QPrinter', html: str) -> None:
        """Print HTML to a QPrinter using QTextDocument.print_ (vector/text output).

        Why this exists:
        - QTextDocument uses its own layout width/height; if we don't bind it to the
          printer's *printable* rect, you get the classic "page inside page" / tiny output.
        - We deliberately avoid screenshot/pixmap scaling so text stays selectable.
        """
        from PySide6.QtGui import QTextDocument, QFont
        from PySide6.QtCore import QSizeF

        doc = QTextDocument()
        doc.setDefaultFont(QFont("Segoe UI", 10))
        doc.setHtml(html)

        # IMPORTANT: Use printable rect in *device pixels* at the printer resolution.
        # Using Point() here often shrinks the layout on HiDPI/HighResolution printers.
        try:
            rect = printer.pageLayout().paintRectPixels(printer.resolution())
        except Exception:
            # Fallback (still device units for the current output device)
            rect = printer.pageRect()

        try:
            w = float(rect.width())
            h = float(rect.height())
            doc.setPageSize(QSizeF(w, h))
            doc.setTextWidth(w)
        except Exception:
            pass

        doc.print_(printer)

    def _prepare_print_html(self, html: str) -> str:
        """Takes the preview HTML and adapts it for true A4 print output.

        Key goals:
        - Remove 'page inside page' look (no gray background, no shadow)
        - Let the content use the printable width (100%)
        - Keep the visual design identical to the preview layout
        """
        if not html:
            return html

        out = html

        # Body: no gray background / outer padding in print
        out = re.sub(
            r'<body\s+style="[^"]*">',
            '<body style="background:#FFFFFF;margin:0;padding:0;">',
            out,
            count=1
        )

        # Outer background table: force white background and remove top/bottom padding
        out = out.replace("background:#F5F7FA;", "background:#FFFFFF;")
        out = out.replace("padding:18px 0;", "padding:0;")

        # The first two tables define the fixed preview width; make them fluid (100%)
        def _w100(m):
            return m.group(0).split('width=')[0] + 'width="100%"'
        # Replace width attribute for the first two <table ... width="...">
        def repl_first_two_tables(s: str) -> str:
            cnt = 0
            def _repl(m):
                nonlocal cnt
                cnt += 1
                if cnt <= 2:
                    return re.sub(r'width="\d+"', 'width="100%"', m.group(0), count=1)
                return m.group(0)
            return re.sub(r'<table\b[^>]*\bwidth="\d+"[^>]*>', _repl, s, flags=re.I)
        out = repl_first_two_tables(out)

        # Paper table: remove centering margin + shadow in print
        out = out.replace("margin: 18px auto;", "margin:0;")
        out = re.sub(r'box-shadow:[^;"]+;', 'box-shadow:none;', out)

        # If the paper has an explicit width attribute, make it 100% too
        out = re.sub(r'(<table\b[^>]*\bid="paper"[^>]*?)\s+width="\d+"', r'\1 width="100%"', out, flags=re.I)

        return out

    def _print_selected_plan(self):
        """Print selected plan to a physical printer (or Microsoft Print to PDF).

        Important: we print the exact same HTML used in the preview so users see the
        same layout on screen and in the printed/PDF output.
        """
        pid = self._selected_plan_id()
        if not pid:
            QMessageBox.information(self, "Bilgi", "Önce bir diyet planı seçin.")
            return

        plan = self._plans_cache.get(pid)
        if not plan:
            try:
                plan = self.svc.get(pid)
                if plan:
                    self._plans_cache[pid] = plan
            except Exception:
                plan = None

        if not plan:
            QMessageBox.warning(self, "Uyarı", "Seçili plan bulunamadı.")
            return

        # Ensure preview HTML is up-to-date for this plan
        if self._last_preview_plan_id != pid or not (self._last_preview_html or "").strip():
            try:
                self._render_preview(plan)
            except Exception:
                pass

        html_doc = (self._last_preview_html or "").strip()
        if not html_doc:
            # last resort: fall back to current preview document
            try:
                html_doc = self.preview.document().toHtml()
            except Exception:
                html_doc = ""

        if not (html_doc or "").strip():
            QMessageBox.warning(self, "Uyarı", "Önizleme oluşturulamadığı için yazdırma yapılamadı.")
            return

        try:
            printer = QPrinter(QPrinter.HighResolution)
            try:
                printer.setResolution(300)
            except Exception:
                pass
            try:
                printer.setPageSize(QPageSize(QPageSize.A4))
            except Exception:
                pass
            try:
                printer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Millimeter)
            except Exception:
                pass

            dlg = QPrintDialog(printer, self)
            dlg.setWindowTitle("Yazdır")
            if dlg.exec() != QPrintDialog.Accepted:
                return

            self._set_pdf_busy(True, "Yazdırılıyor…")
            try:
                html_doc = self._prepare_print_html(html_doc)
                self._print_html_to_printer(printer, html_doc)
            finally:
                self._set_pdf_busy(False)
            self._show_toast("Yazdırma başlatıldı.", ok=True)
        except Exception as e:
            if self.log:
                self.log.exception("Diyet planı yazdırılamadı: %s", e)
            QMessageBox.critical(self, "Hata", f"Yazdırma işlemi başarısız.\n\nDetay: {e}")


    def _preview_selected_pdf(self):

        """PDF Önizleme (Preview == Output)."""

        pid = self._selected_plan_id()

        if not pid:

            QMessageBox.information(self, "Bilgi", "Önce bir diyet planı seçin.")

            return


        plan = self._plans_cache.get(pid)

        if not plan:

            try:

                plan = self.svc.get(pid)

                if plan:

                    self._plans_cache[pid] = plan

            except Exception:

                plan = None


        if not plan:

            QMessageBox.warning(self, "Uyarı", "Seçili plan bulunamadı.")

            return


        client = self._get_client_info() if hasattr(self, "_get_client_info") else {}

        show_diet_plan_preview(self, client=client, plan=plan, fmt_date_ui=self._fmt_date_ui)

        return

    def _export_selected_pdf(self):
        """PDF İndir: Diet plan PDF üretimi (ReportLab)."""
    
        pid = self._selected_plan_id()
        if not pid:
            QMessageBox.information(self, "Bilgi", "Önce bir diyet planı seçin.")
            return
    
        # Default file name should include client name (stable, never crashes)
        client = {}
        try:
            if hasattr(self, "client") and isinstance(self.client, dict):
                client = self.client
        except Exception:
            client = {}
    
        if not client:
            try:
                cur = self.conn.cursor()
                cur.execute("SELECT full_name, name FROM clients WHERE id = ?", (self.client_id,))
                row = cur.fetchone()
                if row:
                    full_name, name = row
                    client = {"full_name": full_name or name or "", "name": name or full_name or ""}
            except Exception:
                client = {}
    
        client_slug = (client.get("full_name") or client.get("name") or "danisan").strip() or "danisan"
        client_slug = "".join(ch for ch in client_slug if ch.isalnum() or ch in (" ", "-", "_")).strip().replace(" ", "_")
        if not client_slug:
            client_slug = "danisan"
    
    
        plan = self._plans_cache.get(pid)

        if not plan:

            try:

                plan = self.svc.get(pid)

                if plan:

                    self._plans_cache[pid] = plan

            except Exception:

                plan = None


        if not plan:

            QMessageBox.warning(self, "Uyarı", "Seçili plan bulunamadı.")

            return


        safe_name = (plan.title or "diyet_plani").strip() or "diyet_plani"

        safe_name = re.sub(r"[^\w\-\s\.]", "", safe_name, flags=re.UNICODE).strip().replace(" ", "_")

        default_name = f"{safe_name}.pdf"


        file_path, _ = QFileDialog.getSaveFileName(self, "PDF Kaydet", default_name, "PDF Files (*.pdf)")

        if not file_path:

            return

        if not file_path.lower().endswith(".pdf"):

            file_path += ".pdf"


        c = self._get_client_info()

        start_ui = self._fmt_date_ui(plan.start_date)

        end_ui = self._fmt_date_ui(plan.end_date)

        date_range = start_ui if not end_ui else f"{start_ui} – {end_ui}"

        # PDF başlık logosu (Ayarlar -> Klinik Logo). Builder tarafı
        # otomatik olarak NutriNexus logosuna düşer.
        try:
            svc = SettingsService(self.conn)
            clinic_logo_path = (svc.get_value("clinic_logo_path", "") or "").strip()
        except Exception:
            clinic_logo_path = ""


        payload = {

            "client": c,

            "plan": {

                "id": plan.id,

                "title": plan.title,

                "start_date": plan.start_date,

                "end_date": plan.end_date,

                "plan_text": plan.plan_text,

                "notes": plan.notes,

            },

            "date_range": date_range,

            "settings": {
                "clinic_logo_path": clinic_logo_path,
            },

        }


        self._set_pdf_busy(True, "PDF hazırlanıyor…")
        try:
            build_diet_plan_pdf(file_path, payload)
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"PDF oluşturulamadı:\n{e}")
            return
        finally:
            self._set_pdf_busy(False)

        self._show_pdf_toast_actions(file_path)

    def _install_tr_context_menu(self, w: QLineEdit):
        """Replace default (English/translucent) line-edit menu with Turkish, opaque menu."""
        try:
            w.setContextMenuPolicy(Qt.CustomContextMenu)

            def _show_menu(pos):
                menu = QMenu(w)
                # Force solid background (some themes may make it translucent)
                menu.setStyleSheet(
                    "QMenu { background-color: #ffffff; color: #222; border: 1px solid #cfcfcf; }"
                    "QMenu::item { padding: 6px 18px; }"
                    "QMenu::item:selected { background-color: #e9f3ec; }"
                    "QMenu::separator { height: 1px; background: #e5e5e5; margin: 4px 8px; }"
                )

                a_undo = menu.addAction("Geri Al")
                a_redo = menu.addAction("Yinele")
                menu.addSeparator()
                a_cut = menu.addAction("Kes")
                a_copy = menu.addAction("Kopyala")
                a_paste = menu.addAction("Yapıştır")
                a_del = menu.addAction("Sil")
                menu.addSeparator()
                a_all = menu.addAction("Tümünü Seç")

                a_undo.setEnabled(w.isUndoAvailable() if hasattr(w, "isUndoAvailable") else True)
                a_redo.setEnabled(w.isRedoAvailable() if hasattr(w, "isRedoAvailable") else True)
                a_cut.setEnabled(bool(w.hasSelectedText()))
                a_copy.setEnabled(bool(w.hasSelectedText()))
                a_paste.setEnabled(bool(w.canPaste()))
                a_del.setEnabled(bool(w.hasSelectedText()))

                act = menu.exec(w.mapToGlobal(pos))
                if act == a_undo:
                    w.undo()
                elif act == a_redo:
                    w.redo()
                elif act == a_cut:
                    w.cut()
                elif act == a_copy:
                    w.copy()
                elif act == a_paste:
                    w.paste()
                elif act == a_del:
                    w.del_()
                elif act == a_all:
                    w.selectAll()

            w.customContextMenuRequested.connect(_show_menu)
        except Exception:
            # If anything goes wrong, keep default menu.
            pass

    def _render_preview(self, plan):
        # Ensure preview is visible (empty state hides it)
        self.empty_wrap.hide()
        self.preview.show()

        c = self._get_client_info()

        title = (plan.title or "").strip() or "Diyet Planı"
        start_ui = self._fmt_date_ui(plan.start_date)
        end_ui = self._fmt_date_ui(plan.end_date)
        date_range = start_ui if not end_ui else f"{start_ui} – {end_ui}"

        plan_text = (plan.plan_text or "").strip()
        notes_text = (plan.notes or "").strip()

        def esc(s: str) -> str:
            return html.escape(s or "", quote=True)

        # Header logo (clinic logo if provided, otherwise NutriNexus)
        logo_url = self._get_header_logo_url()
        if logo_url:
            logo_html = f'<img src="{logo_url}" height="32" />'
        else:
            logo_html = '<div style="font-weight:800; font-size:11pt; color:#233;">NutriNexus</div>'

        # ------------------- Parse plan text into meal sections -------------------
        def is_heading(line: str) -> bool:
            s = line.strip()
            if not s:
                return False
            if re.match(r"^\[[^\]]+\]$", s):
                return True
            if s.endswith(":"):
                return True
            if 1 <= len(s.split()) <= 4 and not s.startswith(("•", "-", "*")):
                return any(k in s.lower() for k in ("kahvalt", "öğle", "ogle", "akşam", "aksam", "ara öğün", "ara ogun", "snack"))
            return False

        def normalize_heading(line: str) -> str:
            s = line.strip()
            if re.match(r"^\[[^\]]+\]$", s):
                s = s[1:-1].strip()
            if s.endswith(":"):
                s = s[:-1].strip()
            return s

        def section_key(title: str) -> str:
            s = (title or "").lower()
            if "kahvalt" in s:
                return "kahvalti"
            if "öğle" in s or "ogle" in s:
                return "ogle"
            if "akşam" in s or "aksam" in s:
                return "aksam"
            if "ara" in s or "snack" in s:
                return "ara"
            return "diger"

        def is_list_item(line: str) -> bool:
            s = line.strip()
            return s.startswith(("•", "-", "*")) or bool(re.match(r"^\d+[\).]\s+", s))

        def split_food_amount(line: str) -> tuple[str, str]:
            s = (line or "").strip()
            if not s:
                return "", ""
            for sep in (" - ", " – ", " — ", " : ", ": "):
                if sep in s:
                    a, b = s.split(sep, 1)
                    return a.strip(), b.strip()
            m = re.search(r"\d", s)
            if m and m.start() > 1:
                left = s[:m.start()].strip(" -–—:\t")
                right = s[m.start():].strip()
                return left.strip(), right
            return s, ""

        sections = {
            "kahvalti": {"title": "Kahvaltı", "items": [], "paras": []},
            "ogle": {"title": "Öğle", "items": [], "paras": []},
            "aksam": {"title": "Akşam", "items": [], "paras": []},
            "ara": {"title": "Ara Öğünler", "items": [], "paras": []},
            "diger": {"title": "Diğer", "items": [], "paras": []},
        }
        current_key = None

        for raw in (plan_text.splitlines() if plan_text else []):
            line = raw.rstrip()
            if not line.strip():
                if current_key and sections[current_key]["paras"] and sections[current_key]["paras"][-1] != "":
                    sections[current_key]["paras"].append("")
                continue

            if is_heading(line):
                h = normalize_heading(line)
                current_key = section_key(h)
                continue

            if current_key is None:
                current_key = "ara"

            if is_list_item(line):
                s = re.sub(r"^(?:[•\-*]|\d+[\).])\s*", "", line.strip())
                sections[current_key]["items"].append(s)
            else:
                sections[current_key]["paras"].append(line.strip())

        # ------------------- Render (Qt-safe: TABLE + inline styles) --------------
        # QTextDocument/QTextBrowser supports a limited HTML/CSS subset.
        # For a stable, printable, "clinic document" look we rely on:
        # - TABLE based layout
        # - inline styles only
        # - fixed amount column (120px), food cell wraps (never clipped)
        PAPER_W = 880

        # Watermark handling
        # Qt stylesheets with background-image can be flaky on some Windows setups.
        # To make watermark loading deterministic, we build a large translucent pixmap
        # and set it as the QTextBrowser Base palette brush.
        wm_path = self._get_watermark_path()
        try:
            if getattr(self, 'preview', None) and wm_path:
                pm = QPixmap(wm_path)
                if not pm.isNull():
                    # Build a reusable "page sized" background (tiled by Qt if viewport is taller).
                    canvas_w, canvas_h = 1000, 1400
                    canvas = QPixmap(canvas_w, canvas_h)
                    canvas.fill(Qt.white)
                    p = QPainter(canvas)
                    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
                    p.setOpacity(0.08)  # subtle
                    # Scale watermark to a sane width while keeping aspect ratio
                    target_w = 520
                    wm_scaled = pm.scaledToWidth(target_w, Qt.SmoothTransformation)
                    x = (canvas_w - wm_scaled.width()) // 2
                    y = (canvas_h - wm_scaled.height()) // 2
                    p.drawPixmap(x, y, wm_scaled)
                    p.end()

                    pal = self.preview.palette()
                    pal.setBrush(QPalette.Base, QBrush(canvas))
                    self.preview.setPalette(pal)
                    self.preview.setAutoFillBackground(True)
        except Exception:
            pass

        def render_meal_section(sec_key: str) -> str:
            sec = sections[sec_key]
            meal_title = esc(sec["title"])
            items = sec["items"]
            paras = sec["paras"]

            empty = (not items) and (not any(p.strip() for p in paras))
            rows_html = []

            if empty:
                hint_map = {
                    "Kahvaltı": "Örn: Yumurta — 1 adet",
                    "Öğle": "Örn: Tavuk göğüs — 120 g",
                    "Akşam": "Örn: Yoğurt — 1 kase",
                    "Ara Öğünler": "Örn: Badem — 10 adet",
                }
                hint = esc(hint_map.get(sec["title"], "Örn: Tavuk — 120 g"))
                rows_html.append(
                    f"""<tr>
<td colspan="2" style="padding:12px 12px; color:#445; font-size:10pt;">
<div style="font-weight:600;">Bu öğün için içerik eklenmemiştir.</div>
<div style="margin-top:4px; color:#667;">{hint}</div>
</td>
</tr>"""
                )
            else:
                def add_line(line: str):
                    a, b = split_food_amount(line)
                    a = esc(a)
                    b = esc(b)
                    if not a and not b:
                        return
                    if b:
                        rows_html.append(
                            f"""<tr>
<td style="padding:7px 10px; vertical-align:top; border-bottom:1px solid #eef2f5; white-space:normal; word-wrap:break-word; word-break:break-word; font-weight:700; color:#0f172a;">
{a}
</td>
<td width="110" style="padding:7px 10px 7px 8px; vertical-align:top; text-align:right; padding-right:14px; border-bottom:1px solid #eef2f5; white-space:nowrap; font-weight:800; color:#111; border-left:1px solid #f0f2f5;">
{b}
</td>
</tr>"""
                        )
                    else:
                        rows_html.append(
                            f"""<tr>
<td colspan="2" style="padding:7px 10px; vertical-align:top; border-bottom:1px solid #eef2f5; white-space:normal; word-wrap:break-word; word-break:break-word; font-weight:700; color:#0f172a;">
{a}
</td>
</tr>"""
                        )

                for it in items:
                    add_line(it)
                for p in paras:
                    if p == "":
                        rows_html.append('<tr><td colspan="2" style="padding:4px 0;"></td></tr>')
                    else:
                        add_line(p)

            # Section wrapper (bordered, printable)
            return f"""
<table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #d7dde3; margin-top:12px;">

<tr>
<td align="center" style="padding:10px 12px; background:#f4f6f8; border-bottom:1px solid #d7dde3; border-left:4px solid #2f7d32;">
<span style="font-size:13.2pt; font-weight:900; color:#102A33;">{meal_title}</span>
</td>
</tr>
<tr>
<td style="padding:8px 18px 12px 18px;">
<table width="100%" cellpadding="0" cellspacing="0" style="table-layout:fixed; width:100%;">
<colgroup>
  <col />
  <col width="110" />
</colgroup>
<tr>
<td style="padding:6px 8px; background:#fafbfc; color:#445; font-size:9.4pt; font-weight:800; border-bottom:1px solid #eef2f5;">Besin</td>
<td width="110" style="padding:6px 14px 6px 8px; background:#fafbfc; color:#445; font-size:9.4pt; font-weight:800; text-align:right; border-bottom:1px solid #eef2f5; border-left:1px solid #f0f2f5;">Miktar</td>
</tr>
{''.join(rows_html)}
</table>
</td>
</tr>
</table>
"""

        meal_order = ["kahvalti", "ogle", "aksam", "ara"]
        meal_html = "".join(render_meal_section(k) for k in meal_order)
        if sections["diger"]["items"] or any(p.strip() for p in sections["diger"]["paras"]):
            meal_html += render_meal_section("diger")

        # ---- Client/plan meta (Qt-safe tables) ----------------------------------
        full_name = esc(c.get("full_name", "") or "")
        phone = esc(c.get("phone", "") or "")
        gender = esc(c.get("gender", "") or "")
        birth_raw = c.get("birth_date", "") or ""
        birth_fmt = ""
        try:
            if isinstance(birth_raw, (date, datetime)):
                birth_fmt = birth_raw.strftime("%d.%m.%Y")
            else:
                s = str(birth_raw).strip()
                if len(s) >= 10 and "-" in s[:10]:
                    birth_fmt = datetime.strptime(s[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
                elif len(s) >= 10 and "." in s[:10]:
                    birth_fmt = s[:10]
                else:
                    birth_fmt = s
        except Exception:
            birth_fmt = str(birth_raw) if birth_raw is not None else ""
        birth = esc(birth_fmt)
        active_flag = getattr(plan, "is_active_plan", None)
        if active_flag is None:
            active_flag = getattr(plan, "is_active", False)
        status_raw = getattr(plan, "status", "") or ""
        status = esc(status_raw) or ("Aktif" if active_flag else "Taslak")
        if active_flag:
            status = "Aktif"
        created_ui = ""
        try:
            created_ui = self._fmt_date_ui(getattr(plan, "created_at", None)) or ""
        except Exception:
            created_ui = ""

        # Small helpers
        def kv(label: str, value: str) -> str:
            if not value:
                value = "—"
            return f"""<tr>
<td style="padding:3px 0; color:#556; font-size:9.6pt; width:120px;">{esc(label)}</td>
<td style="padding:3px 0; color:#102A33; font-size:10.2pt;">{esc(value)}</td>
</tr>"""

        # Notes block
        safe_notes = esc(notes_text).replace("\n", "<br>")
        notes_block = ""
        if notes_text.strip():
            notes_block = f"""
<table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #d7dde3; margin-top:12px;">

<tr>
<td style="padding:8px 12px; background:#f4f6f8; border-bottom:1px solid #d7dde3;">
<span style="font-size:11pt; font-weight:700; color:#102A33;">Notlar</span>
</td>
</tr>
<tr>
<td style="padding:10px 12px; white-space:normal; word-wrap:break-word; word-break:break-word; font-size:10.2pt; color:#102A33;">
                {safe_notes}
</td>
</tr>
</table>
"""

        # ---- Final HTML ---------------------------------------------------------
        html_doc = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
</head>
<body style="margin:0; padding:0; font-family:'Segoe UI', Calibri, Arial, sans-serif; font-size:11pt; line-height:1.35; color:#102A33;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#F5F7FA;">
<tr>
<td align="center" style="padding:18px 12px 22px 12px;">

<!-- PAPER (Qt-safe shadow wrapper) -->
<table width="{PAPER_W + 12}" cellpadding="0" cellspacing="0" style="background:#E9EEF4; border:1px solid #d0d7df;">
<tr>
<td style="padding:6px;">

<table width="{PAPER_W}" cellpadding="0" cellspacing="0" style="background:#ffffff; border:1px solid #cfd6dd;">
<tr>
<td style="padding:20px 22px 16px 22px;">

<!-- HEADER -->
<table width="100%" cellpadding="0" cellspacing="0" style="border-bottom:2px solid #e0e6ec; padding-bottom:10px;">
<tr>
<td valign="top" style="padding:0 0 8px 0;">
{logo_html}
<div style="font-weight:900; font-size:16pt; margin-top:2px;">
{esc(title)}
</div>
<div style="font-size:10pt; color:#667; margin-top:4px;">
Tarih: <b>{esc(date_range)}</b>
</div>
</td>
<td valign="top" align="right" style="padding:0 0 8px 0; font-size:9.6pt; color:#667;">
<div>Oluşturma: {esc(created_ui) if created_ui else esc(start_ui)}</div>
<div style="margin-top:6px;">Durum:
  <span style="display:inline-block; padding:2px 8px; border:1px solid #cfd6dd; background:#f7f9fb; color:#233; font-weight:700;">
    {esc(status)}
  </span>
</div>
</td>
</tr>
</table>

<!-- META BLOCKS -->
<table width="100%" cellpadding="0" cellspacing="0" style="margin-top:12px;">
<tr>
<td valign="top" style="padding-right:10px;">

<table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #d7dde3;">
<tr><td style="padding:10px 12px; background:#f9fafb; border-bottom:1px solid #d7dde3; font-weight:700;">Danışan Bilgileri</td></tr>
<tr><td style="padding:10px 12px;">
<table width="100%" cellpadding="0" cellspacing="0">
{kv('Ad Soyad', full_name)}
{kv('Telefon', phone)}
{kv('Cinsiyet', gender)}
{kv('Doğum Tarihi', birth)}
</table>
</td></tr>
</table>

</td>
<td valign="top" style="width:260px;">

<table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #d7dde3;">
<tr><td style="padding:10px 12px; background:#f9fafb; border-bottom:1px solid #d7dde3; font-weight:700;">Plan Özeti</td></tr>
<tr><td style="padding:10px 12px; font-size:10.2pt; color:#102A33;">
<div><b>{esc(title)}</b></div>
<div style="margin-top:6px; color:#667;">Dönem: {esc(date_range)}</div>
</td></tr>
</table>

</td>
</tr>
</table>

<!-- MEALS -->
<div style="margin-top:14px;">
{meal_html}
</div>

{notes_block}

<!-- FOOTER -->
<table width="100%" cellpadding="0" cellspacing="0" style="margin-top:14px; border-top:1px solid #e0e6ec;">
<tr>
<td style="padding-top:10px; font-size:9.4pt; color:#667;">
Bu plan, danışanın kişisel hedefleri ve değerlendirmesi temel alınarak hazırlanmıştır.
</td>
<td align="right" style="padding-top:10px; font-size:9.4pt; color:#667;">
NutriNexus
</td>
</tr>
</table>

</td>
</tr>
</table>

</td>
</tr>
</table>

</td>
</tr>
</table>
<!-- /PAPER -->

</td>
</tr>
</table>
</body>
</html>
"""

        # Apply to preview widget (keep background neutral, avoid horizontal scroll)
        try:
            self.preview.setStyleSheet("QTextBrowser { background: #EEF2F5; border: none; }")
        except Exception:
            pass

        html_doc = self._prepare_print_html(html_doc)

        self.preview.setHtml(html_doc)

        # Cache for PDF export
        try:
            self._last_preview_html = html_doc
            self._last_preview_plan_id = getattr(plan, 'id', None)
        except Exception:
            self._last_preview_html = html_doc
            self._last_preview_plan_id = None


    def refresh(self):

        plans = self.svc.list_for_client(self.client_id)
        self._plans_cache = {p.id: p for p in plans}

        self.tbl.setRowCount(0)
        for p in plans:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)

            date_disp, date_tip = self._fmt_range_compact(p.start_date, p.end_date)

            it0 = QTableWidgetItem(date_disp if date_disp else "")
            it0.setToolTip(date_tip if date_tip else "")
            it0.setData(Qt.UserRole, p.id)
            it0.setData(ACTIVE_ROLE, bool(p.is_active_plan))

            it1 = QTableWidgetItem((p.title or "").strip())
            if p.title:
                it1.setToolTip(p.title)

            # Status chip (always visible)
            status_text = "Aktif" if p.is_active_plan else "Taslak"

            chip = QLabel(status_text)
            chip.setObjectName("StatusChip")
            chip.setProperty("state", "active" if p.is_active_plan else "draft")
            chip.setAlignment(Qt.AlignCenter)

            wrap = QWidget()
            wrap.setAttribute(Qt.WA_TranslucentBackground, True)
            wl = QHBoxLayout(wrap)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.setSpacing(0)
            wl.addStretch(1)
            wl.addWidget(chip)
            wl.addStretch(1)

            it2 = QTableWidgetItem("")  # for selection/highlight behavior
            it2.setToolTip(status_text)
            it2.setData(Qt.UserRole, status_text)

            # Active row emphasis (keep subtle; QSS handles selection)
            if p.is_active_plan:
                for it in (it0, it1, it2):
                    it.setBackground(Qt.transparent)
                    it.setForeground(Qt.black)

            self.tbl.setItem(r, 0, it0)
            self.tbl.setItem(r, 1, it1)
            self.tbl.setItem(r, 2, it2)
            self.tbl.setCellWidget(r, 2, wrap)
# Select first row by default for a strong "no empty space" UX
        if plans:
            self.tbl.selectRow(0)
        else:
            self._show_empty_preview()

    def _open_view(self):
        pid = self._selected_plan_id()
        if not pid:
            return
        plan = self.svc.get(pid)
        if not plan:
            return
        dlg = DietPlanDialog(self, conn=self.conn, title=plan.title, start_date=plan.start_date, end_date=plan.end_date,
                             plan_text=plan.plan_text, notes=plan.notes, mode='view')
        dlg.exec()

    def _add(self):
        dlg = DietPlanDialog(self, conn=self.conn, mode='edit')
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            self.svc.create(
                self.client_id,
                data.get('title', ''),
                data.get('start_date', ''),
                data.get('end_date') or '',
                data.get('plan_text', ''),
                data.get('notes', ''),
                make_active=True,
            )
            self.refresh()

    def _edit(self):
        pid = self._selected_plan_id()
        if not pid:
            QMessageBox.information(self, 'Bilgi', 'Lütfen bir plan seçin.')
            return
        plan = self.svc.get(pid)
        if not plan:
            QMessageBox.information(self, 'Bilgi', 'Plan bulunamadı.')
            return
        dlg = DietPlanDialog(self, conn=self.conn, title=plan.title, start_date=plan.start_date, end_date=plan.end_date,
                             plan_text=plan.plan_text, notes=plan.notes, mode='edit')
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            self.svc.update(
                pid,
                data.get('title', ''),
                data.get('start_date', ''),
                data.get('end_date') or '',
                data.get('plan_text', ''),
                data.get('notes', ''),
            )
            self.refresh()

    def _set_active(self):
        pid = self._selected_plan_id()
        if not pid:
            QMessageBox.information(self, "Bilgi", "Lütfen bir plan seçin.")
            return
        self.svc.set_active(pid)
        self.refresh()

    def _delete(self):
        pid = self._selected_plan_id()
        if not pid:
            QMessageBox.information(self, "Bilgi", "Lütfen bir plan seçin.")
            return
        # Lightweight confirmation (non-modal): small menu near the button
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: #ffffff; color: #222; border: 1px solid #cfcfcf; }"
            "QMenu::item { padding: 7px 18px; }"
            "QMenu::item:selected { background-color: #fcecec; }"
            "QMenu::separator { height: 1px; background: #e5e5e5; margin: 4px 8px; }"
        )
        act_confirm = menu.addAction("Sil")
        menu.addSeparator()
        act_cancel = menu.addAction("Vazgeç")

        chosen = menu.exec_(self.btn_del.mapToGlobal(QPoint(0, self.btn_del.height() + 2)))
        if chosen != act_confirm:
            return

        try:
            self.svc.soft_delete(pid)
            self.refresh()
            self._show_toast("Plan silindi.", ok=True)
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Plan silinemedi:\n{e}")
            self._show_toast("Silme işlemi başarısız.", ok=False)