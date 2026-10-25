"""Windows 窗口辅助：逐像素透明、不抢焦点、置顶、拖动、DPI、工作区、检测 Steam。"""
import ctypes
import subprocess
from ctypes import wintypes as wt

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
HWND_TOPMOST = -1
SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE, SWP_SHOWWINDOW = 0x10, 0x2, 0x1, 0x40
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
ULW_ALPHA = 0x2
AC_SRC_OVER, AC_SRC_ALPHA = 0, 1

user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wt.UINT]
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetDC.argtypes = [wt.HWND]
user32.GetDC.restype = wt.HDC
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.SelectObject.argtypes = [wt.HDC, wt.HANDLE]
gdi32.SelectObject.restype = wt.HANDLE


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
                ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


user32.UpdateLayeredWindow.argtypes = [wt.HWND, wt.HDC, ctypes.POINTER(wt.POINT), ctypes.POINTER(wt.SIZE),
                                       wt.HDC, ctypes.POINTER(wt.POINT), wt.COLORREF,
                                       ctypes.POINTER(BLENDFUNCTION), wt.DWORD]
user32.UpdateLayeredWindow.restype = wt.BOOL
gdi32.CreateDIBSection.argtypes = [wt.HDC, ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p),
                                   wt.HANDLE, wt.DWORD]
gdi32.CreateDIBSection.restype = wt.HBITMAP


def lower_priority():
    """降到"低于正常"优先级：游戏线程永远优先，键盘只吃空闲的 CPU。"""
    try:
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = wt.HANDLE
        k32.SetPriorityClass.argtypes = [wt.HANDLE, wt.DWORD]
        k32.SetPriorityClass.restype = wt.BOOL
        return bool(k32.SetPriorityClass(k32.GetCurrentProcess(), 0x00004000))   # BELOW_NORMAL_PRIORITY_CLASS
    except Exception:
        return False


def enable_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def work_area():
    """(x, y, w, h) 主屏去掉任务栏后的可用区域。"""
    r = wt.RECT()
    if user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0):
        return r.left, r.top, r.right - r.left, r.bottom - r.top
    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def virtual_screen():
    """(x, y, w, h) 所有显示器合起来的范围。"""
    return (user32.GetSystemMetrics(76), user32.GetSystemMetrics(77),
            user32.GetSystemMetrics(78), user32.GetSystemMetrics(79))


def window_pos(hwnd):
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top


def move_window(hwnd, x, y):
    user32.SetWindowPos(hwnd, HWND_TOPMOST, int(x), int(y), 0, 0, SWP_NOACTIVATE | SWP_NOSIZE)


def cursor_pos():
    p = wt.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def clamp_pos(x, y, w, h):
    """保证窗口至少有一块露在屏幕里（顶栏不会丢）。"""
    vx, vy, vw, vh = virtual_screen()
    x = max(vx - w + 160, min(x, vx + vw - 160))
    y = max(vy, min(y, vy + vh - 60))
    return x, y


def make_overlay(hwnd, x, y, w, h):
    """无边框 + 置顶 + 不激活(点击不会抢走目标窗口焦点) + 逐像素透明(由 Layered 绘制)。"""
    ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    ex |= WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)
    user32.SetWindowPos(hwnd, HWND_TOPMOST, x, y, w, h, SWP_NOACTIVATE | SWP_SHOWWINDOW)


class Layered:
    """把带透明通道的 pygame Surface 贴到分层窗口上（UpdateLayeredWindow，逐像素 alpha）。"""

    def __init__(self, hwnd, w, h):
        self.hwnd, self.w, self.h = hwnd, w, h
        self.hdc = gdi32.CreateCompatibleDC(None)
        bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        self.bits = ctypes.c_void_p()
        self.hbmp = gdi32.CreateDIBSection(self.hdc, ctypes.byref(bmi), 0, ctypes.byref(self.bits), None, 0)
        gdi32.SelectObject(self.hdc, self.hbmp)
        self.size = wt.SIZE(w, h)
        self.src = wt.POINT(0, 0)
        self.ok = bool(self.hbmp and self.bits.value)

    def close(self):
        try:
            gdi32.DeleteObject(self.hbmp)
            gdi32.DeleteDC(self.hdc)
        except Exception:
            pass
        self.ok = False

    def update(self, surf, opacity=1.0):
        if not self.ok:
            return False
        prem = surf.premul_alpha()
        raw = prem.get_buffer().raw
        if len(raw) != self.w * self.h * 4:
            return False
        ctypes.memmove(self.bits, raw, len(raw))
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, max(0, min(255, int(255 * opacity))), AC_SRC_ALPHA)
        return bool(user32.UpdateLayeredWindow(self.hwnd, None, None, ctypes.byref(self.size), self.hdc,
                                               ctypes.byref(self.src), 0, ctypes.byref(blend), ULW_ALPHA))


