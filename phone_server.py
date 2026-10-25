"""手机扫码远程输入：电脑上起一个局域网小网页，手机扫码打开后用手机输入法打字，文字注入电脑当前焦点窗口。

安全：每次开启都会生成随机口令，写进二维码里的网址；没有口令的请求一律拒绝；关闭后服务立即停止。
线程：HTTP 服务在后台线程，只把"要做的事"放进队列，真正的按键注入由主线程完成。
"""
import hmac
import json
import queue
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

MAX_BODY = 40_000
MAX_TEXT = 8_000

KEYS = {"backspace", "enter", "space", "tab", "esc", "left", "right", "up", "down", "home", "end",
        "pgup", "pgdn", "del", "selectall", "copy", "paste", "cut", "undo", "redo"}


def lan_addresses(use_gateway=True):
    """按"最可能是手机能访问到的"排序的本机 IPv4 地址列表。
    use_gateway=True 会调用 PowerShell 找出"有默认网关"的网卡（准但慢，要几秒）；False 只用快速启发式。"""
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    default = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 9))          # 不会真的发包，只用来问系统"走哪张网卡"
        default = s.getsockname()[0]
        s.close()
        ips.add(default)
    except OSError:
        pass

    # 有"默认网关"的网卡才是真正连着路由器的（虚拟网卡 / 蓝牙 / 热点网卡通常没有）
    gateway_ips = set()
    try:
        if not use_gateway:
            raise RuntimeError("skip")
        import subprocess
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway } | "
             "ForEach-Object { $_.IPv4Address.IPAddress }"],
            capture_output=True, text=True, timeout=6, creationflags=0x08000000).stdout
        gateway_ips = {x.strip() for x in out.split() if x.count(".") == 3}
    except Exception:
        pass
    ips |= gateway_ips

    def score(ip):
        a = [int(x) for x in ip.split(".")]
        if ip.startswith("127.") or ip.startswith("169.254.") or ip.startswith("198.18.") or ip.startswith("0."):
            return -100
        s = 0
        if ip in gateway_ips:
            s += 12
        if ip.startswith("192.168.") or ip.startswith("10.") or (a[0] == 172 and 16 <= a[1] <= 31):
            s += 10
        if a[3] == 1:
            s -= 6                      # 虚拟网卡 / 网关地址常常是 x.x.x.1
        if ip == default:
            s += 4
        return s

    return sorted((ip for ip in ips if score(ip) > -50), key=lambda ip: -score(ip))


class _ExclusiveServer(ThreadingHTTPServer):
    """独占端口：Windows 默认允许多个程序绑定同一端口（SO_REUSEADDR），那样别的进程可以蹭/劫持流量。"""
    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self):
        try:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        except (AttributeError, OSError):
            pass
        super().server_bind()


