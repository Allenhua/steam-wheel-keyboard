"""轮盘布局：5 种模式，每种 8 个"组"（左轮），每组 8 个"槽"（右轮）。

槽位 0 = 正上方，顺时针每 45° 一个：上、右上、右、右下、下、左下、左、左上。
"""
from collections import namedtuple

Act = namedtuple("Act", "label vks text cmd", defaults=(None,))   # cmd: 交给主程序处理的内部命令

VK_BACK, VK_TAB, VK_RETURN, VK_ESCAPE, VK_SPACE = 0x08, 0x09, 0x0D, 0x1B, 0x20
VK_SHIFT, VK_CTRL, VK_ALT = 0x10, 0x11, 0x12
VK_PRIOR, VK_NEXT, VK_END, VK_HOME = 0x21, 0x22, 0x23, 0x24
VK_LEFT, VK_UP, VK_RIGHT, VK_DOWN = 0x25, 0x26, 0x27, 0x28
VK_SNAPSHOT, VK_INSERT, VK_DELETE, VK_LWIN = 0x2C, 0x2D, 0x2E, 0x5B
VK_F = [0x70 + i for i in range(12)]
VK_MUTE, VK_VOLDN, VK_VOLUP = 0xAD, 0xAE, 0xAF
VK_NEXT_TRACK, VK_PREV_TRACK, VK_PLAY = 0xB0, 0xB1, 0xB3
VK_PERIOD = 0xBE


def L(c):
    return ord(c.upper())


def K(label, *vks):
    return Act(label, tuple(vks), None)


def ring4(a, b, c, d):
    """4 个字符放在上/右/下/左，更不容易选错。"""
    return [a, None, b, None, c, None, d, None]


def pad(items):
    items = list(items)[:8]
    return items + [None] * (8 - len(items))


PINYIN = [
    ("abcd", ring4("a", "b", "c", "d")),
    ("efgh", ring4("e", "f", "g", "h")),
    ("ijkl", ring4("i", "j", "k", "l")),
    ("mnop", ring4("m", "n", "o", "p")),
    ("qrst", ring4("q", "r", "s", "t")),
    ("uvwx", ring4("u", "v", "w", "x")),
    ("yz，。", ring4("y", "z", "，", "。")),
    ("'？！", ["'", None, "？", None, "！", None, "、", None]),
]

ABC = [
    ("abcd", ring4("a", "b", "c", "d")),
    ("efgh", ring4("e", "f", "g", "h")),
    ("ijkl", ring4("i", "j", "k", "l")),
    ("mnop", ring4("m", "n", "o", "p")),
    ("qrst", ring4("q", "r", "s", "t")),
    ("uvwx", ring4("u", "v", "w", "x")),
    ("yz,.", ring4("y", "z", ",", ".")),
    ("'?!-", ring4("'", "?", "!", "-")),
]

SYMBOLS = [
    ("括号", pad(["(", ")", "[", "]", "{", "}", "<", ">"])),
    ("运算", pad(["+", "-", "*", "/", "=", "%", "^", "~"])),
    ("标点", pad([".", ",", ";", ":", "'", '"', "`", "!"])),
    ("特殊", pad(["?", "@", "#", "$", "&", "_", "|", "\\"])),
    ("中文标点", pad(["，", "。", "、", "？", "！", "：", "；", "…"])),
    ("引号", pad(["“", "”", "‘", "’", "「", "」", "《", "》"])),
    ("货币单位", pad(["¥", "€", "£", "°", "©", "®", "×", "÷"])),
    ("箭头", pad(["→", "←", "↑", "↓", "·", "—", "※", "●"])),
]

NUMBERS = [
    ("1-8", pad(list("12345678"))),
    ("9 0 . ,", pad(list("90.,:-+="))),
    ("符号", pad(["/", "*", "%", "(", ")", "[", "]", "_"])),
    ("货币", pad(["¥", "$", "€", "£", "#", "@", "&", "~"])),
    ("一二三", pad(list("一二三四五六七八"))),
    ("九十百", pad(list("九十百千万亿零元"))),
    ("圈数字", pad(list("①②③④⑤⑥⑦⑧"))),
    ("年月日", pad(list("年月日时分秒周号"))),
]

C = VK_CTRL
FUNC = [
    ("导航", pad([K("Esc", VK_ESCAPE), K("Tab", VK_TAB), K("Home", VK_HOME), K("End", VK_END),
                  K("PgUp", VK_PRIOR), K("PgDn", VK_NEXT), K("Del", VK_DELETE), K("Ins", VK_INSERT)])),
    ("编辑", pad([K("复制", C, L("C")), K("粘贴", C, L("V")), K("剪切", C, L("X")), K("撤销", C, L("Z")),
                  K("全选", C, L("A")), K("保存", C, L("S")), K("重做", C, L("Y")), K("查找", C, L("F"))])),
    ("F1-F8", pad([K(f"F{i + 1}", VK_F[i]) for i in range(8)])),
    ("F9-12等", pad([K("F9", VK_F[8]), K("F10", VK_F[9]), K("F11", VK_F[10]), K("F12", VK_F[11]),
                     K("PrtSc", VK_SNAPSHOT), K("Win", VK_LWIN),
                     K("截图", VK_LWIN, VK_SHIFT, L("S")), K("表情", VK_LWIN, VK_PERIOD)])),
    ("窗口", pad([K("切窗", VK_ALT, VK_TAB), K("任务视图", VK_LWIN, VK_TAB), K("桌面", VK_LWIN, L("D")),
                  K("关闭", VK_ALT, VK_F[3]), K("任务管理", C, VK_SHIFT, VK_ESCAPE),
                  K("资源管理", VK_LWIN, L("E")), K("剪贴板", VK_LWIN, L("V")),
                  Act("手机输入", None, None, "phone")])),
    ("媒体", pad([K("音量+", VK_VOLUP), K("音量-", VK_VOLDN), K("静音", VK_MUTE), K("播放", VK_PLAY),
                  K("上一曲", VK_PREV_TRACK), K("下一曲", VK_NEXT_TRACK), K("刷新", VK_F[4]), K("全屏", VK_F[10])])),
    ("浏览器", pad([K("新标签", C, L("T")), K("关标签", C, L("W")), K("下一页", C, VK_TAB),
                    K("上一页", C, VK_SHIFT, VK_TAB), K("恢复", C, VK_SHIFT, L("T")),
                    K("地址栏", C, L("L")), K("后退", VK_ALT, VK_LEFT), K("前进", VK_ALT, VK_RIGHT)])),
    ("选择", pad([K("到开头", C, VK_HOME), K("到结尾", C, VK_END), K("选至行首", VK_SHIFT, VK_HOME),
                  K("选至行尾", VK_SHIFT, VK_END), K("词左", C, VK_LEFT), K("词右", C, VK_RIGHT),
                  K("选左字", VK_SHIFT, VK_LEFT), K("选右字", VK_SHIFT, VK_RIGHT)])),
]

MODES = [
    {"name": "拼音", "short": "拼", "kind": "pinyin", "groups": PINYIN},
    {"name": "ABC", "short": "En", "kind": "abc", "groups": ABC},
    {"name": "符号", "short": "#+", "kind": "plain", "groups": SYMBOLS},
    {"name": "数字", "short": "123", "kind": "plain", "groups": NUMBERS},
    {"name": "功能", "short": "Fn", "kind": "func", "groups": FUNC},
]


def label_of(item):
    if item is None:
        return ""
    return item.label if isinstance(item, Act) else item
