"""生成 README 用的界面截图（离线渲染，叠在一个模拟的桌面 + 文本编辑器上，不会截到你真实桌面的任何内容）。

用法（在项目根目录）：  python tools/make_screenshots.py
输出：docs/screenshots/*.png
前提：已生成词库（python build_dict.py --download）。
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame  # noqa: E402

from logic import Keyboard  # noqa: E402
from pinyin_engine import PinyinEngine  # noqa: E402
from sender import RecordingSink  # noqa: E402
from ui import UI  # noqa: E402

K = 1.5
OUT = os.path.join(ROOT, "docs", "screenshots")


def gradient(w, h, top, bottom):
    s = pygame.Surface((w, h))
    for y in range(h):
        t = y / max(1, h - 1)
        s.fill(tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)), (0, y, w, 1))
    return s


def desk(ui, w, h, text_lines, title="无标题 - 记事本"):
    """模拟桌面：渐变壁纸 + 一个文本编辑器窗口。"""
    bg = gradient(w, h, (28, 38, 66), (70, 52, 96))
    ex, ey, ew, eh = int(w * 0.07), int(h * 0.05), int(w * 0.86), int(h * 0.70)
    pygame.draw.rect(bg, (250, 250, 252), (ex, ey, ew, eh), border_radius=int(14 * K))
    pygame.draw.rect(bg, (236, 238, 244), (ex, ey, ew, int(44 * K)),
                     border_top_left_radius=int(14 * K), border_top_right_radius=int(14 * K))
    for i, c in enumerate(((255, 96, 92), (255, 189, 68), (0, 202, 78))):
        pygame.draw.circle(bg, c, (ex + int((26 + i * 24) * K), ey + int(22 * K)), int(7 * K))
    bg.blit(ui.fonts.render(title, 17 * K, (90, 96, 110)), (ex + int(110 * K), ey + int(11 * K)))
    y = ey + int(66 * K)
    for line in text_lines:
        img = ui.fonts.render(line, 26 * K, (30, 34, 44))
        bg.blit(img, (ex + int(30 * K), y))
        y += int(44 * K)
    # 光标
    last = ui.fonts.render(text_lines[-1], 26 * K, (30, 34, 44)) if text_lines else None
    cx = ex + int(30 * K) + (last.get_width() if last else 0) + int(3 * K)
    pygame.draw.rect(bg, (60, 100, 220), (cx, y - int(44 * K) + int(3 * K), int(3 * K), int(30 * K)))
    return bg


def shot(name, setup, status, lines, overlay=None, extra_h=0, title="无标题 - 记事本"):
    eng = PinyinEngine(os.path.join(ROOT, "data", "dict.txt"))
    eng.load()
    kb = Keyboard(RecordingSink(), eng)
    setup(kb)
    ui = UI(K, 0.80, 0.0)
    w, h = ui.size
    H = h + int(300 * K) + extra_h
    canvas = pygame.Surface((w, h), pygame.SRCALPHA)
    ui.draw(canvas, kb, status, time.time(), overlay)
    scene = desk(ui, w, H, lines, title)
    scene.blit(canvas, (0, H - h - int(14 * K)))
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name + ".png")
    pygame.image.save(scene, path)
    print("saved", path)


def pinyin_state(kb):
    kb.mode, kb.group = 0, 3
    for ch in "nihaoma":
        kb.output_item(ch)
    kb.sel = 0
    kb.hover = 2
    kb.lx, kb.ly, kb.rx, kb.ry = 0.35, 0.75, 0.95, 0.05
    kb.log = "今天天气很好"


def abc_state(kb):
    kb.mode, kb.group, kb.shift, kb.hover = 1, 4, True, 2
    kb.lx, kb.ly, kb.rx, kb.ry = 0.0, 0.9, 0.92, 0.1
    kb.log = "Hello, Steam Controller"


def symbols_state(kb):
    kb.mode, kb.group, kb.hover = 2, 4, 1
    kb.lx, kb.ly, kb.rx, kb.ry = 0.0, 0.9, 0.7, -0.75
    kb.log = "你好，世界！"


def func_state(kb):
    kb.mode, kb.group, kb.hover = 4, 4, 7
    kb.lx, kb.ly, kb.rx, kb.ry = 0.0, 0.9, -0.7, -0.7
    kb.log = "⟨复制⟩⟨粘贴⟩"


def move_state(kb):
    kb.mode, kb.group = 0, 0
    kb.moving = True


def candwheel_state(kb):
    kb.mode, kb.group = 0, 0
    for ch in "shurufa":
        kb.output_item(ch)
    kb.cwheel = True
    kb.hover = 1
    kb.rx, kb.ry = 0.6, -0.7


TEXT = {
    "zh": {
        "title": "无标题 - 记事本",
        "pinyin": ["你好，", "今天天气很好，我正在用手柄打字。"],
        "english": ["Hello, Steam Controller"],
        "symbols": ["你好，世界！"],
        "function": ["复制、粘贴、Alt+Tab、媒体键……都在这一页"],
        "candidate-wheel": ["按住 RT：右摇杆直接选候选词"],
        "move-mode": ["LB+RB：把键盘挪到不挡输入框的地方"],
        "phone-qr": ["手机扫码后，在手机上打的字会出现在这里"],
        "func_log": "⟨复制⟩⟨粘贴⟩",
    },
    "en": {
        "title": "Untitled - Notepad",
        "pinyin": ["Chinese Pinyin with sentence prediction:", "今天天气很好，我正在用手柄打字。"],
        "english": ["Hello, Steam Controller"],
        "symbols": ["Symbols, CJK punctuation, currency & arrows"],
        "function": ["Copy, paste, Alt+Tab, F-keys, media keys…"],
        "candidate-wheel": ["Hold RT: pick candidates with the right stick"],
        "move-mode": ["LB+RB: move the keyboard out of the way"],
        "phone-qr": ["Whatever you type on your phone shows up here"],
        "func_log": "⟨Copy⟩⟨Paste⟩",
    },
}


def main():
    import i18n
    from i18n import T
    import segno
    pygame.init()
    pygame.font.init()
    global OUT
    base_out = OUT
    for lang in ("zh", "en"):
        i18n.set_lang(lang)
        OUT = os.path.join(base_out, lang)
        tx = TEXT[lang]
        status = T("Steam 模式") + " · Steam Controller"

        def f(state):
            def g(kb):
                state(kb)
                if state is func_state:
                    kb.log = tx["func_log"]
            return g

        for name, state in (("pinyin", pinyin_state), ("english", abc_state), ("symbols", symbols_state),
                            ("function", func_state), ("candidate-wheel", candwheel_state),
                            ("move-mode", move_state)):
            shot(name, f(state), status, tx[name], title=tx["title"])
        url = "http://192.168.1.23:8765/?k=a1B2c3D4"
        ov = {"url": url, "matrix": [list(r) for r in segno.make(url, error="m").matrix],
              "ready": True, "clients": 1, "idx": 0, "n": 2, "error": ""}
        shot("phone-qr", lambda kb: None, status + " · " + T("手机 {n} 台").format(n=1), tx["phone-qr"],
             overlay=ov, title=tx["title"])


if __name__ == "__main__":
    main()
