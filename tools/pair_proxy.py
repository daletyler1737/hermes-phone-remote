#!/usr/bin/env python3
"""手机扫码配对反代 (Phone pairing reverse proxy)。

为什么需要它：Hermes 官方 dashboard 的 auth gate 拦下所有插件路由（公开白名单只有
``/login``、``/auth/*``、几个静态目录），公网隧道域名下没有一个"任何人都能打开"的页面
能给手机种登录 cookie。所以「扫码 → 电脑批准 → 手机免密进去」这件事只能自己做一层：
本进程接管 ``/pair*``；其余请求只有**已批准设备**才透传到 dashboard，其它一律 403。

职责
----
``/pair?t=TOKEN``      手机落地页，按配对的 ``mode`` 分岔：
                       - ``approve``（批准模式）：等待批准页，轮询状态
                       - ``password``（账号密码模式）：登录表单，强制输面板账号密码
``/pair/state?t=TOKEN`` 轮询状态 JSON（批准模式用）
``/pair/claim?t=TOKEN`` 批准后签发官方 session cookie 并 302 进主页（一次性，仅批准模式）
``/pair/login``        账号密码模式的登录提交（POST 表单）→ 验过即签 cookie 302 进去
其它一切               只有带有效面板 session cookie 的请求才透传（chunked / SSE /
                       WebSocket 不受影响）；没 cookie 的一律 403

两种模式为什么要拆开（用户要求）：批准模式 = 电脑点一下、手机免密；账号密码模式 = 电脑
不用管、手机必须自己输账号密码。模式是**服务端状态**（写进 ``pair.json``），手机端改不了，
所以「账号密码模式的二维码强制走账号登录」是强制的；两种模式各自独立生成、独立扫码。

安全模型（对齐用户红线「不要永久不变 安全性要高」「每次 token 要变」「只有批准的设备才可以」）
--------------------------------------------------------------------------------
* token 32 字符随机，每次生成都覆盖旧的（生成即失效），默认 10 分钟有效；模式与它无关
* 批准模式下必须电脑端点「批准」才签发 cookie；claim 一次即焚
* 账号密码模式复用官方 ``BasicAuthProvider.complete_password_login()`` 验密码（scrypt +
  定长比较），同一 CF-Connecting-IP 10 分钟内错 5 次 → 429（官方 auth 插件没有挂点做限速，
  我们自己的表单有，顺手补上）
* cookie 值用官方 ``BasicAuthProvider`` 签发（同一 HMAC secret），因此官方 auth 认它
* **未批准设备拿不到面板的任何东西**：隧道域名不是面板的第二个入口 —— 没有有效 session
  cookie 的请求（含 ``/login``、``/auth/*``）在这里就 403，登录页只存在于局域网面板上
* 只监听 127.0.0.1；对外只有 cloudflared 隧道能碰到它

手机会话与配对 token 解耦（「token 十分钟一变，扫码那台设备要长期稳定」）
----------------------------------------------------------------------
配对成功后手机拿的是官方 session cookie：access 12h、refresh 30 天且**滑动续期**（面板每次
续签重算 30 天）。token 轮换、隧道断开重开、面板重写 ``pair.json`` 都不动老 cookie 的合法性
（同一个 secret），所以手机不用重新扫；接入时 access 过期了也没事 —— 门禁认 refresh，透传上去
面板自己续签。唯一会把手机踢掉的是**改面板密码/secret**（签名 key 变了）。

跑法：``python pair_proxy.py``；环境变量 ``HPR_PORT`` / ``HPR_UPSTREAM`` / ``HPR_STATE``。
"""
from __future__ import annotations

import hmac
import html
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


