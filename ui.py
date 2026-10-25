"""界面绘制：双轮盘 + 候选栏。所有尺寸以 BW x BH 的基准坐标设计，再乘以缩放 k。
画在带透明通道的画布上，由 winutil.Layered 作为逐像素透明窗口显示。"""
import math
import os

import pygame
from pygame import gfxdraw

from layouts import MODES, label_of

BW, BH = 1000, 480

C_PANEL = (22, 24, 31)
C_SECTOR = (44, 48, 62)
C_SECTOR_EMPTY = (32, 35, 45)
C_GROUP = (58, 98, 190)
C_HOVER = (255, 190, 40)
C_TEXT = (236, 239, 246)
C_MUTED = (150, 156, 172)
C_ACCENT = (110, 170, 255)
C_BTN = (40, 44, 58)
C_ON = (70, 150, 110)

FONT_FILES = [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\seguisym.ttf",
              r"C:\Windows\Fonts\simsun.ttc", r"C:\Windows\Fonts\arial.ttf"]

R_IN, R_OUT = 56, 152
LCX, RCX, WCY = 245, 755, 300
BUTTONS = [("space", "空格", "A"), ("bksp", "退格", "X"), ("enter", "回车", "Y"),
           ("esc", "取消 / Esc", "B"), ("shift", "Shift", "LT"), ("caps", "大写锁定", "L3"),
           ("move", "移动窗口", "LB+RB"), ("hide", "收起键盘", "L3+R3"), ("phone", "手机扫码", "功能页")]
BTN_X, BTN_W, BTN_Y0, BTN_H, BTN_GAP = 438, 124, 138, 30, 5
TOPBAR = (8, 6, BW - 16, 52)       # 顶栏（也是拖动区）


