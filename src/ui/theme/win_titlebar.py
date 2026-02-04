from __future__ import annotations
# Windows titlebar color helpers (best-effort)
import sys

def _is_win() -> bool:
    return sys.platform.startswith("win")

def apply_light_titlebar(widget, caption_rgb=(233, 238, 242)):
    """Try to force a light title bar on Windows even if OS is in dark mode.
    caption_rgb: (r,g,b) for caption color, best-effort on Windows 11+.
    Safe no-op on non-Windows.
    """
    if not _is_win():
        return
    try:
        import ctypes
        from ctypes import wintypes

        hwnd = int(widget.winId())
        dwmapi = ctypes.windll.dwmapi

        # 1) Disable immersive dark mode on title bar (attribute 20 or 19 depending on build)
        val = ctypes.c_int(0)
        for attr in (20, 19):
            try:
                dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), ctypes.c_int(attr),
                                            ctypes.byref(val), ctypes.sizeof(val))
            except Exception:
                pass

        # 2) Set caption color (Windows 11+). COLORREF is 0x00BBGGRR
        r, g, b = caption_rgb
        colorref = ctypes.c_int((b << 16) | (g << 8) | r)
        DWMWA_CAPTION_COLOR = 35
        try:
            dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), ctypes.c_int(DWMWA_CAPTION_COLOR),
                                        ctypes.byref(colorref), ctypes.sizeof(colorref))
        except Exception:
            pass
    except Exception:
        # best-effort; ignore
        return
