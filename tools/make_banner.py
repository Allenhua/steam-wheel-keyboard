"""生成 README 顶部的科技风横幅 docs/banner-zh.svg / docs/banner-en.svg。用法：python tools/make_banner.py"""
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 1280, 420

TEXT = {
    "zh": {"sub": "为手柄打造的双轮盘屏幕键盘",
           "tags": ["中文拼音", "英文 / 符号 / 功能键", "手机扫码输入", "透明 · 不抢焦点"],
           "hint": "左摇杆选组 · 右摇杆选字 · 松开即输入"},
    "en": {"sub": "A dual-wheel on-screen keyboard built for gamepads",
           "tags": ["Chinese Pinyin", "English / Symbols / F-keys", "Phone QR typing", "Transparent · No focus steal"],
           "hint": "Left stick picks a group · right stick picks a key · release to type"},
}
FONT = "'Segoe UI','Microsoft YaHei','PingFang SC','Noto Sans CJK SC',Helvetica,Arial,sans-serif"
MONO = "'Cascadia Code','JetBrains Mono',Consolas,'SF Mono',monospace"


def sector(cx, cy, r0, r1, i, gap=0.05):
    a0 = (i - 0.5) * math.pi / 4 + gap
    a1 = (i + 0.5) * math.pi / 4 - gap

    def p(r, a):
        return f"{cx + r * math.sin(a):.1f},{cy - r * math.cos(a):.1f}"
    return (f"M{p(r1, a0)} A{r1},{r1} 0 0 1 {p(r1, a1)} L{p(r0, a1)} "
            f"A{r0},{r0} 0 0 0 {p(r0, a0)} Z")


def wheel(cx, cy, labels, hot, color):
    out = [f'<circle cx="{cx}" cy="{cy}" r="118" fill="none" stroke="{color}" stroke-opacity=".25" stroke-width="1"/>',
           f'<circle cx="{cx}" cy="{cy}" r="126" fill="none" stroke="{color}" stroke-opacity=".12" '
           f'stroke-width="1" stroke-dasharray="2 6"/>']
    for i in range(8):
        on = i == hot
        out.append(f'<path d="{sector(cx, cy, 44, 112, i)}" fill="{color if on else "#1b2338"}" '
                   f'fill-opacity="{0.9 if on else 0.85}" stroke="{color}" stroke-opacity="{0.9 if on else 0.35}" '
                   f'stroke-width="1.2"{" filter=\"url(#glow)\"" if on else ""}/>')
        a = i * math.pi / 4
        x, y = cx + 78 * math.sin(a), cy - 78 * math.cos(a)
        out.append(f'<text x="{x:.1f}" y="{y + 6:.1f}" text-anchor="middle" font-family="{FONT}" font-size="17" '
                   f'font-weight="600" fill="{"#0b1020" if on else "#cdd6f4"}">{labels[i]}</text>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="38" fill="#0d1324" stroke="{color}" stroke-opacity=".6"/>')
    return "\n".join(out)


def build(lang):
    t = TEXT[lang]
    grid = "".join(f'<path d="M{x} 0V{H}" />' for x in range(0, W + 1, 40)) + \
        "".join(f'<path d="M0 {y}H{W}" />' for y in range(0, H + 1, 40))
    tags, x = [], 70
    for s in t["tags"]:
        w = 22 + len(s) * (17 if lang == "zh" else 8.6)
        tags.append(f'<rect x="{x}" y="276" rx="14" width="{w:.0f}" height="30" fill="#6ee7ff" fill-opacity=".08" '
                    f'stroke="#6ee7ff" stroke-opacity=".45"/>'
                    f'<text x="{x + w / 2:.0f}" y="296" text-anchor="middle" font-family="{FONT}" font-size="14.5" '
                    f'fill="#b9f3ff">{s}</text>')
        x += w + 12
    left = wheel(930, 210, ["ab", "ef", "ij", "mn", "qr", "uv", "yz", "'?"], 3, "#7c5cff")
    right = wheel(1150, 210, ["m", "", "n", "", "o", "", "p", ""], 2, "#6ee7ff")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#070b16"/><stop offset=".55" stop-color="#0d1430"/><stop offset="1" stop-color="#1a0f33"/></linearGradient>
  <radialGradient id="spot" cx=".78" cy=".5" r=".45"><stop offset="0" stop-color="#6ee7ff" stop-opacity=".18"/><stop offset="1" stop-color="#6ee7ff" stop-opacity="0"/></radialGradient>
  <linearGradient id="title" x1="0" x2="1"><stop offset="0" stop-color="#ffffff"/><stop offset=".6" stop-color="#b9f3ff"/><stop offset="1" stop-color="#a78bfa"/></linearGradient>
  <filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
</defs>
<rect width="{W}" height="{H}" rx="18" fill="url(#bg)"/>
<g stroke="#6ee7ff" stroke-opacity=".05" stroke-width="1">{grid}</g>
<rect width="{W}" height="{H}" rx="18" fill="url(#spot)"/>
<g font-family="{MONO}" font-size="13" fill="#6ee7ff" fill-opacity=".55">
  <text x="70" y="70">&gt; steam-wheel-keyboard --mode auto</text>
  <text x="70" y="92" fill-opacity=".35">[ok] gamepad: Steam Controller · dict: 884,175 entries · cpu 0.3%</text>
</g>
<text x="68" y="168" font-family="{FONT}" font-size="58" font-weight="800" letter-spacing="1" fill="url(#title)">STEAM WHEEL KEYBOARD</text>
<text x="70" y="222" font-family="{FONT}" font-size="26" font-weight="500" fill="#dbe4ff">{t["sub"]}</text>
<text x="70" y="254" font-family="{FONT}" font-size="15" fill="#8b95b8">{t["hint"]}</text>
{"".join(tags)}
<g font-family="{MONO}" font-size="12" fill="#8b95b8">
  <text x="70" y="370">WIN 10/11  ·  STEAM INPUT  ·  XINPUT / SDL2  ·  GPL-3.0</text>
</g>
{left}
{right}
<text x="930" y="216" text-anchor="middle" font-family="{FONT}" font-size="18" font-weight="700" fill="#a78bfa">L</text>
<text x="1150" y="216" text-anchor="middle" font-family="{FONT}" font-size="18" font-weight="700" fill="#6ee7ff">R</text>
<text x="1040" y="380" text-anchor="middle" font-family="{MONO}" font-size="12" fill="#8b95b8">LEFT STICK · GROUP        RIGHT STICK · KEY</text>
</svg>
'''


if __name__ == "__main__":
    for lang in TEXT:
        p = os.path.join(ROOT, "docs", f"banner-{lang}.svg")
        with open(p, "w", encoding="utf-8") as f:
            f.write(build(lang))
        print("saved", p)