class Fonts:
    def __init__(self):
        self.fonts = {}
        self.cache = {}

    def _font(self, i, size):
        k = (i, size)
        if k not in self.fonts:
            try:
                self.fonts[k] = pygame.font.Font(FONT_FILES[i], size)
            except Exception:
                self.fonts[k] = pygame.font.Font(None, size)
        return self.fonts[k]

    def _pick(self, ch, size):
        for i, p in enumerate(FONT_FILES):
            if not os.path.exists(p):
                continue
            f = self._font(i, size)
            try:
                if f.metrics(ch)[0] is not None:
                    return f
            except Exception:
                pass
        return self._font(0, size)

    def render(self, text, size, color):
        size = max(8, int(size))
        key = (text, size, color)
        s = self.cache.get(key)
        if s is not None:
            return s
        if len(self.cache) > 600:
            self.cache.clear()
        parts, cur, curf = [], "", None
        for ch in text:
            f = self._pick(ch, size)
            if f is not curf and cur:
                parts.append((cur, curf))
                cur = ""
            curf = f
            cur += ch
        if cur:
            parts.append((cur, curf))
        if not parts:
            s = pygame.Surface((1, size), pygame.SRCALPHA)
        else:
            surfs = [f.render(t, True, color) for t, f in parts]
            w = sum(x.get_width() for x in surfs)
            h = max(x.get_height() for x in surfs)
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            x = 0
            for sf in surfs:
                s.blit(sf, (x, (h - sf.get_height()) // 2))
                x += sf.get_width()
        self.cache[key] = s
        return s


def polar(cx, cy, r, th):
    return cx + r * math.sin(th), cy - r * math.cos(th)


class UI:
    def __init__(self, k, bg_alpha=0.80, panel_alpha=0.0):
        self.k = k
        self.fonts = Fonts()
        self.size = (int(BW * k), int(BH * k))
        self.a = int(255 * max(0.1, min(1.0, bg_alpha)))      # 轮盘/按钮底色的不透明度
        self.panel_a = int(255 * max(0.0, min(1.0, panel_alpha)))
        self.cand_rects = []
        self.tab_rects = []
        self.ov_rects = []
        self.overlay_on = False
        self._qr_cache = {}
        self._shapes = {}

    def col(self, rgb, a=None):
        return (rgb[0], rgb[1], rgb[2], self.a if a is None else a)

    # ---------- 基础绘制 ----------
    def s(self, v):
        return int(round(v * self.k))

    def text(self, surf, txt, size, color, x, y, anchor="center"):
        img = self.fonts.render(txt, size * self.k, color)
        r = img.get_rect()
        setattr(r, {"center": "center", "left": "midleft", "right": "midright"}[anchor],
                (self.s(x), self.s(y)))
        surf.blit(img, r)
        return r

    # 形状用 3 倍超采样再缩小来抗锯齿，并缓存（颜色、尺寸相同的形状只画一次）
    SS = 3

    def _cached(self, key, w, h, color, draw):
        img = self._shapes.get(key)
        if img is None:
            if len(self._shapes) > 400:
                self._shapes.clear()
            ss = self.SS
            tmp = pygame.Surface((w * ss, h * ss), pygame.SRCALPHA)
            tmp.fill((color[0], color[1], color[2], 0))     # 保持边缘颜色不被透明黑污染
            draw(tmp, ss)
            img = pygame.transform.smoothscale(tmp, (w, h))
            self._shapes[key] = img
        return img

    def rrect(self, surf, rect, color, radius=10):
        w, h = max(2, rect.w), max(2, rect.h)
        r = self.s(radius)
        img = self._cached(("r", w, h, r, color), w, h, color,
                           lambda t, ss: pygame.draw.rect(t, color, (0, 0, w * ss, h * ss), border_radius=r * ss))
        surf.blit(img, rect.topleft)

    def sector(self, surf, cx, i, color, rin=R_IN, rout=R_OUT, cy=WCY):
        th = i * math.pi / 4
        half = math.pi / 8 - 0.025
        pts = []
        steps = 10
        for n in range(steps + 1):
            a = th - half + 2 * half * n / steps
            pts.append(polar(0, 0, self.s(rout), a))
        for n in range(steps, -1, -1):
            a = th - half + 2 * half * n / steps
            pts.append(polar(0, 0, self.s(rin), a))
        ox = int(math.floor(min(p[0] for p in pts))) - 1
        oy = int(math.floor(min(p[1] for p in pts))) - 1
        w = int(math.ceil(max(p[0] for p in pts))) - ox + 2
        h = int(math.ceil(max(p[1] for p in pts))) - oy + 2
        img = self._cached(("s", i, rin, rout, color, self.k), w, h, color,
                           lambda t, ss: pygame.draw.polygon(
                               t, color, [((x - ox) * ss, (y - oy) * ss) for x, y in pts]))
        surf.blit(img, (self.s(cx) + ox, self.s(cy) + oy))

    def circle(self, surf, cx, cy, r, color):
        rr = self.s(r)
        d = rr * 2 + 4
        img = self._cached(("c", rr, color), d, d, color,
                           lambda t, ss: pygame.draw.circle(t, color, (d * ss // 2, d * ss // 2), rr * ss))
        surf.blit(img, (self.s(cx) - d // 2, self.s(cy) - d // 2))

    # ---------- 主绘制 ----------
    def draw(self, surf, kb, status, now, overlay=None):
        surf.fill((0, 0, 0, 0))
        if self.panel_a:
            self.rrect(surf, pygame.Rect(0, 0, *self.size), self.col(C_PANEL, self.panel_a), 26)
        self._tabs(surf, kb, status)
        self._compose(surf, kb, now)
        self.overlay_on = overlay is not None
        self.ov_rects = []
        if overlay is not None:
            self._overlay(surf, overlay)
            return
        self._wheels(surf, kb)
        self._buttons(surf, kb)
        self.text(surf, "LB/RB 切换模式 · R3 中英 · L3 大写 · L3+R3 收起/呼出 · LB+RB 移动窗口 · RT Tab/候选轮盘",
                  13, C_MUTED, BW / 2, 466)

    # ---------- 手机扫码面板 ----------
    def _qr_surface(self, url, matrix, size_px):
        key = (url, size_px)
        img = self._qr_cache.get(key)
        if img is None:
            n = len(matrix)
            quiet = 2
            mp = max(2, size_px // (n + 2 * quiet))
            side = mp * (n + 2 * quiet)
            img = pygame.Surface((side, side))
            img.fill((255, 255, 255))
            for y, row in enumerate(matrix):
                for x, v in enumerate(row):
                    if v:
                        img.fill((16, 16, 20), ((x + quiet) * mp, (y + quiet) * mp, mp, mp))
            if len(self._qr_cache) > 8:
                self._qr_cache.clear()
            self._qr_cache[key] = img
        return img

    def _overlay(self, surf, ov):
        panel = pygame.Rect(self.s(24), self.s(124), self.s(BW - 48), self.s(334))
        self.rrect(surf, panel, self.col(C_PANEL, 240), 20)
        # 二维码
        qx, qy, qs = 52, 142, 296
        self.rrect(surf, pygame.Rect(self.s(qx - 6), self.s(qy - 6), self.s(qs + 12), self.s(qs + 12)),
                   (255, 255, 255, 255), 14)
        if not ov.get("ready", True):
            self.text(surf, "正在检测网络地址…", 20, (70, 76, 92), qx + qs / 2, qy + qs / 2)
        elif ov.get("matrix"):
            img = self._qr_surface(ov["url"], ov["matrix"], self.s(qs))
            surf.blit(img, (self.s(qx) + (self.s(qs) - img.get_width()) // 2,
                            self.s(qy) + (self.s(qs) - img.get_height()) // 2))
        else:
            self.text(surf, "（二维码库未安装）", 18, (60, 60, 70), qx + qs / 2, qy + qs / 2)
        # 文字
        x = 392
        self.text(surf, "手机扫码远程输入", 28, C_TEXT, x, 156, "left")
        steps = ["① 手机和电脑连到同一个 Wi-Fi",
                 "② 用手机相机或微信扫左边的二维码",
                 "③ 在手机网页里打字，点【发送】（支持中文、语音）"]
        for i, t in enumerate(steps):
            self.text(surf, t, 17, C_TEXT, x, 196 + i * 28, "left")
        if ov.get("ready", True):
            self.text(surf, ov["url"], 15, C_ACCENT, x, 292, "left")
        if ov.get("error"):
            self.text(surf, ov["error"], 16, C_HOVER, x, 322, "left")
        elif ov["clients"] > 0:
            self.text(surf, f"● 已连接 {ov['clients']} 台设备，现在可以在手机上打字了", 17, (90, 210, 150), x, 322, "left")
        else:
            self.text(surf, "○ 等待手机连接…", 17, C_MUTED, x, 322, "left")
        self.text(surf, f"地址 {ov['idx'] + 1}/{ov['n']}：手机打不开就按 X 换一个地址", 14, C_MUTED, x, 350, "left")
        self.text(surf, "还是连不上：在 Windows 防火墙弹窗里勾选【专用网络】和【公用网络】并点允许", 13, C_MUTED, x, 374, "left")
        # 按钮
        for i, (name, label) in enumerate((("next", "换地址  X"), ("hide", "隐藏  A / B"), ("stop", "停止手机输入  Y"))):
            w = (150, 150, 200)[i]
            r = pygame.Rect(self.s(x + sum((150, 150, 200)[:i]) + i * 12), self.s(398), self.s(w), self.s(40))
            self.rrect(surf, r, self.col(C_GROUP if name == "hide" else C_BTN, 255), 12)
            self.text(surf, label, 17, C_TEXT, r.centerx / self.k, 418)
            self.ov_rects.append((name, r))

    def _tabs(self, surf, kb, status):
        self.tab_rects = []
        bx, by, bw, bh = TOPBAR
        self.rrect(surf, pygame.Rect(self.s(bx), self.s(by), self.s(bw), self.s(bh)),
                   self.col(C_PANEL, min(255, self.a + 20)), 16)
        x = 24
        self.text(surf, "LB", 13, C_MUTED, x + 8, 32)
        x += 28
        for i, m in enumerate(MODES):
            r = pygame.Rect(self.s(x), self.s(12), self.s(96), self.s(40))
            self.tab_rects.append(r)
            self.rrect(surf, r, self.col(C_GROUP if i == kb.mode else C_BTN, 255 if i == kb.mode else self.a), 12)
            self.text(surf, m["name"], 20, C_TEXT if i == kb.mode else C_MUTED, x + 48, 32)
            x += 102
        self.text(surf, "RB", 13, C_MUTED, x + 4, 32)
        self.text(surf, status, 14, C_MUTED, BW - 24, 26, "right")
        flags = []
        if kb.shift:
            flags.append("Shift")
        if kb.caps:
            flags.append("CAPS")
        if flags:
            self.text(surf, " ".join(flags), 15, C_HOVER, BW - 24, 45, "right")

    def _compose(self, surf, kb, now):
        r = pygame.Rect(self.s(24), self.s(66), self.s(BW - 48), self.s(50))
        self.rrect(surf, r, self.col(C_BTN, min(255, self.a + 10)), 14)
        self.cand_rects = []
        cy = 91
        if getattr(kb, "moving", False):
            self.text(surf, "移动模式：摇杆移动 · 十字键贴边 · Y 居中 · LB/RB 缩小/放大 · A 确定", 19, C_HOVER, 40, cy, "left")
        elif kb.buf:
            self.text(surf, kb.buf, 24, C_HOVER, 40, cy, "left")
            x = 40 + max(110, self.fonts.render(kb.buf, 24 * self.k, C_TEXT).get_width() / self.k + 30)
            cands = kb.page_cands()
            avail = BW - 48 - x - 70
            size = 26
            while size > 15:
                tot = sum(self.fonts.render(self._clip(w), size * self.k, C_TEXT).get_width() / self.k + 40
                          for w, _ in cands)
                if tot <= avail:
                    break
                size -= 2
            for i, (w, _) in enumerate(cands):
                label = self._clip(w)
                wd = self.fonts.render(label, size * self.k, C_TEXT).get_width() / self.k
                box = pygame.Rect(self.s(x - 6), self.s(70), self.s(wd + 40), self.s(42))
                self.cand_rects.append(box)
                gi = kb.page * 8 + i
                if gi == kb.sel:
                    self.rrect(surf, box, self.col(C_GROUP, 255), 10)
                self.text(surf, str(i + 1), 13, C_MUTED, x + 4, cy + 5)
                self.text(surf, label, size, C_TEXT, x + 16, cy, "left")
                x += wd + 40
            if kb.pages > 1:
                self.text(surf, f"{kb.page + 1}/{kb.pages}", 15, C_MUTED, BW - 40, cy, "right")
        else:
            if now < kb.toast_until and kb.toast:
                self.text(surf, kb.toast, 20, C_HOVER, 40, cy, "left")
            elif kb.banner and not kb.log:
                self.text(surf, kb.banner, 15, C_HOVER, 40, cy, "left")
            elif kb.log:
                self.text(surf, "已输入  " + kb.log[-26:], 20, C_TEXT, 40, cy, "left")
            else:
                self.text(surf, self._hint(kb), 18, C_MUTED, 40, cy, "left")

    def _hint(self, kb):
        return {"pinyin": "左摇杆选组 → 右摇杆指向字母，松开输入拼音；A 选词  X 退格  Y 回车",
                "abc": "左摇杆选组 → 右摇杆指向字母，松开输入；LT 按住大写",
                "plain": "左摇杆选组 → 右摇杆指向符号，松开输入",
                "func": "左摇杆选组 → 右摇杆指向功能键 / 快捷键，松开执行"}[kb.kind]

    @staticmethod
    def _clip(w):
        return w if len(w) <= 7 else w[:6] + "…"

    def _wheels(self, surf, kb):
        self.text(surf, "左摇杆 · 选组", 14, C_MUTED, LCX, 132)
        rtxt = "右摇杆 · 选候选词" if (kb.cwheel and kb.cands) else "右摇杆 · 指向并松开输入"
        self.text(surf, rtxt, 14, C_HOVER if kb.cwheel else C_MUTED, RCX, 132)
        # 每个轮盘垫一层很淡的底，避免缝隙里透出的背景太杂
        for cx in (LCX, RCX):
            self.circle(surf, cx, WCY, R_OUT + 4, (10, 12, 18, int(self.a * 0.45)))
        # 左轮：组
        for i in range(8):
            title, items = MODES[kb.mode]["groups"][i]
            has = any(x is not None for x in items)
            col = self.col(C_GROUP, 245) if i == kb.group else self.col(C_SECTOR if has else C_SECTOR_EMPTY)
            self.sector(surf, LCX, i, col)
            th = i * math.pi / 4
            x, y = polar(LCX, WCY, (R_IN + R_OUT) / 2, th)
            labels = [label_of(it) for it in items if it is not None]
            if kb.mode in (0, 1) and len(labels) <= 4:
                a, b = " ".join(labels[:2]), " ".join(labels[2:4])
                self.text(surf, a, 19, C_TEXT, x, y - 10)
                self.text(surf, b, 19, C_TEXT, x, y + 11)
            else:
                t = title if len(title) <= 5 else title[:5]
                self.text(surf, t, 17, C_TEXT, x, y)
        self._marker(surf, LCX, kb.lx, kb.ly, kb.tune["group"])
        self.circle(surf, LCX, WCY, R_IN - 3, self.col(C_PANEL, 235))
        self.text(surf, MODES[kb.mode]["short"], 28, C_ACCENT, LCX, WCY - 8)
        self.text(surf, kb.group_title()[:6], 13, C_MUTED, LCX, WCY + 16)
        # 右轮：槽
        items = kb.right_items()
        hv = kb.hover if kb.hover >= 0 else kb.mouse_hover
        for i in range(8):
            it = items[i]
            if i == hv and it is not None:
                col = (C_HOVER[0], C_HOVER[1], C_HOVER[2], 255)
            else:
                col = self.col(C_SECTOR if it is not None else C_SECTOR_EMPTY)
            self.sector(surf, RCX, i, col)
            if it is None:
                continue
            lab = label_of(it)
            lab = lab if len(lab) <= 4 else lab[:3] + "…"
            th = i * math.pi / 4
            x, y = polar(RCX, WCY, (R_IN + R_OUT) / 2, th)
            if kb.kind == "abc" and lab.isalpha() and (kb.shift != kb.caps):
                lab = lab.upper()
            size = 30 if len(lab) <= 1 else (22 if len(lab) <= 2 else 17)
            self.text(surf, lab, size, (20, 20, 20) if i == hv else C_TEXT, x, y)
        self._marker(surf, RCX, kb.rx, kb.ry, kb.tune["enter"])
        self.circle(surf, RCX, WCY, R_IN - 3, self.col(C_PANEL, 235))
        if hv >= 0 and items[hv] is not None:
            lab = label_of(items[hv])
            self.text(surf, lab[:4], 30 if len(lab) <= 2 else 20, C_HOVER, RCX, WCY)
        else:
            self.text(surf, "·", 30, C_MUTED, RCX, WCY)

    def _marker(self, surf, cx, x, y, thr):
        """摇杆位置点 + 触发线：圆点越过细线圈才会选中。"""
        r = self.s(R_OUT * thr)
        gfxdraw.aacircle(surf, self.s(cx), self.s(WCY), r, (120, 128, 156, 200))
        m = math.hypot(x, y)
        if m > 1:
            x, y, m = x / m, y / m, 1.0
        px, py = self.s(cx + x * R_OUT), self.s(WCY + y * R_OUT)
        on = m >= thr
        col = (255, 255, 255, 255) if on else (150, 160, 190, 255)
        gfxdraw.filled_circle(surf, px, py, self.s(7), col)
        gfxdraw.aacircle(surf, px, py, self.s(7), (20, 20, 20, 255))

    def _buttons(self, surf, kb):
        for n, (name, label, hint) in enumerate(BUTTONS):
            r = self.btn_rect(n)
            on = (name == "shift" and kb.shift) or (name == "caps" and kb.caps) or \
                 (name == "move" and getattr(kb, "moving", False))
            self.rrect(surf, r, self.col(C_ON, 255) if on else self.col(C_BTN), 10)
            self.text(surf, label, 16, C_TEXT, BTN_X + 12, (r.centery / self.k), "left")
            self.text(surf, hint, 12, C_MUTED, BTN_X + BTN_W - 8, (r.centery / self.k), "right")

    def btn_rect(self, n):
        return pygame.Rect(self.s(BTN_X), self.s(BTN_Y0 + n * (BTN_H + BTN_GAP)),
                           self.s(BTN_W), self.s(BTN_H))

    # ---------- 鼠标命中测试（参数为窗口像素） ----------
    def hit(self, pos):
        x, y = pos
        if self.overlay_on:
            for name, r in self.ov_rects:
                if r.collidepoint(pos):
                    return ("ov", name)
            bx, by, bw, bh = TOPBAR
            if pygame.Rect(self.s(bx), self.s(by), self.s(bw), self.s(bh)).collidepoint(pos):
                return ("drag", None)
            return None
        for i, r in enumerate(self.tab_rects):
            if r.collidepoint(pos):
                return ("tab", i)
        for i, r in enumerate(self.cand_rects):
            if r.collidepoint(pos):
                return ("cand", i)
        for n, (name, _, _) in enumerate(BUTTONS):
            if self.btn_rect(n).collidepoint(pos):
                return ("btn", name)
        for side, cx in (("l", LCX), ("r", RCX)):
            dx, dy = x - self.s(cx), y - self.s(WCY)
            d = math.hypot(dx, dy)
            if self.s(R_IN) <= d <= self.s(R_OUT + 8):
                idx = int(round(math.atan2(dx, -dy) / (math.pi / 4))) % 8
                return (side + "sec", idx)
        bx, by, bw, bh = TOPBAR
        if pygame.Rect(self.s(bx), self.s(by), self.s(bw), self.s(bh)).collidepoint(pos):
            return ("drag", None)
        return None
