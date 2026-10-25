"""手机输入服务自测：真的起服务，用 HTTP 发请求，检查口令校验、事件入队、按键映射。
运行（在项目根目录）：python tests/test_phone.py"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phone_server import PhoneServer, apply_event, lan_addresses   # noqa: E402
from sender import RecordingSink                                   # noqa: E402

bad = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name, extra)
    if not cond:
        bad.append(name)


def http(method, url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


srv = PhoneServer()
check("服务启动", srv.start(), f"port={srv.port} addrs={srv.addrs}")
# 独占端口：同一个端口不能被第二个服务绑定（端口被别的程序占用时应自动换下一个）
srv2 = PhoneServer()
srv2.start()
check("端口独占（第二个服务自动换端口）", srv2.port != srv.port, f"{srv.port} vs {srv2.port}")
srv2.stop()
t0 = time.time()
while not srv.ready and time.time() - t0 < 15:
    time.sleep(0.2)
check("网卡地址精确挑选完成（ready）", srv.ready, f"{time.time() - t0:.1f}s -> {srv.addrs}")
base = f"http://127.0.0.1:{srv.port}"
k = srv.token
print("  LAN 地址（按推荐顺序）:", lan_addresses())
print("  二维码网址:", srv.url)

code, body = http("GET", base + "/")
check("无口令访问首页被拒绝", code == 403, str(code))
code, body = http("GET", base + f"/?k=wrong")
check("错误口令被拒绝", code == 403)
code, body = http("GET", base + f"/?k={k}")
check("正确口令返回页面", code == 200 and "textarea" in body and "手机输入" in body, f"{code} {len(body)}B")
code, body = http("POST", base + "/api/type", {"bs": 0, "text": "你好"})
check("无口令 POST 被拒绝", code == 403)
code, body = http("POST", base + f"/api/type?k={k}", {"bs": 2, "text": "世界\nabc"})
check("POST 文字", code == 200, body)
code, body = http("POST", base + f"/api/key?k={k}", {"key": "paste"})
check("POST 按键", code == 200, body)
code, body = http("POST", base + f"/api/key?k={k}", {"key": "format_c"})
check("非法按键被拒绝", code == 400, str(code))
code, body = http("GET", base + f"/api/ping?k={k}")
check("心跳与连接数", code == 200 and json.loads(body)["clients"] >= 1, body)

sink = RecordingSink()
for ev in srv.drain():
    apply_event(sink, ev)
print("  注入的动作:", sink.out)
check("退格×2 + 文字 + 回车 + 文字 + Ctrl+V",
      sink.out == [("key", 8), ("key", 8), ("text", "世界"), ("key", 13), ("text", "abc"), ("combo", (0x11, 0x56))],
      str(sink.out))
srv.stop()
time.sleep(0.2)
try:
    http("GET", base + f"/api/ping?k={k}")
    check("停止后端口关闭", False)
except Exception:
    check("停止后端口关闭", True)
print("\n全部通过" if not bad else f"\n有失败项: {bad}")
sys.exit(1 if bad else 0)