def show(hwnd, visible):
    user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE if visible else SW_HIDE)
    if visible:
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOACTIVATE | SWP_NOMOVE | SWP_NOSIZE)


# ---------------- 焦点（Steam 大屏幕模式需要） ----------------
user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.BringWindowToTop.argtypes = [wt.HWND]
user32.SetFocus.argtypes = [wt.HWND]
user32.IsWindow.argtypes = [wt.HWND]
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
_k32 = ctypes.windll.kernel32
_k32.OpenProcess.restype = wt.HANDLE
_k32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]


def foreground():
    return user32.GetForegroundWindow()


def window_process(hwnd):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = _k32.OpenProcess(0x1000, False, pid.value)
    name = ""
    if h:
        buf = ctypes.create_unicode_buffer(300)
        n = wt.DWORD(300)
        if _k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            name = buf.value.rsplit("\\", 1)[-1].lower()
        _k32.CloseHandle(h)
    return name


def is_big_picture(hwnd):
    """前台是否是 Steam 大屏幕模式：steamwebhelper 的 SDL 窗口，且基本铺满屏幕。"""
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    cls = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(hwnd, cls, 64)
    if cls.value != "SDL_app" or window_process(hwnd) != "steamwebhelper.exe":
        return False
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    return (r.right - r.left) >= sw * 0.9 and (r.bottom - r.top) >= sh * 0.9


def set_noactivate(hwnd, flag):
    ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    ex = (ex | WS_EX_NOACTIVATE) if flag else (ex & ~WS_EX_NOACTIVATE)
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)


def force_foreground(hwnd):
    """把 hwnd 设为前台窗口。临时挂接到当前前台线程的输入队列，绕过 Windows 的前台锁。"""
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return True
    me = _k32.GetCurrentThreadId()
    other = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = bool(other and other != me and user32.AttachThreadInput(me, other, True))
    try:
        user32.BringWindowToTop(hwnd)
        ok = bool(user32.SetForegroundWindow(hwnd))
        user32.SetFocus(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(me, other, False)
    return ok or user32.GetForegroundWindow() == hwnd


_VK_NAMES = {"ctrl": 0x11, "control": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B,
              "pause": 0x13, "break": 0x13, "scrolllock": 0x91, "scroll": 0x91, "insert": 0x2D, "ins": 0x2D,
              "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "space": 0x20, "tab": 0x09,
              "esc": 0x1B, "apps": 0x5D, "menu": 0x5D}


def parse_hotkey(text):
    """"ctrl+alt+k" / "pause" / "f13" -> 虚拟键码元组；无法识别返回 None。"""
    vks = []
    for part in str(text or "").lower().replace(" ", "").split("+"):
        if not part:
            continue
        if part in _VK_NAMES:
            vks.append(_VK_NAMES[part])
        elif len(part) == 1 and part.isalnum():
            vks.append(ord(part.upper()))
        elif part[0] == "f" and part[1:].isdigit() and 1 <= int(part[1:]) <= 24:
            vks.append(0x70 + int(part[1:]) - 1)
        else:
            return None
    return tuple(vks) or None


def combo_down(vks):
    return bool(vks) and all(key_down(v) for v in vks)


def key_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def process_running(name):
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH"],
                             capture_output=True, text=True, creationflags=0x08000000, timeout=5).stdout
        return name.lower() in out.lower()
    except Exception:
        return False
