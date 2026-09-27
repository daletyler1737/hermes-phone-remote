"""批准/登录签发的 cookie 必须和请求的协议一致，否则手机「批准了却进不去」。

``__Host-`` 前缀的 cookie 带 ``Secure``，浏览器在明文 http 上直接丢弃 → 手机上看起来就是
「已批准，但面板说我未配对」(403 not paired)。所以：
  * 隧道（``X-Forwarded-Proto: https``）→ ``__Host-`` + Secure（官方面板的形状）
  * 局域网直连 http               → 裸名（不带 Secure），浏览器才会存下来
官方门禁 ``_approved_device`` 按值验签名、不写死 cookie 名，所以裸名一样能过。

跑：<hermes venv python> tests/test_pair_cookie_scheme.py   （必须用装了 fastapi 的解释器）
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "tools" / "pair_proxy.py"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _urlopen(port: int, path: str, extra: dict | None = None):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):  # noqa: ANN002,ANN003
            return None

    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), headers=extra or {})
    try:
        return opener.open(req, timeout=5)
    except urllib.error.HTTPError as exc:
        return exc


def _claim(port: int, path: str, extra: dict | None = None) -> tuple[bytes, list[str]]:
    """打一次 claim（token 一次即焚，所以体内和 cookie 头要一次拿完）。"""
    resp = _urlopen(port, path, extra)
    body = resp.read()
    return body, [c.split("=")[0] for c in (resp.headers.get_all("Set-Cookie") or [])]


def demo() -> None:
    port = _free_port()
    tok = "tok-abcdefghijklmnopq"
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "pair.json"
        now = time.time()
        state.write_text(json.dumps({"links": {"approve": {
            "token": tok, "mode": "approve", "status": "approved",
            "created": now, "expires": now + 600, "approved_at": now,
        }}}), encoding="utf-8")
        env = dict(os.environ, HPR_PORT=str(port), HPR_STATE=str(state), HPR_UPSTREAM="127.0.0.1:9")
        proc = subprocess.Popen([sys.executable, str(SCRIPT)], env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(40):
                try:
                    _urlopen(port, "/pair/_ver")
                    break
                except OSError:
                    time.sleep(0.25)
            ver = json.loads(_urlopen(port, "/pair/_ver").read())
            assert ver.get("deps") is True, "反代跑的解释器里导不到 fastapi/官方模块：%s" % ver

            body, naked = _claim(port, "/pair/claim?t=" + tok)
            assert b"__Host-" not in body, body[:200]
            assert b"\xe7\xad\xbe\xe5\x8f\x91\xe5\xa4\xb1\xe8\xb4\xa5" not in body, body[:200]  # 签发失败
            assert naked and all(not n.startswith("__Host-") for n in naked), naked
            assert all(not n.startswith("__Secure-") for n in naked), naked
        finally:
            proc.terminate()
            proc.wait(timeout=10)

    # 再来一遍，这次装成隧道请求（cloudflared 会加 X-Forwarded-Proto）
    port = _free_port()
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "pair.json"
        now = time.time()
        state.write_text(json.dumps({"links": {"approve": {
            "token": tok, "mode": "approve", "status": "approved",
            "created": now, "expires": now + 600, "approved_at": now,
        }}}), encoding="utf-8")
        env = dict(os.environ, HPR_PORT=str(port), HPR_STATE=str(state), HPR_UPSTREAM="127.0.0.1:9")
        proc = subprocess.Popen([sys.executable, str(SCRIPT)], env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(40):
                try:
                    _urlopen(port, "/pair/_ver")
                    break
                except OSError:
                    time.sleep(0.25)
            _, names = _claim(port, "/pair/claim?t=" + tok, {"X-Forwarded-Proto": "https"})
            assert names and all(n.startswith("__Host-") for n in names), names
        finally:
            proc.terminate()
            proc.wait(timeout=10)
    print("pair-proxy: cookie scheme (http bare / https __Host-) OK")


if __name__ == "__main__":
    demo()
