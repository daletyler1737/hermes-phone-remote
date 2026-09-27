"""反代两个致命回归：①版本握手（面板靠它认出跑旧代码的进程）②links 分模式格式的 token 校验。

背景：面板从 per-mode 改造后写 `state["links"][mode]`，但 9121 上跑着一个改造前的旧进程
（12:49 启动），旧校验只认平格式 → 手机扫码一直显示「链接已失效」。这个测试把两种情况都钉住。

跑：python tests/test_pair_proxy_ver.py
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "tools" / "pair_proxy.py"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(port: int, path: str) -> str:
    with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=5) as r:
        return r.read().decode("utf-8", "replace")


def demo() -> None:
    port = _free_port()
    tok = "tok-abcdefghijklmnopq"
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "pair.json"
        state.write_text(json.dumps({"links": {
            "approve": {"token": tok, "status": "pending",
                        "created": time.time(), "expires": time.time() + 600},
            "password": {"token": "other-0000000000000", "status": "pending",
                         "created": time.time(), "expires": time.time() + 600},
        }}), encoding="utf-8")
        env = dict(os.environ, HPR_PORT=str(port), HPR_STATE=str(state), HPR_UPSTREAM="127.0.0.1:9")
        proc = subprocess.Popen([sys.executable, str(SCRIPT)], env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(40):
                try:
                    _get(port, "/pair/_ver")
                    break
                except OSError:
                    time.sleep(0.25)
            ver = json.loads(_get(port, "/pair/_ver"))
            assert abs(ver["mtime"] - os.path.getmtime(SCRIPT)) < 1e-6, ver   # 面板靠这个 mtime 判新旧
            assert json.loads(_get(port, "/pair/state?t=" + tok))["status"] == "pending"   # links 格式必须认得
            assert json.loads(_get(port, "/pair/state?t=" + "x" * 24))["status"] == "invalid"
            assert "等待电脑端批准" in _get(port, "/pair?t=" + tok)           # 扫码页不是「链接已失效」
        finally:
            proc.terminate()
            proc.wait(timeout=10)
    print("pair-proxy: _ver + links-format token OK")


if __name__ == "__main__":
    demo()