def _link(state: dict, token: str) -> dict:
    """这个 token 属于哪条链接：新格式 ``state["links"]``，老的单条平格式就直接是 state。

    返回的是 state 里的同一个对象，改它再 `_write_state(state)` 就落盘了（两种模式各一条，
    互不干扰 —— 用户要求「批准版和密码版分开生成」）。找不到就返回空 dict。
    """
    links = state.get("links")
    if not isinstance(links, dict):
        return state
    for entry in links.values():
        if isinstance(entry, dict) and entry.get("token") and hmac.compare_digest(str(entry["token"]), token):
            return entry
    return {}


def _token_status(state: dict, token: str) -> str:
    if not token or not state.get("token") or not hmac.compare_digest(str(state["token"]), token):
        return "invalid"
    if state.get("status") == "claimed":
        return "claimed"
    if time.time() > float(state.get("expires") or 0):
        return "expired"
    return str(state.get("status") or "pending")


# ---------------------------------------------------------------- 签发官方 session
def _provider():
    """按面板同一份配置造官方 provider，返回 ``(provider, secret)``；面板没设账号密码则 None。

    claim 的签发和门禁的校验共用这一份 —— 只有这里读 config，用户在面板里改了密码不需要
    重启反代。ponytail: 每次调用都读一次 config.yaml（毫秒级，单用户面板够用）；真要压
    这个开销就按 mtime 缓存。
    """
    if str(HERMES_AGENT) not in sys.path:
        sys.path.insert(0, str(HERMES_AGENT))
    import yaml  # noqa: PLC0415
    from plugins.dashboard_auth.basic import (  # noqa: PLC0415
        BasicAuthProvider, _resolve_secret, hash_password)

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
        return None
    # 关键：config 里的 secret 是 base64，官方 _resolve_secret 解码后才当 HMAC key。
    # 直接拿字符串签名 → 官方验不过 → 401（踩过这个坑）。
    secret = _resolve_secret(section)
    ttl = int(str(section.get("session_ttl_seconds") or 43200) or 43200)
    return BasicAuthProvider(username=username, password_hash=password_hash,
                             secret=secret, ttl_seconds=ttl), secret


def _mint_set_cookie_headers() -> list[tuple[str, str]]:
    """用官方 BasicAuthProvider 签一个合法 session，返回 Set-Cookie 头。

    复用官方模块（而不是自己拼 payload）——cookie 名带 ``__Host-`` 前缀、属性、HMAC
    payload 格式全归官方管，升级跟着走，这里只负责取 secret 和调函数。
    """
    from fastapi.responses import Response  # noqa: PLC0415
    from hermes_cli.dashboard_auth.cookies import set_session_cookies  # noqa: PLC0415

    built = _provider()
    if built is None:
        raise RuntimeError("面板还没设账号密码（dashboard.basic_auth），先在面板里设一次再配对")
    provider, _secret = built
    ttl = provider._ttl       # noqa: SLF001 — 官方把 ttl 收在私有属性里，就这一个来源
    session = provider._mint_session(provider._username)  # noqa: SLF001 — 官方签发入口
    resp = Response()
    set_session_cookies(resp, access_token=session.access_token,
                        refresh_token=session.refresh_token,
                        access_token_expires_in=ttl, use_https=True, provider=provider.name)
    return [(k.decode(), v.decode()) for k, v in resp.raw_headers
            if k.decode().lower() == "set-cookie"]


def _approved_device(head: bytes) -> bool:
    """这条请求带没带一个验得过的官方 session cookie（= 已批准设备）。

    隧道域名不是「面板的第二个入口」：只有已批准设备的请求能透传到上游，其它一律 403 ——
    未批准设备连登录页、/auth/* 都拿不到（用户红线：只有批准的设备才可以）。cookie 名不写死，
    挨个值验签名，官方哪天改名这里也不用动。
    """
    m = re.search(rb"\r\ncookie: *([^\r\n]+)", head, re.I)
    if not m:
        return False
    built = _provider()
    if built is None:
        return False          # 面板没配密码 → 门禁失败关闭，什么都不给
    provider, _secret = built
    for kv in m.group(1).decode("latin-1").split(";"):
        if "=" not in kv:
            continue
        val = kv.split("=", 1)[1].strip()
        if provider.verify_session(access_token=val):
            return True
        # refresh 也算「已批准设备」：access 到期后手机带着 refresh 过来，透传上去面板自己会
        # 续签。官方 refresh_session 是无状态 _unsign+_mint（不轮换、不消耗），当纯校验用。
        try:
            provider.refresh_session(refresh_token=val)
            return True
        except Exception:  # noqa: BLE001 — 无效/过期/形状不对，都算没批准
            continue
    return False


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


