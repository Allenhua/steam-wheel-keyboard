"""通过 Win32 SendInput 向当前焦点窗口注入按键 / 文字。"""
import ctypes
from ctypes import wintypes as wt

user32 = ctypes.windll.user32

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

ULONG_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]


class _U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("u", _U)]


user32.SendInput.argtypes = [wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wt.UINT

VK_SHIFT = 0x10
EXTENDED = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E,
            0x5B, 0x5C, 0x6F, 0xA3, 0xA5}


def _vk_event(vk, up):
    flags = KEYEVENTF_KEYUP if up else 0
    if vk in EXTENDED:
        flags |= KEYEVENTF_EXTENDEDKEY
    scan = user32.MapVirtualKeyW(vk, 0)
    i = INPUT(type=INPUT_KEYBOARD)
    i.u.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    return i


def _uni_event(code, up):
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    i = INPUT(type=INPUT_KEYBOARD)
    i.u.ki = KEYBDINPUT(0, code, flags, 0, 0)
    return i


def _send(events):
    if not events:
        return
    arr = (INPUT * len(events))(*events)
    user32.SendInput(len(events), arr, ctypes.sizeof(INPUT))


class Sender:
    def __init__(self, ascii_via_vk=False):
        self.ascii_via_vk = ascii_via_vk

    def text(self, s):
        ev = []
        for ch in s:
            if self.ascii_via_vk and ord(ch) < 128:
                r = user32.VkKeyScanW(ord(ch))
                vk, st = r & 0xFF, (r >> 8) & 0xFF
                if vk != 0xFF and st in (0, 1):
                    if st:
                        ev.append(_vk_event(VK_SHIFT, False))
                    ev += [_vk_event(vk, False), _vk_event(vk, True)]
                    if st:
                        ev.append(_vk_event(VK_SHIFT, True))
                    continue
            data = ch.encode("utf-16-le")
            for n in range(0, len(data), 2):
                code = data[n] | (data[n + 1] << 8)
                ev += [_uni_event(code, False), _uni_event(code, True)]
        _send(ev)

    def key(self, vk):
        _send([_vk_event(vk, False), _vk_event(vk, True)])

    def combo(self, vks):
        vks = list(vks)
        _send([_vk_event(v, False) for v in vks] +
              [_vk_event(v, True) for v in reversed(vks)])


class RecordingSink:
    """测试用：只记录，不真正发送。"""

    def __init__(self):
        self.out = []

    def text(self, s):
        self.out.append(("text", s))

    def key(self, vk):
        self.out.append(("key", vk))

    def combo(self, vks):
        self.out.append(("combo", tuple(vks)))