class PhoneServer:
    def __init__(self):
        self.token = secrets.token_urlsafe(6)
        self.events = queue.Queue()
        self.seen = {}                       # ip -> 最后一次心跳时间
        self.httpd = None
        self.thread = None
        self.port = 0
        self.addrs = []
        self.idx = 0
        self.running = False
        self.error = ""
        self.version = 0          # 地址列表变化时 +1，界面据此刷新二维码
        self.user_chose = False
        self.ready = False        # 后台精确挑选网卡完成之前为 False

    # ---------- 生命周期 ----------
    def start(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/json; charset=utf-8"):
                data = body if isinstance(body, bytes) else body.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def _auth(self):
                k = parse_qs(urlparse(self.path).query).get("k", [""])[0]
                return hmac.compare_digest(k.encode(), outer.token.encode())

            def do_GET(self):
                path = urlparse(self.path).path
                if path == "/":
                    if not self._auth():
                        return self._send(403, "<meta charset=utf-8><h3>请用电脑上显示的二维码打开</h3>",
                                          "text/html; charset=utf-8")
                    outer.seen[self.client_address[0]] = time.time()
                    return self._send(200, PAGE, "text/html; charset=utf-8")
                if path == "/api/ping":
                    if not self._auth():
                        return self._send(403, '{"ok":false}')
                    outer.seen[self.client_address[0]] = time.time()
                    return self._send(200, json.dumps({"ok": True, "clients": outer.clients()}))
                self._send(404, '{"ok":false}')

            def do_POST(self):
                path = urlparse(self.path).path
                if not self._auth():
                    return self._send(403, '{"ok":false}')
                try:
                    n = int(self.headers.get("Content-Length", "0"))
                    if n > MAX_BODY:
                        return self._send(413, '{"ok":false}')
                    body = json.loads(self.rfile.read(n) or b"{}")
                except Exception:
                    return self._send(400, '{"ok":false}')
                outer.seen[self.client_address[0]] = time.time()
                if path == "/api/type":
                    bs = max(0, min(200, int(body.get("bs", 0) or 0)))
                    text = str(body.get("text", ""))[:MAX_TEXT]
                    if bs or text:
                        outer.events.put(("type", bs, text))
                    return self._send(200, '{"ok":true}')
                if path == "/api/key":
                    key = str(body.get("key", ""))
                    if key in KEYS:
                        outer.events.put(("key", key))
                        return self._send(200, '{"ok":true}')
                return self._send(400, '{"ok":false}')

        last = None
        for port in list(range(8765, 8785)) + [0]:
            try:
                self.httpd = _ExclusiveServer(("0.0.0.0", port), Handler)
                break
            except OSError as e:
                last = e
        if self.httpd is None:
            self.error = f"无法开启服务：{last}"
            return False
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.addrs = lan_addresses(False) or ["127.0.0.1"]       # 先用快速结果，立刻可用
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.running = True
        threading.Thread(target=self._refine_addrs, daemon=True).start()
        return True

    def _refine_addrs(self):
        """后台用"默认网关"精确挑选真正连路由器的网卡；用户已手动换过地址就不再改动。"""
        try:
            better = lan_addresses(True)
            if better and better != self.addrs and not self.user_chose:
                self.addrs, self.idx = better, 0
        finally:
            self.ready = True          # 地址确定了，界面才显示二维码
            self.version += 1

    def stop(self):
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
        self.httpd, self.running = None, False

    # ---------- 状态 ----------
    def clients(self):
        now = time.time()
        return sum(1 for t in self.seen.values() if now - t < 6)

    @property
    def url(self):
        if not self.running:
            return ""
        return f"http://{self.addrs[self.idx % len(self.addrs)]}:{self.port}/?k={self.token}"

    def next_addr(self):
        self.user_chose = True
        if self.addrs:
            self.idx = (self.idx + 1) % len(self.addrs)

    def drain(self):
        out = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                return out


_VK = {"backspace": 0x08, "enter": 0x0D, "space": 0x20, "tab": 0x09, "esc": 0x1B, "left": 0x25, "up": 0x26,
       "right": 0x27, "down": 0x28, "home": 0x24, "end": 0x23, "pgup": 0x21, "pgdn": 0x22, "del": 0x2E}
_CTRL = {"selectall": 0x41, "copy": 0x43, "paste": 0x56, "cut": 0x58, "undo": 0x5A, "redo": 0x59}


def apply_event(sink, ev):
    """在主线程里执行手机发来的一个事件；返回要显示在输入栏里的文字（可为空）。"""
    if ev[0] == "key":
        name = ev[1]
        if name in _CTRL:
            sink.combo((0x11, _CTRL[name]))
        elif name in _VK:
            sink.key(_VK[name])
        return ""
    _, bs, text = ev
    for _ in range(bs):
        sink.key(_VK["backspace"])
    shown = ""
    buf = ""
    for ch in text.replace("\r\n", "\n").replace("\r", "\n"):
        if ch in "\n\t":
            if buf:
                sink.text(buf)
                shown += buf
                buf = ""
            sink.key(_VK["enter"] if ch == "\n" else _VK["tab"])
        elif ch >= " ":
            buf += ch
    if buf:
        sink.text(buf)
        shown += buf
    return shown


PAGE = r"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>轮盘键盘 · 手机输入</title>
<style>
:root{--bg:#14161c;--card:#1e2230;--line:#2c3246;--txt:#eef1f8;--mut:#8b93a8;--acc:#4f86f7;--ok:#3fb27f;--bad:#e5534b}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;background:var(--bg);color:var(--txt);font:16px/1.4 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
body{padding:12px 14px 24px;max-width:640px;margin:0 auto;user-select:none}
header{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
h1{font-size:17px;margin:0}
.st{font-size:13px;color:var(--mut)} .st b{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--bad);margin-right:6px}
.st.on b{background:var(--ok)}
textarea{width:100%;height:150px;resize:none;border-radius:14px;border:1px solid var(--line);background:var(--card);color:var(--txt);
 padding:12px;font:inherit;font-size:18px;outline:none;user-select:text;-webkit-user-select:text}
textarea:focus{border-color:var(--acc)}
.row{display:flex;gap:8px;margin-top:8px}
button{flex:1;padding:13px 6px;border-radius:12px;border:1px solid var(--line);background:var(--card);color:var(--txt);font:inherit;font-size:15px;touch-action:manipulation}
button:active{background:#2b3350}
button.pri{background:var(--acc);border-color:var(--acc);color:#fff;font-weight:600}
.sw{display:flex;align-items:center;justify-content:space-between;margin-top:10px;padding:10px 12px;border-radius:12px;background:var(--card);border:1px solid var(--line);font-size:14px}
.sw small{color:var(--mut);display:block;font-size:12px}
input[type=checkbox]{width:44px;height:26px;appearance:none;-webkit-appearance:none;background:#3a4258;border-radius:13px;position:relative;outline:none}
input[type=checkbox]::after{content:"";position:absolute;left:3px;top:3px;width:20px;height:20px;border-radius:50%;background:#fff;transition:.15s}
input[type=checkbox]:checked{background:var(--acc)} input[type=checkbox]:checked::after{left:21px}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:8px}
.sec{margin:14px 2px 0;font-size:12px;color:var(--mut)}
</style></head><body>
<header><h1>轮盘键盘 · 手机输入</h1><div class="st" id="st"><b></b><span>连接中…</span></div></header>
<textarea id="box" placeholder="在这里打字（可用手机自带输入法、语音输入）" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false"></textarea>
<div class="row"><button id="clr">清空</button><button id="sendEnter">发送并回车</button><button class="pri" id="send">发送</button></div>
<div class="sw"><div>实时输入<small>开：边打边同步到电脑；关：点"发送"才发</small></div><input type="checkbox" id="live"></div>

<div class="sec">常用键（长按可连发）</div>
<div class="grid">
<button data-k="backspace" data-rep="1">退格</button><button data-k="enter">回车</button><button data-k="space">空格</button><button data-k="tab">Tab</button>
<button data-k="left" data-rep="1">←</button><button data-k="up" data-rep="1">↑</button><button data-k="down" data-rep="1">↓</button><button data-k="right" data-rep="1">→</button>
<button data-k="home">Home</button><button data-k="end">End</button><button data-k="del" data-rep="1">Del</button><button data-k="esc">Esc</button>
</div>
<div class="sec">编辑</div>
<div class="grid">
<button data-k="selectall">全选</button><button data-k="copy">复制</button><button data-k="paste">粘贴</button><button data-k="cut">剪切</button>
<button data-k="undo">撤销</button><button data-k="redo">重做</button><button data-k="pgup">PgUp</button><button data-k="pgdn">PgDn</button>
</div>
<script>
const K=new URLSearchParams(location.search).get('k')||'';
const $=id=>document.getElementById(id), box=$('box'), st=$('st');
function setSt(on,n){st.className='st'+(on?' on':'');st.lastChild.textContent=on?('已连接 · '+(n||1)+' 台设备'):'连接断开，重连中…'}
async function api(p,b){try{const r=await fetch(p+'?k='+encodeURIComponent(K),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
 const j=await r.json();setSt(j.ok);return j.ok}catch(e){setSt(false);return false}}
async function ping(){try{const r=await fetch('/api/ping?k='+encodeURIComponent(K));const j=await r.json();setSt(j.ok,j.clients)}catch(e){setSt(false)}}
setInterval(ping,2000);ping();
let prev='',composing=false;
function sync(){
  const a=Array.from(prev),b=Array.from(box.value);let p=0;const m=Math.min(a.length,b.length);
  while(p<m&&a[p]===b[p])p++;
  const bs=a.length-p,add=b.slice(p).join('');
  prev=box.value;if(bs||add)api('/api/type',{bs:bs,text:add});
}
box.addEventListener('compositionstart',()=>{composing=true});
box.addEventListener('compositionend',()=>{composing=false;setTimeout(()=>{if($('live').checked)sync()},0)});
box.addEventListener('input',e=>{if($('live').checked&&!composing&&!e.isComposing)sync()});
$('live').addEventListener('change',()=>{box.value='';prev='';box.focus();try{localStorage.live=$('live').checked?1:''}catch(e){}});
try{$('live').checked=!!localStorage.live}catch(e){}
async function sendAll(enter){
  const t=box.value;
  if($('live').checked){ if(enter)await api('/api/key',{key:'enter'}); return }
  if(t){ if(!await api('/api/type',{bs:0,text:t}))return }
  if(enter)await api('/api/key',{key:'enter'});
  box.value='';prev='';
}
$('send').onclick=()=>sendAll(false);$('sendEnter').onclick=()=>sendAll(true);
$('clr').onclick=()=>{box.value='';prev='';box.focus()};
document.querySelectorAll('[data-k]').forEach(btn=>{
  let t1=null,t2=null;const fire=()=>api('/api/key',{key:btn.dataset.k});
  const stop=()=>{clearTimeout(t1);clearInterval(t2)};
  btn.addEventListener('pointerdown',e=>{e.preventDefault();fire();if(btn.dataset.rep){t1=setTimeout(()=>{t2=setInterval(fire,70)},380)}});
  ['pointerup','pointerleave','pointercancel'].forEach(ev=>btn.addEventListener(ev,stop));
  btn.addEventListener('contextmenu',e=>e.preventDefault());
});
</script></body></html>
"""