_SAFE_TOKEN = re.compile(r"[A-Za-z0-9_\-]{16,128}")   # secrets.token_urlsafe 的字符集


def _page(token: str, host: str) -> bytes:
    """配对页：token 与 Host 都是外部输入，落 HTML 前先收敛。

    token 走 URL-safe 白名单（不合规就当空串，反正也匹配不到状态），Host 直接
    html-escape —— 这两个位置是反射型 XSS 的入口（Host 由客户端随便填）。
    """
    tok = token if _SAFE_TOKEN.fullmatch(token) else ""
    return (_PAGE.replace("__TOKEN__", html.escape(tok, quote=True))
                 .replace("__ADDR__", html.escape(host[:120], quote=True))).encode("utf-8")


_INVALID_PAGE = ("""<!doctype html><html lang="zh"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>链接已失效</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#111318;color:#e8e8ea;
font:16px/1.6 system-ui,sans-serif;padding:24px;text-align:center}.card{max-width:380px;background:#1a1d24;
border:1px solid #2a2f3a;border-radius:18px;padding:26px 22px}h1{font-size:19px;margin:0 0 6px;color:#ff8a8a}
p{color:#9aa3b2;font-size:14px;margin:8px 0 0}</style><div class="card"><div style="font-size:40px">⌛</div>
<h1>链接已失效</h1><p>配对链接是一次性的，过期或用过就作废。请在电脑上重新生成。</p></div></html>""").encode("utf-8")


# ---------------------------------------------------------------- 手机页面（账号密码模式）
_LOGIN_PAGE = """<!doctype html><html lang="zh"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>登录 Hermes</title><style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;
background:#111318;color:#e8e8ea;font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}
.card{width:100%;max-width:380px;padding:26px 22px;background:#1a1d24;border:1px solid #2a2f3a;border-radius:18px}
h1{margin:0;font-size:19px;font-weight:600;text-align:center}
p{margin:8px 0 0;color:#9aa3b2;font-size:13px;text-align:center}
label{display:block;margin:16px 0 6px;color:#9aa3b2;font-size:13px}
input{width:100%;padding:12px;font-size:16px;color:#e8e8ea;background:#111318;border:1px solid #2a2f3a;border-radius:10px}
button{width:100%;margin-top:22px;padding:13px;font-size:16px;font-weight:600;color:#fff;background:#5b67ca;border:0;border-radius:10px}
.err{margin:14px 0 0;color:#ff8a8a}
.addr{margin-top:18px;color:#6b7484;font:12px ui-monospace,SFMono-Regular,monospace;word-break:break-all}
</style><form class="card" method="post" action="/pair/login">
<input type="hidden" name="t" value="__TOKEN__">
<h1>登录 Hermes</h1><p>这台手机要进的面板：</p><p class="addr">__ADDR__</p>
<label for="hp-u">账号</label>
<input id="hp-u" name="username" autocomplete="username" autocapitalize="off" spellcheck="false" required>
<label for="hp-p">密码</label>
<input id="hp-p" name="password" type="password" autocomplete="current-password" required>
__ERR__
<button type="submit">登录</button></form></html>"""


