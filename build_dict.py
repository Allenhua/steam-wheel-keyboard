"""生成拼音词库：data/dict.db（运行时用的 SQLite）+ data/dict.txt（可读的源文件）。

数据来源：雾凇拼音 rime-ice（https://github.com/iDvel/rime-ice ，GPL-3.0）的
  cn_dicts/8105.dict.yaml  常用 8105 字（含多音字各自的权重）
  cn_dicts/base.dict.yaml  基础词库（约 54 万词，已校对词频与注音）
  cn_dicts/ext.dict.yaml   扩展词库（约 34 万长词）

用法：
  python build_dict.py --download         自动下载上面三个文件（约 28MB）并生成词库（推荐）
  python build_dict.py <目录>             用你已有的、放着三个 .dict.yaml 的目录生成
  python build_dict.py --jieba            （备用）用 jieba + pypinyin 生成一个小词库，需 pip install jieba pypinyin
"""
import os
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__)) if not getattr(sys, "frozen", False) \
    else os.path.dirname(sys.executable)
OUT_TXT = os.path.join(BASE, "data", "dict.txt")
RIME_URL = "https://raw.githubusercontent.com/iDvel/rime-ice/main/cn_dicts/{}.dict.yaml"
RIME_FILES = ("8105", "base", "ext")

CHAR_SCALE = 0.005        # 单字权重量级比词大得多，压一下，避免整句被切成一堆单字
EXT_WEIGHT_CAP = 100      # ext 词库本身都是 100
INITIALS_MIN_WEIGHT = 3000


def _cjk(s):
    return bool(s) and all("一" <= c <= "鿿" for c in s)


def read_rime(path):
    """逐行产出 (词, [音节], 权重)。"""
    started = False
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not started:
                if line.strip() == "...":
                    started = True
                continue
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            word, py = parts[0], parts[1].strip().lower().split()
            try:
                w = int(parts[2])
            except ValueError:
                continue
            if not _cjk(word) or len(word) != len(py):
                continue
            if not all(p.isascii() and p.isalpha() for p in py):
                continue
            yield word, py, w


def build_from_rime(src_dir, log=print):
    t0 = time.time()
    entries = {}   # (word, "py py") -> score

    def put(word, py, score):
        k = (word, " ".join(py))
        if score > entries.get(k, 0):
            entries[k] = score

    for word, py, w in read_rime(os.path.join(src_dir, "8105.dict.yaml")):
        put(word, py, max(w, 1) * CHAR_SCALE + 1)
    n1 = len(entries)
    for word, py, w in read_rime(os.path.join(src_dir, "base.dict.yaml")):
        put(word, py, w)
    n2 = len(entries)
    ext_path = os.path.join(src_dir, "ext.dict.yaml")
    if os.path.exists(ext_path):
        for word, py, w in read_rime(ext_path):
            put(word, py, min(w, EXT_WEIGHT_CAP))
    log(f"单字 {n1}，+基础词 {n2 - n1}，+扩展词 {len(entries) - n2}，共 {len(entries)} 条，用时 {time.time() - t0:.1f}s")
    return entries


def build_from_jieba(log=print):
    import jieba
    from pypinyin import Style, lazy_pinyin, pinyin
    entries = {}
    src = os.path.join(os.path.dirname(jieba.__file__), "dict.txt")
    with open(src, encoding="utf-8") as f:
        for line in f:
            p = line.split()
            if len(p) < 2 or not _cjk(p[0]) or len(p[0]) < 2 or int(p[1]) < 8:
                continue
            py = lazy_pinyin(p[0], style=Style.NORMAL, errors="ignore")
            if len(py) == len(p[0]):
                entries[(p[0], " ".join(py))] = float(p[1])
    for hi in range(0xB0, 0xF8):
        for lo in range(0xA1, 0xFF):
            try:
                ch = bytes([hi, lo]).decode("gb2312")
            except UnicodeDecodeError:
                continue
            for r in pinyin(ch, style=Style.NORMAL, heteronym=True)[0]:
                entries[(ch, r)] = 5.0
    return entries


OUT_DB = os.path.join(BASE, "data", "dict.db")


def write_db(items, db_path=OUT_DB):
    """生成运行时用的 SQLite 词库：按需查询，不占内存。items 为 [((词, 拼音), 分数)]，需已按分数降序。"""
    import sqlite3
    tmp = db_path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
    con.executescript("""
        PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;
        CREATE TABLE w(key TEXT NOT NULL, word TEXT NOT NULL, score REAL NOT NULL, PRIMARY KEY(key, word)) WITHOUT ROWID;
        CREATE TABLE k(key TEXT PRIMARY KEY, word TEXT NOT NULL, score REAL NOT NULL) WITHOUT ROWID;
        CREATE TABLE ini(key TEXT NOT NULL, word TEXT NOT NULL, score REAL NOT NULL);
    """)
    rows_w, best, rows_i = [], {}, []
    for (word, py), score in items:
        syl = py.split(" ")
        key = "".join(syl)
        rows_w.append((key, word, score))
        if key not in best:                    # items 已降序，第一次出现的就是该 key 的最高分
            best[key] = (word, score)
        if 2 <= len(syl) <= 5 and score >= INITIALS_MIN_WEIGHT:
            rows_i.append(("".join(s[0] for s in syl), word, score))
    con.executemany("INSERT OR IGNORE INTO w VALUES(?,?,?)", rows_w)
    con.executemany("INSERT INTO k VALUES(?,?,?)", ((k_, w_, s_) for k_, (w_, s_) in best.items()))
    con.executemany("INSERT INTO ini VALUES(?,?,?)", rows_i)
    con.execute("CREATE INDEX ini_key ON ini(key)")
    con.commit()
    con.execute("VACUUM")
    con.close()
    os.replace(tmp, db_path)


def write_outputs(entries, log=print):
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    items = sorted(entries.items(), key=lambda kv: -kv[1])
    with open(OUT_TXT + ".tmp", "w", encoding="utf-8") as f:
        for (word, py), score in items:
            f.write(f"{word}\t{py}\t{score:.1f}\n")
    os.replace(OUT_TXT + ".tmp", OUT_TXT)
    write_db(items)
    log(f"已写入 {OUT_TXT}（可读源文件）和 {OUT_DB}（运行时词库）")


def build_db_from_txt(txt_path=OUT_TXT, db_path=OUT_DB):
    """已有 dict.txt 但没有 dict.db 时，直接从文本生成数据库。"""
    items = []
    with open(txt_path, encoding="utf-8") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) == 3:
                items.append(((p[0], p[1]), float(p[2])))
    items.sort(key=lambda kv: -kv[1])
    write_db(items, db_path)


def build(src_dir=None, log=print):
    if src_dir is None:
        entries = build_from_jieba(log)
    else:
        entries = build_from_rime(src_dir, log)
    write_outputs(entries, log)


def download_rime(dest, log=print):
    """把 rime-ice 的三个词库文件下载到 dest 目录。"""
    os.makedirs(dest, exist_ok=True)
    for name in RIME_FILES:
        url = RIME_URL.format(name)
        path = os.path.join(dest, f"{name}.dict.yaml")
        log(f"下载 {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "SteamWheelKeyboard-build"})
        with urllib.request.urlopen(req, timeout=120) as r, open(path + ".tmp", "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        os.replace(path + ".tmp", path)
    return dest


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--jieba":
        build(None)
    elif len(sys.argv) > 1 and sys.argv[1] == "--download":
        src = download_rime(os.path.join(BASE, "data", "rime_src"))
        build(src)
    elif len(sys.argv) > 1:
        build(sys.argv[1])
    else:
        print(__doc__)
