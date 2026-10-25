"""键盘状态机：摇杆 / 按键 -> 轮盘选择、拼音候选、输出。与界面和手柄无关，可单独测试。"""
import math

from layouts import (MODES, Act, label_of, VK_BACK, VK_TAB, VK_RETURN, VK_ESCAPE,
                     VK_SPACE, VK_LEFT, VK_UP, VK_RIGHT, VK_DOWN)

PAGE = 8
REPEAT = {"x", "up", "down", "left", "right"}

# 防误触参数（可在 config.json 的 "wheel" 里覆盖）
DEFAULT_TUNE = {
    "enter": 0.70,      # 右摇杆推到这么深才算"指向"某个字符
    "exit": 0.40,       # 回到这么浅算"松开"，此时输入
    "dwell": 0.07,      # 同一方向至少停留这么久（秒）才有效；一扫而过不输入
    "cooldown": 0.15,   # 输入一个字后的冷却时间（秒）
    "rest": 0.25,       # 输入后摇杆要回到这个幅度以内并稳定，才能输入下一个（防回弹过冲）
    "group": 0.65,      # 左摇杆推到这么深才切换"组"
    "group_dwell": 0.05,
}


def sector(x, y):
    """摇杆 (x, y) -> 0..7，0 为正上方，顺时针。"""
    return int(round(math.atan2(x, -y) / (math.pi / 4))) % 8


