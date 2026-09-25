#!/usr/bin/env python3
"""手机扫码配对反代 (Phone pairing reverse proxy)。

为什么需要它：Hermes 官方 dashboard 的 auth gate 拦下所有插件路由（公开白名单只有
``/login``、``/auth/*``、几个静态目录），公网隧道域名下没有一个"任何人都能打开"的页面
能给手机种登录 cookie。所以「扫码 → 电脑批准 → 手机免密进去」这件事只能自己做一层：
本进程只接管 ``/pair*``，其余请求原样 TCP 透传给 dashboard。

职责
----
``/pair?t=TOKEN``      等待批准页（手机打开）
``/pair/state?t=TOKEN`` 轮询状态 JSON
``/pair/claim?t=TOKEN`` 批准后签发官方 session cookie 并 302 进主页（一次性）
其它一切               原样透传（chunked / SSE / WebSocket 都不受影响）

安全模型（对齐用户红线「不要永久不变 安全性要高」「每次 token 要变」）
------------------------------------------------------------------
* token 32 字符随机，每次生成都覆盖旧的（生成即失效），默认 10 分钟有效
* 必须电脑端点「批准」才签发 cookie；claim 一次即焚
* cookie 值用官方 ``BasicAuthProvider`` 签发（同一 HMAC secret），因此官方 auth 认它
* 只监听 127.0.0.1；对外只有 cloudflared 隧道能碰到它

跑法：``python pair_proxy.py``；环境变量 ``HPR_PORT`` / ``HPR_UPSTREAM`` / ``HPR_STATE``。
"""
from __future__ import annotations

import hmac
import json
import os
import re
import select
import socket
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

PORT = int(os.environ.get("HPR_PORT") or 9121)
_up = (os.environ.get("HPR_UPSTREAM") or "127.0.0.1:9119").rpartition(":")
UPSTREAM = (_up[0] or "127.0.0.1", int(_up[2] or 9119))
PAIR_TTL = int(os.environ.get("HPR_PAIR_TTL") or 600)          # 配对链接有效期（秒）
CLAIM_TTL = int(os.environ.get("HPR_CLAIM_TTL") or 120)       # 批准后多久内必须点进来
HERMES_HOME = Path(os.environ.get("HERMES_HOME") or (Path.home() / "AppData" / "Local" / "hermes"))
HERMES_AGENT = Path(os.environ.get("HERMES_AGENT_DIR") or (HERMES_HOME / "hermes-agent"))
STATE_PATH = Path(os.environ.get("HPR_STATE") or (HERMES_HOME / "phone-remote" / "pair.json"))
_lock = threading.Lock()

# ---------------------------------------------------------------- 状态文件
# 面板（另一个进程）和本反代共享同一份小 json：面板写 approved/denied，这里读。
# ponytail: 单文件 + 进程内锁够用；多面板进程并发再说。

def _read_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_state(data: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, STATE_PATH)


def _token_status(state: dict, token: str) -> str:
    if not token or not state.get("token") or not hmac.compare_digest(str(state["token"]), token):
        return "invalid"
    if state.get("status") == "claimed":
        return "claimed"
    if time.time() > float(state.get("expires") or 0):
        return "expired"
    return str(state.get("status") or "pending")


# ---------------------------------------------------------------- 签发官方 session
def _mint_set_cookie_headers() -> list[tuple[str, str]]:
    """用官方 BasicAuthProvider 签一个合法 session，返回 Set-Cookie 头。

    复用官方模块（而不是自己拼 payload）——cookie 名带 ``__Host-`` 前缀、属性、HMAC
    payload 格式全归官方管，升级跟着走，这里只负责取 secret 和调函数。
    """
    if str(HERMES_AGENT) not in sys.path:
        sys.path.insert(0, str(HERMES_AGENT))
    import yaml  # noqa: PLC0415
    from plugins.dashboard_auth.basic import (  # noqa: PLC0415
        BasicAuthProvider, _resolve_secret, hash_password)
    from fastapi.responses import Response  # noqa: PLC0415
    from hermes_cli.dashboard_auth.cookies import set_session_cookies  # noqa: PLC0415

    env = os.environ.get
    cfg = yaml.safe_load((HERMES_HOME / "config.yaml").read_text(encoding="utf-8")) or {}
    section = dict(((cfg.get("dashboard") or {}).get("basic_auth") or {}))
    if env("HERMES_DASHBOARD_BASIC_AUTH_SECRET"):
        section["secret"] = env("HERMES_DASHBOARD_BASIC_AUTH_SECRET")
    username = env("HERMES_DASHBOARD_BASIC_AUTH_USERNAME") or str(section.get("username") or "")
    password_hash = env("HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH") or str(section.get("password_hash") or "")
    if not password_hash:
        plain = env("HERMES_DASHBOARD_BASIC_AUTH_PASSWORD") or str(section.get("password") or "")
        password_hash = hash_password(plain) if plain else ""
    if not (username and password_hash and section.get("secret")):
        raise RuntimeError("面板还没设账号密码（dashboard.basic_auth），先在面板里设一次再配对")
    # 关键：config 里的 secret 是 base64，官方 _resolve_secret 解码后才当 HMAC key。
    # 直接拿字符串签名 → 官方验不过 → 401（踩过这个坑）。
    secret = _resolve_secret(section)
    ttl = int(str(section.get("session_ttl_seconds") or 43200) or 43200)
    provider = BasicAuthProvider(username=username, password_hash=password_hash,
                                 secret=secret, ttl_seconds=ttl)
    session = provider._mint_session(username)  # noqa: SLF001 — 官方的签发入口就这一个
    resp = Response()
    set_session_cookies(resp, access_token=session.access_token,
                        refresh_token=session.refresh_token,
                        access_token_expires_in=ttl, use_https=True, provider=provider.name)
    return [(k.decode(), v.decode()) for k, v in resp.raw_headers
            if k.decode().lower() == "set-cookie"]


