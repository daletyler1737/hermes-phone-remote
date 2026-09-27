"""配对反代路由回归：绝对式请求行 / 透传不许被 keep-alive 钉住 / Upgrade 不动。

跑法：python tests/test_pair_proxy_routing.py
真起一个反代 + 一个假上游，直接拿 socket 打 —— 这俩坑都是真实链路里才暴露的：
① cloudflared 发绝对式请求行（`GET https://host/pair/...`），老写法只认源站式，
   于是 /pair* 被当普通请求透传给面板，手机轮询拿到 302/登录页 → 永远「等待批准」；
② 透传是裸字节管道，上游 keep-alive 会把连接"钉"在面板上，同一条连接后续的
   /pair* 就不再过路由 → 第一次扫码卡住、过一会儿再扫才通。
ponytail: 纯 assert 脚本，不引测试框架。
"""
import importlib.util
import json
import os
import socket
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOK = "Abc-123_xyzDEF456ghi"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


seen_heads: list = []


def fake_upstream(port: int, stop: threading.Event) -> None:
    """假面板：把收到的请求头记下来，回一个能认出来的 body。"""
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(8)
    srv.settimeout(0.2)
    while not stop.is_set():
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            continue
        except OSError:
            break

        def serve(c: socket.socket) -> None:
            c.settimeout(5)
            buf = b""
            try:
                while b"\r\n\r\n" not in buf:
                    ch = c.recv(65536)
                    if not ch:
                        break
                    buf += ch
                seen_heads.append(buf)
                c.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 8\r\nContent-Type: text/plain\r\n\r\nUPSTREAM")
            except OSError:
                pass
            finally:
                c.close()

        threading.Thread(target=serve, args=(conn,), daemon=True).start()
    srv.close()


up_port, proxy_port = _free_port(), _free_port()
tmp = Path(tempfile.mkdtemp()) / "pair.json"
tmp.write_text(json.dumps({"token": TOK, "status": "pending", "created": time.time(),
                           "expires": time.time() + 600}), encoding="utf-8")
stop = threading.Event()
threading.Thread(target=fake_upstream, args=(up_port, stop), daemon=True).start()

os.environ["HPR_PORT"] = str(proxy_port)
os.environ["HPR_UPSTREAM"] = "127.0.0.1:%d" % up_port
os.environ["HPR_STATE"] = str(tmp)
_spec = importlib.util.spec_from_file_location("pair_proxy_rt", ROOT / "tools" / "pair_proxy.py")
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)
threading.Thread(target=m.main, daemon=True).start()


def _wait_port(p: int, t: float = 5.0) -> None:
    end = time.time() + t
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", p), timeout=0.3).close()
            return
        except OSError:
            time.sleep(0.05)
    raise AssertionError("反代没起来")


def talk(req: bytes, timeout: float = 3.0) -> bytes:
    """一个连接发一个请求，读到 EOF/超时为止。"""
    s = socket.create_connection(("127.0.0.1", proxy_port), timeout=5)
    s.settimeout(timeout)
    try:
        s.sendall(req + b"\r\nHost: h.example\r\n\r\n")
        buf = b""
        while True:
            ch = s.recv(65536)
            if not ch:
                break
            buf += ch
        return buf
    except OSError:
        return b""
    finally:
        s.close()


_wait_port(proxy_port)
time.sleep(0.2)

# 1) 绝对式请求行必须被认成 /pair（cloudflared 就这么发）
got = talk(b"GET https://x.trycloudflare.com/pair/state?t=" + TOK.encode() + b" HTTP/1.1")
assert b'"pending"' in got and b"UPSTREAM" not in got, got[:140]

# 2) 源站式照旧
got = talk(b"GET /pair/state?t=" + TOK.encode() + b" HTTP/1.1")
assert b'"pending"' in got, got[:140]

# 3) 透传请求要被改成 Connection: close（否则连接被 keep-alive 钉住，路由被绕开）
seen_heads.clear()
got = talk(b"GET /no-such-page HTTP/1.1")
assert b"UPSTREAM" in got, got[:80]
assert seen_heads, "上游没收到透传请求"
assert b"connection: close" in seen_heads[0].lower(), seen_heads[0][:200]

# 4) 同一条客户端连接：先透传，再发 /pair —— 第二个响应绝不能是面板的（裸转发就是老 bug）
s = socket.create_connection(("127.0.0.1", proxy_port), timeout=5)
s.settimeout(3)
first = b""
try:
    s.sendall(b"GET /no-such-page HTTP/1.1\r\nHost: h\r\n\r\n")
    while True:
        ch = s.recv(65536)
        if not ch:
            break
        first += ch
except OSError:
    pass
assert b"UPSTREAM" in first, first[:80]
second = b""
try:
    s.sendall(b"GET /pair/state?t=" + TOK.encode() + b" HTTP/1.1\r\nHost: h\r\n\r\n")
    while True:
        ch = s.recv(65536)
        if not ch:
            break
        second += ch
except OSError:
    pass
s.close()
assert b"UPSTREAM" not in second, second[:140]

# 5) Upgrade 请求原样放行（WebSocket 靠它）
up_head = m._one_shot(b"GET /ws HTTP/1.1\r\nHost: h\r\nUpgrade: websocket\r\nConnection: Upgrade")
assert b"Upgrade: websocket" in up_head and b"close" not in up_head.lower(), up_head

# 6) 普通请求里的 keep-alive / Proxy-Connection 被替换掉
h2 = m._one_shot(b"GET / HTTP/1.1\r\nHost: h\r\nProxy-Connection: keep-alive")
assert h2.lower().endswith(b"connection: close") and b"keep-alive" not in h2.lower(), h2

stop.set()
print("ok: 配对反代路由回归 6 项通过")
