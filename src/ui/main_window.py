from PySide6.QtWidgets import (
    QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton,
    QStackedWidget, QSizePolicy, QSystemTrayIcon, QMenu, QMessageBox
)
from PySide6.QtGui import QPixmap, QIcon, QAction
from PySide6.QtCore import Qt, QSize, QTimer

from src.ui.screens.dashboard import DashboardScreen
from src.ui.screens.appointments import AppointmentsScreen
from src.ui.screens.clients import ClientsScreen
from src.ui.screens.foods import FoodsScreen
from src.ui.screens.templates import TemplatesScreen
from src.ui.screens.settings import SettingsScreen
from src.ui.client_detail_window import ClientDetailWindow
from src.ui.theme.win_titlebar import apply_light_titlebar
from src.ui.widgets.custom_titlebar import CustomTitleBar
from src.services.appointments_service import AppointmentsService
from src.services.settings_service import SettingsService

class MainWindow(QMainWindow):
    def __init__(self, state, log):
        super().__init__()
        self.state = state
        self.log = log

        self.setWindowTitle("NutriNexus v1.3.0 — Klinik Danışan Yönetim Sistemi")
        # Make native titlebar light on Windows (best-effort)
        QTimer.singleShot(0, lambda: apply_light_titlebar(self))
        self.setMinimumSize(1200, 720)

        # Root layout
        root = QWidget()
                # Frameless window + custom title bar (kurumsal üst bar)
        try:
            self.setWindowFlag(Qt.FramelessWindowHint, True)
        except Exception:
            pass
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0,0,0,0)
        v.setSpacing(0)
        tb = CustomTitleBar(self, title='NutriNexus', logo_path='src/assets/logo.png', show_maximize=True)
        v.addWidget(tb)
        v.addWidget(root)
        self.setCentralWidget(container)

        main = QHBoxLayout(root)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # Sidebar
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(240)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(14, 14, 14, 14)
        sb.setSpacing(10)

        # Brand (kurumsal görünüm: sadece logo)
        brand_frame = QFrame()
        brand_frame.setObjectName("SidebarBrand")
        brand_frame.setFixedHeight(78)
        brand = QHBoxLayout(brand_frame)
        brand.setContentsMargins(6, 6, 6, 6)

        logo = QLabel()
        logo.setObjectName("SidebarLogo")
        # Logo brand alanında tam ortalı dursun
        logo.setAlignment(Qt.AlignCenter)
        try:
            pix = QPixmap("src/assets/logo.png")
            # Logoyu sol üst alana daha dolu oturt (aspect ratio korunur)
            logo.setPixmap(pix.scaled(196, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception:
            pass
        brand.addStretch(1)
        brand.addWidget(logo)
        brand.addStretch(1)
        sb.addWidget(brand_frame)

        sb.addSpacing(6)

        # Nav buttons
        # İkon + yazı altta (referans görseldeki gibi). Başlıklarla uyumlu özel ikonlar.
        self.btn_dashboard = self._nav_button("Dashboard", self._asset_icon_svg("dashboard"))
        self.btn_appointments = self._nav_button("Randevularım", self._asset_icon_svg("appointments"))
        self.btn_clients = self._nav_button("Danışanlar", self._asset_icon_svg("clients"))
        self.btn_foods = self._nav_button("Besinler", self._asset_icon_svg("foods"))
        self.btn_templates = self._nav_button("Şablonlar", self._asset_icon_svg("templates"))
        self.btn_settings = self._nav_button("Ayarlar", self._asset_icon_svg("settings"))

        # Nav container: sol paneli boydan boya daha dengeli doldursun
        nav_container = QFrame()
        nav_container.setObjectName("SidebarNav")
        navl = QVBoxLayout(nav_container)
        navl.setContentsMargins(0, 0, 0, 0)
        navl.setSpacing(10)

        nav_buttons = [
            self.btn_dashboard,
            self.btn_appointments,
            self.btn_clients,
            self.btn_foods,
            self.btn_templates,
            self.btn_settings,
        ]
        for b in nav_buttons:
            # Boydan boya dolsun; ikon+yazı için yeterli yükseklik
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            navl.addWidget(b, 1)

        sb.addWidget(nav_container, 1)

        # User chip
        chip = QLabel("Admin")
        chip.setObjectName("UserChip")
        sb.addWidget(chip)

        main.addWidget(sidebar)

        # Content
        content = QFrame()
        content.setObjectName("Content")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(18, 18, 18, 18)
        cl.setSpacing(12)

        # Topbar
        topbar = QFrame()
        topbar.setObjectName("Topbar")
        tl = QHBoxLayout(topbar)
        tl.setContentsMargins(14, 10, 14, 10)

        self.breadcrumb_icon = QLabel()
        self.breadcrumb_icon.setObjectName("BreadcrumbIcon")
        self.breadcrumb_icon.setFixedSize(20, 20)
        self.breadcrumb_icon.setScaledContents(True)
        tl.addWidget(self.breadcrumb_icon)

        self.breadcrumb = QLabel("Dashboard")
        self.breadcrumb.setObjectName("Breadcrumb")
        tl.addWidget(self.breadcrumb)
        tl.addStretch(1)

        cl.addWidget(topbar)

        self.stack = QStackedWidget()
        self.pages = {}

        # Pages
        self._add_page("Dashboard", DashboardScreen(state=state, log=log, open_client_detail_cb=self.open_client_detail))
        self._add_page("Randevularım", AppointmentsScreen(conn=state.conn, log=log))
        self._add_page("Danışanlar", ClientsScreen(state=state, log=log, open_client_detail_cb=self.open_client_detail))
        # FoodsScreen requires DB connection (Sprint 4.8)
        self._add_page("Besinler", FoodsScreen(conn=state.conn, log=log))
        self._add_page("Şablonlar", TemplatesScreen(conn=state.conn, log=log))
        self._add_page("Ayarlar", SettingsScreen(state=state, log=log))

        cl.addWidget(self.stack)

        main.addWidget(content)

        # In-app appointment reminders (Sprint 6.0.3)
        self._init_appointment_reminders()

        # Nav events
        self.btn_dashboard.clicked.connect(lambda: self.navigate("Dashboard"))
        self.btn_appointments.clicked.connect(lambda: self.navigate("Randevularım"))
        self.btn_clients.clicked.connect(lambda: self.navigate("Danışanlar"))
        self.btn_foods.clicked.connect(lambda: self.navigate("Besinler"))
        self.btn_templates.clicked.connect(lambda: self.navigate("Şablonlar"))
        self.btn_settings.clicked.connect(lambda: self.navigate("Ayarlar"))

        self.navigate("Dashboard")

    def open_client_detail(self, client: dict):
        win = ClientDetailWindow(client=client, state=self.state, log=self.log)
        win.showMaximized()
        # keep reference
        if not hasattr(self, "_child_windows"):
            self._child_windows = []
        self._child_windows.append(win)
        return win

    def _add_page(self, name: str, widget: QWidget):
        self.pages[name] = widget
        self.stack.addWidget(widget)

    def _nav_button(self, text: str, icon: QIcon) -> QToolButton:
        btn = QToolButton()
        btn.setText(text)
        btn.setIcon(icon)
        # Sidebar butonları cezbedici ve okunur olsun diye ikonları büyütüyoruz.
        btn.setIconSize(QSize(40, 40))
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        btn.setObjectName("NavBtn")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Butonlar sol panelin yüksekliğini doldurabilsin; max height koymuyoruz.
        btn.setMinimumHeight(112)
        return btn

    def _asset_icon_svg(self, name: str) -> QIcon:
        """Loads an SVG icon from assets/icons/svg. Icons are designed for sidebar (white stroke)."""
        from pathlib import Path
        base = Path(__file__).resolve().parents[1]  # src/ui -> src
        icon_path = base / "assets" / "icons" / "svg" / f"{name}.svg"
        return QIcon(str(icon_path))

    def _asset_icon(self, filename: str) -> QIcon:
        """Uygulama içi ikonları yükler."""
        return QIcon(f"src/assets/icons/{filename}")

    def navigate(self, name: str):
        if name not in self.pages:
            return
        self.breadcrumb.setText(name)
        self.stack.setCurrentWidget(self.pages[name])
        # active state
        for b in [self.btn_dashboard, self.btn_appointments, self.btn_clients, self.btn_foods, self.btn_templates, self.btn_settings]:
            b.setProperty("active", b.text() == name)
            b.style().unpolish(b)
            b.style().polish(b)

    # ------------------------------------------------------------
    # Randevu hatırlatıcıları (uygulama açıkken)
    # ------------------------------------------------------------
    def _init_appointment_reminders(self):
        """Uygulama çalışırken yaklaşan randevular için tray bildirimi gönderir.

        Notlar:
        - Uygulama kapalıyken bildirim göndermez (Windows servis/scheduler gerekir).
        - Bildirim spam olmasın diye DB'de appointments.notified alanını kullanır.
        """
        try:
            self._appt_service = AppointmentsService(self.state.conn)
            self._settings = SettingsService(self.state.conn)
            # Bildirim varsayılanları (idempotent)
            self._settings.set_default("appointments.notify_enabled", "1")
            self._settings.set_default("appointments.notify_minutes_before", "0")
        except Exception as e:
            # DB yoksa uygulamayı düşürmeyelim.
            if getattr(self, "log", None):
                self.log.exception("Appointment reminders init failed: %s", e)
            return

        # Tray icon (Windows'ta kurumsal kullanım için ideal)
        try:
            self.tray = QSystemTrayIcon(self)
            icon = self.windowIcon()
            if icon is None or icon.isNull():
                icon = QIcon("src/assets/logo.png")
            self.tray.setIcon(icon)

            tray_menu = QMenu()
            act_open = QAction("NutriNexus'i Aç", self)
            act_open.triggered.connect(self.showNormal)
            tray_menu.addAction(act_open)

            act_quit = QAction("Çıkış", self)
            act_quit.triggered.connect(self.close)
            tray_menu.addAction(act_quit)

            self.tray.setContextMenu(tray_menu)
            self.tray.show()
        except Exception as e:
            # Tray yoksa da devam edelim.
            if getattr(self, "log", None):
                self.log.exception("Tray init failed: %s", e)
            self.tray = None

        # Bildirim penceresi tıklanırsa randevulara götürelim
        self._last_notified_appt = None
        if self.tray:
            self.tray.messageClicked.connect(self._on_reminder_message_clicked)

        # Periyodik kontrol
        self._reminder_timer = QTimer(self)
        self._reminder_timer.setInterval(30_000)  # 30 sn
        self._reminder_timer.timeout.connect(self._check_due_appointments)
        self._reminder_timer.start()

        # İlk açılışta hemen bir kontrol
        QTimer.singleShot(1500, self._check_due_appointments)

    def _check_due_appointments(self):
        try:
            # Ayarlardan oku (varsayılanlar _init_appointment_reminders içinde set ediliyor)
            enabled = 1
            minutes_before = 0
            try:
                enabled = int(self._settings.get_int("appointments.notify_enabled", 1))
                minutes_before = int(self._settings.get_int("appointments.notify_minutes_before", 0))
            except Exception:
                enabled = 1
                minutes_before = 0

            if enabled <= 0:
                return

            due = self._appt_service.due_appointments(window_sec=60, minutes_before=minutes_before)
        except Exception as e:
            if getattr(self, "log", None):
                self.log.exception("Reminder check failed: %s", e)
            return

        if not due:
            return

        # Bir seferde en yakını gösterelim
        ap = due[0]
        try:
            self._appt_service.mark_notified(ap.id)
        except Exception:
            # Bildirim göstersek bile mark_notified başarısız olursa spam olabilir;
            # bu yüzden hata alırsak bildirim de göstermeyelim.
            return

        self._last_notified_appt = ap
        title = "NutriNexus • Randevu Hatırlatma"
        msg = f"{ap.time or ''} — {ap.client_name or ''} • {(ap.title or 'Randevu')}"

        if self.tray:
            try:
                self.tray.showMessage(title, msg, QSystemTrayIcon.Information, 10_000)
            except Exception:
                pass

    def _on_reminder_message_clicked(self):
        # Bildirime tıklanınca Randevularım ekranına git.
        try:
            self.navigate("Randevularım")
        except Exception:
            pass