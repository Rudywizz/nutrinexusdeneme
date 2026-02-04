from __future__ import annotations

import sqlite3
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QFrame,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QDialog
)

from src.services.templates_service import TemplatesService
from src.ui.dialogs.themed_messagebox import ThemedMessageBox
from src.ui.dialogs.food_template_dialog import FoodTemplateDialog
from src.ui.dialogs.meal_template_dialog import MealTemplateDialog


class TemplatesScreen(QWidget):
    """Sprint 6.1.0 - Besin / Öğün şablonları (temel CRUD).

    Not: Bu sprintte amaç ürün bütünlüğü. Sprint 6.1.1'de Besin Tüketimi'ne
    tek tık 'şablondan ekle' entegrasyonunu yapacağız.
    """

    def __init__(self, conn: sqlite3.Connection | None = None, log=None):
        super().__init__()
        self.conn = conn
        self.log = log
        self.svc = TemplatesService(conn, log=log) if conn else None

        lay = QVBoxLayout(self)
        title = QLabel("Şablonlar")
        title.setObjectName("PageTitle")
        lay.addWidget(title)

        # Search bar
        top = QHBoxLayout()
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Ara: şablon adı / besin adı / içerik...")
        self.ed_search.textChanged.connect(self._refresh)
        top.addWidget(self.ed_search, 1)

        self.btn_refresh = QPushButton("Yenile")
        self.btn_refresh.setObjectName("SecondaryBtn")
        self.btn_refresh.clicked.connect(self._refresh)
        top.addWidget(self.btn_refresh)
        lay.addLayout(top)

        tabs = QTabWidget()
        tabs.setObjectName("InnerTabs")

        self.tab_food = self._build_food_tab()
        self.tab_meal = self._build_meal_tab()

        tabs.addTab(self.tab_food, "Besin Şablonları")
        tabs.addTab(self.tab_meal, "Öğün Şablonları")

        lay.addWidget(tabs, 1)

        self._refresh()

    # ---------------- UI Builders ----------------
    def _card(self) -> QFrame:
        f = QFrame()
        f.setObjectName("Card")
        return f

    def _build_food_tab(self) -> QWidget:
        card = self._card()
        cl = QVBoxLayout(card)

        btns = QHBoxLayout()
        self.btn_food_new = QPushButton("Yeni")
        self.btn_food_new.setObjectName("PrimaryBtn")
        self.btn_food_edit = QPushButton("Düzenle")
        self.btn_food_edit.setObjectName("SecondaryBtn")
        self.btn_food_del = QPushButton("Sil")
        self.btn_food_del.setObjectName("DangerBtn")

        self.btn_food_new.clicked.connect(self._food_new)
        self.btn_food_edit.clicked.connect(self._food_edit)
        self.btn_food_del.clicked.connect(self._food_delete)

        btns.addWidget(self.btn_food_new)
        btns.addWidget(self.btn_food_edit)
        btns.addWidget(self.btn_food_del)
        btns.addStretch(1)
        cl.addLayout(btns)

        self.tbl_food = QTableWidget(0, 4)
        self.tbl_food.setHorizontalHeaderLabels(["Şablon", "Besin", "Miktar", "Güncellendi"])
        self.tbl_food.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_food.setSelectionMode(QTableWidget.SingleSelection)
        self.tbl_food.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_food.cellDoubleClicked.connect(lambda r, c: self._food_edit())
        cl.addWidget(self.tbl_food, 1)

        return card

    def _build_meal_tab(self) -> QWidget:
        card = self._card()
        cl = QVBoxLayout(card)

        btns = QHBoxLayout()
        self.btn_meal_new = QPushButton("Yeni")
        self.btn_meal_new.setObjectName("PrimaryBtn")
        self.btn_meal_edit = QPushButton("Düzenle")
        self.btn_meal_edit.setObjectName("SecondaryBtn")
        self.btn_meal_del = QPushButton("Sil")
        self.btn_meal_del.setObjectName("DangerBtn")

        self.btn_meal_new.clicked.connect(self._meal_new)
        self.btn_meal_edit.clicked.connect(self._meal_edit)
        self.btn_meal_del.clicked.connect(self._meal_delete)

        btns.addWidget(self.btn_meal_new)
        btns.addWidget(self.btn_meal_edit)
        btns.addWidget(self.btn_meal_del)
        btns.addStretch(1)
        cl.addLayout(btns)

        self.tbl_meal = QTableWidget(0, 3)
        self.tbl_meal.setHorizontalHeaderLabels(["Şablon", "Özet", "Güncellendi"])
        self.tbl_meal.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_meal.setSelectionMode(QTableWidget.SingleSelection)
        self.tbl_meal.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_meal.cellDoubleClicked.connect(lambda r, c: self._meal_edit())
        cl.addWidget(self.tbl_meal, 1)

        return card

    # ---------------- Helpers ----------------
    def _selected_id(self, table: QTableWidget) -> str | None:
        sel = table.selectedItems()
        if not sel:
            return None
        # we store id in Qt.UserRole of first column
        item = table.item(table.currentRow(), 0)
        if not item:
            return None
        return item.data(Qt.UserRole)

    def _refresh(self):
        if not self.svc:
            return

        q = self.ed_search.text().strip()
        # Food templates
        foods = self.svc.list_food_templates(q=q)
        self.tbl_food.setRowCount(0)
        for r in foods:
            row = self.tbl_food.rowCount()
            self.tbl_food.insertRow(row)

            it0 = QTableWidgetItem(r.name)
            it0.setData(Qt.UserRole, r.id)
            self.tbl_food.setItem(row, 0, it0)

            self.tbl_food.setItem(row, 1, QTableWidgetItem(r.food_name))
            self.tbl_food.setItem(row, 2, QTableWidgetItem(f"{r.amount:g} {r.unit}"))
            self.tbl_food.setItem(row, 3, QTableWidgetItem(r.updated_at))

        self.tbl_food.resizeColumnsToContents()

        # Meal templates
        meals = self.svc.list_meal_templates(q=q)
        self.tbl_meal.setRowCount(0)
        for r in meals:
            row = self.tbl_meal.rowCount()
            self.tbl_meal.insertRow(row)

            it0 = QTableWidgetItem(r.name)
            it0.setData(Qt.UserRole, r.id)
            self.tbl_meal.setItem(row, 0, it0)

            summary = (r.content or "").replace("\n", " ").strip()
            if len(summary) > 60:
                summary = summary[:57] + "..."
            self.tbl_meal.setItem(row, 1, QTableWidgetItem(summary))
            self.tbl_meal.setItem(row, 2, QTableWidgetItem(r.updated_at))

        self.tbl_meal.resizeColumnsToContents()

    # ---------------- Food CRUD ----------------
    def _food_new(self):
        dlg = FoodTemplateDialog(self, title="Yeni Besin Şablonu")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        try:
            self.svc.upsert_food_template(tpl_id=None, **data)
        except Exception as e:
            ThemedMessageBox.warn(self, "Kaydedilemedi", str(e))
            return
        self._refresh()

    def _food_edit(self):
        tpl_id = self._selected_id(self.tbl_food)
        if not tpl_id:
            ThemedMessageBox.info(self, "Seçim Yok", "Lütfen bir şablon seç.")
            return
        # fetch selected row current values from table by reloading list and matching id
        all_rows = self.svc.list_food_templates(q=self.ed_search.text().strip())
        cur = next((x for x in all_rows if x.id == tpl_id), None)
        if not cur:
            self._refresh()
            return

        dlg = FoodTemplateDialog(self, title="Besin Şablonu Düzenle", initial={
            "name": cur.name, "food_name": cur.food_name, "amount": cur.amount, "unit": cur.unit, "note": cur.note
        })
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        try:
            self.svc.upsert_food_template(tpl_id=tpl_id, **data)
        except Exception as e:
            ThemedMessageBox.warn(self, "Kaydedilemedi", str(e))
            return
        self._refresh()

    def _food_delete(self):
        tpl_id = self._selected_id(self.tbl_food)
        if not tpl_id:
            ThemedMessageBox.info(self, "Seçim Yok", "Lütfen bir şablon seç.")
            return
        if not ThemedMessageBox.confirm(self, "Silinsin mi?", "Bu besin şablonu silinecek. Devam edilsin mi?"):
            return
        self.svc.delete_food_template(tpl_id)
        self._refresh()

    # ---------------- Meal CRUD ----------------
    def _meal_new(self):
        dlg = MealTemplateDialog(self, title="Yeni Öğün Şablonu")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        try:
            self.svc.upsert_meal_template(tpl_id=None, **data)
        except Exception as e:
            ThemedMessageBox.warn(self, "Kaydedilemedi", str(e))
            return
        self._refresh()

    def _meal_edit(self):
        tpl_id = self._selected_id(self.tbl_meal)
        if not tpl_id:
            ThemedMessageBox.info(self, "Seçim Yok", "Lütfen bir şablon seç.")
            return
        all_rows = self.svc.list_meal_templates(q=self.ed_search.text().strip())
        cur = next((x for x in all_rows if x.id == tpl_id), None)
        if not cur:
            self._refresh()
            return

        dlg = MealTemplateDialog(self, title="Öğün Şablonu Düzenle", initial={
            "name": cur.name, "content": cur.content
        })
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        try:
            self.svc.upsert_meal_template(tpl_id=tpl_id, **data)
        except Exception as e:
            ThemedMessageBox.warn(self, "Kaydedilemedi", str(e))
            return
        self._refresh()

    def _meal_delete(self):
        tpl_id = self._selected_id(self.tbl_meal)
        if not tpl_id:
            ThemedMessageBox.info(self, "Seçim Yok", "Lütfen bir şablon seç.")
            return
        if not ThemedMessageBox.confirm(self, "Silinsin mi?", "Bu öğün şablonu silinecek. Devam edilsin mi?"):
            return
        self.svc.delete_meal_template(tpl_id)
        self._refresh()