def _login_page(token: str, host: str, err: str = "") -> bytes:
    """账号密码模式的登录页。token/Host/错误文案都是外部输入，落 HTML 前收敛。"""
    tok = token if _SAFE_TOKEN.fullmatch(token) else ""
    return (_LOGIN_PAGE.replace("__TOKEN__", html.escape(tok, quote=True))
                      .replace("__ADDR__", html.escape(host[:120], quote=True))
                      .replace("__ERR__", f'<p class="err">{html.escape(err[:120])}</p>' if err else "")
           ).encode("utf-8")


# 登录失败限速（官方 auth 插件没有挂点，我们自己这张表单有 —— 顺便补上）：
# 按 CF-Connecting-IP 计数，10 分钟错 5 次就 429。进程内内存计数，重启即清。
LOGIN_MAX_FAILS = int(os.environ.get("HPR_LOGIN_MAX_FAILS") or 5)
LOGIN_FAIL_WINDOW = float(os.environ.get("HPR_LOGIN_FAIL_WINDOW") or 600)
_login_fails: dict[str, list[float]] = {}


def _login_blocked(ip: str) -> bool:
    now = time.time()
    hits = [t for t in _login_fails.get(ip or "-", []) if now - t < LOGIN_FAIL_WINDOW]
    _login_fails[ip or "-"] = hits
    return len(hits) >= LOGIN_MAX_FAILS


def _login_failed(ip: str) -> None:
    _login_fails.setdefault(ip or "-", []).append(time.time())


def _body_of(conn: socket.socket, head: bytes, rest: bytes) -> bytes:
    """把请求体读全（只有登录表单走这里，上限 4 KiB）。"""
    m = re.search(rb"\r\nContent-Length: *(\d+)", head, re.I)
    want = min(int(m.group(1)), 4096) if m else 0
    while len(rest) < want:
        try:
            chunk = conn.recv(4096)
        except OSError:
            break
        if not chunk:
            break
        rest += chunk
    return rest[:want]


def _host_of(headers: bytes) -> str:
    if b"\r\nHost: " not in headers:
        return ""
    return headers.split(b"\r\nHost: ")[-1].split(b"\r\n")[0].decode("latin-1")


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


def _serve_pair(conn: socket.socket, target: str, headers: bytes, body: bytes = b"") -> None:
    url = urlsplit(target)
    path = url.path.rstrip("/") or "/pair"
    query = parse_qs(url.query)
    token = (query.get("t") or [""])[0]
    host = _host_of(headers)
    if path == "/pair/login":
        return _serve_login(conn, token, headers, body)
    with _lock:
        state = _read_state()
        entry = _link(state, token)
        mode = str(entry.get("mode") or "approve")
        status = _token_status(entry, token)
        if status == "pending" and path in ("/pair", "/pair/state"):
            ip, ua = _client_of(headers)
            # 只在拿到值时更新：手机页轮询/其他客户端可能不带 UA，别把已记下的覆盖成空。
            if ip and entry.get("ip") != ip:
                entry["ip"] = ip
            if ua and entry.get("ua") != ua:
                entry["ip"], entry["ua"] = ip, ua
            entry["seen"] = time.time()
            _write_state(state)
        elif status == "approved" and path == "/pair/state":
            entry["seen"] = time.time()
            _write_state(state)

    if path == "/pair/state":
        return _json(conn, {"status": status})
    if path == "/pair/claim":
        if status != "approved":
            return _respond(conn, "200 OK", _INVALID_PAGE, ctype="text/html; charset=utf-8")
        if time.time() - float(entry.get("approved_at") or 0) > CLAIM_TTL:
            return _respond(conn, "200 OK", _INVALID_PAGE, ctype="text/html; charset=utf-8")
        try:
            cookies = _mint_set_cookie_headers()
        except Exception as exc:  # noqa: BLE001 — 面板没配密码等，直说
            msg = f"签发失败：{exc}".encode()
            return _respond(conn, "500 Internal Server Error", msg, ctype="text/plain; charset=utf-8")
        with _lock:
            fresh = _read_state()
            # 保留 token 字段（本机文件，下一次生成就覆盖），只把状态置 claimed ——
            # 手机再刷新看到「链接已失效」，面板能显示「已使用」。
            _link(fresh, token).update(status="claimed", claimed_at=time.time())
            _write_state(fresh)
        return _respond(conn, "302 Found", b"", extra=[("Location", "/"), *cookies])
    if path == "/pair":
        if mode == "password":
            # 账号密码模式：二维码/链接直接落在登录表单上，电脑端不参与（用户要求强制账号登录）
            if status == "pending":
                return _respond(conn, "200 OK", _login_page(token, host), ctype="text/html; charset=utf-8")
            return _respond(conn, "200 OK", _INVALID_PAGE, ctype="text/html; charset=utf-8")
        # denied 也要把页面给出去：手机那边由页面 JS 显示「已被拒绝」，
        # 直接抛失效页会让用户以为是链接坏了。
        if status in ("pending", "approved", "denied"):
            return _respond(conn, "200 OK", _page(token, host), ctype="text/html; charset=utf-8")
        return _respond(conn, "200 OK", _INVALID_PAGE, ctype="text/html; charset=utf-8")
    _respond(conn, "404 Not Found", b"not found", ctype="text/plain; charset=utf-8")


