"""Steam Controller 轮盘虚拟键盘 —— 入口。

用法:
  python main.py                 按 config.json（默认 auto：检测到 Steam 在运行就用 Steam 模式）
  python main.py --steam         Steam 模式（读取 Steam Input 提供的虚拟手柄 / 鼠标指针）
  python main.py --direct        直连模式（不依赖 Steam，SDL 直接读 Steam Controller / Deck）
  python main.py --screenshot a.png [--demo pinyin|abc|func]   仅渲染界面截图
"""
import json
import os
import subprocess
import sys
import time

VERSION = "1.1.0"

if getattr(sys, "frozen", False):
    BASE = os.path.dirname(sys.executable)
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from i18n import T, set_lang  # noqa: E402

CONFIG_PATH = os.path.join(BASE, "config.json")
DICT_PATH = os.path.join(BASE, "data", "dict.txt")
USER_PATH = os.path.join(BASE, "data", "user.json")

DEFAULT_CONFIG = {
    "mode": "auto",            # auto | steam | direct
    "lang": "auto",            # auto（跟随系统）| zh | en —— 界面语言
    "scale": 0,                # 0 = 按屏幕自动；也可填 1.0 / 1.5 / 2.0
    "position": "bottom",      # bottom | top
    "opacity": 0.96,           # 整体不透明度（0.3~1.0，越小越透）
    "bg_alpha": 0.80,          # 轮盘/按钮底色不透明度（越小越透明）
    "panel_alpha": 0.0,        # 整个键盘后面的大底板不透明度，0 = 完全没有底板
    "x": None, "y": None,      # 窗口位置；拖动 / 移动模式后会自动记住
    "focus_mode": "auto",      # auto: 下层是 Steam 大屏幕模式时键盘自己拿焦点 | always | never
    "debug": False,            # True: 把手柄原始数据写进 debug.log
    "ascii_via_vk": False,     # True: 英文字符用真实按键发送（部分游戏需要）
    "start_hidden": False,
    "toggle_hotkey": True,     # 是否启用下面两个键盘快捷键
    "hotkey_toggle": "ctrl+alt+k",   # 收起/呼出键盘；也可写单个键，如 "pause"、"f13"、"scrolllock"
    "hotkey_phone": "ctrl+alt+p",    # 手机扫码面板
    # 摇杆防误触（数值越大越"迟钝"、越不容易误输入）。字段含义见 README
    "wheel": {"enter": 0.70, "exit": 0.40, "dwell": 0.07, "cooldown": 0.15,
              "rest": 0.25, "group": 0.65},
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except FileNotFoundError:
        save_config(cfg)
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def arg_value(name):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def resolve_mode(cfg):
    from winutil import process_running
    mode = "steam" if "--steam" in sys.argv else "direct" if "--direct" in sys.argv else cfg["mode"]
    if mode == "auto":
        mode = "steam" if process_running("steam.exe") else "direct"
    return mode


def apply_sdl_hints(mode):
    os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"   # 窗口不在前台也要收到手柄输入
    os.environ["SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
    os.environ["SDL_WINDOW_NO_ACTIVATION_WHEN_SHOWN"] = "1"
    if mode == "steam":
        # 交给 Steam Input：读它模拟出的 XInput 虚拟手柄
        os.environ["SDL_GAMECONTROLLER_ALLOW_STEAM_VIRTUAL_GAMEPAD"] = "1"
        os.environ["SDL_JOYSTICK_HIDAPI_STEAM"] = "0"
        os.environ["SDL_JOYSTICK_HIDAPI_STEAMDECK"] = "0"
    else:
        # 绕开 Steam，SDL 直接读 Steam Controller / Steam Deck
        os.environ["SDL_JOYSTICK_HIDAPI_STEAM"] = "1"
        os.environ["SDL_JOYSTICK_HIDAPI_STEAMDECK"] = "1"
        os.environ["SDL_JOYSTICK_HIDAPI"] = "1"


class XInputPads:
    """直接读 XInput（Steam Input 的虚拟 Xbox 手柄走这条路），作为 SDL 之外的第二输入源。"""

    MASKS = {"up": 0x1, "down": 0x2, "left": 0x4, "right": 0x8, "start": 0x10, "back": 0x20,
             "l3": 0x40, "r3": 0x80, "lb": 0x100, "rb": 0x200,
             "a": 0x1000, "b": 0x2000, "x": 0x4000, "y": 0x8000}

    def __init__(self):
        import ctypes
        self.ok = False
        self.connected = [False] * 4
        self._last_scan = 0.0
        try:
            self.dll = ctypes.windll.LoadLibrary("xinput1_4.dll")
        except OSError:
            try:
                self.dll = ctypes.windll.LoadLibrary("xinput1_3.dll")
            except OSError:
                return

        class Gamepad(ctypes.Structure):
            _fields_ = [("buttons", ctypes.c_ushort), ("lt", ctypes.c_ubyte), ("rt", ctypes.c_ubyte),
                        ("lx", ctypes.c_short), ("ly", ctypes.c_short),
                        ("rx", ctypes.c_short), ("ry", ctypes.c_short)]

        class State(ctypes.Structure):
            _fields_ = [("packet", ctypes.c_ulong), ("pad", Gamepad)]

        self.State = State
        self.ctypes = ctypes
        self.ok = True

    def poll(self, now):
        axes, buttons = [0.0] * 6, set()
        if not self.ok:
            return axes, buttons
        rescan = now - self._last_scan > 1.0
        if rescan:
            self._last_scan = now
        for i in range(4):
            if not self.connected[i] and not rescan:
                continue
            st = self.State()
            self.connected[i] = self.dll.XInputGetState(i, self.ctypes.byref(st)) == 0
            if not self.connected[i]:
                continue
            g = st.pad
            vals = (g.lx / 32768.0, -g.ly / 32768.0, g.rx / 32768.0, -g.ry / 32768.0,
                    g.lt / 255.0, g.rt / 255.0)
            for n, v in enumerate(vals):
                if abs(v) > abs(axes[n]):
                    axes[n] = v
            for name, m in self.MASKS.items():
                if g.buttons & m:
                    buttons.add(name)
        return axes, buttons

    @property
    def count(self):
        return sum(self.connected)


class Pads:
    """打开所有手柄，合并成一份状态（任意一个手柄的输入都生效）。"""

    def __init__(self):
        import pygame
        from pygame._sdl2 import controller
        self.pg, self.ctl = pygame, controller
        controller.init()
        self.xinput = XInputPads()
        self.raw = ([0.0] * 6, [0.0] * 6)
        self.pads, self.count = [], -1
        self.names = []
        self.last_scan = 0.0
        BTN = {
            "a": pygame.CONTROLLER_BUTTON_A, "b": pygame.CONTROLLER_BUTTON_B,
            "x": pygame.CONTROLLER_BUTTON_X, "y": pygame.CONTROLLER_BUTTON_Y,
            "back": pygame.CONTROLLER_BUTTON_BACK, "start": pygame.CONTROLLER_BUTTON_START,
            "l3": pygame.CONTROLLER_BUTTON_LEFTSTICK, "r3": pygame.CONTROLLER_BUTTON_RIGHTSTICK,
            "lb": pygame.CONTROLLER_BUTTON_LEFTSHOULDER, "rb": pygame.CONTROLLER_BUTTON_RIGHTSHOULDER,
            "up": pygame.CONTROLLER_BUTTON_DPAD_UP, "down": pygame.CONTROLLER_BUTTON_DPAD_DOWN,
            "left": pygame.CONTROLLER_BUTTON_DPAD_LEFT, "right": pygame.CONTROLLER_BUTTON_DPAD_RIGHT,
        }
        self.btn = BTN
        self.AX = (pygame.CONTROLLER_AXIS_LEFTX, pygame.CONTROLLER_AXIS_LEFTY,
                   pygame.CONTROLLER_AXIS_RIGHTX, pygame.CONTROLLER_AXIS_RIGHTY,
                   pygame.CONTROLLER_AXIS_TRIGGERLEFT, pygame.CONTROLLER_AXIS_TRIGGERRIGHT)

    def invalidate(self):
        self.count = -1

    def rescan(self):
        for p in self.pads:
            try:
                p.quit()
            except Exception:
                pass
        self.pads, self.names = [], []
        try:
            n = self.ctl.get_count()
        except Exception:
            n = 0
        for i in range(n):
            try:
                if self.ctl.is_controller(i):
                    p = self.ctl.Controller(i)
                    self.pads.append(p)
                    self.names.append(str(getattr(p, "name", "") or self.ctl.name_forindex(i)))
            except Exception:
                pass
        self.count = n

    def poll(self, now):
        if now - self.last_scan > 1.0:
            self.last_scan = now
            try:
                if self.ctl.get_count() != self.count:
                    self.rescan()
            except Exception:
                pass
        axes = [0.0] * 6
        buttons = set()
        for p in self.pads:
            try:
                for n, a in enumerate(self.AX):
                    v = p.get_axis(a)
                    v = v / 32768.0 if isinstance(v, int) and abs(v) > 1 else float(v)
                    if n >= 4:
                        v = max(0.0, v)
                    if abs(v) > abs(axes[n]):
                        axes[n] = v
                for name, b in self.btn.items():
                    if p.get_button(b):
                        buttons.add(name)
            except Exception:
                pass
        xa, xb = self.xinput.poll(now)
        self.raw = (list(axes), list(xa))     # 调试用：SDL / XInput 各自的原始值
        if self.xinput.count > 0:
            # 有 XInput（Steam 虚拟手柄）就只用它：和 SDL 是同一个手柄，合并取最大值反而会把
            # SDL 偶发的单帧毛刺带进来（实测右摇杆会闪一下）
            return xa, set(xb)
        return axes, buttons


class DebugLog:
    """把各来源的原始摇杆数据写进 debug.log（config.json 里 "debug": true 时启用）。"""

    NAMES = ("lx", "ly", "rx", "ry", "lt", "rt")

    def __init__(self, path):
        self.f = open(path, "w", encoding="utf-8", buffering=1)
        self.t0 = time.time()
        self.last_row = 0.0
        self.last_sum = self.t0
        self.stats = {}
        self.f.write("# 列: 时间 | SDL: lx ly rx ry lt rt | XInput: lx ly rx ry lt rt | 按下的键\n")

    def sample(self, now, pads, axes, btn):
        sdl, xi = pads.raw
        for src, vals in (("sdl", sdl), ("xi", xi)):
            for name, v in zip(self.NAMES, vals):
                lo, hi = self.stats.get((src, name), (9.0, -9.0))
                self.stats[(src, name)] = (min(lo, v), max(hi, v))
        if now - self.last_row >= 0.05:
            self.last_row = now
            fmt = lambda v: " ".join(f"{x:+.2f}" for x in v)
            self.f.write(f"{now - self.t0:7.2f} | {fmt(sdl)} | {fmt(xi)} | {','.join(sorted(btn))}\n")
        if now - self.last_sum >= 2.0:
            self.last_sum = now
            parts = [f"{s}.{n}[{lo:+.2f},{hi:+.2f}]" for (s, n), (lo, hi) in sorted(self.stats.items())]
            self.f.write(f"# SUMMARY(2s) sdlpads={len(pads.pads)} names={pads.names} xinput={pads.xinput.count} "
                         + " ".join(parts) + "\n")
            self.stats = {}


class FocusBridge:
    """包住真正的 Sender。键盘自己握着焦点时（Steam 大屏幕模式），每次输出前把焦点瞬间还给目标窗口，
    发完再拿回来；没握焦点时直接发送，和以前完全一样。"""

    def __init__(self, sender, get_hwnd):
        import winutil
        self.w = winutil
        self.s = sender
        self.get_hwnd = get_hwnd
        self.active = False
        self.target = None

    def _deliver(self, fn, *a):
        if not self.active or not self.target or not self.w.user32.IsWindow(self.target):
            return fn(*a)
        me = self.get_hwnd()
        self.w.force_foreground(self.target)
        time.sleep(0.03)
        fn(*a)
        time.sleep(0.06)
        self.w.force_foreground(me)

    def text(self, s):
        self._deliver(self.s.text, s)

    def key(self, vk):
        self._deliver(self.s.key, vk)

    def combo(self, vks):
        self._deliver(self.s.combo, vks)


def make_demo(kb, demo):
    if demo == "pinyin":
        kb.mode, kb.group = 0, 3
        for ch in "nihao":
            kb.output_item(ch)
        kb.hover = 2
        kb.sel = 1
    elif demo == "abc":
        kb.mode, kb.group, kb.shift, kb.hover = 1, 4, True, 2
        kb.log = "Hello, world"
        kb.lx, kb.ly, kb.rx, kb.ry = -0.2, 0.8, 0.85, 0.1
    elif demo == "func":
        kb.mode, kb.group, kb.hover = 4, 1, 3
    else:
        kb.mode, kb.group = 2, 4
        kb.log = "你好，世界！"


def screenshot(path, k, demo, cfg):
    """离线渲染一张预览图（叠在浅色/深色棋盘上，方便看透明效果）。"""
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    import pygame
    from logic import Keyboard
    from pinyin_engine import PinyinEngine
    from sender import RecordingSink
    from ui import UI
    pygame.init()
    eng = PinyinEngine(DICT_PATH, None)
    eng.load()
    kb = Keyboard(RecordingSink(), eng)
    make_demo(kb, demo)
    ui = UI(k, cfg["bg_alpha"], cfg["panel_alpha"])
    canvas = pygame.Surface(ui.size, pygame.SRCALPHA)
    ov = None
    if demo == "phone":
        import segno
        url = "http://192.168.1.23:8765/?k=a1B2c3D4"
        ov = {"url": url, "matrix": [list(r) for r in segno.make(url, error="m").matrix],
              "clients": 1, "idx": 0, "n": 3, "error": ""}
    ui.draw(canvas, kb, T("Steam 模式") + " · Steam Controller · " + T("手机 {n} 台").format(n=1), time.time(), ov)
    bg = pygame.Surface(ui.size)
    for yy in range(0, ui.size[1], 24):
        for xx in range(0, ui.size[0], 24):
            c = (235, 235, 235) if ((xx // 24 + yy // 24) % 2) else (200, 205, 215)
            bg.fill(c, (xx, yy, 24, 24))
    bg.blit(canvas, (0, 0))
    pygame.image.save(bg, path)
    print("saved", path)


def restart_with_mode(mode):
    cfg = load_config()
    cfg["mode"] = mode
    save_config(cfg)
    args = [a for a in sys.argv[1:] if a not in ("--steam", "--direct")]
    exe = sys.executable
    cmd = [exe] + ([] if getattr(sys, "frozen", False) else [os.path.abspath(__file__)]) + args
    subprocess.Popen(cmd, cwd=BASE)
    sys.exit(0)


# 组合键：两个键同时按下触发动作；单独按时在"松开"才生效，避免组合时误触单键功能
CHORDS = (("l3", "r3", "hide"), ("lb", "rb", "move"))
CHORD_MEMBERS = {"l3", "r3", "lb", "rb"}


def run():
    if "--version" in sys.argv:
        print("Steam Wheel Keyboard", VERSION)
        return
    cfg = load_config()
    set_lang(arg_value("--lang") or cfg.get("lang", "auto"))
    if "--screenshot" in sys.argv:
        screenshot(arg_value("--screenshot"), float(arg_value("--scale") or 1.0),
                   arg_value("--demo") or "pinyin", cfg)
        return

    mode = resolve_mode(cfg)
    apply_sdl_hints(mode)

    import threading
    import pygame
    import winutil
    from logic import Keyboard
    from pinyin_engine import PinyinEngine
    from sender import Sender
    from phone_server import PhoneServer, apply_event
    from ui import UI

    winutil.enable_dpi_awareness()
    winutil.lower_priority()          # 永远让着游戏
    pygame.display.init()
    pygame.font.init()

    wx, wy, ww, wh = winutil.work_area()
    k = float(cfg["scale"] or 0)
    if k <= 0:
        # 默认：宽不超过屏幕 45%、高不超过 36%，4K 屏也不会铺满
        k = max(0.8, min(ww * 0.45 / 1000, wh * 0.36 / 480, 3.0))
    ui = UI(k, cfg["bg_alpha"], cfg["panel_alpha"])
    w, h = ui.size
    if cfg.get("x") is not None and cfg.get("y") is not None:
        x, y = winutil.clamp_pos(int(cfg["x"]), int(cfg["y"]), w, h)
    else:
        x = wx + (ww - w) // 2
        y = wy + wh - h - 12 if cfg["position"] == "bottom" else wy + 12
    os.environ["SDL_VIDEO_WINDOW_POS"] = f"{x},{y}"
    pygame.display.set_mode((w, h), pygame.NOFRAME)
    pygame.display.set_caption("Steam 轮盘键盘")
    hwnd = pygame.display.get_wm_info()["window"]
    winutil.make_overlay(hwnd, x, y, w, h)
    layered = winutil.Layered(hwnd, w, h)
    canvas = pygame.Surface((w, h), pygame.SRCALPHA)
    opacity = float(cfg["opacity"])

    # 词库放到后台线程加载，窗口先出来
    engine = PinyinEngine(DICT_PATH, USER_PATH)
    load_state = {"done": False, "ok": False}

    def bg_load():
        load_state["ok"] = engine.load()
        load_state["done"] = True

    threading.Thread(target=bg_load, daemon=True).start()

    bridge = FocusBridge(Sender(bool(cfg["ascii_via_vk"])), lambda: hwnd)
    kb = Keyboard(bridge, engine, cfg.get("wheel"))
    focus_mode = str(cfg.get("focus_mode", "auto")).lower()      # auto | always | never
    last_focus_check = 0.0
    pads = Pads()
    steam_up = winutil.process_running("steam.exe")
    kb.say("词库加载中…", time.time(), 60)

    visible = not cfg["start_hidden"]
    if not visible:
        winutil.show(hwnd, False)
    prev_btn, start_t, start_fired = set(), None, False
    last_btn = None
    chord_used = {c[2]: False for c in CHORDS}
    dbg = DebugLog(os.path.join(BASE, "debug.log")) if cfg.get("debug") else None
    hk_prev = False
    hk_toggle = winutil.parse_hotkey(cfg.get("hotkey_toggle", "ctrl+alt+k")) or winutil.parse_hotkey("ctrl+alt+k")
    hk_phone = winutil.parse_hotkey(cfg.get("hotkey_phone", "ctrl+alt+p")) or winutil.parse_hotkey("ctrl+alt+p")
    last_draw, last_status, status = 0.0, "", ""
    last_t = time.time()
    last_active = last_t
    clock = pygame.time.Clock()

    moving = False
    drag = None          # (起始鼠标位置, 起始窗口位置)
    pos = [float(x), float(y)]

    def save_pos():
        px, py = winutil.window_pos(hwnd)
        cfg["x"], cfg["y"] = int(px), int(py)
        save_config(cfg)

    def set_moving(flag):
        nonlocal moving
        moving = flag
        kb.moving = flag
        kb.dirty = True
        if not flag:
            save_pos()

    def rescale(new_k):
        """改变窗口大小（保持左上角位置不变），并记住。"""
        nonlocal k, ui, w, h, hwnd, layered, canvas
        new_k = max(0.5, min(4.0, new_k))
        if abs(new_k - k) < 1e-3:
            return
        px, py = winutil.window_pos(hwnd)
        k = new_k
        ui = UI(k, cfg["bg_alpha"], cfg["panel_alpha"])
        w, h = ui.size
        px, py = winutil.clamp_pos(px, py, w, h)
        os.environ["SDL_VIDEO_WINDOW_POS"] = f"{px},{py}"
        pygame.display.set_mode((w, h), pygame.NOFRAME)
        hwnd = pygame.display.get_wm_info()["window"]
        winutil.make_overlay(hwnd, px, py, w, h)
        layered.close()
        layered = winutil.Layered(hwnd, w, h)
        canvas = pygame.Surface((w, h), pygame.SRCALPHA)
        pos[0], pos[1] = float(px), float(py)
        cfg["scale"] = round(k, 3)
        save_config(cfg)
        kb.dirty = True

    def need_focus(fg):
        if focus_mode == "never" or not fg or fg == hwnd:
            return False
        return focus_mode == "always" or winutil.is_big_picture(fg)

    def grab_focus(target):
        """Steam 只把手柄交给"前台"的程序：大屏幕模式在前台时，键盘必须自己拿到焦点才收得到手柄。"""
        bridge.target, bridge.active = target, True
        winutil.set_noactivate(hwnd, False)
        winutil.force_foreground(hwnd)
        if dbg:
            dbg.f.write(f"# FOCUS grab target={target} ok={winutil.foreground() == hwnd}" + chr(10))

    def release_focus():
        if not bridge.active:
            return
        bridge.active = False
        winutil.set_noactivate(hwnd, True)
        if bridge.target and winutil.user32.IsWindow(bridge.target):
            winutil.force_foreground(bridge.target)
        if dbg:
            dbg.f.write("# FOCUS release" + chr(10))

    def set_visible(flag):
        nonlocal visible
        visible = flag
        if not flag and moving:
            set_moving(False)
        if not flag:
            release_focus()
        winutil.show(hwnd, flag)
        if flag:
            fg = winutil.foreground()
            if need_focus(fg):
                grab_focus(fg)
        kb.dirty = True

    # ---- 手机扫码远程输入 ----
    phone = None
    overlay = False
    qr_cache = {}
    last_clients, last_pver = 0, 0
    pk_prev = False

    def make_qr(url):
        if url not in qr_cache:
            try:
                import segno
                qr_cache.clear()
                qr_cache[url] = [list(r) for r in segno.make(url, error="m").matrix]
            except Exception:
                qr_cache[url] = None
        return qr_cache[url]

    def toggle_phone():
        """打开二维码面板（必要时启动服务）；面板已打开则隐藏。"""
        nonlocal phone, overlay
        if overlay:
            overlay = False
        else:
            if phone is None or not phone.running:
                phone = PhoneServer()
                if not phone.start():
                    kb.say(phone.error or "手机输入启动失败", time.time(), 5)
                    phone = None
                    return
            overlay = True
            if dbg:
                dbg.f.write(f"# PHONE {phone.url} addrs={phone.addrs}\n")
            if not visible:
                set_visible(True)
        kb.dirty = True

    def stop_phone():
        nonlocal phone, overlay
        if phone:
            phone.stop()
        phone, overlay = None, False
        kb.say("手机输入已停止", time.time(), 2)

    def overlay_info():
        url = phone.url
        return {"url": url, "matrix": make_qr(url) if phone.ready else None, "ready": phone.ready,
                "clients": phone.clients(),
                "idx": phone.idx % max(1, len(phone.addrs)), "n": len(phone.addrs), "error": ""}

    try:
        while True:
            now = time.time()
            dt = min(0.1, now - last_t)
            last_t = now
            for e in pygame.event.get():
                if e.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEWHEEL):
                    last_active = now
                if dbg and e.type not in (pygame.CONTROLLERAXISMOTION, pygame.JOYAXISMOTION):
                    dbg.f.write(f"# EV {pygame.event.event_name(e.type)} {getattr(e, 'pos', '')}\n")
                if e.type == pygame.QUIT:
                    raise SystemExit
                if e.type in (pygame.CONTROLLERDEVICEADDED, pygame.CONTROLLERDEVICEREMOVED):
                    pads.invalidate()
                elif e.type == pygame.WINDOWLEAVE:
                    kb.mouse_hover = -1
                    kb.dirty = True
                elif e.type == pygame.MOUSEWHEEL and visible:
                    rescale(k * (1.08 if e.y > 0 else 1 / 1.08))
                elif e.type == pygame.MOUSEMOTION and visible:
                    hit = ui.hit(e.pos)
                    mh = hit[1] if hit and hit[0] == "rsec" else -1
                    if hit and hit[0] == "lsec" and hit[1] != kb.group and drag is None:
                        kb.group, kb.dirty = hit[1], True
                    if mh != kb.mouse_hover:
                        kb.mouse_hover, kb.dirty = mh, True
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and visible:
                    hit = ui.hit(e.pos)
                    if dbg:
                        dbg.f.write(f"# MOUSEDOWN pos={e.pos} hit={hit}\n")
                    if not hit:
                        continue
                    kind, v = hit
                    if kind == "drag":
                        drag = (winutil.cursor_pos(), winutil.window_pos(hwnd))
                    elif kind == "lsec":
                        kb.group, kb.dirty = v, True
                    elif kind == "rsec":
                        kb.commit_slot(v)
                    elif kind == "tab":
                        kb.set_mode(v)
                    elif kind == "cand":
                        kb.choose(kb.page * 8 + v)
                    elif kind == "ov":
                        if v == "next" and phone:
                            phone.next_addr()
                        elif v == "hide":
                            overlay = False
                        elif v == "stop":
                            stop_phone()
                    elif kind == "btn":
                        if v == "phone":
                            toggle_phone()
                        elif v == "hide":
                            set_visible(False)
                        elif v == "move":
                            set_moving(not moving)
                        elif v == "shift":
                            kb.shift = not kb.shift
                        elif v == "caps":
                            kb.button("l3", now)
                        else:
                            kb.button({"space": "a", "bksp": "x", "enter": "y", "esc": "b"}[v], now)
                    kb.dirty = True

            # 鼠标拖动顶栏移动窗口
            if drag is not None:
                if winutil.key_down(0x01):
                    (cx0, cy0), (wx0, wy0) = drag
                    cx, cy = winutil.cursor_pos()
                    nx, ny = winutil.clamp_pos(wx0 + cx - cx0, wy0 + cy - cy0, w, h)
                    winutil.move_window(hwnd, nx, ny)
                    pos = [float(nx), float(ny)]
                else:
                    drag = None
                    save_pos()

            if load_state["done"] and load_state.get("announced") is None:
                load_state["announced"] = True
                kb.toast_until = 0
                if load_state["ok"]:
                    if kb.buf:
                        kb.refresh()
                    kb.say("词库已加载", now, 1.2)
                else:
                    kb.say("未找到拼音词库：请先运行  python build_dict.py --download", now, 12)

            axes, btn = pads.poll(now)
            if btn or max(abs(axes[0]), abs(axes[1]), abs(axes[2]), abs(axes[3]), axes[4], axes[5]) > 0.12:
                last_active = now
            if dbg:
                dbg.sample(now, pads, axes, btn)
            pressed = btn - prev_btn
            released = prev_btn - btn
            prev_btn = btn

            # ---- 组合键 ----
            fire = set(pressed) - CHORD_MEMBERS
            actions = []
            for a, b, act in CHORDS:
                if a in btn and b in btn and not chord_used[act]:
                    chord_used[act] = True
                    actions.append(act)
            for n in CHORD_MEMBERS & released:
                if not any(chord_used[act] for a, b, act in CHORDS if n in (a, b)):
                    fire.add(n)
            for a, b, act in CHORDS:
                if a not in btn and b not in btn:
                    chord_used[act] = False

            toggle = "back" in pressed or "hide" in actions
            if cfg["toggle_hotkey"]:
                hk = winutil.combo_down(hk_toggle)
                toggle = toggle or (hk and not hk_prev)
                hk_prev = hk
            if toggle:
                set_visible(not visible)
            if "move" in actions and visible and not overlay:
                set_moving(not moving)
            if cfg["toggle_hotkey"]:
                pk = winutil.combo_down(hk_phone)
                if pk and not pk_prev:
                    toggle_phone()
                pk_prev = pk
            for cmd in kb.commands:
                if cmd == "phone":
                    toggle_phone()
            kb.commands.clear()

            # 手机发来的文字 / 按键：在主线程里注入（键盘隐藏时也生效）
            if phone and phone.running:
                for ev in phone.drain():
                    last_active = now
                    try:
                        shown = apply_event(kb.sink, ev)
                    except Exception:
                        shown = ""
                    if shown:
                        kb.log = (kb.log + shown)[-30:]
                    kb.dirty = True
                nc = phone.clients()
                if nc != last_clients or phone.version != last_pver:
                    last_clients, last_pver, kb.dirty = nc, phone.version, True

            # 长按 Start 1.5 秒：切换 Steam / 直连模式并重启
            if "start" in btn:
                start_t = start_t or now
                if not start_fired and now - start_t > 1.5:
                    start_fired = True
                    restart_with_mode("direct" if mode == "steam" else "steam")
            else:
                start_t, start_fired = None, False

            if visible and moving:
                # ---- 移动窗口模式：摇杆移动，十字键贴边，Y 居中，A/B 确定 ----
                vx = axes[0] + axes[2]
                vy = axes[1] + axes[3]
                m = (vx * vx + vy * vy) ** 0.5
                if m > 0.2:
                    sp = 1000.0 * min(1.0, m) * dt / max(m, 1e-6)
                    pos[0] += vx * sp
                    pos[1] += vy * sp
                if "up" in pressed:
                    pos[1] = wy + 8
                if "down" in pressed:
                    pos[1] = wy + wh - h - 8
                if "left" in pressed:
                    pos[0] = wx + 8
                if "right" in pressed:
                    pos[0] = wx + ww - w - 8
                if "y" in pressed:
                    pos[0] = wx + (ww - w) / 2
                if "lb" in fire:
                    rescale(k / 1.12)
                if "rb" in fire:
                    rescale(k * 1.12)
                pos[0], pos[1] = winutil.clamp_pos(pos[0], pos[1], w, h)
                winutil.move_window(hwnd, pos[0], pos[1])
                if pressed & {"a", "b", "start"}:
                    set_moving(False)
            elif visible and overlay:
                # ---- 二维码面板：X 换地址，A/B 隐藏，Y 停止手机输入 ----
                if "x" in pressed and phone:
                    phone.next_addr()
                    kb.dirty = True
                if pressed & {"a", "b"}:
                    overlay = False
                    kb.dirty = True
                if "y" in pressed:
                    stop_phone()
            elif visible:
                for name in fire:
                    if name not in ("back", "start"):
                        kb.button_down(name, now)
                for name in released:
                    kb.button_up(name)
                kb.update_axes(axes[0], axes[1], axes[2], axes[3], axes[4], axes[5], now)
                kb.tick(now)

            # 大屏幕模式：键盘显示期间保持焦点；被抢走（比如大屏幕自己跳回前台）就拿回来
            if visible and now - last_focus_check > 0.4:
                last_focus_check = now
                fg = winutil.foreground()
                if fg != hwnd:
                    if bridge.active and (fg == bridge.target or winutil.is_big_picture(fg)):
                        grab_focus(fg)
                    elif not bridge.active and need_focus(fg):
                        grab_focus(fg)
                    elif bridge.active and fg:
                        bridge.active = False            # 用户切到了别的程序：不再抢焦点
                        winutil.set_noactivate(hwnd, True)

            if visible:
                if pressed:
                    last_btn = (sorted(pressed)[0].upper(), now)
                have_pad = bool(pads.pads) or pads.xinput.count > 0
                kb.banner = "" if have_pad else \
                    "未检测到手柄 — 请从 Steam 启动本程序（见 README），现在可用触摸板/鼠标点选"
                label = T("Steam 模式") if mode == "steam" else T("直连模式")
                dev = "、".join(pads.names) if pads.names else (
                    T("XInput 手柄 ×{n}").format(n=pads.xinput.count) if pads.xinput.count else T("无手柄"))
                status = f"{label} · {dev}"
                if phone and phone.running:
                    status += " · " + T("手机 {n} 台").format(n=phone.clients())
                if last_btn and now - last_btn[1] < 1.5:
                    status += " · " + T("按下 {b}").format(b=last_btn[0])
                    kb.dirty = True
                if status != last_status:
                    last_status, kb.dirty = status, True
                if kb.toast and now >= kb.toast_until:
                    kb.toast, kb.dirty = "", True          # 提示到时间了，重画一次把它去掉
                if (kb.dirty and now - last_draw >= 1 / 60) or now - last_draw > 15.0:
                    ui.draw(canvas, kb, status, now, overlay_info() if (overlay and phone) else None)
                    layered.update(canvas, opacity)
                    kb.dirty, last_draw = False, now
            # 省电/省 CPU：有操作时 120Hz，空闲 1.5 秒后降到 30Hz，隐藏时 20Hz
            clock.tick(120 if (visible and now - last_active < 1.5) else (30 if visible else 20))
    except SystemExit:
        pass
    finally:
        try:
            release_focus()
        except Exception:
            pass
        if phone:
            phone.stop()
        engine.save()
        if dbg:
            dbg.f.close()
        pygame.quit()


if __name__ == "__main__":
    run()