class Keyboard:
    def __init__(self, sink, engine, tune=None):
        self.sink = sink
        self.engine = engine
        self.tune = dict(DEFAULT_TUNE)
        if tune:
            self.tune.update({k: float(v) for k, v in tune.items() if k in DEFAULT_TUNE})
        self.mode = 0
        self.group = 0
        self.hover = -1          # 摇杆指向的右轮槽位
        self.mouse_hover = -1    # 鼠标指向的右轮槽位
        self._h_t = 0.0          # 当前扇区开始时间
        self._stable = -1        # 已停留足够久、可以输入的扇区
        self._need_rest = False  # 输入后等待摇杆回中
        self._rest_t = None
        self._cool_until = 0.0
        self._enter_t = None     # 右摇杆刚越过触发线的时间（用来滤掉单帧毛刺）
        self._g_cand, self._g_t = -1, 0.0
        self.lx = self.ly = self.rx = self.ry = 0.0   # 供界面显示摇杆位置
        self._suppress = False
        self.shift = False
        self.caps = False
        self.buf = ""
        self.cands = []
        self.sel = 0
        self.cwheel = False
        self._rt_prev = False
        self.held = {}
        self.log = ""
        self.toast = ""
        self.toast_until = 0.0
        self.banner = ""         # 常驻提示（如：未检测到手柄）
        self.moving = False      # 移动窗口模式（界面显示用）
        self.commands = []       # 轮盘上"内部命令"类按键（如 phone），由主程序取走执行
        self.dirty = True

    # ---------- 属性 ----------
    @property
    def kind(self):
        return MODES[self.mode]["kind"]

    def group_items(self, g=None):
        return MODES[self.mode]["groups"][self.group if g is None else g][1]

    def group_title(self, g=None):
        return MODES[self.mode]["groups"][self.group if g is None else g][0]

    @property
    def page(self):
        return self.sel // PAGE

    @property
    def pages(self):
        return max(1, (len(self.cands) + PAGE - 1) // PAGE)

    def page_cands(self):
        b = self.page * PAGE
        return self.cands[b:b + PAGE]

    def right_items(self):
        """右轮当前显示的 8 个槽位（候选轮盘模式下显示候选词）。"""
        if self.cwheel and self.cands:
            items = [w for w, _ in self.page_cands()]
            return items + [None] * (8 - len(items))
        return self.group_items()

    def say(self, msg, now, secs=1.8):
        self.toast, self.toast_until, self.dirty = msg, now + secs, True

    # ---------- 摇杆 ----------
    def update_axes(self, lx, ly, rx, ry, lt, rt, now):
        T = self.tune
        if abs(lx - self.lx) + abs(ly - self.ly) + abs(rx - self.rx) + abs(ry - self.ry) > 0.01:
            self.dirty = True
        self.lx, self.ly, self.rx, self.ry = lx, ly, rx, ry
        # 左摇杆：选组（粘滞，松开后仍保持；需稳定指向一小会儿才切换）
        if math.hypot(lx, ly) >= T["group"]:
            s = sector(lx, ly)
            if s != self._g_cand:
                self._g_cand, self._g_t = s, now
            if s != self.group and now - self._g_t >= T["group_dwell"]:
                self.group = s
                self.dirty = True
        else:
            self._g_cand = -1
        # LT = Shift
        sh = lt > 0.5
        if sh != self.shift:
            self.shift, self.dirty = sh, True
        # RT：无拼音时 = Tab；有拼音时按住 = 候选轮盘
        rt_down = rt > 0.5
        if rt_down and not self._rt_prev:
            if self.buf and self.cands:
                self.cwheel = True
                self._suppress = self.hover >= 0 or math.hypot(rx, ry) >= T["exit"]
                self.hover = -1
            else:
                self.sink.key(VK_TAB)
            self.dirty = True
        elif not rt_down and self._rt_prev:
            if self.cwheel:
                self.cwheel = False
                self._suppress = self.hover >= 0 or math.hypot(rx, ry) >= T["exit"]
                self.hover = -1
                self.dirty = True
        self._rt_prev = rt_down

        # 右摇杆：推到底指向 -> 停留一会儿 -> 松开输入
        m = math.hypot(rx, ry)
        if self._suppress:
            self._enter_t = None
            if m < T["exit"]:
                self._suppress = False
            return
        if self._need_rest:
            # 刚输入过：摇杆必须回到中心附近并稳定，期间的回弹/过冲一律忽略
            if m < T["rest"]:
                if self._rest_t is None:
                    self._rest_t = now
                elif now - self._rest_t >= 0.05:
                    self._need_rest = False
            else:
                self._rest_t = None
            if self._need_rest:
                self._enter_t = None
                return
        if self.hover < 0:
            if now >= self._cool_until and m >= T["enter"]:
                # 需要持续 25ms 才算指向：单帧毛刺直接忽略（不会闪、不会误触）
                if self._enter_t is None:
                    self._enter_t = now
                if now - self._enter_t >= 0.025:
                    self.hover, self._h_t, self._stable = sector(rx, ry), self._enter_t, -1
                    self._enter_t = None
                    self.dirty = True
            else:
                self._enter_t = None
        elif m < T["exit"]:
            slot = self._stable          # 只输入"停留够久"的扇区；轻轻碰一下 = 取消
            self.hover, self._stable = -1, -1
            self._need_rest, self._rest_t = True, None
            self._cool_until = now + T["cooldown"]
            self.dirty = True
            if slot >= 0:
                self.commit_slot(slot)
        else:
            s = sector(rx, ry)
            if s != self.hover:
                self.hover, self._h_t, self._stable = s, now, -1
                self.dirty = True
        if self.hover >= 0 and now - self._h_t >= T["dwell"]:
            self._stable = self.hover

    # ---------- 输出 ----------
    def commit_slot(self, slot):
        if self.cwheel and self.cands:
            idx = self.page * PAGE + slot
            if idx < len(self.cands):
                self.choose(idx)
            return
        self.output_item(self.group_items()[slot])

    def _emit(self, s):
        self.sink.text(s)
        self.log = (self.log + s)[-30:]
        self.dirty = True

    def output_item(self, item):
        if item is None:
            return
        if isinstance(item, Act):
            if item.cmd:
                self.commands.append(item.cmd)
                self.dirty = True
                return
            if self.buf:
                self.cancel()
            if item.vks:
                self.sink.combo(item.vks)
            elif item.text:
                self._emit(item.text)
            self.log = (self.log + "⟨" + item.label + "⟩")[-30:]
            self.dirty = True
            return
        ch = item
        if self.kind == "pinyin":
            if (ch.isascii() and ch.isalpha()) or (ch == "'" and self.buf):
                self.buf += ch
                self.refresh()
                return
            if ch == "'":
                return
            self.flush()
            self._emit(ch)
            return
        if self.kind == "abc" and ch.isalpha() and (self.shift != self.caps):
            ch = ch.upper()
        self._emit(ch)

    # ---------- 拼音 ----------
    def refresh(self):
        self.cands = self.engine.candidates(self.buf) if self.buf else []
        self.sel = 0
        self.dirty = True

    def choose(self, idx):
        if not (0 <= idx < len(self.cands)):
            return
        word, used = self.cands[idx]
        if word != self.buf:
            self.engine.learn(self.buf[:used], word)
        self._emit(word)
        self.buf = self.buf[used:].lstrip("'")
        self.refresh()

    def flush(self):
        """标点等触发：先上屏当前首选，剩余的拼音按原样上屏。"""
        if not self.buf:
            return
        self.choose(self.sel)
        if self.buf:
            self._emit(self.buf)
            self.cancel()

    def commit_raw(self):
        if self.buf:
            self._emit(self.buf.replace("'", ""))
            self.cancel()

    def cancel(self):
        self.buf, self.cands, self.sel, self.cwheel = "", [], 0, False
        self.dirty = True

    # ---------- 模式 ----------
    def set_mode(self, i):
        self.cancel()
        self.mode = i % len(MODES)
        self.group = 0
        self.dirty = True

    def toggle_zh_en(self):
        self.set_mode(1 if self.mode == 0 else 0)

    # ---------- 按键 ----------
    def button_down(self, name, now):
        self.button(name, now)
        if name in REPEAT:
            self.held[name] = now + 0.4

    def button_up(self, name):
        self.held.pop(name, None)

    def tick(self, now):
        for name, t in list(self.held.items()):
            if now >= t:
                self.held[name] = now + 0.055
                self.button(name, now)

    def button(self, name, now=0.0):
        s = self.sink
        self.dirty = True
        if name == "a":
            if self.buf:
                self.choose(self.sel)
            else:
                s.key(VK_SPACE)
        elif name == "b":
            if self.buf:
                self.cancel()
            else:
                s.key(VK_ESCAPE)
        elif name == "x":
            if self.buf:
                self.buf = self.buf[:-1]
                self.refresh()
            else:
                s.key(VK_BACK)
                self.log = self.log[:-1]
        elif name == "y":
            if self.buf:
                self.commit_raw()
            else:
                s.key(VK_RETURN)
        elif name == "lb":
            self.set_mode(self.mode - 1)
        elif name == "rb":
            self.set_mode(self.mode + 1)
        elif name == "l3":
            self.caps = not self.caps
        elif name == "r3":
            self.toggle_zh_en()
        elif name in ("left", "right", "up", "down"):
            if self.buf:
                step = {"left": -1, "right": 1, "up": -PAGE, "down": PAGE}[name]
                self.sel = min(max(0, self.sel + step), len(self.cands) - 1)
            else:
                s.key({"left": VK_LEFT, "right": VK_RIGHT, "up": VK_UP, "down": VK_DOWN}[name])