def _login_and_mint(username: str, password: str) -> list[tuple[str, str]]:
    """验面板账号密码，过了就签一份和批准模式同款的 session cookie。

    校验交给官方 ``complete_password_login``（scrypt + 定长比较 + 不泄露账号是否存在），
    不自己碰密码 hash。cookie 走 ``_mint_set_cookie_headers``，和批准模式同一条路。
    """
    built = _provider()
    if built is None:
        raise RuntimeError("面板还没设账号密码")
    provider, _secret = built
    provider.complete_password_login(username=username, password=password)
    return _mint_set_cookie_headers()


def _serve_login(conn: socket.socket, token: str, headers: bytes, body: bytes) -> None:
    """账号密码模式的 /pair/login：GET/空表单出登录页，POST 验密码过了直接进面板。

    浏览器 form 提交不会带 ``?t=``，token 在表单体里，所以先读体再定 token。
    """
    host = _host_of(headers)
    body = _body_of(conn, headers, body)
    form = {k: v[0] for k, v in parse_qs(body.decode("utf-8", "replace")).items()}
    token = token or str(form.get("t") or "")
    with _lock:
        state = _read_state()
        entry = _link(state, token)
        mode = str(entry.get("mode") or "approve")
        status = _token_status(entry, token)
        if status == "pending":
            ip, ua = _client_of(headers)
            if ip:
                entry["ip"] = ip
            if ua:
                entry["ua"] = ua
            entry["seen"] = time.time()
            _write_state(state)

    # 模式不对（这个 token 是批准模式的）或链接作废：给失效页，不泄露任何信息
    if mode != "password" or status != "pending":
        return _respond(conn, "200 OK", _INVALID_PAGE, ctype="text/html; charset=utf-8")
    if not form.get("username") and not form.get("password"):
        return _respond(conn, "200 OK", _login_page(token, host), ctype="text/html; charset=utf-8")

    ip, _ua = _client_of(headers)
    if _login_blocked(ip):
        return _respond(conn, "429 Too Many Requests",
                        _login_page(token, host, "错误次数太多，过 10 分钟再试"),
                        ctype="text/html; charset=utf-8")
    try:
        cookies = _login_and_mint(str(form.get("username") or ""), str(form.get("password") or ""))
    except Exception:  # noqa: BLE001 — 失败理由统一成一句话，别提示账号存不存在
        _login_failed(ip)
        return _respond(conn, "200 OK", _login_page(token, host, "账号或密码不对"),
                        ctype="text/html; charset=utf-8")
    with _lock:
        fresh = _read_state()
        _link(fresh, token).update(status="claimed", claimed_at=time.time(), claimed_by="password")
        _write_state(fresh)
    return _respond(conn, "302 Found", b"", extra=[("Location", "/"), *cookies])


