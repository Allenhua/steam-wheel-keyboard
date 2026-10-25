"""界面语言（中文 / English）。

用法：set_lang("en" | "zh" | "auto")，界面文字统一经过 T() 翻译；查不到的原样返回
（候选词、字符等本来就不需要翻译）。带参数的句子写成模板：T("已连接 {n} 台设备").format(n=2)。
"""
import ctypes

LANG = "zh"

EN = {
    # 模式 / 标签
    "拼音": "Pinyin", "符号": "Symbols", "数字": "Numbers", "功能": "Func",
    "拼": "拼", "123": "123", "Fn": "Fn",
    # 符号组
    "括号": "Brackets", "运算": "Math", "标点": "Punct", "特殊": "Special", "中文标点": "CJK Punct",
    "引号": "Quotes", "货币单位": "Currency", "箭头": "Arrows",
    # 数字组
    "符号 ": "Symbols", "货币": "Currency", "一二三": "CN 1-8", "九十百": "CN 9+", "圈数字": "Circled",
    "年月日": "Date/Time",
    # 功能组
    "导航": "Navigate", "编辑": "Edit", "F9-12等": "F9-12+", "窗口": "Window", "媒体": "Media",
    "浏览器": "Browser", "选择": "Select",
    # 功能键
    "复制": "Copy", "粘贴": "Paste", "剪切": "Cut", "撤销": "Undo", "全选": "Sel All", "保存": "Save",
    "重做": "Redo", "查找": "Find", "截图": "Snip", "表情": "Emoji", "切窗": "Alt+Tab",
    "任务视图": "Task View", "桌面": "Desktop", "关闭": "Close", "任务管理": "Task Mgr",
    "资源管理": "Explorer", "剪贴板": "Clipboard", "运行": "Run", "手机输入": "Phone",
    "音量+": "Vol +", "音量-": "Vol -", "静音": "Mute", "播放": "Play", "上一曲": "Prev",
    "下一曲": "Next", "刷新": "Refresh", "全屏": "Full", "新标签": "New Tab", "关标签": "Close Tab",
    "下一页": "Next Tab", "上一页": "Prev Tab", "恢复": "Reopen", "地址栏": "Address", "后退": "Back",
    "前进": "Forward", "到开头": "Doc Start", "到结尾": "Doc End", "选至行首": "Sel Home",
    "选至行尾": "Sel End", "词左": "Word ←", "词右": "Word →", "选左字": "Sel ←", "选右字": "Sel →",
    # 中间按钮
    "空格": "Space", "退格": "Backspace", "回车": "Enter", "取消 / Esc": "Cancel / Esc",
    "大写锁定": "Caps Lock", "移动窗口": "Move", "收起键盘": "Hide", "手机扫码": "Phone QR",
    "功能页": "Func",
    # 提示
    "左摇杆 · 选组": "Left stick · group",
    "右摇杆 · 指向并松开输入": "Right stick · point & release",
    "右摇杆 · 选候选词": "Right stick · pick candidate",
    "LB/RB 切换模式 · R3 中英 · L3 大写 · L3+R3 收起/呼出 · LB+RB 移动窗口 · RT Tab/候选轮盘":
        "LB/RB mode · R3 CN/EN · L3 caps · L3+R3 hide/show · LB+RB move · RT Tab/candidate wheel",
    "左摇杆选组 → 右摇杆指向字母，松开输入拼音；A 选词  X 退格  Y 回车":
        "Left stick: group → right stick: letter, release to type Pinyin · A pick · X bksp · Y enter",
    "左摇杆选组 → 右摇杆指向字母，松开输入；LT 按住大写":
        "Left stick: group → right stick: letter, release to type · hold LT for Shift",
    "左摇杆选组 → 右摇杆指向符号，松开输入": "Left stick: group → right stick: symbol, release to type",
    "左摇杆选组 → 右摇杆指向功能键 / 快捷键，松开执行":
        "Left stick: group → right stick: key / shortcut, release to run",
    "移动模式：摇杆移动 · 十字键贴边 · Y 居中 · LB/RB 缩小/放大 · A 确定":
        "Move mode: sticks move · D-pad snap · Y center · LB/RB resize · A done",
    "已输入  ": "Typed  ",
    # 手机面板
    "手机扫码远程输入": "Type from your phone",
    "① 手机和电脑连到同一个 Wi-Fi": "① Connect phone and PC to the same Wi-Fi",
    "② 用手机相机或微信扫左边的二维码": "② Scan the QR code with your phone camera",
    "③ 在手机网页里打字，点【发送】（支持中文、语音）": "③ Type on the web page and tap Send (any IME, voice)",
    "正在检测网络地址…": "Detecting network address…",
    "（二维码库未安装）": "(QR library not installed)",
    "● 已连接 {n} 台设备，现在可以在手机上打字了": "● {n} device(s) connected — start typing on your phone",
    "○ 等待手机连接…": "○ Waiting for phone…",
    "地址 {i}/{n}：手机打不开就按 X 换一个地址": "Address {i}/{n}: press X to try another if it won't open",
    "还是连不上：在 Windows 防火墙弹窗里勾选【专用网络】和【公用网络】并点允许":
        "Still nothing? Allow the app in Windows Firewall (Private and Public networks)",
    "换地址  X": "Next  X", "隐藏  A / B": "Hide  A / B", "停止手机输入  Y": "Stop  Y",
    # 状态 / 提示
    "Steam 模式": "Steam mode", "直连模式": "Direct mode", "无手柄": "no gamepad",
    "XInput 手柄 ×{n}": "XInput pad ×{n}", "手机 {n} 台": "phone ×{n}", "按下 {b}": "pressed {b}",
    "词库加载中…": "Loading dictionary…", "词库已加载": "Dictionary loaded",
    "手机输入启动失败": "Phone input failed to start", "手机输入已停止": "Phone input stopped",
    "未找到拼音词库：请先运行  python build_dict.py --download":
        "Pinyin dictionary missing: run  python build_dict.py --download",
    "未检测到手柄 — 请从 Steam 启动本程序（见 README），现在可用触摸板/鼠标点选":
        "No gamepad — launch this app from Steam (see README); mouse/trackpad works meanwhile",
}


def detect():
    """Windows 界面语言是中文就用中文，否则英文。"""
    try:
        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return "zh" if (lid & 0x3FF) == 0x04 else "en"
    except Exception:
        return "zh"


def set_lang(lang):
    global LANG
    LANG = detect() if lang in (None, "", "auto") else ("en" if str(lang).lower().startswith("en") else "zh")
    return LANG


def T(s):
    if LANG == "en" and isinstance(s, str):
        return EN.get(s, s)
    return s
