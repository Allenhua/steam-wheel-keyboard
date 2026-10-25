"""简易拼音输入法引擎：SQLite 大词库(按需查询，省内存) + 整句切分(Viterbi) + 首字母缩写 + 最长前缀部分上屏 + 个人词频学习。"""
import json
import math
import os
import sqlite3
from collections import OrderedDict


class PinyinEngine:
    SEG_PENALTY = 12.0   # 整句切分：每多切一个词的惩罚
    LEN_BONUS = 3.0      # 整句切分：词越长越好
    CACHE_SIZE = 6000

    def __init__(self, dict_path, user_path=None):
        self.dict_path = dict_path                                  # data/dict.txt（可读源文件，可选）
        self.db_path = os.path.splitext(dict_path)[0] + ".db"       # data/dict.db（运行时词库）
        self.user_path = user_path
        self.con = None
        self.user = {}       # "key|word" -> 次数
        self._dirty = 0
        self._cache = OrderedDict()
        self._comp_cache = OrderedDict()
        self.loaded = False

    # ---------- 加载 / 保存 ----------
    def load(self):
        if not os.path.exists(self.db_path) and os.path.exists(self.dict_path):
            try:
                import build_dict
                build_dict.build_db_from_txt(self.dict_path, self.db_path)   # 只有源文件时现场生成（约十几秒）
            except Exception:
                return False
        if not os.path.exists(self.db_path):
            return False
        try:
            self.con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, check_same_thread=False)
            self.con.execute("PRAGMA cache_size=-4096")        # 页缓存约 4MB
            self.con.execute("SELECT 1 FROM k LIMIT 1")
        except sqlite3.Error:
            self.con = None
            return False
        self._load_user()
        self.loaded = True
        return True

    def _load_user(self):
        if self.user_path and os.path.exists(self.user_path):
            try:
                with open(self.user_path, encoding="utf-8") as f:
                    self.user = json.load(f)
            except Exception:
                self.user = {}

    def save(self):
        if not self.user_path or not self._dirty:
            return
        try:
            with open(self.user_path, "w", encoding="utf-8") as f:
                json.dump(self.user, f, ensure_ascii=False)
            self._dirty = 0
        except OSError:
            pass

    def learn(self, buf, word):
        key = buf.replace("'", "")
        k = f"{key}|{word}"
        self.user[k] = self.user.get(k, 0) + 1
        self._dirty += 1
        if self._dirty >= 5:
            self.save()

    # ---------- 词库查询（带小缓存） ----------
    def _entries(self, key):
        """该拼音对应的词（分数降序，最多 60 个）。"""
        c = self._cache.get(key)
        if c is not None:
            self._cache.move_to_end(key)
            return c
        rows = self.con.execute("SELECT word, score FROM w WHERE key=? ORDER BY score DESC LIMIT 60", (key,)).fetchall()
        self._cache[key] = rows
        if len(self._cache) > self.CACHE_SIZE:
            self._cache.popitem(last=False)
        return rows

    def _initials(self, key, n):
        return self.con.execute("SELECT word, score FROM ini WHERE key=? ORDER BY score DESC LIMIT ?", (key, n)).fetchall()

    def _completions(self, key, n=8):
        """以 key 开头的更长拼音里，分数最高的词（补全）。"""
        c = self._comp_cache.get(key)
        if c is None:
            c = [r[0] for r in self.con.execute(
                "SELECT word FROM k WHERE key > ? AND key < ? ORDER BY score DESC LIMIT ?",
                (key, key + "￿", n)).fetchall()]
            self._comp_cache[key] = c
            if len(self._comp_cache) > 500:
                self._comp_cache.popitem(last=False)
        return c

    # ---------- 排序 ----------
    def _ranked(self, key, entries, n):
        """取前 n 个词；用户选过的词会被抬到前面（选一次就超过原来的第一名）。"""
        if not entries:
            return []
        unit = max(entries[0][1] * 1.2, 1e4)
        ranked = [(s + unit * self.user.get(f"{key}|{w}", 0), w) for w, s in entries[:60]]
        ranked.sort(key=lambda e: -e[0])
        return ranked[:n]

    def _top(self, key, entries, n):
        return [w for _, w in self._ranked(key, entries, n)]

    def _sentence(self, key, bounds, max_seg=36):
        """一元模型 Viterbi：把整串拼音切成最可能的词序列，返回整句；切不开返回 None。"""
        n = len(key)
        if n < 3:
            return None
        cut = set(bounds)
        NEG = -1e18
        best = [NEG] * (n + 1)
        back = [None] * (n + 1)
        best[0] = 0.0
        for i in range(1, n + 1):
            for j in range(max(0, i - max_seg), i):
                if best[j] == NEG or any(j < b < i for b in cut):
                    continue
                sub = key[j:i]
                ent = self._entries(sub)
                if not ent:
                    continue
                score, word = self._ranked(sub, ent, 1)[0]
                sc = best[j] + math.log(score + 1.0) - self.SEG_PENALTY + self.LEN_BONUS * (len(word) - 1)
                if sc > best[i]:
                    best[i], back[i] = sc, (j, word)
        if best[n] == NEG:
            return None
        out, i = [], n
        while i > 0:
            j, w = back[i]
            out.append(w)
            i = j
        out.reverse()
        return "".join(out) if len(out) >= 2 else None

    def candidates(self, buf, limit=48):
        """返回 [(词, 消耗的 buf 长度)]。最后一项总是原始拼音本身。"""
        if not buf:
            return []
        if not self.loaded:
            return [(buf, len(buf))]
        clean, pos = [], []
        for i, ch in enumerate(buf):
            if ch != "'":
                clean.append(ch)
                j = i + 1
                while j < len(buf) and buf[j] == "'":
                    j += 1
                pos.append(j)
        key = "".join(clean)
        n = len(key)
        res, seen = [], set()

        def add(word, used):
            if word not in seen and len(res) < limit:
                seen.add(word)
                res.append((word, used))

        raw_len = len(buf)
        # 撇号 = 强制音节边界（xi'an）：第一个边界之前的部分单独处理
        bounds = sorted({sum(1 for c in buf[:i] if c != "'") for i, c in enumerate(buf) if c == "'"})
        bounds = [b for b in bounds if 0 < b < n]
        first = bounds[0] if bounds else n
        sentence = self._sentence(key, bounds)

        exact_full = self._top(key, self._entries(key), 24)
        if bounds:
            # xi'an：撇号分出了 N 段，词至少要有 N 个字，这样 "西安" 保留、"先" 排除
            exact_full = [w for w in exact_full if len(w) >= len(bounds) + 1][:14]
        else:
            exact_full = exact_full[:14]
            # 单音节（xian）：常用单字（先/现）排在多字词（西安）前面
            chars = [w for w in exact_full if len(w) == 1][:3]
            if chars:
                exact_full = chars + [w for w in exact_full if w not in chars]
        for w in exact_full[:2]:
            add(w, raw_len)
        if sentence:
            add(sentence, raw_len)
        for w in exact_full[2:]:
            add(w, raw_len)
        # 缩写（nh -> 你好）
        if not bounds and 2 <= n <= 6:
            for w in self._top(key, self._initials(key, 12), 6):
                add(w, raw_len)
        # 最长前缀切分：nihaoma -> 你好 + ma
        for k in range(first if bounds else n - 1, 0, -1):
            sub = key[:k]
            if k == 1 and sub in ("n", "m", "g", "h"):
                continue
            ent = self._entries(sub)
            if ent:
                for w in self._top(sub, ent, 3):
                    add(w, pos[k - 1])
        # 补全：ni -> 你们 / 你好 ...
        if len(res) < 24 and n >= 2:
            for w in self._completions(key):
                add(w, raw_len)
        # 保证原始拼音在最后
        res = [r for r in res if r[0] != buf] + [(buf, raw_len)]
        return res