def _client_of(headers: bytes) -> tuple[str, str]:
    """手机 IP / UA（面板上给用户看一眼「是不是这台手机」）。"""
    ip, ua = "", ""
    # CF-Connecting-IP 由 Cloudflare 写入，客户端伪造不了；X-Forwarded-For 是客户端可填的，
    # 所以它只能当兜底 —— 这个 IP 是用户用来确认「是不是我这台手机」的依据，不能被伪造。
    cf = re.search(rb"\r\nCF-Connecting-IP: *([^\r\n]+)", headers, re.I)
    if cf:
        ip = cf.group(1).decode("latin-1").strip()
    if not ip:
        real = re.search(rb"\r\nX-Forwarded-For: *([^\r\n]+)", headers, re.I)
        if real:
            ip = real.group(1).decode("latin-1").split(",")[0].strip()
    m = re.search(rb"\r\nUser-Agent: *([^\r\n]+)", headers, re.I)
    ua = m.group(1).decode("latin-1").strip() if m else ""
    return ip[:64], ua[:160]


# ---------------------------------------------------------------- 透传
def _pipe(src: socket.socket, dst: socket.socket) -> None:
    """单向搬运。阻塞 recv/sendall：sendall 自带背压等待，不会丢数据。"""
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try:
            # 半关：只结束这个方向，另一个方向接着收（客户端半关请求体是常态）
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def _pump(a: socket.socket, b: socket.socket) -> None:
    """双向透传：两条阻塞线程，各管一个方向。

    别改回 select + 非阻塞 sendall（踩过）：对端读得慢时（手机加载大资源、
    cloudflared 反压）非阻塞 sendall 抛 BlockingIOError，被 except OSError 吞掉 →
    连接半路关闭 → cloudflared 报 "Failed to proxy HTTP: unexpected EOF"，手机白屏。
    """
    other = threading.Thread(target=_pipe, args=(b, a), daemon=True)
    other.start()
    _pipe(a, b)
    other.join(timeout=10)


def _one_shot(head: bytes) -> bytes:
    """透传请求改成 Connection: close（Upgrade 请求不动，WebSocket 要它）。

    踩过：透传是裸字节管道，上游若保持 keep-alive，这条连接就被"钉"在面板上 ——
    cloudflared 复用同一条连接再发 /pair* 时不再经过上面的路由（裸转发），手机配对页
    就永远停在「等待批准」。一次性用完就关，下个请求必然重新进来过路由。
    """
    if re.search(rb"\r\nupgrade:", head, re.I):
        return head
    keep = [ln for ln in head.split(b"\r\n") if not re.match(rb"(proxy-)?connection:", ln, re.I)]
    return b"\r\n".join(keep + [b"Connection: close"])


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
        # 认路径要同时吃「源站式 /pair/...」和「绝对式 https://host/pair/...」：cloudflared
        # 会发绝对式，漏认就被当普通请求透传给面板 → 手机轮询拿到 302/登录页 → 永远等批准。
        if urlsplit(parts[1]).path.rstrip("/").split("/")[1:2] == ["pair"]:
            return _serve_pair(conn, parts[1], head, rest)
        # 门禁：隧道域名对未批准设备什么都不是 —— 面板、登录页、静态资源一并拦在这里。
        if not _approved_device(head):
            return _respond(conn, "403 Forbidden", b"forbidden: this device is not paired",
                            ctype="text/plain; charset=utf-8")
        up = socket.create_connection(UPSTREAM, timeout=10)
        up.settimeout(None)   # 建连超时用完就撤，别让 10s 读超时把长连接掐了
        up.sendall(_one_shot(head) + b"\r\n\r\n" + rest)
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