# ---------------------------------------------------------------- 手机页面
_PAGE = """<!doctype html><html lang="zh"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>连接 Hermes</title><style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;
background:#111318;color:#e8e8ea;font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif;padding:24px}
.card{width:100%;max-width:380px;background:#1a1d24;border:1px solid #2a2f3a;border-radius:18px;padding:26px 22px;text-align:center}
h1{margin:0 0 6px;font-size:19px;font-weight:600}
p{margin:8px 0 0;color:#9aa3b2;font-size:14px}
.spin{width:34px;height:34px;margin:20px auto 4px;border:3px solid #2a2f3a;border-top-color:#7c8cff;border-radius:50%;animation:s .9s linear infinite}
@keyframes s{to{transform:rotate(360deg)}}
.mark{font-size:40px;line-height:1;margin:14px 0 2px}
.bad{color:#ff8a8a}.ok{color:#7ddc9a}
.addr{margin-top:16px;font:12px ui-monospace,monospace;color:#6b7484;word-break:break-all}
</style><div class="card" id="c"><h1>连接 Hermes</h1><div class="spin"></div>
<p id="m">正在等待电脑端批准…</p><p class="addr">__ADDR__</p></div>
<script>
var t="__TOKEN__",el=document.getElementById("m"),box=document.getElementById("c"),n=0;
function stop(html,cls){box.innerHTML=html;if(cls)el.className=cls}
function tick(){
 fetch("/pair/state?t="+encodeURIComponent(t),{cache:"no-store"}).then(function(r){return r.json()}).then(function(j){
  if(j.status==="approved"){el.textContent="已批准，正在进入…";location.replace("/pair/claim?t="+encodeURIComponent(t));return}
  if(j.status==="denied"){stop('<div class="mark bad">✕</div><h1 class="bad">已被拒绝</h1><p>在电脑上重新生成配对链接。</p>');return}
  if(j.status==="expired"||j.status==="invalid"||j.status==="claimed"){
   stop('<div class="mark bad">⌛</div><h1 class="bad">链接已失效</h1><p>配对链接是一次性的，请在电脑上重新生成。</p>');return}
  n++;if(n%5===0)el.textContent="仍在等待电脑端批准…";
  setTimeout(tick,1000);
 }).catch(function(){setTimeout(tick,2000)});
}
tick();
</script></html>"""


def _page(token: str, host: str) -> bytes:
    return (_PAGE.replace("__TOKEN__", token).replace("__ADDR__", host)).encode("utf-8")


_INVALID_PAGE = ("""<!doctype html><html lang="zh"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>链接已失效</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#111318;color:#e8e8ea;
font:16px/1.6 system-ui,sans-serif;padding:24px;text-align:center}.card{max-width:380px;background:#1a1d24;
border:1px solid #2a2f3a;border-radius:18px;padding:26px 22px}h1{font-size:19px;margin:0 0 6px;color:#ff8a8a}
p{color:#9aa3b2;font-size:14px;margin:8px 0 0}</style><div class="card"><div style="font-size:40px">⌛</div>
<h1>链接已失效</h1><p>配对链接是一次性的，过期或用过就作废。请在电脑上重新生成。</p></div></html>""").encode("utf-8")


# ---------------------------------------------------------------- HTTP 小工具
def _respond(conn: socket.socket, status: str, body: bytes, *,
             ctype: str = "", extra: list[tuple[str, str]] | None = None) -> None:
    head = [f"HTTP/1.1 {status}", f"Content-Length: {len(body)}", "Cache-Control: no-store",
            "Connection: close", "Referrer-Policy: no-referrer", "X-Content-Type-Options: nosniff"]
    if ctype:
        head.append(f"Content-Type: {ctype}")
    for k, v in extra or []:
        head.append(f"{k}: {v}")
    conn.sendall(("\r\n".join(head) + "\r\n\r\n").encode("latin-1") + body)


def _json(conn: socket.socket, obj: dict) -> None:
    _respond(conn, "200 OK", json.dumps(obj).encode(), ctype="application/json")


