import sys
import time
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from src.app.bootstrap import bootstrap
from src.ui.main_window import MainWindow

from src.ui.splash import PremiumSplash

from PySide6.QtCore import qInstallMessageHandler, QtMsgType

def _qt_msg_handler(mode, context, message):
    # Konsolu gereksiz dolduran font uyarısını bastıralım.
    # (Fonksiyonel bir sorun değil; bazı Windows tema/font kombinasyonlarında çıkabiliyor.)
    if "QFont::setPointSize" in message:
        return
    # Diğer mesajları standart şekilde yazdır
    try:
        sys.stderr.write(message + "\n")
    except Exception:
        pass


def load_qss(app: QApplication) -> None:
    try:
        with open("src/ui/theme/style.qss", "r", encoding="utf-8") as fp:
            app.setStyleSheet(fp.read())
    except Exception as exc:
        sys.stderr.write(f"Failed to load QSS: {exc}\n")

def apply_default_font(app: QApplication) -> None:
    # Bazı sistemlerde/temalarda point size -1 uyarıları görülebiliyor.
    # Net bir varsayılan font/size verelim.
    try:
        f = QFont("Segoe UI", 10)
        if f.pointSize() <= 0:
            f.setPointSize(10)
        app.setFont(f)
    except Exception as exc:
        sys.stderr.write(f"Failed to apply default font: {exc}\n")

def main():
    app = QApplication(sys.argv)
    qInstallMessageHandler(_qt_msg_handler)
    apply_default_font(app)
    load_qss(app)

    # Premium açılış splash (video yerine stabil animasyon)
    splash = None
    try:
        splash = PremiumSplash(logo_path="src/assets/nutrinexus_logo.png")
        splash.show()
        splash.play()
        app.processEvents()
    except Exception as exc:
        sys.stderr.write(f"Splash failed to start: {exc}\n")

    t0 = time.monotonic()
    state, log = bootstrap()

    win = MainWindow(state=state, log=log)
    # Ana pencereyi splash kapanana kadar göstermeyelim (arkadan açılıp üstte splash kalmasın).
    win.setWindowOpacity(0.0)
    win.showMaximized()

    if splash is not None:
        # Splash en az belirli bir süre ekranda kalsın.
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        remaining = max(0, splash.minimum_visible_ms - elapsed_ms)
        # Fade-out animasyonu event loop içinde düzgün çalışsın diye timer ile kapatıyoruz.
        from PySide6.QtCore import QTimer
        def _show_main_after_splash():
            try:
                win.setWindowOpacity(1.0)
                win.raise_()
                win.activateWindow()
            except Exception as exc:
                sys.stderr.write(f"Failed to show main window: {exc}\n")

        # Splash fade-out bitince ana pencereyi görünür yap.
        splash.finished.connect(_show_main_after_splash)

        QTimer.singleShot(int(remaining), splash.close_with_fade)
    else:
        win.setWindowOpacity(1.0)

    rc = app.exec()
    try:
        state.conn.close()
    except Exception:
        pass
    sys.exit(rc)

if __name__ == "__main__":
    main()
