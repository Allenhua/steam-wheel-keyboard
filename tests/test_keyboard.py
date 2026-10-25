"""自测：拼音引擎 + 状态机 + 防误触（不需要手柄）。运行（在项目根目录）：python tests/test_keyboard.py
需要先生成词库：python build_dict.py --download"""
import math
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # 项目根目录
sys.path.insert(0, BASE)

from logic import Keyboard                     # noqa: E402
from pinyin_engine import PinyinEngine         # noqa: E402
from sender import RecordingSink               # noqa: E402


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name, extra)
    if not cond:
        check.failed = True


check.failed = False


def push(kb, slot_dir, t):
    """模拟右摇杆推向某扇区然后松开。"""
    import math
    a = slot_dir * math.pi / 4
    kb.update_axes(0, 0, math.sin(a), -math.cos(a), 0, 0, t)
    kb.update_axes(0, 0, math.sin(a), -math.cos(a), 0, 0, t + 0.2)
    kb.update_axes(0, 0, 0, 0, 0, 0, t + 0.3)
    for i in range(1, 8):                  # 回中后稳定若干帧
        kb.update_axes(0, 0, 0, 0, 0, 0, t + 0.3 + i * 0.02)


def stick(kb, x, y, t):
    kb.update_axes(0, 0, x, y, 0, 0, t)


def left(kb, g, t):
    import math
    a = g * math.pi / 4
    for i in range(4):
        kb.update_axes(math.sin(a), -math.cos(a), 0, 0, 0, 0, t + i * 0.03)
    kb.update_axes(0, 0, 0, 0, 0, 0, t + 0.15)


def main():
    eng = PinyinEngine(os.path.join(BASE, "data", "dict.txt"))
    if not eng.load():
        print("未找到词库，请先运行：python build_dict.py --download")
        return 2
    check("词库加载", True, f"db={os.path.basename(eng.db_path)}")
    for buf in ["ni", "nihao", "nh", "zhongguo", "woaini", "xian", "xi'an", "nihaoma", "lv", "nv"]:
        c = eng.candidates(buf)
        print(f"  {buf:10s} ->", " ".join(f"{w}" for w, _ in c[:10]))
    c = [w for w, _ in eng.candidates("nihao")]
    check("nihao 含 你好", "你好" in c[:3])
    c = [w for w, _ in eng.candidates("zhongguo")]
    check("zhongguo 含 中国", "中国" in c[:3])
    c = [w for w, _ in eng.candidates("woaini")]
    check("woaini 含 我爱你", "我爱你" in c[:5])
    c = eng.candidates("nihaoma")
    check("nihaoma 可部分上屏", any(w == "你好" and u == 5 for w, u in c), str(c[:6]))

    sink = RecordingSink()
    kb = Keyboard(sink, eng)
    # 拼音：左摇杆选第 2 组(efgh)... 先选组 2(ijkl)，右摇杆上=i
    t = 1.0
    left(kb, 3, t)       # mnop 组
    push(kb, 4, t + 1)   # 下 = o ? ring4(m,n,o,p): 上m 右n 下o 左p
    check("输入拼音字母 o", kb.buf == "o", kb.buf)
    kb.cancel()
    left(kb, 3, 2)
    push(kb, 2, 3)       # n
    left(kb, 2, 4)
    push(kb, 0, 5)       # i
    check("buf=ni", kb.buf == "ni", kb.buf)
    kb.button("a", 6)
    check("A 上屏候选", sink.out and sink.out[-1][0] == "text" and sink.out[-1][1] != "ni",
          str(sink.out))
    # 模式切换 / ABC 大写
    kb.set_mode(1)
    sink.out.clear()
    left(kb, 0, 7)
    push(kb, 0, 8)
    check("ABC 小写 a", sink.out == [("text", "a")], str(sink.out))
    kb.button("l3", 9)
    push(kb, 0, 10)
    check("ABC 大写 A", sink.out[-1] == ("text", "A"), str(sink.out))
    # 功能键
    kb.set_mode(4)
    sink.out.clear()
    left(kb, 1, 11)
    push(kb, 0, 12)
    check("功能：复制 Ctrl+C", sink.out == [("combo", (0x11, ord("C")))], str(sink.out))
    # ---------- 防误触 ----------
    kb.set_mode(1)
    kb.caps = False
    sink.out.clear()
    left(kb, 0, 20)
    # 1) 轻轻碰一下（幅度 0.5，没推到 enter 阈值）-> 不输入
    for i in range(20):
        stick(kb, 0, -0.5, 21 + i * 0.01)
    stick(kb, 0, 0, 22)
    check("轻推不输入", sink.out == [], str(sink.out))
    # 2) 推到底但一扫而过（<dwell）-> 不输入
    stick(kb, 0, -1, 23.00)
    stick(kb, 0, -1, 23.03)
    stick(kb, 0, 0, 23.04)
    for i in range(8):
        stick(kb, 0, 0, 23.05 + i * 0.02)
    check("一扫而过不输入", sink.out == [], str(sink.out))
    # 3) 正常输入 a，随后松手回弹过冲到反方向 0.6 -> 只输入一个字
    stick(kb, 0, -1, 24.00)
    stick(kb, 0, -1, 24.12)
    stick(kb, 0, 0, 24.14)           # 松开 -> 输入 a
    stick(kb, 0, 0.6, 24.16)         # 过冲到下方 0.6（若不防护会再输入一个）
    stick(kb, 0, 0.6, 24.25)
    stick(kb, 0, 0.1, 24.30)
    for i in range(8):
        stick(kb, 0, 0, 24.35 + i * 0.02)
    check("回弹过冲只输入一个字", sink.out == [("text", "a")], str(sink.out))
    # 4) 扇区抖动：在边界来回快速切换并松开 -> 不输入
    sink.out.clear()
    for i in range(10):
        ang = (0.35 if i % 2 else 0.45) * math.pi / 4 * 2
        stick(kb, math.sin(ang), -math.cos(ang), 25 + i * 0.02)
    stick(kb, 0, 0, 25.25)
    for i in range(8):
        stick(kb, 0, 0, 25.3 + i * 0.02)
    check("抖动不输入", len(sink.out) <= 1, str(sink.out))

    # 5) 单帧毛刺（实测 SDL 偶发右摇杆单帧到 -1.0）：不闪、不输入
    sink.out.clear()
    stick(kb, 0, 0, 30.00)
    stick(kb, 0, -1.0, 30.008)       # 仅一帧
    check("毛刺帧不触发指向", kb.hover == -1, f"hover={kb.hover}")
    stick(kb, 0, 0, 30.016)
    for i in range(8):
        stick(kb, 0, 0, 30.03 + i * 0.02)
    check("毛刺不输入", sink.out == [], str(sink.out))

    print("\n全部通过" if not check.failed else "\n有失败项")
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(main())