def _serve_pair(conn: socket.socket, target: str, headers: bytes) -> None:
    url = urlsplit(target)
    path = url.path.rstrip("/") or "/pair"
    query = parse_qs(url.query)
    token = (query.get("t") or [""])[0]
    with _lock:
        state = _read_state()
        status = _token_status(state, token)
        if status == "pending" and path in ("/pair", "/pair/state"):
            ip, ua = _client_of(headers)
            # 只在拿到值时更新：手机页轮询/其他客户端可能不带 UA，别把已记下的覆盖成空。
            if ip and state.get("ip") != ip:
                state["ip"] = ip
            if ua and state.get("ua") != ua:
                state["ip"], state["ua"] = ip, ua
            state["seen"] = time.time()
            _write_state(state)
        elif status == "approved" and path == "/pair/state":
            state["seen"] = time.time()
            _write_state(state)

    if path == "/pair/state":
        return _json(conn, {"status": status})
    if path == "/pair/claim":
        if status != "approved":
            return _respond(conn, "200 OK", _INVALID_PAGE, ctype="text/html; charset=utf-8")
        if time.time() - float(state.get("approved_at") or 0) > CLAIM_TTL:
            return _respond(conn, "200 OK", _INVALID_PAGE, ctype="text/html; charset=utf-8")
        try:
            cookies = _mint_set_cookie_headers()
        except Exception as exc:  # noqa: BLE001 — 面板没配密码等，直说
            msg = f"签发失败：{exc}".encode()
            return _respond(conn, "500 Internal Server Error", msg, ctype="text/plain; charset=utf-8")
        with _lock:
            state = _read_state()
            # 保留 token 字段（本机文件，下一次生成就覆盖），只把状态置 claimed ——
            # 手机再刷新看到「链接已失效」，面板能显示「已使用」。
            state.update(status="claimed", claimed_at=time.time())
            _write_state(state)
        return _respond(conn, "302 Found", b"", extra=[("Location", "/"), *cookies])
    if path == "/pair":
        # denied 也要把页面给出去：手机那边由页面 JS 显示「已被拒绝」，
        # 直接抛失效页会让用户以为是链接坏了。
        if status in ("pending", "approved", "denied"):
            host = (headers.split(b"\r\nHost: ")[-1].split(b"\r\n")[0].decode("latin-1")
                    if b"\r\nHost: " in headers else "")
            return _respond(conn, "200 OK", _page(token, host), ctype="text/html; charset=utf-8")
        return _respond(conn, "200 OK", _INVALID_PAGE, ctype="text/html; charset=utf-8")
    _respond(conn, "404 Not Found", b"not found", ctype="text/plain; charset=utf-8")


def _client_of(headers: bytes) -> tuple[str, str]:
    """手机 IP / UA（面板上给用户看一眼「是不是这台手机」）。"""
    ip, ua = "", ""
    real = re.search(rb"\r\nX-Forwarded-For: *([^\r\n]+)", headers, re.I)
    if real:
        ip = real.group(1).decode("latin-1").split(",")[0].strip()
    if not ip:
        cf = re.search(rb"\r\nCF-Connecting-IP: *([^\r\n]+)", headers, re.I)
        ip = cf.group(1).decode("latin-1").strip() if cf else ""
    m = re.search(rb"\r\nUser-Agent: *([^\r\n]+)", headers, re.I)
    ua = m.group(1).decode("latin-1").strip() if m else ""
    return ip[:64], ua[:160]


# ---------------------------------------------------------------- 透传
def _pump(a: socket.socket, b: socket.socket) -> None:
    a.setblocking(False)
    b.setblocking(False)
    socks = (a, b)
    while True:
        try:
            ready, _, _ = select.select(socks, (), (), 300)
        except (OSError, ValueError):
            return
        if not ready:
            return
        for s in ready:
            other = b if s is a else a
            try:
                data = s.recv(65536)
            except (BlockingIOError, InterruptedError):
                continue
            except OSError:
                return
            if not data:
                return
            try:
                other.sendall(data)
            except OSError:
                return


def _handle(conn: socket.socket) -> None:
    up = None
    try:
        conn.settimeout(30)
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = conn.recv(65536)
            if not chunk:
                return
            buf += chunk
            if len(buf) > 262144:  # 别让畸形请求撑爆内存
                return
        head, _, rest = buf.partition(b"\r\n\r\n")
        line = head.split(b"\r\n", 1)[0].decode("latin-1")
        parts = line.split(" ")
        if len(parts) < 2:
            return
        if parts[1].split("?")[0].split("/")[1:2] == ["pair"]:
            return _serve_pair(conn, parts[1], head)
        up = socket.create_connection(UPSTREAM, timeout=10)
        up.sendall(head + b"\r\n\r\n" + rest)
        conn.settimeout(None)
        _pump(conn, up)
    except (OSError, ValueError):
        pass
    finally:
        for s in (up, conn):
            try:
                if s is not None:
                    s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                if s is not None:
                    s.close()
            except OSError:
                pass


def main() -> None:
    if not STATE_PATH.parent.exists():
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", PORT))
    srv.listen(64)
    print(f"pair-proxy listening 127.0.0.1:{PORT} -> {UPSTREAM[0]}:{UPSTREAM[1]}", flush=True)
    while True:
        try:
            conn, _ = srv.accept()
        except OSError:
            break
        threading.Thread(target=_handle, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()
